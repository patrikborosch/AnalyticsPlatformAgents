# Unit tests for .github/scripts/weekly-flake-report.py.
#
# Focus areas:
#   - classify_cause() output taxonomy + flag-flag interactions
#   - trailing-Y flag-removal logic, including '-' placeholder handling
#   - resolve_test_team() routing via tests.json::expectedSkills + manifest
#   - load_ownership() returns the manifest + skill_to_team map

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "weekly-flake-report.py"


def load_script_module():
    """Load weekly-flake-report.py as a module so we can call its functions."""
    spec = importlib.util.spec_from_file_location("weekly_flake_report", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["weekly_flake_report"] = module
    spec.loader.exec_module(module)
    return module


V2_MANIFEST_YAML = """
schemaVersion: 2
teams:
  platform:
    displayName: Platform
    scope: Shared
    contact:
      name: Matan
      email: matan@example.com
      github: matan_example
  dataflows:
    displayName: Dataflows
    scope: Dataflows skills
    contact:
      name: Shani
      email: shani@example.com
      github: shani_example
  catalog:
    displayName: OneLake Catalog
    scope: Catalog
    contact:
      name: Nadav
      email: nadav@example.com
      github: nadav_example
skills:
  dataflows-consumption-cli:
    owningTeam: dataflows
    area: consumption
  search-consumption-cli:
    owningTeam: catalog
    area: consumption
  check-updates:
    owningTeam: platform
    area: utility
""".strip()


class ClassifyCauseTests(unittest.TestCase):
    def setUp(self):
        self.m = load_script_module()
        self.flaky_entry = {"flaky": {"githubIssue": "https://github.com/x/y/issues/1"}}
        self.no_flag_entry = {"name": "any"}

    def test_all_pass_returns_stable(self):
        self.assertEqual(self.m.classify_cause("YYYYY", None), "stable")

    def test_all_dash_returns_no_data(self):
        self.assertIn("no-data", self.m.classify_cause("-----", None))

    def test_all_F_with_flag_is_known_flaky(self):
        result = self.m.classify_cause("FFFFF", self.flaky_entry)
        self.assertIn("known-flaky", result)

    def test_all_N_without_flag_is_consistently_broken(self):
        result = self.m.classify_cause("NNNNN", self.no_flag_entry)
        self.assertIn("consistently broken", result)
        self.assertNotIn("all F", result)
        self.assertNotIn("consistently F", result)

    def test_all_N_with_flag_describes_N_not_F(self):
        result = self.m.classify_cause("NNNNN", self.flaky_entry)
        self.assertIn("consistently N", result)
        self.assertNotIn("consistently F", result)
        self.assertNotIn("all F", result)

    def test_mixed_Y_and_N_is_intermittent(self):
        result = self.m.classify_cause("YNYYN", self.no_flag_entry)
        self.assertIn("intermittent", result)

    def test_mixed_Y_and_F_with_flag(self):
        result = self.m.classify_cause("YFYFY", self.flaky_entry)
        self.assertIn("flaky-flagged", result)

    def test_mixed_F_and_N_no_Y(self):
        result = self.m.classify_cause("FFNFN", self.no_flag_entry)
        self.assertIn("mixed F+N", result)

    def test_dashes_are_ignored_in_classification(self):
        self.assertEqual(self.m.classify_cause("Y--YY", None), "stable")


class FlagRemovalTrailingYTests(unittest.TestCase):
    """Tests the production trailing_y_count() helper used by render_report()
    for flag-removal candidate detection. Calls the real function so changes
    to the production logic surface as test failures."""

    def setUp(self):
        self.m = load_script_module()

    def test_all_Y_returns_full_count(self):
        self.assertEqual(self.m.trailing_y_count("YYYYY"), 5)

    def test_trailing_N_resets_count(self):
        self.assertEqual(self.m.trailing_y_count("YYYYN"), 0)

    def test_trailing_dash_is_skipped_not_break(self):
        self.assertEqual(self.m.trailing_y_count("YYYY-"), 4)
        self.assertEqual(self.m.trailing_y_count("YYY--"), 3)

    def test_F_in_middle_breaks(self):
        self.assertEqual(self.m.trailing_y_count("YYYFY"), 1)

    def test_N_then_dash_still_breaks(self):
        self.assertEqual(self.m.trailing_y_count("YYYNY-"), 1)

    def test_empty_string_returns_zero(self):
        self.assertEqual(self.m.trailing_y_count(""), 0)

    def test_only_dashes_returns_zero(self):
        self.assertEqual(self.m.trailing_y_count("-----"), 0)


class LoadOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.m = load_script_module()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.manifest_path = Path(self.tmpdir.name) / "manifest.yml"
        self.manifest_path.write_text(V2_MANIFEST_YAML, encoding="utf-8")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_load_ownership_returns_manifest_and_skill_to_team(self):
        ownership = self.m.load_ownership(self.manifest_path)
        self.assertIn("manifest", ownership)
        self.assertIn("skill_to_team", ownership)
        s2t = ownership["skill_to_team"]
        self.assertEqual(s2t.get("dataflows-consumption-cli"), "dataflows")
        self.assertEqual(s2t.get("search-consumption-cli"), "catalog")
        self.assertEqual(s2t.get("check-updates"), "platform")


class ResolveTestTeamTests(unittest.TestCase):
    def setUp(self):
        self.m = load_script_module()
        self.skill_to_team = {
            "dataflows-consumption-cli": "dataflows",
            "search-consumption-cli": "catalog",
            "check-updates": "platform",
        }

    def test_first_expected_skill_resolves_to_team(self):
        entry = {"name": "t1", "expectedSkills": ["dataflows-consumption-cli"]}
        self.assertEqual(
            self.m.resolve_test_team(entry, self.skill_to_team),
            "dataflows",
        )

    def test_empty_expected_skills_returns_unmapped(self):
        entry = {"name": "agent-test", "expectedSkills": []}
        self.assertEqual(
            self.m.resolve_test_team(entry, self.skill_to_team),
            self.m.UNMAPPED_SECTION,
        )

    def test_missing_expected_skills_returns_unmapped(self):
        entry = {"name": "no-key"}
        self.assertEqual(
            self.m.resolve_test_team(entry, self.skill_to_team),
            self.m.UNMAPPED_SECTION,
        )

    def test_first_unknown_skill_falls_through_to_next_known(self):
        entry = {
            "name": "t1",
            "expectedSkills": ["unknown-skill-xyz", "search-consumption-cli"],
        }
        self.assertEqual(
            self.m.resolve_test_team(entry, self.skill_to_team),
            "catalog",
        )

    def test_all_unknown_skills_returns_unmapped(self):
        entry = {"name": "t1", "expectedSkills": ["unknown-a", "unknown-b"]}
        self.assertEqual(
            self.m.resolve_test_team(entry, self.skill_to_team),
            self.m.UNMAPPED_SECTION,
        )


class BuildOutcomeStringTests(unittest.TestCase):
    def setUp(self):
        self.m = load_script_module()

    def test_present_in_all_runs(self):
        per_run = [
            {"foo": {"area": "x", "isPass": True, "rawStatus": "Y"}},
            {"foo": {"area": "x", "isPass": False, "rawStatus": "N"}},
            {"foo": {"area": "x", "isPass": True, "rawStatus": "Y"}},
        ]
        self.assertEqual(self.m.build_outcome_string("foo", per_run), "YNY")

    def test_absent_run_becomes_dash(self):
        per_run = [
            {"foo": {"area": "x", "isPass": True, "rawStatus": "Y"}},
            {},
            {"foo": {"area": "x", "isPass": True, "rawStatus": "Y"}},
        ]
        self.assertEqual(self.m.build_outcome_string("foo", per_run), "Y-Y")

    def test_missing_rawStatus_falls_back_to_isPass_Y(self):
        # Older smoke artifacts may not have rawStatus. Falls back to Y/N
        # derived from isPass so the outcome string + classify_cause stay
        # stable. Matches build-dashboard.py's tolerance for the same drift.
        per_run = [
            {"foo": {"area": "x", "isPass": True}},  # no rawStatus
            {"foo": {"area": "x", "isPass": False}},  # no rawStatus
        ]
        self.assertEqual(self.m.build_outcome_string("foo", per_run), "YN")

    def test_unknown_rawStatus_falls_back_to_isPass(self):
        # rawStatus='?' (or any non-Y/F/N value) should fall back to isPass.
        per_run = [
            {"foo": {"area": "x", "isPass": True, "rawStatus": "?"}},
            {"foo": {"area": "x", "isPass": False, "rawStatus": "?"}},
        ]
        self.assertEqual(self.m.build_outcome_string("foo", per_run), "YN")


class ParseTestResultsSchemaVersionTests(unittest.TestCase):
    """parse_test_results_for_run must ignore the reserved top-level
    `schemaVersion` int (and any other non-object metadata) so the producer
    adding it cannot crash this consumer with `'int' object has no attribute
    'get'`. Regression guard for the schemaVersion field."""

    def setUp(self):
        self.m = load_script_module()
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_schema_version_top_level_field_is_ignored(self):
        run_dir = Path(self.tmpdir.name) / "2026-06-14" / "run-1" / "eventhouse-authoring-cli"
        run_dir.mkdir(parents=True)
        (run_dir / "testResults.json").write_text(
            json.dumps({
                "schemaVersion": 1,
                "stim one": {"isPass": True, "rawStatus": "Y"},
                "stim two": {"isPass": False, "rawStatus": "N"},
            }),
            encoding="utf-8",
        )
        results = self.m.parse_test_results_for_run(Path(self.tmpdir.name))
        self.assertNotIn("schemaVersion", results)
        self.assertEqual(set(results), {"stim one", "stim two"})
        self.assertTrue(results["stim one"]["isPass"])
        self.assertFalse(results["stim two"]["isPass"])


if __name__ == "__main__":
    unittest.main()
