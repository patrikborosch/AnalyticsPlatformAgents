---
name: release-public
description: >
  End-to-end public-release workflow for skills-for-fabric: stamp version, open the
  microsoft/skills-for-fabric PR, run the release-artifact smoke (structural + install +
  behavioral Copilot probes), then tag and publish. Captures the exact verification harness
  used for 0.3.2. Use when the user wants to: (1) cut a new public release, (2) smoke-test
  a release branch before merging the public PR, (3) verify a release artifact behaves
  correctly in a clean Copilot CLI install. Triggers: "cut a release", "public release",
  "release smoke", "verify release", "stamp version", "publish to public", "0.x.y release",
  "release workflow", "release runbook".
---

# Release Public — Stamp, Publish, Smoke, Tag

End-to-end workflow for cutting a public release of `microsoft/skills-for-fabric` from the
internal `gim-home/skills-for-fabric` repo. Two scripts do the heavy lifting; this skill
captures the **operator decisions, the smoke harness, and the gotchas** that aren't in the
scripts themselves.

## When to Use

- Cutting a new public release (any `0.x.y` bump)
- Verifying a release branch before merging the public PR
- Confirming a release artifact installs and routes correctly in a clean Copilot CLI

## Prerequisites

| Tool / Setup | Why |
|---|---|
| `git`, `python`, `gh` CLI on PATH | All three scripts require them |
| Clean working tree on internal `main` | `CreateFullRelease.ps1` refuses otherwise |
| `gh auth status` shows a **non-EMU** account with push access to `microsoft/skills-for-fabric` | EMU accounts cannot open PRs against the public repo |
| GitHub Copilot CLI v1.0.46+ installed | Behavioral smoke uses `copilot -p` + session-state telemetry |
| **No Azure auth required** for this workflow | The repo's heavyweight `tests/run-vally-eval.ps1` (and legacy `tests/run-smoke-tests.ps1`) does need Fabric tenant + cert -- that is **not** part of this skill |

To switch accounts for the public PR step (and restore after):

```powershell
gh auth switch -u <non-emu-account>       # before PublishToPublic.ps1
# ... open PR ...
gh auth switch -u <emu-account>           # restore default
```

---

## Workflow Overview

```
Phase 0 — Stamp version on internal main      (CreateFullRelease.ps1 -CommitAndPush)
    |
Phase 1 — Open public PR                       (PublishToPublic.ps1, no flag)
    |
Phase 2 — Release-artifact smoke               (this skill — structural + install + behavioral)
    |
Phase 3 — Merge public PR (human)
    |
Phase 4 — Tag + GitHub Release                 (PublishToPublic.ps1 -PublishRelease)
```

---

## Phase 0 — Stamp Version on Internal Main

`CreateFullRelease.ps1` regenerates the skill catalog, stamps the new version into
`package.json` + every `plugins/*/plugin.json`, regenerates **both** marketplace files via
`build/build_plugins.py`, runs `build_plugins.py --check`, then commits/tags/pushes.

```powershell
cd C:\path\to\skills-for-fabric
.\ReleaseScripts\CreateFullRelease.ps1                  # local stamp only (preview)
.\ReleaseScripts\CreateFullRelease.ps1 -CommitAndPush   # commit + tag + push + GH release on internal
```

Verify the stamp before continuing:

```powershell
(Get-Content package.json | ConvertFrom-Json).version
Get-ChildItem plugins -Filter plugin.json -Recurse |
  ForEach-Object { "$($_.Directory.Name): $((Get-Content $_ | ConvertFrom-Json).version)" }
# All should print the new version. Both marketplace files must be byte-identical:
(Get-FileHash .github\plugin\marketplace.json).Hash -eq (Get-FileHash .claude-plugin\marketplace.json).Hash
```

If the marketplaces don't match, **stop** — re-run `python build/build_plugins.py` and
`--check` until they agree. A stale marketplace ships broken plugin installs.

---

## Phase 1 — Open the Public PR

```powershell
gh auth switch -u <non-emu-account>          # required for public push
.\ReleaseScripts\PublishToPublic.ps1 -DryRun # preview what will be synced/scrubbed
.\ReleaseScripts\PublishToPublic.ps1         # creates branch release/v<version> + PR
gh auth switch -u <emu-account>              # restore
```

The script clones `microsoft/skills-for-fabric`, syncs publishable content, scrubs internal
references (`msitapi.fabric.microsoft.com` → `api.fabric.microsoft.com`,
`gim-home` → `microsoft`), flattens `compatibility/*` to the public root (`CLAUDE.md`,
`.cursorrules`, `.windsurfrules`, `AGENTS.md`), pushes the branch, and opens the PR.

Record the **public PR URL** — Phase 2 smoke tests against the branch from that PR.

---

## Phase 2 — Release-Artifact Smoke (the part this skill exists for)

Three layers, executed in order. Stop on the first failure.

### 2.1 Structural smoke (clone the public release branch)

```powershell
$smoke = "$env:TEMP\smoke-public-<version>"
git clone --branch release/v<version> --depth 1 `
  https://github.com/microsoft/skills-for-fabric.git $smoke
cd $smoke

# Version stamps consistent across all manifests
(Get-Content package.json | ConvertFrom-Json).version
Get-ChildItem plugins -Filter plugin.json -Recurse |
  ForEach-Object { "$($_.Directory.Name): $((Get-Content $_ | ConvertFrom-Json).version)" }

# Marketplaces byte-identical
(Get-FileHash .github\plugin\marketplace.json).Hash -eq `
  (Get-FileHash .claude-plugin\marketplace.json).Hash

# References resolve (skills + agents + common)
python skill_validation.py    # if present in the release; otherwise use the build script
python build\build_plugins.py --check
```

Expected: every plugin at the new version, marketplace hashes equal, validators exit 0.

### 2.2 Install smoke (real `copilot plugin install` from the clone)

Point a temporary Copilot marketplace at the public clone, install every shipped plugin,
verify versions and on-disk skill counts match.

```powershell
copilot plugin marketplace list                              # remember current state
copilot plugin marketplace remove fabric-collection 2>$null
copilot plugin marketplace add fabric-collection $smoke      # local marketplace

foreach ($p in @('fabric-skills','fabric-authoring','fabric-consumption',
                 'fabric-operations','powerbi-authoring')) {
  copilot plugin install "${p}@fabric-collection"
}
copilot plugin list                                          # should show v<version> for all 5

# Count skills shipped vs counts in plugins/<name>/plugin.json
foreach ($p in Get-ChildItem $smoke\plugins -Directory) {
  $manifest = Get-Content "$($p.FullName)\plugin.json" | ConvertFrom-Json
  $shipped  = (Get-ChildItem "$($p.FullName)\skills" -Directory -ErrorAction SilentlyContinue).Count
  "$($p.Name): manifest=$($manifest.skills.Count) shipped=$shipped"
}
```

Expected: zero install errors, `copilot plugin list` shows all 5 at the new version,
shipped == manifest counts.

### 2.3 Behavioral smoke (live `copilot -p` probes)

Six canonical prompts, run **non-interactively**, captured to per-session telemetry. Each
probe should route to the expected skill with zero retries.

```powershell
$probes = @(
  @{ id='enum';      prompt='List every Fabric skill you can see. One per line, no commentary.';                                                     expect='enumeration' }
  @{ id='semmodel';  prompt='I want to create a Power BI semantic model and deploy it. Which skill should I use? Reply with skill name only.';      expect='semantic-model-authoring' }
  @{ id='fabriciq';  prompt='I want to ask questions of a Power BI report in natural language. Which skill? Reply with skill name only.';           expect='fabriciq' }
  @{ id='medallion'; prompt='I want to build a medallion architecture for NYC taxi data. Which skill? Reply with skill name only.';                 expect='e2e-medallion-architecture' }
  @{ id='sparkops';  prompt='I need to investigate why a Spark job is running slow. Which skill? Reply with skill name only.';                      expect='spark-operations-cli (agent acceptable)' }
  @{ id='sqldw';     prompt='I want to create a Fabric Warehouse and load data via T-SQL. Which skill? Reply with skill name only.';                expect='sqldw-authoring-cli' }
)
$work = "$env:TEMP\smoke-public-<version>-probe"; New-Item -ItemType Directory -Force -Path $work | Out-Null
Push-Location $work
foreach ($p in $probes) {
  "==== $($p.id) ===="
  copilot --allow-all-tools -p $p.prompt *>&1 | Tee-Object "probe-$($p.id).txt"
}
Pop-Location
```

Then decode telemetry from `~/.copilot/session-state/<session-id>/events.jsonl`:

```powershell
$stateRoot = "$env:USERPROFILE\.copilot\session-state"
# Today's sessions, in cwd order — first session is the help/enum check, then probes
$sessions = Get-ChildItem $stateRoot -Directory |
  Where-Object { $_.LastWriteTime.Date -eq (Get-Date).Date } |
  Sort-Object LastWriteTime

foreach ($s in $sessions) {
  $sd = Get-Content (Join-Path $s.FullName 'events.jsonl') |
    Where-Object { ($_ | ConvertFrom-Json).type -eq 'session.shutdown' } |
    Select-Object -First 1 | ConvertFrom-Json
  $m  = $sd.data
  $am = Get-Content (Join-Path $s.FullName 'events.jsonl') |
    Where-Object { ($_ | ConvertFrom-Json).type -eq 'assistant.message' } |
    Select-Object -First 1 | ConvertFrom-Json
  [pscustomobject]@{
    session       = $s.Name.Substring(0,8)
    model         = $m.currentModel
    shutdown      = $m.shutdownType
    inputTokens   = $m.modelMetrics.($m.currentModel).usage.inputTokens
    outputTokens  = $m.modelMetrics.($m.currentModel).usage.outputTokens
    cacheRead     = $m.modelMetrics.($m.currentModel).usage.cacheReadTokens
    cacheWrite    = $m.modelMetrics.($m.currentModel).usage.cacheWriteTokens
    apiMs         = $m.totalApiDurationMs
    requests      = $m.modelMetrics.($m.currentModel).requests.count
    toolCalls     = if ($am.data.toolRequests) { $am.data.toolRequests.Count } else { 0 }
    response      = if ($am.data.content.Length -gt 60) { $am.data.content.Substring(0,60) + '...' } else { $am.data.content }
  }
} | Format-Table -AutoSize
```

**Pass criteria:**

- All 6 probes exit 0
- `shutdownType: routine` on every session
- Zero `*error*` / `*retry*` / `*fail*` events in any `events.jsonl`
- Enumeration probe returns **every shipped skill** (cross-check against
  `Get-ChildItem $smoke\skills -Directory`) — zero gap
- 5/6 probes route to the exact expected skill name; the Spark-ops probe may route to
  the `FabricDataEngineer` agent (acceptable — investigative prompts are designed to
  orchestrate, not pick a single leaf skill)

**Capture per-probe metrics for the release log:** input/output/cache tokens, API duration,
premium request count, `totalNanoAiu`, retry count. These come from
`session.shutdown.data.modelMetrics["<model>"].usage` and `.totalApiDurationMs`.

### 2.4 Cleanup

```powershell
foreach ($p in @('fabric-skills','fabric-authoring','fabric-consumption',
                 'fabric-operations','powerbi-authoring')) {
  copilot plugin uninstall $p
}
copilot plugin marketplace remove fabric-collection
copilot plugin marketplace add fabric-collection <dev-repo-path>   # restore dev marketplace
Remove-Item $work -Recurse -Force
# Optionally keep $smoke around for forensic inspection
```

---

## Phase 3 — Human Review and Merge

Post the smoke report to the public PR. Wait for review. Once merged on
`microsoft/skills-for-fabric`, proceed to Phase 4.

---

## Phase 4 — Tag + GitHub Release

```powershell
gh auth switch -u <non-emu-account>
.\ReleaseScripts\PublishToPublic.ps1 -PublishRelease -Version <version>
gh auth switch -u <emu-account>
```

`-PublishRelease` enforces three preconditions and **hard-fails** on any violation:

1. `$Version` is strictly greater than the latest published release (first release on a
   fresh repo is exempt)
2. Public `main` HEAD is the merge commit of `release/v$Version`
3. If the GitHub Release already exists, exits 0 (idempotent); if only the tag exists,
   continues so the Release can be created on top

Release notes come from the `## [<Version>] - <date>` section of `public/CHANGELOG.md`.

---

## What This Skill **Doesn't** Cover

| Asset | What it does | Why not in scope |
|---|---|---|
| `tests/run-vally-eval.ps1` | Provisions / reuses a Fabric workspace, runs live Copilot sessions against `tests/evals/<skill>/eval.yaml` -- the primary CI harness since PR #322 | Requires Fabric tenant + capacity + cert auth (E2EAPIMSIT2 OR shared ephemeral tenant SP). Use the `pre-pr-check` skill or run manually with credentials. |
| `tests/run-smoke-tests.ps1` (legacy) | Same idea against `tests/tests.json` -- kept as break-glass after the Vally cutover | See `docs/ephemeral-tenant-smoke.md`. |
| `tests/run-full-tests.ps1` | Even heavier end-to-end eval suite | Same prerequisites. |
| `pytest -m semantic tests/` | Lightweight routing / disambiguation / structure tests, no Azure | Optional add-on. Run with `pip install -r tests/requirements-dev.txt` first if you want extra coverage of the release artifact. |
| `pytest -m integration tests/` | Live Fabric endpoint tests | Requires `FABRIC_TEST_*` env vars + `az login`. |

The smoke in **Phase 2** is functionally equivalent to "does Copilot CLI discover and
route correctly to the installed skills in a clean install". It is **not** a substitute
for the live Fabric-tenant smoke when shipping changes that touch live endpoints.

---

## Known Gotchas

- **EMU account cannot push to `microsoft/skills-for-fabric`.** Switch with
  `gh auth switch -u <non-emu>` before Phase 1 and Phase 4; restore after.
- **PowerShell `$_:` breaks variable interpolation.** Use `${_}` or rename the loop
  variable (`foreach ($n in @(...)) { "${n}:" }`).
- **`copilot mcp list` does not show plugin-bundled MCPs.** Plugin MCPs are
  lazy-loaded on skill activation, not eagerly listed. Not a release defect.
- **Token usage is NOT in `assistant.turn_end.data.usage`.** It lives in
  `session.shutdown.data.tokenDetails` and
  `session.shutdown.data.modelMetrics["<model>"].usage`.
- **`copilot --resume=<uuid>` no longer deterministic** (CLI 1.0.46+). Find the
  session by `cwd` match or by most-recent `LastWriteTime` under
  `~/.copilot/session-state/`.
- **Marketplace mismatch is a silent foot-gun.** Always confirm
  `.github/plugin/marketplace.json` and `.claude-plugin/marketplace.json` are
  byte-identical after `CreateFullRelease.ps1`; if not, re-run
  `python build/build_plugins.py`.

---

## Example: 0.3.2 Release Numbers (reference baseline)

Used for sanity-checking future runs. Wildly different numbers warrant investigation.

- 5 plugin bundles: `fabric-skills` (24 skills, 4 agents, 1 MCP),
  `fabric-authoring` (10, 3, 0), `fabric-consumption` (10, 4, 1),
  `fabric-operations` (3, 3, 0), `powerbi-authoring` (2, 0, 1)
- 91/91 skill+agent refs resolve, 1015/1015 common refs resolve
- 6-probe behavioral smoke: ~91s total wall time, ~367k input tokens,
  ~215k cache reads (3-onward), 0 retries, 5/6 exact-skill routing,
  1/6 agent-acceptable routing (Spark investigative)
- Per-probe cost: 1 premium request, ~4.6 nanoAIU credits each (probes 3-6 with cache),
  22.9 nanoAIU on probe 1 (cold cache)
