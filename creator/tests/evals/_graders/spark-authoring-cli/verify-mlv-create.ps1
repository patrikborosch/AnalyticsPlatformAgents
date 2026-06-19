[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$modulePath = Join-Path $PSScriptRoot '..' | Join-Path -ChildPath '_lib' | Join-Path -ChildPath 'Vally.Grader.psm1'
Import-Module $modulePath -Force

# ---------------------------------------------------------------------------
# Verifier for "MLV -- create a Materialized Lake View with Spark SQL".
#
# Asserts:
#   1. The MLV $expectedMlvName exists in schema $expectedSchema.
#   2. The MLV definition contains CONSTRAINT ... CHECK ... ON MISMATCH.
#
# Uses a Livy session to run SHOW MATERIALIZED LAKE VIEWS and
# SHOW CREATE MATERIALIZED LAKE VIEW. READ-ONLY on the MLV itself.
#
# Grounded in real trajectory from workspace MLV_At_Scale (2026-06-16).
# ---------------------------------------------------------------------------

$graderName = 'verify-mlv-create'
$expectedMlvName = ($env:MLV_EXPECTED_NAME ?? '').Trim()
$expectedSchema = ($env:MLV_EXPECTED_SCHEMA ?? '').Trim()
$metadata = [ordered]@{}

if ([string]::IsNullOrWhiteSpace($expectedMlvName)) {
    throw "MLV_EXPECTED_NAME env var must be set in eval.yaml program-grader env block."
}
if ([string]::IsNullOrWhiteSpace($expectedSchema)) {
    throw "MLV_EXPECTED_SCHEMA env var must be set in eval.yaml program-grader env block."
}

try {
    [void](Read-EvaluateGraderInput)
    $workspaceId = Get-ResolvedWorkspaceId
    $metadata.workspaceId = Format-DiagnosticGuid -Guid $workspaceId

    # --- Resolve lakehouse ---
    $lhUri = "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/lakehouses"
    $lhResponse = Invoke-AzRestJson -Method get -Uri $lhUri
    $lakehouses = @($lhResponse.value)
    if ($lakehouses.Count -eq 0) {
        Write-GraderResult -Name $graderName -Passed $false -Score 0 `
            -Evidence "No lakehouses found in workspace '$workspaceId'." -Metadata $metadata
        return
    }
    $lakehouse = $lakehouses[0]
    $lakehouseId = $lakehouse.id
    $metadata.lakehouseId = Format-DiagnosticGuid -Guid $lakehouseId
    $metadata.lakehouseName = $lakehouse.displayName

    # --- Create Livy session ---
    $sessionUri = "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/lakehouses/$lakehouseId/livyApi/versions/2023-12-01/sessions"
    $sessionBody = @{
        name = "vally-verify-mlv"
        driverMemory = "28g"
        driverCores = 4
        executorMemory = "28g"
        executorCores = 4
        conf = @{ "spark.fabric.lakehouse.default.id" = $lakehouseId }
    } | ConvertTo-Json -Compress

    $sessionResp = Invoke-AzRestJson -Method post -Uri $sessionUri -Body $sessionBody
    $sessionId = $sessionResp.id
    $metadata.sessionId = $sessionId

    # --- Poll until session idle ---
    $sessionStatusUri = "$sessionUri/$sessionId"
    $sessionReady = Invoke-WithPolling -Deadline 120 -Interval 5 -ScriptBlock {
        $status = Invoke-AzRestJson -Method get -Uri $sessionStatusUri
        if ($status.state -eq 'idle') { return $true }
        if ($status.state -eq 'error' -or $status.state -eq 'dead') {
            throw "Livy session entered state '$($status.state)'"
        }
        return $null
    }

    if (-not $sessionReady) {
        Write-GraderResult -Name $graderName -Passed $false -Score 0 `
            -Evidence "Livy session did not reach idle state within 120s." -Metadata $metadata
        return
    }

    # --- Helper: submit statement and get result ---
    $stmtUri = "$sessionUri/$sessionId/statements"
    function Invoke-SparkSql {
        param([string]$Sql)
        $code = "spark.sql(""""""$Sql"""""").show(1000, truncate=False)"
        $body = @{ code = $code; kind = "pyspark" } | ConvertTo-Json -Compress
        $stmtResp = Invoke-AzRestJson -Method post -Uri $stmtUri -Body $body
        $stmtId = $stmtResp.id

        $result = Invoke-WithPolling -Deadline 60 -Interval 3 -ScriptBlock {
            $r = Invoke-AzRestJson -Method get -Uri "$stmtUri/$stmtId"
            if ($r.state -eq 'available') { return $r }
            if ($r.state -eq 'error' -or $r.state -eq 'cancelled') {
                throw "Statement $stmtId entered state '$($r.state)'"
            }
            return $null
        }
        return $result
    }

    # --- Step 1: SHOW MATERIALIZED LAKE VIEWS IN <schema> ---
    $showResult = Invoke-SparkSql -Sql "SHOW MATERIALIZED LAKE VIEWS IN $expectedSchema"
    $showOutput = $showResult.output.data.'text/plain'
    $metadata.showMlvsOutput = if ($showOutput.Length -gt 500) { $showOutput.Substring(0, 500) } else { $showOutput }

    if ($showOutput -notmatch [regex]::Escape($expectedMlvName)) {
        Write-GraderResult -Name $graderName -Passed $false -Score 0 `
            -Evidence "MLV '$expectedMlvName' not found in schema '$expectedSchema'. SHOW output: $showOutput" `
            -Metadata $metadata
        return
    }

    # --- Step 2: SHOW CREATE MATERIALIZED LAKE VIEW ---
    $createResult = Invoke-SparkSql -Sql "SHOW CREATE MATERIALIZED LAKE VIEW $expectedSchema.$expectedMlvName"
    $createOutput = $createResult.output.data.'text/plain'
    $metadata.showCreateOutput = if ($createOutput.Length -gt 800) { $createOutput.Substring(0, 800) } else { $createOutput }

    # Verify CONSTRAINT ... CHECK ... ON MISMATCH
    $hasConstraint = $createOutput -match '(?is)CONSTRAINT\b[\s\S]{0,120}?CHECK\b'
    $hasOnMismatch = $createOutput -match '(?i)ON\s+MISMATCH\s+(DROP|FAIL)'

    if (-not $hasConstraint -or -not $hasOnMismatch) {
        $missing = @()
        if (-not $hasConstraint) { $missing += "CONSTRAINT...CHECK" }
        if (-not $hasOnMismatch) { $missing += "ON MISMATCH DROP|FAIL" }
        Write-GraderResult -Name $graderName -Passed $false -Score 0 `
            -Evidence "MLV '$expectedMlvName' exists but missing: $($missing -join ', '). Definition: $createOutput" `
            -Metadata $metadata
        return
    }

    # --- All checks passed ---
    Write-GraderResult -Name $graderName -Passed $true -Score 1 `
        -Evidence "MLV '$expectedSchema.$expectedMlvName' exists with CONSTRAINT...CHECK...ON MISMATCH clause." `
        -Metadata $metadata

} catch {
    Write-GraderResult -Name $graderName -Passed $false -Score 0 `
        -Evidence "Verifier failed: $($_.Exception.Message)" -Metadata $metadata
} finally {
    # Cleanup: delete the Livy session (best-effort)
    if ($sessionId) {
        try {
            Invoke-AzRestJson -Method delete -Uri "$sessionUri/$sessionId" | Out-Null
        } catch { }
    }
}
