<#
.SYNOPSIS
Classify a single vally failure (one FailureRows entry) into a stable
machine-readable RootCause class. Sibling to Classify-VallyExit.ps1 -- both
live under tests/vally-ci/ so the workflow can dot-source them after the
checkout step in the summarise job.

.DESCRIPTION
Inputs the per-failure (GraderName, Evidence) pair captured by
Aggregate-VallyResults.ps1 and returns a fixed taxonomy of root-cause
classes. Deterministic precedence so a fixture-pinned grader name wins
over a regex-matched evidence string. Default class is `Other` so a new
grader / new evidence shape NEVER throws -- it just lands in Other and a
follow-up adds the rule.

Taxonomy (11 classes, captured by the planner from PR #292 reviewer
suggestions on failure-bucket triage). Stable IDs -- consumers (renderer,
future Power BI) MUST treat the string as opaque and rely on this list:

  Routing            Agent picked the wrong skill / wrong tool.
  WallTimeBudget     Stim exceeded its wall-time budget grader.
  TokenBudget        Stim exceeded its token-budget grader.
  TurnBudget         Stim exceeded its turn-count budget grader.
  SessionIdle        Stim crashed on a session.idle timeout
                      (vally "Timeout after Nms waiting for session.idle").
  AuthOrSetup        Auth / workspace-setup / Fabric provisioning issue.
  ToolError          Tool invocation raised (4xx/5xx, malformed call,
                      missing parameter).
  ContentMismatch    Grader compared output against expected and content
                      did not match (regex / substring / json compare).
  HarnessCrash       vally itself died (eval-crash, "grader(s) failed"
                      with no underlying numeric score; non-trial-level
                      grader-fail from the log fallback).
  EvalThreshold      Eval-aggregate scored below threshold without an
                      attributable per-grader fail (from log fallback
                      with grader='eval-score-threshold').
  Other              Everything else. Default. NOT an error.

Precedence (first match wins):
  1. Grader-name exact / prefix rules (most specific -- a known grader
     name like `wall-time-budget` is unambiguous).
  2. Grader-name from log-fallback (eval-score-threshold / eval-crash).
  3. Evidence-regex rules (lowest precedence -- evidence varies, so
     names that we recognise should always win).

.PARAMETER GraderName
The grader name from FailureRows[i].Grader. May be empty/null.

.PARAMETER Evidence
The grader evidence string from FailureRows[i].Evidence. May be empty/null.

.OUTPUTS
[hashtable] with keys:
  RootCause    (string)  One of the taxonomy values above. Always set.
  Confidence   (string)  'high' (grader-name match), 'medium' (evidence
                          regex), 'low' (defaulted to Other).
  MatchedRule  (string)  Diagnostic string naming the rule that fired,
                          e.g. 'grader:wall-time-budget',
                          'evidence:session.idle', 'default'. Useful for
                          future Pester regressions on rule drift.
#>
function Get-VallyRootCause {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $false)]
        [AllowNull()]
        [AllowEmptyString()]
        [string]$GraderName,

        [Parameter(Mandatory = $false)]
        [AllowNull()]
        [AllowEmptyString()]
        [string]$Evidence
    )

    $verdict = [ordered]@{
        RootCause   = 'Other'
        Confidence  = 'low'
        MatchedRule = 'default'
    }

    $grader = if ($null -eq $GraderName) { '' } else { ([string]$GraderName).Trim() }
    $evid   = if ($null -eq $Evidence)   { '' } else { ([string]$Evidence).Trim() }
    $graderLc = $grader.ToLowerInvariant()
    $evidLc   = $evid.ToLowerInvariant()

    # ---------------- Pass 1: grader-name rules (highest precedence) ----------------
    # Ordered most-specific first. Each rule is (matcher-script, RootCause,
    # MatchedRule-tag). Matcher is a script-block evaluated against $graderLc.
    $graderRules = @(
        @{ Match = { param($g) $g -match '^(wall[-_ ]?time|walltime|time[-_ ]?budget)' }; Class = 'WallTimeBudget'; Tag = 'grader:wall-time-budget' }
        @{ Match = { param($g) $g -match '^(token[-_ ]?budget|tokens?-?used|max[-_ ]?tokens)' }; Class = 'TokenBudget'; Tag = 'grader:token-budget' }
        @{ Match = { param($g) $g -match '^(turn[-_ ]?count|turn[-_ ]?budget|max[-_ ]?turns)' }; Class = 'TurnBudget'; Tag = 'grader:turn-budget' }
        @{ Match = { param($g) $g -match '^(session[-_ .]?idle|idle[-_ ]?timeout)' }; Class = 'SessionIdle'; Tag = 'grader:session-idle' }
        @{ Match = { param($g) $g -match '^(tool[-_ ]?error|tool[-_ ]?failure|tool[-_ ]?call[-_ ]?(error|failure)|tool[-_ ]?(invocation|invoke)[-_ ]?error)' }; Class = 'ToolError'; Tag = 'grader:tool-error' }
        @{ Match = { param($g) $g -match '^(routing|skill[-_ ]?routing|expected[-_ ]?skill|tool[-_ ]?routing|tool[-_ ]?calls?$|tool[-_ ]?calls?-)' -or $g -eq 'tool-calls' }; Class = 'Routing'; Tag = 'grader:routing' }
        @{ Match = { param($g) $g -match '^(auth|workspace[-_ ]?setup|setup[-_ ]?check|provision|fabric[-_ ]?setup)' }; Class = 'AuthOrSetup'; Tag = 'grader:auth-or-setup' }
        @{ Match = { param($g) $g -match '^(output[-_ ]?matches|content[-_ ]?match|substring[-_ ]?match|regex[-_ ]?match|json[-_ ]?match|verify[-_ ])' }; Class = 'ContentMismatch'; Tag = 'grader:content-mismatch' }
        @{ Match = { param($g) $g -eq 'eval-crash' }; Class = 'HarnessCrash'; Tag = 'grader:eval-crash' }
        @{ Match = { param($g) $g -eq 'eval-score-threshold' }; Class = 'EvalThreshold'; Tag = 'grader:eval-score-threshold' }
    )
    foreach ($r in $graderRules) {
        if ($graderLc -and (& $r.Match $graderLc)) {
            $verdict.RootCause   = $r.Class
            $verdict.Confidence  = 'high'
            $verdict.MatchedRule = $r.Tag
            return [hashtable]$verdict
        }
    }

    # ---------------- Pass 2: evidence-regex rules (medium precedence) ----------------
    # Evidence varies more than grader names so we pattern-match conservatively.
    # First match wins; order intentional.
    $evidenceRules = @(
        @{ Pattern = 'timeout\s+after\s+\d+\s*ms\s+waiting\s+for\s+session\.idle'; Class = 'SessionIdle'; Tag = 'evidence:session.idle' }
        @{ Pattern = '(?:exceeded|over|above).{0,20}(?:wall[- ]?time|time[- ]?budget)|wall[- ]?time.{0,20}exceeded'; Class = 'WallTimeBudget'; Tag = 'evidence:wall-time' }
        @{ Pattern = '(?:exceeded|over|above).{0,20}token[- ]?budget|token[- ]?budget.{0,20}exceeded|max[- ]?tokens?.{0,20}(?:exceeded|reached)'; Class = 'TokenBudget'; Tag = 'evidence:token-budget' }
        @{ Pattern = '(?:exceeded|over|above).{0,20}turn[- ]?(?:count|budget)|turn[- ]?(?:count|budget).{0,20}exceeded|max[- ]?turns?.{0,20}(?:exceeded|reached)'; Class = 'TurnBudget'; Tag = 'evidence:turn-budget' }
        @{ Pattern = 'http\s*4(?:01|03)|unauthori[sz]ed|forbidden|aadsts\d+|invalid[_ -]?(?:client|token|grant)|workspace\s+not\s+found|tenant\s+not\s+found|capacity\s+not\s+assigned'; Class = 'AuthOrSetup'; Tag = 'evidence:auth-or-setup' }
        @{ Pattern = 'http\s*5\d\d|tool\s+invocation\s+(?:failed|error)|invalid\s+(?:argument|parameter)\s+for\s+tool|mcp\s+(?:server|tool)\s+error'; Class = 'ToolError'; Tag = 'evidence:tool-error' }
        @{ Pattern = 'expected\s+(?:skill|tool|call)|did\s+not\s+(?:invoke|call)\s+(?:expected|required)\s+(?:skill|tool)|routed\s+to\s+wrong\s+skill'; Class = 'Routing'; Tag = 'evidence:routing' }
        @{ Pattern = 'score\s+\d+(?:\.\d+)?%\s+below\s+threshold'; Class = 'EvalThreshold'; Tag = 'evidence:eval-threshold' }
        @{ Pattern = 'grader\(s\)\s+failed|vally\s+reported|stim\s+trial\s+crashed'; Class = 'HarnessCrash'; Tag = 'evidence:harness-crash' }
        @{ Pattern = '(?:does\s+not\s+match|did\s+not\s+match|no\s+match\s+for|missing\s+(?:column|table|row|value)|expected\s+.+\s+(?:got|but)\s+)'; Class = 'ContentMismatch'; Tag = 'evidence:content-mismatch' }
    )
    foreach ($r in $evidenceRules) {
        if ($evidLc -and ($evidLc -match $r.Pattern)) {
            $verdict.RootCause   = $r.Class
            $verdict.Confidence  = 'medium'
            $verdict.MatchedRule = $r.Tag
            return [hashtable]$verdict
        }
    }

    return [hashtable]$verdict
}
