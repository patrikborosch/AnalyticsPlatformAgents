Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Describe 'Classify-VallyFailure / Get-VallyRootCause' {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot 'Classify-VallyFailure.ps1'
        . $scriptPath
    }

    Context 'grader-name rules (high confidence)' {
        It 'classifies wall-time-budget grader as WallTimeBudget' {
            $v = Get-VallyRootCause -GraderName 'wall-time-budget' -Evidence 'irrelevant'
            $v.RootCause  | Should -Be 'WallTimeBudget'
            $v.Confidence | Should -Be 'high'
            $v.MatchedRule | Should -Be 'grader:wall-time-budget'
        }

        It 'classifies token-budget grader as TokenBudget' {
            $v = Get-VallyRootCause -GraderName 'token-budget' -Evidence ''
            $v.RootCause | Should -Be 'TokenBudget'
        }

        It 'classifies turn-count grader as TurnBudget' {
            (Get-VallyRootCause -GraderName 'turn-count').RootCause | Should -Be 'TurnBudget'
            (Get-VallyRootCause -GraderName 'turn-budget').RootCause | Should -Be 'TurnBudget'
            (Get-VallyRootCause -GraderName 'max-turns').RootCause   | Should -Be 'TurnBudget'
        }

        It 'classifies session-idle grader as SessionIdle' {
            (Get-VallyRootCause -GraderName 'session-idle').RootCause | Should -Be 'SessionIdle'
            (Get-VallyRootCause -GraderName 'session.idle').RootCause | Should -Be 'SessionIdle'
        }

        It 'classifies tool-calls / routing graders as Routing' {
            (Get-VallyRootCause -GraderName 'tool-calls').RootCause      | Should -Be 'Routing'
            (Get-VallyRootCause -GraderName 'expected-skill').RootCause  | Should -Be 'Routing'
            (Get-VallyRootCause -GraderName 'routing-check').RootCause   | Should -Be 'Routing'
        }

        It 'classifies auth/setup graders as AuthOrSetup' {
            (Get-VallyRootCause -GraderName 'auth-check').RootCause      | Should -Be 'AuthOrSetup'
            (Get-VallyRootCause -GraderName 'workspace-setup').RootCause | Should -Be 'AuthOrSetup'
            (Get-VallyRootCause -GraderName 'provision-fabric').RootCause | Should -Be 'AuthOrSetup'
        }

        It 'classifies tool-error grader as ToolError' {
            (Get-VallyRootCause -GraderName 'tool-error').RootCause       | Should -Be 'ToolError'
            (Get-VallyRootCause -GraderName 'tool-call-error').RootCause  | Should -Be 'ToolError'
        }

        It 'classifies content/verify graders as ContentMismatch' {
            (Get-VallyRootCause -GraderName 'output-matches').RootCause           | Should -Be 'ContentMismatch'
            (Get-VallyRootCause -GraderName 'verify-iot-sensor-table').RootCause  | Should -Be 'ContentMismatch'
            (Get-VallyRootCause -GraderName 'json-match').RootCause               | Should -Be 'ContentMismatch'
        }

        It 'classifies eval-crash as HarnessCrash' {
            (Get-VallyRootCause -GraderName 'eval-crash').RootCause | Should -Be 'HarnessCrash'
        }

        It 'classifies eval-score-threshold as EvalThreshold' {
            (Get-VallyRootCause -GraderName 'eval-score-threshold').RootCause | Should -Be 'EvalThreshold'
        }
    }

    Context 'evidence-regex rules (medium confidence)' {
        It 'classifies session.idle timeout evidence as SessionIdle' {
            $v = Get-VallyRootCause -GraderName 'unknown-grader' -Evidence 'Timeout after 600000ms waiting for session.idle'
            $v.RootCause  | Should -Be 'SessionIdle'
            $v.Confidence | Should -Be 'medium'
            $v.MatchedRule | Should -Be 'evidence:session.idle'
        }

        It 'classifies wall-time-exceeded evidence as WallTimeBudget' {
            (Get-VallyRootCause -GraderName 'x' -Evidence 'Stim exceeded wall-time budget at 95s').RootCause | Should -Be 'WallTimeBudget'
        }

        It 'classifies token budget exceeded evidence as TokenBudget' {
            (Get-VallyRootCause -GraderName 'x' -Evidence 'Token budget exceeded: 100000 of 50000').RootCause | Should -Be 'TokenBudget'
        }

        It 'classifies HTTP 401 evidence as AuthOrSetup' {
            (Get-VallyRootCause -GraderName 'x' -Evidence 'HTTP 401 Unauthorized when calling Fabric API').RootCause | Should -Be 'AuthOrSetup'
            (Get-VallyRootCause -GraderName 'x' -Evidence 'AADSTS50000 invalid token').RootCause | Should -Be 'AuthOrSetup'
        }

        It 'classifies HTTP 5xx evidence as ToolError' {
            (Get-VallyRootCause -GraderName 'x' -Evidence 'HTTP 503 from Fabric Items API').RootCause | Should -Be 'ToolError'
            (Get-VallyRootCause -GraderName 'x' -Evidence 'MCP server error: invalid response').RootCause | Should -Be 'ToolError'
        }

        It 'classifies expected-skill evidence as Routing' {
            (Get-VallyRootCause -GraderName 'x' -Evidence 'Did not invoke expected skill sqldw-consumption-cli').RootCause | Should -Be 'Routing'
        }

        It 'classifies below-threshold evidence as EvalThreshold' {
            (Get-VallyRootCause -GraderName 'x' -Evidence 'Score 82.0% below threshold 95.0%').RootCause | Should -Be 'EvalThreshold'
        }

        It 'classifies "grader(s) failed" evidence as HarnessCrash' {
            (Get-VallyRootCause -GraderName 'x' -Evidence 'Vally reported grader(s) failed for entire eval').RootCause | Should -Be 'HarnessCrash'
        }

        It 'classifies content-mismatch evidence as ContentMismatch' {
            (Get-VallyRootCause -GraderName 'x' -Evidence 'Table IoTSensorReadings missing column Timestamp').RootCause | Should -Be 'ContentMismatch'
            (Get-VallyRootCause -GraderName 'x' -Evidence 'Output does not match expected regex').RootCause | Should -Be 'ContentMismatch'
        }
    }

    Context 'default and precedence' {
        It 'returns Other with low confidence when nothing matches' {
            $v = Get-VallyRootCause -GraderName 'brand-new-grader' -Evidence 'opaque blob with no keywords'
            $v.RootCause   | Should -Be 'Other'
            $v.Confidence  | Should -Be 'low'
            $v.MatchedRule | Should -Be 'default'
        }

        It 'returns Other for null / empty inputs' {
            (Get-VallyRootCause -GraderName $null -Evidence $null).RootCause | Should -Be 'Other'
            (Get-VallyRootCause -GraderName '' -Evidence '').RootCause | Should -Be 'Other'
        }

        It 'grader-name rule wins over evidence-regex rule (precedence)' {
            # Grader = wall-time-budget (high conf) BUT evidence text mentions session.idle.
            # Grader rule must win.
            $v = Get-VallyRootCause -GraderName 'wall-time-budget' -Evidence 'Timeout after 1000ms waiting for session.idle'
            $v.RootCause  | Should -Be 'WallTimeBudget'
            $v.Confidence | Should -Be 'high'
        }

        It 'evidence rule fires when grader is unknown but evidence has keywords' {
            $v = Get-VallyRootCause -GraderName 'unrecognised' -Evidence 'AADSTS50076 multi-factor auth required'
            $v.RootCause  | Should -Be 'AuthOrSetup'
            $v.Confidence | Should -Be 'medium'
        }
    }

    Context 'covers all 11 classes' {
        It 'each class has a deterministic hit path' {
            $classes = 'Routing','WallTimeBudget','TokenBudget','TurnBudget','SessionIdle','AuthOrSetup','ToolError','ContentMismatch','HarnessCrash','EvalThreshold','Other'
            $hits = @{}
            foreach ($c in $classes) { $hits[$c] = $false }
            $hits['Routing']         = (Get-VallyRootCause -GraderName 'tool-calls').RootCause -eq 'Routing'
            $hits['WallTimeBudget']  = (Get-VallyRootCause -GraderName 'wall-time-budget').RootCause -eq 'WallTimeBudget'
            $hits['TokenBudget']     = (Get-VallyRootCause -GraderName 'token-budget').RootCause -eq 'TokenBudget'
            $hits['TurnBudget']      = (Get-VallyRootCause -GraderName 'turn-count').RootCause -eq 'TurnBudget'
            $hits['SessionIdle']     = (Get-VallyRootCause -GraderName 'session-idle').RootCause -eq 'SessionIdle'
            $hits['AuthOrSetup']     = (Get-VallyRootCause -GraderName 'auth-check').RootCause -eq 'AuthOrSetup'
            $hits['ToolError']       = (Get-VallyRootCause -GraderName 'tool-error').RootCause -eq 'ToolError'
            $hits['ContentMismatch'] = (Get-VallyRootCause -GraderName 'verify-foo').RootCause -eq 'ContentMismatch'
            $hits['HarnessCrash']    = (Get-VallyRootCause -GraderName 'eval-crash').RootCause -eq 'HarnessCrash'
            $hits['EvalThreshold']   = (Get-VallyRootCause -GraderName 'eval-score-threshold').RootCause -eq 'EvalThreshold'
            $hits['Other']           = (Get-VallyRootCause -GraderName 'xyz').RootCause -eq 'Other'
            foreach ($c in $classes) {
                $hits[$c] | Should -BeTrue -Because "class '$c' must be reachable"
            }
        }
    }
}
