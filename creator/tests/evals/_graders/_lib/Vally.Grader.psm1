Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ------------------------------------------------------------------------
# Schema version stamped on every GraderResult JSON envelope. Bump only on
# a breaking shape change. Workload-team verifiers should not set this
# themselves; Write-GraderResult adds it.
# ------------------------------------------------------------------------
$script:GraderResultSchemaVersion = 1

# ------------------------------------------------------------------------
# Exception classification for Invoke-WithPolling. A permanent failure
# (4xx HTTP, malformed JSON, our own validation throws) will never become
# transient via retry; classify and bail immediately so a typo cannot burn
# the full polling deadline.
#
# Exit-code patterns include BOTH the literal integer (Windows / pwsh, which
# propagates az rest's full HTTP-status return) AND the POSIX-truncated form
# (Linux runners, where the shell returns the status mod 256: 400->144,
# 401->145, 403->147, 404->148, 429->173). Anchored with \b on each side so
# an incidental substring inside a transient error body (e.g. a correlation
# id containing 'exit-code-401') doesn't bypass the retry loop.
# ------------------------------------------------------------------------
$script:PermanentFailurePatterns = @(
    '\bexit code 4\d{2}\b'                       # Windows / direct integer 4xx
    '\bexit code (144|145|147|148|173)\b'        # POSIX-truncated 400/401/403/404/429
    'ConvertFrom-Json'                           # malformed JSON in az rest stdout
    'JSON.*invalid'                              # parse error variants
    'is not a valid workspace GUID'              # Get-ResolvedWorkspaceId throw
    'FABRIC_WORKSPACE_ID is not set'             # Get-ResolvedWorkspaceId throw
    'EVALUATE_GRADER_INPUT'                      # Read-EvaluateGraderInput throw
    'Expected KQL database .* not found'         # Resolve-KqlDatabase throw
)

function Read-EvaluateGraderInput {
    <#
    .SYNOPSIS
    Parse the Vally-injected grader input JSON for the current trial.

    .DESCRIPTION
    Vally invokes program graders with EVALUATE_GRADER_INPUT set to the
    absolute path of a JSON file containing the captured trajectory plus
    the stimulus + grader config. This function reads that file and
    returns the deserialised object. For Pester unit-tests that exercise
    a verifier without a real Vally run, EVALUATE_GRADER_INPUT may also
    be set to a literal JSON STRING (one starting with '{'); the function
    detects that case and parses the string directly.

    Throws on missing env var, missing file, or invalid JSON. Verifiers
    should call this first and let the outer catch surface the failure
    via Write-GraderResult with passed:$false.

    .OUTPUTS
    [pscustomobject] -- the parsed grader input. Top-level shape mirrors
    Vally's GraderInput TypeScript interface: { trajectory, stimulus,
    config, ... }.

    .EXAMPLE
    $graderInput = Read-EvaluateGraderInput
    $stimulusName = $graderInput.trajectory.stimulus.name
    #>
    [CmdletBinding()]
    param()

    $raw = $env:EVALUATE_GRADER_INPUT
    if ([string]::IsNullOrWhiteSpace($raw)) {
        throw 'EVALUATE_GRADER_INPUT is not set. Program graders must be invoked by Vally.'
    }

    # Distinguish "looks like a file path" from "looks like inline JSON"
    # explicitly. Calling Test-Path with a JSON string that contains
    # illegal-on-disk characters (e.g. '{', '"') throws "Illegal characters
    # in path" on PowerShell 5.1, so the previous unconditional Test-Path
    # call would crash for unit-test callers passing inline JSON.
    $trimmed = $raw.Trim()
    $looksLikeInlineJson = $trimmed.StartsWith('{') -or $trimmed.StartsWith('[')

    $json = $null
    try {
        if ($looksLikeInlineJson) {
            $json = $trimmed
        } elseif (Test-Path -LiteralPath $raw -PathType Leaf) {
            $json = Get-Content -LiteralPath $raw -Raw -Encoding utf8
        } else {
            throw "EVALUATE_GRADER_INPUT '$raw' is neither inline JSON (starts with '{' or '[') nor an existing file."
        }

        if ([string]::IsNullOrWhiteSpace($json)) {
            throw 'grader input JSON is empty'
        }

        return $json | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "EVALUATE_GRADER_INPUT could not be parsed as JSON: $($_.Exception.Message)"
    }
}

function Get-ResolvedWorkspaceId {
    <#
    .SYNOPSIS
    Resolve the Fabric workspace GUID for the current verifier run.

    .DESCRIPTION
    Reads FABRIC_WORKSPACE_ID (templated into the program grader's env: by
    tests/run-vally-eval.ps1's {{WORKSPACE_ID}} substitution), validates it
    is a real GUID via [Guid]::TryParse, and returns it.

    Fails fast (does not poll) when the env var is missing, still contains
    the literal '{{WORKSPACE_ID}}' placeholder (templating did not run), or
    is not a valid GUID. This is intentional: a verifier that silently
    swallows a missing workspace would pass against a stale or wrong
    workspace and defeat the whole Layer 2 contract.

    .OUTPUTS
    [string] -- the GUID, suitable for splicing into REST URLs.

    .EXAMPLE
    $workspaceId = Get-ResolvedWorkspaceId
    $uri = "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/kqlDatabases"
    #>
    [CmdletBinding()]
    param()

    $workspaceId = ($env:FABRIC_WORKSPACE_ID ?? '').Trim()
    if ($workspaceId -eq '{{WORKSPACE_ID}}') {
        $workspaceId = ''
    }

    if ([string]::IsNullOrWhiteSpace($workspaceId)) {
        throw 'FABRIC_WORKSPACE_ID is not set. tests/run-vally-eval.ps1 must substitute {{WORKSPACE_ID}} before program graders run.'
    }

    $guidRef = [ref]([Guid]::Empty)
    if (-not [Guid]::TryParse($workspaceId, $guidRef)) {
        throw "FABRIC_WORKSPACE_ID '$workspaceId' is not a valid workspace GUID."
    }

    return $workspaceId
}

function Get-FabricAccessToken {
    <#
    .SYNOPSIS
    Acquire an Azure access token for the given Fabric / Azure resource.

    .DESCRIPTION
    Wraps `az account get-access-token --resource <X>` and returns the
    raw token string. Used for paths that need a raw bearer token outside
    of `az rest` (e.g. Invoke-WebRequest in a verifier). For ordinary
    `az rest` calls you should NOT call this -- pass --resource to `az
    rest` directly and let the Azure CLI mint and inject the token; that
    avoids leaking the token onto argv where any same-user process can
    read it.

    --only-show-errors suppresses warnings/progress that would otherwise
    leak into the returned string. stderr is captured separately so a real
    failure can be surfaced verbatim.

    .PARAMETER Resource
    The Azure resource URI to acquire the token for. Required.

    .OUTPUTS
    [string] -- the trimmed access token.

    .EXAMPLE
    # Only when you genuinely need a raw token. Prefer az rest --resource.
    $token = Get-FabricAccessToken -Resource 'https://api.fabric.microsoft.com'
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$Resource
    )

    $stderrFile = [System.IO.Path]::GetTempFileName()
    try {
        $output = & az account get-access-token --resource $Resource --query accessToken -o tsv --only-show-errors 2>$stderrFile
        $exitCode = $LASTEXITCODE
        $text = ($output | Out-String).Trim()
        $stderrText = if (Test-Path -LiteralPath $stderrFile) { (Get-Content -LiteralPath $stderrFile -Raw -ErrorAction SilentlyContinue) } else { '' }
    } finally {
        if (Test-Path -LiteralPath $stderrFile) { Remove-Item -LiteralPath $stderrFile -Force -ErrorAction SilentlyContinue }
    }

    if ($exitCode -ne 0) {
        $detail = if ($text) { $text } else { $stderrText }
        throw "az account get-access-token failed for resource '$Resource' (exit code $exitCode): $detail"
    }

    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "az account get-access-token returned an empty access token for resource '$Resource'."
    }

    return $text
}

function Invoke-AzRestJson {
    <#
    .SYNOPSIS
    Call `az rest` and return the parsed JSON response.

    .DESCRIPTION
    Wraps `az rest --method <X> --resource <Y> --url <Z>` and handles:
    - Token acquisition (delegated to az rest --resource; we do NOT pass
      Authorization header on argv, which would leak the token to any
      same-user process).
    - stderr isolation (captured to a temp file, not merged into stdout,
      so warnings cannot poison ConvertFrom-Json).
    - POST body materialisation via @file (avoids cmdline length limits
      and quoting hazards on Windows).
    - Cross-platform path joins for the scratch body file.

    .PARAMETER Method
    HTTP method. One of 'get', 'post'.

    .PARAMETER Uri
    Full URL to call. The function infers the Azure resource from the
    URL's host (api.fabric.microsoft.com -> Fabric; kusto.fabric -> Kusto).

    .PARAMETER Body
    JSON body string for POST. Ignored for GET.

    .OUTPUTS
    [pscustomobject] -- parsed JSON response, or $null if the response
    body was empty.

    .EXAMPLE
    $databases = Invoke-AzRestJson -Method get -Uri "https://api.fabric.microsoft.com/v1/workspaces/$wsId/kqlDatabases"

    .EXAMPLE
    $body = @{ db = $db; csl = '.show tables' } | ConvertTo-Json -Compress
    $tables = Invoke-AzRestJson -Method post -Uri "$cluster/v1/rest/mgmt" -Body $body
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('get', 'post')]
        [string]$Method,

        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$Uri,

        [Parameter(Mandatory = $false)]
        [string]$Body
    )

    # Resource inference from URL host. Add cases as new endpoint
    # families enter the verifier surface.
    $resource = if ($Uri -like 'https://api.fabric.microsoft.com/*') {
        'https://api.fabric.microsoft.com'
    } elseif ($Uri -like '*.kusto.fabric.microsoft.com/*' -or $Uri -like '*.kusto.windows.net/*') {
        'https://kusto.kusto.windows.net'
    } elseif ($Uri -like 'https://management.azure.com/*') {
        'https://management.azure.com'
    } else {
        throw "Invoke-AzRestJson: cannot infer Azure resource for URI '$Uri'. Extend the host->resource map in _lib/Vally.Grader.psm1."
    }

    # Token is acquired and injected by az rest --resource; do NOT pass
    # --headers Authorization=Bearer here (would leak on argv).
    $argList = @('rest', '--method', $Method, '--resource', $resource, '--url', $Uri, '--only-show-errors')
    $bodyFile = $null
    if ($Method -eq 'post' -and -not [string]::IsNullOrWhiteSpace($Body)) {
        $scratchDir = Join-Path (Get-Location) 'tests' | Join-Path -ChildPath '.vally-staging' | Join-Path -ChildPath 'grader-program'
        New-Item -ItemType Directory -Path $scratchDir -Force | Out-Null
        $bodyFile = Join-Path $scratchDir ("body-{0}.json" -f ([Guid]::NewGuid().ToString('N')))
        [System.IO.File]::WriteAllText($bodyFile, $Body, [System.Text.UTF8Encoding]::new($false))
        $argList += @('--headers', 'Content-Type=application/json', '--body', "@$bodyFile")
    }

    $stderrFile = [System.IO.Path]::GetTempFileName()
    try {
        $output = & az @argList 2>$stderrFile
        $exitCode = $LASTEXITCODE
        $text = ($output | Out-String).Trim()
        $stderrText = if (Test-Path -LiteralPath $stderrFile) { (Get-Content -LiteralPath $stderrFile -Raw -ErrorAction SilentlyContinue) } else { '' }
    } finally {
        if (Test-Path -LiteralPath $stderrFile) { Remove-Item -LiteralPath $stderrFile -Force -ErrorAction SilentlyContinue }
        if ($bodyFile -and (Test-Path -LiteralPath $bodyFile)) {
            Remove-Item -LiteralPath $bodyFile -Force -ErrorAction SilentlyContinue
        }
    }

    if ($exitCode -ne 0) {
        $detail = if ($text) { $text } else { $stderrText }
        throw "az rest $Method $Uri failed (exit code $exitCode): $detail"
    }

    if ([string]::IsNullOrWhiteSpace($text)) {
        return $null
    }

    return $text | ConvertFrom-Json -ErrorAction Stop
}

function Test-PermanentFailure {
    <#
    .SYNOPSIS
    Classify an exception message as permanent (do not retry) or transient.

    .DESCRIPTION
    Used by Invoke-WithPolling to bail immediately on errors that retry
    cannot resolve (4xx HTTP, malformed JSON, our own validation throws)
    rather than burning the full polling deadline.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateNotNull()]
        [object]$ErrorRecord
    )

    $message = ''
    if ($ErrorRecord -is [System.Management.Automation.ErrorRecord]) {
        $message = $ErrorRecord.Exception.Message
    } elseif ($ErrorRecord.PSObject.Properties['Message']) {
        $message = [string]$ErrorRecord.Message
    } else {
        $message = [string]$ErrorRecord
    }

    foreach ($pattern in $script:PermanentFailurePatterns) {
        if ($message -match $pattern) {
            return $true
        }
    }
    return $false
}

function Write-GraderResult {
    <#
    .SYNOPSIS
    Emit a Vally GraderResult JSON envelope on stdout.

    .DESCRIPTION
    Serialises the standard Vally GraderResult shape (name, kind, passed,
    score, evidence, metadata) plus a schemaVersion field for forward
    compatibility, and writes it as a single line to stdout. Vally's
    program-grader plumbing reads the LAST stdout line as the result.

    Verifiers MUST call this exactly once. The top-level catch in a
    verifier should call it with $Passed:$false and the exception message
    in $Evidence -- never let the verifier silently exit non-zero without
    emitting a result.

    Refuses to emit passed:$true with empty or whitespace-only evidence.
    This is a minimal sanity check, not a security guarantee -- it
    catches "Write-GraderResult -Passed $true -Evidence $errorMessage"
    where $errorMessage happened to be empty. Verifiers still own writing
    meaningful evidence text.

    .PARAMETER Name
    Grader name. Shows in the workflow summary. Must be non-empty.

    .PARAMETER Passed
    Boolean pass/fail. Required.

    .PARAMETER Score
    Decimal score 0..1. Vally aggregates per-stim across graders.

    .PARAMETER Evidence
    Human-readable explanation of what was checked and what the result
    means. For passed:$false, include enough detail for a workload-team
    author to triage from the artifact bundle without re-running CI.

    .PARAMETER Metadata
    Optional hashtable of structured diagnostic data. Lands in
    results.jsonl -> CI artifact -> 30-day retention. Do NOT put raw
    secrets or full tenant-topology data here; use Format-DiagnosticGuid
    and Format-DiagnosticUri to elide.

    .EXAMPLE
    Write-GraderResult -Name 'verify-table' -Passed $true -Score 1 -Evidence 'Table foo exists with expected schema.'
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateNotNullOrEmpty()]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [bool]$Passed,

        [Parameter(Mandatory = $true)]
        [ValidateRange(0, 1)]
        [double]$Score,

        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Evidence,

        [Parameter(Mandatory = $false)]
        [object]$Metadata = $null
    )

    if ($Passed -and [string]::IsNullOrWhiteSpace($Evidence)) {
        throw 'Passing GraderResult values must include non-empty evidence (sanity check, not a security guarantee).'
    }

    $result = [ordered]@{
        schemaVersion = $script:GraderResultSchemaVersion
        name          = $Name
        kind          = 'code'
        passed        = $Passed
        score         = $Score
        evidence      = $Evidence
    }

    if ($null -ne $Metadata) {
        $result.metadata = $Metadata
    }

    $json = $result | ConvertTo-Json -Depth 32 -Compress
    Write-Output $json
}

function Invoke-WithPolling {
    <#
    .SYNOPSIS
    Run a script block repeatedly until it returns a non-null result or
    the deadline expires.

    .DESCRIPTION
    Bounded polling helper for Fabric eventual-consistency cases (an item
    was just created and may not appear in a list call immediately). Calls
    $ScriptBlock; if it returns $null, sleeps $Interval seconds and tries
    again until $Deadline seconds have elapsed.

    Sentinel: ONLY $null means "keep polling". $false, 0, [], '' are all
    treated as real results and the function returns them. The earlier
    version coerced everything through @() and broke $false callers.

    Exception classification: if $ScriptBlock throws, the error message is
    classified via Test-PermanentFailure. Permanent failures (4xx HTTP,
    malformed JSON, our own validation throws) bail immediately and
    re-throw; transient errors are caught and retried until the deadline.
    This prevents a 401 from burning the full polling budget.

    .PARAMETER Deadline
    Maximum seconds to keep polling. Ceiling 3600 (1 hour) -- Fabric
    eventual consistency is on the order of seconds, not hours; a higher
    value almost always indicates a configuration typo.

    .PARAMETER Interval
    Seconds to sleep between attempts. 0 means no sleep (back-to-back
    retries; useful for unit tests).

    .PARAMETER ScriptBlock
    Block to invoke. Return $null to continue polling, anything else to
    return the value, or throw to propagate (if classified permanent) or
    retry (if classified transient).

    .OUTPUTS
    The value returned by $ScriptBlock, or $null if the deadline expired
    without a non-null return.

    .EXAMPLE
    $table = Invoke-WithPolling -Deadline 60 -Interval 2 -ScriptBlock {
        try { return Find-Table -Name 'IoTSensorReadings' } catch { return $null }
    }
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [ValidateRange(0, 3600)]
        [int]$Deadline,

        [Parameter(Mandatory = $true)]
        [ValidateRange(0, 600)]
        [int]$Interval,

        [Parameter(Mandatory = $true)]
        [scriptblock]$ScriptBlock
    )

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $lastError = $null
    $attempted = $false

    do {
        $attempted = $true
        try {
            $result = & $ScriptBlock
            # Strict sentinel: only $null means "keep polling". This
            # allows $false / 0 / '' / [] as legitimate non-null results.
            if ($null -ne $result) {
                return $result
            }
        } catch {
            $lastError = $_
            if (Test-PermanentFailure -ErrorRecord $_) {
                throw "Polling aborted on permanent failure after $([math]::Round($stopwatch.Elapsed.TotalSeconds,1))s: $($_.Exception.Message)"
            }
        }

        if ($stopwatch.Elapsed.TotalSeconds -ge $Deadline) {
            break
        }

        if ($Interval -gt 0) {
            Start-Sleep -Seconds $Interval
        }
    } while ($true)

    if ($lastError -and $attempted) {
        throw "Polling did not produce a result within ${Deadline}s. Last transient error: $($lastError.Exception.Message)"
    }

    return $null
}

function Format-DiagnosticGuid {
    <#
    .SYNOPSIS
    Render a GUID as a stable short opaque identifier for diagnostic metadata
    in GraderResult.

    .DESCRIPTION
    Verifiers often want to include "which workspace" in failure evidence so
    two failures in the same run can be distinguished, but they should not
    leak the full GUID into a 30-day artifact bundle. This produces a short
    SHA256 prefix (e.g. "sha256:a3f1b9c8") -- stable for the same input,
    sufficient for "did these two failures see the same workspace".

    NOT a privacy boundary. The output is an 8-hex-char (32-bit) SHA-256
    prefix. A caller with access to the tenant's workspace inventory can
    build a (workspace_guid -> sha256_prefix) lookup in seconds and recover
    the candidate GUIDs. Treat the output as a stable opaque tag for
    diagnostic correlation, NOT as a one-way redaction. Do not route
    secrets, PII, or other genuinely sensitive data through this helper
    expecting privacy guarantees.

    .EXAMPLE
    $metadata.workspaceId = Format-DiagnosticGuid -Guid $workspaceId
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Guid
    )

    if ([string]::IsNullOrWhiteSpace($Guid)) { return '' }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Guid)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha.ComputeHash($bytes)
        return 'sha256:' + (([System.BitConverter]::ToString($hash, 0, 4)) -replace '-', '').ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Format-DiagnosticUri {
    <#
    .SYNOPSIS
    Render a URI with the host obfuscated, for diagnostic metadata.

    .DESCRIPTION
    Keeps the scheme, replaces the host with its first 12 chars + ellipsis,
    drops the path. Enough to say "we hit a Kusto cluster" without leaking
    the full hostname into a 30-day artifact bundle.

    .EXAMPLE
    $metadata.queryServiceUri = Format-DiagnosticUri -Uri $database.QueryServiceUri
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Uri
    )

    if ([string]::IsNullOrWhiteSpace($Uri)) { return '' }
    try {
        $u = [Uri]$Uri
        $uriHost = $u.Host
        if ([string]::IsNullOrWhiteSpace($uriHost)) { return '[opaque]' }
        $sub = if ($uriHost.Length -gt 12) { $uriHost.Substring(0, 12) + '...' } else { $uriHost }
        return "$($u.Scheme)://$sub"
    } catch {
        return '[unparseable-uri]'
    }
}

function Limit-DiagnosticList {
    <#
    .SYNOPSIS
    Cap a list-of-strings to the first N entries plus a "and N more" tag
    for diagnostic metadata.

    .DESCRIPTION
    Prevents a "list all tables" or "list all databases" diagnostic from
    dumping unbounded tenant-topology data into a 30-day artifact when the
    target workspace has hundreds of items.

    .EXAMPLE
    $metadata.tables = Limit-DiagnosticList -Items $allTableNames -Max 10
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $false)]
        [AllowEmptyCollection()]
        [object[]]$Items,

        [Parameter(Mandatory = $false)]
        [ValidateRange(1, 100)]
        [int]$Max = 10
    )

    if ($null -eq $Items -or $Items.Count -eq 0) { return '' }
    if ($Items.Count -le $Max) {
        return ($Items -join ', ')
    }
    $head = $Items[0..($Max - 1)]
    $extra = $Items.Count - $Max
    return (($head -join ', ') + " (and $extra more)")
}

<#
.SYNOPSIS
    Read the skill tag from a vally results.jsonl entry.

.DESCRIPTION
    Vally writes one combined results.jsonl per run at
    `<output>/<timestamp>/results.jsonl`, so directory-based eval naming
    silently collapses every row to the literal string `vally-output`.
    The actual skill / eval identifier lives inside each line at
    `trajectory.stimulus.tags.skill`, which build_plugins.py stamps onto
    every rendered stim. This helper reads that field defensively (the
    intermediate objects may be `$null` in malformed or future-vally
    payloads) and returns the sentinel '(unknown-skill)' so the caller
    can detect drift without crashing.

    The same one-line logic is INLINED in
    .github/workflows/fabric-smoke-vally.yml (Summarise step) for the
    summarise table -- the workflow does not import this module today.
    Keep the two in sync. Pester regression tests in
    Vally.Grader.tests.ps1 pin the field path that the workflow relies
    on, so a vally schema rename would surface there before it slips
    silently into a green-but-broken summary table.

.PARAMETER Entry
    A single deserialised results.jsonl line. Expected shape:
    { trajectory: { stimulus: { tags: { skill: '<name>' } } } }.
    Any missing intermediate field returns '(unknown-skill)'.

.OUTPUTS
    System.String. Either the trimmed skill tag or '(unknown-skill)'.
#>
function Get-StimulusSkillTag {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $false, ValueFromPipeline = $true)]
        [object]$Entry
    )
    # Strict-mode-safe property reader. Works on both [hashtable]
    # (used in tests) and [PSCustomObject] (what ConvertFrom-Json
    # returns at runtime). Direct dotted access throws
    # PropertyNotFoundException under Set-StrictMode -Version Latest
    # when an intermediate key is absent.
    function _Get-Prop {
        param([object]$Obj, [string]$Name)
        if ($null -eq $Obj) { return $null }
        if ($Obj -is [System.Collections.IDictionary]) {
            if ($Obj.Contains($Name)) { return $Obj[$Name] }
            return $null
        }
        $p = $Obj.PSObject.Properties[$Name]
        if ($p) { return $p.Value }
        return $null
    }
    $traj  = _Get-Prop -Obj $Entry -Name 'trajectory'
    $stim  = _Get-Prop -Obj $traj  -Name 'stimulus'
    $tags  = _Get-Prop -Obj $stim  -Name 'tags'
    $skill = _Get-Prop -Obj $tags  -Name 'skill'
    if ($null -eq $skill) { return '(unknown-skill)' }
    $s = [string]$skill
    if ([string]::IsNullOrWhiteSpace($s)) { return '(unknown-skill)' }
    return $s.Trim()
}

Export-ModuleMember -Function `
    Read-EvaluateGraderInput, `
    Get-ResolvedWorkspaceId, `
    Get-FabricAccessToken, `
    Invoke-AzRestJson, `
    Test-PermanentFailure, `
    Write-GraderResult, `
    Invoke-WithPolling, `
    Format-DiagnosticGuid, `
    Format-DiagnosticUri, `
    Limit-DiagnosticList, `
    Get-StimulusSkillTag
