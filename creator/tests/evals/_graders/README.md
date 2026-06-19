# Vally program-grader contract

This is the contract that every verifier under `tests/evals/_graders/<skill>/`
must follow. It is the canonical reference cited from
[`tests/evals/README.md`](../README.md).

## Invocation

A verifier is run as a subprocess by Vally's built-in `program` grader. The
caller (Vally) sets two environment variables and waits for the verifier to
emit a single line of JSON on stdout.

| Env var | What it is | Set by |
|---|---|---|
| `EVALUATE_GRADER_INPUT` | Either an absolute path to a JSON file containing the captured trajectory + stimulus + grader config, OR (for unit tests) an inline JSON STRING starting with `{` or `[`. | Vally |
| `EVALUATE_WORKSPACE` | Absolute path to the agent's working directory (where it may have written files during the run). | Vally |

The verifier may declare additional env vars in its eval.yaml `program.config.env`
block. The shared substitution layer expands `{{WORKSPACE_ID}}` to the GUID of
the ephemeral workspace the smoke shard provisioned.

## Output (the GraderResult envelope)

Emit exactly ONE line of JSON on stdout via `Write-GraderResult` from
`_lib/Vally.Grader.psm1`. Shape:

```jsonc
{
  "schemaVersion": 1,            // stamped by Write-GraderResult; do not set manually
  "name": "verify-<artefact>",   // grader name; appears in the summarise table
  "kind": "code",                // always "code" for program graders
  "passed": false,               // boolean
  "score": 0,                    // 0..1 decimal
  "evidence": "Table X not found after 60s polling in DB Y. Tables present: [...].",
  "metadata": { ... }            // optional structured diagnostic data
}
```

Vally's program-grader plumbing reads the LAST stdout line as the result; do
NOT print anything else to stdout. For in-flight logs, prefer `Write-Warning`
(true stderr / stream 3), or write directly to stderr with
`[Console]::Error.WriteLine(...)`. **Avoid `Write-Host` for logs that must NOT
land in the result payload**: in PowerShell 5+ `Write-Host` writes to the
Information stream (stream 6), which is not stdout by default but CAN merge
into stdout under `*>&1` or other broad redirection, and at that point the
last `Write-Host` line silently becomes the grader's "result" line and
corrupts the run.

`schemaVersion` is added by `Write-GraderResult` and is bumped only on
breaking envelope changes. Workload teams should not set it themselves.

## Rules (hard)

1. **Read-only.** Verifiers list, get, and run KQL `.show` / SQL `SELECT`
   queries. They do NOT create, update, delete, or mutate any Fabric state.
   Mutation belongs in a setup/teardown stimulus or in the agent's own run,
   not in a verifier. This keeps verifier failures debuggable (state is what
   the agent left) and keeps the shared tenant clean.

2. **Never swallow-to-pass.** The top-level `catch` in your verifier MUST
   emit `passed: $false` with the exception message in evidence. A verifier
   that errors FAILS, it never passes. `Write-GraderResult` enforces a minor
   version of this contract: it throws if you try to emit `passed: $true`
   with empty or whitespace-only evidence. That is a sanity check, not a
   security guarantee -- it only catches "I forgot to set evidence", not
   "my evidence text was made up".

3. **Bounded polling for Fabric eventual consistency.** A `.create` followed
   immediately by a `.show` may race. Use `Invoke-WithPolling` with an
   explicit deadline. Ceiling for `Invoke-WithPolling -Deadline` is 3600s
   (1 hour); realistic Fabric eventual-consistency windows are in the
   single-digit seconds.

4. **Exception classification.** `Invoke-WithPolling` bails immediately on
   permanent failures (4xx HTTP, malformed JSON, our own validation throws)
   rather than retrying until the deadline. If you wrap `Invoke-AzRestJson`
   inside the polling block and the call returns 401, you bail in 1 second,
   not 60. The classifier is `Test-PermanentFailure`; extend
   `$script:PermanentFailurePatterns` in `_lib/Vally.Grader.psm1` if your
   verifier has a domain-specific permanent failure.

5. **No bearer tokens on argv.** Call `Invoke-AzRestJson` (or any other `az
   rest` wrapper); `az rest --resource <X>` mints and injects the token
   internally. Do NOT pass `--headers "Authorization=Bearer $token"` --
   that leaks the token to any same-user process via the process command
   line, and it is also redundant.

6. **Sanitised diagnostic dumps.** If you write metadata that goes into
   `results.jsonl` (which is uploaded to a 30-day-retention CI artifact),
   use `Format-DiagnosticGuid` for GUIDs, `Format-DiagnosticUri` for full
   URLs, and `Limit-DiagnosticList` to cap large enumerations. Raw workspace
   IDs and cluster hostnames are tenant-topology data that doesn't belong in
   artifacts that outlive the run.

## Helpers in `_lib/Vally.Grader.psm1`

All exports have comment-based help; `Get-Help <Name> -Full` shows it.

| Function | Purpose |
|---|---|
| `Read-EvaluateGraderInput` | Parses `$env:EVALUATE_GRADER_INPUT` (file path or inline JSON) and returns the trajectory + stimulus + config object. Throws on missing/invalid. Verifiers should call this first. |
| `Get-ResolvedWorkspaceId` | Reads + validates `$env:FABRIC_WORKSPACE_ID`. Fails fast on missing, literal placeholder, or non-GUID. |
| `Get-FabricAccessToken -Resource <X>` | Acquires a raw bearer token via `az account get-access-token`. Use this only when you need a raw token outside `az rest` (e.g. Invoke-WebRequest). For normal `az rest` calls, do NOT call this -- `Invoke-AzRestJson` lets `az rest` handle auth. |
| `Invoke-AzRestJson -Method <get\|post> -Uri <X> [-Body <json>]` | The canonical `az rest` wrapper. Infers the Azure resource from the URI host (Fabric / Kusto / ARM), keeps stdout clean, captures stderr separately so warnings can't corrupt JSON parsing. Returns parsed JSON or `$null` on empty response. |
| `Test-PermanentFailure -ErrorRecord <err>` | Classifies an exception as permanent (do-not-retry) or transient. Used internally by `Invoke-WithPolling`. |
| `Write-GraderResult -Name -Passed -Score -Evidence [-Metadata]` | Emits the GraderResult envelope on stdout. Refuses to emit `passed: $true` with empty evidence. |
| `Invoke-WithPolling -Deadline -Interval -ScriptBlock { ... }` | Bounded retry helper. `$null` from the block means "keep polling"; any other value (including `$false`, `0`, `''`) is returned. Permanent failures inside the block re-throw immediately. |
| `Format-DiagnosticGuid -Guid <X>` | Renders a GUID as a stable short SHA256 prefix (`sha256:a3f1b9c8`) for diagnostic metadata. |
| `Format-DiagnosticUri -Uri <X>` | Renders a URI with the host truncated to 12 chars + ellipsis. |
| `Limit-DiagnosticList -Items <a> -Max <n>` | Caps a list of strings to N items plus a `(and N more)` tag. |

## Worked example shape

```powershell
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$modulePath = Join-Path $PSScriptRoot '..' | Join-Path -ChildPath '_lib' | Join-Path -ChildPath 'Vally.Grader.psm1'
Import-Module $modulePath -Force

$graderName = 'verify-<your-artefact>'
$metadata = [ordered]@{}

try {
    [void](Read-EvaluateGraderInput)
    $workspaceId = Get-ResolvedWorkspaceId
    $metadata.workspaceId = Format-DiagnosticGuid -Guid $workspaceId

    # ... your skill-specific resolve + poll + assert logic ...
    $result = Invoke-WithPolling -Deadline 60 -Interval 2 -ScriptBlock {
        try { return Invoke-AzRestJson -Method get -Uri "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/..." }
        catch { return $null }
    }

    if (-not $result) {
        Write-GraderResult -Name $graderName -Passed $false -Score 0 -Evidence "..." -Metadata $metadata
        return
    }

    Write-GraderResult -Name $graderName -Passed $true -Score 1 -Evidence "..." -Metadata $metadata
} catch {
    Write-GraderResult -Name $graderName -Passed $false -Score 0 -Evidence "Verifier failed: $($_.Exception.Message)" -Metadata $metadata
}
```

The eventhouse pilot at `eventhouse-authoring-cli/verify-iot-sensor-readings-table.ps1`
is the copy-paste template; it exercises every helper above.

## Pester tests

Per-skill verifier scripts are deliberately NOT Pester-tested. Mock-based
unit tests at the Fabric boundary drift from real Fabric and produce false
confidence; the live smoke shard is the authoritative correctness check.

The shared `_lib/Vally.Grader.psm1` IS Pester-tested
(`_lib/Vally.Grader.tests.ps1`, runs via the `grader-unit-tests` CI job)
because its complexity (polling classification, evidence guard, JSON
parsing) is logic-only and reused by every future verifier.
