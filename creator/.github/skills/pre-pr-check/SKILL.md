---
name: pre-pr-check
description: >
  Verify a skill PR locally before submitting. Walks workload-team contributors through
  the three local checks that mirror what CI runs on every PR: quality_checker structural
  lint, Vally eval for changed skills, and filtered full-eval for changed skills. Vally
  is the primary harness; legacy smoke is break-glass only. Use before opening or pushing
  to a PR that touches `skills/`, `common/`, `agents/`, or `tests/`. Triggers: "pre-PR
  check", "verify my PR locally", "run vally locally", "run full eval locally",
  "validate my skill before submit", "check my changes before push", "what should I run
  before opening a PR".
---

# Pre-PR Check -- Local Verification Before Submitting

Run the same three checks CI runs, locally, so your PR lands green on the first push.

## When to Use

- Before opening a PR that touches `skills/**`, `common/**`, `agents/**`, or `tests/**`
- Before pushing a new commit to an open PR after substantive changes
- When CI fails and you want to reproduce the failure locally before re-pushing

## What This Skill Does

Walks you through the three checks. **All three matter** -- stop after Step 1 ONLY when the diff is comment-only / docs-only / SKILL.md prose with no behavior impact. Any change to instructions, MUST/PREFER/AVOID lists, examples, or reference files = run Step 2 (and Step 3 if multi-step behavior is in scope).

1. **Quality check** (~10 sec) -- structural lint, broken refs, semantic conflicts
2. **Vally eval for your changed skills** (~3-10 min per skill) -- primary CI harness
3. **Filtered full-eval for your changed skills** (~10-30 min per plan)

If step 1 fails, fix and re-run before step 2. If step 2 fails, fix and re-run before step 3.

> **Legacy smoke is break-glass only.** PR #322 cut over from `tests/run-smoke-tests.ps1` to `tests/run-vally-eval.ps1` as the primary CI harness. Use the legacy smoke path only to cross-check a suspected Vally false negative or during a Vally outage; see [`docs/ephemeral-tenant-smoke.md`](../../../docs/ephemeral-tenant-smoke.md).

---

## Step 0 -- Identify changed skills + build plugin tree (~30 sec)

The Vally + full-eval steps run only what your PR touches. Figure out what changed:

```powershell
# From repo root
git diff --name-only origin/main...HEAD -- skills/ common/ agents/ tests/ | Sort-Object -Unique
```

Note which skill directories under `skills/` show up. Those are the skills you must verify. Example output `skills/dataflows-consumption-cli/SKILL.md` means you must run Vally + full-eval for `dataflows-consumption-cli`.

After PR #322 (Vally cutover, Option C), **Vally launches MCP servers directly from each eval.yaml's `environment.mcpServers` block** -- you no longer need to materialize the plugin tree for Vally to see MCP. If your skill needs `powerbi-modeling-mcp` (e.g. `semantic-model-authoring`, `powerbi-report-*`), confirm that `tests/evals/<skill>/eval.yaml` declares the server under `environment.mcpServers.powerbi-modeling-mcp`. Local-dev runs use the committed interactive args; CI rewrites the staged copy with SP cert auth via `Add-CiPowerBiMcpAuthToStagedEval` in `tests/run-vally-eval.ps1`. See [`tests/evals/README.md` -> "Declaring an MCP server your skill needs"](../../../tests/evals/README.md) for the canonical guidance.

If you ALSO want to validate end-user CLI install behavior (separate concern from Vally), run `python build/build_plugins.py` to materialize `plugins/<name>/{skills,agents,common,.mcp.json}` locally. This is needed by the legacy smoke harness and by `copilot mcp install`, NOT by Vally.

---

## Step 1 -- Quality check (always, ~10 sec)

This is the structural lint CI runs first. Catches missing frontmatter, broken cross-references, semantic conflicts with existing skills, naming convention violations.

```powershell
# Prereq (once per machine)
pip install PyYAML requests pytest

# Run from repo root
python .github/workflows/quality_checker.py
```

**Pass criteria:** exit code 0 (warnings are OK, critical issues are not). Inspect `quality-report.json` for details.

If this fails, the `quality-check` skill has deeper coverage:
- Invoke: `/quality-check` (Copilot CLI) or read `.github/skills/quality-check/SKILL.md`

### Optional companion lints for Vally + MCP changes

When your PR touches an `eval.yaml` (any `tests/evals/<skill>/`) or a plugin manifest (`plugins/<plug>/.github/plugin/plugin.json`), also run:

```powershell
# eval.yaml structure gate: every stim needs the Layer-0 graders (minus any
# dropped via a per-stim `l0_exempt`), and every NEW eval dir or NEW stim needs
# Layer-1 `tool-calls` + Layer-2 `program` graders (offline / codegen stims opt
# out with a per-stim `l1l2_exempt: "<reason>"`).
# This is the check that fails a new eval missing L1+L2 -- run it before push.
python -m unittest tests/test_eval_yaml_structure.py -v

# Plugin manifest <-> eval.yaml MCP consistency:
# every MCP-bearing plugin's skills must declare the server in their eval.yaml
python -m unittest tests/test_eval_yaml_mcp_servers.py -v

# End-to-end Vally MCP staging behavior (DryRun: local + CI inject + missing-cert + non-MCP)
python -m unittest tests/test_vally_native_mcp_staging.py -v
```

All three are wired into CI's quality-check job. Running them locally before push catches the same drift CI would flag minutes later.

> **Watch for silent skips.** `test_vally_native_mcp_staging.py` requires Node 22+ AND `pwsh` on PATH (it shells out to the wrapper). On a machine without Node 22 (Windows default ships Node 20), you will see `OK (skipped=4)` -- exit code 0, looks like a pass, but **no test actually ran**. Set up Node 22 per Step 2a's prereqs first, then re-run.

---

## Step 2 -- Vally eval for your changed skill (~3-10 min per skill; RUN BEFORE PUSH unless your change is comment-only)

Runs the same Vally harness CI runs, against a workspace on the shared ephemeral test tenant. Vally measures: skill-invocation routing, output matching expected behavior, tool-use, and Layer 0/1/2 graders (budget, completion, deterministic checks). The canonical eval guide is [`tests/evals/README.md`](../../../tests/evals/README.md).

### 2.0 PREREQUISITE -- log in to the shared ephemeral tenant as AdminUser01 BEFORE invoking this skill

> **Copilot CLI cannot pop a browser.** If you start the Vally wrapper before `az login` has succeeded, the underlying Fabric REST calls (workspace-ID resolution, Layer 2 graders) silently block on an Azure browser interaction you cannot see. Authenticate first, then invoke the wrapper.

Vally runs against the **shared ephemeral test tenant** (the same one CI uses), NOT your corporate tenant. Sign in as that tenant's admin user:

> **Access prerequisite:** make sure you are a member of the `PBI-Test-UserAcc-Access` AAD security group (auto-approved for Azure Data Org; allow 24-48h to propagate after you join).

1. **Find the current tenant + cert.** Open `aka.ms/fabrictenants` and open the **MSIT** tab. Note the current admin user `AdminUser01@msitprimary<date>.onmicrosoft.com` and tenant `msitprimary<date>.onmicrosoft.com`. The tenant rotates (~90 days) -- always read the current one, do not hardcode a date.
2. **Download + install the admin cert.** Download `AdminCert01.pfx` for that tenant from the same page and install it into your user certificate store so the browser can present it during sign-in. On Windows, double-click the `.pfx` and import it to **Current User**; on macOS/Linux, import it into your login keychain / user cert store.
3. **Log in as AdminUser01** (certificate-based auth; pick the installed cert when prompted) and confirm:
   ```pwsh
   az login --tenant msitprimary<date>.onmicrosoft.com --allow-no-subscriptions
   az account show --query "{tenant:tenantId, user:user.name}" -o json   # expect AdminUser01@msitprimary<date>
   ```

Full cert + SP details are in [`docs/ephemeral-tenant-smoke.md`](../../../docs/ephemeral-tenant-smoke.md). Then return to Copilot CLI and continue with Step 2a -- the skill provisions a fresh workspace on this tenant via `setup_test_env.py` and runs Vally.

### 2a. Run Vally for your changed skill (one command, end-to-end)

> **Prefer `pwsh` over `powershell.exe`.** Nightly CI uses `pwsh` (PowerShell 7+); using the same shell locally gives you the closest parity with CI behavior and works cross-platform. On Windows: install [PowerShell 7](https://github.com/PowerShell/PowerShell/releases/latest).

You also need:
- **Node 22+** on PATH (the vally CLI + copilot-sdk depend on `Promise.withResolvers`). Use `fnm install 22 && fnm use 22`.
- For MCP-bearing skills: confirm `tests/evals/<skill>/eval.yaml` declares `environment.mcpServers.<server-name>`. After PR #322, Vally launches MCP servers from that block directly; no plugin install is required for the Vally path.

**First, provision a fresh CI-equivalent workspace (this is the default -- do NOT reuse your own workspace).** CI builds a brand-new ephemeral workspace per shard via `setup_test_env.py` and seeds it (lakehouse, sanity notebook, the tables stims reference). Reproduce that locally so your run matches CI.

**Pin a Spark-capable capacity.** If you omit `--capacity-id`, `setup_test_env.py` auto-discovers any Active capacity -- but small Trial (FT-class) capacities often have no warm Spark/Livy, so the seed-data load and every Spark stim fail. Prefer an `FTL64` / F64-class capacity (closest to CI's F64). The agent should pick one and pass it:

```pwsh
# Prefer an FTL64 / F64-class Active capacity (Spark-capable); fall back to any Active one.
$caps = az rest --method get --resource https://api.fabric.microsoft.com --url "https://api.fabric.microsoft.com/v1/capacities" --query "value[?state=='Active']" -o json | ConvertFrom-Json
$pick = $caps | Where-Object { $_.sku -match '64$' } | Select-Object -First 1
if (-not $pick) { $pick = $caps | Select-Object -First 1 }
if (-not $pick) {
  throw "No Active Fabric capacity is visible to your login. Re-check Step 2.0: 'az login' against the ephemeral tenant (msitprimary<date>) as AdminUser01, and confirm your PBI-Test-UserAcc-Access membership has propagated (can take 24-48h after joining)."
}
# Provisions skills-for-fabric-test-<timestamp>, seeds it, and writes the name + id
# to tests/testdata/last_setup.json. You already did `az login` in 2.0.
python tests/testdata/setup_test_env.py --skip-login --capacity-id $pick.id
```

**Then confirm the seed loaded.** If Spark was unavailable on the capacity, the load fails with `data_loaded=NO` and the Spark stims fail locally for an environmental reason (not a skill bug) -- re-provision on an F64-class capacity, or trust CI's F64 gate for the Spark stims:

```pwsh
$s = Get-Content tests/testdata/last_setup.json -Raw | ConvertFrom-Json
if (-not $s.data_loaded) { Write-Warning "data_loaded=NO -- Spark/Livy was not available on this capacity; Spark stims will fail locally and do NOT reflect CI's F64." }
```

**Then run Vally against that workspace.** Pass the name `setup_test_env.py` printed; the wrapper auto-resolves its id from `last_setup.json`, so you do not pass the GUID:

```pwsh
# Scope Vally to a single skill's eval via -EvalDirs.
pwsh -File tests/run-vally-eval.ps1 `
  -Workspace "<name printed by setup_test_env.py, e.g. skills-for-fabric-test-20260617-112042>" `
  -EvalDirs "<your-skill-eval-dir>" `
  -Runs 1
```

> **Why provision instead of reusing your own workspace?** Your interactive workspace has seed data (tables, item ids) the fresh CI workspace does not, so a stim can pass locally and fail in CI -- the exact trap in the Local vs CI parity table below. A freshly provisioned workspace reproduces CI faithfully, including CI's current gaps (e.g. the lakehouse is created without schemas enabled, so a stim that needs `CREATE SCHEMA` fails the same way it does in CI). Remember to delete the workspace afterward (Step 4).

> **Escape hatch (fast iteration only, NOT CI-faithful).** For a quick inner-loop check you MAY point the wrapper at a workspace you already own: `-Workspace "<your-workspace>"` (the wrapper does not provision; it resolves the id live). This is faster but does NOT match CI, so it must never be your final pre-push check -- re-run against a freshly provisioned workspace before you push. When running this skill on a user's behalf, default to provisioning; do NOT ask whether they want to use their own workspace. Only reuse an existing workspace if the user explicitly asks, and then say results may not match CI.

`-EvalDirs` accepts a comma-separated list of directories under `tests/evals/`, e.g. `-EvalDirs "dataflows-consumption-cli"` or `-EvalDirs "dataflows-consumption-cli,dataflows-authoring-cli"`. Use `-EvalDirs ALL` for the full suite.

What this does end-to-end:
1. Validates Node 22+, prepares the optional MCP service-principal env injection (no-op locally unless `CI_MCP_OVERLAY=true` + `AZURE_*` env vars are present), checks workspace
2. Stages eval.yaml files into `tests/.vally-staging/` with `{{WORKSPACE}}` / `{{WORKSPACE_ID}}` substituted
3. Resolves the suite filter (skill / tier / scope tags) from `.vally.yaml`
4. Invokes `npx @microsoft/vally-cli@0.5.0 eval --eval-spec ...` against the staged files
5. Writes per-trial results.jsonl + trajectory JSONs to `tests/.vally-results/`

`-DryRun` is for verifying the staged YAML SHAPE only (use it when you just edited eval.yaml structure and want to inspect what the wrapper would pass to Vally). It does NOT replace Step 2 -- it never starts Vally or calls Fabric, so it catches zero routing or behavior regressions.

### 2b. `-EvalDirs` accepts directory names from `tests/evals/`

It is NOT a regex; it matches directories under `tests/evals/`. Find the right directory by listing what exists:

```powershell
Get-ChildItem tests/evals -Directory | Select-Object Name
```

A skill named `dataflows-consumption-cli` has its eval at `tests/evals/dataflows-consumption-cli/eval.yaml`.

### 2c. Read results

Vally writes to `tests/.vally-results/<timestamp>/` (one subdir per run). Find the latest:

```powershell
$latest = Get-ChildItem tests/.vally-results -Directory |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
$latest.FullName
```

Inside that dir:
- `<eval-name>/results.jsonl` -- one line per trial with `gradeResult.passed`, grader scores, token usage
- `<eval-name>/trial-*/trajectory.json` -- the full Copilot CLI session transcript

**Pass criteria:** every trial in `results.jsonl` shows `gradeResult.passed: true`, and the wrapper's terminal output shows `vally exited 0`.

If a trial fails, open the matching `trajectory.json` -- it contains the prompt, tool calls, and final agent response that the graders evaluated.

### 2d. Iterate fast with `-Runs 1` + `-EvalDirs <one-skill>`

`-Runs 1` runs each stimulus once (default is the eval's `config.runs`, usually 5). For PR-pre-flight that's enough to confirm the skill loads and routes correctly. Bump to `-Runs 3` if you suspect flakiness.

### 2e. L1 (`tool-calls`) + L2 (`program` verifier) are MANDATORY for new evals

L0 (`output-contains` / `skill-invocation`) catches "did the skill answer". L1 + L2 catch "did the skill do the right thing in Fabric" -- the difference between graders judging *prose* and graders judging *behavior*. **This is not an optional follow-up:** for any NEW eval dir, or any NEW stim added to an existing eval, the structural gate (`tests/test_eval_yaml_structure.py`) HARD-FAILS the PR unless every stim carries a `tool-calls` (L1) grader AND a `program` (L2) verifier. The eventhouse-authoring-cli pilot is the worked example; follow [`tests/evals/README.md#how-to-write-a-verifier-for-your-skill`](../../../tests/evals/README.md#how-to-write-a-verifier-for-your-skill) (Steps 1-5) to add a `tool-calls` matcher and a paired `program` verifier under `tests/evals/_graders/<skill>/verify-<artefact>.ps1`. Ship them together -- a `tool-calls: required` matcher without a paired `program` verifier just checks the LLM mentioned an endpoint, not that it actually fired one with the right payload.

**Offline / codegen / pure-advice stims** -- where the agent writes SQL or reviews a query and builds nothing in Fabric, so there is no tool call or artefact to assert -- opt out instead of bolting on meaningless graders: add a `l1l2_exempt: "<reason>"` to the stim. The reason is mandatory and surfaces as a WARN so the gap stays auditable. Prefer reshaping the stim into an execution task (so L1+L2 are real) when that fits; reach for `l1l2_exempt` only when the task genuinely produces no Fabric side effect.

---

## Step 3 -- Filtered full-eval for your changed skill (~10-30 min per plan; run if your change affects multi-step behavior -- CI runs this on every PR)

CI runs full-eval nightly + on PRs touching `skills/**` (PR-touched full-eval). If you want to validate locally before CI does, run only the relevant plans.

`tests/run-full-tests.ps1` provisions its own `FullEval-*` workspace -- it does NOT reuse the Vally workspace from Step 2 -- so you don't need to coordinate workspaces between the two steps.

> Same `az login` prerequisite as Step 2.0 -- the wrapper drops `-skipLogin` by default to a real interactive login that Copilot CLI can't surface. Authenticate in your terminal first, then pass `-skipLogin` here too.

```pwsh
pwsh -File tests/run-full-tests.ps1 `
  -PlanFilter "eval-<your-skill>" `
  -skipLogin `
  -SkipWarehouse -SkipLakehouse -SkipCleanup `
  -capacityId "<capacity-GUID>" `
  -tenant "<ephemeral-tenant>.onmicrosoft.com"
```

- `-PlanFilter` accepts a comma-separated list and wildcards. Unknown names hard-fail BEFORE any provisioning, so typos are caught instantly.
- Drop `-SkipWarehouse` if your skill needs a warehouse; similarly `-SkipLakehouse`.
- Plan names live under `tests/full-eval-tests/plan/03-individual-skills/eval-*.md`.

**Pass criteria:** the run produces `tests/full-eval-tests/result/eval-<skill>-results.md` with a `## Totals` table showing `PASS` >= 1 and `FAIL` / `ERROR` == 0.

For full details on plan structure, see [`tests/full-eval-tests/README.md`](../../../tests/full-eval-tests/README.md).

---

## Step 4 -- Cleanup

If you provisioned a workspace in Step 2 (the default) via `setup_test_env.py`, it does NOT auto-delete -- `tests/run-vally-eval.ps1` only runs against it, it never cleans up. Delete it when you are done (its name and id are recorded in `last_setup.json`):

```powershell
$setup = Get-Content tests/testdata/last_setup.json -Raw | ConvertFrom-Json
$setup.workspace_name + " (" + $setup.workspace_id + ")"
az rest --method DELETE `
  --url "https://api.fabric.microsoft.com/v1/workspaces/$($setup.workspace_id)" `
  --resource "https://api.fabric.microsoft.com"
```

`tests/run-full-tests.ps1` (Step 3) provisions its own `FullEval-<timestamp>` workspace and auto-deletes it on a clean pass -- it does NOT write `last_setup.json`. If the run bailed out (`EVAL-SUITE-*`), was interrupted, or the auto-delete failed, that workspace is left behind -- find it by its `FullEval-` prefix and delete it:

```powershell
az rest --method GET --url "https://api.fabric.microsoft.com/v1/workspaces" `
  --resource "https://api.fabric.microsoft.com" `
  --query "value[?starts_with(displayName, 'FullEval-')].[displayName,id]" -o tsv
# then DELETE each id you recognize, exactly as the Step 2 snippet above does.
```

Workspaces left behind accumulate against the shared capacity and have caused throttling incidents. The CI tenant has an orphan sweeper for `FullEval-*` (not for the Step 2 `skills-for-fabric-test-*` workspaces), so delete what you create.

---

## Local-vs-CI tenant differences

Vally runs on a different tenant + workspace shape locally vs in CI. Skills that pass local but fail CI almost always trip on one of the differences below. Skim this BEFORE you push so you don't waste a CI shard rediscovering them.

| Aspect | Local (your `az login`) | CI (ephemeral tenant) |
|---|---|---|
| **Workspace** | Default: fresh `skills-for-fabric-test-<timestamp>` via `setup_test_env.py` (same shape as CI); escape hatch only: your own interactive workspace | `skills-for-fabric-test-<timestamp>` via `setup_test_env.py`, created + destroyed per shard |
| **Capacity** | Whatever your workspace is bound to (often Premium Personal) | F64 `cditestautomatiodonotdelete`, pinned via repo var `FABRIC_CAPACITY_ID` |
| **Spark/Livy availability** | A small Trial (FT-class) capacity may have no warm Spark, so the seed-load and Spark stims fail (`data_loaded=NO`); pin an FTL64/F64-class capacity (see Step 2a) | F64 is always Spark-capable |
| **Auth** | `az login` interactive browser | Federated SP `fabric-skills-smoke-test` via `azure/login@v2` OIDC; cert at `$env:AZURE_CLIENT_CERTIFICATE_PATH` |
| **MCP env** | `environment.mcpServers` block in your `eval.yaml` (committed interactive form; browser auth on first call) | Same committed block, BUT `tests/run-vally-eval.ps1` rewrites the staged copy to add `--authmode=serviceprincipal --skipconfirmation` plus `AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_CLIENT_CERTIFICATE_PATH` env entries (gated by `$env:CI_MCP_OVERLAY -eq 'true'`) |
| **`{{WORKSPACE}}` substitution** | From the `-Workspace` name you pass; id resolves from `last_setup.json` (or `$env:FABRIC_WORKSPACE_ID`) | From `WORKSPACE_ID` emitted by `tests/testdata/setup_test_env.py` into `$env:GITHUB_OUTPUT` |
| **Time-to-first-token** | Fast (warm token, your tenant's region) | Slower (capacity provisioning + workspace bind round-trips) |
| **Hardcoded artifact IDs in stims** | Often work because you seeded them | Always fail -- CI workspace is fresh |

**3 mitigation rules:**

1. **Always parametrize workspace via `{{WORKSPACE}}` in stims.** Never hardcode workspace names, item GUIDs, or capacity IDs. If your skill needs a seeded artifact, document it in `tests/testdata/setup_test_env.py` so CI provisions it too.
2. **Verify the staged MCP block locally before pushing** any change to an eval.yaml that declares `powerbi-modeling-mcp`. `pwsh -File tests/run-vally-eval.ps1 -Workspace "any-name-here" -DryRun -EvalDirs "<your-skill>"` writes the staged YAML to `tests/.vally-staging/` -- inspect it to confirm the MCP block is shaped the way you expect. `-Workspace` is required even for `-DryRun` (any string works -- it's only substituted into the staged YAML; no Fabric call is made). Then re-run with `$env:CI_MCP_OVERLAY = 'true'` plus valid `AZURE_*` env vars to confirm the CI rewrite path also yields valid YAML; `AZURE_CLIENT_CERTIFICATE_PATH` must point to an existing file on disk (any content -- create a throwaway one-liner with `[IO.File]::WriteAllText("$pwd\dummy.pem","-----BEGIN CERTIFICATE-----`n-----END CERTIFICATE-----`n")` if you need a placeholder; the helper validates the path exists but not the cert content).
3. **If 5/5 local + 1/3 CI fails, do NOT silently bump `max_duration`.** File a flakiness issue with the failing trial's `trajectory.json`. Masking timing flakes with bigger budgets is how budget drift starts.

---

## Must

- Run **step 1 (quality_checker) before EVERY push** -- it's 10 seconds and catches the most common bot / reviewer nits
- Run **step 2 (Vally) when you touch a skill body or an eval** -- CI will run it anyway; catching failures locally saves a review round
- Use **`tests/run-vally-eval.ps1`** (the wrapper), not raw `npx vally` -- the wrapper handles `{{WORKSPACE}}` substitution, sharding, and the optional CI MCP rewrite for `powerbi-modeling-mcp`
- Use `-EvalDirs "<skill>"` to scope to ONLY your changed skill -- full-suite local runs take hours and burn tokens

## Prefer

- `-Runs 1` for fast pre-flight; bump to `-Runs 3` only if you suspect flakiness
- `-DryRun` first if you changed the eval.yaml itself -- it confirms staging is correct without spending tokens
- One Vally round per skill before pushing; then open a draft PR so CI runs the full PR-touched gate
- Adding or updating Vally coverage in `tests/evals/<skill>/eval.yaml` (NOT in legacy `tests/tests.json`) for new or changed skill behavior

## Avoid

- Pushing without running quality_checker -- > 80% of bot review noise is structural issues this catches
- Running Vally without `-EvalDirs` locally -- that's CI's job; the full suite takes ~1h, no value for one-skill PRs
- Using legacy `tests/run-smoke-tests.ps1` as your primary path -- it is break-glass only since PR #322; Vally is now the primary CI gate
- Editing `tests/tests.json` to make a legacy smoke test pass -- legacy smoke is no longer the gate; add or fix Vally coverage instead
- Leaving workspaces behind when full-eval (Step 3) is interrupted -- orphans cause capacity throttling

---

## Examples

### Example 1: I touched one skill, what should I run?

**User prompt:** "I added a sentence to `skills/dataflows-consumption-cli/SKILL.md`. What do I run before pushing?"

**Response:**
1. `git diff --name-only origin/main...HEAD -- skills/` confirms only `dataflows-consumption-cli` changed.
2. Run step 1 (quality_checker).
3. Confirm the eval dir exists: `Get-ChildItem tests/evals -Directory | Where-Object Name -eq 'dataflows-consumption-cli'`.
4. Run step 2 with `-EvalDirs "dataflows-consumption-cli" -Runs 1`.
5. Skip step 3 unless the change affects multi-step behavior -- CI's PR-touched full-eval will run it anyway.

### Example 2: I added a new skill

**User prompt:** "I added a new skill `skills/my-new-skill-cli/SKILL.md` and a corresponding `tests/full-eval-tests/plan/03-individual-skills/eval-my-new-skill.md`. What do I run?"

**Response:**
1. Step 1 (quality_checker). New skills often miss the update-notice blockquote -- this catches that.
2. Add Vally coverage at `tests/evals/my-new-skill-cli/eval.yaml` (see [`tests/evals/README.md`](../../../tests/evals/README.md) for the Layer 0 graders AND the mandatory Layer-1 `tool-calls` + Layer-2 `program` graders every new eval needs -- offline / codegen stims opt out with `l1l2_exempt: "<reason>"` -- plus the "Declaring an MCP server your skill needs" subsection if your skill needs one). Register it under the appropriate suites in `.vally.yaml`. Run `python -m unittest tests/test_eval_yaml_structure.py -v` to confirm the structure gate passes before you push.
3. Step 2 with `-EvalDirs "my-new-skill-cli" -Runs 3` -- new skills should land with multiple runs to surface flakiness early.
4. Step 3 with `-PlanFilter "eval-my-new-skill"` -- new skills SHOULD have an eval plan and a local-pass before submission.
5. If you want the new skill to ship in a plugin bundle (end-user `copilot mcp install`), also run `python build/build_plugins.py` to materialize `plugins/<plug>/{skills,agents,common,.mcp.json}` locally. This is independent of Vally -- Vally already sees the skill from your eval.yaml's `environment.skills` path.
6. In your PR description, note the baseline-no-skills delta (CI does not run baseline) per [CONTRIBUTING.md](../../../CONTRIBUTING.md#minimum-evaluation-prompts).

### Example 3: CI failed on Vally but my local pass was clean

**User prompt:** "My local Vally passed but CI Vally shows two failing trials on `eventhouse-authoring-cli`. Why?"

**Response:** Most common causes:
1. **You ran against a workspace with seed data CI doesn't have.** Re-run against a fresh CI-equivalent workspace (provision via `python tests/testdata/setup_test_env.py`) -- or look at the trial's trajectory.json for resource-not-found errors.
2. **Your skill change is non-deterministic** (e.g. depends on tool-call ordering). Re-run Vally with `-Runs 3` locally; if any trial fails, that's the bug.
3. **MCP server missing locally.** If the skill depends on `powerbi-modeling-mcp` (e.g. `semantic-model-authoring`), ensure your eval.yaml declares the server in `environment.mcpServers` (committed form is interactive auth). Locally that block stays interactive; in CI the wrapper rewrites it to `--authmode=serviceprincipal --skipconfirmation` plus the `AZURE_*` env block (gated by `CI_MCP_OVERLAY=true`). The Vally workflow exports those env vars after SP login. If your local run hangs on a browser prompt, that's the interactive auth path engaging as designed.
4. **Eval grader expectations changed.** Compare the trial's `gradeResult` block in `results.jsonl` against the local pass to see which grader differs. For a faster read, the CI artifact `vally-smoke-results-<runid>-<attempt>-shard<N>` ships per-trial transcripts at `transcripts/<eval>__<stim>__trial<N>.txt` (rendered by `tests/vally-ci/Render-VallyTranscripts.ps1`); each file shows the full agent dialog plus per-grader PASS/FAIL with evidence, in the same shape the legacy smoke harness used.

---

## See Also

- `.github/skills/quality-check/SKILL.md` -- deeper quality checker usage
- `.github/skills/pre-pr-review/SKILL.md` -- run a deep cross-verified review on YOUR OWN PR before submitting it
- `tests/evals/README.md` -- canonical Vally eval guide (Layer 0/1/2 graders, suite tags, threshold tuning)
- `docs/testing-guide.md` -- the canonical local-test cookbook (table of all `-EvalDirs` / `-PlanFilter` variants)
- `docs/ephemeral-tenant-smoke.md` -- legacy smoke break-glass + shared-tenant rotation details
- `tests/full-eval-tests/README.md` -- full-eval plan structure + grading
