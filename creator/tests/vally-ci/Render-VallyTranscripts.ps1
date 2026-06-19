<#
.SYNOPSIS
    Render Vally results.jsonl into per-trial human-readable transcripts (.txt).

.DESCRIPTION
    Vally ships every trial's full conversation as a single line in
    results.jsonl (nested under trajectory.events[]). Debugging a failing
    trial from that format requires writing a parser each time. This script
    walks all results.jsonl files under a root directory and produces one
    plain-text transcript per trial, mirroring the per-test _output.txt
    format the legacy smoke harness used.

    For each line in results.jsonl, writes:
        transcripts/<evalName>__<stimulusName>__trial<N>.txt

    Each transcript shows: stim prompt, per-grader pass/fail with evidence,
    then the event stream as USER / ASSISTANT / >> tool_call / << tool_result.
    No data is fabricated; everything comes from the trajectory as-is.

.PARAMETER ResultsRoot
    Directory to walk recursively for results.jsonl files. Defaults to
    $env:VALLY_RESULTS_DIR if set, else current dir.

.PARAMETER OutputDir
    Where to write the *.txt transcripts. Defaults to
    <ResultsRoot>/transcripts.

.EXAMPLE
    pwsh -File tests/vally-ci/Render-VallyTranscripts.ps1 `
        -ResultsRoot $env:VALLY_RESULTS_DIR
#>
[CmdletBinding()]
param(
    [string]$ResultsRoot = $(if ($env:VALLY_RESULTS_DIR) { $env:VALLY_RESULTS_DIR } else { (Get-Location).Path }),
    [string]$OutputDir
)

$ErrorActionPreference = 'Stop'

# Producer-side Evidence redaction (GUIDs, bearer tokens, tenant= query
# strings, 500-char cap) -- shared with Export-VallySchemaArtifact.ps1 so
# both producer surfaces strip the same leak vectors before content lands
# in an artifact. Without this, AZURE_TENANT_ID GUIDs, workspace IDs, and
# anything an MCP tool response surfaces (bearer headers, tenant= URLs)
# would land verbatim in `transcripts/*.txt` files that ship in the
# 30-day-retained shard artifact.
. (Join-Path $PSScriptRoot 'Get-RedactedEvidence.ps1')

if (-not $OutputDir) { $OutputDir = Join-Path $ResultsRoot 'transcripts' }
if (-not (Test-Path $OutputDir)) { New-Item -Path $OutputDir -ItemType Directory -Force | Out-Null }

# Map characters that are invalid in Windows filenames to '_' so the produced
# transcript filename is portable across uploaders and download tooling.
$invalidChars = [System.IO.Path]::GetInvalidFileNameChars() + @(':', '/', '\\')
function script:Sanitize-FileNamePart {
    param([string]$Value)
    $sb = New-Object System.Text.StringBuilder
    foreach ($c in $Value.ToCharArray()) {
        if ($invalidChars -contains $c) { [void]$sb.Append('_') }
        else { [void]$sb.Append($c) }
    }
    $out = $sb.ToString().Trim()
    if (-not $out) { $out = 'unnamed' }
    if ($out.Length -gt 80) { $out = $out.Substring(0, 80) }
    return $out
}

function script:Format-EventStream {
    param($Events)
    $sb = New-Object System.Text.StringBuilder
    foreach ($e in $Events) {
        if (-not $e) { continue }
        $type = $e.type
        $d = $e.data
        switch ($type) {
            'user_message' {
                $content = if ($d -and $d.content) { [string]$d.content } else { '' }
                [void]$sb.AppendLine("[USER]")
                [void]$sb.AppendLine((Get-RedactedEvidence -Text $content))
                [void]$sb.AppendLine('')
            }
            'assistant_message' {
                $content = if ($d -and $d.content) { [string]$d.content } else { '' }
                if ($content.Trim()) {
                    [void]$sb.AppendLine("[ASSISTANT]")
                    [void]$sb.AppendLine((Get-RedactedEvidence -Text $content))
                    [void]$sb.AppendLine('')
                }
            }
            'tool_call' {
                $name = if ($d) { $d.toolName } else { '?' }
                $args = if ($d -and $d.arguments) { $d.arguments | ConvertTo-Json -Compress -Depth 5 } else { '{}' }
                # Length cap happens inside Get-RedactedEvidence (500-char cap)
                # so we don't need the previous 500-char substring step here.
                [void]$sb.AppendLine("  >> tool_call: $name $(Get-RedactedEvidence -Text $args)")
            }
            'tool_result' {
                $name = if ($d) { $d.toolName } else { '?' }
                $ok = if ($d -and $d.PSObject.Properties['success']) { $d.success } else { $true }
                $tag = if ($ok) { 'OK' } else { 'FAIL' }
                $result = if ($d -and $d.PSObject.Properties['result']) { $d.result } else { '' }
                $resultStr = if ($result -is [string]) { $result } else { ($result | ConvertTo-Json -Compress -Depth 5 -ErrorAction SilentlyContinue) }
                [void]$sb.AppendLine("  << tool_result [$tag] ${name}: $(Get-RedactedEvidence -Text $resultStr)")
            }
            default { } # turn_start / turn_end / token_usage intentionally omitted to keep transcripts readable
        }
    }
    return $sb.ToString()
}

$jsonlFiles = Get-ChildItem -Path $ResultsRoot -Recurse -Force -Filter 'results.jsonl' -ErrorAction SilentlyContinue
if (-not $jsonlFiles) {
    Write-Host "[Render-VallyTranscripts] No results.jsonl found under $ResultsRoot; nothing to render."
    exit 0
}

$trialCount = 0
# Counter keyed by "<evalName>|<stimName>" so each stim's trials number
# 1..N independently (matches the legacy smoke harness's per-test output
# numbering). Keying only by evalName previously caused 4-stim evals at
# runs=1 to produce trial1/trial2/trial3/trial4 across stims instead of
# all four reading as trial1.
$evalCount = @{}
foreach ($jsonl in $jsonlFiles) {
    $lines = Get-Content -Path $jsonl.FullName -ErrorAction SilentlyContinue
    foreach ($line in $lines) {
        if (-not $line -or -not $line.Trim()) { continue }
        try {
            $t = $line | ConvertFrom-Json -ErrorAction Stop
        } catch {
            Write-Warning "[Render-VallyTranscripts] Skipping malformed line in $($jsonl.FullName)"
            continue
        }
        $gr = $t.gradeResult
        $traj = $t.trajectory
        if (-not $traj) { continue }

        $stim = $traj.stimulus
        $stimName = if ($stim -and $stim.name) { $stim.name } elseif ($gr -and $gr.stimulusName) { $gr.stimulusName } else { 'unknown-stim' }
        $evalName = 'unknown-eval'
        if ($stim -and $stim.tags -and $stim.tags.skill) { $evalName = $stim.tags.skill }
        elseif ($traj.metadata -and $traj.metadata.evalName) { $evalName = $traj.metadata.evalName }

        $countKey = "${evalName}|${stimName}"
        if (-not $evalCount.ContainsKey($countKey)) { $evalCount[$countKey] = 0 }
        $evalCount[$countKey] += 1
        $trialIdx = $evalCount[$countKey]

        $safeEval = Sanitize-FileNamePart $evalName
        $safeStim = Sanitize-FileNamePart $stimName
        $outPath = Join-Path $OutputDir ("{0}__{1}__trial{2}.txt" -f $safeEval, $safeStim, $trialIdx)

        $sb = New-Object System.Text.StringBuilder
        [void]$sb.AppendLine("===== TRIAL =====")
        [void]$sb.AppendLine("eval:    $evalName")
        [void]$sb.AppendLine("stim:    $stimName")
        if ($gr) {
            [void]$sb.AppendLine("passed:  $($gr.passed)")
            [void]$sb.AppendLine("score:   $($gr.score)")
        }
        if ($stim -and $stim.prompt) {
            [void]$sb.AppendLine('')
            [void]$sb.AppendLine("===== PROMPT =====")
            [void]$sb.AppendLine((Get-RedactedEvidence -Text ([string]$stim.prompt)))
        }
        if ($gr -and $gr.details) {
            [void]$sb.AppendLine('')
            [void]$sb.AppendLine("===== GRADERS =====")
            foreach ($det in $gr.details) {
                $tag = if ($det.passed) { 'PASS' } else { 'FAIL' }
                $evidence = if ($det.evidence) { [string]$det.evidence } else { '' }
                # Length cap + redaction live in Get-RedactedEvidence (500-char cap).
                [void]$sb.AppendLine("  [$tag] $($det.name) (score=$($det.score))  $(Get-RedactedEvidence -Text $evidence)")
            }
        }
        [void]$sb.AppendLine('')
        [void]$sb.AppendLine("===== TRANSCRIPT =====")
        $events = if ($traj.events) { $traj.events } else { @() }
        [void]$sb.Append((Format-EventStream -Events $events))

        [System.IO.File]::WriteAllText($outPath, $sb.ToString(), [System.Text.UTF8Encoding]::new($false))
        $trialCount += 1
    }
}

Write-Host "[Render-VallyTranscripts] Wrote $trialCount transcript(s) to $OutputDir"
