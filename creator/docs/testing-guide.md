# Testing Guide

This guide explains how to test skills-for-fabric before submitting changes.

## Test Suite Overview

| Test | File | Purpose |
|------|------|---------|
| Quality Checker | `.github/workflows/quality_checker.py` | Structural and semantic validation |
| Skill Catalog Sync | `.github/scripts/generate_skill_catalog.py --check` | Verifies `docs/skill-catalog.md` matches checked-in skill frontmatter |
| Coverage Gap Report | `tests/coverage_gap_report.py` | Advisory audit of legacy smoke / individual / combined eval coverage |
| Coverage Enforcement | `tests/coverage_enforcement.py` | Enforced new-skill ownership + legacy smoke / eval policy with governed allow-missing entries |
| Vally | `tests/evals/<skill>/eval.yaml` | Primary PR and nightly behavioral harness for skills |
| Semantic Tests | `tests/test_semantic.py` | Naming, similarity, description quality |
| Routing Tests | `tests/test_skill_routing.py` | Prompts route to correct skills |

> Current automated tests target `skills/` content. Agent definitions should still be validated manually for routing boundaries, reference integrity, and delegation clarity.

### Vally Test Principles

Vally (`tests/evals/<skill>/eval.yaml`) is the primary PR and nightly behavioral harness. Add new skill coverage there, not in legacy `tests/tests.json`. The canonical source is [`../tests/evals/README.md`](../tests/evals/README.md).

1. **Load the target skill explicitly.** Use `environment.skills: [../../../skills/<skill>]` so the eval measures the intended skill boundary.
2. **Start with Layer 0.** Include `skill-invocation`, `completed`, crash-pattern rejection, one output assertion grounded in expected behavior, and budget graders.
3. **Calibrate budgets after merge.** The cutover defaults are inherited from the eventhouse pilot; workload teams should tune them during the first 1-2 weeks of real runs.

### Legacy manual-only smoke break-glass

Legacy smoke (`tests/tests.json` and `tests/run-smoke-tests.ps1`) is frozen for manual break-glass only. Use it only to cross-check a suspected Vally false negative or during a Vally outage. See [`legacy-smoke-break-glass.md`](legacy-smoke-break-glass.md).

### Marking legacy smoke tests as flaky

Only maintain existing legacy `tests/tests.json` entries. If one is known to fail, keep the existing `flaky.githubIssue` shape so the manual-only break-glass runner can distinguish known failures from new regressions.

### Per-Plugin Testing

Both the legacy manual-only smoke runner (`tests/testFabricSkills.ps1`) and the full-eval runner
(`tests/run-full-tests.ps1`) honor an opt-in `plugin:` selector that decides
which `@<plugin>@fabric-collection` is installed for that test or plan. Tests /
plans without the selector default to `fabric-skills` (the catch-all bundle),
preserving the historical single-plugin behaviour.

#### How the selector is declared

| Surface | File | Where the selector goes |
|---|---|---|
| Legacy manual-only smoke | `tests/tests.json` | `"plugin": "<name>"` (or `["a","b"]`) sibling to `name`, `area`, `prompt`. Omit = `fabric-skills`. |
| Full-eval | `tests/full-eval-tests/plan/**/eval-*.md` | YAML front-matter: `---\nplugin: <name>\n---` at top of the plan. Omit = `fabric-skills`. |
| Vally | `tests/evals/<test>/eval.yaml` | NOT a plugin install; Vally uses `environment.skills: [<path>...]` to load skills by source path. See the Vally note at the bottom of this section. |

#### How the runners use the selector

- **Legacy manual-only smoke** groups tests by `plugin`, then for each group: uninstall every other
  known plugin (canonical list = each per-plugin manifest's `name` field at
  `plugins/<name>/.github/plugin/plugin.json`), sweep any orphaned
  stdio MCP processes that match the previous plugin's install path, and
  install the group's plugin once. Tests in the group then run against that
  single-plugin agent session.
- **Full-eval** groups plans by `plugin` (front-matter `plugin: <name>`,
  default `fabric-skills`) and runs each plugin group sequentially. Per group,
  `Sync-PluginInstallation` uninstalls + sweeps the previously-installed
  plugin (if different) and installs the new one, then PR #256's parallel
  chain orchestrator dispatches every plan in the group with up to
  `--throttle-limit` chains running concurrently. Day-1 (every plan defaults
  to `fabric-skills`) collapses to a single plugin group whose behaviour is
  identical to the pre-grouping single-install path. After all groups finish,
  the post-processing phase (merged summary + regression analysis) is
  re-pinned to `fabric-skills` to keep dashboard semantics stable.

#### Probes / end-to-end verification

The per-plugin path was empirically verified end-to-end via short-lived
"probe" tests + plans (one per plugin lane) that asked the agent to invoke
its plugin's marker skill, enumerate every `AVAILABLE-SKILL: <name>` and
`AVAILABLE-MCP: <name>` it could see, and emit a sentinel. The per-plan
log + legacy smoke `_output.txt` gave a positive "I can only see X" assertion
per lane. Those probes were stripped from the tree once the SWITCH path
was proven; the runner code (`Get-EvalPlanPlugin`, `Sync-PluginInstallation`,
the smoke shard loop in `testFabricSkills.ps1`) stays live for real
consumers. To re-prove the SWITCH path against a new plugin, drop a probe
legacy manual-only test into `tests/tests.json` with `"plugin": "<your-plugin>"` and / or a
probe plan under `tests/full-eval-tests/plan/03-individual-skills/` with
`plugin: <your-plugin>` front-matter.

#### Dispatching targeted manual runs (legacy smoke + full-eval)

```powershell
# Legacy manual-only smoke break-glass -- one specific test or a comma-separated list
gh workflow run fabric-smoke-ephemeral.yml `
  --repo gim-home/skills-for-fabric `
  --ref <your-branch> `
  --field test-names=<test-name>[,<test-name>...] `
  --field throttle-limit=2 `
  --field timeout-seconds=900

# Full-eval -- targeted plans via PlanFilter (wildcard list; comma/semicolon/whitespace separated)
gh workflow run fabric-full-eval-ephemeral.yml `
  --repo gim-home/skills-for-fabric `
  --ref <your-branch> `
  --field plan-filter='eval-<your-pattern>-*.md' `
  --field skip-warehouse=true `
  --field skip-lakehouse=true `
  --field skip-cleanup=true
```

Notes:
- `skip-*` switches are only safe when every selected plan makes ZERO Fabric API
  calls (short probe / smoke-tier plans qualify; most real eval plans do NOT).
  Set them only for probe or smoke-tier plans, never for a full schedule.
- The full-eval `plan-filter` input matches against filename via PowerShell
  `-like`. Multiple patterns are OR-ed. Empty / unset = every discovered plan
  runs (the historical cron behaviour).

#### Vally migration note

Vally (`tests/evals/<test>/eval.yaml`, configured via `.vally.yaml`) does not
install Copilot plugins. Each `eval.yaml` declares its own skills via
`environment.skills: [../../../skills/<name>]` and uses the `copilot-sdk`
executor directly. Per-test isolation is intrinsic to that model.

The per-plugin infrastructure in this repo still supports the Vally direction
in two concrete ways:

1. Per-plugin manifests at `plugins/<name>/.github/plugin/plugin.json` are the
   canonical source of "which skills belong to which plugin"; any tests.json
   -> eval.yaml translator (today or future) can read the mapping via
   `build/plugin_index.py::load_plugin_index()`.
2. The `plugin:` selector on smoke entries and the `plugin:` front-matter on
   full-eval plans give that translator a clean per-test plugin tag without
   re-inventing it for each surface.

## Quick Start

### Install Dependencies

```bash
pip install PyYAML requests pytest
```

### Run All Checks

```bash
# Quality checker
python .github/workflows/quality_checker.py

# Coverage gap report
python tests/coverage_gap_report.py

# Coverage enforcement
python tests/coverage_enforcement.py --base-ref origin/main

# Fast tests
python -m pytest tests/test_semantic.py -q
python -m unittest tests/test_coverage_gap_report.py tests/test_coverage_enforcement.py tests/test_skill_ownership_manifest.py -v
```

> `docs/skill-catalog.md` is refreshed manually by maintainers; do not regenerate it in feature PRs.

`tests/coverage_gap_report.py` remains advisory. `tests/coverage_enforcement.py` is the
blocking policy check for new-skill ownership / coverage requirements and for keeping
the current allow-missing baseline governed in `.github/coverage-policy.yml`.

## Contributor pre-merge validation

For a skill PR, these are the current checks contributors should understand before merge:

> **Prerequisite for smoke + full-eval rows below**: run `az login --tenant <ephemeral>.onmicrosoft.com --allow-no-subscriptions` in your terminal FIRST. Smoke / full-eval wrappers spawn a Python subprocess that calls Azure APIs; if you have no live `az` session they block waiting for a browser pop the CLI can't surface. Then pass `-skipLogin` to the wrappers below. See [ephemeral-tenant-smoke.md](ephemeral-tenant-smoke.md) for the current tenant + capacity ID.

| Validation | Command / Entry Point | What it tells you | When to use it |
|------------|------------------------|-------------------|----------------|
| Quality checker | `python .github/workflows/quality_checker.py` | Structural, semantic, and reference validation | Every skill PR |
| Coverage asset audit | `python tests/coverage_gap_report.py` | Whether the repo still sees your skill as missing smoke / individual eval assets | Every skill PR |
| Coverage enforcement | `python tests/coverage_enforcement.py --base-ref origin/main` | Whether new skills satisfy ownership / smoke / eval policy and current gaps are governed | Every skill PR |
| Ownership manifest validation | `python -m unittest tests/test_skill_ownership_manifest.py -v` | Whether `.github/skill-ownership.yml` is in sync | When ownership manifest changes |
| Python tests | `pytest tests/ -v` or targeted test files | Repo test coverage for changed tests / helpers | When tests change |
| Legacy manual-only smoke harness (single test, no env setup) | `pwsh -File tests/testFabricSkills.ps1 -testName "<smoke-test-name>" -directoryPath C:\temp\fabric-smoke` | Break-glass execution of a legacy smoke scenario from legacy `tests/tests.json` against a workspace you already provisioned | Manual-only fallback |
| Legacy manual-only smoke break-glass runner | `pwsh -File tests/run-smoke-tests.ps1 [-tenant <tenant>] [-spLogin <app-id> -spCertPath <pem>]` | Logs in, provisions a fresh workspace, runs legacy smoke tests, and cleans up on full pass | Manual-only fallback; see [ephemeral-tenant-smoke.md](ephemeral-tenant-smoke.md) |
| Full-eval, all plans | `pwsh -File tests/run-full-tests.ps1 [-tenant <tenant>] -TestFolder C:\temp\fabric-full-eval` | Runs the full eval suite (~30 plans) | Full-suite validation |
| Full-eval, one skill | `pwsh -File tests/run-full-tests.ps1 -PlanFilter "eval-<skill>" -skipLogin -SkipWarehouse -SkipLakehouse -SkipCleanup -capacityId "<cap>" -tenant "<tenant>"` | Runs only the named plan(s); unknown names hard-fail before any provisioning | Workload-owner validating their own skill |

Important distinctions:

- `tests/coverage_gap_report.py` is a **report script**, not a behavioral test runner.
- `tests/coverage_enforcement.py` is the **blocking policy check** for new-skill coverage expectations.
- `tests/testFabricSkills.ps1` is the legacy **manual-only single-test smoke break-glass entry point** (no env setup).
- `tests/run-smoke-tests.ps1` is the legacy **manual-only end-to-end smoke break-glass runner** (provisions env, runs tests, cleans up).
- `tests/run-full-tests.ps1` is the current **manual full-eval suite runner**.

### Running locally against the shared ephemeral tenant

The shared tenant from `aka.ms/fabrictenants` is the path nightly CI uses today. Microsoft contributors with shared-tenant access can run Vally and full-eval locally; legacy manual-only smoke break-glass is documented separately. See [ephemeral-tenant-smoke.md](ephemeral-tenant-smoke.md) for the full setup (cert installation, SP provisioning, secrets). Quick reference once setup is done:

```powershell
# Option 1 -- as the AdminUser01 you logged in as (browser CBA)
./tests/run-vally-eval.ps1 -Workspace "skills-for-fabric-test-YYYYMMDD" -Skill "<skill>" -Runs 1

# Option 2 -- as a service principal (matches the CI flow exactly)
./tests/run-full-tests.ps1 -PlanFilter "eval-<skill>" -TestFolder C:\temp\fabric-full-eval
```

Replace `<current-tenant>` with the rotation name shown on `aka.ms/fabrictenants` (rotates every ~90 days; see [tenant-rotation-runbook.md](tenant-rotation-runbook.md)).

### PR-touched gates (CI auto-runs)

| Gate | Trigger | What runs |
|---|---|---|
| Vally | Any PR that touches skills, common test infrastructure, or `tests/evals/`. | Affected Vally eval specs or suites from `tests/evals/`. |
| Full-eval | Any PR that touches `skills/`, `common/`, `plugins/`, `tests/full-eval-tests/`, or `build/build_plugins.py`. Same approval model as Vally. Skill-only changes narrow to matching plan(s); plugin-folder changes (any path under `plugins/<name>/`) narrow to the skills listed in that plugin's manifest at HEAD; changes to shared infrastructure (`common/`, `tests/full-eval-tests/`, `build/build_plugins.py`) escalate to all plans. | Only the matching plan(s), OR all plans on infra change. PRs whose touched skills have no eval coverage post a skipped sticky and consume no eval time. |

Vally and full-eval gates auto-cancel in-flight runs on new pushes (per-PR concurrency group, `cancel-in-progress: true`) and post a sticky comment with the per-plan result. Nightly cron (21:00 UTC) runs every plan regardless of touched-files. A nightly orphan-workspace sweeper deletes any `FullEval-*` workspace older than 24h, bounding the stranded-resource risk from mid-step cancellation.

PR automation now runs a fast validation workflow that covers:

- `quality_checker.py`
- `tests/test_semantic.py`
- `tests/test_coverage_gap_report.py`
- `tests/test_coverage_enforcement.py`
- `tests/test_skill_ownership_manifest.py`
- `tests/coverage_enforcement.py`

> `docs/skill-catalog.md` is refreshed manually by maintainers and is not a PR-time gate.

The workflow also posts one sticky PR summary comment with changed-skill ownership /
Vally / individual / combined coverage status.

For new skills or material behavior changes, CI auto-runs the PR-touched Vally and
PR-touched full-eval (only the plans matching changed skills) and posts the result to
the sticky comment. You do NOT need to paste those results in the PR body. Contributors
should still record any **manual** evidence CI cannot produce (trigger-overlap pair scores for
multi-skill PRs, baseline no-skill comparison for new skills, tenant-specific repro)
as a short note in the PR description. Legacy manual-only smoke break-glass results
should be recorded only when that fallback path is intentionally used.

## Quality Checker

The quality checker (`quality_checker.py`) validates every skill in `skills/`:

### What It Checks

| Category | Checks |
|----------|--------|
| **Structure** | YAML frontmatter, name/description fields, update notice |
| **Content** | Must/Prefer/Avoid sections, examples, code block tags |
| **Semantics** | Trigger uniqueness, description similarity (Jaccard) |
| **References** | Cross-reference link validation |
| **Quality** | Description starts with action verb, mentions technologies |

### Running Locally

```bash
python .github/workflows/quality_checker.py
```

### Sample Output

```
📋 skills-for-fabric QUALITY CHECK
==================================================

📂 Scanning: check-updates
📂 Scanning: spark-authoring-cli
📂 Scanning: sqldw-authoring-cli

🔄 Running cross-skill analysis...

==================================================
📊 QUALITY CHECK SUMMARY
Files scanned: 5
Critical issues: 0
Warnings: 2

⚠️  Semantically ambiguous triggers: 2

   | Trigger Phrase | Matches These Skills                    | Ambiguity |
   |----------------|----------------------------------------|-----------|
   | run sql        | spark-consumption-cli, sqldw-consumption-cli | 2 skills |

✅ RESULT: PASSED with 2 warning(s)
📄 Report saved to: quality-report.json
```

### Understanding Results

| Status | Meaning | Action |
|--------|---------|--------|
| `PASSED` | All checks passed | Ready to submit |
| `PASSED with warnings` | Non-blocking issues found | Review and consider fixing |
| `CRITICAL` | Blocking issues found | Must fix before merge |

## Pytest Tests

### Test Categories

```bash
# Run all tests
pytest tests/ -v

# Run only semantic tests
pytest tests/test_semantic.py -v

# Run only routing tests
pytest tests/test_skill_routing.py -v

# Run by marker
pytest tests/ -v -m semantic
pytest tests/ -v -m routing
```

### Semantic Tests (`test_semantic.py`)

Validates skill semantics:

| Test Class | Purpose |
|------------|---------|
| `TestTriggerUniqueness` | No duplicate triggers, ambiguous triggers have qualifiers |
| `TestDescriptionSimilarity` | Jaccard similarity < 30% between skills |
| `TestNamingConventions` | Names follow `{endpoint}-{authoring|consumption|monitoring}-cli` pattern |
| `TestDescriptionQuality` | Descriptions start with action verbs, mention technologies |

### Routing Tests (`test_skill_routing.py`)

Validates that user prompts route to the correct skill:

```python
@pytest.mark.parametrize("prompt", [
    "show me all tables in my warehouse",
    "query my warehouse to get top 10 products",
    "run a T-SQL query against Fabric",
])
def test_routes_to_sql_consumption(self, prompt, all_skills):
    """Prompt should route to sqldw-consumption-cli."""
    skill, score = route_prompt(prompt, all_skills)
    assert skill == "sqldw-consumption-cli"
```

### Adding New Routing Tests

When adding a new skill, add routing tests:

```python
# tests/test_skill_routing.py

@pytest.mark.routing
class TestMyNewSkillRouting:
    """Test prompts that should route to my-new-skill."""
    
    @pytest.mark.parametrize("prompt", [
        "prompt that should trigger my skill",
        "another triggering prompt",
    ])
    def test_routes_to_my_skill(self, prompt, all_skills):
        """Prompt should route to my-new-skill."""
        skill, score = route_prompt(prompt, all_skills)
        assert skill == "my-new-skill"
```

## Pre-commit Hook

### Installation

```bash
# Windows (PowerShell)
Copy-Item .github\hooks\pre-commit .git\hooks\pre-commit

# macOS/Linux
cp .github/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

### What It Does

Before each commit, the hook:

1. Runs the quality checker on changed skill files
2. Blocks commit if critical issues are found
3. Shows warnings but allows commit

### Bypassing (Not Recommended)

```bash
git commit --no-verify -m "message"
```

## CI/CD Workflow

### Pull Request Checks

When you push a PR that changes skills or the validation pipeline:

1. **Skill PR Validation** (`quality-check.yml`)
   - Runs quality checker, semantic/unit tests, ownership validation, and coverage enforcement
   - Posts one sticky PR validation summary comment
   - Uploads `quality-report.json` and `coverage-enforcement.json` as artifacts

2. **Security Audit** (`security-audit.yml`)
   - Scans for secrets and sensitive data
   - Validates security guidelines
   - Uploads `security-report.json` as an artifact without adding extra PR comment noise

3. **Daily Coverage Gap Report** (`daily-coverage-gap-report.yml`)
   - Runs `tests/coverage_gap_report.py` on a daily schedule
   - Uploads `coverage-gap-report.json` as a workflow artifact
   - Can also be triggered manually with `workflow_dispatch`

> Fast PR automation still does **not** execute manual smoke or full-eval workflows for
> you. Record the relevant manual evidence in the PR whenever the change needs it.

### Workflow Triggers

```yaml
on:
  pull_request:
    branches: [ main, master ]
    paths:
      - 'skills/**/*.md'
      - '.github/coverage-policy.yml'
      - '.github/skill-ownership.yml'
      - '.github/workflows/*.py'
      - '.github/workflows/*.yml'
      - 'tests/**/*.md'
      - 'tests/**/*.py'
      - 'tests/tests.json' # legacy manual-only smoke break-glass
  push:
    branches: [ main, master ]
    paths:
      - 'skills/**/*.md'
      - '.github/coverage-policy.yml'
      - '.github/skill-ownership.yml'
      - '.github/workflows/*.py'
      - '.github/workflows/*.yml'
      - 'tests/**/*.md'
      - 'tests/**/*.py'
      - 'tests/tests.json' # legacy manual-only smoke break-glass
```

Scheduled coverage reporting is separate:

```yaml
on:
  schedule:
    - cron: '0 12 * * *'
  workflow_dispatch:
```

## Testing Locally with Copilot CLI

### Symlink Your Skill

```bash
# Windows (PowerShell as Admin)
New-Item -ItemType SymbolicLink `
  -Path "$env:USERPROFILE\.copilot\skills\my-new-skill" `
  -Target ".\skills\my-new-skill"

# macOS/Linux
ln -s $(pwd)/skills/my-new-skill ~/.copilot/skills/my-new-skill
```

### Verify Loading

Start a new Copilot CLI session:

```
/skills list
```

Your skill should appear in the list.

### Test Prompts

Try prompts that should trigger your skill and verify correct routing.

## Test File Structure

```
tests/
├── conftest.py              # Shared fixtures (all_skills, etc.)
├── README.md                # Test documentation
├── requirements-dev.txt     # Test dependencies
├── test_semantic.py         # Semantic validation tests
└── test_skill_routing.py    # Routing tests
```

### Shared Fixtures (`conftest.py`)

```python
@pytest.fixture
def all_skills():
    """Load all skills from skills/ folder."""
    skills = {}
    skills_dir = Path(__file__).parent.parent / "skills"
    
    for skill_folder in skills_dir.iterdir():
        skill_md = skill_folder / "SKILL.md"
        if skill_md.exists():
            # Parse frontmatter and add to skills dict
            ...
    
    return skills
```

## Debugging Test Failures

### Quality Checker Failures

1. Read the specific error message
2. Check `quality-report.json` for details
3. Common fixes:
   - Add missing frontmatter fields
   - Add update notice
   - Tag code blocks with language
   - Fix broken cross-references

### Routing Test Failures

```
AssertionError: Expected sqldw-consumption-cli but got spark-consumption-cli
```

1. Check your skill's triggers in the description
2. Add more specific trigger phrases
3. Ensure triggers don't overlap with other skills

### Semantic Test Failures

```
Skills with similarity >= 30%: [{'skills': ('skill-a', 'skill-b'), 'similarity': 35.2}]
```

1. Differentiate descriptions between the two skills
2. Use more specific terminology
3. Clarify distinct use cases

## Best Practices

1. **Run tests before every commit** — Use the pre-commit hook
2. **Add routing tests for new skills** — Verify correct routing
3. **Check quality report** — Review `quality-report.json` for details
4. **Test locally first** — Don't rely only on CI/CD
5. **Keep tests updated** — When adding triggers, add corresponding tests

## Next Steps

- [Quality Requirements](quality-requirements.md) — What the tests check
- [Skill Authoring Guide](skill-authoring-guide.md) — How to create skills
