Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Describe 'Format-VallyJobSummary / Format-VallySummary' {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot 'Format-VallyJobSummary.ps1'
        . $scriptPath
    }

    Context 'happy path: aggregate with eval + stim + wall data' {
        BeforeAll {
            $script:happyAgg = @{
                Total            = 19
                Passed           = 18
                Failed           = 1
                PerEval          = @{
                    'sqldw-eval'     = @{ Total = 5; Passed = 5; Failed = 0 }
                    'lakehouse-eval' = @{ Total = 4; Passed = 3; Failed = 1 }
                }
                StimTotal        = 45
                StimPass         = 43
                StimFail         = 2
                ShardWall        = @{ 'shard0' = 120.5; 'shard1' = 95.0; 'shard2' = 110.0 }
                UsedFallback     = $false
                LoadedLineCount  = 19
                ShardLogCount    = 3
                ShardsWithJsonl  = 3
                GatingStimTotal  = 45
                GatingStimFailed = 2
                FailureRows      = @(
                    [pscustomobject]@{ Skill = 'lakehouse-eval'; Stimulus = 'Load sample'; Shard = 'shard2'; Grader = 'verify-table'; Evidence = 'Table missing' },
                    [pscustomobject]@{ Skill = 'sqldw-eval';     Stimulus = 'Query DMV';   Shard = 'shard1'; Grader = 'output-matches'; Evidence = 'Output does not match /executeQuery/' }
                )
                PerStimTokens   = @{
                    'sqldw-eval|Query DMV'              = @{ Skill = 'sqldw-eval';     Stimulus = 'Query DMV';   InputTokens = 25000; OutputTokens = 1500; TotalTokens = 26500; CacheReadTokens = 20000; CacheWriteTokens = 4000; CallCount = 12; TrialCount = 5 }
                    'lakehouse-eval|Load sample'        = @{ Skill = 'lakehouse-eval'; Stimulus = 'Load sample'; InputTokens = 16000; OutputTokens = 2000; TotalTokens = 18000; CacheReadTokens =  8000; CacheWriteTokens = 6000; CallCount =  9; TrialCount = 4 }
                }
            }
        }

        It 'returns an array of markdown lines' {
            $lines = Format-VallySummary -Aggregate $script:happyAgg -ScopeNote '(PR scope: full suite)'
            $lines | Should -BeOfType [string]
            $lines.Count | Should -BeGreaterThan 5
        }

        It 'emits the H2 heading with the scope note (no hardcoded shard count)' {
            $lines = Format-VallySummary -Aggregate $script:happyAgg -ScopeNote '(PR scope: full suite)'
            # Shard count is dynamic per PR scope (1-5 today) so the header
            # is count-neutral. Regression guard against re-introducing a
            # "5-way shard" literal that would mislead 1-3 shard runs.
            $lines[0] | Should -Be '## Vally smoke results (PR scope: full suite)'
            $lines[0] | Should -Not -Match '\d+-way shard'
        }

        It 'emits the stim + trial totals table row with correct numbers' {
            $lines = Format-VallySummary -Aggregate $script:happyAgg -ScopeNote '(test)'
            $joined = $lines -join "`n"
            $joined | Should -Match '\| Stims \(binary all-graders-pass\) \| 45 \| 43 \| 2 \|'
            $joined | Should -Match '\| Trials \(per results\.jsonl entry\) \| 19 \| 18 \| 1 \|'
        }

        It 'emits a per-skill breakdown table sorted by name (trial counts, NOT eval-level threshold)' {
            $lines = Format-VallySummary -Aggregate $script:happyAgg -ScopeNote '(test)'
            $joined = $lines -join "`n"
            # Regression: header was "Per-skill breakdown (aggregate threshold)"
            # which implied eval.yaml scoring.threshold semantics, but the
            # underlying numbers are per-results.jsonl trial counts.
            $joined | Should -Match '### Per-skill breakdown \(trial counts\)'
            $joined | Should -Not -Match 'aggregate threshold'
            # Alphabetical sort: lakehouse-eval before sqldw-eval
            $lakeIdx  = $lines.IndexOf('| lakehouse-eval | 4 | 3 | 1 |')
            $sqldwIdx = $lines.IndexOf('| sqldw-eval | 5 | 5 | 0 |')
            $lakeIdx  | Should -BeGreaterThan -1
            $sqldwIdx | Should -BeGreaterThan -1
            $lakeIdx  | Should -BeLessThan $sqldwIdx
        }

        It 'emits per-shard wall-time table with min / max / avg row' {
            $lines = Format-VallySummary -Aggregate $script:happyAgg -ScopeNote '(test)'
            $joined = $lines -join "`n"
            $joined | Should -Match '### Per-shard wall-time'
            $joined | Should -Match '\| shard0 \| 120\.5 \|'
            $joined | Should -Match '\| shard1 \| 95 \|'
            $joined | Should -Match '\| shard2 \| 110 \|'
            $joined | Should -Match '\| \*\*min / max / avg\*\* \| 95 / 120\.5 / 108\.5 \|'
        }
    }

    Context 'EBUSY case: no per-shard wall-time available' {
        It 'falls back to a pointer row when ShardWall is empty' {
            $agg = @{
                Total = 3; Passed = 3; Failed = 0
                PerEval = @{ 'a-eval' = @{ Total = 3; Passed = 3; Failed = 0 } }
                StimTotal = 3; StimPass = 3; StimFail = 0
                ShardWall = @{}
                UsedFallback = $true
                LoadedLineCount = 3
                ShardLogCount = 1
                ShardsWithJsonl = 0
                GatingStimTotal = 3; GatingStimFailed = 0
                FailureRows = @()
                PerStimTokens = @{}
            }
            $lines = Format-VallySummary -Aggregate $agg -ScopeNote '(test)'
            $joined = $lines -join "`n"
            $joined | Should -Match '\(per-shard wall-time tracked in run page; see job times\)'
            # No min/max/avg row should be emitted in this case.
            $joined | Should -Not -Match 'min / max / avg'
        }
    }

    Context 'format-drift: aggregate has zero evals' {
        It 'still produces the H2 heading and totals table (no per-eval section)' {
            $agg = @{
                Total = 0; Passed = 0; Failed = 0
                PerEval = @{}
                StimTotal = 0; StimPass = 0; StimFail = 0
                ShardWall = @{}
                UsedFallback = $true
                LoadedLineCount = 0
                ShardLogCount = 1
                ShardsWithJsonl = 0
                GatingStimTotal = 0; GatingStimFailed = 0
                FailureRows = @()
                PerStimTokens = @{}
            }
            $lines = Format-VallySummary -Aggregate $agg -ScopeNote '(BASELINE -- no skills loaded, informational only)'
            $joined = $lines -join "`n"
            $joined | Should -Match '## Vally smoke results'
            $joined | Should -Match '\| Stims \(binary all-graders-pass\) \| 0 \| 0 \| 0 \|'
            $joined | Should -Match '\| Trials \(per results\.jsonl entry\) \| 0 \| 0 \| 0 \|'
            # No per-skill breakdown when PerEval is empty.
            $joined | Should -Not -Match '### Per-skill breakdown'
            # No Grader failures section when FailureRows is empty.
            $joined | Should -Not -Match '### Grader failures'
        }
    }

    Context 'Grader failures table (the operationally important rendering)' {
        It 'emits a Grader failures section when FailureRows is non-empty' {
            $lines = Format-VallySummary -Aggregate $script:happyAgg -ScopeNote '(test)'
            $joined = $lines -join "`n"
            $joined | Should -Match '### Grader failures'
            $joined | Should -Match '\| Skill \| Stimulus \| Shard \| Grader \| Evidence \|'
            # Both fixture rows present.
            $joined | Should -Match '\| lakehouse-eval \| Load sample \| shard2 \| verify-table \| Table missing \|'
            $joined | Should -Match '\| sqldw-eval \| Query DMV \| shard1 \| output-matches \|'
        }

        It 'emits the merge-gating row in the Level totals table' {
            $lines = Format-VallySummary -Aggregate $script:happyAgg -ScopeNote '(test)'
            $joined = $lines -join "`n"
            # The 3rd row is the merge gate: GatingStimTotal=45, Failed=2.
            $joined | Should -Match '\| Stims with any grader failed \| 45 \| 43 \| 2 \|'
        }

        It 'omits the Grader failures section when FailureRows is empty' {
            $agg = @{
                Total = 3; Passed = 3; Failed = 0
                PerEval = @{ 'a-eval' = @{ Total = 3; Passed = 3; Failed = 0 } }
                StimTotal = 3; StimPass = 3; StimFail = 0
                ShardWall = @{}
                UsedFallback = $false; LoadedLineCount = 3; ShardLogCount = 1; ShardsWithJsonl = 1
                GatingStimTotal = 3; GatingStimFailed = 0
                FailureRows = @()
                PerStimTokens = @{}
            }
            $lines = Format-VallySummary -Aggregate $agg -ScopeNote '(test)'
            ($lines -join "`n") | Should -Not -Match '### Grader failures'
        }

        It 'escapes pipes and collapses newlines in evidence cells' {
            $agg = @{
                Total = 1; Passed = 0; Failed = 1
                PerEval = @{ 'a-eval' = @{ Total = 1; Passed = 0; Failed = 1 } }
                StimTotal = 1; StimPass = 0; StimFail = 1
                ShardWall = @{}
                UsedFallback = $false; LoadedLineCount = 1; ShardLogCount = 1; ShardsWithJsonl = 1
                GatingStimTotal = 1; GatingStimFailed = 1
                FailureRows = @(
                    [pscustomobject]@{ Skill = 'eh'; Stimulus = 'Create'; Shard = 'shard0'; Grader = 'verify'; Evidence = "Found | extra | pipes`nand newlines" }
                )
                PerStimTokens = @{}
            }
            $lines = Format-VallySummary -Aggregate $agg -ScopeNote '(test)'
            $joined = $lines -join "`n"
            # Pipes escaped, newline collapsed to single space.
            $joined | Should -Match 'Found \\\| extra \\\| pipes and newlines'
        }
    }

    Context 'Per-stim token usage table (cache visibility)' {
        It 'emits a Per-stim token usage section when PerStimTokens is non-empty' {
            $lines = Format-VallySummary -Aggregate $script:happyAgg -ScopeNote '(test)'
            $joined = $lines -join "`n"
            $joined | Should -Match '### Per-stim token usage \(summed across trials, sorted by total\)'
            $joined | Should -Match '\| Skill \| Stimulus \| Trials \| Calls \| Input \| Output \| Total \| Cache-read \| Cache% \| Cache-write \|'
        }

        It 'renders thousands-separated numbers and the computed Cache% per stim' {
            $lines = Format-VallySummary -Aggregate $script:happyAgg -ScopeNote '(test)'
            $joined = $lines -join "`n"
            # sqldw-eval|Query DMV: 5 trials, 12 calls, input 25000 / output 1500 / total 26500
            # / cacheRead 20000 / cacheWrite 4000. Cache% = 20000/25000 = 80%.
            # NOTE on semantics: cacheRead and cacheWrite are SUBSETS of inputTokens
            # (see Aggregate-VallyResults OUTPUTS docstring). Cache-write is shown
            # as a raw number, not a percentage -- premium price tier, but adding a
            # column would create noise without changing the triage decision.
            $joined | Should -Match '\| sqldw-eval \| Query DMV \| 5 \| 12 \| 25,000 \| 1,500 \| 26,500 \| 20,000 \| 80% \| 4,000 \|'
            # lakehouse-eval|Load sample: 4 trials, 9 calls, input 16000 / cacheRead 8000
            # / cacheWrite 6000. Cache% = 8000/16000 = 50%.
            $joined | Should -Match '\| lakehouse-eval \| Load sample \| 4 \| 9 \| 16,000 \| 2,000 \| 18,000 \| 8,000 \| 50% \| 6,000 \|'
        }

        It 'sorts by Total descending so worst-offender stims float to the top' {
            $lines = Format-VallySummary -Aggregate $script:happyAgg -ScopeNote '(test)'
            # sqldw|Query DMV total 26500, lakehouse|Load sample total 18000.
            # sqldw row should appear BEFORE lakehouse row in the rendered output.
            $sqldwIdx = $lines.IndexOf('| sqldw-eval | Query DMV | 5 | 12 | 25,000 | 1,500 | 26,500 | 20,000 | 80% | 4,000 |')
            $lakeIdx  = $lines.IndexOf('| lakehouse-eval | Load sample | 4 | 9 | 16,000 | 2,000 | 18,000 | 8,000 | 50% | 6,000 |')
            $sqldwIdx | Should -BeGreaterThan -1
            $lakeIdx  | Should -BeGreaterThan -1
            $sqldwIdx | Should -BeLessThan $lakeIdx
        }

        It 'omits the Per-stim token usage section when PerStimTokens is empty' {
            $agg = @{
                Total = 3; Passed = 3; Failed = 0
                PerEval = @{ 'a-eval' = @{ Total = 3; Passed = 3; Failed = 0 } }
                StimTotal = 3; StimPass = 3; StimFail = 0
                ShardWall = @{}
                UsedFallback = $false; LoadedLineCount = 3; ShardLogCount = 1; ShardsWithJsonl = 1
                GatingStimTotal = 3; GatingStimFailed = 0
                FailureRows = @()
                PerStimTokens = @{}
            }
            $lines = Format-VallySummary -Aggregate $agg -ScopeNote '(test)'
            ($lines -join "`n") | Should -Not -Match '### Per-stim token usage'
        }

        It 'handles zero-denominator Cache% safely (no cache, no fresh input)' {
            $agg = @{
                Total = 1; Passed = 1; Failed = 0
                PerEval = @{ 'noop-eval' = @{ Total = 1; Passed = 1; Failed = 0 } }
                StimTotal = 1; StimPass = 1; StimFail = 0
                ShardWall = @{}
                UsedFallback = $false; LoadedLineCount = 1; ShardLogCount = 1; ShardsWithJsonl = 1
                GatingStimTotal = 1; GatingStimFailed = 0
                FailureRows = @()
                PerStimTokens = @{
                    'noop-eval|noop' = @{ Skill = 'noop-eval'; Stimulus = 'noop'; InputTokens = 0; OutputTokens = 0; TotalTokens = 0; CacheReadTokens = 0; CacheWriteTokens = 0; CallCount = 0; TrialCount = 1 }
                }
            }
            $lines = Format-VallySummary -Aggregate $agg -ScopeNote '(test)'
            ($lines -join "`n") | Should -Match '\| noop-eval \| noop \| 1 \| 0 \| 0 \| 0 \| 0 \| 0 \| 0% \| 0 \|'
        }
    }

    Context 'Root-cause breakdown section (in-run job summary)' {
        It 'renders the Root-cause breakdown table when FailureRows carry RootCause' {
            $agg = @{
                Total = 4; Passed = 1; Failed = 3
                PerEval = @{ 'a-eval' = @{ Total = 4; Passed = 1; Failed = 3 } }
                StimTotal = 4; StimPass = 1; StimFail = 3
                ShardWall = @{}
                UsedFallback = $false; LoadedLineCount = 4; ShardLogCount = 1; ShardsWithJsonl = 1
                GatingStimTotal = 4; GatingStimFailed = 3
                FailureRows = @(
                    [pscustomobject]@{ Skill = 'a-eval'; Stimulus = 's1'; Shard = 'shard0'; Grader = 'wall-time-budget'; Evidence = 'x'; RootCause = 'WallTimeBudget' }
                    [pscustomobject]@{ Skill = 'a-eval'; Stimulus = 's2'; Shard = 'shard0'; Grader = 'wall-time-budget'; Evidence = 'x'; RootCause = 'WallTimeBudget' }
                    [pscustomobject]@{ Skill = 'a-eval'; Stimulus = 's3'; Shard = 'shard0'; Grader = 'verify-table';     Evidence = 'x'; RootCause = 'ContentMismatch' }
                )
                PerStimTokens = @{}
            }
            $lines = Format-VallySummary -Aggregate $agg -ScopeNote '(test)'
            $joined = $lines -join "`n"

            # Section heading present.
            $joined | Should -Match '### Root-cause breakdown'
            # Counts: WallTimeBudget=2 (most), ContentMismatch=1.
            $joined | Should -Match '\| WallTimeBudget \| 2 \|'
            $joined | Should -Match '\| ContentMismatch \| 1 \|'
            # Grader failures table includes the Root cause column.
            $joined | Should -Match '\| Skill \| Stimulus \| Shard \| Grader \| Root cause \| Evidence \|'
            $joined | Should -Match '\| a-eval \| s1 \| shard0 \| wall-time-budget \| WallTimeBudget \|'
        }

        It 'sorts the Root-cause table by descending count' {
            $agg = @{
                Total = 5; Passed = 0; Failed = 5
                PerEval = @{ 'a-eval' = @{ Total = 5; Passed = 0; Failed = 5 } }
                StimTotal = 5; StimPass = 0; StimFail = 5
                ShardWall = @{}
                UsedFallback = $false; LoadedLineCount = 5; ShardLogCount = 1; ShardsWithJsonl = 1
                GatingStimTotal = 5; GatingStimFailed = 5
                FailureRows = @(
                    [pscustomobject]@{ Skill = 'a'; Stimulus = '1'; Shard = 's0'; Grader = 'tool-calls';       Evidence = ''; RootCause = 'Routing' }
                    [pscustomobject]@{ Skill = 'a'; Stimulus = '2'; Shard = 's0'; Grader = 'tool-calls';       Evidence = ''; RootCause = 'Routing' }
                    [pscustomobject]@{ Skill = 'a'; Stimulus = '3'; Shard = 's0'; Grader = 'tool-calls';       Evidence = ''; RootCause = 'Routing' }
                    [pscustomobject]@{ Skill = 'a'; Stimulus = '4'; Shard = 's0'; Grader = 'wall-time-budget'; Evidence = ''; RootCause = 'WallTimeBudget' }
                    [pscustomobject]@{ Skill = 'a'; Stimulus = '5'; Shard = 's0'; Grader = 'opaque';           Evidence = ''; RootCause = 'Other' }
                )
                PerStimTokens = @{}
            }
            $lines = Format-VallySummary -Aggregate $agg -ScopeNote '(test)'
            $routingIdx = $lines.IndexOf('| Routing | 3 |')
            $wallIdx    = $lines.IndexOf('| WallTimeBudget | 1 |')
            $otherIdx   = $lines.IndexOf('| Other | 1 |')
            $routingIdx | Should -BeGreaterThan -1
            $wallIdx    | Should -BeGreaterThan -1
            $otherIdx   | Should -BeGreaterThan -1
            $routingIdx | Should -BeLessThan $wallIdx
        }

        It 'omits the Root-cause breakdown section when FailureRows is empty' {
            $agg = @{
                Total = 3; Passed = 3; Failed = 0
                PerEval = @{ 'a-eval' = @{ Total = 3; Passed = 3; Failed = 0 } }
                StimTotal = 3; StimPass = 3; StimFail = 0
                ShardWall = @{}
                UsedFallback = $false; LoadedLineCount = 3; ShardLogCount = 1; ShardsWithJsonl = 1
                GatingStimTotal = 3; GatingStimFailed = 0
                FailureRows = @()
                PerStimTokens = @{}
            }
            $lines = Format-VallySummary -Aggregate $agg -ScopeNote '(test)'
            ($lines -join "`n") | Should -Not -Match '### Root-cause breakdown'
        }

        It 'degrades cleanly when FailureRows lack RootCause (legacy fixtures)' {
            $agg = @{
                Total = 1; Passed = 0; Failed = 1
                PerEval = @{ 'a-eval' = @{ Total = 1; Passed = 0; Failed = 1 } }
                StimTotal = 1; StimPass = 0; StimFail = 1
                ShardWall = @{}
                UsedFallback = $false; LoadedLineCount = 1; ShardLogCount = 1; ShardsWithJsonl = 1
                GatingStimTotal = 1; GatingStimFailed = 1
                FailureRows = @(
                    [pscustomobject]@{ Skill = 'a'; Stimulus = '1'; Shard = 's0'; Grader = 'g'; Evidence = 'e' }
                )
                PerStimTokens = @{}
            }
            $lines = Format-VallySummary -Aggregate $agg -ScopeNote '(test)'
            $joined = $lines -join "`n"
            # Legacy header without Root cause column.
            $joined | Should -Match '\| Skill \| Stimulus \| Shard \| Grader \| Evidence \|'
            # Root-cause breakdown section is skipped.
            $joined | Should -Not -Match '### Root-cause breakdown'
        }
    }
}

