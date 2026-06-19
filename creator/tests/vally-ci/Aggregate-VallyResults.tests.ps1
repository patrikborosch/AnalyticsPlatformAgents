Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Describe 'Aggregate-VallyResults / Get-VallyAggregate' {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot 'Aggregate-VallyResults.ps1'
        . $scriptPath
        $script:ScratchRoot = Join-Path (Split-Path -Parent $PSScriptRoot) '.test-scratch' | Join-Path -ChildPath 'Aggregate-VallyResults'

        # Pester 5 only surfaces functions to It blocks when they are defined in
        # BeforeAll/BeforeEach (or with global: scope). Defining the helper here
        # with `function script:` keeps it visible across every Context/It under
        # this Describe without polluting the global session.
        function script:New-ShardArtifact {
            param(
                [Parameter(Mandatory = $true)][string]$ResultsRoot,
                [Parameter(Mandatory = $true)][int]$ShardIndex,
                [Parameter(Mandatory = $true)][hashtable]$EvalEntries,
                [string]$LogContent = ''
            )
            $shardDir = Join-Path $ResultsRoot ("vally-smoke-results-12345-1-shard{0}" -f $ShardIndex)
            $vallyRoot = Join-Path $shardDir '.vally-results'
            foreach ($evalName in $EvalEntries.Keys) {
                $evalDir = Join-Path $vallyRoot $evalName
                New-Item -ItemType Directory -Path $evalDir -Force | Out-Null
                $entries = $EvalEntries[$evalName]
                $lines = foreach ($e in $entries) { ($e | ConvertTo-Json -Compress -Depth 10) }
                $jsonlPath = Join-Path $evalDir 'results.jsonl'
                [System.IO.File]::WriteAllLines($jsonlPath, $lines, [System.Text.UTF8Encoding]::new($false))
            }
            if ($LogContent) {
                $logPath = Join-Path $vallyRoot 'vally-run.log'
                [System.IO.File]::WriteAllText($logPath, $LogContent, [System.Text.UTF8Encoding]::new($false))
            }
        }
    }

    BeforeEach {
        if (Test-Path $script:ScratchRoot) { Remove-Item -Path $script:ScratchRoot -Recurse -Force }
        New-Item -ItemType Directory -Path $script:ScratchRoot -Force | Out-Null
    }

    AfterAll {
        if (Test-Path $script:ScratchRoot) { Remove-Item -Path $script:ScratchRoot -Recurse -Force }
    }

    Context 'happy path: results.jsonl across multiple shards' {
        It 'aggregates eval-level totals from gradeResult.passed' {
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'sqldw-eval'     = @( @{ gradeResult = @{ passed = $true } }, @{ gradeResult = @{ passed = $false } } )
                'lakehouse-eval' = @( @{ gradeResult = @{ passed = $true } } )
            } -LogContent "Loaded 3 stimul for sqldw-eval`nAll graders passed.`n2 grader(s) failed.`nWall time     12.5s`n"
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 1 -EvalEntries @{
                'warehouse-eval' = @( @{ gradeResult = @{ passed = $true } } )
            } -LogContent "Loaded 1 stimul for warehouse-eval`nAll graders passed.`nWall time     5.0s`n"

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot

            $agg.Total  | Should -Be 4
            $agg.Passed | Should -Be 3
            $agg.Failed | Should -Be 1
            $agg.UsedFallback | Should -BeFalse
            $agg.PerEval['sqldw-eval'].Total  | Should -Be 2
            $agg.PerEval['sqldw-eval'].Passed | Should -Be 1
            $agg.PerEval['sqldw-eval'].Failed | Should -Be 1
            $agg.PerEval['lakehouse-eval'].Passed | Should -Be 1
            $agg.PerEval['warehouse-eval'].Passed | Should -Be 1
        }

        It 'preserves per-eval grouping (does NOT collapse under .vally-results)' {
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'a-eval' = @( @{ gradeResult = @{ passed = $true } } )
                'b-eval' = @( @{ gradeResult = @{ passed = $true } } )
            }
            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $agg.PerEval.Keys.Count | Should -Be 2
            $agg.PerEval.ContainsKey('a-eval') | Should -BeTrue
            $agg.PerEval.ContainsKey('b-eval') | Should -BeTrue
            $agg.PerEval.ContainsKey('.vally-results') | Should -BeFalse
        }

        It 'tallies stim-level pass/fail/timeout from vally-run.log' {
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'sqldw-eval' = @( @{ gradeResult = @{ passed = $true } } )
            } -LogContent @"
Loaded 4 stimul for sqldw-eval
All graders passed.
All graders passed.
2 grader(s) failed.
Error: Error running stim-3: Timeout after 600000ms waiting for session.idle
"@
            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $agg.StimPass  | Should -Be 2
            $agg.StimFail  | Should -Be 2  # one explicit "grader(s) failed" + one timeout
            $agg.StimTotal | Should -Be 4
        }

        It 'sums per-shard wall-time' {
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'a-eval' = @( @{ gradeResult = @{ passed = $true } } )
            } -LogContent "Wall time     10.5s`nWall time     5.5s`n"
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 1 -EvalEntries @{
                'b-eval' = @( @{ gradeResult = @{ passed = $true } } )
            } -LogContent "Wall time     20.0s`n"

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $agg.ShardWall['shard0'] | Should -Be 16.0
            $agg.ShardWall['shard1'] | Should -Be 20.0
        }
    }

    Context 'EBUSY case: results.jsonl missing, fall back to vally-run.log scores' {
        It 'parses eval-level score lines when no results.jsonl is present' {
            $shardDir = Join-Path $script:ScratchRoot 'vally-smoke-results-12345-1-shard0'
            $vallyRoot = Join-Path $shardDir '.vally-results'
            New-Item -ItemType Directory -Path $vallyRoot -Force | Out-Null
            $log = @"
Loaded 2 stimul for sqldw-eval
Loaded 1 stimul for lakehouse-eval
sqldw-eval [run1] score: 100.0% (threshold: 95.0%)
sqldw-eval [run2] score: 80.0% (threshold: 95.0%)
lakehouse-eval [run1] score: 99.0% (threshold: 95.0%)
EBUSY: resource busy or locked
"@
            [System.IO.File]::WriteAllText((Join-Path $vallyRoot 'vally-run.log'), $log, [System.Text.UTF8Encoding]::new($false))

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot

            $agg.UsedFallback | Should -BeTrue
            $agg.Total  | Should -Be 3
            $agg.Passed | Should -Be 2  # sqldw run1 (100>=95) + lakehouse (99>=95)
            $agg.Failed | Should -Be 1  # sqldw run2 (80<95)
            # Fallback strips the "-eval" suffix from CLI output to align with
            # the JSONL-path naming convention (which uses the bare skill tag).
            $agg.PerEval['sqldw'].Failed | Should -Be 1
        }

        It 'counts grader\(s\) failed crash lines as eval-level FAILS in the log fallback' {
            $shardDir = Join-Path $script:ScratchRoot 'vally-smoke-results-12345-1-shard0'
            $vallyRoot = Join-Path $shardDir '.vally-results'
            New-Item -ItemType Directory -Path $vallyRoot -Force | Out-Null
            $log = @"
Loaded 1 stimul for sqldw-eval
sqldw-eval [run1] grader(s) failed
"@
            [System.IO.File]::WriteAllText((Join-Path $vallyRoot 'vally-run.log'), $log, [System.Text.UTF8Encoding]::new($false))

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $agg.UsedFallback | Should -BeTrue
            $agg.Total  | Should -Be 1
            $agg.Failed | Should -Be 1
            $agg.Passed | Should -Be 0
        }
    }

    Context 'format-drift: regex no longer matches' {
        It 'returns Total=0 / Failed=0 without throwing when score lines are absent' {
            $shardDir = Join-Path $script:ScratchRoot 'vally-smoke-results-12345-1-shard0'
            $vallyRoot = Join-Path $shardDir '.vally-results'
            New-Item -ItemType Directory -Path $vallyRoot -Force | Out-Null
            $log = "Vally 0.6 reformatted output with no score: line at all`n"
            [System.IO.File]::WriteAllText((Join-Path $vallyRoot 'vally-run.log'), $log, [System.Text.UTF8Encoding]::new($false))

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $agg.Total | Should -Be 0
            $agg.UsedFallback | Should -BeTrue
            $agg.LoadedLineCount | Should -Be 0
        }

        It 'reports LoadedLineCount when Loaded lines exist but scoring lines do not' {
            $shardDir = Join-Path $script:ScratchRoot 'vally-smoke-results-12345-1-shard0'
            $vallyRoot = Join-Path $shardDir '.vally-results'
            New-Item -ItemType Directory -Path $vallyRoot -Force | Out-Null
            $log = "Loaded 3 stimul for sqldw-eval`nReformatted score that does not match the regex`n"
            [System.IO.File]::WriteAllText((Join-Path $vallyRoot 'vally-run.log'), $log, [System.Text.UTF8Encoding]::new($false))

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $agg.Total | Should -Be 0
            $agg.LoadedLineCount | Should -Be 1  # the "Loaded 3 stimul" line
        }
    }

    Context 'empty results root' {
        It 'returns zeroed aggregate when ResultsRoot does not exist' {
            $missing = Join-Path $script:ScratchRoot 'nope'
            $agg = Get-VallyAggregate -ResultsRoot $missing
            $agg.Total | Should -Be 0
            $agg.PerEval.Count | Should -Be 0
            $agg.UsedFallback | Should -BeFalse
        }
    }

    Context 'vally output WITHOUT [model-name] bracket (observed in CI run 26820621238)' {
        # vally 0.5.0 emits the [model-name] bracket for some invocations and
        # omits it for others on the same version + wrapper invocation. The
        # original lineRx required the bracket and silently parsed zero
        # scores in the log fallback path when vally chose to omit it. Lock
        # the no-bracket form in with explicit fixtures so a future regex
        # tightening can't regress.
        It 'parses fallback log score + crash lines without the [model-name] bracket' {
            # Source files stay ASCII-only (Windows encoding hygiene rule);
            # vally's actual U+2718 / U+2714 icons are injected at runtime.
            $x = [char]0x2718  # heavy ballot X
            $shardDir = Join-Path $script:ScratchRoot 'vally-smoke-results-12345-1-shard0'
            $vallyRoot = Join-Path $shardDir '.vally-results'
            New-Item -ItemType Directory -Path $vallyRoot -Force | Out-Null
            $log = @"
Loaded 1 stimul for activator-authoring-cli-integration-eval
Loaded 1 stimul for powerbi-authoring-cli-integration-eval
Loaded 1 stimul for spark-consumption-cli-integration-eval
$x activator-authoring-cli-integration-eval  score: 95.0% (threshold: 95.0%)
$x powerbi-authoring-cli-integration-eval  score: 81.8% (threshold: 95.0%)
$x spark-consumption-cli-integration-eval  grader(s) failed
"@
            [System.IO.File]::WriteAllText((Join-Path $vallyRoot 'vally-run.log'), $log, [System.Text.UTF8Encoding]::new($false))

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $agg.UsedFallback | Should -BeTrue
            $agg.Total | Should -Be 3  # 2 scores + 1 crash
            $agg.Passed | Should -Be 1  # activator (95>=95)
            $agg.Failed | Should -Be 2  # powerbi (81.8<95) + spark crash
        }
    }

    Context 'ShardsWithJsonl: mixed-EBUSY divergence signal' {
        It 'reports ShardsWithJsonl == ShardLogCount when every shard finalised JSONL' {
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'sqldw-eval' = @( @{ gradeResult = @{ passed = $true } } )
            } -LogContent "Loaded 1 stimul`nAll graders passed.`n"
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 1 -EvalEntries @{
                'lakehouse-eval' = @( @{ gradeResult = @{ passed = $true } } )
            } -LogContent "Loaded 1 stimul`nAll graders passed.`n"

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot

            $agg.ShardLogCount   | Should -Be 2
            $agg.ShardsWithJsonl | Should -Be 2
        }

        It 'correctly counts ShardsWithJsonl when ResultsRoot has mixed slashes (Windows runner $env:RUNNER_TEMP/all-shards)' {
            # Regression: $env:RUNNER_TEMP on Windows is a forward-slash
            # mixed path (D:\a\_temp/all-shards), but $f.Directory.Parent.FullName
            # returns canonical Windows form (D:\a\_temp\all-shards). The
            # original implementation did a literal `-ne` comparison which
            # never matched, the while loop walked to root, and every
            # shard collapsed to ShardsWithJsonl=1 even when 5 shards
            # finalised JSONL.
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'sqldw-eval' = @( @{ gradeResult = @{ passed = $true } } )
            } -LogContent "Loaded 1 stimul`nAll graders passed.`n"
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 1 -EvalEntries @{
                'lakehouse-eval' = @( @{ gradeResult = @{ passed = $true } } )
            } -LogContent "Loaded 1 stimul`nAll graders passed.`n"

            # Pass ResultsRoot with mixed separators to simulate Windows runner.
            $mixedRoot = $script:ScratchRoot -replace '\\', '/'
            $agg = Get-VallyAggregate -ResultsRoot $mixedRoot

            $agg.ShardsWithJsonl | Should -Be 2
        }

        It 'reports ShardsWithJsonl < ShardLogCount in the mixed-EBUSY scenario (the warning trigger)' {
            # Shard 0 finalised JSONL; shard 1 hit EBUSY and only has vally-run.log.
            # The summarise step emits a ::warning:: when ShardsWithJsonl < ShardLogCount
            # so operators notice shard 1's failures are not in the merge gate.
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'sqldw-eval' = @( @{ gradeResult = @{ passed = $true } } )
            } -LogContent "Loaded 1 stimul`nAll graders passed.`n"

            # Shard 1: just a log file, no JSONL.
            $shard1Dir = Join-Path $script:ScratchRoot 'vally-smoke-results-12345-1-shard1'
            $shard1Vally = Join-Path $shard1Dir '.vally-results'
            New-Item -ItemType Directory -Path $shard1Vally -Force | Out-Null
            [System.IO.File]::WriteAllText(
                (Join-Path $shard1Vally 'vally-run.log'),
                "Loaded 1 stimul`n2 grader(s) failed.`n",
                [System.Text.UTF8Encoding]::new($false))

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot

            $agg.ShardLogCount   | Should -Be 2
            $agg.ShardsWithJsonl | Should -Be 1
            # Global Total > 0 so harness-wide fallback stays dormant (correct).
            $agg.UsedFallback | Should -BeFalse
        }

        It 'does NOT count a shard whose JSONL exists but contains zero gradeResult entries' {
            # Shard 1's results.jsonl was created but truncated before any
            # gradeResult line landed. Should NOT count as "JSONL contributed".
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'sqldw-eval' = @( @{ gradeResult = @{ passed = $true } } )
            } -LogContent "Loaded 1 stimul`n"

            $shard1Dir = Join-Path $script:ScratchRoot 'vally-smoke-results-12345-1-shard1'
            $emptyEvalDir = Join-Path $shard1Dir '.vally-results' | Join-Path -ChildPath 'lakehouse-eval'
            New-Item -ItemType Directory -Path $emptyEvalDir -Force | Out-Null
            [System.IO.File]::WriteAllText(
                (Join-Path $emptyEvalDir 'results.jsonl'),
                "",
                [System.Text.UTF8Encoding]::new($false))
            [System.IO.File]::WriteAllText(
                (Join-Path $shard1Dir '.vally-results' | Join-Path -ChildPath 'vally-run.log'),
                "Loaded 1 stimul`n",
                [System.Text.UTF8Encoding]::new($false))

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $agg.ShardsWithJsonl | Should -Be 1
        }
    }

    Context 'FailureRows + GatingStim* (merge-gate signal)' {
        It 'populates FailureRows from gradeResult.details with per-grader rows' {
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'eventhouse-authoring-cli' = @(
                    @{
                        trajectory = @{ stimulus = @{ name = 'Create idempotent KQL table'; tags = @{ skill = 'eventhouse-authoring-cli' } } }
                        gradeResult = @{
                            passed   = $false
                            name     = 'aggregate'
                            evidence = 'aggregate failed'
                            details  = @(
                                @{ name = 'tool-calls'; passed = $true;  evidence = '3/3 matched' },
                                @{ name = 'verify-iot-sensor-readings-table'; passed = $false; evidence = 'Table IoTSensorReadings missing column Timestamp' }
                            )
                        }
                    }
                )
            }

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot

            $agg.FailureRows.Count | Should -Be 1
            $row = $agg.FailureRows[0]
            $row.Skill    | Should -Be 'eventhouse-authoring-cli'
            $row.Stimulus | Should -Be 'Create idempotent KQL table'
            $row.Shard    | Should -Be 'shard0'
            $row.Grader   | Should -Be 'verify-iot-sensor-readings-table'
            $row.Evidence | Should -Match 'IoTSensorReadings missing column Timestamp'
            # RootCause: grader name 'verify-...' matches ContentMismatch.
            $row.RootCause | Should -Be 'ContentMismatch'

            # Per-stim gating: one stim, one failure => gate fires.
            $agg.GatingStimTotal  | Should -Be 1
            $agg.GatingStimFailed | Should -Be 1
        }

        It 'collapses runs>1 into ONE GatingStim row when any trial fails' {
            # Same stim, 3 trials. Only trial 2 fails. GatingStimTotal should
            # be 1 (one distinct stim), GatingStimFailed 1 (the stim has at
            # least one failing trial).
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'sqldw-consumption-cli' = @(
                    @{ trajectory = @{ stimulus = @{ name = 'List tables'; tags = @{ skill = 'sqldw-consumption-cli' } } }; gradeResult = @{ passed = $true; details = @(@{ name = 'g'; passed = $true; evidence = 'ok' }) } },
                    @{ trajectory = @{ stimulus = @{ name = 'List tables'; tags = @{ skill = 'sqldw-consumption-cli' } } }; gradeResult = @{ passed = $false; details = @(@{ name = 'g'; passed = $false; evidence = 'flake' }) } },
                    @{ trajectory = @{ stimulus = @{ name = 'List tables'; tags = @{ skill = 'sqldw-consumption-cli' } } }; gradeResult = @{ passed = $true; details = @(@{ name = 'g'; passed = $true; evidence = 'ok' }) } }
                )
            }

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot

            $agg.Total            | Should -Be 3   # three trials
            $agg.GatingStimTotal  | Should -Be 1   # one distinct stim
            $agg.GatingStimFailed | Should -Be 1   # stim failed at least once
        }

        It 'falls back to top-level gr.passed when gradeResult.details is absent' {
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'old-eval' = @(
                    @{
                        trajectory = @{ stimulus = @{ name = 'no-details'; tags = @{ skill = 'old-eval' } } }
                        gradeResult = @{ passed = $false; name = 'legacy'; evidence = 'fallback evidence' }
                    }
                )
            }

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot

            $agg.FailureRows.Count | Should -Be 1
            $agg.FailureRows[0].Grader    | Should -Be 'legacy'
            $agg.FailureRows[0].Evidence  | Should -Be 'fallback evidence'
            # Unknown grader name + opaque evidence => defaults to Other.
            $agg.FailureRows[0].RootCause | Should -Be 'Other'
            $agg.GatingStimFailed         | Should -Be 1
        }

        It 'populates FailureRows from log-fallback eval-aggregate + crash lines' {
            # No JSONL anywhere -> fallback runs. Both score-below-threshold
            # and crash lines should produce FailureRows so summarise can
            # surface them in the Grader failures table.
            $shardDir = Join-Path $script:ScratchRoot 'vally-smoke-results-12345-1-shard2'
            $vallyRoot = Join-Path $shardDir '.vally-results'
            New-Item -ItemType Directory -Path $vallyRoot -Force | Out-Null
            $log = @"
Loaded 2 stimul
powerbi-authoring-cli-eval [run1] score: 82.0% (threshold: 95.0%)
spark-authoring-cli-eval [run1] grader(s) failed
"@
            [System.IO.File]::WriteAllText((Join-Path $vallyRoot 'vally-run.log'), $log, [System.Text.UTF8Encoding]::new($false))

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot

            $agg.UsedFallback     | Should -BeTrue
            $agg.FailureRows.Count | Should -Be 2
            $belowThr = $agg.FailureRows | Where-Object { $_.Skill -eq 'powerbi-authoring-cli' }
            $belowThr.Stimulus | Should -Be '(eval-aggregate from log fallback)'
            $belowThr.Shard    | Should -Be 'shard2'
            $belowThr.Grader   | Should -Be 'eval-score-threshold'
            $belowThr.RootCause | Should -Be 'EvalThreshold'
            $crash = $agg.FailureRows | Where-Object { $_.Skill -eq 'spark-authoring-cli' }
            $crash.Grader   | Should -Be 'eval-crash'
            $crash.Shard    | Should -Be 'shard2'
            $crash.RootCause | Should -Be 'HarnessCrash'
            $agg.GatingStimFailed | Should -Be 2
        }
    }

    Context 'RootCause classification covers all 11 taxonomy classes' {
        It 'classifies a representative fixture for each class' {
            # One shard with a stim per class, each failing with a grader name
            # that pins the classifier into the expected class. Asserts the
            # aggregator+classifier wiring produces the full taxonomy.
            $classToGrader = [ordered]@{
                'Routing'         = 'routing-check'
                'WallTimeBudget'  = 'wall-time-budget'
                'TokenBudget'     = 'token-budget'
                'TurnBudget'      = 'turn-count'
                'SessionIdle'     = 'session-idle'
                'AuthOrSetup'     = 'auth-check'
                'ToolError'       = 'tool-error'
                'ContentMismatch' = 'verify-table-shape'
                'Other'           = 'opaque-unknown-grader'
            }
            $evalEntries = @{ 'taxonomy-eval' = @() }
            $i = 0
            foreach ($cls in $classToGrader.Keys) {
                $i++
                $evalEntries['taxonomy-eval'] += @{
                    trajectory = @{ stimulus = @{ name = "stim-$i"; tags = @{ skill = 'taxonomy-eval' } } }
                    gradeResult = @{
                        passed  = $false
                        name    = 'aggregate'
                        details = @(@{ name = $classToGrader[$cls]; passed = $false; evidence = "fixture for $cls" })
                    }
                }
            }
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries $evalEntries

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $byClass = @{}
            foreach ($r in $agg.FailureRows) { $byClass[$r.RootCause] = $true }
            foreach ($cls in $classToGrader.Keys) {
                $byClass.ContainsKey($cls) | Should -BeTrue -Because "RootCause '$cls' should be present in aggregated FailureRows"
            }
        }

        It 'EvalThreshold and HarnessCrash classes are populated via log fallback' {
            # Already covered shape-wise above; this re-asserts both classes
            # fire deterministically under the fallback path (no JSONL).
            $shardDir = Join-Path $script:ScratchRoot 'vally-smoke-results-12345-1-shard0'
            $vallyRoot = Join-Path $shardDir '.vally-results'
            New-Item -ItemType Directory -Path $vallyRoot -Force | Out-Null
            $log = @"
Loaded 2 stimul
foo-eval [run1] score: 50.0% (threshold: 90.0%)
bar-eval [run1] grader(s) failed
"@
            [System.IO.File]::WriteAllText((Join-Path $vallyRoot 'vally-run.log'), $log, [System.Text.UTF8Encoding]::new($false))

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            ($agg.FailureRows | Where-Object { $_.RootCause -eq 'EvalThreshold' }).Count | Should -Be 1
            ($agg.FailureRows | Where-Object { $_.RootCause -eq 'HarnessCrash'  }).Count | Should -Be 1
        }
    }

    Context 'StimGraders (full pass+fail context for dashboard disclosure)' {
        It 'records every grader (passing + failing) per stim, not just the failing ones' {
            # Stim with 5 graders: 3 pass, 2 fail. Dashboard disclosure
            # needs the full set so it can show "2 of 5 graders failed"
            # rather than just "2 graders failed".
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'spark-authoring-cli' = @(
                    @{
                        trajectory = @{ stimulus = @{ name = 'Codegen ADLS mount'; tags = @{ skill = 'spark-authoring-cli' } } }
                        gradeResult = @{
                            stimulusName = 'Codegen ADLS mount'
                            passed = $false
                            details = @(
                                @{ name = 'tool-routing';     passed = $true  },
                                @{ name = 'code-shape-check'; passed = $false; evidence = 'wrong API' },
                                @{ name = 'no-crash';         passed = $true  },
                                @{ name = 'runtime-validate'; passed = $false; evidence = '403 from ADLS' },
                                @{ name = 'expected-output';  passed = $true  }
                            )
                        }
                    }
                )
            }
            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $key = 'spark-authoring-cli|Codegen ADLS mount'
            $graders = @($agg.StimGraders[$key])
            $graders.Count | Should -Be 5
            ($graders | Where-Object { $_.Passed }).Count | Should -Be 3
            ($graders | Where-Object { -not $_.Passed }).Count | Should -Be 2
            # Failing graders carry RootCause + Evidence; passing ones don't.
            ($graders | Where-Object { $_.Grader -eq 'code-shape-check' }).RootCause | Should -Not -BeNullOrEmpty
            ($graders | Where-Object { $_.Grader -eq 'runtime-validate' }).Evidence  | Should -Be '403 from ADLS'
            ($graders | Where-Object { $_.Grader -eq 'tool-routing' }).Passed | Should -BeTrue
        }

        It 'any-fail-wins when the same grader is seen across trials (runs>1)' {
            # Same stim across two trials. wall-time grader passes trial
            # 1 but fails trial 2 -- StimGraders must show Passed=false
            # for that grader (any failure across trials counts as failed,
            # mirroring the merge-gate convention).
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'sk' = @(
                    @{
                        trajectory = @{ stimulus = @{ name = 'st'; tags = @{ skill = 'sk' } } }
                        gradeResult = @{
                            stimulusName = 'st'; passed = $true
                            details = @(
                                @{ name = 'wall-time';   passed = $true  },
                                @{ name = 'tool-routing'; passed = $true }
                            )
                        }
                    },
                    @{
                        trajectory = @{ stimulus = @{ name = 'st'; tags = @{ skill = 'sk' } } }
                        gradeResult = @{
                            stimulusName = 'st'; passed = $false
                            details = @(
                                @{ name = 'wall-time';    passed = $false; evidence = 'exceeded 300s' },
                                @{ name = 'tool-routing'; passed = $true  }
                            )
                        }
                    }
                )
            }
            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $key = 'sk|st'
            $graders = @($agg.StimGraders[$key])
            $graders.Count | Should -Be 2
            $wt = $graders | Where-Object { $_.Grader -eq 'wall-time' }
            $wt.Passed | Should -BeFalse
            $wt.Evidence | Should -Be 'exceeded 300s'
            $tr = $graders | Where-Object { $_.Grader -eq 'tool-routing' }
            $tr.Passed | Should -BeTrue
        }

        It 'gives unnamed graders distinct dedupe keys so multiple empty-name details do not collapse' {
            # Producer may emit a `details` array where some entries
            # are missing the `name` field. Without a stable per-detail
            # fallback the dedupe key collapses them all into one row,
            # silently dropping the extras + their evidence. The fix
            # tags each unnamed detail with its position index in the
            # trial.
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'sk' = @(
                    @{
                        trajectory = @{ stimulus = @{ name = 'st'; tags = @{ skill = 'sk' } } }
                        gradeResult = @{
                            stimulusName = 'st'; passed = $false
                            details = @(
                                @{ name = '';  passed = $false; evidence = 'first unnamed failed'  },
                                @{ name = '';  passed = $false; evidence = 'second unnamed failed' },
                                @{ name = 'g3'; passed = $true }
                            )
                        }
                    }
                )
            }
            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $graders = @($agg.StimGraders['sk|st'])
            # All 3 entries preserved -- no collapse.
            $graders.Count | Should -Be 3
            $unnamed = @($graders | Where-Object { $_.Grader -like '(unnamed*' })
            $unnamed.Count | Should -Be 2
            # Each unnamed entry carries its own evidence (not all
            # collapsed to one).
            ($unnamed | ForEach-Object { $_.Evidence } | Sort-Object) | Should -Be @(
                'first unnamed failed', 'second unnamed failed'
            )
            # FailureRows MUST use the same fallback names, not raw empty
            # strings. Without this fix the dashboard / job summary
            # would show blank grader names and the RootCause classifier
            # could never apply its grader-name precedence rules.
            $fr = @($agg.FailureRows | Where-Object { $_.Stimulus -eq 'st' })
            $fr.Count | Should -Be 2
            $blankNames = @($fr | Where-Object { [string]::IsNullOrWhiteSpace($_.Grader) })
            $blankNames.Count | Should -Be 0
            ($fr | ForEach-Object { $_.Grader } | Sort-Object) | Should -Be @(
                '(unnamed #0)', '(unnamed #1)'
            )
        }
    }

    Context 'PerStimTokens (cache visibility)' {
        It 'sums trajectory.metrics.tokenUsage fields per stim across trials' {
            # Fixture honours the documented semantics:
            #   totalTokens = inputTokens + outputTokens
            #   cacheReadTokens, cacheWriteTokens are SUBSETS of inputTokens
            # (verified against evaluate metrics-collector.ts:74 and real-run
            # results.jsonl in PR #292 verification step).
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'eventhouse-authoring-cli' = @(
                    @{
                        trajectory = @{
                            stimulus = @{ name = 'Create KQL table'; tags = @{ skill = 'eventhouse-authoring-cli' } }
                            metrics  = @{ tokenUsage = @{
                                inputTokens = 25000; outputTokens = 1500; totalTokens = 26500
                                cacheReadTokens = 20000; cacheWriteTokens = 1500; callCount = 5
                            } }
                        }
                        gradeResult = @{ passed = $true; stimulusName = 'Create KQL table' }
                    },
                    @{
                        trajectory = @{
                            stimulus = @{ name = 'Create KQL table'; tags = @{ skill = 'eventhouse-authoring-cli' } }
                            metrics  = @{ tokenUsage = @{
                                inputTokens = 13000; outputTokens =  500; totalTokens = 13500
                                cacheReadTokens = 10000; cacheWriteTokens = 0; callCount = 3
                            } }
                        }
                        gradeResult = @{ passed = $true; stimulusName = 'Create KQL table' }
                    }
                )
            }

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $stimKey = 'eventhouse-authoring-cli|Create KQL table'
            $t = $agg.PerStimTokens[$stimKey]
            $t.Skill            | Should -Be 'eventhouse-authoring-cli'
            $t.Stimulus         | Should -Be 'Create KQL table'
            $t.TrialCount       | Should -Be 2
            $t.CallCount        | Should -Be 8
            $t.InputTokens      | Should -Be 38000  # 25000 + 13000
            $t.OutputTokens     | Should -Be 2000   # 1500 + 500
            $t.TotalTokens      | Should -Be 40000  # 26500 + 13500
            $t.CacheReadTokens  | Should -Be 30000  # 20000 + 10000
            $t.CacheWriteTokens | Should -Be 1500
        }

        It 'keeps different stims under the same skill as separate rows' {
            # spark-authoring-cli has 6 different Codegen prompts in production.
            # Their token costs vary by ~5x; collapsing them under one skill
            # row would hide the per-stim outliers. Regression-pin that.
            # Fixture honours totalTokens = inputTokens + outputTokens.
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'spark-authoring-cli' = @(
                    @{
                        trajectory = @{
                            stimulus = @{ name = 'Codegen Postgres'; tags = @{ skill = 'spark-authoring-cli' } }
                            metrics  = @{ tokenUsage = @{
                                inputTokens = 500000; outputTokens = 2000; totalTokens = 502000
                                cacheReadTokens = 200000; cacheWriteTokens = 0; callCount = 10
                            } }
                        }
                        gradeResult = @{ passed = $false; stimulusName = 'Codegen Postgres' }
                    },
                    @{
                        trajectory = @{
                            stimulus = @{ name = 'Codegen mount ADLS'; tags = @{ skill = 'spark-authoring-cli' } }
                            metrics  = @{ tokenUsage = @{
                                inputTokens = 100000; outputTokens = 1000; totalTokens = 101000
                                cacheReadTokens = 30000; cacheWriteTokens = 0; callCount = 4
                            } }
                        }
                        gradeResult = @{ passed = $true; stimulusName = 'Codegen mount ADLS' }
                    }
                )
            }

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $agg.PerStimTokens.Keys.Count | Should -Be 2
            $heavy = $agg.PerStimTokens['spark-authoring-cli|Codegen Postgres']
            $light = $agg.PerStimTokens['spark-authoring-cli|Codegen mount ADLS']
            $heavy.TotalTokens | Should -Be 502000
            $light.TotalTokens | Should -Be 101000
            # Same skill, different Skill field stays consistent
            $heavy.Skill | Should -Be 'spark-authoring-cli'
            $light.Skill | Should -Be 'spark-authoring-cli'
        }

        It 'tolerates entries that have no tokenUsage block (older trial formats)' {
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'pre-token-eval' = @(
                    @{
                        trajectory = @{ stimulus = @{ name = 'old'; tags = @{ skill = 'pre-token-eval' } } }
                        gradeResult = @{ passed = $true; stimulusName = 'old' }
                    }
                )
            }

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            # Stim should NOT appear in PerStimTokens when no entry had
            # a tokenUsage block to contribute.
            $agg.PerStimTokens.ContainsKey('pre-token-eval|old') | Should -BeFalse
            $agg.PerEval['pre-token-eval'].Total | Should -Be 1
        }
    }

    Context 'PerStimStatus tracks every stim regardless of tokenUsage (fix #8)' {
        It 'records a passing trial even when trajectory.metrics.tokenUsage is absent' {
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'sk-eval' = @(
                    @{
                        trajectory = @{ stimulus = @{ name = 'silent-pass'; tags = @{ skill = 'sk' } } }
                        gradeResult = @{ passed = $true; stimulusName = 'silent-pass' }
                    }
                )
            }
            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $agg.PerStimStatus.ContainsKey('sk|silent-pass') | Should -BeTrue
            $agg.PerStimStatus['sk|silent-pass'].Passed | Should -BeTrue
            $agg.PerStimStatus['sk|silent-pass'].HasAnyTrial | Should -BeTrue
            # And NOT in PerStimTokens because tokenUsage was absent.
            $agg.PerStimTokens.ContainsKey('sk|silent-pass') | Should -BeFalse
        }
        It 'flips Passed=false the first time any trial of a stim fails' {
            New-ShardArtifact -ResultsRoot $script:ScratchRoot -ShardIndex 0 -EvalEntries @{
                'sk-eval' = @(
                    @{
                        trajectory = @{ stimulus = @{ name = 's1'; tags = @{ skill = 'sk' } } }
                        gradeResult = @{ passed = $true; stimulusName = 's1' }
                    }
                    @{
                        trajectory = @{ stimulus = @{ name = 's1'; tags = @{ skill = 'sk' } } }
                        gradeResult = @{ passed = $false; stimulusName = 's1' }
                    }
                )
            }
            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot
            $agg.PerStimStatus['sk|s1'].Passed | Should -BeFalse
        }
    }

    Context 'JSONL parse-error counter (fix #6)' {
        It 'increments JsonlParseErrors and still aggregates the good lines around a bad line' {
            $shardDir = Join-Path $script:ScratchRoot 'vally-smoke-results-12345-1-shard0'
            $vallyRoot = Join-Path $shardDir '.vally-results'
            $evalDir = Join-Path $vallyRoot 'mix-eval'
            New-Item -ItemType Directory -Path $evalDir -Force | Out-Null
            $good1 = (@{ gradeResult = @{ passed = $true } } | ConvertTo-Json -Compress)
            $bad   = 'this is not a json line {{{'
            $good2 = (@{ gradeResult = @{ passed = $false } } | ConvertTo-Json -Compress)
            [System.IO.File]::WriteAllLines((Join-Path $evalDir 'results.jsonl'), @($good1, $bad, $good2), [System.Text.UTF8Encoding]::new($false))

            $agg = Get-VallyAggregate -ResultsRoot $script:ScratchRoot -WarningAction SilentlyContinue
            $agg.JsonlParseErrors | Should -BeGreaterThan 0
            $agg.Total  | Should -Be 2
            $agg.Passed | Should -Be 1
            $agg.Failed | Should -Be 1
        }
    }
}
