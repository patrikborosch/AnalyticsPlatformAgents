Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Describe 'verify-pipeline-translation (offline output verifier)' {
    BeforeAll {
        $script:Verifier = Join-Path $PSScriptRoot 'verify-pipeline-translation.ps1'
        $script:Stim2 = 'Offline JSON translate -- Synapse pipeline + dataset -> Fabric'
        $script:Stim1 = 'Routing positive -- pipeline migration steps'

        function script:Invoke-Verifier {
            param([string]$StimName, [string]$Content)
            $obj = @{ trajectory = @{ stimulus = @{ name = $StimName }; events = @(
                @{ type = 'user_message'; data = @{ content = 'prompt' } },
                @{ type = 'assistant_message'; data = @{ content = $Content } }
            ) } }
            $env:EVALUATE_GRADER_INPUT = ($obj | ConvertTo-Json -Depth 12 -Compress)
            try {
                $line = (& pwsh -NoProfile -ExecutionPolicy Bypass -File $script:Verifier 2>&1 | Select-Object -Last 1)
                return ($line | ConvertFrom-Json)
            }
            finally {
                Remove-Item Env:\EVALUATE_GRADER_INPUT -ErrorAction SilentlyContinue
            }
        }
    }

    AfterAll {
        Remove-Item Env:\EVALUATE_GRADER_INPUT -ErrorAction SilentlyContinue
    }

    It 'PASSES a correct stim-2 answer even when it echoes source JSON and shows a before/after (the brittle L0 forbid false-fails this)' {
        $content = @'
Original Synapse pipeline (source reference):
```json
{"type":"SynapseNotebook","parameters":{"env":"@pipeline().globalParameters.env_name"}}
```
The `@pipeline().globalParameters.env_name` expression becomes `@pipeline().libraryVariables.env_name`.

Fabric pipeline:
```json
{"type":"TridentNotebook","typeProperties":{"notebookId":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee","parameters":{"env":"@pipeline().libraryVariables.env_name"}}}
```
Dataset uses connection "My ADLS Connection".
'@
        $res = Invoke-Verifier -StimName $script:Stim2 -Content $content
        $res.passed | Should -BeTrue
    }

    It 'FAILS when globalParameters survives inside the emitted Fabric pipeline block (incomplete rewrite)' {
        $content = @'
Fabric pipeline:
```json
{"type":"TridentNotebook","typeProperties":{"notebookId":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee","parameters":{"env":"@pipeline().globalParameters.env_name"}}}
```
connection "My ADLS Connection", libraryVariables.env_name
'@
        $res = Invoke-Verifier -StimName $script:Stim2 -Content $content
        $res.passed | Should -BeFalse
    }

    It 'FAILS when the notebook GUID substitution is missing' {
        $content = @'
Fabric pipeline:
```json
{"type":"TridentNotebook","typeProperties":{"notebookId":"PrepNotebook","parameters":{"env":"@pipeline().libraryVariables.env_name"}}}
```
connection "My ADLS Connection"
'@
        $res = Invoke-Verifier -StimName $script:Stim2 -Content $content
        $res.passed | Should -BeFalse
    }

    It 'FAILS when the connection display-name substitution is missing' {
        $content = @'
Fabric pipeline:
```json
{"type":"TridentNotebook","typeProperties":{"notebookId":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee","parameters":{"env":"@pipeline().libraryVariables.env_name"}}}
```
'@
        $res = Invoke-Verifier -StimName $script:Stim2 -Content $content
        $res.passed | Should -BeFalse
    }

    It 'PASSES a correct stim-1 narrative (TridentNotebook + libraryVariables + inlining)' {
        $content = @'
Migration steps: rename SynapseNotebook activities to TridentNotebook; convert global
parameters to a Variable Library and reference them via libraryVariables; dataset
references are inlined into each activity's typeProperties.
'@
        $res = Invoke-Verifier -StimName $script:Stim1 -Content $content
        $res.passed | Should -BeTrue
    }

    It 'FAILS a stim-1 narrative that omits dataset inlining' {
        $content = @'
Migration steps: rename SynapseNotebook activities to TridentNotebook and convert
global parameters to a Variable Library referenced via libraryVariables.
'@
        $res = Invoke-Verifier -StimName $script:Stim1 -Content $content
        $res.passed | Should -BeFalse
    }

    It 'FAILS (does not crash) when there is no assistant output' {
        $res = Invoke-Verifier -StimName $script:Stim1 -Content ''
        $res.passed | Should -BeFalse
        $res.evidence | Should -BeLike '*No assistant output*'
    }

    # ---- Unfenced-fallback path (verifier.ps1 fabricBlockSource == 'unfenced-fallback') ----
    # The verifier extracts the JSON object enclosing each TridentNotebook
    # marker via brace-counting when no fenced block contains the marker.
    # These tests pin the two failure modes the fallback exists to prevent:
    # (1) false-fail when adjacent prose mentions globalParameters but the
    # JSON itself is clean, (2) false-pass when globalParameters survives
    # inside the unfenced JSON.

    It 'PASSES unfenced inline Fabric JSON when adjacent prose mentions @pipeline().globalParameters.* in a before/after explanation' {
        $content = @'
Here is the converted Fabric pipeline (inline, no code fence):
{"type":"TridentNotebook","typeProperties":{"notebookId":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee","parameters":{"env":"@pipeline().libraryVariables.env_name"}}}
Note the rewrite: `@pipeline().globalParameters.env_name` becomes `@pipeline().libraryVariables.env_name` -- the deprecated expression no longer appears inside the Fabric pipeline JSON above.
Connection: "My ADLS Connection".
'@
        $res = Invoke-Verifier -StimName $script:Stim2 -Content $content
        $res.passed | Should -BeTrue
        $res.metadata.fabricBlockSource | Should -Be 'unfenced-fallback'
    }

    It 'FAILS unfenced inline Fabric JSON when globalParameters survives INSIDE the JSON object itself' {
        $content = @'
Fabric pipeline (inline):
{"type":"TridentNotebook","typeProperties":{"notebookId":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee","parameters":{"env":"@pipeline().globalParameters.env_name"}}}
Connection: "My ADLS Connection". libraryVariables.env_name appears in narrative only.
'@
        $res = Invoke-Verifier -StimName $script:Stim2 -Content $content
        $res.passed | Should -BeFalse
        $res.metadata.fabricBlockSource | Should -Be 'unfenced-fallback'
    }

    It 'FAILS explicitly when no TridentNotebook marker is present anywhere (no translation performed)' {
        $content = @'
I will migrate your Synapse pipeline shortly. The SynapseNotebook activity stays as-is for now.
libraryVariables would replace globalParameters, and "My ADLS Connection" would be used.
'@
        $res = Invoke-Verifier -StimName $script:Stim2 -Content $content
        $res.passed | Should -BeFalse
        $res.evidence | Should -BeLike "*JSON translation was not performed*"
    }

    # ---- Fenced-block extractor: single-line ``` form ----
    # Assistants occasionally emit a fenced block on one line
    # (```json {...} ```) instead of the canonical multi-line form. The
    # extractor must capture both so single-line emission does not
    # silently fall back to the unfenced path and change pass/fail.
    It 'PASSES a correct stim-2 answer when the Fabric JSON is in a SINGLE-LINE fenced code block' {
        $content = @'
Here is the converted Fabric pipeline:
```json {"type":"TridentNotebook","typeProperties":{"notebookId":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee","parameters":{"env":"@pipeline().libraryVariables.env_name"}}} ```
Connection: "My ADLS Connection".
'@
        $res = Invoke-Verifier -StimName $script:Stim2 -Content $content
        $res.passed | Should -BeTrue
        $res.metadata.fabricBlockSource | Should -Be 'fenced'
    }

    # ---- Stimulus discrimination is name-only ----
    # The verifier must select mode strictly on the stimulus name so a
    # future stim that happens to reference the canonical notebook GUID
    # (or an example that quotes it) is not silently treated as
    # stim-2 and held to its stricter substitution invariants. An
    # unrecognised stim name should fall back to the shared invariants
    # only -- NOT trigger the json-translate mode just because the GUID
    # appears in the output.
    It 'Does NOT switch to json-translate mode when an unrecognised stim incidentally contains the canonical GUID' {
        $content = @'
TridentNotebook + libraryVariables walkthrough with dataset inlining. For
illustration only, a notebookId might look like
aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee in an example. This narrative does NOT
include the connection display name substitution because we are not in
JSON-translate mode; we inlined the dataset properties directly.
'@
        $res = Invoke-Verifier -StimName 'Some future routing stim that mentions the example GUID' -Content $content
        # If the verifier wrongly entered json-translate mode it would
        # require the connection display-name substitution and FAIL. The
        # absence of that failure here proves name-only discrimination.
        $res.passed | Should -BeTrue
        $res.metadata.mode | Should -Be 'routing-narrative'
    }
}
