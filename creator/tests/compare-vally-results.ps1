<#
.SYNOPSIS
    Compare Vally evaluation results across suites or skills.

.DESCRIPTION
    Parses Vally result JSON files and produces a comparison table showing:
    - Score (mean across runs)
    - Token usage (input + output, mean)
    - Wall time (mean seconds)
    - Pass rate per grader type

.PARAMETER ResultsDir
    Path to the Vally results directory. Default: tests/.vally-results/

.PARAMETER GroupBy
    Group results by "skill" (default) or "suite".

.PARAMETER All
    Include all runs in aggregation. By default, only the most recent run per
    skill is considered.

.EXAMPLE
    .\tests\compare-vally-results.ps1
    # Shows per-skill comparison of latest results

.EXAMPLE
    .\tests\compare-vally-results.ps1 -GroupBy suite
    # Shows per-suite aggregated comparison
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ResultsDir,

    [Parameter(Mandatory = $false)]
    [ValidateSet("skill", "suite")]
    [string]$GroupBy = "skill",

    [Parameter(Mandatory = $false)]
    [switch]$All
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$gitRoot = git rev-parse --show-toplevel 2>$null
if ($gitRoot) {
    $RepoRoot = Convert-Path $gitRoot
} else {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}

if (-not $ResultsDir) {
    $ResultsDir = Join-Path $RepoRoot "tests/.vally-results"
}

if (-not (Test-Path $ResultsDir)) {
    Write-Error "No results found at $ResultsDir. Run evaluations first."
    exit 1
}

# Find all result JSON/JSONL files
$resultFiles = Get-ChildItem -Path $ResultsDir -Recurse -Filter "results.jsonl" |
    Sort-Object LastWriteTime -Descending

if ($resultFiles.Count -eq 0) {
    $resultFiles = Get-ChildItem -Path $ResultsDir -Recurse -Filter "results.json" |
        Sort-Object LastWriteTime -Descending
}

if ($resultFiles.Count -eq 0) {
    # Try alternative naming patterns
    $resultFiles = Get-ChildItem -Path $ResultsDir -Recurse -Filter "*.json" |
        Where-Object { $_.Name -match "result|eval|run" } |
        Sort-Object LastWriteTime -Descending
}

if ($resultFiles.Count -eq 0) {
    Write-Warning "No result files found in $ResultsDir"
    Write-Host "`nExpected structure:" -ForegroundColor Yellow
    Write-Host "  tests/.vally-results/<eval-name>/<timestamp>/results.jsonl"
    Write-Host "`nRun evaluations first:"
    Write-Host "  .\tests\run-vally-eval.ps1 -Workspace <name> -Skill <skill>"
    exit 0
}

# Parse results
$results = @()
foreach ($file in $resultFiles) {
    try {
        # Determine eval name from directory structure.
        # Vally writes results to: tests/.vally-results/<eval-name>/<timestamp>/results.jsonl
        # so $file.Directory.Name is the timestamp dir and Parent.Name is the eval name.
        $evalName = $file.Directory.Name
        if ($evalName -match "^\d{4}-\d{2}-\d{2}") {
            $parentName = $file.Directory.Parent.Name
            if ($parentName -and $parentName -ne ".vally-results") {
                $evalName = $parentName
            } else {
                $evalName = "run-$($file.Directory.Name)"
            }
        }

        # Parse JSONL (one JSON per line)
        $lines = Get-Content $file.FullName -Encoding utf8
        $entries = @()
        foreach ($line in $lines) {
            $trimmed = $line.Trim()
            if ($trimmed -and $trimmed.StartsWith('{')) {
                try {
                    $parsed = $trimmed | ConvertFrom-Json
                    if ($parsed.gradeResult -and $parsed.gradeResult.stimulusName) {
                        $entries += $parsed
                    }
                } catch {}
            }
        }

        # Read staged eval.yaml path from summary line if present
        $evalMd = Join-Path $file.Directory.FullName "eval-results.md"
        if (Test-Path $evalMd) {
            $mdContent = Get-Content $evalMd -Raw -Encoding utf8
            if ($mdContent -match 'evaluation for ([\w-]+)') {
                $evalName = $Matches[1]
            } elseif ($mdContent -match 'Composition matrix variant') {
                $evalName = "spark-consumption-cli-isolated"
            } elseif ($mdContent -match '([\w-]+)-integration-eval') {
                $evalName = $Matches[1]
            } elseif ($mdContent -match '([\w-]+)-eval') {
                $evalName = $Matches[1]
            }
        }

        # Determine suite from eval name
        $suite = "unknown"
        if ($evalName -match "isolated") { $suite = "composition" }
        elseif ($evalName -match "consumption") { $suite = "consumption" }
        elseif ($evalName -match "authoring") { $suite = "authoring" }
        elseif ($evalName -match "operations") { $suite = "operations" }

        foreach ($entry in $entries) {
            $tokenTotal = 0
            $wallTime = 0
            $score = 0
            $stimulusName = ""

            # Extract from gradeResult
            if ($entry.gradeResult) {
                $score = if ($entry.gradeResult.score -ne $null) { [double]$entry.gradeResult.score } else { 0 }
                $stimulusName = if ($entry.gradeResult.stimulusName) { $entry.gradeResult.stimulusName } else { "" }
            }

            # Extract from trajectory.metrics
            if ($entry.trajectory -and $entry.trajectory.metrics) {
                $m = $entry.trajectory.metrics
                if ($m.tokenUsage -and $m.tokenUsage.totalTokens) {
                    $tokenTotal = [long]$m.tokenUsage.totalTokens
                }
                if ($m.wallTimeMs) {
                    $wallTime = [double]$m.wallTimeMs / 1000
                }
            }

            $results += [PSCustomObject]@{
                Skill      = $evalName
                Suite      = $suite
                Stimulus   = $stimulusName
                Score      = $score
                TokenTotal = $tokenTotal
                WallTime   = $wallTime
                Passed     = if ($entry.gradeResult.passed) { $true } else { $false }
                Timestamp  = $file.LastWriteTime
                File       = $file.FullName
            }
        }
    } catch {
        Write-Verbose "Skipping $($file.FullName): $_"
    }
}

if ($results.Count -eq 0) {
    Write-Warning "No parseable results found. Vally result format may differ from expected."
    Write-Host "`nFiles found:" -ForegroundColor Yellow
    $resultFiles | Select-Object -First 5 | ForEach-Object { Write-Host "  $_" }
    exit 0
}

# If not -All, keep only latest per skill
if (-not $All) {
    $latestPerSkill = @{}
    foreach ($r in $results) {
        if (-not $latestPerSkill[$r.Skill] -or $r.Timestamp -gt $latestPerSkill[$r.Skill]) {
            $latestPerSkill[$r.Skill] = $r.Timestamp
        }
    }
    $results = @($results | Where-Object { $_.Timestamp -eq $latestPerSkill[$_.Skill] })
}

# Group and aggregate
$groupKey = if ($GroupBy -eq "suite") { "Suite" } else { "Skill" }
$grouped = $results | Group-Object -Property $groupKey

Write-Host "`n=== Vally Results Comparison (grouped by $GroupBy) ===" -ForegroundColor Cyan
Write-Host "Results dir: $ResultsDir" -ForegroundColor Gray
Write-Host ""

$table = @()
foreach ($group in $grouped | Sort-Object Name) {
    $items = @($group.Group)
    $avgScore = ($items | Measure-Object -Property Score -Average).Average
    $avgTokenTotal = ($items | Measure-Object -Property TokenTotal -Average).Average
    $avgWallTime = ($items | Measure-Object -Property WallTime -Average).Average
    $trialCount = $items.Count
    $stimuliCount = ($items | Select-Object -ExpandProperty Stimulus -Unique | Where-Object { $_ }).Count
    $passCount = @($items | Where-Object { $_.Passed }).Count
    $passRate = if ($trialCount -gt 0) { $passCount / $trialCount * 100 } else { 0 }

    $table += [PSCustomObject]@{
        $groupKey        = $group.Name
        Stimuli          = $stimuliCount
        Trials           = $trialCount
        "Pass Rate"      = "{0:N0}%" -f $passRate
        "Avg Score"      = "{0:N2}" -f $avgScore
        "Avg Tokens"     = "{0:N0}" -f $avgTokenTotal
        "Avg Time (s)"   = "{0:N1}" -f $avgWallTime
    }
}

$table | Format-Table -AutoSize

# Summary
Write-Host "--- Summary ---" -ForegroundColor Gray
$totalTrials = ($results | Measure-Object).Count
$totalStimuli = ($results | Select-Object -ExpandProperty Stimulus -Unique | Where-Object { $_ }).Count
$overallAvgScore = ($results | Measure-Object -Property Score -Average).Average
$overallAvgTokens = ($results | Measure-Object -Property TokenTotal -Average).Average
$overallPassCount = ($results | Where-Object { $_.Passed }).Count
Write-Host "Total trials: $totalTrials ($totalStimuli distinct stimuli) | Passed: $overallPassCount/$totalTrials | Avg score: $("{0:N2}" -f $overallAvgScore) | Avg tokens: $("{0:N0}" -f $overallAvgTokens)"
Write-Host ""
