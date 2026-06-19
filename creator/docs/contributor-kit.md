# Contributor Kit

This guide is the practical checklist for adding or changing skills in `skills-for-fabric`.
Use it together with:

- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [Skill Authoring Guide](skill-authoring-guide.md)
- [Testing Guide](testing-guide.md)

## Required artifacts for skill work

Every contributor-facing skill change should consider these five artifacts:

1. **Skill content**
   - `skills/{name}/SKILL.md`
   - Any `references/` or `resources/` files needed by the skill

2. **Ownership metadata**
   - `.github/skill-ownership.yml`
   - Every checked-in skill must have one ownership entry

3. **Coverage policy metadata**
   - `.github/coverage-policy.yml`
   - Update this only when you add an explicit coverage exemption or pay down tracked coverage debt

4. **Behavior coverage (Vally eval)**
   - A Vally eval at `tests/evals/<name>/eval.yaml` is **required** for new skills -- it is the behavior surface CI enforces
   - A `tests/tests.json` smoke entry is **advisory only** (a fast break-glass check); it is not required

5. **Eval coverage**
   - An individual eval plan for the skill
   - A combined eval update only when the change participates in a documented paired or handoff workflow

## Ownership manifest

The ownership manifest lives at:

```text
.github/skill-ownership.yml
```

The manifest is the repository source of truth for **who owns what inside this repo**.
Its `owningTeam` values are repository ownership buckets. They do not need to match GitHub
teams or Azure AD groups one-to-one.

As of schemaVersion 2, every team that owns at least one skill MUST declare a
`contact` block with `name`, `email`, and `github` fields. The weekly smoke
health ritual (see [weekly-smoke-health.md](weekly-smoke-health.md)) routes
flake/fail findings to that contact, so missing or stale contact info silently
degrades who gets pinged about regressions in your area.

### Example entry

```yaml
schemaVersion: 2

teams:
  sqldw:
    displayName: SQL Data Warehouse
    scope: Warehouse and SQL endpoint authoring/consumption skills
    contact:
      name: Mariya Ali
      email: mariyaali@microsoft.com
      github: mariyaali_microsoft

skills:
  sqldw-authoring-cli:
    owningTeam: sqldw
    area: authoring
```

### When to update it

Update `.github/skill-ownership.yml` when you:

- add a new skill (CI gate: `tests/coverage_enforcement.py` fails the PR otherwise)
- rename a skill
- move a skill between ownership buckets
- split one skill into multiple skills
- change a team's primary contact (name / email / GitHub handle)
- add a new team (must include a `contact` block before any skill references it)

## Coverage expectations

The enforced coverage policy lives at:

```text
.github/coverage-policy.yml
```

Use it to track the current repo baseline of allowed-missing coverage and any explicit
coverage exemptions. New skills should not add `status: debt`; either add the missing
asset or record a justified `status: exempt`.

### Vally eval coverage

Add or update a Vally eval at `tests/evals/<name>/eval.yaml` for new or changed skill behavior.
This is the **required** behavior surface for new skills (`requireVallyEvalForNewSkills: true` in
`.github/coverage-policy.yml`); see `tests/evals/README.md`.

### Smoke coverage (advisory)

Add or update smoke coverage only when a fast break-glass sanity check is appropriate.
Smoke is **advisory, not required** -- the Vally eval is the enforced behavior surface.

### Individual eval coverage

Add or update an individual eval when the skill's core behavior changes or when a new skill is introduced.

### Combined eval coverage

Combined eval is **not automatic for every skill**.
Add or update combined eval only when the skill participates in a real multi-skill handoff or paired workflow that the repo intends to support.

## Commands to run locally

```bash
python .github/workflows/quality_checker.py
python tests/coverage_gap_report.py
python tests/coverage_enforcement.py --base-ref origin/main
python -m unittest tests/test_skill_ownership_manifest.py -v
pytest tests/ -v
```

> `docs/skill-catalog.md` is refreshed manually by maintainers; do not regenerate in feature PRs.

> **If you also plan to run smoke / full-eval locally**: `az login --tenant <ephemeral>.onmicrosoft.com --allow-no-subscriptions` first, in your terminal. Smoke and full-eval wrappers cannot trigger an interactive browser login from inside Copilot CLI. Pass `-skipLogin` to the wrappers once authenticated. See [`.github/skills/pre-pr-check`](../.github/skills/pre-pr-check/SKILL.md) Step 2.0 for the full sequence.

## Optional: manual checks worth mentioning in the PR

CI runs the heavy validators automatically on every PR: quality lint, semantic / unit tests, ownership validation, coverage enforcement, **PR-touched Vally eval** (only the evals matching changed skills), and **PR-touched full-eval** (only the plans matching changed skills). The sticky `Skill PR Validation` comment summarizes the result.

You do NOT need to paste Vally / eval results in the PR description -- CI captures all of that. Briefly mention any of these that apply:

- **Trigger-overlap pair scores** for multi-skill PRs (CI flags pairs > 30% but does not show the pair-wise table).
- **Baseline (no-skills) comparison** for new skills -- a paragraph noting how output differs without the skill loaded.
- **Tenant-specific repro** or anything else CI cannot capture -- screenshots, manual eval against a specific workspace state, etc.

For local pre-PR validation use [`.github/skills/pre-pr-check`](../.github/skills/pre-pr-check/SKILL.md) (covers the runtime checks CI runs) and [`.github/skills/pre-pr-review`](../.github/skills/pre-pr-review/SKILL.md) (cross-verified self-review).

## Suggested PR shape

For a new skill or a meaningful behavior change, a good PR usually includes:

1. skill content updates
2. ownership manifest update
3. coverage policy update if you add an explicit exemption or remove tracked debt
4. Vally eval update (`tests/evals/<name>/eval.yaml`) -- required for new skills
5. individual eval update
6. combined eval update if the workflow is paired/handoff-based
7. smoke coverage update only if a fast break-glass check is appropriate (advisory)
8. `.changeset/PR<number>-<slug>.md` fragment describing the change
9. documentation updates if contributor expectations changed

## Reviewer checklist

Reviewers should be able to answer:

- Does the ownership manifest include this skill?
- Is the owning team bucket reasonable?
- If the skill is intentionally missing Vally or eval coverage, is that reflected in `.github/coverage-policy.yml` with a clear reason?
- Is a Vally eval (`tests/evals/<name>/eval.yaml`) present for a new skill, or a justified exemption recorded?
- Is individual eval coverage present for the changed behavior?
- Is smoke coverage present only where a fast break-glass check is appropriate (advisory)?
- If the PR changes a paired workflow, was combined eval considered?
- Does the PR include a `.changeset/` fragment naming the skill?
