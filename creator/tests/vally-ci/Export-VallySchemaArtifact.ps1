<#
.SYNOPSIS
Emit the dashboard schema artifact (per docs/skill-test-result-schema.md)
from a vally aggregate produced by Aggregate-VallyResults.ps1 + the
deep-link metadata gathered by Get-VallyDeepLinks.ps1.

.DESCRIPTION
Phase 3 of the vally dashboard ingest plan. Per-skill emission of:
  - testResults.json   keyed by stim name; per-stim binary pass = all
                       graders for that stim passed across all trials
  - token-summary.jsonl  one line per stim from PerStimTokens, preserving
                         the PR #292 semantics (totalTokens = input + output;
                         cacheRead/Write are subsets of input, NOT additive)
  - SKILL-REPORT.md      pass/fail rollup with Root cause column on failures
  - deepLinks.json       sibling file with runId + jobs + artifacts +
                         stimGraders (full pass+fail per-grader breakdown
                         for stims that had at least one grader failure;
                         passing graders carry passed:true with no
                         rootCause/evidence to keep the payload compact)

Producer-side Evidence redaction (per Open Question 4 conservative
starting point): GUIDs, bearer tokens, tenant= query strings are stripped
from any Evidence string written into the schema artifact. The redaction
runs ONLY here (emitter), NOT in the aggregator -- the in-run job summary
keeps full evidence for the PR author. Evidence is also capped at 500
chars (truncated with a single ellipsis).

Per-stim binary pass derivation: walk Aggregate.FailureRows -- the SET
of (skill, stim) pairs present in FailureRows is the set of stims with
at least one grader failure on at least one trial. Everything else in
the aggregate that maps to a stim (via PerStimTokens) is a pass. This
matches GatingStim* semantics in Aggregate-VallyResults.ps1.

Path layout (matches the documented schema):
  ${OutputRoot}/${Date}/${RunId}/${SkillArea}/testResults.json
  ${OutputRoot}/${Date}/${RunId}/${SkillArea}/token-summary.jsonl
  ${OutputRoot}/${Date}/${RunId}/${SkillArea}/SKILL-REPORT.md
  ${OutputRoot}/${Date}/${RunId}/${SkillArea}/deepLinks.json

.PARAMETER Aggregate
The hashtable returned by Get-VallyAggregate. Must carry PerEval,
FailureRows, PerStimTokens at minimum.

.PARAMETER DeepLinks
The hashtable returned by Get-VallyDeepLinks (RunId, Jobs, Artifacts).
May be $null when deep-link data is unavailable; in that case the
emitter writes a deepLinks.json containing only runId + empty
jobs/artifacts + an empty stimGraders array so the renderer degrades
silently to the existing top-level run link.

.PARAMETER OutputRoot
Root directory under which to emit the ${Date}/${RunId}/... subtree.

.PARAMETER RunId
Run identifier (typically ${github.run_id}-${github.run_attempt}).

.PARAMETER Date
Optional yyyy-MM-dd date string (UTC). Defaults to today's UTC date.

.OUTPUTS
[hashtable] with keys:
  WrittenFiles  (string[])  Absolute paths of every file emitted (one per
                            skill x file-type). Useful for in-process
                            validation + the workflow's
                            if-no-files-found: error gate.
  SkillCount    (int)       Distinct skills emitted (one subtree per skill).
  StimCount     (int)       Total stim rows written across all testResults.json.
#>
function Export-VallySchemaArtifact {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Aggregate,

        [Parameter(Mandatory = $false)]
        [AllowNull()]
        [hashtable]$DeepLinks,

        [Parameter(Mandatory = $true)]
        [string]$OutputRoot,

        [Parameter(Mandatory = $true)]
        [string]$RunId,

        [Parameter(Mandatory = $false)]
        [string]$Date = ([DateTime]::UtcNow.ToString('yyyy-MM-dd'))
    )

    if ([string]::IsNullOrWhiteSpace($RunId)) {
        throw "Export-VallySchemaArtifact: RunId is required."
    }
    if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
        throw "Export-VallySchemaArtifact: OutputRoot is required."
    }
    if (-not (Test-Path $OutputRoot)) {
        New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    }

    # Defensive: tolerate missing keys on legacy / partial fixtures.
    function script:Get-AggField {
        param([hashtable]$Agg, [string]$Name, $Default)
        if ($Agg -and $Agg.Contains($Name) -and $null -ne $Agg[$Name]) { return $Agg[$Name] }
        return $Default
    }

    $failureRows  = @(Get-AggField $Aggregate 'FailureRows' @())
    $perEval      = Get-AggField $Aggregate 'PerEval' @{}
    $perStim      = Get-AggField $Aggregate 'PerStimTokens' @{}
    $perStimStat  = Get-AggField $Aggregate 'PerStimStatus' @{}
    $usedFallback = [bool](Get-AggField $Aggregate 'UsedFallback' $false)

    # ---------------- Stim discovery (per skill) ----------------
    # The skill universe is the union of:
    #   - PerStimTokens keys (everything that emitted a tokenUsage)
    #   - FailureRows skills (stims that failed at least one grader trial)
    #   - PerEval keys (catches eval-only / log-fallback skills with no
    #     per-stim data)
    # Per-stim pass derivation walks FailureRows: a (skill, stim) pair
    # present in FailureRows is FAILED. Everything else (with stim data)
    # is PASSED. The (skill -> {stim -> failed}) bag is the data we emit.

    $skillStims = @{}        # skill -> hashtable<stim, $true (failed)>
    $skillStimEvidence = @{} # skill -> hashtable<stim, list[{grader, rootCause, evidence, shard}]>
    $skillTokenLines = @{}   # skill -> list[hashtable] one per stim
    $skillSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)

    # Seed from PerStimStatus (all stims that had ANY trial, regardless of
    # whether tokenUsage was emitted). A passing trial without tokenUsage
    # would otherwise be invisible to the dashboard. PerStimStatus is
    # populated in Aggregate-VallyResults.ps1 at the same site that
    # increments PerEval[$evalName].Total.
    foreach ($key in $perStimStat.Keys) {
        $rec = $perStimStat[$key]
        $skill = [string]$rec.Skill
        $stim  = [string]$rec.Stimulus
        if ([string]::IsNullOrWhiteSpace($skill) -or [string]::IsNullOrWhiteSpace($stim)) { continue }
        [void]$skillSet.Add($skill)
        if (-not $skillStims.ContainsKey($skill)) { $skillStims[$skill] = @{} }
        # Default state is pass; FailureRows pass below overrides to fail.
        if (-not $skillStims[$skill].ContainsKey($stim)) { $skillStims[$skill][$stim] = $false }
    }

    # Seed from PerStimTokens (passing + failing stims that exposed tokens)
    # for token-summary.jsonl emission. Also union the stim into skillStims
    # in case PerStimStatus is missing on legacy fixtures.
    foreach ($key in $perStim.Keys) {
        $rec = $perStim[$key]
        $skill = [string]$rec.Skill
        $stim  = [string]$rec.Stimulus
        if ([string]::IsNullOrWhiteSpace($skill) -or [string]::IsNullOrWhiteSpace($stim)) { continue }
        [void]$skillSet.Add($skill)
        if (-not $skillStims.ContainsKey($skill)) { $skillStims[$skill] = @{} }
        if (-not $skillStims[$skill].ContainsKey($stim)) { $skillStims[$skill][$stim] = $false }
        if (-not $skillTokenLines.ContainsKey($skill)) { $skillTokenLines[$skill] = New-Object System.Collections.Generic.List[hashtable] }
        $skillTokenLines[$skill].Add(@{
            testName         = $stim
            inputTokens      = [int]$rec.InputTokens
            outputTokens     = [int]$rec.OutputTokens
            cacheReadTokens  = [int]$rec.CacheReadTokens
            cacheWriteTokens = [int]$rec.CacheWriteTokens
        })
    }

    # Mark failures + capture evidence (redacted).
    foreach ($row in $failureRows) {
        if (-not $row) { continue }
        $skill = [string]$row.Skill
        $stim  = [string]$row.Stimulus
        if ([string]::IsNullOrWhiteSpace($skill)) { continue }
        if ([string]::IsNullOrWhiteSpace($stim))  { $stim = '(unknown stimulus)' }
        [void]$skillSet.Add($skill)
        if (-not $skillStims.ContainsKey($skill)) { $skillStims[$skill] = @{} }
        $skillStims[$skill][$stim] = $true
        if (-not $skillStimEvidence.ContainsKey($skill)) { $skillStimEvidence[$skill] = @{} }
        if (-not $skillStimEvidence[$skill].ContainsKey($stim)) {
            $skillStimEvidence[$skill][$stim] = New-Object System.Collections.Generic.List[hashtable]
        }
        $rcVal = if ($row.PSObject.Properties['RootCause'] -and $row.RootCause) { [string]$row.RootCause } else { 'Other' }
        $skillStimEvidence[$skill][$stim].Add(@{
            grader    = [string]$row.Grader
            rootCause = $rcVal
            evidence  = (Get-RedactedEvidence ([string]$row.Evidence))
            shard     = [string]$row.Shard
        })
    }

    # Seed from PerEval so eval-only / log-fallback skills appear even
    # with no per-stim data. These show up in deepLinks.json's
    # stimFailures (when they failed) but contribute zero testResults.json
    # rows (no stim name).
    foreach ($evalName in $perEval.Keys) {
        if (-not [string]::IsNullOrWhiteSpace($evalName)) { [void]$skillSet.Add($evalName) }
    }

    # ---------------- Deep-link projection ----------------
    # runId on disk MUST be the caller-supplied $RunId (typically
    # "$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"), matching the directory name
    # and the example in docs/skill-test-result-schema.md. $DeepLinks.RunId
    # is the bare run_id used for URL composition and never lands on disk.
    # workflowRunId carries the bare GitHub Actions numeric run id so
    # consumers can compose /actions/runs/{workflowRunId}/job/{job_id}
    # URLs without having to strip the attempt suffix off runId; see the
    # field table in docs/skill-test-result-schema.md.
    $dlRunId        = [string]$RunId
    $dlWorkflowRunId = if ($DeepLinks -and $DeepLinks.Contains('RunId')) {
        # Coerce to long when the caller supplied a bare numeric form;
        # otherwise fall back to stripping any -<attempt> suffix off
        # the on-disk RunId. Both branches end with a sane integer or
        # 0 (when the producer is operating without gh API access).
        # [long] (Int64) is required: real GitHub Actions run IDs are
        # routinely 10-11 digits (>2^31) and would overflow [int].
        $candidate = [string]$DeepLinks.RunId
        $parsed = [long]0
        if ([long]::TryParse(($candidate -split '-', 2)[0], [ref]$parsed)) { $parsed } else { [long]0 }
    } else {
        $parsed = [long]0
        if ([long]::TryParse(($dlRunId -split '-', 2)[0], [ref]$parsed)) { $parsed } else { [long]0 }
    }
    $dlJobs      = if ($DeepLinks -and $DeepLinks.Contains('Jobs'))      { $DeepLinks.Jobs }      else { @{} }
    $dlArtifacts = if ($DeepLinks -and $DeepLinks.Contains('Artifacts')) { $DeepLinks.Artifacts } else { @{} }

    $written = New-Object System.Collections.Generic.List[string]
    $totalStimRows = 0
    $skillCount = 0
    $dateDir = Join-Path $OutputRoot $Date
    $runDir  = Join-Path $dateDir   $RunId

    foreach ($skill in $skillSet) {
        $skillCount++
        $skillDir = Join-Path $runDir (script:Get-SafePathSegment $skill)
        if (-not (Test-Path $skillDir)) { New-Item -ItemType Directory -Path $skillDir -Force | Out-Null }

        # ---- testResults.json ----
        # `schemaVersion` is a reserved top-level field: the on-disk contract
        # version, bumped only on a breaking shape change (see
        # docs/skill-test-result-schema.md). It sits alongside the per-stim
        # entries; consumers that iterate stim rows skip any non-object
        # top-level value.
        $stimMap = if ($skillStims.ContainsKey($skill)) { $skillStims[$skill] } else { @{} }
        # `schemaVersion` is reserved for the top-level contract version stamp
        # below. A stimulus literally named `schemaVersion` would overwrite the
        # int with a stim object at `$tr[$stim]` further down, emitting
        # ambiguous JSON (consumers would read the stim object as the version).
        # Hard-fail so a producer cannot silently clobber the version stamp.
        if ($stimMap.ContainsKey('schemaVersion')) {
            throw "Stimulus name 'schemaVersion' in skill '$skill' collides with the reserved top-level testResults.json contract field. Rename the stimulus."
        }
        $tr = [ordered]@{ schemaVersion = 1 }
        foreach ($stim in ($stimMap.Keys | Sort-Object)) {
            $isFail = [bool]$stimMap[$stim]
            $isPass = -not $isFail
            $entry = [ordered]@{
                isPass      = $isPass
                rawStatus   = $(if ($isPass) { 'Y' } else { 'N' })
                foundSkills = @($skill)
                warnings    = @()
            }
            if ($isFail) {
                # Concatenate redacted evidence from the first 3 failing
                # graders -- enough to give the reviewer a triage hint
                # without flooding the dashboard cell.
                $hints = if ($skillStimEvidence.ContainsKey($skill) -and $skillStimEvidence[$skill].ContainsKey($stim)) {
                    @($skillStimEvidence[$skill][$stim])
                } else { @() }
                $msgs = foreach ($h in ($hints | Select-Object -First 3)) {
                    $g = if ($h.grader)    { $h.grader }    else { '(grader)' }
                    $e = if ($h.evidence)  { $h.evidence }  else { '' }
                    "${g}: ${e}"
                }
                $entry.message = ($msgs -join ' | ')
            } else {
                $entry.message = 'All graders passed.'
            }
            $tr[$stim] = $entry
            $totalStimRows++
        }
        $trPath = Join-Path $skillDir 'testResults.json'
        $trJson = ($tr | ConvertTo-Json -Depth 10)
        [System.IO.File]::WriteAllText($trPath, $trJson, [System.Text.UTF8Encoding]::new($false))
        $written.Add($trPath)

        # ---- token-summary.jsonl ----
        # Build content as a single LF-joined string and write via
        # WriteAllText for newline determinism. WriteAllLines uses
        # Environment.NewLine (CRLF on Windows runners), which would
        # diverge from the LF convention SKILL-REPORT.md uses one
        # screen up + the consumer side parses LF-split. Force LF.
        $tokenPath = Join-Path $skillDir 'token-summary.jsonl'
        $tokenLines = if ($skillTokenLines.ContainsKey($skill)) { @($skillTokenLines[$skill]) } else { @() }
        $jsonl = @(foreach ($t in $tokenLines) { ($t | ConvertTo-Json -Compress -Depth 5) })
        $jsonlText = if ($jsonl.Count -eq 0) { '' } else { ($jsonl -join "`n") + "`n" }
        [System.IO.File]::WriteAllText($tokenPath, $jsonlText, [System.Text.UTF8Encoding]::new($false))
        $written.Add($tokenPath)

        # ---- SKILL-REPORT.md ----
        $reportPath = Join-Path $skillDir 'SKILL-REPORT.md'
        $totalStimsHere = $stimMap.Keys.Count
        $passedHere = @($stimMap.GetEnumerator() | Where-Object { -not $_.Value }).Count
        $failedHere = $totalStimsHere - $passedHere
        $reportLines = @(
            "# Vally skill report: $skill"
            ""
            "Run: $RunId"
            "Date: $Date"
            ""
            "**Stim totals**: $passedHere passed of $totalStimsHere (failed: $failedHere)."
            ""
        )
        if ($failedHere -gt 0) {
            $reportLines += '## Failures (with root cause)'
            $reportLines += ''
            $reportLines += '| Stimulus | Grader | Root cause | Evidence |'
            $reportLines += '|---|---|---|---|'
            foreach ($stim in ($stimMap.Keys | Where-Object { $stimMap[$_] } | Sort-Object)) {
                $hints = if ($skillStimEvidence.ContainsKey($skill) -and $skillStimEvidence[$skill].ContainsKey($stim)) {
                    @($skillStimEvidence[$skill][$stim])
                } else { @() }
                foreach ($h in $hints) {
                    $stimCell = (script:Format-MdCell $stim)
                    $gCell    = (script:Format-MdCell $h.grader)
                    $rcCell   = (script:Format-MdCell $h.rootCause)
                    $eCell    = (script:Format-MdCell $h.evidence)
                    $reportLines += "| $stimCell | $gCell | $rcCell | $eCell |"
                }
            }
        } else {
            $reportLines += '_All stims passed for this skill._'
        }
        if ($usedFallback) {
            $reportLines += ''
            $reportLines += '_(Aggregate parsed via vally-run.log fallback; results.jsonl missing across all shards.)_'
        }
        # LF line endings on .md per validation gate Phase 3.
        $reportText = ($reportLines -join "`n")
        [System.IO.File]::WriteAllText($reportPath, $reportText, [System.Text.UTF8Encoding]::new($false))
        $written.Add($reportPath)

        # ---- deepLinks.json (sibling) ----
        # Build per-skill stimGraders from StimGraders for THIS skill --
        # ALL graders (pass + fail) for any stim that had at least one
        # failure. Passing stims don't need their grader list surfaced
        # in the disclosure (the disclosure exists for triage, and a
        # passing stim has nothing to triage). The renderer then shows
        # full context ("3 of 8 passed, 5 failed") instead of just the
        # failed-grader count.
        #
        # FALLBACK: when StimGraders is empty for a failing stim (no-
        # details JSONL path or log-fallback path -- aggregator adds to
        # FailureRows but not StimGraders in those branches), synthesize
        # failing-only entries from FailureRows so the disclosure still
        # has content. Without this fallback those stims render as
        # red rows with an empty disclosure.
        $stimGraders = New-Object System.Collections.Generic.List[hashtable]
        $allStimGraders = Get-AggField $Aggregate 'StimGraders' @{}
        $rowsForSkill = @($failureRows | Where-Object { [string]$_.Skill -eq $skill })
        # Set of (skill, stim) tuples that had any failing grader. Only
        # surface graders for THESE stims.
        $failingStimNames = @{}
        foreach ($r in $rowsForSkill) { $failingStimNames[[string]$r.Stimulus] = $true }
        # Track which (stim) had StimGraders coverage so we can fall back
        # for the rest.
        $stimsWithGraderCoverage = @{}
        foreach ($key in $allStimGraders.Keys) {
            # Key is "<skill>|<stim>".
            $parts = $key -split '\|', 2
            if ($parts.Count -lt 2) { continue }
            if ($parts[0] -ne $skill) { continue }
            $stimName = $parts[1]
            if (-not $failingStimNames.ContainsKey($stimName)) { continue }
            $stimsWithGraderCoverage[$stimName] = $true
            foreach ($g in @($allStimGraders[$key])) {
                $entry = [ordered]@{
                    stim      = [string]$g.Stimulus
                    shard     = [string]$g.Shard
                    grader    = [string]$g.Grader
                    passed    = [bool]$g.Passed
                }
                # rootCause + evidence only meaningful for failing graders;
                # omit them on passing entries to keep the on-disk payload
                # compact and to make the renderer's pass-vs-fail switch
                # unambiguous (presence of evidence == failure).
                if (-not $g.Passed) {
                    $rc = if ($g.PSObject.Properties['RootCause'] -and $g.RootCause) { [string]$g.RootCause } else { 'Other' }
                    $entry['rootCause'] = $rc
                    $entry['evidence']  = (Get-RedactedEvidence ([string]$g.Evidence))
                }
                # logLineOffset intentionally not emitted: per-stim line offsets
                # require pairing log lines (per-stim-trial granularity) with
                # FailureRows (per-grader granularity). The pairing is unsafe
                # for multi-skill shards or multi-grader stims, so the renderer
                # already degrades to a job-page link without a line anchor.
                # Deferred to a follow-up when the log parser tracks stim context.
                $stimGraders.Add($entry)
            }
        }
        # FALLBACK pass: any failing stim missing from StimGraders gets
        # synthesized entries from its FailureRows (failing-only).
        foreach ($r in $rowsForSkill) {
            $stimName = [string]$r.Stimulus
            if ($stimsWithGraderCoverage.ContainsKey($stimName)) { continue }
            $rc = if ($r.PSObject.Properties['RootCause'] -and $r.RootCause) { [string]$r.RootCause } else { 'Other' }
            $entry = [ordered]@{
                stim      = $stimName
                shard     = [string]$r.Shard
                grader    = [string]$r.Grader
                passed    = $false
                rootCause = $rc
                evidence  = (Get-RedactedEvidence ([string]$r.Evidence))
            }
            $stimGraders.Add($entry)
        }
        $dlObj = [ordered]@{
            runId          = $dlRunId
            workflowRunId  = $dlWorkflowRunId
            jobs           = $dlJobs
            artifacts      = $dlArtifacts
            stimGraders    = @($stimGraders)
        }
        $dlPath = Join-Path $skillDir 'deepLinks.json'
        $dlJson = ($dlObj | ConvertTo-Json -Depth 10)
        [System.IO.File]::WriteAllText($dlPath, $dlJson, [System.Text.UTF8Encoding]::new($false))
        $written.Add($dlPath)
    }

    return [hashtable]@{
        WrittenFiles = @($written)
        SkillCount   = $skillCount
        StimCount    = $totalStimRows
    }
}

# ----------------- Helpers (script-scope) -----------------

# Producer-side Evidence redaction. Strips three pattern classes that are
# the highest-risk leak vectors for an internal-repo dashboard surface:
#   - GUIDs (workspace IDs, tenant IDs in canonical 8-4-4-4-12 form)
#   - Bearer tokens (anything after 'bearer ')
#   - tenant=... query-string values
# Each match is replaced with [REDACTED]. The final Evidence is capped at
# 500 chars total: the first 499 characters are kept and a single
# horizontal ellipsis is appended (so the rendered string is exactly
# 500 chars). Longer inputs lose their tail, not their head.
#
# Implementation lives in Get-RedactedEvidence.ps1 (shared with
# Render-VallyTranscripts.ps1 so both producer surfaces stay in lockstep).
# Dot-source brings the function into this script's scope; call it as
# `Get-RedactedEvidence ...` (NOT `script:Get-RedactedEvidence`, which
# would shadow the dot-sourced function with a recursive wrapper -- bug
# observed on run 27214839689: PowerShell call-depth overflow).
. (Join-Path $PSScriptRoot 'Get-RedactedEvidence.ps1')

# Replace path-unsafe characters in a skill name (forward/back slashes,
# colons, etc.) with hyphens so an upstream skill like 'foo/bar' lands
# at .../foo-bar/testResults.json instead of breaking the directory shape.
function script:Get-SafePathSegment {
    param([string]$Name)
    if ([string]::IsNullOrWhiteSpace($Name)) { return 'unknown' }
    $n = ($Name -replace '[\\/:*?"<>|]', '-').Trim()
    # Reject dot-segments that would resolve outside the intended directory.
    # An upstream skill name of '.' or '..' would otherwise let the join
    # escape ${runDir} via path traversal (e.g. ${runDir}/../testResults.json
    # lands in the sibling of runDir, not under it). Windows also strips
    # trailing dots from filenames, so '_.' / '_..' would themselves become
    # '_' on disk -- use a no-trailing-dot replacement instead.
    if ($n -eq '.')  { return '_dot' }
    if ($n -eq '..') { return '_dotdot' }
    return $n
}

# Escape a value for a markdown table cell: pipes -> backslash-pipe,
# embedded newlines -> spaces, trim outer whitespace. Mirrors
# Format-VallyJobSummary.ps1's Format-SummaryCell so the SKILL-REPORT.md
# follows the same conventions a reviewer reads in the job summary.
function script:Format-MdCell {
    param([object]$Value)
    if ($null -eq $Value) { return '' }
    $s = [string]$Value
    $s = $s -replace '\|', '\|'
    $s = $s -replace "`r?`n", ' '
    return $s.Trim()
}
