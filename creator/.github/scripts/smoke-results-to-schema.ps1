#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Translate smoke runner output to the documented skill-test-result schema.

.DESCRIPTION
  Reads the flat per-test results emitted by `tests/testFabricSkills.ps1`
  (`testsResults.json` = array of `{name, passed, flakyIssue?}`) plus the
  per-test `_output.txt` agent trajectories, and emits the directory tree
  documented in `docs/skill-test-result-schema.md`:

      ${OutputRoot}/${Date}/${RunId}/${SkillArea}/
        ├── testResults.json
        ├── test-run-${datetime}-${skill}-SKILL-REPORT.md
        └── ${test-case}/
             ├── test-consolidated-report.md
             └── agent-metadata-${datetime}.md

  Test names are grouped into skill areas using the `area` field in
  `tests/tests.json` (e.g., "sqldw", "powerbi", "eventhouse"). Tests whose
  name is not found in `tests.json` are grouped under `"unknown"`.

  This is a one-way translation: the source files remain unchanged.

.PARAMETER ResultsJsonPath
  Path to the `testsResults.json` produced by testFabricSkills.ps1.

.PARAMETER OutputsDir
  Directory containing per-test `_output.txt` agent-trajectory files.
  Usually the same directory as `testsResults.json`.

.PARAMETER TestsJsonPath
  Path to `tests/tests.json`. Used to resolve test name -> skill area.

.PARAMETER OutputRoot
  Root directory under which to emit the schema-compliant tree.
  A `${Date}/${RunId}/...` subtree is created beneath this.

.PARAMETER RunId
  Run identifier. The smoke workflow uses `${{ github.run_id }}-${{ github.run_attempt }}`.

.PARAMETER SmokeRunLogPath
  Optional path to the streaming `smoke-run.log` produced by the workflow's
  `Tee-Object` of the smoke runner output. When provided, the translator
  parses each test's status block (`=== Running test: <name> ===` ... `Test
  result: Y|F|N`) and enriches `testResults.json` with optional fields:
  `rawStatus`, `durationSeconds`, `foundSkills`, `foundResults`,
  `missingSkills`, `missingResults`. The aggregator surfaces these in the
  dashboard.

.PARAMETER Date
  Optional yyyy-MM-dd date string (UTC). Defaults to today's UTC date.

.PARAMETER SummaryMarkdownPath
  Optional path to a markdown file. If provided, writes a per-skill rollup
  table to this file (overwriting). The smoke workflow appends this file to
  `$GITHUB_STEP_SUMMARY` to surface a leadership-readable status table at
  the top of the workflow run page.

.EXAMPLE
  ./smoke-results-to-schema.ps1 `
      -ResultsJsonPath D:/a/_temp/smoke-results/testsResults.json `
      -OutputsDir D:/a/_temp/smoke-results `
      -TestsJsonPath ./tests/tests.json `
      -OutputRoot D:/a/_temp/smoke-results-schema `
      -RunId 25852605473-1 `
      -SmokeRunLogPath D:/a/_temp/smoke-results/smoke-run.log
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $ResultsJsonPath,
    [Parameter(Mandatory)] [string] $OutputsDir,
    [Parameter(Mandatory)] [string] $TestsJsonPath,
    [Parameter(Mandatory)] [string] $OutputRoot,
    [Parameter(Mandatory)] [string] $RunId,
    [string] $Date = ([DateTime]::UtcNow.ToString('yyyy-MM-dd')),
    [string] $SummaryMarkdownPath,
    [string] $SmokeRunLogPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function ConvertTo-SafeName([string] $name) {
    # Match the directory-naming convention from the upstream schema:
    # replace path-unsafe characters with '-', collapse runs, cap at 200.
    $sanitized = $name -replace '[<>:"/\\|?*]', '-'
    $sanitized = $sanitized -replace '\s+', '_'
    $sanitized = $sanitized -replace '-+', '-'
    $sanitized = $sanitized -replace '_+', '_'
    if ($sanitized.Length -gt 200) { $sanitized = $sanitized.Substring(0, 200) }
    return $sanitized
}

function Get-SmokeRunLogDetails {
    <#
    .SYNOPSIS
        Parse the streaming smoke-run.log into a per-test details map.

    .DESCRIPTION
        The smoke runner emits one block per test:

            === Running test: <test-name> ===
              Starting test: <ts> ... finished: <ts> duration: <n> s
              [WARNING / Found skill / MISSING skill / Found result / MISSING result lines]
              [KNOWN FLAKY note]
              Test result: Y | F | N | F (TIMEOUT...) | N (TIMEOUT)

        Returns a hashtable keyed by test name with structured fields.

    .PARAMETER LogPath
        Path to the smoke-run.log file. Returns @{} if the file is missing
        or the parse fails open.
    #>
    [CmdletBinding()]
    param([string] $LogPath)

    $details = @{}
    if (-not $LogPath -or -not (Test-Path $LogPath)) { return $details }

    try {
        $logText = Get-Content $LogPath -Raw -ErrorAction Stop
    } catch {
        Write-Warning "Could not read smoke-run.log at ${LogPath}: $_"
        return $details
    }

    # Split on "=== Running test:" markers; the first segment is pre-amble noise.
    $segments = [regex]::Split($logText, '(?m)^=== Running test: ')
    for ($i = 1; $i -lt $segments.Count; $i++) {
        $segment = $segments[$i]
        # The first line of the segment is "<test-name> ===" (we stripped the prefix).
        $firstNl = $segment.IndexOf("`n")
        if ($firstNl -lt 0) { continue }
        $header = $segment.Substring(0, $firstNl).TrimEnd("`r", " ", "=")
        $testName = $header.Trim()
        $body = $segment.Substring($firstNl + 1)

        # Stop the body at the next "=== Running test:" marker (already split out).
        # The 'Test result:' line is the last meaningful line for this test.
        $endIdx = $body.IndexOf("`n=== ")
        if ($endIdx -ge 0) { $body = $body.Substring(0, $endIdx) }

        $entry = [ordered]@{
            rawStatus       = $null
            durationSeconds = $null
            foundSkills     = @()
            foundResults    = @()
            missingSkills   = @()
            missingResults  = @()
            warnings        = @()
        }

        foreach ($line in $body -split "`r?`n") {
            $trimmed = $line.Trim()
            if (-not $trimmed) { continue }

            if ($trimmed -match '^Starting test:.*?duration:\s*([\d.]+)\s*s\s*$') {
                $entry.durationSeconds = [double]$Matches[1]
            }
            elseif ($trimmed -match '^Found skill:\s*(.+)$')        { $entry.foundSkills    += $Matches[1].Trim() }
            elseif ($trimmed -match '^MISSING skill:\s*(.+)$')      { $entry.missingSkills  += $Matches[1].Trim() }
            elseif ($trimmed -match '^Found result:\s*(.+)$')       { $entry.foundResults   += $Matches[1].Trim() }
            elseif ($trimmed -match '^MISSING result:\s*(.+)$')     { $entry.missingResults += $Matches[1].Trim() }
            elseif ($trimmed -match '^WARNING:\s*(.+)$')            { $entry.warnings       += $Matches[1].Trim() }
            elseif ($trimmed -match '^Test result:\s*([YFN])')      { $entry.rawStatus      = $Matches[1] }
        }

        if ($testName) { $details[$testName] = $entry }
    }

    return $details
}

if (-not (Test-Path $ResultsJsonPath)) {
    throw "ResultsJsonPath not found: $ResultsJsonPath"
}
if (-not (Test-Path $TestsJsonPath)) {
    throw "TestsJsonPath not found: $TestsJsonPath"
}

Write-Host "Reading results: $ResultsJsonPath"
$rawResults = Get-Content $ResultsJsonPath -Raw | ConvertFrom-Json
if ($null -eq $rawResults) {
    Write-Warning "testsResults.json was empty/null. Nothing to translate."
    return
}
# ConvertFrom-Json returns a single object when the JSON has one entry; force-array.
$resultsArray = @($rawResults)

Write-Host "Reading tests.json: $TestsJsonPath"
$testsArray = @((Get-Content $TestsJsonPath -Raw | ConvertFrom-Json))
$areaByName = @{}
foreach ($t in $testsArray) {
    if ($t.PSObject.Properties['name'] -and $t.PSObject.Properties['area'] -and -not [string]::IsNullOrWhiteSpace($t.area)) {
        $areaByName[$t.name] = $t.area
    }
}
Write-Host "  Indexed $($areaByName.Count) test name -> area mappings."

# Data-driven fallback: derive area from test name prefix for any test that
# is missing an explicit `area` in tests.json. The known set is learned from
# tests.json itself (no hardcoded workload list). Longest prefix wins so
# multi-segment areas like "synapse-migration" beat "synapse".
$knownAreas = @($areaByName.Values | Sort-Object -Unique | Sort-Object -Property Length -Descending)

function Resolve-TestArea {
    param([string]$testName, [hashtable]$nameToArea, [string[]]$known)
    if ($nameToArea.ContainsKey($testName)) { return $nameToArea[$testName] }
    foreach ($a in $known) {
        if ($testName -eq $a -or $testName.StartsWith("$a-")) { return $a }
    }
    return 'unknown'
}

# Parse the streaming smoke-run.log for richer per-test telemetry (rawStatus,
# duration, found/missing skills + results, warnings). Returns @{} if the log
# is unavailable; testResults.json then degrades gracefully to the minimal
# {isPass, message} shape from testsResults.json alone.
$logDetails = Get-SmokeRunLogDetails -LogPath $SmokeRunLogPath
if ($logDetails.Count -gt 0) {
    Write-Host "  Parsed $($logDetails.Count) test block(s) from smoke-run.log"
}

# Group results by skill area.
$nowUtc = [DateTime]::UtcNow
$datetimeStamp = $nowUtc.ToString('yyyy-MM-ddTHHmmssZ')
$resultsByArea = @{}
$fallbackCount = 0
foreach ($r in $resultsArray) {
    if (-not $r.PSObject.Properties['name']) { continue }
    $area = Resolve-TestArea -testName $r.name -nameToArea $areaByName -known $knownAreas
    if (-not $areaByName.ContainsKey($r.name) -and $area -ne 'unknown') {
        $fallbackCount++
        Write-Host "  Fallback: '$($r.name)' -> area '$area' (derived from name prefix)"
    }
    if (-not $resultsByArea.ContainsKey($area)) { $resultsByArea[$area] = @() }
    $resultsByArea[$area] += $r
}
if ($fallbackCount -gt 0) {
    Write-Host "  ($fallbackCount test(s) bucketed via name-prefix fallback; add explicit 'area' to tests.json to silence.)"
}
Write-Host "Grouped into $($resultsByArea.Keys.Count) skill area(s): $($resultsByArea.Keys -join ', ')"

$runRoot = Join-Path $OutputRoot $Date | Join-Path -ChildPath $RunId
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null

# Track per-skill totals so we can emit a rollup table to the job summary.
$perSkillRollup = @{}

foreach ($area in $resultsByArea.Keys) {
    $skillResults = $resultsByArea[$area]
    $skillDir = Join-Path $runRoot $area
    New-Item -ItemType Directory -Path $skillDir -Force | Out-Null

    # 1. testResults.json - object keyed by test name.
    $testResultsObj = [ordered]@{}
    $passCount = 0
    $failCount = 0
    foreach ($r in $skillResults) {
        # isPass is true for 'Y' (pass) and 'F' (flaky-pass); everything else is failure.
        $isPass = $r.passed -in @('Y', 'F')
        if ($isPass) { $passCount++ } else { $failCount++ }
        $message = "Smoke status: $($r.passed)"
        if ($r.PSObject.Properties['flakyIssue'] -and $r.flakyIssue) {
            $message += " (flaky issue: $($r.flakyIssue))"
        }
        $entry = [ordered]@{ isPass = $isPass; message = $message }
        # Always include the raw runner status (Y/F/N) - simple, no log
        # parsing required, just lifts the existing 'passed' field.
        if ($r.PSObject.Properties['passed'] -and $r.passed) {
            $entry.rawStatus = $r.passed
        }
        if ($r.PSObject.Properties['flakyIssue'] -and $r.flakyIssue) {
            $entry.flakyIssue = $r.flakyIssue
        }
        # Enrich from the smoke-run.log parse when available.
        if ($logDetails.ContainsKey($r.name)) {
            $d = $logDetails[$r.name]
            if ($null -ne $d.durationSeconds)   { $entry.durationSeconds = $d.durationSeconds }
            if ($d.foundSkills.Count    -gt 0)  { $entry.foundSkills    = @($d.foundSkills) }
            if ($d.foundResults.Count   -gt 0)  { $entry.foundResults   = @($d.foundResults) }
            if ($d.missingSkills.Count  -gt 0)  { $entry.missingSkills  = @($d.missingSkills) }
            if ($d.missingResults.Count -gt 0)  { $entry.missingResults = @($d.missingResults) }
            if ($d.warnings.Count       -gt 0)  { $entry.warnings       = @($d.warnings) }
        }
        $testResultsObj[$r.name] = $entry
    }
    $testResultsPath = Join-Path $skillDir 'testResults.json'
    ($testResultsObj | ConvertTo-Json -Depth 4) | Set-Content -Path $testResultsPath -Encoding utf8 -NoNewline
    Write-Host "  [$area] testResults.json -> $($skillResults.Count) tests ($passCount pass, $failCount fail)"

    # 1b. token-summary.jsonl - per-test token usage records (one JSON object
    # per line). Optional file; only emitted when at least one test in this
    # skill area has tokenUsage data from the smoke runner.
    $tokenLines = @()
    foreach ($r in $skillResults) {
        if ($r.PSObject.Properties['tokenUsage'] -and $r.tokenUsage) {
            $tu = $r.tokenUsage
            $rec = [ordered]@{
                testName         = $r.name
                inputTokens      = if ($null -ne $tu.inputTokens)      { [int]$tu.inputTokens }      else { 0 }
                outputTokens     = if ($null -ne $tu.outputTokens)     { [int]$tu.outputTokens }     else { 0 }
                cacheReadTokens  = if ($null -ne $tu.cacheReadTokens)  { [int]$tu.cacheReadTokens }  else { 0 }
                cacheWriteTokens = if ($null -ne $tu.cacheWriteTokens) { [int]$tu.cacheWriteTokens } else { 0 }
            }
            $tokenLines += ($rec | ConvertTo-Json -Compress -Depth 3)
        }
    }
    if ($tokenLines.Count -gt 0) {
        $tokenPath = Join-Path $skillDir 'token-summary.jsonl'
        ($tokenLines -join "`n") | Set-Content -Path $tokenPath -Encoding utf8 -NoNewline
        Write-Host "  [$area] token-summary.jsonl -> $($tokenLines.Count) records"
    }

    $perSkillRollup[$area] = @{
        total = $skillResults.Count
        pass  = $passCount
        fail  = $failCount
    }

    # 2. SKILL-REPORT.md - per-skill summary.
    $reportLines = @()
    $reportLines += "# $area smoke run $Date ($RunId)"
    $reportLines += ""
    $reportLines += "- Total: $($skillResults.Count)"
    $reportLines += "- Passed: $passCount"
    $reportLines += "- Failed: $failCount"
    $reportLines += ""
    $reportLines += "## Per-test results"
    $reportLines += ""
    $reportLines += "| Test | Status |"
    $reportLines += "|---|---|"
    foreach ($r in $skillResults) {
        $reportLines += "| $($r.name) | $($r.passed) |"
    }
    $reportPath = Join-Path $skillDir "test-run-${datetimeStamp}-${area}-SKILL-REPORT.md"
    ($reportLines -join "`n") | Set-Content -Path $reportPath -Encoding utf8

    # 3. Per-test-case directories with agent trajectory + consolidated report.
    foreach ($r in $skillResults) {
        $caseDir = Join-Path $skillDir (ConvertTo-SafeName $r.name)
        New-Item -ItemType Directory -Path $caseDir -Force | Out-Null

        # test-consolidated-report.md (per-test summary).
        $caseLines = @()
        $caseLines += "# $($r.name)"
        $caseLines += ""
        $caseLines += "- Skill area: $area"
        $caseLines += "- Status: $($r.passed)"
        $caseLines += "- Result: $(if ($r.passed -in @('Y','F')) { '✅ Pass' } else { '❌ Fail' })"
        if ($r.PSObject.Properties['flakyIssue'] -and $r.flakyIssue) {
            $caseLines += "- Flaky issue: $($r.flakyIssue)"
        }
        ($caseLines -join "`n") | Set-Content -Path (Join-Path $caseDir 'test-consolidated-report.md') -Encoding utf8

        # agent-metadata-{datetime}.md (agent trajectory from _output.txt).
        $safeName = $r.name -replace '[^a-zA-Z0-9_-]', '_'
        $outputCandidate = Join-Path $OutputsDir "${safeName}_output.txt"
        $trajectoryLines = @()
        $trajectoryLines += "# $($r.name) - agent run $datetimeStamp"
        $trajectoryLines += ""
        $trajectoryLines += "Status: $($r.passed)"
        $trajectoryLines += ""
        if (Test-Path $outputCandidate) {
            $trajectoryLines += "## Agent output"
            $trajectoryLines += ""
            $trajectoryLines += '```'
            $trajectoryLines += (Get-Content $outputCandidate -Raw)
            $trajectoryLines += '```'
        }
        else {
            $trajectoryLines += "_No agent _output.txt captured at expected path: ${outputCandidate}_"
        }
        $trajectoryPath = Join-Path $caseDir "agent-metadata-${datetimeStamp}.md"
        ($trajectoryLines -join "`n") | Set-Content -Path $trajectoryPath -Encoding utf8
    }
}

Write-Host ""
Write-Host "Schema-compliant tree emitted under: $runRoot"
Get-ChildItem $runRoot -Recurse -File |
    Group-Object DirectoryName |
    ForEach-Object { "  $($_.Name): $($_.Count) file(s)" }

# Optionally emit a per-skill rollup markdown (consumed by the workflow to
# append to GITHUB_STEP_SUMMARY).
if ($SummaryMarkdownPath) {
    Write-Host ""
    Write-Host "Writing per-skill rollup to: $SummaryMarkdownPath"
    $totalAll = 0; $passAll = 0; $failAll = 0
    foreach ($k in $perSkillRollup.Keys) {
        $totalAll += $perSkillRollup[$k].total
        $passAll  += $perSkillRollup[$k].pass
        $failAll  += $perSkillRollup[$k].fail
    }
    $rollupLines = @()
    $rollupLines += "## Per-skill smoke rollup"
    $rollupLines += ""
    $rollupLines += "Run $RunId on $Date (UTC). Schema: ``docs/skill-test-result-schema.md``."
    $rollupLines += ""
    $rollupLines += "| Skill area | Pass | Fail | Total | Status |"
    $rollupLines += "|---|---:|---:|---:|---|"
    foreach ($area in ($perSkillRollup.Keys | Sort-Object)) {
        $s = $perSkillRollup[$area]
        $status = if ($s.fail -eq 0) { '✅' } elseif ($s.pass -eq 0) { '❌' } else { '⚠️' }
        $rollupLines += "| $area | $($s.pass) | $($s.fail) | $($s.total) | $status |"
    }
    $rollupLines += "| **Total** | **$passAll** | **$failAll** | **$totalAll** | **$(if ($failAll -eq 0) { '✅' } elseif ($passAll -eq 0) { '❌' } else { '⚠️' })** |"
    $rollupLines += ""
    $rollupLines += "Schema-compliant artifact uploaded under the ``smoke-results-schema-${RunId}`` artifact."
    ($rollupLines -join "`n") | Set-Content -Path $SummaryMarkdownPath -Encoding utf8
}
