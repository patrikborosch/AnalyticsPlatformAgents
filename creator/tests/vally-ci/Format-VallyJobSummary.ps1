<#
.SYNOPSIS
Render a Get-VallyAggregate result into the markdown lines written to
$GITHUB_STEP_SUMMARY. Extracted from .github/workflows/fabric-smoke-vally.yml.

.DESCRIPTION
Pure function -- takes the aggregate structure + scope note (PR scope /
nightly / dispatch / baseline) and returns an array of markdown lines.
The caller joins with "`n" and appends to $env:GITHUB_STEP_SUMMARY.

Kept separate from Get-VallyAggregate so a future change to the rendered
format (e.g. adding cost / token columns) does not couple to the parser.

.PARAMETER Aggregate
The hashtable returned by Get-VallyAggregate.

.PARAMETER ScopeNote
The parenthetical scope hint shown in the H2 heading, e.g. "(PR scope: full
suite)", "(BASELINE -- no skills loaded, informational only)". The caller
computes this from $env:GITHUB_EVENT_NAME / $env:VALLY_BASELINE.

.OUTPUTS
[string[]] One entry per markdown line (no trailing newline). The caller
should `($lines -join "`n") | Out-File ... -Append`.
#>
function Format-VallySummary {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$Aggregate,

        [Parameter(Mandatory = $true)]
        [string]$ScopeNote
    )

    $lines = @()
    $lines += "## Vally smoke results $ScopeNote"
    $lines += ''
    $lines += 'Vally reports multiple levels of pass/fail. All are shown so the binary '
    $lines += 'per-stimulus signal (closest to the legacy harness''s notion of ``one test pass/fail``) '
    $lines += 'is visible alongside the per-trial threshold signal and the merge-gating signal.'
    $lines += ''
    $lines += '| Level | Total | Passed | Failed | Definition |'
    $lines += '|---|---|---|---|---|'
    $lines += "| Stims (binary all-graders-pass) | $($Aggregate.StimTotal) | $($Aggregate.StimPass) | $($Aggregate.StimFail) | One row per stimulus executed. Counts ``All graders passed.`` vs ``N grader(s) failed.`` lines emitted by vally per stim. Closest analogue to the legacy harness's per-test pass/fail. |"
    $lines += "| Trials (per results.jsonl entry) | $($Aggregate.Total) | $($Aggregate.Passed) | $($Aggregate.Failed) | One row per ``results.jsonl`` entry (one trial of a stimulus). With runs>1 a single stim contributes N trial rows. Counts gradeResult.passed directly. Trial-level failures: any single grader fail flips the row. (NOT eval.yaml scoring.threshold aggregate -- that level is rendered in the per-eval score lines vally writes to vally-run.log; surfaced via the log-fallback path or a future eval-aggregate parser.) |"
    $gatingPassed = $Aggregate.GatingStimTotal - $Aggregate.GatingStimFailed
    $lines += "| Stims with any grader failed | $($Aggregate.GatingStimTotal) | $gatingPassed | $($Aggregate.GatingStimFailed) | One row per stimulus (runs>1 collapses to one row). Counts a stim as failed if ANY grader (any layer, any trial) failed. This is the merge-gating signal -- summarise exits 1 when Failed > 0. |"
    $lines += ''

    if ($Aggregate.PerEval -and $Aggregate.PerEval.Keys.Count -gt 0) {
        $lines += '### Per-skill breakdown (trial counts)'
        $lines += ''
        $lines += '| Skill | Total | Passed | Failed |'
        $lines += '|---|---|---|---|'
        foreach ($k in ($Aggregate.PerEval.Keys | Sort-Object)) {
            $pe = $Aggregate.PerEval[$k]
            $lines += "| $k | $($pe.Total) | $($pe.Passed) | $($pe.Failed) |"
        }
        $lines += ''
    }

    # Per-shard wall-time (PR #272 retrospective). Falls back to a pointer
    # row when no "Wall time" lines were parseable (format drift or empty
    # logs).
    $lines += '### Per-shard wall-time (parsed from vally-run.log)'
    $lines += ''
    if ($Aggregate.ShardWall -and $Aggregate.ShardWall.Keys.Count -gt 0) {
        $wallValues = @($Aggregate.ShardWall.Values | ForEach-Object { [double]$_ })
        $wallMin = ($wallValues | Measure-Object -Minimum).Minimum
        $wallMax = ($wallValues | Measure-Object -Maximum).Maximum
        $wallAvg = ($wallValues | Measure-Object -Average).Average
        $lines += '| Shard | Wall time (s, sum of stim wall times) |'
        $lines += '|---|---|'
        foreach ($sk in ($Aggregate.ShardWall.Keys | Sort-Object)) {
            $lines += "| $sk | $([math]::Round([double]$Aggregate.ShardWall[$sk], 1)) |"
        }
        $lines += "| **min / max / avg** | $([math]::Round($wallMin,1)) / $([math]::Round($wallMax,1)) / $([math]::Round($wallAvg,1)) |"
    } else {
        $lines += '(per-shard wall-time tracked in run page; see job times)'
    }
    $lines += ''

    # Per-stim token usage. Vally writes inputTokens / outputTokens /
    # cacheReadTokens / cacheWriteTokens / callCount per trial entry under
    # trajectory.metrics.tokenUsage; this surfaces the per-stim rollup
    # (skill + stim) broken out by cached vs fresh. Cache reads are ~10x
    # cheaper than fresh input at most provider price points -- the Cache%
    # column makes the cost story visible (high cache% on a stim that
    # consumes token-budget = expected; low cache% on the same = real cost
    # regression). Sorted by Total descending so the worst offenders are
    # at the top of the table for quick triage. Hidden when no stim
    # exposed tokenUsage (older trial formats or budget-stripped
    # Layer-1-only runs).
    #
    # NOTE on semantics (verified against
    # evaluate/packages/core/src/trajectory/metrics-collector.ts:74
    # AND empirically against real run results.jsonl):
    #   totalTokens = inputTokens + outputTokens
    #   cacheReadTokens + cacheWriteTokens + uncachedRemainder ~= inputTokens
    # i.e. inputTokens is the WHOLE input the model saw and it partitions
    # into three sub-classes (cheap cache-hit, premium cache-write, and
    # a small uncached/dynamic remainder). cacheReadTokens and
    # cacheWriteTokens are DESCRIPTIVE SUBSETS of inputTokens, not
    # additive. So:
    #   Read%  = cacheReadTokens  / inputTokens   (cache-hit ratio; higher = cheaper)
    #   Write% = cacheWriteTokens / inputTokens   (cache-miss ratio; high = cold start
    #                                              OR unstable prompt; cache-write costs
    #                                              ~125% of base, so this is the
    #                                              priciest input class)
    # NOT cacheRead / (input + cacheRead) -- that would double-count.
    #
    # The .Contains() check tolerates hashtable fixtures that omit the
    # field entirely -- under Set-StrictMode -Version Latest the bare
    # `$Aggregate.PerStimTokens` access would throw PropertyNotFoundException.
    $perStimTokens = if ($Aggregate -is [System.Collections.IDictionary] -and $Aggregate.Contains('PerStimTokens')) {
        $Aggregate['PerStimTokens']
    } elseif ($Aggregate.PSObject.Properties['PerStimTokens']) {
        $Aggregate.PerStimTokens
    } else { $null }
    if ($perStimTokens -and $perStimTokens.Keys.Count -gt 0) {
        $lines += '### Per-stim token usage (summed across trials, sorted by total)'
        $lines += ''
        $lines += '_Input partitions into cache-read (cheap, ~10% price), cache-write (premium, ~125% price -- high values flag cold starts or unstable prompts), and a small uncached remainder._'
        $lines += ''
        $lines += '| Skill | Stimulus | Trials | Calls | Input | Output | Total | Cache-read | Cache% | Cache-write |'
        $lines += '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|'
        $sortedStims = $perStimTokens.Values | Sort-Object -Property @{ Expression = 'TotalTokens'; Descending = $true }, Skill, Stimulus
        foreach ($t in $sortedStims) {
            # Cache% = cacheRead / inputTokens (cacheRead is a SUBSET of input;
            # see semantics note above). Cache-write is shown as a raw number --
            # interesting on its own (premium ~125% price) but a percentage would
            # add noise without changing the triage call.
            $cachePct = if ($t.InputTokens -gt 0) { [math]::Round(($t.CacheReadTokens / $t.InputTokens) * 100, 1) } else { 0 }
            $lines += "| $(Format-SummaryCell $t.Skill) | $(Format-SummaryCell $t.Stimulus) | $($t.TrialCount) | $($t.CallCount) | $('{0:N0}' -f $t.InputTokens) | $('{0:N0}' -f $t.OutputTokens) | $('{0:N0}' -f $t.TotalTokens) | $('{0:N0}' -f $t.CacheReadTokens) | $cachePct% | $('{0:N0}' -f $t.CacheWriteTokens) |"
        }
        $lines += ''
    }

    # Grader failures table (one row per failing grader). Populated from
    # gradeResult.details on the JSONL path and from eval-aggregate / crash
    # lines on the log-fallback path. This is the operationally most useful
    # rendering -- it's what reviewers click first when summarise red-fails.
    if ($Aggregate.FailureRows -and $Aggregate.FailureRows.Count -gt 0) {
        $lines += '### Grader failures'
        $lines += ''
        # Render with the RootCause column when the field is present on the
        # FailureRows (added in the dashboard-ingest PR via
        # Classify-VallyFailure.ps1). The Aggregate-VallyResults output added
        # the field unconditionally; legacy callers passing pre-classifier
        # hashtable fixtures degrade to the no-RootCause shape.
        $hasRootCause = $false
        foreach ($r in $Aggregate.FailureRows) {
            if ($null -ne $r -and $r.PSObject.Properties['RootCause']) { $hasRootCause = $true; break }
        }
        if ($hasRootCause) {
            $lines += '| Skill | Stimulus | Shard | Grader | Root cause | Evidence |'
            $lines += '|---|---|---|---|---|---|'
            foreach ($row in ($Aggregate.FailureRows | Sort-Object Skill, Stimulus, Shard, Grader)) {
                $rc = if ($row.PSObject.Properties['RootCause']) { $row.RootCause } else { '' }
                $lines += "| $(Format-SummaryCell $row.Skill) | $(Format-SummaryCell $row.Stimulus) | $(Format-SummaryCell $row.Shard) | $(Format-SummaryCell $row.Grader) | $(Format-SummaryCell $rc) | $(Format-SummaryCell $row.Evidence) |"
            }
        } else {
            $lines += '| Skill | Stimulus | Shard | Grader | Evidence |'
            $lines += '|---|---|---|---|---|'
            foreach ($row in ($Aggregate.FailureRows | Sort-Object Skill, Stimulus, Shard, Grader)) {
                $lines += "| $(Format-SummaryCell $row.Skill) | $(Format-SummaryCell $row.Stimulus) | $(Format-SummaryCell $row.Shard) | $(Format-SummaryCell $row.Grader) | $(Format-SummaryCell $row.Evidence) |"
            }
        }
        $lines += ''

        # ----- Root-cause breakdown mini-table -----
        # Counts FailureRows grouped by RootCause class so PR authors see the
        # classifier output BEFORE the dashboard PR ships (per design
        # decision on Open Question 2). Hidden when none of the rows carry
        # a RootCause field (pre-classifier fixtures).
        if ($hasRootCause) {
            $rcCounts = @{}
            foreach ($r in $Aggregate.FailureRows) {
                $cls = if ($r.PSObject.Properties['RootCause'] -and $r.RootCause) { [string]$r.RootCause } else { 'Other' }
                if (-not $rcCounts.ContainsKey($cls)) { $rcCounts[$cls] = 0 }
                $rcCounts[$cls]++
            }
            if ($rcCounts.Keys.Count -gt 0) {
                $lines += '### Root-cause breakdown'
                $lines += ''
                $lines += '_Failures bucketed by the rule-based classifier in ``Classify-VallyFailure.ps1``. ``Other`` means the failure matched no rule -- consider adding a rule if a class becomes recurrent._'
                $lines += ''
                $lines += '| Root cause | Failures |'
                $lines += '|---|---:|'
                # Sort: highest count first, then class name asc (stable
                # presentation across runs).
                $sortedClasses = $rcCounts.Keys | Sort-Object @{ Expression = { $rcCounts[$_] }; Descending = $true }, @{ Expression = { $_ } }
                foreach ($cls in $sortedClasses) {
                    $lines += "| $(Format-SummaryCell $cls) | $($rcCounts[$cls]) |"
                }
                $lines += ''
            }
        }
    }

    return ,$lines
}

# Helper: escape a value safely for a markdown table cell. Pipes are
# backslash-escaped, embedded newlines collapsed to single spaces, leading
# and trailing whitespace trimmed. Empty / $null values render as a blank
# cell rather than collapsing the table column.
function Format-SummaryCell {
    param([object]$Value)
    if ($null -eq $Value) { return '' }
    $text = [string]$Value
    $text = $text -replace '\|', '\|'
    $text = $text -replace "`r?`n", ' '
    return $text.Trim()
}
