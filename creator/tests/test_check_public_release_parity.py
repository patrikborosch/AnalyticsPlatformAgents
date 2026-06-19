# Unit tests for .github/scripts/check_public_release_parity.py.
#
# Focus areas (pure logic only -- no network):
#   - normalize_tag() canonicalisation
#   - parse_package_version() happy path + malformed inputs
#   - released_tag_names() draft exclusion + shape tolerance
#   - find_missing_release() present / absent / empty
#   - build_issue_body() actionable + ASCII-only + no @mentions
#   - main() exit-code contract the PublishToPublic.ps1 Phase-1 gate depends on

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "check_public_release_parity.py"


def load_script_module():
    """Load check_public_release_parity.py as a module so we can call its functions."""
    spec = importlib.util.spec_from_file_location("check_public_release_parity", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_public_release_parity"] = module
    spec.loader.exec_module(module)
    return module


mod = load_script_module()


class TestNormalizeTag(unittest.TestCase):
    def test_adds_v_prefix(self):
        self.assertEqual(mod.normalize_tag("0.3.3"), "v0.3.3")

    def test_keeps_existing_v_prefix(self):
        self.assertEqual(mod.normalize_tag("v0.3.3"), "v0.3.3")

    def test_strips_whitespace(self):
        self.assertEqual(mod.normalize_tag("  0.3.3 "), "v0.3.3")

    def test_empty(self):
        self.assertEqual(mod.normalize_tag(""), "v")


class TestParsePackageVersion(unittest.TestCase):
    def test_happy_path(self):
        self.assertEqual(mod.parse_package_version('{"version": "0.3.3"}'), "0.3.3")

    def test_strips_whitespace(self):
        self.assertEqual(mod.parse_package_version('{"version": " 0.3.3 "}'), "0.3.3")

    def test_missing_version_raises(self):
        with self.assertRaises(ValueError):
            mod.parse_package_version('{"name": "x"}')

    def test_non_string_version_raises(self):
        with self.assertRaises(ValueError):
            mod.parse_package_version('{"version": 3}')

    def test_empty_version_raises(self):
        with self.assertRaises(ValueError):
            mod.parse_package_version('{"version": "  "}')

    def test_non_object_json_raises(self):
        # Valid JSON that is not an object (e.g. a list) must raise ValueError,
        # not AttributeError -- main() only catches ValueError/GitHubApiError, so
        # an AttributeError would escape and bypass the exit-code contract.
        with self.assertRaises(ValueError):
            mod.parse_package_version("[]")
        with self.assertRaises(ValueError):
            mod.parse_package_version('"just-a-string"')


class TestReleasedTagNames(unittest.TestCase):
    def test_collects_tag_names(self):
        payload = [{"tag_name": "v0.3.0"}, {"tag_name": "v0.3.1"}]
        self.assertEqual(mod.released_tag_names(payload), {"v0.3.0", "v0.3.1"})

    def test_excludes_drafts(self):
        payload = [{"tag_name": "v0.3.0"}, {"tag_name": "v0.3.9", "draft": True}]
        self.assertEqual(mod.released_tag_names(payload), {"v0.3.0"})

    def test_skips_entries_without_tag_name(self):
        payload = [{"tag_name": "v0.3.0"}, {"name": "no tag"}, "not-a-dict"]
        self.assertEqual(mod.released_tag_names(payload), {"v0.3.0"})

    def test_non_list_returns_empty(self):
        self.assertEqual(mod.released_tag_names({"message": "Not Found"}), set())
        self.assertEqual(mod.released_tag_names(None), set())


class TestFindMissingRelease(unittest.TestCase):
    def test_present_returns_none(self):
        self.assertIsNone(mod.find_missing_release("0.3.3", {"v0.3.3", "v0.3.1"}))

    def test_present_with_v_prefix(self):
        self.assertIsNone(mod.find_missing_release("v0.3.3", {"v0.3.3"}))

    def test_absent_returns_expected_tag(self):
        self.assertEqual(mod.find_missing_release("0.3.3", {"v0.3.1", "v0.3.0"}), "v0.3.3")

    def test_empty_release_set(self):
        self.assertEqual(mod.find_missing_release("0.3.3", set()), "v0.3.3")


class TestBuildIssueBody(unittest.TestCase):
    def setUp(self):
        self.body = mod.build_issue_body("microsoft/skills-for-fabric", "main", "0.3.3", "v0.3.3")

    def test_mentions_version_and_repo(self):
        self.assertIn("0.3.3", self.body)
        self.assertIn("microsoft/skills-for-fabric", self.body)

    def test_includes_phase2_command(self):
        self.assertIn("-PublishRelease -Version 0.3.3", self.body)

    def test_is_ascii_only(self):
        # Encoding hygiene: tracking issue body must be plain ASCII.
        self.body.encode("ascii")

    def test_no_at_mentions(self):
        # Auto-filed issues must not @-ping anyone. This also enforces the
        # "no individual contributor names in artifacts" rule generically --
        # without embedding any account name in the test itself.
        self.assertNotRegex(self.body, r"@\w")


class TestReconcileTrackingIssues(unittest.TestCase):
    """F3: only close issues whose version is now released; leave still-missing ones open."""

    def _issues(self):
        return [
            {"number": 1, "title": "[public-release-parity] Missing public release v0.3.2"},  # now released -> close
            {"number": 2, "title": "[public-release-parity] Missing public release v0.3.9"},  # still missing -> keep
            {"number": 3, "title": "[public-release-parity] Missing public release "},          # unparseable tag -> keep
            {"number": 4, "title": "Some unrelated labeled issue"},                              # not a parity title -> skip
        ]

    def test_closes_only_released_tag_issues(self):
        calls = []

        def fake_req(method, path, token, payload=None):
            calls.append((method, path))
            return {}

        with mock.patch.object(mod, "list_open_labeled_issues", return_value=self._issues()), \
             mock.patch.object(mod, "github_request", side_effect=fake_req):
            closed = mod.reconcile_tracking_issues("o/r", "tok", {"v0.3.2"})

        self.assertEqual(closed, [1])
        patched = [p for (m, p) in calls if m == "PATCH"]
        self.assertEqual(patched, ["/repos/o/r/issues/1"])  # only the released-tag issue is closed

    def test_no_op_when_nothing_released(self):
        with mock.patch.object(mod, "list_open_labeled_issues", return_value=self._issues()), \
             mock.patch.object(mod, "github_request", side_effect=AssertionError("must not write")):
            closed = mod.reconcile_tracking_issues("o/r", "tok", set())
        self.assertEqual(closed, [])


class TestMainExitCodes(unittest.TestCase):
    """The PublishToPublic.ps1 Phase-1 gate keys off these exit codes, so lock them.

    All runs pass --no-issue so main() does no issue I/O (manage_issue is False);
    the two public-read functions are mocked so there is no network.
    """

    def _run(self, content, tags, argv):
        with mock.patch.object(mod, "get_public_content_version", return_value=content), \
             mock.patch.object(mod, "get_public_release_tags", return_value=set(tags)):
            return mod.main(argv)

    def test_gap_exits_2(self):
        self.assertEqual(mod.EXIT_GAP, 2)
        self.assertEqual(self._run("0.3.9", {"v0.3.1"}, ["--no-issue"]), mod.EXIT_GAP)

    def test_parity_ok_exits_0(self):
        self.assertEqual(self._run("0.3.1", {"v0.3.1"}, ["--no-issue"]), mod.EXIT_OK)

    def test_no_fail_on_gap_stays_green(self):
        # Weekly backstop contract: a gap stays green when --no-fail-on-gap is set.
        self.assertEqual(self._run("0.3.9", {"v0.3.1"}, ["--no-issue", "--no-fail-on-gap"]), mod.EXIT_OK)

    def test_api_error_exits_1(self):
        with mock.patch.object(mod, "get_public_content_version", side_effect=mod.GitHubApiError(0, "network")), \
             mock.patch.object(mod, "get_public_release_tags", return_value=set()):
            self.assertEqual(mod.main(["--no-issue"]), mod.EXIT_ERROR)


if __name__ == "__main__":
    unittest.main()
