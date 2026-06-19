## Description

<!-- Provide a clear and concise description of your changes -->

## Type of Change

<!-- Check all that apply -->

- [ ] New skill
- [ ] Skill enhancement/update
- [ ] Bug fix
- [ ] Documentation update
- [ ] CI/CD improvement
- [ ] Security fix

## Checklist

### General
- [ ] I have read [CONTRIBUTING.md](../CONTRIBUTING.md)
- [ ] My code follows the project's coding standards
- [ ] I have updated relevant documentation
- [ ] I have added tests for my changes
- [ ] I added a `.changeset/` fragment for my changelog entry (see [`.changeset/README.md`](../.changeset/README.md))
- [ ] I updated `.github/skill-ownership.yml` for any added, renamed, or moved skill
- [ ] I updated `.github/coverage-policy.yml` if I added a new coverage exemption or paid down tracked coverage debt
- [ ] I added or updated Vally eval coverage (`tests/evals/<skill>/eval.yaml`) for new or changed skill behavior
- [ ] I added or updated individual eval coverage for new or changed skill behavior
- [ ] I evaluated whether combined eval coverage is needed for paired or handoff workflows
- [ ] I added or updated smoke coverage only if a fast break-glass sanity check is appropriate (advisory; not required)
- [ ] **Ran [`.github/skills/pre-pr-check`](../.github/skills/pre-pr-check/SKILL.md) locally and it passed** (quality lint + Vally eval + filtered full-eval for changed skills)
- [ ] **Ran [`.github/skills/pre-pr-review`](../.github/skills/pre-pr-review/SKILL.md) as self-review and addressed its findings** before requesting human review

### New Skill (If applicable)
<!--
  Complete this checklist if you're adding a brand-new skill. For enhancements
  to existing skills, skip this section.

  This is a soft gate -- items here are not auto-enforced; they're a reminder of
  the manifest / ownership / coverage / docs surface that a new skill touches.
  CI will enforce a subset (skill-ownership, coverage-policy) via the
  `.github/workflows/quality-check.yml` workflow (which invokes
  `tests/coverage_enforcement.py`).
-->

- [ ] `SKILL.md` description follows the rubric: starts with an action verb, mentions specific technologies (SDKs, languages, tools), distinguishes from similar skills, stays under the **1023-character hard limit** (warning at 900) per `docs/quality-requirements.md`
- [ ] Use folded YAML (`description: >`) for multi-line descriptions per repo convention (see existing skills like `dataflows-authoring-cli` or `databricks-migration`)
- [ ] Description includes the standard "Use when the user wants to: (1) …, (2) …, (3) …" enumeration and a "Triggers: …" comma-separated list inline within the description text (not as separate blocks)
- [ ] Triggers don't overlap with neighboring skills (cross-checked with similar skills in the same area)
- [ ] Added entry to `.github/skill-ownership.yml` with named owner email
- [ ] Added entry to `.github/coverage-policy.yml` if the skill is intentionally exempt from Vally eval / individual eval at creation time
- [ ] Added a Vally eval at `tests/evals/<name>/eval.yaml` (the required behavior surface for new skills; see `tests/evals/README.md`)
- [ ] Added individual eval plan under `tests/full-eval-tests/plan/03-individual-skills/`
- [ ] Evaluated whether a combined eval plan is appropriate (paired/handoff workflows under `tests/full-eval-tests/plan/04-combined-skills/`)
- [ ] (Optional) Added a smoke entry to `tests/tests.json` only if a fast break-glass check is appropriate -- smoke is advisory, not required
- [ ] `docs/skill-catalog.md` is refreshed manually by maintainers (do not regenerate in feature PRs -- it causes conflicts when multiple skill PRs are open)
- [ ] Skill stays under the 15,000-token budget per `docs/quality-requirements.md`

### Security (Required)
- [ ] No hardcoded secrets, API keys, or credentials
- [ ] I have reviewed [docs/RAI_THREAT_MODEL.md](../docs/compliance/RAI_THREAT_MODEL.md)
- [ ] Input validation implemented for external data
- [ ] Output redaction for sensitive information
- [ ] No arbitrary code execution vulnerabilities
- [ ] Tool parameters validated and sanitized

### RAI/Prompt Security (If applicable)
- [ ] Skill uses clear delimiters for user content vs instructions
- [ ] No patterns that reveal system prompts
- [ ] No patterns that bypass security controls
- [ ] Added red-team test cases for prompt injection
- [ ] Tested against common injection attacks
- [ ] Tool calls require appropriate user confirmation

### Threat Model Impact

<!-- Assess impact on each threat category -->

| Threat Category | Impact | Mitigation |
|----------------|--------|------------|
| Prompt Injection | None / Low / Medium / High | <!-- Describe mitigation --> |
| Sensitive Info Disclosure | None / Low / Medium / High | <!-- Describe mitigation --> |
| Excessive Agency | None / Low / Medium / High | <!-- Describe mitigation --> |
| Supply Chain | None / Low / Medium / High | <!-- Describe mitigation --> |
| Data Exfiltration | None / Low / Medium / High | <!-- Describe mitigation --> |

## Testing

<!-- CI auto-runs on every push:
     - Skill PR Validation: quality lint, semantic / unit tests, ownership, coverage
     - PR-touched Smoke: smoke tests for the skills you changed
     - PR-touched Full-Eval: eval plans for the skills you changed
     Results land as sticky PR comments. No need to paste smoke / eval output manually.

     For local pre-push validation, use `.github/skills/pre-pr-check` (runtime) and
     `.github/skills/pre-pr-review` (cross-verified self-review). -->

### Manual checks worth mentioning (optional)
<!-- Only if your PR adds a NEW skill or touches MULTIPLE skills, briefly note: -->
<!-- - **Trigger-overlap scores** (multi-skill PRs): paste any pair-wise overlap above 30% reported by
       `python .github/workflows/quality_checker.py` if any pair is borderline.
     - **Baseline no-skills delta** (new skills): document the delta between with-skill
       and without-skill runs so reviewers can see the skill's value.
     - **Tenant-specific repro**: anything you couldn't put in CI. -->

### Automated Testing
<!-- List any new unit / semantic tests you added. -->

### Red-Team Testing (for skills)
<!-- Describe prompt injection attempts tested. -->

## Dependencies

<!-- List any new dependencies added and why they're needed -->

## Breaking Changes

<!-- List any breaking changes and migration guide -->

## Screenshots/Examples

<!-- Optional supporting screenshots or example outputs. -->

## Additional Context

<!-- Any additional information reviewers should know -->

---

By submitting this pull request, I confirm that:
- My contribution is made under the project's license
- I have the right to submit this contribution
- I understand maintainers will review for security and quality
