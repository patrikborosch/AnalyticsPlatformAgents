[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$modulePath = Join-Path $PSScriptRoot '..' | Join-Path -ChildPath '_lib' | Join-Path -ChildPath 'Vally.Grader.psm1'
Import-Module $modulePath -Force

# ---------------------------------------------------------------------------
# Verifier contract for the eventhouse pilot stimulus
# "Create idempotent KQL table with retention".
#
# Asserts THREE things, all of which the prompt explicitly requires:
#   1. A table named exactly $tableName exists in $expectedDatabase.
#   2. The table schema matches the expected (Name, Type) pairs EXACTLY
#      (set equality, not substring; PR #282 review theme 2).
#   3. The table has a retention policy with SoftDeletePeriod of 30 days
# (PR #282 reading-guide item #1: prompt explicitly asks for retention; the previous verifier only checked columns and produced false positives).
#
# Anything else (wrong table name, wrong column type, missing retention,
# table in wrong DB, agent never made the create call) emits passed:$false
# with a diagnostic dump that lists what is actually present so the
# author can triage from the CI artifact bundle without re-running.
# ---------------------------------------------------------------------------

$graderName = 'verify-iot-sensor-readings-table'
$tableName = 'IoTSensorReadings'
$expectedColumns = @(
    @{ Name = 'Timestamp'; Type = 'datetime' },
    @{ Name = 'DeviceId'; Type = 'string' },
    @{ Name = 'Temperature'; Type = 'real' },
    @{ Name = 'Humidity'; Type = 'real' },
    @{ Name = 'Location'; Type = 'string' }
)
$expectedRetentionDays = 30

# ---------------------------------------------------------------------------
# KQL response shape helpers. KQL-specific; live here (not in _lib) until a
# second KQL verifier shows the pattern is reusable.
# ---------------------------------------------------------------------------

function ConvertTo-KustoRows {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [object]$Response
    )

    $rows = New-Object System.Collections.Generic.List[object]
    foreach ($table in @($Response.Tables)) {
        $columns = @($table.Columns)
        foreach ($row in @($table.Rows)) {
            $item = [ordered]@{}
            for ($i = 0; $i -lt $columns.Count; $i++) {
                $columnName = $columns[$i].ColumnName
                if ([string]::IsNullOrWhiteSpace($columnName)) {
                    $columnName = $columns[$i].Name
                }
                if ([string]::IsNullOrWhiteSpace($columnName)) {
                    $columnName = "Column$i"
                }
                $rowValues = @($row)
                $value = $null
                if ($i -lt $rowValues.Count) {
                    $value = $rowValues[$i]
                }
                $item[$columnName] = $value
            }
            $rows.Add([pscustomobject]$item) | Out-Null
        }
    }
    return $rows.ToArray()
}

function Resolve-KqlDatabase {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkspaceId
    )

    $uri = "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId/kqlDatabases"
    $response = Invoke-AzRestJson -Method get -Uri $uri
    $items = @($response.value)
    if ($items.Count -eq 0) {
        throw "No KQL databases were returned for workspace '$WorkspaceId'."
    }

    $expectedDatabaseRaw = ($env:EVENTHOUSE_EXPECTED_DATABASE ?? '').Trim()
    if ([string]::IsNullOrWhiteSpace($expectedDatabaseRaw)) {
        # Match the polling-env-var contract: no silent local default
        # that drifts from eval.yaml. The only caller (eval.yaml) wires
        # this explicitly; throwing here makes a future workload-team
        # copy of this verifier surface the missing wiring immediately
        # rather than picking up the pilot's fixture name by accident.
        throw "EVENTHOUSE_EXPECTED_DATABASE must be set in the eval.yaml program-grader env block; got empty value. (contract: no silent local defaults that drift from canonical eval.yaml values)"
    }
    $expectedDatabase = $expectedDatabaseRaw
    $withQueryUri = @($items | Where-Object { $_.properties -and $_.properties.queryServiceUri })
    if ($withQueryUri.Count -eq 0) {
        throw "No KQL database in workspace '$WorkspaceId' exposed properties.queryServiceUri."
    }

    # Fabric workspace items are unique by displayName within a single
    # item type (case-insensitive on the server side), so -eq is the
    # correct match operator here for KQL DATABASE lookup. Contrast with
    # KQL TABLE NAMES (see Get-CslSchemaForTable, -cne match below):
    # table names live inside the Kusto engine where they ARE
    # case-sensitive, hence the -cne contract there.
    $matchList = @($withQueryUri | Where-Object { $_.displayName -eq $expectedDatabase } | Select-Object -First 1)
    if ($matchList.Count -eq 0) {
        $names = ($withQueryUri | ForEach-Object { $_.displayName }) -join ', '
        throw "Expected KQL database '$expectedDatabase' not found in workspace '$WorkspaceId'. Available: $names"
    }
    $selected = $matchList[0]

    [pscustomobject]@{
        DatabaseName = [string]$selected.displayName
        QueryServiceUri = ([string]$selected.properties.queryServiceUri).TrimEnd('/')
    }
}

function ConvertFrom-CslSchemaString {
    <#
    .SYNOPSIS
    Parse a KQL cslschema string into an ordered list of (Name, Type) pairs.

    .DESCRIPTION
    KQL cslschema is a comma-separated list of "Name:type" segments
    optionally wrapped in parens, e.g. "(Timestamp:datetime, DeviceId:string, ...)".
    Returns a list of pscustomobject for set-equality comparison; this
    replaces the earlier String.Contains test which let `MyTimestamp:datetime`
    satisfy a `Timestamp:datetime` assertion (PR #282 review theme 2).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$SchemaString)

    $stripped = $SchemaString.Trim().Trim('(').Trim(')').Trim()
    if ([string]::IsNullOrWhiteSpace($stripped)) { return @() }
    $segments = $stripped -split ','
    $cols = @()
    foreach ($seg in $segments) {
        $parts = $seg.Trim() -split ':', 2
        if ($parts.Count -eq 2) {
            $cols += [pscustomobject]@{
                Name = $parts[0].Trim()
                Type = $parts[1].Trim().ToLowerInvariant()
            }
        }
    }
    return ,$cols
}

function Test-SchemaSetEquality {
    <#
    .SYNOPSIS
    Compare the actual parsed schema against expected (Name, Type) pairs as a SET.

    .DESCRIPTION
    Set equality, not subset containment. An extra column on the actual
    side is a mismatch; a missing column is a mismatch; a wrong type is a
    mismatch. Returns a result object with Passed + Missing + Extra +
    TypeMismatches arrays for diagnostic evidence.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][object[]]$Actual,
        [Parameter(Mandatory = $true)][object[]]$Expected
    )

    $actualMap = @{}
    foreach ($a in $Actual) { $actualMap[[string]$a.Name] = [string]$a.Type }
    $expectedMap = @{}
    foreach ($e in $Expected) { $expectedMap[[string]$e.Name] = ([string]$e.Type).ToLowerInvariant() }

    $missing = @()
    $typeMismatches = @()
    foreach ($name in $expectedMap.Keys) {
        if (-not $actualMap.ContainsKey($name)) {
            $missing += "$name`:$($expectedMap[$name])"
        } elseif ($actualMap[$name] -ne $expectedMap[$name]) {
            $typeMismatches += "$name (expected $($expectedMap[$name]), got $($actualMap[$name]))"
        }
    }
    $extra = @()
    foreach ($name in $actualMap.Keys) {
        if (-not $expectedMap.ContainsKey($name)) {
            $extra += "$name`:$($actualMap[$name])"
        }
    }

    [pscustomobject]@{
        Passed = ($missing.Count -eq 0 -and $extra.Count -eq 0 -and $typeMismatches.Count -eq 0)
        Missing = $missing
        Extra = $extra
        TypeMismatches = $typeMismatches
    }
}

function Get-CslSchemaForTable {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][object]$Response,
        [Parameter(Mandatory = $true)][string]$ExpectedTableName
    )

    foreach ($row in (ConvertTo-KustoRows -Response $Response)) {
        # Affirmative match: only accept rows that conclusively identify
        # themselves as the expected table. Skip any row missing a
        # TableName column, missing a value, OR whose value does not
        # case-sensitively equal the expected name. The earlier
        # negative-skip (`-cne` only) would let a row with a null
        # TableName fall through and return its Schema field as though
        # it belonged to the expected table -- a false-positive pass
        # risk if the Kusto response shape ever changes upstream.
        # -ceq is the case-sensitive comparator: KQL table names are
        # case-sensitive inside the Kusto engine, so 'IotSensorReadings'
        # must NOT satisfy a check for 'IoTSensorReadings'.
        $tableColumn = $row.PSObject.Properties['TableName']
        if (-not ($tableColumn -and $tableColumn.Value -and ([string]$tableColumn.Value -ceq $ExpectedTableName))) {
            continue
        }
        foreach ($schemaPropertyName in @('Schema', 'CslSchema', 'CSLSchema')) {
            $schemaProperty = $row.PSObject.Properties[$schemaPropertyName]
            if ($schemaProperty -and -not [string]::IsNullOrWhiteSpace([string]$schemaProperty.Value)) {
                return [string]$schemaProperty.Value
            }
        }
    }
    return $null
}

function Get-RetentionPolicyDays {
    <#
    .SYNOPSIS
    Parse the .show table policy retention response and return the
    SoftDeletePeriod expressed in whole days.

    .DESCRIPTION
    KQL retention policy is returned as a JSON string under the Policy
    column. Within it, SoftDeletePeriod is a .NET TimeSpan string like
    "30.00:00:00". We parse just the leading day count.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][object]$Response)

    foreach ($row in (ConvertTo-KustoRows -Response $Response)) {
        $policyCol = $row.PSObject.Properties['Policy']
        if (-not $policyCol -or [string]::IsNullOrWhiteSpace([string]$policyCol.Value)) { continue }
        try {
            $policy = $policyCol.Value | ConvertFrom-Json -ErrorAction Stop
        } catch {
            continue
        }
        $sdp = $policy.SoftDeletePeriod
        if ([string]::IsNullOrWhiteSpace([string]$sdp)) { continue }
        $tsParts = ([string]$sdp) -split '\.'
        if ($tsParts.Count -ge 2 -and ($tsParts[0] -match '^\d+$')) {
            return [int]$tsParts[0]
        }
        # Fall back to TimeSpan.Parse for "HH:MM:SS"-only forms.
        $ts = $null
        if ([TimeSpan]::TryParse([string]$sdp, [ref]$ts)) {
            return [int][math]::Floor($ts.TotalDays)
        }
    }
    return $null
}

# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

$passed = $false
$score = 0.0
$evidence = ''
$metadata = [ordered]@{
    table = $tableName
    expectedRetentionDays = $expectedRetentionDays
}

try {
    [void](Read-EvaluateGraderInput)
    $workspaceId = Get-ResolvedWorkspaceId
    $metadata.workspaceId = Format-DiagnosticGuid -Guid $workspaceId

    $database = Resolve-KqlDatabase -WorkspaceId $workspaceId
    $metadata.database = $database.DatabaseName
    $metadata.queryServiceUri = Format-DiagnosticUri -Uri $database.QueryServiceUri

    $mgmtUri = "$($database.QueryServiceUri)/v1/rest/mgmt"

    # Polling deadline / interval: workflow + eval.yaml own the canonical
    # values via VALLY_GRADER_POLL_DEADLINE_SECONDS / _INTERVAL_SECONDS.
    # No silent local default: if the env vars are absent, throw so a
    # workload-team author hits the missing config immediately rather than
    # getting a hidden 30s default that drifts from what they wired in
    # eval.yaml (review theme: env-var fallback duplicates the canonical
    # value and drifts).
    $deadlineRaw = ($env:VALLY_GRADER_POLL_DEADLINE_SECONDS ?? '').Trim()
    if (-not ($deadlineRaw -match '^\d+$')) {
        throw "VALLY_GRADER_POLL_DEADLINE_SECONDS must be a positive integer; got '$deadlineRaw'. Set it in the eval.yaml program-grader env block."
    }
    $deadline = [int]$deadlineRaw
    $intervalRaw = ($env:VALLY_GRADER_POLL_INTERVAL_SECONDS ?? '').Trim()
    if (-not ($intervalRaw -match '^\d+$')) {
        throw "VALLY_GRADER_POLL_INTERVAL_SECONDS must be a positive integer; got '$intervalRaw'. Set it in the eval.yaml program-grader env block."
    }
    $interval = [int]$intervalRaw

    # ---- Probe 1: table schema ----
    $schemaBody = @{ db = $database.DatabaseName; csl = ".show table $tableName cslschema" } | ConvertTo-Json -Compress
    $lastKqlError = $null

    $schemaResponse = Invoke-WithPolling -Deadline $deadline -Interval $interval -ScriptBlock {
        try {
            $response = Invoke-AzRestJson -Method post -Uri $mgmtUri -Body $schemaBody
            $schemaText = Get-CslSchemaForTable -Response $response -ExpectedTableName $tableName
            if ([string]::IsNullOrWhiteSpace($schemaText)) { return $null }
            return [pscustomobject]@{ Response = $response; Schema = $schemaText }
        } catch {
            $script:lastKqlError = $_.Exception.Message
            return $null
        }
    }

    if (-not $schemaResponse) {
        # Diagnostic dump (sanitised). Tells the author whether the agent
        # created the table elsewhere, never created it, or named it wrong.
        $actualTables = @()
        try {
            $listBody = @{ db = $database.DatabaseName; csl = '.show tables' } | ConvertTo-Json -Compress
            $tablesResp = Invoke-AzRestJson -Method post -Uri $mgmtUri -Body $listBody
            $rows = ConvertTo-KustoRows -Response $tablesResp
            $actualTables = @($rows | ForEach-Object { [string]$_.TableName })
        } catch {
            $actualTables = @("(.show tables failed: $($_.Exception.Message))")
        }
        $metadata.actualTablesInDatabase = Limit-DiagnosticList -Items $actualTables -Max 10

        $otherDbs = @()
        try {
            $allDbsUri = "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/kqlDatabases"
            $allDbsResp = Invoke-AzRestJson -Method get -Uri $allDbsUri
            $otherDbs = @($allDbsResp.value | ForEach-Object { [string]$_.displayName })
        } catch {
            $otherDbs = @("(workspace KQL DB list failed: $($_.Exception.Message))")
        }
        $metadata.allKqlDatabasesInWorkspace = Limit-DiagnosticList -Items $otherDbs -Max 10

        $suffix = if ($lastKqlError) { " Last KQL error: $lastKqlError" } else { '' }
        $evidence = "Table '$tableName' was not found after ${deadline}s of polling in KQL database '$($database.DatabaseName)'.$suffix Tables actually present: [$($metadata.actualTablesInDatabase)]. KQL databases in workspace: [$($metadata.allKqlDatabasesInWorkspace)]."
        Write-GraderResult -Name $graderName -Passed $false -Score 0 -Evidence $evidence -Metadata $metadata
        return
    }

    $actualSchema = ConvertFrom-CslSchemaString -SchemaString $schemaResponse.Schema
    $metadata.actualSchema = $schemaResponse.Schema
    $schemaCheck = Test-SchemaSetEquality -Actual $actualSchema -Expected $expectedColumns

    if (-not $schemaCheck.Passed) {
        $parts = @()
        if ($schemaCheck.Missing.Count -gt 0) { $parts += "missing: [$($schemaCheck.Missing -join ', ')]" }
        if ($schemaCheck.TypeMismatches.Count -gt 0) { $parts += "type mismatches: [$($schemaCheck.TypeMismatches -join ', ')]" }
        if ($schemaCheck.Extra.Count -gt 0) { $parts += "extra columns: [$($schemaCheck.Extra -join ', ')]" }
        $evidence = "Table '$tableName' schema set-equality failed: $($parts -join '; '). Actual schema: $($schemaResponse.Schema)"
        Write-GraderResult -Name $graderName -Passed $false -Score 0 -Evidence $evidence -Metadata $metadata
        return
    }

    # ---- Probe 2: retention policy ----
    # The prompt explicitly asks for a 30-day retention policy. Without
    # this probe, an agent that creates the columns and forgets retention
    # passes (PR #282 reading-guide item #1).
    #
    # Wrapped in Invoke-WithPolling for the same eventual-consistency
    # reason the schema probe is: an agent that emits
    # `.create-merge table` immediately followed by
    # `.alter table policy retention` returns from both commands
    # synchronously, but the Kusto control plane needs a moment to
    # propagate the alter before `.show table policy retention` will
    # observe the new SoftDeletePeriod. Without polling, this verifier
    # can spuriously emit "no retention policy was found" on an agent
    # whose run was actually correct.
    $retentionBody = @{ db = $database.DatabaseName; csl = ".show table $tableName policy retention" } | ConvertTo-Json -Compress
    $lastRetentionError = $null

    $retentionDays = Invoke-WithPolling -Deadline $deadline -Interval $interval -ScriptBlock {
        try {
            $retentionResp = Invoke-AzRestJson -Method post -Uri $mgmtUri -Body $retentionBody
            $days = Get-RetentionPolicyDays -Response $retentionResp
            # Invoke-WithPolling treats $null strictly as "not ready,
            # keep polling". Returning $null here lets the helper retry
            # until the .alter propagates or the deadline hits.
            return $days
        } catch {
            $script:lastRetentionError = $_.Exception.Message
            return $null
        }
    }

    $metadata.actualRetentionDays = $retentionDays
    if ($null -eq $retentionDays) {
        $suffix = if ($lastRetentionError) { " Last KQL error: $lastRetentionError" } else { '' }
        $evidence = "Table '$tableName' schema verified, but no retention policy was found after ${deadline}s of polling (.show table policy retention returned no SoftDeletePeriod). Expected $expectedRetentionDays days.$suffix"
        Write-GraderResult -Name $graderName -Passed $false -Score 0 -Evidence $evidence -Metadata $metadata
        return
    }
    if ($retentionDays -ne $expectedRetentionDays) {
        $evidence = "Table '$tableName' schema verified, but retention policy is $retentionDays days (expected $expectedRetentionDays)."
        Write-GraderResult -Name $graderName -Passed $false -Score 0 -Evidence $evidence -Metadata $metadata
        return
    }

    # ---- All probes passed ----
    $passed = $true
    $score = 1.0
    $evidence = "Table '$tableName' verified in KQL database '$($database.DatabaseName)': schema matches expected $($expectedColumns.Count) columns by set equality; retention policy is $retentionDays days."
    Write-GraderResult -Name $graderName -Passed $passed -Score $score -Evidence $evidence -Metadata $metadata
} catch {
    $evidence = "Verifier failed: $($_.Exception.Message)"
    Write-GraderResult -Name $graderName -Passed $false -Score 0 -Evidence $evidence -Metadata $metadata
}
