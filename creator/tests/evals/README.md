# Vally evals (`tests/evals/`)

Vally is the primary auto-firing test harness for skills-for-fabric PR and nightly validation. New behavioral coverage belongs in `tests/evals/<skill>/eval.yaml`; legacy smoke (`tests/tests.json`, `tests/run-smoke-tests.ps1`, `fabric-smoke-ephemeral.yml`, and `fabric-smoke-pr-touched.yml`) is frozen for manual break-glass only.

## What's here

| Path | Stimuli | Persona | Notes |
|---|---:|---|---|
| `dataflows-consumption-cli/` | 4 | consumption | list, query execution, custom M, refresh history |
| `spark-consumption-cli/` | 1 | consumption | Livy sanity |
| `sqldw-consumption-cli/` | 2 | consumption | basic + advanced query |
| `eventhouse-consumption-cli/` | 3 | consumption | basic + analytical + routing negative |
| `eventhouse-authoring-cli/` | 1 | authoring | idempotent create-merge table plus Layer 1+2 pilot |
| `activator-consumption-cli/` | 3 | consumption | list + show + inspect |
| `activator-authoring-cli/` | 3 | authoring | create + alert + notify |
| `semantic-model-consumption/` | 1 | consumption | DAX query execution |
| `fabriciq/` | 1 | consumption | Ask Power BI data analysis |
| `semantic-model-authoring/` | 4 | authoring | refresh, rename, AI readiness, permissions |
| `spark-operations-cli/` | 3 | operations | failed-notebook + pipeline + sessions |
| `sqldw-operations-cli/` | 1 | operations | slow queries via queryinsights (MSIT-only) |
| `eventstream-consumption-cli/` | 3 | consumption | list + inspect + health |
| `eventstream-authoring-cli/` | 4 | authoring | create + source + filter + deploy |
| `spark-authoring-cli/` | 9 | authoring | notebook codegen (token-budget sensitive) |
| `dataflows-authoring-cli/` | 6 | authoring | mashup authoring, preview, output destinations |
| `dataflows-save-as-authoring-cli/` | 1 | authoring | save-as clone flow |
| `search-consumption-cli/` | 1 | consumption | workspace item search |
| `synapse-migration/` | 2 | migration | Synapse-to-Fabric migration guidance |
| `pipeline-migration/` | 2 | migration | Synapse-pipeline-to-Fabric guidance + offline JSON translate |
| `document-workspace-agent/` | 1 | agent | free-routing documentation agent |
| `spark-consumption-cli-isolated/` | 1 | composition | same as spark-consumption-cli but isolated skills |
| `powerbi-report-planning/` | 1 | authoring | plan a Power BI executive report |
| `powerbi-report-design/` | 1 | authoring | pick a report design archetype |
| `powerbi-report-authoring/` | 1 | authoring | add page + validate local PBIR |
| `powerbi-report-management/` | 1 | authoring | publish a local PBIP to Fabric |

**Total: 26 eval.yaml, 61 stimuli** across consumption (19), authoring (32), operations (4), migration (4), agent (1), and composition (1). 60 stimuli are `tier: smoke`; 1 (`sqldw-operations-cli`) is `scope: msit-only` (no tier).

Most graders are built-in Vally (`skill-invocation`, `completed`, `output-not-matches`, `output-contains`, `output-matches`, `token-budget`, `error-count`). The eventhouse-authoring-cli pilot also includes Layer 1 `tool-calls` checks and one Layer 2 `program` verifier.

Each stimulus carries an in-flight **constraints** kill-switch (`max_turns`, `max_tokens`, `max_duration`) and a per-eval pass `threshold: 1.0`. All graders today return binary 0/1; 1.0 is the semantically explicit 'every grader must pass' verdict and future-proofs against fractional LLM judges.

## Primary harness

Use Vally for new and changed skill behavior. `.github/workflows/fabric-smoke-vally.yml` is the PR and nightly gate; it discovers eval specs from this folder and filters suites through `.vally.yaml`.

Legacy smoke stays in the repo only as a manual break-glass fallback. Do not add new `tests/tests.json` stims unless you are deliberately maintaining that legacy path; add Vally stimuli here instead. See `docs/legacy-smoke-break-glass.md` for the manual-only workflow and revert recipe.

### Reviewer policy pointers

Instruction files stay short; this README is canonical for Vally testing detail. When reviewing skill or test changes:

- Require `tests/evals/<skill>/eval.yaml` for new skills or material behavior changes.
- Pair new trigger surfaces with `tests/test_routing.py` coverage and, when practical, a Vally stimulus.
- Keep legacy `tests/tests.json` frozen for manual break-glass; maintain only `prompt` and `expectedSkills` when intentionally touching that fallback, and keep a matching Vally update for behavior changes.
- Do not re-arm legacy smoke workflows by adding `schedule`, `pull_request`, or `pull_request_target` to `.github/workflows/fabric-smoke-ephemeral.yml` or `.github/workflows/fabric-smoke-pr-touched.yml`.

### Suites (`.vally.yaml`)

| Suite | Contents |
|---|---|
| `ci` | Default CI suite -- all portable evals except MSIT-only (25 skill tags) |
| `smoke` | Smoke-tier stimuli only (`tags.tier: smoke`, 60 stimuli) |
| `consumption` | Consumption-persona evals (9) |
| `authoring` | Authoring-persona evals (11) |
| `operations` | Operations-persona evals -- portable, excludes MSIT-only (1: spark-operations-cli) |
| `composition` | Composition matrix variants (isolated skill loading) |
| `msit` | MSIT-only evals (require MSSales workspace/warehouse access; opt-in) |

`sqldw-operations-cli` is tagged `scope: msit-only` and lives only in the `msit` suite. Default `operations`/`ci` runs work for any tenant; MSIT contributors opt in explicitly via `-Suite msit`.

### Relationship to legacy smoke / full-eval marking

Legacy smoke and full-eval runners still support `plugin:` selectors, but Vally does not install Copilot plugins. Each `eval.yaml` declares `environment.skills: [../../../skills/<name>]` and Vally loads those skills directly via the Copilot SDK.

When porting legacy coverage, translate the smoke `plugin:` tag and `expectedSkills` list to the matching `environment.skills` list. The source of truth for plugin membership remains `plugins/<name>/.github/plugin/plugin.json`, read by `build/plugin_index.py::load_plugin_index()`.

## How to run locally

### Quick start (wrapper script)

```powershell
# Run a single skill's eval
.\tests\run-vally-eval.ps1 -Workspace "skills-for-fabric-test-YYYYMMDD" -Skill eventhouse-consumption-cli -Runs 3

# Run all smoke-tier stimuli
.\tests\run-vally-eval.ps1 -Workspace "skills-for-fabric-test-YYYYMMDD" -Suite smoke -Runs 1

# Run a suite with N parallel workers (default 5; CI shards use -Workers 3)
.\tests\run-vally-eval.ps1 -Workspace "skills-for-fabric-test-YYYYMMDD" -Suite smoke -Runs 1 -Workers 3

# Run all evals (expensive!)
.\tests\run-vally-eval.ps1 -Workspace "skills-for-fabric-test-YYYYMMDD" -Runs 5

# Dry run (stage files only, no tokens spent)
.\tests\run-vally-eval.ps1 -Workspace "skills-for-fabric-test-YYYYMMDD" -DryRun

# Composition matrix: run spark with only spark-consumption-cli loaded
.\tests\run-vally-eval.ps1 -Workspace "skills-for-fabric-test-YYYYMMDD" `
  -Skill spark-consumption-cli-isolated `
  -SkillDir "skills/spark-consumption-cli" -Runs 5
```

### Prerequisites

1. **Node 22+** (the `@github/copilot` SDK Vally spawns requires `Promise.withResolvers`):
   ```powershell
   fnm install 22
   fnm use 22
   node --version   # v22.x.x
   ```
2. **Azure CLI logged in to the ephemeral test tenant**:
   ```powershell
   az login --tenant <ephemeral-tenant>
   ```
3. **A fresh test workspace** (the prompts contain `{{WORKSPACE}}` placeholders):
   ```powershell
   python tests/testdata/setup_test_env.py
   # outputs a workspace name like skills-for-fabric-test-YYYYMMDD-HHmmss
   ```

### Manual invocation (without wrapper)

```powershell
$workspace = "skills-for-fabric-test-YYYYMMDD-HHmmss"
$src = "tests/evals/eventhouse-consumption-cli/eval.yaml"
$dst = "tests/.vally-staging/eventhouse-consumption-cli/eval.yaml"
New-Item -ItemType Directory -Path (Split-Path $dst) -Force | Out-Null
(Get-Content $src -Raw) -replace '{{WORKSPACE}}', $workspace | `
  Set-Content -Path $dst -Encoding utf8NoBOM

npx --yes @microsoft/vally-cli@0.5.0 eval `
  --eval-spec $dst `
  --runs 5
```

### Lint only (no tokens)

```powershell
npx --yes @microsoft/vally-cli@0.5.0 lint `
  --eval-spec tests/evals/eventhouse-consumption-cli/eval.yaml
```

## Composition matrix

The `spark-consumption-cli-isolated` eval is the first **composition matrix
pair**. It runs the same stimulus as `spark-consumption-cli` but with ONLY the
target skill loaded (via `-SkillDir`), excluding all other skills that
`.vally.yaml`'s `paths.skills: skills/` would normally load.

**Why**: PR #199 discovered that spark-consumption-cli is mis-routed 4/5 times
when all 27 skills are loaded. The isolated variant tests whether the routing
failure is caused by description overlap with spark-authoring-cli.

**How**: The wrapper script's `-SkillDir` param overrides Vally's skill discovery
root to a directory containing only the target skill.

## Where results land

`tests/.vally-results/<run-name>/<timestamp>/` (gitignored):

- `results.jsonl` -- one JSON object per trial
- `eval-results.md` -- human-readable aggregate summary

### Comparing results across suites/skills

```powershell
# Compare by skill (default)
.\tests\compare-vally-results.ps1

# Compare by suite (consumption vs authoring vs operations)
.\tests\compare-vally-results.ps1 -GroupBy suite

# Include all historical runs (not just latest)
.\tests\compare-vally-results.ps1 -All
```

Shows per-group: avg score, token usage (in/out/total), wall time, run count,
and estimated cost. Use to detect regressions or compare efficiency between
personas.

## Metric threshold graders

All 25 eval.yaml include metric graders as baseline monitors:

| Grader | Baseline | Per-eval overrides |
|---|---|---|
| `token-budget` | **500K tokens** (input + output) | `semantic-model-consumption` (1M, DAX exploration), `sqldw-operations-cli` (800K, DMV exploration) |
| `error-count` | **0** (zero-tolerance) | -- |
| `wall-time` | **5m** | Spark evals: up to 7m (Livy session startup overhead) |
| `turn-count` | **20** | `semantic-model-consumption`: 30 |
| `tool-call-count` | **25** | `semantic-model-consumption`: 40 |

These are free/static graders (no LLM cost). Where a stimulus' in-flight
`constraints.max_duration` kill-switch fires **before** the wall-time grader
could (i.e. the grader threshold exceeded the constraint and was therefore dead
code), the wall-time grader was lowered to match `max_duration` so the grader
stays meaningful. Overrides reflect legitimate workload weight, not threshold
noise. The baselines establish a floor for Phase B+2 dashboarding and
degradation detection; workload teams can adjust per-skill overrides via their
own PRs (Phase D handoff).

## Adding Vally coverage to a new skill (Layer 0)

Start every new skill with Layer 0 coverage. This catches routing failures, crashes, missing expected output, and runaway cost before adding deeper tool-call or program verifiers. **Layer 0 is the starting point, not the finish line:** the structure gate (`tests/test_eval_yaml_structure.py`) HARD-FAILS a new eval whose stims lack Layer 1 `tool-calls` + Layer 2 `program` graders (see "New evals (and new stims) must ship L1 + L2 from day 1" below; offline / codegen stims opt out with `l1l2_exempt`).

```yaml
name: my-skill-layer0-eval
description: Layer 0 eval for my-skill.
tags: { type: integration, skill: my-skill }
environment: { skills: [../../../skills/my-skill] }
config: { runs: 5, timeout: "15m", executor: copilot-sdk, model: claude-sonnet-4.6 }
scoring: { threshold: 1.0 }
stimuli:
  - name: "Core behavior"
    prompt: |
      Ask for the core behavior using {{WORKSPACE}}.
    tags: { type: integration, tier: smoke, cost: llm, area: my-area }
    constraints: { max_turns: 15, max_tokens: 150000, max_duration: 5m }
    graders:
      - { type: skill-invocation, config: { required: [my-skill], disallowed: [sibling-skill] } }
      - { type: completed }
      - { type: output-not-matches, config: { pattern: "(?i)fatal error|unhandled exception|stack trace" } }
      - { type: output-matches, config: { pattern: "(?i)expected term" } }
      - { type: token-budget, config: { max: 500000 } }
      - { type: error-count, config: { max: 0 } }
      - { type: wall-time, config: { max: "5m" } }
      - { type: turn-count, config: { max: 20 } }
      - { type: tool-call-count, config: { max: 25 } }
```

The `constraints` and metric-grader numbers above are pilot defaults inherited from `eventhouse-authoring-cli`. Watch your eval's real runtime over the first 1-2 weeks and tune them down to fit your skill's profile. That calibration belongs in the workload team's PR, not in the cutover PR.

### Exempting a stim from an L0 grader (`l0_exempt`)

`tests/test_eval_yaml_structure.py` enforces a minimum L0 grader set on every
stim. A stim that legitimately cannot satisfy one of those graders opts out
with a per-stim `l0_exempt` list. **`l0_exempt` lists GRADER-TYPE names, not
skill names.**

```yaml
stimuli:
  - name: "Routing negative - sibling prompt must NOT route here"
    prompt: |
      A prompt that should route to a sibling skill, not this one.
    # This stim asserts a NON-event (a sibling was not invoked) and has no
    # testable positive output of its own, so it opts out of the
    # positive-output-assertion requirement.
    l0_exempt: [positive-output-assertion]
    graders:
      - { type: skill-invocation, config: { disallowed: [this-skill] } }
      - { type: completed }
      # ... remaining L0 graders ...
```

Allowed `l0_exempt` names (any other value fails CI with a clear message):

- The required L0 grader types: `skill-invocation`, `completed`,
  `output-not-matches`, `wall-time`, `token-budget`, `tool-call-count`,
  `turn-count`, `error-count`.
- The synthetic key `positive-output-assertion` (the "at least one
  `output-matches` or `output-contains`" requirement).

When to use it:

- **`positive-output-assertion`** -- routing-negative stims that only confirm a
  sibling skill was NOT invoked, or stims whose positive assertions live
  entirely in Layer 1 `tool-calls` + Layer 2 `program` graders.
- **`skill-invocation`** -- multi-skill agent-composition stims where no single
  required skill exists.

Keep the list tight: each exemption removes real coverage, so add a comment
explaining why. A typo (e.g. `skill-invokation`) or a skill name placed here is
rejected by `test_l0_exempt_values_are_known_grader_names` so it cannot
silently mask a gap. Every `l0_exempt` usage is also surfaced as a stderr WARN
(`test_warn_when_l0_exempt_used`) listing the stim and exempted graders, so
exemptions stay visible on every run and a reviewer can challenge any that
shouldn't be there.

### Declaring an MCP server your skill needs

If your skill drives Fabric through an MCP server (e.g. `powerbi-modeling-mcp`), declare it in `environment.mcpServers` of your `eval.yaml` -- Vally launches it for the trial via the Copilot SDK, no plugin install required for CI.

```yaml
environment:
  skills: [../../../skills/my-skill]
  mcpServers:
    powerbi-modeling-mcp:
      type: stdio
      command: npx
      args: ['-y', '@microsoft/powerbi-modeling-mcp@latest', '--start']
      timeout: 2m
```

Rules:

- Commit the **interactive** form (no `--authmode=serviceprincipal`, no `env:` block). Local-dev runs use browser auth.
- In CI, `tests/run-vally-eval.ps1` rewrites the staged copy to append `--authmode=serviceprincipal --skipconfirmation` plus the SP cert `env` block when `$env:CI_MCP_OVERLAY -eq 'true'`. Committed YAML is untouched.
- If the MCP server is already in `plugins/<plugin>/.github/plugin/plugin.json#mcpServers` and your skill is bundled in that plugin, `tests/test_eval_yaml_mcp_servers.py` will enforce the declaration in CI (`powerbi-modeling-mcp` is the only server in the enforcement scope today).
- Verify locally: `pwsh tests/run-vally-eval.ps1 -DryRun -EvalDirs "<your-skill>"` writes the staged YAML under `tests/.vally-staging/` -- inspect it to confirm the MCP block shape.

## How to write a verifier for your skill

The Layer 0 evals above answer "did the agent *say* the right things?" (output
matches, skill routing, budgets). They cannot answer "did the agent *actually
build the right thing in Fabric?*" -- an agent can narrate a flawless
`.create-merge table` and leave nothing behind. The **layered verifier** pattern
closes that gap with two cheap, deterministic layers you add per stimulus. Use
the `eventhouse-authoring-cli` pilot as the worked example.

### The two layers

- **Layer 1 -- `tool-calls`** (built-in Vally grader, lives in your `eval.yaml`):
  regex assertions on the agent's tool calls. Proves the agent *attempted* the
  right operations and avoided wrong-shaped ones. Offline, no creds.
- **Layer 2 -- `program`** (a PowerShell verifier under
  `tests/evals/_graders/<skill>/`): independently inspects the real Fabric side
  and proves the artefact exists with the right shape. Catches "right-looking
  call, wrong/absent result".

Ship them **together**. A `tool-calls: required` matcher with no paired `program`
verifier is an attack surface: narrate success + emit the right command =
green. The contract and helper reference live in
[`_graders/README.md`](_graders/README.md).

### Step 1 -- add Layer 1 to your `eval.yaml`

Ground every regex in a **real** production trajectory (a smoke run's tool
calls), never an invented command. For the pilot:

> **Use the canonical 6-alternation `name` regex below.** Real GitHub
> Copilot trajectories invoke shell-style tools under 6 names:
> `bash`, `powershell`, `shell`, `run_in_terminal`, `functions.bash`,
> and `functions.powershell`. Hand-rolling a shorter list (for example
> `bash|pwsh|powershell` as some early drafts had) silently
> un-asserts the 3 missing modes, so a Layer 1 grader can show green
> even when the agent really did make the wrong call under
> `run_in_terminal`. Keep the list byte-identical across every
> `required` and `disallowed` matcher in the same `tool-calls` block;
> the eval YAML supports `&shell_tool` / `*shell_tool` anchors to
> avoid drift between sites.

```yaml
- type: tool-calls
  config:
    required:
      - name: &shell_tool "(?i)^(bash|powershell|shell|run_in_terminal|functions\\.bash|functions\\.powershell)$"
        command: "az rest .*--method get .*/v1/workspaces"
      - name: *shell_tool
        command: "az rest .*--method get .*/v1/workspaces/[^/]+/kqlDatabases"
      - name: *shell_tool
        command: "/v1/rest/mgmt"            # assert the endpoint; Layer 2 proves the artefact
    disallowed:
      - name: *shell_tool
        command: "/v2/"                     # no public Fabric v2 surface today
      - name: *shell_tool
        command: "executeQuery"             # SQL construct, not KQL
```

Tips: the `name` regex matches the tool name and the `command` regex matches the
command string. Keep the `required` matcher on the *endpoint* (robust to
phrasing) and let Layer 2 assert the *correctness* (right name, right schema).

### Step 2 -- add the Layer 2 program grader to the same stimulus

```yaml
- type: program
  name: verify-<artefact>
  config:
    program: pwsh
    args:
      - -NoProfile
      - -ExecutionPolicy
      - Bypass
      - -File
      - tests/evals/_graders/<skill>/verify-<artefact>.ps1
    timeout: 60s
    env:
      FABRIC_WORKSPACE_ID: "{{WORKSPACE_ID}}"   # templated by run-vally-eval.ps1
      EXPECTED_TABLE: "<your-table-name>"        # your test inputs here
```

`{{WORKSPACE_ID}}` is substituted at staging by `tests/run-vally-eval.ps1` to
the GUID of the ephemeral workspace the smoke run provisioned. The verifier
fails fast if the env var is still the literal placeholder.

### Step 3 -- write the verifier

Put it at `tests/evals/_graders/<skill>/verify-<artefact>.ps1`. Import the shared
module and follow the read-only / never-swallow-to-pass / bounded-polling rules
in [`_graders/README.md`](_graders/README.md):

```powershell
Import-Module (Join-Path $PSScriptRoot '..' | Join-Path -ChildPath '_lib' | Join-Path -ChildPath 'Vally.Grader.psm1') -Force
$null = Read-EvaluateGraderInput
$token = Get-FabricAccessToken -Resource 'https://api.fabric.microsoft.com'
# ... resolve the artefact via az rest, inspect it read-only ...
Write-GraderResult -Name 'verify-<artefact>' -Passed $ok -Score (if($ok){1}else{0}) -Evidence $why -Metadata $meta
```

`Write-GraderResult` **throws** if you try to pass with empty (or whitespace-only)
evidence -- a minor sanity check, NOT a security guarantee. The verifier's
top-level `catch` must emit `passed: false` -- a verifier that errors FAILS,
it never passes.

### Step 4 -- smoke-test your verifier locally before pushing

The live smoke shard is the source of truth for verifier correctness. Before
opening a PR, run the verifier yourself against a real workspace:

```pwsh
# 1. Log in as a user (or service principal) that can read your workspace.
az login                                    # or: az login --service-principal ...

# 2. Find a recent ephemeral workspace's GUID from a previous smoke run.
#    Either: pull from a CI run's `_setup` output:
#      gh run download <run-id> --repo gim-home/skills-for-fabric --pattern '*shard0*'
#      grep FABRIC_WORKSPACE_ID <downloaded>/vally-run.log
#    Or: list workspaces and pick one you provisioned recently:
#      az rest --method get --resource https://api.fabric.microsoft.com --url https://api.fabric.microsoft.com/v1/workspaces --only-show-errors --query "value[?starts_with(displayName, 'skills-for-fabric-test')].{name:displayName, id:id}"

# 3. Run the verifier with the env vars Vally would have set:
$env:EVALUATE_GRADER_INPUT = '{"trajectory":{"id":"local"}}'
$env:FABRIC_WORKSPACE_ID = '<the-guid-you-found-above>'
$env:VALLY_GRADER_POLL_DEADLINE_SECONDS = '60'
$env:VALLY_GRADER_POLL_INTERVAL_SECONDS = '2'
# any other env vars your eval.yaml's program.config.env sets
pwsh -File tests/evals/_graders/<skill>/verify-<artefact>.ps1
```

You should see a single line of `GraderResult` JSON. Try it against a workspace
where the artefact exists (should `passed:true`) and one where it doesn't
(should `passed:false` with a clear evidence string). That round-trip catches
most authoring bugs before CI ever sees them.

The shared `_lib/Vally.Grader.psm1` helper IS Pester-tested (`_lib/Vally.Grader.tests.ps1`,
runs via the `grader-unit-tests` CI job). Per-skill verifiers are deliberately
NOT Pester-tested -- mock-based unit tests at the Fabric boundary drift from
real Fabric and produce false confidence; the live smoke shard is the
authoritative check.

### Step 5 -- deterministic graders are merge-gating from day 1

The new `tool-calls` and `program` graders contribute to the stimulus's
aggregate score exactly like the legacy graders. If they fail, the eval's
score drops; if the score drops below the eval threshold (1.0 in the
current cutover policy), the stim fails and the workflow fails. There is
no separate "report-only" bucket -- if a deterministic check exists, it
counts.

This means: ground your `tool-calls` regex in a REAL recent smoke trajectory
(not invented strings), and smoke-test your verifier locally per Step 4
before pushing. A broken verifier will block PR merge, not just produce a
warning.

### New evals (and new stims) must ship L1 + L2 from day 1 (the grandfather baseline)

`tests/test_eval_yaml_structure.py` HARD-FAILS any stim that does not carry at
least one Layer 1 `tool-calls` grader AND at least one Layer 2 `program` grader,
unless that stim is a named legacy stim in the `L1L2_GRANDFATHERED` baseline.
The `eventhouse-authoring-cli` eval is the worked pilot: copy its shape.

`L1L2_GRANDFATHERED` is a per-stim baseline (`dir -> frozen set of stim names`)
naming the specific stims that predate this requirement; those named stims emit
a stderr WARN instead of failing, until their owning team adds the two
deterministic layers. The rule is keyed per stim, on purpose:

- A stim in a directory **not** in the baseline (any brand-new eval) must meet
  the L1+L2 bar immediately, or CI fails.
- A **brand-new stim added to a grandfathered eval** must also meet the bar --
  it is not in the baseline, so adding a new test case to a legacy eval cannot
  silently skip the deterministic layers. Do **not** add the new stim name to
  the baseline to dodge this.
- A named legacy stim only warns -- but the baseline is meant to **shrink,
  never grow**. When you add `tool-calls` + `program` to a grandfathered stim,
  delete its name from `L1L2_GRANDFATHERED` (the stale-entry test fails until
  you do) so the gate locks the layers in going forward.
- An **offline / codegen / pure-advice stim** that builds nothing in Fabric
  (the agent writes SQL or reviews a query and never calls a tool or creates an
  artefact) has nothing for L1/L2 to assert. Opt it out with `l1l2_exempt`
  (below) instead of grandfathering it or bolting on meaningless graders.

### Exempting a stim from L1+L2 (`l1l2_exempt`)

Some stims legitimately produce **no Fabric side effect** -- the agent writes
SQL, reviews a query, or returns advice as text, building nothing for a Layer 2
`program` verifier to inspect and firing no tool call for a Layer 1 `tool-calls`
matcher to assert. Forcing L1/L2 graders onto such a stim only tests prose
dressed up as behaviour. Opt out instead, with a per-stim `l1l2_exempt` reason:

```yaml
stimuli:
  - name: "Review a query for incremental-refresh readiness"
    # Offline analysis: the agent reviews the provided SQL and returns advice,
    # building nothing in Fabric, so there is no tool call or artefact to assert.
    l1l2_exempt: "Offline review of provided SQL text; nothing is created in Fabric to verify (no tool call, no artefact)."
    prompt: |
      Review this materialized lake view query for incremental refresh ...
    graders:
      - { type: skill-invocation, config: { required: [my-skill] } }
      - { type: completed }
      # ... remaining L0 graders ...
```

Rules:

- `l1l2_exempt` is a **single non-empty reason string** (not a list). The reason
  is mandatory: a present-but-empty value fails CI via
  `test_l1l2_exempt_requires_reason`.
- It exempts the stim from **both** Layer 1 and Layer 2. Use it only when the
  task genuinely has no Fabric side effect; prefer reshaping the stim into an
  execution task (so L1+L2 are real) when that fits.
- Every usage is surfaced as a stderr WARN (`test_warn_when_l1l2_exempt_used`)
  listing the stim and reason, so opt-outs stay visible on every run and a
  reviewer can challenge any that should instead carry real graders.

## When your CI run goes red -- triage runbook

The workflow's "Grader failures" table in the summarise job lists every
failed grader with its evidence. If you need to dig deeper than that:

1. **Download the artifact bundle** from the failed run:
   ```
   gh run download <run-id> --repo gim-home/skills-for-fabric --pattern 'vally-smoke-results-*-shard*'
   ```
   Each shard becomes a directory.

2. **Find the shard that ran your eval.** Search shard logs for your eval
   directory name:
   ```
   Select-String -Path */vally-run.log -Pattern '<your-eval-dir>'
   ```

3. **Open the structured results file.** Inside the matching shard:
   `vally-output/<timestamp>/results.jsonl`. Each line is one stim trial:
   ```jsonc
   {
     "gradeResult": {
       "details": [
         { "name": "tool-calls-...", "passed": false, "evidence": "..." },
         { "name": "verify-...", "passed": false, "evidence": "..." }
       ]
     },
     "trajectory": {
       "events": [
         { "type": "tool_call", "data": { "toolName": "powershell", "arguments": { "command": "az rest ..." } } },
         { "type": "tool_result", "data": { "result": "..." } }
       ]
     }
   }
   ```
   The `trajectory.events` array is the agent's full transcript -- every
   `az rest` call it made, every result, every assistant message. The
   `gradeResult.details[].evidence` is what each grader concluded and why.

4. **Match the failure pattern to a fix:**

   | Evidence says | Most likely cause | Fix |
   |---|---|---|
   | `Table 'X' not found ... Tables actually present: [Y]` | Agent named the artefact differently than your verifier expects | Tighten the prompt to specify the exact name, OR loosen the verifier if any name is acceptable |
   | `required tools were not called: ... command pattern ...` | Your `tool-calls` required regex doesn't match what the agent actually ran | Open the trajectory `events[]`, find the relevant `tool_call.data.arguments.command`, ground your regex on the real command shape (not an invented one) |
   | `disallowed tools were called: ... command pattern ...` | Your `tool-calls` disallowed regex is too greedy and matches a legitimate call | Anchor the disallowed regex to the specific host / path / verb you actually want to block |
   | `Verifier failed: az rest ... failed (exit code 4xx)` | Workspace gone, auth issue, or wrong URL shape | Check the workflow's `Provision ephemeral test environment` step; check `az account show` in your local repro; verify the URL against MS Learn |
   | `Verifier failed: Polling aborted on permanent failure` | The verifier hit a 4xx / JSON parse error inside its polling loop and bailed | Same as the row above; the evidence string includes the underlying error |
   | `EBUSY: resource busy or locked` in shard log | Vally 0.5.0 Windows cleanup race (known) | The workflow's exit-swap heuristic should treat this as a warning. If the workflow still failed, file an issue. |

5. **Reproduce locally** with the same workspace if possible (see Step 4
   above). Most failures reproduce in 1-2 minutes against the original
   ephemeral workspace before it's torn down by the next workflow run.

## What's NOT in this PR (sequenced for follow-ups)

- **B+2**: `.github/workflows/fabric-vally-nightly.yml` (cron + Node 22 + SP login + dashboard)
- **Phase C**: LLM-judge graders (`type: prompt` + `rubric:`)
- **Phase D**: workload-team ownership (quality_checker rule + CODEOWNERS)

## References

- Vally CLI on npm: https://www.npmjs.com/package/@microsoft/vally-cli
- Built-in grader catalog: https://literate-engine-r3wnl4v.pages.github.io/reference/graders/
- Trajectory format reference: https://literate-engine-r3wnl4v.pages.github.io/reference/trajectory/
- Reference PR: microsoft/GitHub-Copilot-for-Azure#2235
- PR #199 (pilot): https://github.com/gim-home/skills-for-fabric/pull/199
