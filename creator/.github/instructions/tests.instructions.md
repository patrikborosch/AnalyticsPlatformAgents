---
applyTo: "tests/**"
---

# Test Coverage Review Guidelines

## Purpose

Review `tests/**`. CI (`coverage_enforcement.py`, `test_semantic.py`, `test_skill_ownership_manifest.py`) already enforces eval-plan presence and ownership-manifest validity; do not re-flag those. Focus on coverage gaps below and cite CONTRIBUTING.md per finding.

## Eval plan minimum (5 cases)

For a new or renamed skill, `tests/full-eval-tests/plan/03-individual-skills/eval-<skill>.md` MUST contain at least 5 cases. Each case needs: Case ID, Prompt, Expected Result, and Pass Criteria. Flag fewer than 5 cases or missing fields.

## Baseline (no-skill) validation

Required for NEW skills only. The PR description should mention a without-skill vs. with-skill delta proving the skill adds value (note in prose or as a short bullet -- CI captures the structured eval). NOT required for renames or expansions of existing skills. Do not flag baseline missing on a rename.

## Rename consistency

When a skill is renamed, every old-name reference embedded in eval artifacts MUST be updated:

- Case ID prefixes (e.g. `SD-01` -> `SO-01`)
- Fixture / sample-data names (e.g. `spark_diagnostics_failing_notebook` -> `spark_operations_failing_notebook`)
- References in Data Setup, Pass Criteria, and Data Teardown sections
- File names of supporting artifacts under `tests/full-eval-tests/data/` if any

Flag eval-plan files whose Case ID prefix or fixture name still embeds the old skill name.

## Routing parity for new triggers

Whenever `SKILL.md` adds or removes trigger phrases (YAML `description`, "When to use", or "Triggers"), the test surface MUST match:

- `tests/test_routing.py` -- the per-skill prompt class or `*_PROMPTS` constant should cover each new trigger surface.
- `tests/evals/<skill>/eval.yaml` -- add a Vally stimulus when behavior coverage is practical; see `tests/evals/README.md` for the Layer 0 pattern.

If new triggers lack routing or Vally coverage, routing regressions will not be caught nightly. Name the uncovered trigger and propose a concrete prompt.

## Vally and legacy smoke policy

Vally evals are the primary testing surface. See `tests/evals/README.md` for grader policy, threshold semantics, and the Layer 0/1/2 onboarding walkthrough. New or changed skill behavior belongs in `tests/evals/<skill>/eval.yaml`; legacy `tests/tests.json` is manual break-glass only.

For intentional legacy `tests/tests.json` maintenance, require `prompt` and `expectedSkills`. Flag entries whose `expectedSkills` folder is missing, whose `prompt` is empty / placeholder, or whose behavior change lacks matching Vally coverage. Flag any PR that re-adds `schedule`, `pull_request`, or `pull_request_target` to `.github/workflows/fabric-smoke-ephemeral.yml` or `.github/workflows/fabric-smoke-pr-touched.yml`.

## Prompt anti-patterns

Prompts in legacy `tests/tests.json` MUST read like natural user requests. They MUST NOT name a skill folder with an invocation verb; CI enforces `(using|use|via|through|invoke)\s+(?:the\s+)?<skill-name>\s+skill` (see `.github/scripts/check_test_prompt_anti_patterns.py`).

WRONG: `Using the activator-authoring-cli skill, create an Activator named X.`

Why: naming the skill short-circuits routing verification, so regressions in `description` / triggers go unnoticed. Fix the skill description or disambiguation triggers, not the prompt.

## test_routing.py rename leftovers

When a skill is renamed, ensure:

- The class is renamed (e.g. `TestSparkDiagnosticsRouting` -> `TestSparkOperationsRouting`).
- Constants embedding the old name are renamed.
- Imports / fixture references match the new name.

Flag any class, constant, or fixture name still embedding the old skill name.
