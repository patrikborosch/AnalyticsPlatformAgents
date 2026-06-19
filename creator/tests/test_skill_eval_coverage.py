"""Static, full-tree coverage guards for the Vally eval surface.

Two independent guards live here:

1. Every ``skills/<skill>/`` directory must have a corresponding
   ``tests/evals/<skill>/eval.yaml`` UNLESS the skill is in an explicit,
   commented exemption set. This is the *static* complement to the
   *diff-based* enforcement in ``tests/test_coverage_enforcement.py`` (which
   exercises ``coverage_enforcement.py`` against synthetic git histories and
   fails a PR that ADDS a new skill without a Vally eval). The diff-based
   check only sees changed files on a branch; this static check walks the
   whole checked-in tree every run, so it also catches drift that no single
   diff introduces -- e.g. an eval dir deleted out from under an existing
   skill, an exemption that has gone stale, or a skill that arrived through a
   path the diff gate did not evaluate. Both are intentionally kept: the
   diff-based one gives rich PR-time messaging, this one gives a tree-wide
   invariant.

2. ``tests/tests.json`` (the legacy smoke catalog) is frozen: it must keep
   its deprecation banner and must not grow. New behaviour goes to
   ``tests/evals/<skill>/eval.yaml``, not to the smoke catalog.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
EVALS_DIR = REPO_ROOT / "tests" / "evals"
COVERAGE_POLICY = REPO_ROOT / ".github" / "coverage-policy.yml"
TESTS_JSON = REPO_ROOT / "tests" / "tests.json"

# Skills that legitimately ship WITHOUT a tests/evals/<skill>/eval.yaml. This
# mirrors EVAL_LESS_SKILLS in tests/test_eval_yaml_mcp_servers.py (which only
# needs the single utility skill) and is the static-test analogue of the
# allowMissing.vallyEval list in .github/coverage-policy.yml that the
# diff-based enforcement consults. Each entry carries a justification so a
# reviewer can see WHY it is uncovered; the set is asserted to stay in lockstep
# with coverage-policy.yml by test_exemptions_match_coverage_policy.
#
# Adding a new skill here is a deliberate decision that must be justified --
# the default expectation is that a new skill ships a Vally eval.
EXEMPT_FROM_VALLY_EVAL: set[str] = {
    # Utility skill for marketplace version checks; no Fabric workspace or
    # runtime behaviour to evaluate with a stimulus.
    "check-updates",
    # Cross-platform migration guidance skill; no stable Fabric runtime action
    # suitable for a Vally stimulus.
    "databricks-migration",
    # Cross-platform migration guidance skill; no stable Fabric runtime action
    # suitable for a Vally stimulus.
    "hdinsight-migration",
    # End-to-end orchestration pattern better covered by combined-eval
    # scenarios than a single-skill Vally eval.
    "e2e-medallion-architecture",
    # Existing authoring skill without a dedicated Vally eval yet (tracked as
    # debt in coverage-policy.yml; expected to gain an eval over time).
    "sqldw-authoring-cli",
}

# tests/tests.json is the legacy smoke catalog. It is frozen at the cutover
# baseline: no NEW entries. This count is the number of array elements at the
# freeze point (including the leading _deprecated banner element). The freeze
# test asserts the live count does not EXCEED this, so removals are allowed but
# additions are blocked.
FROZEN_SMOKE_CASE_COUNT = 59

# A stable substring of the tests.json deprecation banner. The banner lives in
# the leading element's `_deprecated` key (and is mirrored into its `prompt`).
DEPRECATION_BANNER_SUBSTR = (
    "DEPRECATED: this catalog feeds the legacy smoke break-glass path only"
)


def _skill_dirs() -> list[str]:
    if not SKILLS_DIR.is_dir():
        return []
    return sorted(
        p.name
        for p in SKILLS_DIR.iterdir()
        if p.is_dir() and (p / "SKILL.md").is_file()
    )


def _has_eval(skill_name: str) -> bool:
    return (EVALS_DIR / skill_name / "eval.yaml").is_file()


class SkillEvalCoverageTests(unittest.TestCase):
    maxDiff = None

    def test_every_skill_has_eval_or_explicit_exemption(self) -> None:
        """Fail when a skill has neither a Vally eval nor an explicit
        exemption. This is what catches "a new skill was added without an
        eval" tree-wide; the diff-based test_new_skill_requires_vally_eval in
        tests/test_coverage_enforcement.py catches the same class of problem
        at PR time from the git diff.
        """
        skills = _skill_dirs()
        self.assertTrue(skills, f"no skills discovered under {SKILLS_DIR}")
        uncovered = [
            name
            for name in skills
            if not _has_eval(name) and name not in EXEMPT_FROM_VALLY_EVAL
        ]
        self.assertEqual(
            uncovered,
            [],
            "The following skill(s) have no tests/evals/<skill>/eval.yaml and "
            f"are not in the explicit exemption set: {uncovered}. Add a Vally "
            "eval (see tests/evals/README.md and the eventhouse-authoring-cli "
            "pilot), or -- only if the skill genuinely has no testable Fabric "
            "behaviour -- add it to EXEMPT_FROM_VALLY_EVAL here AND to "
            "allowMissing.vallyEval in .github/coverage-policy.yml with a "
            "justification.",
        )

    def test_no_stale_exemptions(self) -> None:
        """An exemption must name a real skill that genuinely lacks an eval.
        If an exempt skill gains an eval, the exemption is stale and must be
        removed so the gap cannot silently reappear later.
        """
        skills = set(_skill_dirs())
        missing_skill = sorted(EXEMPT_FROM_VALLY_EVAL - skills)
        self.assertEqual(
            missing_skill,
            [],
            f"EXEMPT_FROM_VALLY_EVAL names skill(s) that do not exist under "
            f"{SKILLS_DIR}: {missing_skill}. Remove the stale entries.",
        )
        now_covered = sorted(
            name for name in EXEMPT_FROM_VALLY_EVAL if _has_eval(name)
        )
        self.assertEqual(
            now_covered,
            [],
            "The following exempt skill(s) now HAVE a Vally eval: "
            f"{now_covered}. Remove them from EXEMPT_FROM_VALLY_EVAL (and from "
            "allowMissing.vallyEval in .github/coverage-policy.yml) so the "
            "exemption cannot mask a future regression.",
        )

    def test_exemptions_match_coverage_policy(self) -> None:
        """The static exemption set must mirror allowMissing.vallyEval in
        .github/coverage-policy.yml -- the single source of truth that the
        diff-based enforcement also consults -- so the two cannot drift apart.
        """
        self.assertTrue(
            COVERAGE_POLICY.is_file(),
            f"coverage policy not found at {COVERAGE_POLICY}",
        )
        policy = yaml.safe_load(COVERAGE_POLICY.read_text(encoding="utf-8"))
        vally = ((policy or {}).get("allowMissing") or {}).get("vallyEval") or {}
        policy_keys = set(vally.keys())
        self.assertEqual(
            EXEMPT_FROM_VALLY_EVAL,
            policy_keys,
            "EXEMPT_FROM_VALLY_EVAL is out of sync with "
            "allowMissing.vallyEval in .github/coverage-policy.yml.\n"
            f"  only in test:   {sorted(EXEMPT_FROM_VALLY_EVAL - policy_keys)}\n"
            f"  only in policy: {sorted(policy_keys - EXEMPT_FROM_VALLY_EVAL)}\n"
            "Update both so the static guard and the diff-based enforcement "
            "agree on which skills are uncovered.",
        )


class SmokeCatalogFrozenTests(unittest.TestCase):
    maxDiff = None

    def _load_cases(self) -> list:
        self.assertTrue(TESTS_JSON.is_file(), f"missing {TESTS_JSON}")
        cases = json.loads(TESTS_JSON.read_text(encoding="utf-8"))
        self.assertIsInstance(cases, list, "tests.json must be a JSON array")
        return cases

    def test_tests_json_carries_deprecation_banner(self) -> None:
        """The legacy smoke catalog must keep its deprecation banner so it is
        unmistakably break-glass-only.
        """
        cases = self._load_cases()
        banners = [
            c.get("_deprecated", "")
            for c in cases
            if isinstance(c, dict) and "_deprecated" in c
        ]
        self.assertTrue(
            any(DEPRECATION_BANNER_SUBSTR in b for b in banners),
            "tests/tests.json must carry its deprecation banner entry "
            f"containing {DEPRECATION_BANNER_SUBSTR!r}. Do not remove it -- "
            "the catalog is frozen break-glass; new stims go to "
            "tests/evals/<skill>/eval.yaml.",
        )

    def test_tests_json_entry_count_not_grown(self) -> None:
        """tests.json is frozen: its entry count must not exceed the cutover
        baseline. A new smoke entry (count > baseline) fails here and points
        the author at the Vally eval surface instead.
        """
        cases = self._load_cases()
        self.assertLessEqual(
            len(cases),
            FROZEN_SMOKE_CASE_COUNT,
            f"tests/tests.json has grown to {len(cases)} entries (frozen "
            f"baseline is {FROZEN_SMOKE_CASE_COUNT}). The legacy smoke catalog "
            "is frozen; do not add new entries. Add a stim to "
            "tests/evals/<skill>/eval.yaml instead (see tests/evals/README.md). "
            "If you intentionally removed entries and need to re-baseline, "
            "lower FROZEN_SMOKE_CASE_COUNT in this test to the new count.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
