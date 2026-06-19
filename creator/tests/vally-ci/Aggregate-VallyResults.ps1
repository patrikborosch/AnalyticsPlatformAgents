<#
.SYNOPSIS
Aggregate vally shard artifacts into a per-eval breakdown + stim-level totals
+ per-shard wall-time. Extracted from .github/workflows/fabric-smoke-vally.yml
so the parser is unit-testable.

.DESCRIPTION
The summarise job downloads each shard's results.jsonl + vally-run.log into
$RUNNER_TEMP/all-shards/<shard-artifact>/.vally-results/<eval>/. This function
walks that tree and returns a single aggregate structure the workflow can pass
to Format-VallyJobSummary and use for the fail-on-regression decision.

Two parsing passes:
  (a) Per-trial totals from each results.jsonl entry's gradeResult.passed.
      Vally writes one JSONL line per stimulus trial; in the smoke harness
      each stim runs 1 trial per shard, so per-trial counts grouped by
      eval-name (directory) approximate per-stim counts. The per-eval
      breakdown the workflow surfaces is "trials below their eval's
      scoring.threshold" not "eval specs as a whole below threshold" --
      the distinction only matters when an eval is configured for runs>1,
      where Total grows as a multiple of the stim count.
  (b) Stim-level totals + per-shard wall-time from vally-run.log lines.

If pass (a) finds nothing (results.jsonl empty/missing across all shards due to
vally 0.5.0 Windows EBUSY cleanup race), the function falls back to parsing
eval-level score: lines + grader(s) failed lines from each vally-run.log and
sets UsedFallback=$true.

.PARAMETER ResultsRoot
The absolute path to the download-artifact output directory (typically
"$env:RUNNER_TEMP/all-shards").

.OUTPUTS
[hashtable] with keys:
  Total           (int)        Per-trial total summed across all shards
                               (one row per results.jsonl entry; or one row
                               per fallback-parsed score / grader(s) failed
                               log line when UsedFallback=$true).
  Passed          (int)        Per-trial passed (gradeResult.passed=$true,
                               or score >= threshold under fallback).
  Failed          (int)        Per-trial failed.
  PerEval         (hashtable)  EvalName -> @{ Total; Passed; Failed }, with
                               EvalName derived from the immediate parent
                               directory of each results.jsonl
                               (.vally-results/<eval>/results.jsonl).
  StimTotal       (int)        Stim-level total from vally-run.log
                               ("All graders passed." + "N grader(s) failed."
                               + session.idle timeouts).
  StimPass        (int)        Stim-level passed.
  StimFail        (int)        Stim-level failed (incl. session.idle timeouts).
  ShardWall       (hashtable)  ShardLabel -> seconds (sum of stim wall times).
  UsedFallback    (bool)       Whether per-trial counts came from log fallback.
  LoadedLineCount (int)        Sum of "Loaded N stimul" line counts across shard
                               logs. Used by the workflow to distinguish a
                               format-drift failure from a "ran clean, 0 evals
                               loaded" failure when Total ends up 0.
  ShardLogCount   (int)        Number of vally-run.log files seen across shards.
  ShardsWithJsonl (int)        Number of distinct shards that produced any parseable
                               results.jsonl content. Used to detect the mixed-EBUSY
                               scenario where some shards finalised JSONL and others
                               did not -- the per-shard divergence is the signal that
                               a partial-loss is in play, since the global Total > 0
                               keeps the harness-wide fallback dormant. The summarise
                               step emits a ::warning:: when ShardsWithJsonl <
                               ShardLogCount so operators can investigate; gate
                               semantics are unchanged. Tracking a full per-shard
                               fallback restructure as a follow-up (TODO).
  GatingStimTotal (int)        Per-stimulus total (one row per distinct
                               eval-name + stimulus-name across all shards/trials).
                               When runs>1, multiple trials of the same stim
                               collapse to ONE GatingStim row -- the merge-gate
                               counts a stim as failed if ANY trial had any
                               grader fail.
  GatingStimFailed (int)       Per-stimulus failed count. This is the merge-gating
                               signal that summarise's `if ($agg.GatingStimFailed
                               -gt 0)` consumes.
  FailureRows     (object[])   One row per failing grader: pscustomobject with
                               Skill, Stimulus, Shard, Grader, Evidence string
                               fields. Drives the "Grader failures" table in the
                               job summary; also useful for log-grep / future
                               machine consumption.
  PerStimTokens   (hashtable)  "<skill>|<stim>" -> @{ Skill; Stimulus;
                               InputTokens; OutputTokens; TotalTokens;
                               CacheReadTokens; CacheWriteTokens; CallCount;
                               TrialCount }.
                               Summed from `trajectory.metrics.tokenUsage` on
                               every results.jsonl entry. NOTE on semantics
                               (verified against
                               evaluate/packages/core/src/trajectory/metrics-collector.ts:74
                               AND empirically against real-run results.jsonl):
                                 totalTokens   = inputTokens + outputTokens
                                 cacheRead + cacheWrite + uncached ~= inputTokens
                               i.e. inputTokens is the WHOLE input the model saw,
                               which partitions into three sub-classes -- cheap
                               cache-hit (~10% price), premium cache-write
                               (~125% price; high values flag cold starts or
                               unstable prompts), and a small uncached/dynamic
                               remainder. cacheReadTokens and cacheWriteTokens
                               are DESCRIPTIVE SUBSETS of inputTokens, not
                               additive. The renderer computes
                               Cache% = cacheRead / input, NOT cacheRead /
                               (input + cacheRead). Cache-write is shown as a
                               raw number (premium ~125% price; high values
                               flag cold starts or unstable prompts).
                               Drives the "Per-stim token usage" table --
                               per-stim (not per-skill) so reviewers triaging a
                               per-stim token-budget grader fail can see the
                               cost story for THAT specific stim.
#>
function Get-VallyAggregate {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$ResultsRoot
    )

    # Dot-source the sibling classifier if not already loaded. Allows callers
    # who dot-source ONLY Aggregate-VallyResults.ps1 (e.g. the inline pwsh
    # block in fabric-smoke-vally.yml summarise job historically) to still
    # benefit from RootCause classification without coupling the file
    # ordering. Idempotent: if Get-VallyRootCause is already defined the
    # dot-source is skipped.
    if (-not (Get-Command -Name Get-VallyRootCause -ErrorAction SilentlyContinue)) {
        $classifierPath = Join-Path $PSScriptRoot 'Classify-VallyFailure.ps1'
        if (Test-Path $classifierPath) { . $classifierPath }
    }

    $aggregate = [ordered]@{
        Total            = 0
        Passed           = 0
        Failed           = 0
        PerEval          = @{}
        StimTotal        = 0
        StimPass         = 0
        StimFail         = 0
        ShardWall        = @{}
        UsedFallback     = $false
        LoadedLineCount  = 0
        ShardLogCount    = 0
        ShardsWithJsonl  = 0
        GatingStimTotal  = 0
        GatingStimFailed = 0
        FailureRows      = [System.Collections.Generic.List[object]]::new()
        PerStimTokens    = @{}
        # PerStimStatus tracks every (skill, stim) pair that had at least
        # one trial, regardless of whether trajectory.metrics.tokenUsage
        # was present. Without this, the schema emitter (which previously
        # seeded its stim universe from PerStimTokens) would silently drop
        # passing trials that had no tokenUsage data.
        PerStimStatus    = @{}
        # StimGraders tracks ALL graders (passing AND failing) per stim
        # so the dashboard disclosure can show full triage context
        # (e.g. "7 of 8 passed, 1 failed" rather than just "1 grader
        # failed" with no denominator). Keyed by "<skill>|<stim>";
        # each value is a List of @{Skill, Stimulus, Shard, Grader,
        # Passed, RootCause, Evidence}. For runs>1, multiple trials of
        # the same (shard, grader) pair are deduped via $stimGraderState
        # below using any-fail semantics (a grader is recorded as failed
        # if ANY trial failed it; mirrors the merge-gate convention).
        StimGraders      = @{}
        # Counter for malformed JSONL lines dropped by the parser. Used to
        # surface a ::warning:: annotation when > 0 so the summarise step
        # does not silently undercount per-eval rows.
        JsonlParseErrors = 0
    }

    # Per-stim gating bookkeeping (eval+stim -> bool failed-any-trial).
    # Derived to GatingStimTotal / GatingStimFailed after the JSONL pass so
    # runs>1 collapse to one stim row, not N trials.
    $stimGating = @{}

    # Per-(skill, stim, shard, grader) dedupe state for StimGraders. Carries
    # the current any-fail verdict so re-seeing the same grader on a later
    # trial can downgrade a Pass to a Fail but not vice versa. Maps the
    # composite key to the index of the entry in the corresponding
    # StimGraders list so we can mutate in place.
    $stimGraderState = @{}

    if (-not (Test-Path -Path $ResultsRoot)) {
        return [hashtable]$aggregate
    }

    # Safe property access for PSCustomObject (ConvertFrom-Json output) AND
    # hashtables. Under Set-StrictMode -Version Latest, accessing a missing
    # property on a PSCustomObject throws PropertyNotFoundException; this
    # helper returns $null instead so the per-entry parsing can tolerate
    # heterogeneous JSONL shapes (older vally trial entries without a
    # stimulus.tags block; future-vally entries that drop gradeResult.details).
    function script:Get-Prop {
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

    # ---------- Pass (a): results.jsonl per-eval ----------
    # -Force traverses dot-prefixed dirs (".vally-results" is hidden on Linux
    # by Unix convention; Windows treats the dot as a normal name character).
    # Without -Force the entire artifact tree is invisible to Get-ChildItem
    # on the ubuntu-latest runner.
    $jsonl = Get-ChildItem -Path $ResultsRoot -Recurse -Force -Filter 'results.jsonl' -ErrorAction SilentlyContinue
    $shardsWithContent = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($f in $jsonl) {
        # Artifact layout on download is
        #   $RUNNER_TEMP/all-shards/<shard-artifact>/.vally-results/<eval>/results.jsonl
        # (the shard step uses Copy-Item -Recurse to stage tests/.vally-results
        # into VALLY_RESULTS_DIR; when the destination already exists,
        # Copy-Item preserves the source dir name -- hence the extra
        # .vally-results/ level inside each shard artifact).
        # $f.Directory.Name is therefore <eval>; reverting to
        # $f.Directory.Parent.Name would collapse every eval across every shard
        # under the single key ".vally-results", destroying per-eval grouping.
        $evalDirName = $f.Directory.Name
        if ($evalDirName -eq '.vally-results' -or $evalDirName -like 'vally-smoke-results-*' -or $evalDirName -like 'shard*' -or $evalDirName -eq 'all-shards') {
            Write-Warning "Unexpected results.jsonl layout: $($f.FullName); per-eval grouping may be incorrect."
        }
        # Extract the shard label from the path (vally-smoke-results-...-shard<N>).
        # Used for both ShardsWithJsonl tracking and the FailureRows Shard column.
        $shardMatch = [regex]::Match($f.FullName, 'shard(\d+)')
        $shardLabel = if ($shardMatch.Success) { "shard$($shardMatch.Groups[1].Value)" } else { '(unknown shard)' }
        $lines = Get-Content $f.FullName -ErrorAction SilentlyContinue
        $shardEntryCount = 0
        foreach ($line in $lines) {
            if ([string]::IsNullOrWhiteSpace($line)) { continue }
            try {
                $entry = $line | ConvertFrom-Json -ErrorAction Stop
            } catch {
                $aggregate.JsonlParseErrors++
                Write-Warning "Aggregate-VallyResults: skipping malformed JSONL line in $($f.FullName): $($_.Exception.Message)"
                continue
            }
            $gr = Get-Prop $entry 'gradeResult'
            if (-not $gr) { continue }
            # Derive eval-name from trajectory.stimulus.tags.skill when present,
            # falling back to the directory name. Matches the main-branch inline
            # behavior so per-eval breakdown rows read as the skill being
            # exercised (e.g. "eventhouse-authoring-cli") rather than the dir
            # name when they differ.
            $evalName = $evalDirName
            $stimulus = Get-Prop (Get-Prop $entry 'trajectory') 'stimulus'
            $tagSkill = Get-Prop (Get-Prop $stimulus 'tags') 'skill'
            if ($tagSkill -and -not [string]::IsNullOrWhiteSpace([string]$tagSkill)) {
                $evalName = ([string]$tagSkill).Trim()
            }
            if (-not $aggregate.PerEval.ContainsKey($evalName)) {
                $aggregate.PerEval[$evalName] = @{ Total = 0; Passed = 0; Failed = 0 }
            }
            # Derive stimulus display name for the FailureRows Stimulus column
            # and the per-stim gating key. Prefer gradeResult.stimulusName,
            # then trajectory.stimulus.name, fall back to a placeholder.
            $stimulusName = '(unknown stimulus)'
            $stimName = Get-Prop $gr 'stimulusName'
            if ($stimName -and -not [string]::IsNullOrWhiteSpace([string]$stimName)) {
                $stimulusName = [string]$stimName
            } else {
                $stimNameAlt = Get-Prop $stimulus 'name'
                if ($stimNameAlt -and -not [string]::IsNullOrWhiteSpace([string]$stimNameAlt)) {
                    $stimulusName = [string]$stimNameAlt
                }
            }
            $stimKey = "$evalName|$stimulusName"
            if (-not $stimGating.ContainsKey($stimKey)) { $stimGating[$stimKey] = $false }

            # Walk gradeResult.details for per-grader pass/fail. When details
            # are present (the normal case), each failing grader gets its own
            # row in FailureRows AND each grader (passing or failing) gets
            # an entry in StimGraders so the dashboard disclosure can show
            # full triage context (X of Y graders passed). When details are
            # absent (a future vally reporter format that omits them), fall
            # back to the top-level gradeResult.passed bool.
            $thisTrialFailed = $false
            $detailsRaw = Get-Prop $gr 'details'
            $details = @()
            if ($detailsRaw) { $details = @($detailsRaw) }
            $grPassed = [bool](Get-Prop $gr 'passed')
            if ($details.Count -gt 0) {
                # Pre-resolve grader names ONCE per detail (with
                # unnamed-ordinal fallback) so the StimGraders dedupe
                # loop AND the FailureRows loop both see consistent
                # names. Without this, FailureRows would still collapse
                # on raw empty names even though StimGraders does the
                # right thing -- and the RootCause classifier's
                # grader-name rules could never match an empty string.
                $resolvedDetails = New-Object System.Collections.Generic.List[object]
                $unnamedIdx = 0
                foreach ($d in $details) {
                    $n = [string](Get-Prop $d 'name')
                    if ([string]::IsNullOrWhiteSpace($n)) {
                        $n = "(unnamed #$unnamedIdx)"
                    }
                    $unnamedIdx++
                    # Wrap as a small object exposing the resolved name
                    # alongside the original passed/evidence fields so
                    # downstream code uses one shape and one accessor.
                    $resolvedDetails.Add([pscustomobject]@{
                        name     = $n
                        passed   = [bool](Get-Prop $d 'passed')
                        evidence = [string](Get-Prop $d 'evidence')
                    })
                }

                # Populate StimGraders for EVERY detail (pass + fail), then
                # the FailureRows loop below only adds to the failed list.
                # Dedupe by (shard, grader) across trials via $stimGraderState
                # using any-fail semantics: a grader stays Passed=$true only
                # if every trial of that grader passed; a single trial fail
                # downgrades the dedup entry.
                if (-not $aggregate.StimGraders.ContainsKey($stimKey)) {
                    $aggregate.StimGraders[$stimKey] = [System.Collections.Generic.List[object]]::new()
                }
                foreach ($detail in $resolvedDetails) {
                    $detailGraderName = $detail.name
                    $detailPassed     = $detail.passed
                    $detailEvidence   = $detail.evidence
                    $dedupeKey = "$stimKey|$shardLabel|$detailGraderName"
                    if ($stimGraderState.ContainsKey($dedupeKey)) {
                        # Re-seen on a later trial. Downgrade Pass -> Fail
                        # if this trial failed; preserve the prior verdict
                        # otherwise. Carry the first failure's evidence so
                        # the dashboard shows what broke (not whichever
                        # trial happened to be processed last).
                        $idx = $stimGraderState[$dedupeKey]
                        $existing = $aggregate.StimGraders[$stimKey][$idx]
                        if (-not $detailPassed -and $existing.Passed) {
                            $rcVerdict = Get-VallyRootCause -GraderName $detailGraderName -Evidence $detailEvidence
                            $aggregate.StimGraders[$stimKey][$idx] = [pscustomobject]@{
                                Skill     = $evalName
                                Stimulus  = $stimulusName
                                Shard     = $shardLabel
                                Grader    = $detailGraderName
                                Passed    = $false
                                RootCause = $rcVerdict.RootCause
                                Evidence  = $detailEvidence
                            }
                        }
                    } else {
                        $rc = if ($detailPassed) { '' } else { (Get-VallyRootCause -GraderName $detailGraderName -Evidence $detailEvidence).RootCause }
                        $ev = if ($detailPassed) { '' } else { $detailEvidence }
                        $aggregate.StimGraders[$stimKey].Add([pscustomobject]@{
                            Skill     = $evalName
                            Stimulus  = $stimulusName
                            Shard     = $shardLabel
                            Grader    = $detailGraderName
                            Passed    = $detailPassed
                            RootCause = $rc
                            Evidence  = $ev
                        })
                        $stimGraderState[$dedupeKey] = $aggregate.StimGraders[$stimKey].Count - 1
                    }
                }

                $stimFailures = @($resolvedDetails | Where-Object { -not $_.passed })
                if ($stimFailures.Count -gt 0) {
                    $thisTrialFailed = $true
                    foreach ($detail in $stimFailures) {
                        $detailGraderName = $detail.name
                        $detailEvidence   = $detail.evidence
                        $rcVerdict        = Get-VallyRootCause -GraderName $detailGraderName -Evidence $detailEvidence
                        $aggregate.FailureRows.Add([pscustomobject]@{
                            Skill     = $evalName
                            Stimulus  = $stimulusName
                            Shard     = $shardLabel
                            Grader    = $detailGraderName
                            Evidence  = $detailEvidence
                            RootCause = $rcVerdict.RootCause
                        })
                    }
                }
            } elseif (-not $grPassed) {
                $thisTrialFailed = $true
                $grGraderName = [string](Get-Prop $gr 'name')
                $grEvidence   = [string](Get-Prop $gr 'evidence')
                $rcVerdict    = Get-VallyRootCause -GraderName $grGraderName -Evidence $grEvidence
                $aggregate.FailureRows.Add([pscustomobject]@{
                    Skill     = $evalName
                    Stimulus  = $stimulusName
                    Shard     = $shardLabel
                    Grader    = $grGraderName
                    Evidence  = $grEvidence
                    RootCause = $rcVerdict.RootCause
                })
            }
            if ($thisTrialFailed) { $stimGating[$stimKey] = $true }

            # PerStimStatus: track every (skill, stim) regardless of
            # tokenUsage presence so the schema emitter sees passing
            # stims that produced no metrics. Default Passed=true;
            # flip to false the first time ANY trial fails (mirrors
            # the $stimGating bucketing already used by the merge gate).
            if (-not $aggregate.PerStimStatus.ContainsKey($stimKey)) {
                $aggregate.PerStimStatus[$stimKey] = @{
                    Skill       = $evalName
                    Stimulus    = $stimulusName
                    Passed      = $true
                    HasAnyTrial = $true
                }
            }
            if ($thisTrialFailed) { $aggregate.PerStimStatus[$stimKey].Passed = $false }

            $aggregate.Total++
            $aggregate.PerEval[$evalName].Total++
            if ($grPassed) {
                $aggregate.Passed++
                $aggregate.PerEval[$evalName].Passed++
            } else {
                $aggregate.Failed++
                $aggregate.PerEval[$evalName].Failed++
            }

            # Per-stim token accumulation. Vally writes the per-trial token
            # summary at trajectory.metrics.tokenUsage with input/output/
            # cacheRead/cacheWrite/callCount fields (provenance:
            # evaluate/packages/core/src/trajectory/types.ts TokenMetrics).
            # Keyed by "<skill>|<stimulus>" to match the merge-gate's
            # $stimGating bucketing and the Grader failures table -- when
            # runs>1, multiple trials of the same stim sum into the same
            # row. Per-stim (not per-skill) so a reviewer triaging a
            # token-budget grader fail (which fires per-stim) can see the
            # cost story for THAT specific stim, not summed with peer
            # stims under the same skill that may have wildly different
            # cost profiles.
            $tu = Get-Prop (Get-Prop $entry 'trajectory') 'metrics' | ForEach-Object {
                if ($_) { Get-Prop $_ 'tokenUsage' }
            }
            if ($tu) {
                if (-not $aggregate.PerStimTokens.ContainsKey($stimKey)) {
                    $aggregate.PerStimTokens[$stimKey] = @{
                        Skill            = $evalName
                        Stimulus         = $stimulusName
                        InputTokens      = 0
                        OutputTokens     = 0
                        TotalTokens      = 0
                        CacheReadTokens  = 0
                        CacheWriteTokens = 0
                        CallCount        = 0
                        TrialCount       = 0
                    }
                }
                $ps = $aggregate.PerStimTokens[$stimKey]
                $ps.InputTokens      += [int](Get-Prop $tu 'inputTokens')
                $ps.OutputTokens     += [int](Get-Prop $tu 'outputTokens')
                $ps.TotalTokens      += [int](Get-Prop $tu 'totalTokens')
                $ps.CacheReadTokens  += [int](Get-Prop $tu 'cacheReadTokens')
                $ps.CacheWriteTokens += [int](Get-Prop $tu 'cacheWriteTokens')
                $ps.CallCount        += [int](Get-Prop $tu 'callCount')
                $ps.TrialCount       += 1
            }

            $shardEntryCount++
        }
        # Track which shard-artifact this jsonl came from so we can detect
        # mixed-EBUSY scenarios where some shards finalised JSONL and others
        # did not. Path shape after `vally --output-dir` adoption:
        #   $RUNNER_TEMP/all-shards/<shard-artifact>/vally-output/<timestamp>/results.jsonl
        # OR (older Copy-Item path):
        #   $RUNNER_TEMP/all-shards/<shard-artifact>/.vally-results/<eval>/results.jsonl
        # Walk parents until we find the one whose Parent IS the artifact
        # root. The path comparison is normalized to forward slashes on
        # both sides because $env:RUNNER_TEMP on Windows is a mixed-slash
        # path (D:\a\_temp/all-shards) while .Parent.FullName returns the
        # canonical Windows form (D:\a\_temp\all-shards) -- a literal `-ne`
        # never matches, the while loop runs to root, and every shard
        # collapses under one bogus name.
        if ($shardEntryCount -gt 0) {
            $normalizedRoot = ($ResultsRoot -replace '\\', '/').TrimEnd('/')
            $shardDir = $f.Directory
            while ($shardDir -and $shardDir.Parent) {
                $parentNormalized = ($shardDir.Parent.FullName -replace '\\', '/').TrimEnd('/')
                if ($parentNormalized -eq $normalizedRoot) { break }
                $shardDir = $shardDir.Parent
            }
            if ($shardDir) { [void]$shardsWithContent.Add($shardDir.Name) }
        }
    }

    # ---------- Pass (a-fallback): vally-run.log eval-level score lines ----------
    # See note above on -Force vs Linux dot-hidden traversal.
    $logs = Get-ChildItem -Path $ResultsRoot -Recurse -Force -Filter 'vally-run.log' -ErrorAction SilentlyContinue
    $aggregate.ShardLogCount = ($logs | Measure-Object).Count
    $aggregate.ShardsWithJsonl = $shardsWithContent.Count

    # Surface per-line parse drops as a workflow annotation so reviewers can
    # see when per-eval counts may be undercounted from results.jsonl
    # tail-truncation (e.g. EBUSY race writing a half-line) without failing
    # the job; the log-fallback path still catches whole-results.jsonl loss.
    if ($aggregate.JsonlParseErrors -gt 0) {
        Write-Host "::warning::Aggregate-VallyResults: dropped $($aggregate.JsonlParseErrors) malformed JSONL line(s) across $($aggregate.ShardLogCount) shard(s). Per-eval counts may be undercounted."
    }

    if ($aggregate.Total -eq 0) {
        # vally 0.5.0 on Windows frequently dies on the post-run EBUSY cleanup
        # race *before* finalising results.jsonl, even though every eval scored
        # and the scores were streamed to stdout (captured into vally-run.log).
        # Parse those score lines as a fallback so an EBUSY-driven missing
        # results.jsonl does not render as a harness-wide 0/0/0 outcome.
        $aggregate.UsedFallback = $true
        # See Classify-VallyExit.ps1 for why the [model-name] bracket is
        # optional: vally 0.5.0 emits it for some invocations and omits it
        # for others on the SAME version + wrapper invocation. The original
        # regex required it and silently parsed zero scores when vally chose
        # to omit it; that drove false-positive "harness crash" verdicts.
        $lineRx  = [regex]'([\w\-]+-eval)\s+(?:\[[^\]]*\]\s+)?score:\s*([\d.]+)%\s*\(threshold:\s*([\d.]+)%\)'
        # Vally also emits "grader(s) failed" (without a numeric score) when a
        # stim crashes its entire trial (session.idle timeout). Count these as
        # eval-level FAILS so they appear in the count and are not silently dropped.
        $crashRx = [regex]'([\w\-]+-eval)\s+(?:\[[^\]]*\]\s+)?grader\(s\) failed'
        foreach ($lf in $logs) {
            $txt = Get-Content $lf.FullName -Raw -ErrorAction SilentlyContinue
            if (-not $txt) { continue }
            $txt = $txt -replace "\u001b\[[0-9;]*m", ''
            # Per-shard label from the log path so fallback FailureRows can
            # surface the shard the eval crashed on.
            $shardMatch = [regex]::Match($lf.FullName, 'shard(\d+)')
            $shardLabel = if ($shardMatch.Success) { "shard$($shardMatch.Groups[1].Value)" } else { '(unknown shard)' }
            foreach ($ln in ($txt -split "`r?`n")) {
                $mm = $lineRx.Match($ln)
                if ($mm.Success) {
                    # Vally CLI output names evals as "<eval-dir>-eval"
                    # (e.g. "spark-authoring-cli-eval"). Strip the "-eval"
                    # suffix so fallback rows align with JSONL-path naming
                    # which uses the bare skill tag.
                    $evalName = ($mm.Groups[1].Value -replace '-eval$', '')
                    $score    = [double]$mm.Groups[2].Value
                    $thr      = [double]$mm.Groups[3].Value
                    if (-not $aggregate.PerEval.ContainsKey($evalName)) {
                        $aggregate.PerEval[$evalName] = @{ Total = 0; Passed = 0; Failed = 0 }
                    }
                    # Feed fallback into per-stim gating + FailureRows so the
                    # merge gate sees EBUSY-only failures. Without this the
                    # gate would silently pass an all-fallback run with a
                    # below-threshold eval.
                    $stimKey = "$evalName|(eval-aggregate)"
                    if (-not $stimGating.ContainsKey($stimKey)) { $stimGating[$stimKey] = $false }
                    $aggregate.Total++
                    $aggregate.PerEval[$evalName].Total++
                    if ($score -ge $thr) {
                        $aggregate.Passed++
                        $aggregate.PerEval[$evalName].Passed++
                    } else {
                        $aggregate.Failed++
                        $aggregate.PerEval[$evalName].Failed++
                        $stimGating[$stimKey] = $true
                        $thrEvidence = "Score $score% below threshold $thr% (parsed from vally-run.log; results.jsonl missing)"
                        $rcVerdict = Get-VallyRootCause -GraderName 'eval-score-threshold' -Evidence $thrEvidence
                        $aggregate.FailureRows.Add([pscustomobject]@{
                            Skill     = $evalName
                            Stimulus  = '(eval-aggregate from log fallback)'
                            Shard     = $shardLabel
                            Grader    = 'eval-score-threshold'
                            Evidence  = $thrEvidence
                            RootCause = $rcVerdict.RootCause
                        })
                    }
                    continue
                }
                $cm = $crashRx.Match($ln)
                if ($cm.Success) {
                    $evalName = ($cm.Groups[1].Value -replace '-eval$', '')
                    if (-not $aggregate.PerEval.ContainsKey($evalName)) {
                        $aggregate.PerEval[$evalName] = @{ Total = 0; Passed = 0; Failed = 0 }
                    }
                    $stimKey = "$evalName|(crash from log fallback)"
                    $stimGating[$stimKey] = $true
                    $aggregate.Total++
                    $aggregate.Failed++
                    $aggregate.PerEval[$evalName].Total++
                    $aggregate.PerEval[$evalName].Failed++
                    $crashEvidence = 'Vally reported "grader(s) failed" for the entire eval (stim trial crashed before grading)'
                    $rcVerdict = Get-VallyRootCause -GraderName 'eval-crash' -Evidence $crashEvidence
                    $aggregate.FailureRows.Add([pscustomobject]@{
                        Skill     = $evalName
                        Stimulus  = '(crash from log fallback)'
                        Shard     = $shardLabel
                        Grader    = 'eval-crash'
                        Evidence  = $crashEvidence
                        RootCause = $rcVerdict.RootCause
                    })
                }
            }
        }
    }

    # Per-stim gating totals: derived AFTER the JSONL pass + fallback so that
    # runs>1 collapses to one stim row (not N trials) and any fallback
    # contributions land in the same bookkeeping.
    $aggregate.GatingStimTotal  = $stimGating.Keys.Count
    $aggregate.GatingStimFailed = @($stimGating.Values | Where-Object { $_ }).Count

    # ---------- Pass (b): stim-level totals from vally-run.log ----------
    # Eval-level Total above counts one entry per eval spec (e.g. 19 evals);
    # stim-level counts the actual prompts executed (e.g. 45 stims), which is the
    # more intuitive "tests run" number. Vally emits "All graders passed." after
    # a passing stim and "N grader(s) failed." after a failing stim -- regardless
    # of whether the eval-level aggregate score crosses its threshold. A stim
    # that crashes on session.idle timeout emits a different per-eval-level
    # "grader(s) failed" line plus a "Timeout after Nms waiting for session.idle"
    # error.
    foreach ($lf in $logs) {
        $txt = Get-Content $lf.FullName -Raw -ErrorAction SilentlyContinue
        if (-not $txt) { continue }
        $txt = $txt -replace "\u001b\[[0-9;]*m", ''
        $shardPass    = ([regex]'All graders passed\.').Matches($txt).Count
        $shardFail    = ([regex]'\d+ grader\(s\) failed\.').Matches($txt).Count
        # Timeout-killed stims emit "Error: Error running ...: Timeout after"
        # instead of a per-stim grader summary, so they would otherwise be
        # invisible to the stim-level counter. Count them here as fails.
        $shardTimeout = ([regex]'Error: Error running .+?: Timeout after \d+ms waiting for session\.idle').Matches($txt).Count
        $aggregate.StimPass += $shardPass
        $aggregate.StimFail += $shardFail + $shardTimeout
    }
    $aggregate.StimTotal = $aggregate.StimPass + $aggregate.StimFail

    # ---------- Pass (c): per-shard wall-time from vally-run.log ----------
    # PR #272 retrospective: vally emits "Wall time     XX.Xs" per stim in its
    # run log. Sum those per shard log so the summary surfaces min/max/avg
    # shard wall-time -- the cheapest proxy for by-eval-DIR (not by-stim)
    # sharding imbalance. results.jsonl does not carry wall-time, so this
    # parses vally-run.log.
    $wallRx = [regex]'Wall time\s+([\d.]+)s'
    foreach ($lf in $logs) {
        $txt = Get-Content $lf.FullName -Raw -ErrorAction SilentlyContinue
        if (-not $txt) { continue }
        $txt = $txt -replace "\u001b\[[0-9;]*m", ''
        $shardMatch = [regex]::Match($lf.FullName, 'shard(\d+)')
        $shardLabel = if ($shardMatch.Success) { "shard$($shardMatch.Groups[1].Value)" } else { $lf.Directory.Name }
        $sum = 0.0
        foreach ($wm in $wallRx.Matches($txt)) { $sum += [double]$wm.Groups[1].Value }
        if (-not $aggregate.ShardWall.ContainsKey($shardLabel)) { $aggregate.ShardWall[$shardLabel] = 0.0 }
        $aggregate.ShardWall[$shardLabel] += $sum
    }

    # ---------- Pass (d): Loaded-line presence for format-drift detection ----------
    # If Total is still 0 after both pass (a) and the log fallback, the
    # workflow needs to know whether *any* "Loaded N stimul" line was present
    # (i.e. vally started but produced no scores -> probably format drift) vs
    # zero loaded lines (could be a setup / wrapper failure). Compute eagerly
    # so the caller does not re-walk the directory.
    $loadedAssertRx = [regex]'Loaded \d+ stimul'
    foreach ($lf in $logs) {
        $txt = Get-Content $lf.FullName -Raw -ErrorAction SilentlyContinue
        if ($txt) { $aggregate.LoadedLineCount += $loadedAssertRx.Matches($txt).Count }
    }

    return [hashtable]$aggregate
}
