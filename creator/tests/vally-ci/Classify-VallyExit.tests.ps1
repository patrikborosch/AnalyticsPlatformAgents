Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Describe 'Classify-VallyExit / Get-VallyExitVerdict' {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot 'Classify-VallyExit.ps1'
        . $scriptPath
    }

    Context 'exit 0 fast-path' {
        It 'returns unchanged exit code with no messages when ExitCode is 0' {
            $verdict = Get-VallyExitVerdict -LogText 'irrelevant' -ExitCode 0
            $verdict.Exit | Should -Be 0
            $verdict.Reason | Should -Be ''
            $verdict.Messages.Count | Should -Be 0
        }
    }

    Context 'happy path: EBUSY rescue, all evals cleared threshold' {
        BeforeAll {
            # Fixture: 3 loaded evals, 3 score lines all above threshold, EBUSY
            # marker present. Verdict should swap exit to 0 with Windows-EBUSY reason.
            $script:happyLog = @"
Loaded 12 stimul for sqldw-eval
Loaded 8 stimul for lakehouse-eval
Loaded 4 stimul for warehouse-eval
sqldw-eval [run1] score: 98.5% (threshold: 95.0%)
lakehouse-eval [run1] score: 100.0% (threshold: 95.0%)
warehouse-eval [run1] score: 97.0% (threshold: 95.0%)
EBUSY: resource busy or locked, rmdir 'C:\Users\runneradmin\AppData\Local\Temp\xyz'
"@
        }

        It 'swaps exit to 0' {
            $v = Get-VallyExitVerdict -LogText $script:happyLog -ExitCode 1
            $v.Exit | Should -Be 0
        }

        It 'identifies EBUSY as the reason' {
            $v = Get-VallyExitVerdict -LogText $script:happyLog -ExitCode 1
            $v.EbusyDetected | Should -BeTrue
            $v.Reason | Should -Match 'EBUSY'
        }

        It 'counts loaded / scored / crashes correctly' {
            $v = Get-VallyExitVerdict -LogText $script:happyLog -ExitCode 1
            $v.LoadedCount | Should -Be 3
            $v.ScoredCount | Should -Be 3
            $v.CrashCount  | Should -Be 0
            $v.BelowCount  | Should -Be 0
        }

        It 'emits a ::warning:: annotation in Messages' {
            $v = Get-VallyExitVerdict -LogText $script:happyLog -ExitCode 1
            ($v.Messages -join "`n") | Should -Match '::warning::Vally exited 1'
            ($v.Messages -join "`n") | Should -Match 'Treating as success'
        }
    }

    Context 'sub-grader budget trip without EBUSY (wall-time / session.idle)' {
        It 'attributes the swap to a sub-grader budget trip when no EBUSY' {
            $log = @"
Loaded 5 stimul for sqldw-eval
sqldw-eval [run1] score: 100.0% (threshold: 95.0%)
"@
            $v = Get-VallyExitVerdict -LogText $log -ExitCode 1
            $v.Exit | Should -Be 0
            $v.EbusyDetected | Should -BeFalse
            $v.Reason | Should -Match 'sub-grader budget trip'
        }
    }

    Context 'every loaded eval produced an outcome but some below threshold' {
        It 'still swaps exit to 0 (harness ran clean) and emits ::notice::' {
            $log = @"
Loaded 2 stimul for sqldw-eval
sqldw-eval [run1] score: 99.0% (threshold: 95.0%)
sqldw-eval [run2] score: 80.0% (threshold: 95.0%)
"@
            $v = Get-VallyExitVerdict -LogText $log -ExitCode 1
            $v.Exit | Should -Be 0
            $v.BelowCount | Should -Be 1
            ($v.Messages -join "`n") | Should -Match '::notice::'
            ($v.Messages -join "`n") | Should -Match 'harness success'
        }

        It 'counts grader\(s\) failed lines toward outcomes' {
            $log = @"
Loaded 1 stimul for sqldw-eval
sqldw-eval [run1] grader(s) failed
"@
            $v = Get-VallyExitVerdict -LogText $log -ExitCode 1
            $v.Exit | Should -Be 0
            $v.CrashCount | Should -Be 1
            $v.ScoredCount | Should -Be 0
        }
    }

    Context 'partial outcomes: propagate failure' {
        It 'propagates exit code when fewer outcomes than loaded evals' {
            $log = @"
Loaded 3 stimul for sqldw-eval
Loaded 2 stimul for lakehouse-eval
sqldw-eval [run1] score: 100.0% (threshold: 95.0%)
"@
            $v = Get-VallyExitVerdict -LogText $log -ExitCode 7
            $v.Exit | Should -Be 7
            $v.Reason | Should -Match 'partial outcomes'
            ($v.Messages -join "`n") | Should -Match 'propagating failure'
        }
    }

    Context 'log not captured / no scores parseable' {
        It 'returns original exit with a clear "log not captured" message when log is empty' {
            $v = Get-VallyExitVerdict -LogText '' -ExitCode 9
            $v.Exit | Should -Be 9
            ($v.Messages -join "`n") | Should -Match 'log not captured'
        }

        It 'returns original exit with a clear "log not captured" message when log is null' {
            $v = Get-VallyExitVerdict -LogText $null -ExitCode 9
            $v.Exit | Should -Be 9
            ($v.Messages -join "`n") | Should -Match 'log not captured'
        }

        It 'propagates exit when log has content but zero loaded lines (format drift)' {
            $log = 'random unrelated output with no loaded line'
            $v = Get-VallyExitVerdict -LogText $log -ExitCode 2
            $v.Exit | Should -Be 2
            $v.LoadedCount | Should -Be 0
            ($v.Messages -join "`n") | Should -Match 'no scores parsed'
        }
    }

    Context 'ANSI escape stripping' {
        It 'strips ANSI colour codes before matching' {
            # Embed real ANSI escape (ESC = 0x1B) in the score line.
            $esc = [char]27
            $log = "Loaded 1 stimul for sqldw-eval`n${esc}[32msqldw-eval${esc}[0m [run1] score: 100.0% (threshold: 95.0%)`n"
            $v = Get-VallyExitVerdict -LogText $log -ExitCode 1
            $v.ScoredCount | Should -Be 1
            $v.Exit | Should -Be 0
        }
    }

    Context 'vally output WITHOUT [model-name] bracket (observed in CI run 26820621238)' {
        # vally 0.5.0 emits the [model-name] bracket for some invocations and
        # omits it for others on the same version + wrapper invocation. The
        # original regex required the bracket and silently parsed zero scores
        # when vally chose to omit it; the EBUSY rescue then degraded to
        # "partial outcomes; propagating failure" and failed every shard in
        # workflow_dispatch run 26820621238. Lock the no-bracket form in
        # with explicit fixtures so a future regex tightening can't regress.
        It 'parses score lines without the [model-name] bracket' {
            # Source files stay ASCII-only (Windows encoding hygiene rule);
            # vally's actual U+2718 / U+2714 icons are injected at runtime.
            $x = [char]0x2718  # heavy ballot X
            $v = [char]0x2714  # heavy check mark
            $log = @"
Loaded 1 stimul for activator-authoring-cli-integration-eval
Loaded 1 stimul for document-workspace-agent-integration-eval
Loaded 1 stimul for powerbi-authoring-cli-integration-eval
Loaded 1 stimul for spark-consumption-cli-integration-eval
$x activator-authoring-cli-integration-eval  score: 95.0% (threshold: 95.0%)
$v document-workspace-agent-integration-eval  score: 100.0% (threshold: 95.0%)
$x powerbi-authoring-cli-integration-eval  score: 81.8% (threshold: 95.0%)
$x spark-consumption-cli-integration-eval  grader(s) failed
"@
            $verdict = Get-VallyExitVerdict -LogText $log -ExitCode 1
            $verdict.LoadedCount | Should -Be 4
            $verdict.ScoredCount | Should -Be 3
            $verdict.CrashCount  | Should -Be 1
            $verdict.Exit | Should -Be 0  # harness completed all loaded evals
            # Below = scored stims with score < threshold. activator (95.0)
            # and document-workspace (100.0) are at or above threshold; only
            # powerbi (81.8) is below. spark is a crash, counted separately.
            $verdict.BelowCount | Should -Be 1
        }

        It 'parses score lines with AND without bracket in the same log' {
            $log = @"
Loaded 2 stimul for sqldw-eval
sqldw-eval [claude-sonnet-4.6] score: 99.0% (threshold: 95.0%)
sqldw-eval  score: 100.0% (threshold: 95.0%)
"@
            $verdict = Get-VallyExitVerdict -LogText $log -ExitCode 1
            $verdict.ScoredCount | Should -Be 2
            $verdict.Exit | Should -Be 0
        }
    }
}
