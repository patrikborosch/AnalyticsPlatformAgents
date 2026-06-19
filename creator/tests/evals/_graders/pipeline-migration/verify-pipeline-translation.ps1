[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$modulePath = Join-Path $PSScriptRoot '..' | Join-Path -ChildPath '_lib' | Join-Path -ChildPath 'Vally.Grader.psm1'
Import-Module $modulePath -Force

# ---------------------------------------------------------------------------
# Offline output verifier for the pipeline-migration eval.
#
# pipeline-migration is a guidance/offline skill: both stimuli explicitly
# forbid live API calls, so there is NO Fabric-side artefact to inspect. The
# only deterministic artefact an offline run produces is the agent's emitted
# answer (the converted Fabric JSON + the migration narrative). This Layer 2
# verifier reads that answer from the captured trajectory and deterministically
# re-checks the canonical Synapse -> Fabric Data Factory translation invariants.
#
# It is the AUTHORITATIVE correctness signal and is strictly more robust than
# the cheap Layer 0 `output-contains` / `output-not-matches` string graders,
# because:
#
#   * It scopes the "deprecated `pipeline().globalParameters.` must not survive"
#     check to the EMITTED FABRIC artefact (a fenced block that contains
#     `TridentNotebook`). A flat `output-not-matches` regex false-fails the run
#     when the model legitimately ECHOES the source Synapse JSON or shows a
#     before/after ("`@pipeline().globalParameters.env` becomes
#     `@pipeline().libraryVariables.env`") -- both of which mention the
#     deprecated form without it surviving the rewrite. This false-fail is the
#     exact brittleness that made graders flip red on otherwise-correct runs.
#
#   * It tolerates JSON formatting variance (the `libraryVariables` rewrite is
#     accepted in both expression form `@pipeline().libraryVariables.env_name`
#     and block form `"libraryVariables": { "env_name": ... }`).
#
# Stim coupling: the two stimuli verify different invariant sets, so the
# verifier branches on the stimulus name (mirrors the eventhouse pilot, which
# hard-codes its single stimulus' expectations). Discrimination is on a stable
# substring, not the full name, so a cosmetic rename does not silently skip
# checks; an unrecognised name falls back to the invariants both stims share.
#
# Contract (see tests/evals/_graders/README.md): read-only, never-swallow-to-
# pass (the top-level catch emits passed:$false), one line of GraderResult JSON
# via Write-GraderResult. No live Fabric calls, so no workspace id / token.
# ---------------------------------------------------------------------------

$graderName = 'verify-pipeline-translation'

# Canonical substitutions asserted by the stim-2 prompt.
$expectedNotebookGuid = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
$expectedConnectionName = 'My ADLS Connection'

# Strict-mode-safe property reader. ConvertFrom-Json yields [PSCustomObject];
# dotted access on an absent property throws under Set-StrictMode -Version
# Latest. Hashtables are used by the self-test / unit harness.
function Get-Prop {
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

# Concatenate every assistant_message content string from the trajectory.
# The trajectory event shape (events[].type / events[].data.content) is the
# same one Vally writes to results.jsonl and that tests/vally-ci/
# Render-VallyTranscripts.ps1 parses -- the grader input carries the identical
# trajectory object.
function Get-AssistantOutput {
    param([object]$GraderInput)
    $traj = Get-Prop $GraderInput 'trajectory'
    $events = Get-Prop $traj 'events'
    if (-not $events) { $events = Get-Prop $GraderInput 'events' }  # defensive fallback
    $sb = New-Object System.Text.StringBuilder
    foreach ($e in @($events)) {
        if (-not $e) { continue }
        if ((Get-Prop $e 'type') -ne 'assistant_message') { continue }
        $content = Get-Prop (Get-Prop $e 'data') 'content'
        if (-not [string]::IsNullOrWhiteSpace([string]$content)) {
            [void]$sb.AppendLine([string]$content)
        }
    }
    return $sb.ToString()
}

# Return the inner text of every fenced (``` ... ```) code block in the answer.
function Get-FencedBlocks {
    param([string]$Text)
    $blocks = New-Object System.Collections.Generic.List[string]
    if ([string]::IsNullOrEmpty($Text)) { return $blocks.ToArray() }
    # ``` <optional language> <whitespace-or-newline> <body> ``` ; non-greedy
    # body, DOTALL. The separator after the language tag is \s* (matches \n,
    # \r, spaces, tabs) so both the canonical multi-line form
    #   ```json
    #   {...}
    #   ```
    # and the single-line form
    #   ```json {...} ```
    # (which assistants occasionally emit) are captured. The language tag is
    # restricted to identifier chars so `{` cannot accidentally be consumed
    # as part of the language slot in the no-whitespace single-line form
    #   ```json{...}```.
    $pattern = '(?s)```(?:[a-zA-Z0-9_+-]*)\s*(.*?)```'
    foreach ($m in [regex]::Matches($Text, $pattern)) {
        $blocks.Add($m.Groups[1].Value) | Out-Null
    }
    return $blocks.ToArray()
}

$passed = $false
$score = 0.0
$evidence = ''
$metadata = [ordered]@{}

try {
    $graderInput = Read-EvaluateGraderInput
    $stimName = [string](Get-Prop (Get-Prop (Get-Prop $graderInput 'trajectory') 'stimulus') 'name')
    $metadata.stimulus = $stimName

    $output = Get-AssistantOutput -GraderInput $graderInput
    if ([string]::IsNullOrWhiteSpace($output)) {
        $evidence = "No assistant output was found in the trajectory; cannot verify the translation invariants. The agent produced no answer text (a no-load or crashed run)."
        Write-GraderResult -Name $graderName -Passed $false -Score 0 -Evidence $evidence -Metadata $metadata
        return
    }

    # @() guards against PowerShell unrolling an empty array return to $null
    # (which would make the .Count read throw under Set-StrictMode).
    $blocks = @(Get-FencedBlocks -Text $output)
    $metadata.fencedBlockCount = $blocks.Count

    $failures = New-Object System.Collections.Generic.List[string]

    # ---- Invariants shared by BOTH stimuli ----
    # SynapseNotebook activity is renamed to the Fabric type (case-sensitive
    # type-name literal).
    if ($output -cnotmatch 'TridentNotebook') {
        $failures.Add("the converted notebook activity type 'TridentNotebook' is absent (SynapseNotebook was not renamed)") | Out-Null
    }
    # The globalParameters -> libraryVariables rewrite is named.
    if ($output -notmatch '(?i)libraryVariables') {
        $failures.Add("'libraryVariables' (the Variable Library rewrite of globalParameters) is absent") | Out-Null
    }

    # Discriminate the stimulus by NAME ONLY. Stim 2 ('Offline JSON
    # translate ...') ships inline source JSON + substitutions; stim 1
    # ('Routing positive ...') is a narrative walk-through. An earlier
    # version OR'd in a content check on the expected notebook GUID as a
    # fallback against a cosmetic stim rename, but coupling mode selection
    # to a specific prompt literal misclassifies any future stim that
    # legitimately references the same GUID (or examples that quote it).
    # Name-only discrimination is resilient: an unrecognised name falls
    # back to the shared invariants below instead of silently applying
    # stim-2's stricter checks.
    $isJsonTranslate = ($stimName -match '(?i)JSON\s+translate')

    if ($isJsonTranslate) {
        $metadata.mode = 'json-translate'

        # Substitution: the Fabric notebook GUID replaces the 'PrepNotebook' ref.
        if (-not $output.Contains($expectedNotebookGuid)) {
            $failures.Add("the substituted Fabric notebook GUID '$expectedNotebookGuid' is absent") | Out-Null
        }
        # Substitution: linked service -> connection display name.
        if (-not $output.Contains($expectedConnectionName)) {
            $failures.Add("the substituted Fabric connection display name '$expectedConnectionName' is absent") | Out-Null
        }
        # The env parameter is rewritten onto libraryVariables. Accept the
        # expression form (@pipeline().libraryVariables.env_name) and the block
        # form ("libraryVariables": { "env_name": ... }).
        $dotted = $output -match '(?i)libraryVariables\.env_name'
        $blockForm = $output -match '(?i)libraryVariables[\s\S]{0,80}env_name'
        if (-not ($dotted -or $blockForm)) {
            $failures.Add("the 'env' parameter was not rewritten onto libraryVariables.env_name") | Out-Null
        }

        # FORBID: the deprecated globalParameters expression must not SURVIVE
        # in the emitted Fabric artefact. Scope the check to the converted
        # Fabric pipeline content (identified by a TridentNotebook marker);
        # a pure source echo (SynapseNotebook only, no TridentNotebook) or a
        # before/after prose mention is intentionally ignored -- those
        # legitimately reference the old form.
        #
        # Primary: scan fenced code blocks that contain TridentNotebook.
        # Fallback: when no fenced block contains the marker but
        # TridentNotebook still appears in the raw output (unfenced inline
        # JSON), extract the *JSON object* containing each marker by brace-
        # counting from the marker outward. A JSON-only window is essential
        # here -- an arbitrary character window around the marker can sweep
        # in adjacent prose like "`@pipeline().globalParameters.env` becomes
        # ..." and reintroduce the exact false-fail this verifier exists to
        # eliminate. The brace-counted extraction follows actual JSON
        # structure (balanced { } honoring "..." strings and \-escapes), so
        # explanatory prose around the JSON is excluded by construction.
        $fabricBlocks = @($blocks | Where-Object { $_ -cmatch 'TridentNotebook' })
        if ($fabricBlocks.Count -eq 0 -and ($output -cmatch 'TridentNotebook')) {
            # Precompute an "in-string" mask in a single forward pass. This
            # avoids a direction-sensitive bug: the TridentNotebook marker
            # is itself inside a JSON string literal, so a naive
            # right-to-left toggle starting at inString=false would count
            # quotes the wrong way and misclassify the enclosing structural
            # '{'. The forward pass is canonical: track the JSON string
            # state honoring "..." and \-escapes, then both the left and
            # right walks just consult the mask.
            $len = $output.Length
            $inStr = New-Object bool[] $len
            $cur = $false
            $esc = $false
            for ($i = 0; $i -lt $len; $i++) {
                $c = $output[$i]
                $inStr[$i] = $cur
                if ($esc) { $esc = $false; continue }
                if ($c -eq '\') { $esc = $true; continue }
                if ($c -eq '"') { $cur = -not $cur }
            }

            $jsonObjects = New-Object System.Collections.Generic.List[string]
            $startIdx = 0
            while ($true) {
                $markerIdx = $output.IndexOf('TridentNotebook', $startIdx, [System.StringComparison]::Ordinal)
                if ($markerIdx -lt 0) { break }
                # Walk LEFT from the marker to find the enclosing '{',
                # skipping any '{' that the mask says is inside a string.
                $openIdx = -1
                $depth = 0
                for ($i = $markerIdx - 1; $i -ge 0; $i--) {
                    if ($inStr[$i]) { continue }
                    $ch = $output[$i]
                    if ($ch -eq '}') { $depth++ }
                    elseif ($ch -eq '{') {
                        if ($depth -eq 0) { $openIdx = $i; break }
                        $depth--
                    }
                }
                if ($openIdx -lt 0) {
                    $startIdx = $markerIdx + 'TridentNotebook'.Length
                    continue
                }
                # Walk RIGHT from openIdx to find the matching '}',
                # likewise skipping in-string braces via the mask.
                $closeIdx = -1
                $depth = 0
                for ($i = $openIdx; $i -lt $len; $i++) {
                    if ($inStr[$i]) { continue }
                    $ch = $output[$i]
                    if ($ch -eq '{') { $depth++ }
                    elseif ($ch -eq '}') {
                        $depth--
                        if ($depth -eq 0) { $closeIdx = $i; break }
                    }
                }
                if ($closeIdx -lt 0) {
                    $startIdx = $markerIdx + 'TridentNotebook'.Length
                    continue
                }
                $jsonObjects.Add($output.Substring($openIdx, $closeIdx - $openIdx + 1)) | Out-Null
                $startIdx = $closeIdx + 1
            }
            $fabricBlocks = @($jsonObjects)
            $metadata.fabricBlockSource = 'unfenced-fallback'
        }
        else {
            $metadata.fabricBlockSource = 'fenced'
        }
        $metadata.fabricBlockCount = $fabricBlocks.Count

        # If after both primary and fallback we still have no inspection
        # window, the model never emitted a converted Fabric pipeline at
        # all in JSON-translate mode -- that's a separate failure (no
        # translation was actually performed) so flag it explicitly with
        # actionable evidence instead of silently passing the survival
        # check on an empty set.
        if ($fabricBlocks.Count -eq 0) {
            $failures.Add("no Fabric pipeline content (no 'TridentNotebook' marker in any fenced block or extractable JSON object) found in the output -- the JSON translation was not performed") | Out-Null
        }
        else {
            $survivedIn = @($fabricBlocks | Where-Object { $_ -match '(?i)pipeline\(\)\.globalParameters\.' })
            if ($survivedIn.Count -gt 0) {
                $failures.Add("the deprecated 'pipeline().globalParameters.' expression survived inside the emitted Fabric pipeline JSON (the rewrite to libraryVariables is incomplete)") | Out-Null
            }
        }
    }
    else {
        $metadata.mode = 'routing-narrative'
        # The narrative must cover dataset inlining (the third migration mechanic
        # the prompt asks about). No GUID/connection substitution and no
        # globalParameters forbid here: a guidance answer legitimately shows the
        # deprecated form in a before/after to explain the rewrite.
        if ($output -notmatch '(?i)\binlin(e|ed|ing)\b') {
            $failures.Add("the dataset-inlining migration mechanic is not narrated (no 'inline/inlined/inlining')") | Out-Null
        }
    }

    if ($failures.Count -gt 0) {
        $metadata.failures = @($failures)
        $evidence = "pipeline-migration translation invariants failed ($($failures.Count)): " + ($failures -join '; ') + "."
        Write-GraderResult -Name $graderName -Passed $false -Score 0 -Evidence $evidence -Metadata $metadata
        return
    }

    $passed = $true
    $score = 1.0
    if ($isJsonTranslate) {
        $evidence = "Fabric translation verified: TridentNotebook present; notebook GUID '$expectedNotebookGuid' substituted; connection '$expectedConnectionName' substituted; env rewritten onto libraryVariables; no deprecated globalParameters survived in the emitted Fabric pipeline ($($metadata.fabricBlockCount) Fabric block(s) inspected)."
    }
    else {
        $evidence = "Migration guidance verified: TridentNotebook rename, libraryVariables rewrite, and dataset inlining are all narrated."
    }
    Write-GraderResult -Name $graderName -Passed $passed -Score $score -Evidence $evidence -Metadata $metadata
}
catch {
    $evidence = "Verifier failed: $($_.Exception.Message)"
    Write-GraderResult -Name $graderName -Passed $false -Score 0 -Evidence $evidence -Metadata $metadata
}
