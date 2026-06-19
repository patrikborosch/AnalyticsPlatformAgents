import importlib.util
import os
import shutil
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
CLEANUP_SCRIPT = REPO_ROOT / ".github" / "scripts" / "cleanup_stale_fabric_workspaces.py"
ALERT_SCRIPT = REPO_ROOT / ".github" / "scripts" / "vally_nightly_alert.py"
ARTIFACT_ROOT = REPO_ROOT / "tests" / ".generated-vally-alert-artifacts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None:
        raise RuntimeError(f"Could not load spec for {name} at {path}")
    if spec.loader is None:
        raise RuntimeError(f"Spec for {name} at {path} has no loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CleanupScriptTests(unittest.TestCase):
    def setUp(self):
        self.cleanup = load_module("cleanup_stale_fabric_workspaces", CLEANUP_SCRIPT)

    def test_parse_created_accepts_only_smoke_workspace_prefix(self):
        parsed = self.cleanup.parse_created_from_smoke_name(
            "skills-for-fabric-test-20260601-010203-shard2",
            "skills-for-fabric-test-",
        )

        self.assertIsNotNone(parsed)
        self.assertIsNone(
            self.cleanup.parse_created_from_smoke_name(
                "prod-skills-for-fabric-test-20260601-010203-shard2",
                "skills-for-fabric-test-",
            )
        )

    def test_fabric_url_handles_absolute_and_v1_continuation_urls(self):
        self.assertEqual(
            self.cleanup._fabric_url("/workspaces"),
            "https://api.fabric.microsoft.com/v1/workspaces",
        )
        self.assertEqual(
            self.cleanup._fabric_url("/v1/workspaces?continuationToken=abc"),
            "https://api.fabric.microsoft.com/v1/workspaces?continuationToken=abc",
        )
        self.assertEqual(
            self.cleanup._fabric_url("https://api.fabric.microsoft.com/v1/workspaces"),
            "https://api.fabric.microsoft.com/v1/workspaces",
        )


class NightlyAlertScriptTests(unittest.TestCase):
    def setUp(self):
        self.alert = load_module("vally_nightly_alert", ALERT_SCRIPT)
        shutil.rmtree(ARTIFACT_ROOT, ignore_errors=True)
        (ARTIFACT_ROOT / "vally-smoke-results-1-1-shard0" / "dataflows-consumption-cli" / "2026-06-01T00-00-00").mkdir(parents=True)
        (ARTIFACT_ROOT / "vally-smoke-results-1-1-shard0" / "vally-run.log").write_text(
            "Wall time     12.3s\n",
            encoding="utf-8",
        )
        result_file = ARTIFACT_ROOT / "vally-smoke-results-1-1-shard0" / "dataflows-consumption-cli" / "2026-06-01T00-00-00" / "results.jsonl"
        result_file.write_text(
            '{"gradeResult":{"passed":true}}\n{"gradeResult":{"passed":false}}\n',
            encoding="utf-8",
        )

    def tearDown(self):
        shutil.rmtree(ARTIFACT_ROOT, ignore_errors=True)
        for key in [
            "GITHUB_REPOSITORY",
            "GITHUB_RUN_ID",
            "GITHUB_RUN_ATTEMPT",
            "GITHUB_SHA",
            "SETUP_RESULT",
            "DETECT_RESULT",
            "SHARD_RESULT",
            "SUMMARISE_RESULT",
        ]:
            os.environ.pop(key, None)

    def test_parse_artifacts_reports_eval_counts_and_shard_wall_time(self):
        stats, wall_times, artifact_signals = self.alert.parse_artifacts(ARTIFACT_ROOT)

        self.assertEqual(artifact_signals, 1)
        self.assertEqual(stats["dataflows-consumption-cli"], {"total": 2, "passed": 1, "failed": 1})
        self.assertEqual(wall_times["shard0"], 12.3)

    def test_parse_artifacts_uses_per_shard_fallback_for_missing_jsonl(self):
        import contextlib
        import io

        mixed_root = REPO_ROOT / "tests" / ".generated-vally-alert-mixed"
        shutil.rmtree(mixed_root, ignore_errors=True)
        try:
            shard0_results = mixed_root / "vally-smoke-results-1-2-shard0" / "dataflows-consumption-cli" / "2026-06-01T00-00-00"
            shard0_results.mkdir(parents=True)
            (shard0_results / "results.jsonl").write_text(
                '{"gradeResult":{"passed":true}}\n',
                encoding="utf-8",
            )
            shard1 = mixed_root / "vally-smoke-results-2-2-shard1"
            shard1.mkdir(parents=True)
            (shard1 / "vally-run.log").write_text(
                "lakehouse-consumption-cli-eval [case] score: 40.0% (threshold: 90.0%)\n",
                encoding="utf-8",
            )

            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                stats, _wall_times, artifact_signals = self.alert.parse_artifacts(mixed_root)
            output = buffer.getvalue()

            self.assertEqual(artifact_signals, 1)
            self.assertIn("dataflows-consumption-cli", stats)
            self.assertIn("lakehouse-consumption-cli-eval", stats)
            self.assertEqual(
                stats["lakehouse-consumption-cli-eval"],
                {"total": 1, "passed": 0, "failed": 1},
            )
            self.assertIn("vally-smoke-results-1-2-shard0: source=results.jsonl", output)
            self.assertIn("vally-smoke-results-2-2-shard1: source=vally-run.log (fallback)", output)
        finally:
            shutil.rmtree(mixed_root, ignore_errors=True)

    def test_build_issue_body_contains_required_failure_details(self):
        os.environ.update(
            {
                "GITHUB_REPOSITORY": "gim-home/skills-for-fabric",
                "GITHUB_RUN_ID": "123",
                "GITHUB_RUN_ATTEMPT": "2",
                "GITHUB_SHA": "abcdef1234567890",
                "SETUP_RESULT": "success",
                "DETECT_RESULT": "skipped",
                "SHARD_RESULT": "failure",
                "SUMMARISE_RESULT": "failure",
            }
        )

        body = self.alert.build_issue_body(ARTIFACT_ROOT, "nightly-vally-fail")

        self.assertIn("https://github.com/gim-home/skills-for-fabric/actions/runs/123", body)
        self.assertIn("abcdef1234567890", body)
        self.assertIn("| dataflows-consumption-cli | 2 | 1 | 1 |", body)
        self.assertIn("| shard0 | 12.3 |", body)

    def test_parse_artifacts_renders_shard_with_no_wall_time_as_none(self):
        """A shard whose log has no Wall time lines must NOT appear as `0.0`
        (would read as "shard hung at 0s"). Record None instead so the
        renderer can show `-` and distinguish missing from measured-zero.
        """
        empty_walltime_root = REPO_ROOT / "tests" / ".generated-vally-alert-empty-wt"
        shutil.rmtree(empty_walltime_root, ignore_errors=True)
        try:
            shard0 = empty_walltime_root / "vally-smoke-results-9-1-shard0"
            shard0.mkdir(parents=True)
            # Log present but has no "Wall time" lines (format drift / truncation /
            # provisioning failure before vally ran any stim).
            (shard0 / "vally-run.log").write_text(
                "Some preamble log without any wall-time data\n",
                encoding="utf-8",
            )
            shard1 = empty_walltime_root / "vally-smoke-results-9-1-shard1"
            shard1.mkdir(parents=True)
            (shard1 / "vally-run.log").write_text(
                "Wall time     5.5s\nWall time     2.0s\n",
                encoding="utf-8",
            )

            _stats, wall_times, _signals = self.alert.parse_artifacts(empty_walltime_root)

            # Both shards visible (key present) but shard0 has None (no data)
            # and shard1 has the summed float.
            self.assertIn("shard0", wall_times)
            self.assertIn("shard1", wall_times)
            self.assertIsNone(wall_times["shard0"])
            self.assertEqual(wall_times["shard1"], 7.5)
        finally:
            shutil.rmtree(empty_walltime_root, ignore_errors=True)

    def test_build_issue_body_renders_missing_shard_wall_time_as_dash(self):
        """The issue body must render shards with no parseable wall-time data
        as `-` and call them out in a follow-up note so on-call sees them as
        distinct from "wall time was actually 0 seconds".
        """
        mixed_walltime_root = REPO_ROOT / "tests" / ".generated-vally-alert-mixed-wt"
        shutil.rmtree(mixed_walltime_root, ignore_errors=True)
        os.environ.update(
            {
                "GITHUB_REPOSITORY": "gim-home/skills-for-fabric",
                "GITHUB_RUN_ID": "456",
                "GITHUB_RUN_ATTEMPT": "1",
                "GITHUB_SHA": "deadbeef",
                "SETUP_RESULT": "success",
                "DETECT_RESULT": "skipped",
                "SHARD_RESULT": "failure",
                "SUMMARISE_RESULT": "success",
            }
        )
        try:
            shard0 = mixed_walltime_root / "vally-smoke-results-10-1-shard0"
            shard0.mkdir(parents=True)
            (shard0 / "vally-run.log").write_text(
                "Wall time     8.0s\n",
                encoding="utf-8",
            )
            shard1 = mixed_walltime_root / "vally-smoke-results-10-1-shard1"
            shard1.mkdir(parents=True)
            # No Wall time lines at all -- a benign provisioning failure
            # before vally ran. Must NOT show as `shard1 | 0.0`.
            (shard1 / "vally-run.log").write_text(
                "Workspace provisioning timed out before vally invocation\n",
                encoding="utf-8",
            )

            body = self.alert.build_issue_body(mixed_walltime_root, "nightly-vally-fail")

            self.assertIn("| shard0 | 8.0 |", body)
            self.assertIn("| shard1 | - |", body)
            # The min/max/avg row must NOT include the None shard
            self.assertIn("| min / max / avg | 8.0 / 8.0 / 8.0 |", body)
            # Call-out note must surface the missing-data shard explicitly
            self.assertIn("shard1", body.lower())
            self.assertIn("no parseable", body.lower())
        finally:
            shutil.rmtree(mixed_walltime_root, ignore_errors=True)

    def test_parse_artifacts_aggregates_multiple_logs_in_one_shard_dir(self):
        """Multiple vally-run.log files under the same shard directory must
        sum their wall times. The runner's `rglob` recursion can pick up nested
        logs (e.g. one at the shard root + one under .vally-results/<eval>/),
        so the aggregation arithmetic on the multi-log path needs explicit
        coverage; the single-log fixture in other tests never reaches it.
        """
        multi_log_root = REPO_ROOT / "tests" / ".generated-vally-alert-multi-log"
        shutil.rmtree(multi_log_root, ignore_errors=True)
        try:
            shard0 = multi_log_root / "vally-smoke-results-7-1-shard0"
            nested = shard0 / ".vally-results" / "some-eval"
            nested.mkdir(parents=True)
            (shard0 / "vally-run.log").write_text("Wall time     5.0s\n", encoding="utf-8")
            (nested / "vally-run.log").write_text("Wall time     7.5s\n", encoding="utf-8")

            _stats, wall_times, _signals = self.alert.parse_artifacts(multi_log_root)

            self.assertIn("shard0", wall_times)
            self.assertEqual(wall_times["shard0"], 12.5)
        finally:
            shutil.rmtree(multi_log_root, ignore_errors=True)

    def test_parse_artifacts_handles_missing_artifacts_dir(self):
        """The alert script must still produce a usable issue body when the
        --artifacts-dir is missing or empty (the `gh run download` step uses
        set +e specifically so the alerter still runs when no artifacts were
        uploaded). build_issue_body against a non-existent path must return
        a string containing the explicit "No per-eval results" sentinel plus
        the workflow result metadata.
        """
        os.environ.update(
            {
                "GITHUB_REPOSITORY": "gim-home/skills-for-fabric",
                "GITHUB_RUN_ID": "999",
                "GITHUB_RUN_ATTEMPT": "1",
                "GITHUB_SHA": "1234567890abcdef",
                "SETUP_RESULT": "failure",
                "DETECT_RESULT": "skipped",
                "SHARD_RESULT": "failure",
                "SUMMARISE_RESULT": "failure",
            }
        )
        missing = REPO_ROOT / "tests" / ".this-path-does-not-exist-on-purpose"
        shutil.rmtree(missing, ignore_errors=True)

        body = self.alert.build_issue_body(missing, "nightly-vally-fail")

        self.assertIn("No per-eval results were available", body)
        self.assertIn("https://github.com/gim-home/skills-for-fabric/actions/runs/999", body)
        self.assertIn("1234567890abcdef", body)

    def test_parse_shard_log_scores_accepts_line_without_model_bracket(self):
        """The headline bracket-optional fix added `(?:\\[[^\\]]*\\]\\s+)?` to
        SCORE_RE / CRASH_RE. The bracket-WITH form is exercised elsewhere;
        the bracket-WITHOUT form (the actual reason for the fix) needs an
        explicit fixture so a future regex tightening that drops the
        optional group still goes red here.
        """
        text = "foo-eval score: 40.0% (threshold: 90.0%)\n"
        fragment = self.alert.parse_shard_log_scores(text)
        self.assertEqual(fragment["foo-eval"], {"total": 1, "passed": 0, "failed": 1})

        text_pass = "bar-eval score: 99.0% (threshold: 95.0%)\n"
        fragment_pass = self.alert.parse_shard_log_scores(text_pass)
        self.assertEqual(fragment_pass["bar-eval"], {"total": 1, "passed": 1, "failed": 0})

        text_with = "baz-eval [claude-sonnet-4.6] score: 100.0% (threshold: 95.0%)\n"
        fragment_with = self.alert.parse_shard_log_scores(text_with)
        self.assertEqual(fragment_with["baz-eval"], {"total": 1, "passed": 1, "failed": 0})

    def test_parse_shard_log_scores_accepts_eval_name_without_eval_suffix(self):
        """Eval names need not end in `-eval`. The framework uses whatever
        the eval.yaml's `name:` field says, and nothing guarantees the
        suffix. Pin both shapes so a future regex revert that re-anchors
        on `-eval` goes red.
        """
        no_suffix = "lakehouse-consumption-cli score: 80.0% (threshold: 95.0%)\n"
        fragment = self.alert.parse_shard_log_scores(no_suffix)
        self.assertEqual(fragment["lakehouse-consumption-cli"], {"total": 1, "passed": 0, "failed": 1})

        crash_no_suffix = "powerbi-authoring-cli grader(s) failed\n"
        fragment_crash = self.alert.parse_shard_log_scores(crash_no_suffix)
        self.assertEqual(fragment_crash["powerbi-authoring-cli"], {"total": 1, "passed": 0, "failed": 1})


class NightlyAlertGitHubApiTests(unittest.TestCase):
    """Coverage for the GitHub API interaction layer: retry on transient
    failures, pagination of dedup-list, hot-path of ensure_label, and the
    issue-already-exists comment branch."""

    def setUp(self):
        self.alert = load_module("vally_nightly_alert", ALERT_SCRIPT)

    def test_github_request_retries_5xx_then_succeeds(self):
        """A transient 502 followed by a 200 must complete without raising,
        and the eventual return value must be the 200's JSON body."""
        import io
        import json as _json
        from unittest.mock import patch

        success_payload = _json.dumps({"ok": True}).encode("utf-8")
        success_response = io.BytesIO(success_payload)
        # Pretend the underlying response has the headers + JSON
        success_response.read = lambda *_: success_payload  # type: ignore[assignment]
        success_response.getheaders = lambda: []  # type: ignore[assignment]
        success_response.__enter__ = lambda s: s  # type: ignore[assignment]
        success_response.__exit__ = lambda *args: False  # type: ignore[assignment]

        call_count = {"n": 0}

        def fake_urlopen(_request, timeout=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                import urllib.error
                raise urllib.error.HTTPError(
                    url="https://api.github.com/test", code=502, msg="Bad Gateway",
                    hdrs=None, fp=io.BytesIO(b'{"message":"server hiccup"}'),
                )
            return success_response

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep", return_value=None):
            result = self.alert.github_request("GET", "/test", "fake-token")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(call_count["n"], 2)

    def test_github_request_does_not_retry_4xx(self):
        """A 401/403/404 must raise immediately without consuming retries
        (no point retrying an auth or not-found error)."""
        import io
        from unittest.mock import patch

        call_count = {"n": 0}

        def fake_urlopen(_request, timeout=None):
            import urllib.error
            call_count["n"] += 1
            raise urllib.error.HTTPError(
                url="https://api.github.com/test", code=403, msg="Forbidden",
                hdrs=None, fp=io.BytesIO(b'{"message":"forbidden"}'),
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep", return_value=None):
            with self.assertRaises(self.alert.GitHubApiError) as ctx:
                self.alert.github_request("GET", "/test", "fake-token")

        self.assertEqual(ctx.exception.status, 403)
        self.assertEqual(call_count["n"], 1, "4xx must not trigger retries")

    def test_github_request_wraps_exhausted_urlerror_in_github_api_error(self):
        """A persistent network error (DNS, timeout, connection refused)
        must surface as a GitHubApiError on exhaustion, not a raw URLError.
        main()'s step-summary fallback branches on `except GitHubApiError`,
        so a raw URLError would bypass the fallback and the alerter would
        die without dumping the would-be body to the workflow summary.
        """
        from unittest.mock import patch

        def fake_urlopen(_request, timeout=None):
            import urllib.error
            raise urllib.error.URLError("name resolution failed")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep", return_value=None):
            with self.assertRaises(self.alert.GitHubApiError) as ctx:
                self.alert.github_request("GET", "/test", "fake-token")

        self.assertEqual(ctx.exception.status, 0, "wrapped network errors must carry status=0 as the sentinel")
        self.assertIn("network error after", str(ctx.exception))

    def test_ensure_label_swallows_422_already_exists(self):
        """ensure_label hits this branch on EVERY run after the first one
        (the create-label path only runs once per repo). It must return
        cleanly on 422 'already_exists' so the hot path doesn't red the
        alerter."""
        from unittest.mock import patch

        def fake_request(method, url, token, payload=None):
            raise self.alert.GitHubApiError(422, '{"message":"already_exists"}')

        with patch.object(self.alert, "github_request", side_effect=fake_request):
            # Should not raise.
            self.alert.ensure_label("gim-home/skills-for-fabric", "fake-token", "nightly-vally-fail")

    def test_ensure_label_propagates_non_422_errors(self):
        """A 403 on the create-label path means the token lacks perms; that
        must propagate so the alerter fails loudly instead of silently
        proceeding without a label."""
        from unittest.mock import patch

        def fake_request(method, url, token, payload=None):
            raise self.alert.GitHubApiError(403, '{"message":"forbidden"}')

        with patch.object(self.alert, "github_request", side_effect=fake_request):
            with self.assertRaises(self.alert.GitHubApiError) as ctx:
                self.alert.ensure_label("gim-home/skills-for-fabric", "fake-token", "x")
            self.assertEqual(ctx.exception.status, 403)

    def test_list_open_labeled_issues_follows_pagination(self):
        """When the dedup-list crosses the 100-per-page boundary the script
        must follow Link: rel=next so the dedup filter still sees older
        matches. Without pagination it would silently miss them and open a
        duplicate issue every day."""
        from unittest.mock import patch

        page1 = [{"number": i, "title": f"issue {i}"} for i in range(1, 101)]
        page2 = [{"number": 101, "title": "issue 101"}, {"number": 102, "title": "issue 102"}]
        responses = [
            (page1, {"link": '<https://api.github.com/repos/o/r/issues?page=2>; rel="next"'}),
            (page2, {}),
        ]
        call_iter = iter(responses)

        def fake_call(method, url, token, payload=None):
            return next(call_iter)

        with patch.object(self.alert, "_github_request_with_response", side_effect=fake_call):
            issues = self.alert.list_open_labeled_issues("o/r", "fake-token", "lbl")

        self.assertEqual(len(issues), 102)
        self.assertEqual(issues[0]["number"], 1)
        self.assertEqual(issues[-1]["number"], 102)

    def test_create_or_update_issue_comments_on_existing(self):
        """The dedup branch (POST /issues/{n}/comments) is the whole point of
        opening labeled issues vs. random titles; it has its own explicit
        coverage so a future change to title matching doesn't silently fall
        back to create-new and produce a flood of duplicate issues."""
        from unittest.mock import patch, call

        existing_issue = {"number": 42, "title": "[vally-nightly] Failure on 2026-06-04 (commit deadbee)", "html_url": "https://example/42"}
        captured: dict[str, Any] = {}

        def fake_request(method, url, token, payload=None):
            captured.setdefault("calls", []).append((method, url, payload))
            if url == "/repos/o/r/issues/42/comments":
                return {"id": 1}
            return {}  # ensure_label POST

        with patch.object(self.alert, "github_request", side_effect=fake_request), \
             patch.object(self.alert, "list_open_labeled_issues", return_value=[existing_issue]):
            url = self.alert.create_or_update_issue("o/r", "fake-token", "lbl", "2026-06-04", "[vally-nightly] Failure on 2026-06-04 (commit deadbee)", "body")

        self.assertEqual(url, "https://example/42")
        comment_calls = [c for c in captured.get("calls", []) if c[1] == "/repos/o/r/issues/42/comments"]
        self.assertEqual(len(comment_calls), 1, "must POST to the comments endpoint")
        # And must NOT have called the create-issue endpoint
        create_calls = [c for c in captured.get("calls", []) if c[1] == "/repos/o/r/issues"]
        self.assertEqual(len(create_calls), 0, "must not create a new issue when one already matches")

    def test_main_dumps_body_to_step_summary_on_api_failure(self):
        """If the GitHub Issues API is unreachable, main() must dump the body
        into GITHUB_STEP_SUMMARY before re-raising, so an on-call checking
        the workflow UI still sees the per-eval breakdown."""
        import tempfile
        from unittest.mock import patch

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md") as f:
            summary_path = f.name
        os.environ.update({
            "GITHUB_REPOSITORY": "gim-home/skills-for-fabric",
            "GITHUB_RUN_ID": "12345",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_SHA": "1234567890",
            "GITHUB_STEP_SUMMARY": summary_path,
            "GITHUB_TOKEN": "fake-token",
            "SETUP_RESULT": "failure",
            "DETECT_RESULT": "skipped",
            "SHARD_RESULT": "failure",
            "SUMMARISE_RESULT": "failure",
        })
        try:
            with patch.object(self.alert, "create_or_update_issue", side_effect=self.alert.GitHubApiError(503, '{"message":"unavailable"}')):
                with self.assertRaises(self.alert.GitHubApiError):
                    self.alert.main(["--artifacts-dir", str(REPO_ROOT / "tests" / ".this-dir-does-not-exist-anywhere")])

            with open(summary_path, "r", encoding="utf-8") as fh:
                summary = fh.read()
            self.assertIn("Alerter could not file an issue", summary)
            self.assertIn("GitHub API error 503", summary)
            self.assertIn("1234567890", summary)
        finally:
            os.unlink(summary_path)


class CleanupScript404Tests(unittest.TestCase):
    """A benign race where the workspace is already deleted (HTTP 404)
    must NOT turn the cron run red. Only non-404 errors are real failures.
    """

    def setUp(self):
        self.cleanup = load_module("cleanup_stale_fabric_workspaces", CLEANUP_SCRIPT)

    def test_main_treats_404_as_already_gone_not_failed(self):
        import contextlib
        import datetime as dt
        import io
        from unittest.mock import patch

        # Two stale workspaces: one deletes fine, one already gone (404 race).
        # cutoff_hours = 1 makes both "stale enough" given the names below.
        old_iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)).strftime("%Y%m%d-%H%M%S")
        workspaces = [
            {"id": "ws-ok", "displayName": f"skills-for-fabric-test-{old_iso}-shard0"},
            {"id": "ws-already-gone", "displayName": f"skills-for-fabric-test-{old_iso}-shard1"},
        ]

        def fake_delete(workspace_id, _token):
            if workspace_id == "ws-already-gone":
                raise self.cleanup.FabricApiError(404, '{"message":"Workspace not found"}')
            return None

        with patch.object(self.cleanup, "get_fabric_token", return_value="fake-token"), \
             patch.object(self.cleanup, "list_workspaces", return_value=iter(workspaces)), \
             patch.object(self.cleanup, "delete_workspace_by_id", side_effect=fake_delete):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = self.cleanup.main(["--cutoff-hours", "1"])
            output = buffer.getvalue()

        self.assertEqual(rc, 0, "404 race must not turn the cron run red")
        self.assertIn("Already gone (404, benign race)", output)
        self.assertIn("already_gone=1", output)
        self.assertIn("deleted=1", output)
        self.assertIn("failed=0", output)

    def test_main_returns_nonzero_on_non_404_delete_failure(self):
        import contextlib
        import datetime as dt
        import io
        from unittest.mock import patch

        old_iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)).strftime("%Y%m%d-%H%M%S")
        workspaces = [{"id": "ws-server-error", "displayName": f"skills-for-fabric-test-{old_iso}-shard0"}]

        def fake_delete(_workspace_id, _token):
            raise self.cleanup.FabricApiError(500, '{"message":"Internal server error"}')

        with patch.object(self.cleanup, "get_fabric_token", return_value="fake-token"), \
             patch.object(self.cleanup, "list_workspaces", return_value=iter(workspaces)), \
             patch.object(self.cleanup, "delete_workspace_by_id", side_effect=fake_delete):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = self.cleanup.main(["--cutoff-hours", "1"])
            output = buffer.getvalue()

        self.assertEqual(rc, 1, "Real (non-404) errors must still red the cron")
        self.assertIn("failed=1", output)
        self.assertNotIn("already_gone=1", output)

    def test_main_rejects_cutoff_hours_below_minimum(self):
        """Operators must not be able to widen the deletion window by typing
        --cutoff-hours 0.1 from workflow_dispatch. Anything below MIN_CUTOFF_HOURS
        fails loudly with a clear reason rather than silently targeting workspaces
        a few minutes old.
        """
        for too_small in ["0.1", "0.5", "0.9"]:
            with self.assertRaises(SystemExit) as ctx:
                self.cleanup.main(["--cutoff-hours", too_small])
            msg = str(ctx.exception)
            self.assertIn("must be at least", msg)
            self.assertIn(too_small, msg)

    def test_main_skips_matched_but_unparseable_timestamp(self):
        """A workspace whose name matches the prefix but whose timestamp doesn't
        parse must end up in NEITHER deleted NOR failed. The safety branch is
        designed to leave such workspaces alone (in case the regex tightens
        accidentally), so it's tested here so a regression surfaces loudly.
        """
        import contextlib
        import io
        from unittest.mock import patch

        workspaces = [
            {"id": "ws-malformed", "displayName": "skills-for-fabric-test-malformed-shard0"},
        ]

        # Should be unreachable -- if the test fails the safety branch let
        # the workspace through to the delete path.
        def fake_delete(_workspace_id, _token):
            raise AssertionError("delete must not be called for unparseable timestamps")

        with patch.object(self.cleanup, "get_fabric_token", return_value="fake-token"), \
             patch.object(self.cleanup, "list_workspaces", return_value=iter(workspaces)), \
             patch.object(self.cleanup, "delete_workspace_by_id", side_effect=fake_delete):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                rc = self.cleanup.main(["--cutoff-hours", "1"])
            output = buffer.getvalue()

        self.assertEqual(rc, 0, "Malformed-name workspace must not red the cron")
        self.assertIn("Skipping matched workspace with unparseable timestamp", output)
        self.assertIn("deleted=0", output)
        self.assertIn("failed=0", output)
        self.assertIn("already_gone=0", output)


class CleanupScriptFabricApiTests(unittest.TestCase):
    """Coverage for the Fabric REST interaction layer: retry on transient
    failures, pagination safety cap. Mirrors the alerter's GitHub-API tests
    so both sibling scripts have the same defensive posture."""

    def setUp(self):
        self.cleanup = load_module("cleanup_stale_fabric_workspaces", CLEANUP_SCRIPT)

    def test_fabric_request_retries_5xx_then_succeeds(self):
        """A transient 502 followed by a 200 must complete without raising."""
        import io
        import json as _json
        from unittest.mock import patch

        payload = _json.dumps({"value": []}).encode("utf-8")

        class _Resp:
            def __init__(self, body):
                self._body = body
            def read(self):
                return self._body
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        call_count = {"n": 0}

        def fake_urlopen(_request, timeout=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                import urllib.error
                raise urllib.error.HTTPError(
                    url="https://api.fabric.microsoft.com/v1/workspaces", code=502, msg="Bad Gateway",
                    hdrs=None, fp=io.BytesIO(b'{"message":"server hiccup"}'),
                )
            return _Resp(payload)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep", return_value=None):
            result = self.cleanup.fabric_request("GET", "/workspaces", "fake-token")

        self.assertEqual(result, {"value": []})
        self.assertEqual(call_count["n"], 2)

    def test_fabric_request_does_not_retry_4xx(self):
        """A 401/403/404 must raise immediately without consuming retries."""
        import io
        from unittest.mock import patch

        call_count = {"n": 0}

        def fake_urlopen(_request, timeout=None):
            import urllib.error
            call_count["n"] += 1
            raise urllib.error.HTTPError(
                url="https://api.fabric.microsoft.com/v1/workspaces/x", code=404, msg="Not Found",
                hdrs=None, fp=io.BytesIO(b'{"message":"workspace not found"}'),
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep", return_value=None):
            with self.assertRaises(self.cleanup.FabricApiError) as ctx:
                self.cleanup.fabric_request("DELETE", "/workspaces/x", "fake-token")

        self.assertEqual(ctx.exception.status, 404)
        self.assertEqual(call_count["n"], 1, "4xx must not trigger retries")

    def test_fabric_request_wraps_exhausted_urlerror(self):
        """A persistent URLError must surface as FabricApiError(status=0)
        so callers branching on FabricApiError still catch it."""
        from unittest.mock import patch

        def fake_urlopen(_request, timeout=None):
            import urllib.error
            raise urllib.error.URLError("dns resolution failed")

        with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
             patch("time.sleep", return_value=None):
            with self.assertRaises(self.cleanup.FabricApiError) as ctx:
                self.cleanup.fabric_request("GET", "/workspaces", "fake-token")

        self.assertEqual(ctx.exception.status, 0)
        self.assertIn("network error after", str(ctx.exception))

    def test_list_workspaces_safety_cap_does_not_loop_forever(self):
        """If the API returned a self-referential continuation token forever,
        list_workspaces would hold the runner until token expiry. The 500-page
        cap bounds the worst case; verify by simulating an infinite cursor
        and asserting the cap message is emitted (the loop terminates).
        """
        import contextlib
        import io
        from unittest.mock import patch

        # Every fabric_request call returns 1 workspace + a continuation token
        # pointing at the same URL. Without the cap this would never terminate.
        def fake_fabric_request(method, path_or_url, token, payload=None):
            return {
                "value": [{"id": "loop-ws", "displayName": "loop-workspace"}],
                "continuationToken": "same-token-forever",
            }

        buffer = io.StringIO()
        with patch.object(self.cleanup, "fabric_request", side_effect=fake_fabric_request):
            with contextlib.redirect_stdout(buffer):
                workspaces = list(self.cleanup.list_workspaces("fake-token"))

        self.assertEqual(len(workspaces), 500, "must yield 500 pages worth before hitting cap")
        self.assertIn("500-page pagination safety cap", buffer.getvalue())


class RetryHelperTests(unittest.TestCase):
    """Contract tests for the shared `.github/scripts/retry.sh` bash helper.
    Cover the documented behaviour (sleep durations, returned exit code,
    eventual-success path) so a future tweak of the helper does not silently
    drop semantics from any call site.
    """

    RETRY_SCRIPT = REPO_ROOT / ".github" / "scripts" / "retry.sh"

    @classmethod
    def setUpClass(cls):
        # Skip the whole class on environments without a usable POSIX bash
        # (e.g. Windows boxes where `bash` resolves to WSL with no installed
        # distribution). CI runs these on ubuntu-latest where this is moot.
        import shutil as _shutil
        import subprocess

        bash_path = _shutil.which("bash")
        if not bash_path:
            raise unittest.SkipTest("bash not on PATH; retry.sh tests run on CI (ubuntu-latest)")
        try:
            probe = subprocess.run(
                ["bash", "-c", "echo ok"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise unittest.SkipTest(f"bash on PATH is not usable: {exc}")
        if probe.returncode != 0 or probe.stdout.strip() != "ok":
            raise unittest.SkipTest(
                "bash on PATH does not execute a simple POSIX command "
                f"(rc={probe.returncode}, stdout={probe.stdout!r}, stderr={probe.stderr!r}); "
                "likely WSL without a distro on Windows. retry.sh tests run on CI (ubuntu-latest)."
            )

    def _run_bash(self, script: str) -> "tuple[int, str, str]":
        import subprocess

        result = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode, result.stdout, result.stderr

    def test_retry_helper_returns_zero_on_first_success(self):
        rc, _stdout, _stderr = self._run_bash(
            f"set -euo pipefail; source {self.RETRY_SCRIPT.as_posix()}; retry true"
        )
        self.assertEqual(rc, 0)

    def test_retry_helper_returns_nonzero_after_exhausting_attempts(self):
        # Use a fake command that always fails. The retry helper will sleep
        # 5s + 10s = 15s between attempts; budget the timeout accordingly.
        rc, _stdout, stderr = self._run_bash(
            f"set -euo pipefail; source {self.RETRY_SCRIPT.as_posix()}; retry false || echo 'caught-exhaustion'"
        )
        self.assertEqual(rc, 0)  # the || branch catches the exhaustion
        # Should have emitted exactly 2 warning lines (attempts 1 and 2 failed
        # before the final attempt; the helper doesn't warn on the final fail).
        self.assertEqual(stderr.count("::warning::Command failed"), 2)

    def test_retry_helper_returns_zero_after_eventual_success(self):
        # Use a counter file. The command "succeeds on the second invocation"
        # by incrementing the counter and exiting non-zero on attempt 1.
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as counter:
            counter.write(b"0")
            counter_path = counter.name
        try:
            counter_posix = counter_path.replace("\\", "/")
            script = f"""
            set -euo pipefail
            source {self.RETRY_SCRIPT.as_posix()}
            try_once() {{
              local n
              n=$(cat {counter_posix})
              n=$((n + 1))
              echo "$n" > {counter_posix}
              if [ "$n" -ge 2 ]; then return 0; fi
              return 1
            }}
            retry try_once
            """
            rc, _stdout, _stderr = self._run_bash(script)
            self.assertEqual(rc, 0)
            with open(counter_path) as fh:
                self.assertEqual(fh.read().strip(), "2")
        finally:
            os.unlink(counter_path)


if __name__ == "__main__":
    unittest.main()
