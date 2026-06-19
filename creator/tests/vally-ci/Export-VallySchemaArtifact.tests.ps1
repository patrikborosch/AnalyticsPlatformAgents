Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Describe 'Export-VallySchemaArtifact' {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot 'Export-VallySchemaArtifact.ps1'
        . $scriptPath
        $script:ScratchRoot = Join-Path (Split-Path -Parent $PSScriptRoot) '.test-scratch' | Join-Path -ChildPath 'Export-VallySchemaArtifact'
    }

    BeforeEach {
        if (Test-Path $script:ScratchRoot) { Remove-Item -Path $script:ScratchRoot -Recurse -Force }
        New-Item -ItemType Directory -Path $script:ScratchRoot -Force | Out-Null
    }

    AfterAll {
        if (Test-Path $script:ScratchRoot) { Remove-Item -Path $script:ScratchRoot -Recurse -Force }
    }

    function script:New-Aggregate {
        param(
            [hashtable]$FailureRows = @{},
            [hashtable]$PerStimTokens = @{},
            [hashtable]$PerEval = @{},
            [bool]$UsedFallback = $false,
            [hashtable]$StimGraders = @{}
        )
        $rows = New-Object System.Collections.Generic.List[object]
        # StrictMode-safe: hashtable property access on a missing key throws
        # PropertyNotFoundException under pwsh + Set-StrictMode -Version Latest
        # (Linux CI). Use IDictionary.Contains() instead. Same pattern as
        # Aggregate-VallyResults.ps1's Get-Prop helper.
        if ($FailureRows -and $FailureRows.Contains('Rows') -and $FailureRows['Rows']) {
            foreach ($r in $FailureRows['Rows']) { $rows.Add($r) }
        }
        # Synthesise StimGraders from FailureRows when the caller didn't
        # supply one explicitly. Treats every FailureRow as a failed grader
        # with no passing peers -- enough to drive the emitter's stimGraders
        # output for tests that only care about failure surfacing. Tests
        # that need mixed pass/fail context populate $StimGraders directly.
        $gradersByStim = @{}
        if ($StimGraders -and $StimGraders.Count -gt 0) {
            foreach ($k in $StimGraders.Keys) { $gradersByStim[$k] = $StimGraders[$k] }
        } else {
            foreach ($r in $rows) {
                $key = "$($r.Skill)|$($r.Stimulus)"
                if (-not $gradersByStim.ContainsKey($key)) {
                    $gradersByStim[$key] = [System.Collections.Generic.List[object]]::new()
                }
                $rc = if ($r.PSObject.Properties['RootCause'] -and $r.RootCause) { $r.RootCause } else { 'Other' }
                $gradersByStim[$key].Add([pscustomobject]@{
                    Skill     = $r.Skill
                    Stimulus  = $r.Stimulus
                    Shard     = $r.Shard
                    Grader    = $r.Grader
                    Passed    = $false
                    RootCause = $rc
                    Evidence  = $r.Evidence
                })
            }
        }
        return @{
            Total            = 0
            Passed           = 0
            Failed           = 0
            PerEval          = $PerEval
            StimTotal        = 0
            StimPass         = 0
            StimFail         = 0
            ShardWall        = @{}
            UsedFallback     = $UsedFallback
            LoadedLineCount  = 0
            ShardLogCount    = 0
            ShardsWithJsonl  = 0
            GatingStimTotal  = 0
            GatingStimFailed = 0
            FailureRows      = $rows
            PerStimTokens    = $PerStimTokens
            PerStimStatus    = @{}
            StimGraders      = $gradersByStim
            JsonlParseErrors = 0
        }
    }

    Context 'happy path: per-skill tree with mixed pass/fail' {
        It 'writes testResults.json keyed by stim name with per-stim binary pass' {
            $agg = New-Aggregate `
                -PerStimTokens @{
                    'sqldw-consumption-cli|List tables'   = @{ Skill = 'sqldw-consumption-cli'; Stimulus = 'List tables';   InputTokens = 4000; OutputTokens = 200; CacheReadTokens = 1000; CacheWriteTokens = 0 }
                    'sqldw-consumption-cli|Query DMV'     = @{ Skill = 'sqldw-consumption-cli'; Stimulus = 'Query DMV';     InputTokens = 5000; OutputTokens = 300; CacheReadTokens = 2000; CacheWriteTokens = 0 }
                } `
                -FailureRows @{
                    Rows = @(
                        [pscustomobject]@{ Skill = 'sqldw-consumption-cli'; Stimulus = 'Query DMV'; Shard = 'shard1'; Grader = 'verify-output'; Evidence = 'mismatch'; RootCause = 'ContentMismatch' }
                    )
                }
            $dl = @{ RunId = '12345-1'; Jobs = @{ shard1 = 999 }; Artifacts = @{}; StimLogOffsets = @{} }
            $res = Export-VallySchemaArtifact -Aggregate $agg -DeepLinks $dl -OutputRoot $script:ScratchRoot -RunId '12345-1' -Date '2026-06-07'

            $skillDir = Join-Path $script:ScratchRoot '2026-06-07/12345-1/sqldw-consumption-cli'
            (Test-Path "$skillDir/testResults.json") | Should -BeTrue
            (Test-Path "$skillDir/token-summary.jsonl") | Should -BeTrue
            (Test-Path "$skillDir/SKILL-REPORT.md") | Should -BeTrue
            (Test-Path "$skillDir/deepLinks.json") | Should -BeTrue

            $tr = Get-Content "$skillDir/testResults.json" -Raw | ConvertFrom-Json
            $tr.'List tables'.isPass | Should -BeTrue
            $tr.'List tables'.rawStatus | Should -Be 'Y'
            $tr.'Query DMV'.isPass | Should -BeFalse
            $tr.'Query DMV'.rawStatus | Should -Be 'N'
            # Message carries the redacted evidence + grader.
            $tr.'Query DMV'.message | Should -Match 'verify-output.*mismatch'

            $res.SkillCount | Should -Be 1
            $res.StimCount  | Should -Be 2
        }

        It 'stamps schemaVersion = 1 at the top level of testResults.json' {
            $agg = New-Aggregate -PerStimTokens @{
                'sk|s1' = @{ Skill = 'sk'; Stimulus = 's1'; InputTokens = 1; OutputTokens = 1; CacheReadTokens = 0; CacheWriteTokens = 0 }
            }
            Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r-sv' -Date '2026-06-07' | Out-Null
            $tr = Get-Content (Join-Path $script:ScratchRoot '2026-06-07/r-sv/sk/testResults.json') -Raw | ConvertFrom-Json
            # Reserved top-level on-disk contract version (docs/skill-test-result-schema.md);
            # bumped only on a breaking shape change. Sits alongside per-stim entries.
            $tr.schemaVersion | Should -Be 1
            # The per-stim entries still render alongside the version stamp.
            $tr.'s1'.isPass | Should -BeTrue
        }

        It 'hard-fails when a stimulus name collides with the reserved schemaVersion key' {
            # A stim literally named `schemaVersion` would clobber the reserved
            # top-level contract version with a stim object, emitting ambiguous
            # JSON. The writer must hard-fail instead of silently overwriting.
            $agg = New-Aggregate -PerStimTokens @{
                'sk|schemaVersion' = @{ Skill = 'sk'; Stimulus = 'schemaVersion'; InputTokens = 1; OutputTokens = 1; CacheReadTokens = 0; CacheWriteTokens = 0 }
            }
            { Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r-reserved' -Date '2026-06-07' } |
                Should -Throw -ExpectedMessage "*'schemaVersion'*reserved*"
        }

        It 'preserves token-summary.jsonl semantics (no cache double-count, no totalTokens emission)' {
            # Schema's token-summary.jsonl carries inputTokens, outputTokens,
            # cacheReadTokens, cacheWriteTokens. NO totalTokens field --
            # the consumer computes total = input + output. Cache subsets
            # remain subsets (NOT added on top).
            $agg = New-Aggregate -PerStimTokens @{
                'a|s' = @{ Skill = 'a'; Stimulus = 's'; InputTokens = 1000; OutputTokens = 100; CacheReadTokens = 800; CacheWriteTokens = 50 }
            }
            Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r1' -Date '2026-06-07' | Out-Null
            $jsonl = Get-Content (Join-Path $script:ScratchRoot '2026-06-07/r1/a/token-summary.jsonl')
            $rec = $jsonl | Select-Object -First 1 | ConvertFrom-Json
            $rec.testName         | Should -Be 's'
            $rec.inputTokens      | Should -Be 1000
            $rec.outputTokens     | Should -Be 100
            $rec.cacheReadTokens  | Should -Be 800
            $rec.cacheWriteTokens | Should -Be 50
            # totalTokens MUST NOT appear; the dashboard derives it as
            # input + output (matches the PR #292 confirmed semantics).
            $rec.PSObject.Properties['totalTokens'] | Should -BeNullOrEmpty
        }

        It 'writes token-summary.jsonl with LF newlines (not CRLF) for cross-platform determinism' {
            # WriteAllLines uses Environment.NewLine which is CRLF on
            # Windows runners. The schema convention here (matching
            # SKILL-REPORT.md) is LF. Regression test for the CRLF
            # producer bug: assert no \r in the written file.
            $agg = New-Aggregate -PerStimTokens @{
                'a|s1' = @{ Skill = 'a'; Stimulus = 's1'; InputTokens = 1; OutputTokens = 1; CacheReadTokens = 0; CacheWriteTokens = 0 }
                'a|s2' = @{ Skill = 'a'; Stimulus = 's2'; InputTokens = 2; OutputTokens = 2; CacheReadTokens = 0; CacheWriteTokens = 0 }
            }
            Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r-lf' -Date '2026-06-07' | Out-Null
            $path = Join-Path $script:ScratchRoot '2026-06-07/r-lf/a/token-summary.jsonl'
            $bytes = [System.IO.File]::ReadAllBytes($path)
            # Assert: no 0x0D (CR) anywhere; at least one 0x0A (LF) line terminator.
            ($bytes -contains [byte]0x0D) | Should -BeFalse
            ($bytes -contains [byte]0x0A) | Should -BeTrue
        }
    }

    Context 'all-pass case' {
        It 'emits only passing rows when FailureRows is empty' {
            $agg = New-Aggregate -PerStimTokens @{
                'foo|s1' = @{ Skill = 'foo'; Stimulus = 's1'; InputTokens = 1; OutputTokens = 1; CacheReadTokens = 0; CacheWriteTokens = 0 }
            }
            Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r' -Date '2026-06-07' | Out-Null
            $tr = Get-Content (Join-Path $script:ScratchRoot '2026-06-07/r/foo/testResults.json') -Raw | ConvertFrom-Json
            $tr.'s1'.isPass | Should -BeTrue
            $tr.'s1'.message | Should -Be 'All graders passed.'
        }
    }

    Context 'empty case (no stims at all)' {
        It 'still writes the per-skill files when PerEval has the skill but no stims exist' {
            $agg = New-Aggregate -PerEval @{ 'eval-only-skill' = @{ Total = 0; Passed = 0; Failed = 0 } }
            $res = Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r' -Date '2026-06-07'
            $skillDir = Join-Path $script:ScratchRoot '2026-06-07/r/eval-only-skill'
            (Test-Path "$skillDir/testResults.json") | Should -BeTrue
            (Test-Path "$skillDir/deepLinks.json") | Should -BeTrue
            # The version stamp is present even when no stims exist, and it is
            # NOT counted as a stim (StimCount stays 0).
            $trEmpty = Get-Content "$skillDir/testResults.json" -Raw | ConvertFrom-Json
            $trEmpty.schemaVersion | Should -Be 1
            $res.StimCount | Should -Be 0
        }
    }

    Context 'gating-only-fail case (log-fallback)' {
        It 'records (eval-aggregate from log fallback) as a failing stim' {
            $agg = New-Aggregate -UsedFallback $true `
                -PerEval @{ 'powerbi-authoring-cli' = @{ Total = 1; Passed = 0; Failed = 1 } } `
                -FailureRows @{
                    Rows = @(
                        [pscustomobject]@{ Skill = 'powerbi-authoring-cli'; Stimulus = '(eval-aggregate from log fallback)'; Shard = 'shard2'; Grader = 'eval-score-threshold'; Evidence = 'Score 82% below threshold 95%'; RootCause = 'EvalThreshold' }
                    )
                }
            Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r' -Date '2026-06-07' | Out-Null
            $report = Get-Content (Join-Path $script:ScratchRoot '2026-06-07/r/powerbi-authoring-cli/SKILL-REPORT.md') -Raw
            $report | Should -Match 'EvalThreshold'
            $report | Should -Match 'fallback'
        }
    }

    Context 'missing-JSONL EBUSY fixture (degraded but valid)' {
        It 'still writes a valid per-skill tree when only PerEval+FailureRows are populated (no PerStimTokens)' {
            # Mirrors the Windows EBUSY race: results.jsonl never landed,
            # but vally-run.log fallback captured eval-level failures.
            $agg = New-Aggregate -UsedFallback $true `
                -PerEval @{ 'spark-authoring-cli' = @{ Total = 1; Passed = 0; Failed = 1 } } `
                -FailureRows @{
                    Rows = @(
                        [pscustomobject]@{ Skill = 'spark-authoring-cli'; Stimulus = '(crash from log fallback)'; Shard = 'shard0'; Grader = 'eval-crash'; Evidence = 'grader(s) failed'; RootCause = 'HarnessCrash' }
                    )
                }
            $res = Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r' -Date '2026-06-07'
            $skillDir = Join-Path $script:ScratchRoot '2026-06-07/r/spark-authoring-cli'
            (Test-Path "$skillDir/testResults.json") | Should -BeTrue
            (Test-Path "$skillDir/token-summary.jsonl") | Should -BeTrue
            # token-summary.jsonl exists but is empty (degraded shape).
            (Get-Content "$skillDir/token-summary.jsonl" -Raw -ErrorAction SilentlyContinue) | Should -BeNullOrEmpty
            # deepLinks.json has stimGraders populated with the crash row.
            $dl = Get-Content "$skillDir/deepLinks.json" -Raw | ConvertFrom-Json
            $dl.stimGraders.Count | Should -Be 1
            $dl.stimGraders[0].rootCause | Should -Be 'HarnessCrash'
            $dl.stimGraders[0].passed | Should -BeFalse
            $res.SkillCount | Should -Be 1
        }
    }

    Context 'deepLinks.json shape' {
        It 'embeds runId, jobs, artifacts, and stimGraders' {
            $agg = New-Aggregate -FailureRows @{
                Rows = @(
                    [pscustomobject]@{ Skill = 'sk'; Stimulus = 'st'; Shard = 'shard3'; Grader = 'g'; Evidence = 'e'; RootCause = 'Other' }
                )
            }
            $dl = @{
                RunId = '99'
                Jobs = @{ shard1 = 111; shard2 = 222; shard3 = 333 }
                Artifacts = @{ 'vally-smoke-results-99-1-shard3' = 7777 }
                StimLogOffsets = @{}
            }
            Export-VallySchemaArtifact -Aggregate $agg -DeepLinks $dl -OutputRoot $script:ScratchRoot -RunId '99' -Date '2026-06-07' | Out-Null
            $obj = Get-Content (Join-Path $script:ScratchRoot '2026-06-07/99/sk/deepLinks.json') -Raw | ConvertFrom-Json
            $obj.runId | Should -Be '99'
            $obj.jobs.shard3 | Should -Be 333
            $obj.artifacts.'vally-smoke-results-99-1-shard3' | Should -Be 7777
            $obj.stimGraders.Count | Should -Be 1
            $obj.stimGraders[0].stim     | Should -Be 'st'
            $obj.stimGraders[0].shard    | Should -Be 'shard3'
            $obj.stimGraders[0].rootCause | Should -Be 'Other'
            $obj.stimGraders[0].passed   | Should -BeFalse
        }

        It 'tolerates a null DeepLinks parameter (writes runId-only deepLinks.json)' {
            $agg = New-Aggregate -PerStimTokens @{
                'sk|st' = @{ Skill = 'sk'; Stimulus = 'st'; InputTokens = 1; OutputTokens = 1; CacheReadTokens = 0; CacheWriteTokens = 0 }
            }
            Export-VallySchemaArtifact -Aggregate $agg -DeepLinks $null -OutputRoot $script:ScratchRoot -RunId 'rrr' -Date '2026-06-07' | Out-Null
            $obj = Get-Content (Join-Path $script:ScratchRoot '2026-06-07/rrr/sk/deepLinks.json') -Raw | ConvertFrom-Json
            $obj.runId | Should -Be 'rrr'
        }

        It 'uses the on-disk runId parameter (NOT DeepLinks.RunId) so the field matches the directory name + schema example' {
            # docs/skill-test-result-schema.md example uses "12345678-1"
            # (run_id-attempt); $DeepLinks.RunId is the bare run_id used
            # for URL composition and must NOT land on disk.
            $agg = New-Aggregate -PerStimTokens @{
                'sk|st' = @{ Skill = 'sk'; Stimulus = 'st'; InputTokens = 1; OutputTokens = 1; CacheReadTokens = 0; CacheWriteTokens = 0 }
            }
            $dl = @{ RunId = '12345678'; Jobs = @{}; Artifacts = @{} }
            Export-VallySchemaArtifact -Aggregate $agg -DeepLinks $dl -OutputRoot $script:ScratchRoot -RunId '12345678-1' -Date '2026-06-07' | Out-Null
            $obj = Get-Content (Join-Path $script:ScratchRoot '2026-06-07/12345678-1/sk/deepLinks.json') -Raw | ConvertFrom-Json
            $obj.runId | Should -Be '12345678-1'
        }

        It 'emits workflowRunId as bare numeric for URL composition (separate from runId)' {
            # runId carries the attempt suffix (matches directory name);
            # workflowRunId carries the bare numeric so consumers can
            # build /actions/runs/{workflowRunId}/job/{id} without
            # having to strip the suffix.
            $agg = New-Aggregate -PerStimTokens @{
                'sk|st' = @{ Skill = 'sk'; Stimulus = 'st'; InputTokens = 1; OutputTokens = 1; CacheReadTokens = 0; CacheWriteTokens = 0 }
            }
            $dl = @{ RunId = '12345678'; Jobs = @{}; Artifacts = @{} }
            Export-VallySchemaArtifact -Aggregate $agg -DeepLinks $dl -OutputRoot $script:ScratchRoot -RunId '12345678-1' -Date '2026-06-07' | Out-Null
            $obj = Get-Content (Join-Path $script:ScratchRoot '2026-06-07/12345678-1/sk/deepLinks.json') -Raw | ConvertFrom-Json
            $obj.runId         | Should -Be '12345678-1'
            $obj.workflowRunId | Should -Be 12345678
        }

        It 'falls back to RunId-parameter parse when DeepLinks is null' {
            # Even without DeepLinks, workflowRunId should still be a bare
            # numeric (parsed from the RunId parameter's leading segment).
            $agg = New-Aggregate -PerStimTokens @{
                'sk|st' = @{ Skill = 'sk'; Stimulus = 'st'; InputTokens = 1; OutputTokens = 1; CacheReadTokens = 0; CacheWriteTokens = 0 }
            }
            Export-VallySchemaArtifact -Aggregate $agg -DeepLinks $null -OutputRoot $script:ScratchRoot -RunId '99887766-2' -Date '2026-06-07' | Out-Null
            $obj = Get-Content (Join-Path $script:ScratchRoot '2026-06-07/99887766-2/sk/deepLinks.json') -Raw | ConvertFrom-Json
            $obj.workflowRunId | Should -Be 99887766
        }

        It 'parses 11-digit (Int64-range) run IDs without overflow into workflowRunId' {
            # Real GitHub Actions run IDs are routinely 10-11 digits
            # (> Int32.MaxValue = 2147483647). [int]::TryParse would
            # silently fail to parse them, falling back to workflowRunId=0
            # which would break downstream URL composition. Regression-pin
            # the [long]::TryParse fix.
            $bigRunId = '79980111111'   # 11 digits, just past Int32 max
            $agg = New-Aggregate -PerStimTokens @{
                'sk|st' = @{ Skill = 'sk'; Stimulus = 'st'; InputTokens = 1; OutputTokens = 1; CacheReadTokens = 0; CacheWriteTokens = 0 }
            }
            $dl = @{ RunId = $bigRunId; Jobs = @{}; Artifacts = @{} }
            Export-VallySchemaArtifact -Aggregate $agg -DeepLinks $dl -OutputRoot $script:ScratchRoot -RunId "$bigRunId-1" -Date '2026-06-07' | Out-Null
            $obj = Get-Content (Join-Path $script:ScratchRoot "2026-06-07/$bigRunId-1/sk/deepLinks.json") -Raw | ConvertFrom-Json
            # Comes through as a long; ConvertFrom-Json round-trips it as
            # System.Int64. Should -Be uses value equality so 79980111111
            # matches whether it's [long] or [string] in the round-trip.
            $obj.workflowRunId | Should -Be 79980111111
        }

        It 'synthesizes failing-only stimGraders from FailureRows when StimGraders is empty (no-details / log-fallback path)' {
            # Aggregator's no-details JSONL path and log-fallback path
            # both add to FailureRows but not StimGraders. Without
            # this fallback, those failures render as red rows with
            # an empty disclosure. The emitter must synthesize so
            # the disclosure has content.
            $failureRows = @{
                Rows = @(
                    [pscustomobject]@{ Skill = 'sk'; Stimulus = 'st'; Shard = 'shard0'; Grader = '(eval-aggregate)'; Evidence = 'eval crashed'; RootCause = 'HarnessCrash' }
                )
            }
            # Explicitly empty StimGraders to simulate the no-details branch.
            $agg = New-Aggregate -FailureRows $failureRows -StimGraders @{}
            Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'fb' -Date '2026-06-07' | Out-Null
            $obj = Get-Content (Join-Path $script:ScratchRoot '2026-06-07/fb/sk/deepLinks.json') -Raw | ConvertFrom-Json
            $obj.stimGraders.Count | Should -Be 1
            $obj.stimGraders[0].grader    | Should -Be '(eval-aggregate)'
            $obj.stimGraders[0].passed    | Should -BeFalse
            $obj.stimGraders[0].rootCause | Should -Be 'HarnessCrash'
        }

        It 'emits redacted evidence on each failing stimGraders entry (fix #3)' {
            # Renderer needs per-failure evidence to surface in the
            # disclosure chip. Without this field the dashboard shows
            # only RootCause without any context.
            $evidence = 'expected X but got Y, workspace 11111111-1111-1111-1111-111111111111 failed'
            $agg = New-Aggregate -FailureRows @{
                Rows = @(
                    [pscustomobject]@{ Skill = 'sk'; Stimulus = 'st'; Shard = 'shard1'; Grader = 'verify'; Evidence = $evidence; RootCause = 'ContentMismatch' }
                )
            }
            Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r' -Date '2026-06-07' | Out-Null
            $obj = Get-Content (Join-Path $script:ScratchRoot '2026-06-07/r/sk/deepLinks.json') -Raw | ConvertFrom-Json
            $obj.stimGraders[0].evidence | Should -Match '\[REDACTED\]'
            $obj.stimGraders[0].evidence | Should -Match 'got Y'
            $obj.stimGraders[0].passed   | Should -BeFalse
        }

        It 'emits passing graders without rootCause/evidence (compact shape)' {
            # Passing graders surface in stimGraders so the dashboard can
            # show "N of M passed" denominators, but they don't carry
            # rootCause/evidence (those are meaningless for passes; omitting
            # keeps the on-disk payload small and the renderer's
            # pass-vs-fail switch unambiguous).
            $stimGraders = @{
                'sk|st' = @(
                    [pscustomobject]@{ Skill = 'sk'; Stimulus = 'st'; Shard = 'shard0'; Grader = 'wall-time'; Passed = $false; RootCause = 'WallTimeBudget'; Evidence = 'timeout' },
                    [pscustomobject]@{ Skill = 'sk'; Stimulus = 'st'; Shard = 'shard0'; Grader = 'tool-routing'; Passed = $true; RootCause = ''; Evidence = '' }
                )
            }
            $failureRows = @{
                Rows = @(
                    [pscustomobject]@{ Skill = 'sk'; Stimulus = 'st'; Shard = 'shard0'; Grader = 'wall-time'; Evidence = 'timeout'; RootCause = 'WallTimeBudget' }
                )
            }
            $agg = New-Aggregate -FailureRows $failureRows -StimGraders $stimGraders
            Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r' -Date '2026-06-07' | Out-Null
            $obj = Get-Content (Join-Path $script:ScratchRoot '2026-06-07/r/sk/deepLinks.json') -Raw | ConvertFrom-Json
            $obj.stimGraders.Count | Should -Be 2
            $failing = @($obj.stimGraders | Where-Object { -not $_.passed })
            $passing = @($obj.stimGraders | Where-Object { $_.passed })
            $failing.Count | Should -Be 1
            $passing.Count | Should -Be 1
            $failing[0].rootCause | Should -Be 'WallTimeBudget'
            $failing[0].evidence  | Should -Be 'timeout'
            # Passing entry has NO rootCause / evidence properties.
            ($passing[0].PSObject.Properties.Name -contains 'rootCause') | Should -BeFalse
            ($passing[0].PSObject.Properties.Name -contains 'evidence')  | Should -BeFalse
        }
    }

    Context 'Evidence redaction' {
        It 'does NOT introduce recursion when called many times in one export (regression: run 27214839689 call-depth overflow)' {
            # Reproduces the call-depth overflow that hit fabric-smoke-vally
            # on commit d891b41: a `function script:Get-RedactedEvidence`
            # wrapper that called bare `Get-RedactedEvidence` shadowed the
            # dot-sourced global, recursing into itself. Pester's BeforeAll
            # scoping happened to mask it locally; the workflow's shell-task
            # dot-source surfaced it as "The script failed due to call depth
            # overflow." If anyone reintroduces a script:-prefixed wrapper
            # in Export-VallySchemaArtifact.ps1, this test will overflow
            # before the assertion fires.
            $rows = 1..50 | ForEach-Object {
                [pscustomobject]@{
                    Skill     = "s$_"
                    Stimulus  = "st$_"
                    Shard     = 'shard0'
                    Grader    = 'g'
                    Evidence  = "workspaceId=12345678-aaaa-bbbb-cccc-1234567890ab Bearer abc.def tenant=72f988bf-86f1-41af-91ab-2d7cd011db47"
                    RootCause = 'AuthOrSetup'
                }
            }
            $agg = New-Aggregate -FailureRows @{ Rows = $rows }
            { Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r' -Date '2026-06-10' | Out-Null } | Should -Not -Throw
        }

        It 'strips GUIDs, bearer tokens, and tenant= query strings from Evidence' {
            $evidence = 'Failed call to https://api.fabric.microsoft.com/v1/workspaces/12345678-aaaa-bbbb-cccc-1234567890ab?tenant=72f988bf-86f1-41af-91ab-2d7cd011db47 with Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.abc.def'
            $agg = New-Aggregate -FailureRows @{
                Rows = @(
                    [pscustomobject]@{ Skill = 's'; Stimulus = 'st'; Shard = 'shard0'; Grader = 'g'; Evidence = $evidence; RootCause = 'AuthOrSetup' }
                )
            }
            Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r' -Date '2026-06-07' | Out-Null
            $tr = Get-Content (Join-Path $script:ScratchRoot '2026-06-07/r/s/testResults.json') -Raw | ConvertFrom-Json
            $msg = [string]$tr.'st'.message
            # All three patterns removed.
            $msg | Should -Not -Match '12345678-aaaa-bbbb-cccc-1234567890ab'
            $msg | Should -Not -Match '72f988bf-86f1-41af-91ab-2d7cd011db47'
            $msg | Should -Not -Match 'eyJ0eXAi'
            $msg | Should -Match '\[REDACTED\]'
            $msg | Should -Match 'tenant=\[REDACTED\]'
        }

        It 'caps Evidence at 500 characters with a single ellipsis' {
            $long = 'X' * 800
            $agg = New-Aggregate -FailureRows @{
                Rows = @(
                    [pscustomobject]@{ Skill = 's'; Stimulus = 'st'; Shard = 'shard0'; Grader = 'g'; Evidence = $long; RootCause = 'Other' }
                )
            }
            Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r' -Date '2026-06-07' | Out-Null
            # SKILL-REPORT carries the redacted evidence (truncated to 500).
            $report = Get-Content (Join-Path $script:ScratchRoot '2026-06-07/r/s/SKILL-REPORT.md') -Raw
            # Find a line of XXXX. The "X"-prefix-then-ellipsis cap is 500 chars.
            ($report -match 'X{499}\u2026') | Should -BeTrue
        }
    }

    Context 'UTF-8 no-BOM and LF newlines' {
        It 'writes UTF-8 no-BOM for all emitted files' {
            $agg = New-Aggregate -PerStimTokens @{ 'sk|st' = @{ Skill = 'sk'; Stimulus = 'st'; InputTokens = 1; OutputTokens = 1; CacheReadTokens = 0; CacheWriteTokens = 0 } }
            Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r' -Date '2026-06-07' | Out-Null
            $files = 'testResults.json','token-summary.jsonl','SKILL-REPORT.md','deepLinks.json'
            foreach ($f in $files) {
                $bytes = [System.IO.File]::ReadAllBytes((Join-Path $script:ScratchRoot "2026-06-07/r/sk/$f"))
                if ($bytes.Length -ge 3) {
                    # UTF-8 BOM is EF BB BF. Must NOT appear.
                    ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) | Should -BeFalse -Because "$f must not start with a UTF-8 BOM"
                }
            }
        }
    }

    Context 'path traversal sanitization (Get-SafePathSegment, fix #7)' {
        It 'rejects ".." dot-segment so the file lands UNDER runDir (no escape)' {
            # Without the dot-segment guard a malicious / malformed
            # upstream stim name of ".." would have the join resolve
            # to $runDir/../testResults.json -- a sibling of $runDir,
            # not under it. Replacement is "_dotdot" (NOT "_..") because
            # Windows file APIs strip trailing dots from filenames.
            $agg = New-Aggregate -PerEval @{ '..' = @{ Total = 0; Passed = 0; Failed = 0 } }
            Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r' -Date '2026-06-07' | Out-Null
            $runDir  = Join-Path $script:ScratchRoot '2026-06-07/r'
            (Test-Path (Join-Path $runDir '_dotdot/testResults.json')) | Should -BeTrue
            # And the escaped path must NOT exist.
            (Test-Path (Join-Path $script:ScratchRoot '2026-06-07/testResults.json')) | Should -BeFalse
        }
        It 'rejects "." dot-segment' {
            $agg = New-Aggregate -PerEval @{ '.' = @{ Total = 0; Passed = 0; Failed = 0 } }
            Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r' -Date '2026-06-07' | Out-Null
            (Test-Path (Join-Path $script:ScratchRoot '2026-06-07/r/_dot/testResults.json')) | Should -BeTrue
        }
        It 'falls back to "unknown" for an empty/whitespace skill segment' {
            # PerEval keys cannot be all-whitespace under Pester's hashtable
            # literal evaluation; use a FailureRows fixture with an empty
            # Skill string to exercise the same branch.
            $agg = New-Aggregate -FailureRows @{
                Rows = @(
                    [pscustomobject]@{ Skill = ' '; Stimulus = 'st'; Shard = 'shard0'; Grader = 'g'; Evidence = ''; RootCause = 'Other' }
                )
            }
            # Empty/whitespace Skill rows are filtered out by the emitter
            # (see the '[string]::IsNullOrWhiteSpace($skill)' guard in the
            # FailureRows loop), so test Get-SafePathSegment directly with
            # an in-script call instead of going through the full path.
            $seg = script:Get-SafePathSegment ' '
            $seg | Should -Be 'unknown'
        }
    }

    Context 'PerStimStatus seeds the stim universe even without tokenUsage (fix #8)' {
        It 'emits a passing stim row when the aggregate carries PerStimStatus but no PerStimTokens' {
            # Mirrors a real shard where a trial passed but trajectory.metrics.tokenUsage
            # was absent -- previously the stim was invisible because the emitter
            # seeded the stim universe from PerStimTokens.
            $agg = New-Aggregate -PerEval @{ 'sk' = @{ Total = 1; Passed = 1; Failed = 0 } }
            $agg.PerStimStatus = @{
                'sk|silent-pass' = @{ Skill = 'sk'; Stimulus = 'silent-pass'; Passed = $true; HasAnyTrial = $true }
            }
            Export-VallySchemaArtifact -Aggregate $agg -OutputRoot $script:ScratchRoot -RunId 'r' -Date '2026-06-07' | Out-Null
            $tr = Get-Content (Join-Path $script:ScratchRoot '2026-06-07/r/sk/testResults.json') -Raw | ConvertFrom-Json
            $tr.'silent-pass'.isPass | Should -BeTrue
            $tr.'silent-pass'.rawStatus | Should -Be 'Y'
        }
    }
}
