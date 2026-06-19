# Legacy smoke break-glass runbook

Vally is the primary PR and nightly harness. Use legacy smoke only when Vally is unavailable or when you need to cross-check a suspected Vally false negative against the old `tests/tests.json` substring grader.

## When to use

- Vally outage or CLI regression blocks validation for more than a few hours.
- A Vally failure looks like a grader false negative and needs old-harness comparison.
- A release manager explicitly asks for legacy smoke evidence during incident response.

Do not add new coverage here. New stims go to `tests/evals/<skill>/eval.yaml`.

## Manual GitHub Actions invocation

```powershell
gh workflow run fabric-smoke-ephemeral.yml --repo gim-home/skills-for-fabric --ref <branch> --field test-names=all
```

For one legacy smoke stim, replace `all` with the `tests/tests.json` name.

## Local invocation

```powershell
.\tests\run-smoke-tests.ps1 -tenant "<current-tenant>.onmicrosoft.com" -skipLogin -testName "<legacy-smoke-name>"
```

## 15-minute revert recipe

If the cutover must be backed out, revert the merge commit that introduced the trigger changes. This restores `pull_request_target` / `schedule` on the legacy smoke workflows without touching Vally eval specs, docs, or migrated coverage.

```powershell
# Identify the cutover merge commit (PR title contains "vally" + "cutover").
git log --oneline --merges --grep "vally.*cutover" main | head -n 5

# Revert just the workflow files from that merge (preserves Vally evals + docs).
git checkout -b revert/vally-cutover-triggers main
git checkout <cutover-merge-sha>^ -- `
  .github\workflows\fabric-smoke-ephemeral.yml `
  .github\workflows\fabric-smoke-pr-touched.yml
git commit -m "revert: restore legacy smoke auto-fire triggers (Vally outage break-glass)"
git push -u origin revert/vally-cutover-triggers
```

Open a PR from `revert/vally-cutover-triggers` -> `main`. The `tests/test_workflow_triggers.py` guard will (intentionally) fail because the forbidden triggers are back; bypass via the standard branch-protection break-glass review path, do not admin-merge.

If you also need to roll back the Vally workflow, revert the whole merge: `git revert -m 1 <cutover-merge-sha>`.
