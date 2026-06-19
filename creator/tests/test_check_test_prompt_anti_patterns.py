"""Unit tests for ``.github/scripts/check_test_prompt_anti_patterns.py``.

Run via:
    python -m unittest tests/test_check_test_prompt_anti_patterns.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / ".github" / "scripts"
sys.path.insert(0, str(SCRIPT_PATH))

import check_test_prompt_anti_patterns as checker  # noqa: E402


class FindViolationsTests(unittest.TestCase):
    """Verify the regex + cross-reference logic.

    Each test exercises one phrasing variation that the rule must catch
    (or one false-positive that the rule must NOT catch).
    """

    SKILL_FOLDERS = {
        "activator-authoring-cli",
        "activator-consumption-cli",
        "dataflows-authoring-cli",
        "spark-operations-cli",
    }

    def assert_no_violations(self, prompt: str) -> None:
        tests_json = [{"name": "tc", "prompt": prompt}]
        violations = checker.find_violations(tests_json, self.SKILL_FOLDERS)
        self.assertEqual(violations, [], f"unexpected violation for prompt: {prompt!r}")

    def assert_one_violation(self, prompt: str, expected_skill: str) -> None:
        tests_json = [{"name": "tc", "prompt": prompt}]
        violations = checker.find_violations(tests_json, self.SKILL_FOLDERS)
        self.assertEqual(len(violations), 1, f"expected exactly one violation for: {prompt!r}")
        self.assertEqual(violations[0]["matched_skill"], expected_skill)

    # ---- positive cases (must be flagged) ----

    def test_using_the_X_skill_is_flagged(self):
        self.assert_one_violation(
            "Using the activator-authoring-cli skill, create an Activator named X.",
            "activator-authoring-cli",
        )

    def test_use_the_X_skill_is_flagged(self):
        self.assert_one_violation(
            "Use the dataflows-authoring-cli skill to create a Dataflow named X.",
            "dataflows-authoring-cli",
        )

    def test_via_the_X_skill_is_flagged(self):
        self.assert_one_violation(
            "via the activator-consumption-cli skill list all activators",
            "activator-consumption-cli",
        )

    def test_invoke_the_X_skill_is_flagged(self):
        self.assert_one_violation(
            "Invoke the spark-operations-cli skill to diagnose the failed notebook.",
            "spark-operations-cli",
        )

    def test_case_insensitive_match(self):
        self.assert_one_violation(
            "USING THE Activator-Authoring-CLI SKILL, do X.",
            "activator-authoring-cli",
        )

    def test_no_the_article_still_matches(self):
        self.assert_one_violation(
            "Use activator-authoring-cli skill to create an Activator.",
            "activator-authoring-cli",
        )

    # ---- negative cases (must NOT be flagged) ----

    def test_natural_user_prompt_passes(self):
        self.assert_no_violations("Create an Activator named eval_smoke_activator in {{WORKSPACE}}.")

    def test_meta_mention_in_skill_metadata_field_passes(self):
        # The rule applies only to `prompt`, but the function should also tolerate
        # incidental mentions in prompts that don't fit the verb pattern.
        self.assert_no_violations("The activator-authoring-cli skill is one of many available skills.")

    def test_non_existent_skill_name_not_flagged(self):
        # Skill not in SKILL_FOLDERS -- could be a typo or deprecated reference;
        # leave to other validators to catch.
        self.assert_no_violations("Using the nonexistent-thing-cli skill, do X.")

    def test_other_suffix_not_flagged(self):
        # The pattern is anchored to canonical suffixes; arbitrary "-cli" doesn't qualify.
        self.assert_no_violations("Using the random-cli skill, do X.")

    def test_prompt_field_missing(self):
        violations = checker.find_violations([{"name": "tc"}], self.SKILL_FOLDERS)
        self.assertEqual(violations, [])

    def test_prompt_field_empty(self):
        violations = checker.find_violations([{"name": "tc", "prompt": ""}], self.SKILL_FOLDERS)
        self.assertEqual(violations, [])

    # ---- multiple-entry scenarios ----

    def test_one_violation_among_many_clean_entries(self):
        tests_json = [
            {"name": "good-a", "prompt": "Create an Activator in {{WORKSPACE}}."},
            {"name": "good-b", "prompt": "List dataflows in workspace X."},
            {"name": "bad", "prompt": "Using the activator-authoring-cli skill, do X."},
            {"name": "good-c", "prompt": "Refresh the powerbi model."},
        ]
        violations = checker.find_violations(tests_json, self.SKILL_FOLDERS)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["name"], "bad")

    def test_multiple_anti_patterns_in_one_prompt_each_reported(self):
        prompt = (
            "Using the activator-authoring-cli skill, then via the dataflows-authoring-cli skill, do X."
        )
        tests_json = [{"name": "tc", "prompt": prompt}]
        violations = checker.find_violations(tests_json, self.SKILL_FOLDERS)
        self.assertEqual(len(violations), 2)
        self.assertEqual({v["matched_skill"] for v in violations},
                         {"activator-authoring-cli", "dataflows-authoring-cli"})


class FormatViolationTests(unittest.TestCase):
    def test_format_includes_test_name_and_phrase(self):
        v = {
            "name": "my-test",
            "prompt": "Using the activator-authoring-cli skill, do X.",
            "matched_phrase": "Using the activator-authoring-cli skill",
            "matched_skill": "activator-authoring-cli",
            "position": 0,
        }
        formatted = checker.format_violation(v)
        self.assertIn("my-test", formatted)
        self.assertIn("activator-authoring-cli", formatted)
        self.assertIn("Using the activator-authoring-cli skill", formatted)


if __name__ == "__main__":
    unittest.main(verbosity=2)
