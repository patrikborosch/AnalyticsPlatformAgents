<#
.SYNOPSIS
Classify a vally run's exit code into a CI verdict (real failure vs harness-level
false-positive that should be swallowed).

.DESCRIPTION
Extracted from the inline pwsh in .github/workflows/fabric-smoke-vally.yml so the
exit-swap heuristic is unit-testable. Do NOT change behaviour here without first
adjusting Aggregate-VallyResults.ps1 in lockstep -- both modules share the same
score-line and crash-line regex shapes.

Vally 0.5.0 exits non-zero in several "all evals actually passed" scenarios that
should NOT fail CI:
  (1) Windows-only EBUSY race on post-run temp-dir cleanup (results.jsonl never
      finalised, but every eval scored).
  (2) Per-stimulus sub-grader budget trips (wall-time, turn-count, session.idle
      timeout) while the aggregate eval score still clears its threshold.

Heuristic: count "Loaded N stimul" lines (= evals invoked) and eval-level
"score: X% (threshold: Y%)" lines plus "grader(s) failed" lines. If every loaded
eval produced an outcome, the harness completed its job and the shard SUCCEEDED
-- swap the exit code to 0 regardless of whether each stim cleared its threshold.

.PARAMETER LogText
The raw stdout+stderr captured from `vally eval` (typically read from
vally-run.log via `Get-Content -Raw`). May be $null/empty if log was not captured.

.PARAMETER ExitCode
The integer exit code returned by `vally eval`. Already-zero is returned
unchanged with a no-op verdict.

.OUTPUTS
[hashtable] with keys:
  Exit         (int)    The swapped exit code (0 on swallow, original on propagate).
  Reason       (string) Human-readable explanation; empty when Exit unchanged.
  Messages     (string[]) Lines the caller should `Write-Host` to emit
                          ::warning:: / ::notice:: annotations preserving the
                          inline-pwsh behaviour. Empty when no annotation needed.
  LoadedCount  (int)    Number of "Loaded N stimul" lines matched.
  ScoredCount  (int)    Number of eval-level score lines matched.
  CrashCount   (int)    Number of eval-level "grader(s) failed" lines matched.
  BelowCount   (int)    Of ScoredCount, how many scored below their threshold.
  EbusyDetected (bool)  Whether the EBUSY-resource-busy marker was seen.
#>
function Get-VallyExitVerdict {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $false)]
        [AllowNull()]
        [AllowEmptyString()]
        [string]$LogText,

        [Parameter(Mandatory = $true)]
        [int]$ExitCode
    )

    $verdict = [ordered]@{
        Exit          = $ExitCode
        Reason        = ''
        Messages      = @()
        LoadedCount   = 0
        ScoredCount   = 0
        CrashCount    = 0
        BelowCount    = 0
        EbusyDetected = $false
    }

    if ($ExitCode -eq 0) {
        # Healthy run -- nothing to classify.
        return [hashtable]$verdict
    }

    if ([string]::IsNullOrWhiteSpace($LogText)) {
        $verdict.Messages = @("Vally exited $ExitCode -- log not captured.")
        return [hashtable]$verdict
    }

    # Strip ANSI escapes + normalise line endings to plain LF so the regexes
    # can be anchored to "\n" boundaries regardless of the runner's pty
    # handling. Collapse CRLF first (would otherwise double-up to "\n\n"),
    # then any lone CR (mac classic / pty quirks). The current regexes are
    # not line-anchored so duplicate newlines are harmless, but the order
    # matters if a future regex adds (?m) anchors.
    $logClean = $LogText -replace "`e\[[0-9;]*m", '' -replace "`r`n", "`n" -replace "`r", "`n"

    $verdict.EbusyDetected = [bool]($logClean -match 'EBUSY:\s*resource busy or locked')

    $loadedRx = [regex]'Loaded \d+ stimul'
    $loadedHits = $loadedRx.Matches($logClean)
    $verdict.LoadedCount = $loadedHits.Count

    # TODO(vally-format-drift): if vally 0.6+ reformats "Loaded N stimul" /
    # "X-eval [...] score: Y%" / "X-eval [...] grader(s) failed" lines, this
    # exit-swap silently stops swapping. Track upstream format stability in
    # https://github.com/microsoft/evaluate -- file an issue when 0.6 ships.
    # The "[model-name]" bracket block between the eval name and score: is
    # optional -- vally 0.5.0 emits it for some invocations and omits it for
    # others (observed empirically across two runs on the same vally version,
    # same wrapper invocation). The original regex required the brackets and
    # silently matched zero scores when vally chose to omit them, defeating
    # the EBUSY rescue. Making the bracket optional handles both forms.
    $scoreRx = [regex]"[\u2713\u2714\u2717\u2718]?\s*[\w\-]+-eval\s+(?:\[[^\]]+\]\s+)?score:\s*([\d.]+)%\s*\(threshold:\s*([\d.]+)%\)"
    $scores  = $scoreRx.Matches($logClean)
    $verdict.ScoredCount = $scores.Count

    # Vally emits a 'grader(s) failed' line (without a numeric score) when a stim
    # crashes its entire trial (e.g. session.idle timeout). These count toward
    # the loaded-vs-outcome balance because vally DID finish that eval (just
    # with a hard fail instead of a number). Same optional-bracket caveat applies.
    $crashRx = [regex]"[\u2713\u2714\u2717\u2718]?\s*[\w\-]+-eval\s+(?:\[[^\]]+\]\s+)?grader\(s\) failed"
    $crashes = $crashRx.Matches($logClean)
    $verdict.CrashCount = $crashes.Count

    $totalEvalOutcomes = $verdict.ScoredCount + $verdict.CrashCount

    if ($totalEvalOutcomes -gt 0 -and $verdict.LoadedCount -gt 0 -and $totalEvalOutcomes -ge $verdict.LoadedCount) {
        # Every loaded eval produced either a score or a crash line. The harness
        # did its job (provisioned workspace, ran every stimulus, captured every
        # outcome, will upload the artifact). Swap exit to 0.
        $below = 0
        foreach ($m in $scores) {
            try {
                # scoreRx captures TWO groups: Groups[1]=score, Groups[2]=threshold.
                # The eval-name prefix is NOT captured. If vally changes the
                # format and drops/adds a group, this cast throws and we degrade
                # to "treat as below-threshold" rather than stack-trace out of
                # the EBUSY-rescue path (which exists precisely to swallow
                # harness-level false-positive exits).
                $scoreVal = [double]$m.Groups[1].Value
                $thrVal   = [double]$m.Groups[2].Value
                if ($scoreVal -lt $thrVal) { $below++ }
            } catch {
                $verdict.Messages += "Warning: Score-regex parse failed (vally output drift?); treating match as below-threshold. Raw: $($m.Value); err: $_"
                $below++
            }
        }
        $verdict.BelowCount = $below

        if ($below -eq 0 -and $verdict.CrashCount -eq 0) {
            $verdict.Reason = if ($verdict.EbusyDetected) {
                'Windows EBUSY temp-dir cleanup race'
            } else {
                'sub-grader budget trip (wall-time / turn-count / session.idle) with aggregate threshold met'
            }
            $verdict.Messages += "::warning::Vally exited $ExitCode due to $($verdict.Reason), but all $($verdict.ScoredCount) eval(s) (>= $($verdict.LoadedCount) loaded) cleared their thresholds. Treating as success."
        } else {
            $verdict.Reason = 'harness completed; per-eval threshold misses or stim crashes captured in summarise step'
            $verdict.Messages += "::notice::$below of $($verdict.ScoredCount) eval(s) scored below their threshold and $($verdict.CrashCount) eval(s) crashed on timeout; the aggregate signal is captured in the summarise step and the per-eval breakdown. The shard harness completed all $($verdict.LoadedCount) loaded eval(s) -- treating as harness success."
        }
        $verdict.Exit = 0
    } elseif ($totalEvalOutcomes -lt $verdict.LoadedCount) {
        $verdict.Reason = 'partial outcomes; likely true harness crash'
        $verdict.Messages += "Warning: Vally exited $ExitCode -- only $totalEvalOutcomes of $($verdict.LoadedCount) loaded eval(s) produced any outcome (score or crash); propagating failure (likely true harness crash where vally itself died)."
    } else {
        $verdict.Reason = 'no parseable scores'
        $verdict.Messages += "Warning: Vally exited $ExitCode -- no scores parsed (log not captured or zero stims loaded); propagating failure."
    }

    return [hashtable]$verdict
}
