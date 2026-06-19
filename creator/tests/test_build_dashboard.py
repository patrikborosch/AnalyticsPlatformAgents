"""Unit tests for .github/scripts/build-dashboard.py.

Covers the aggregation edge cases identified by Copilot reviewer on PR #203:
- Window cutoff: pre-cutoff runs must not inflate the rendered totals.
- Rerun ordering: a workflow re-run (higher attempt) must replace the
  prior attempt for the same (skill, date).
- Empty-state HTML render.
- Sparkline gaps for missing days.
- HTML escaping of skill names / repo names.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "build-dashboard.py"
SPEC = importlib.util.spec_from_file_location("build_dashboard", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
build_dashboard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_dashboard)


def _write_results(root: Path, date: str, run_id: str, skill: str, results: dict) -> Path:
    skill_dir = root / date / run_id / skill
    skill_dir.mkdir(parents=True, exist_ok=True)
    out = skill_dir / "testResults.json"
    out.write_text(json.dumps(results), encoding="utf-8")
    return out


class DiscoverRunsTests(unittest.TestCase):
    def test_returns_empty_list_when_root_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "does-not-exist"
            self.assertEqual(build_dashboard.discover_runs(missing), [])

    def test_returns_empty_list_when_no_results_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "noise").mkdir()
            self.assertEqual(build_dashboard.discover_runs(Path(td)), [])

    def test_skips_directories_with_non_iso_dates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write_results(root, "not-a-date", "1-1", "sqldw", {"t": {"isPass": True}})
            self.assertEqual(build_dashboard.discover_runs(root), [])

    def test_extracts_gh_run_id_from_run_id_with_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            _write_results(root, today_iso, "12345-2", "sqldw", {"t": {"isPass": True}})
            runs = build_dashboard.discover_runs(root)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["run_id"], "12345-2")
            self.assertEqual(runs[0]["gh_run_id"], "12345")
            # No token-summary.jsonl present → token_totals defaults to {}.
            self.assertEqual(runs[0]["token_totals"], {})

    def test_schema_version_top_level_key_is_ignored_not_treated_as_a_stim(self) -> None:
        # testResults.json carries a reserved top-level `schemaVersion` int
        # alongside the per-stim entries. discover_runs must drop it so the
        # dashboard does not treat it as a (non-object) test case and crash
        # when summing isPass. Regression guard for the schemaVersion field.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            _write_results(
                root, today_iso, "777-1", "sqldw",
                {"schemaVersion": 1, "t1": {"isPass": True}, "t2": {"isPass": False}},
            )
            runs = build_dashboard.discover_runs(root)
            self.assertEqual(len(runs), 1)
            self.assertNotIn("schemaVersion", runs[0]["test_results"])
            self.assertEqual(set(runs[0]["test_results"]), {"t1", "t2"})
            # Aggregation must not crash on the reserved key and must count
            # only the two real stims.
            agg = build_dashboard.aggregate_by_skill(runs, window_days=30)
            date_entry = agg["by_skill"]["sqldw"]["dates"][today_iso]
            self.assertEqual(date_entry["pass"], 1)
            self.assertEqual(date_entry["fail"], 1)

    def test_discovers_token_summary_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            results_path = _write_results(root, today_iso, "1-1", "sqldw", {"t1": {"isPass": True}})
            token_path = results_path.parent / "token-summary.jsonl"
            token_path.write_text(
                '{"testName":"t1","inputTokens":4210,"outputTokens":612,"cacheReadTokens":0,"cacheWriteTokens":0}\n',
                encoding="utf-8",
            )
            runs = build_dashboard.discover_runs(root)
            self.assertIn("t1", runs[0]["token_totals"])
            self.assertEqual(runs[0]["token_totals"]["t1"]["inputTokens"], 4210)
            self.assertEqual(runs[0]["token_totals"]["t1"]["outputTokens"], 612)
            self.assertEqual(runs[0]["token_totals"]["t1"]["runCount"], 1)

    def test_token_summary_aggregates_multiple_runs_of_same_test(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            results_path = _write_results(root, today_iso, "1-1", "sqldw", {"t1": {"isPass": True}})
            (results_path.parent / "token-summary.jsonl").write_text(
                '\n'.join([
                    '{"testName":"t1","inputTokens":1000,"outputTokens":100,"cacheReadTokens":0,"cacheWriteTokens":0}',
                    '{"testName":"t1","inputTokens":2000,"outputTokens":200,"cacheReadTokens":0,"cacheWriteTokens":0}',
                ]),
                encoding="utf-8",
            )
            runs = build_dashboard.discover_runs(root)
            self.assertEqual(runs[0]["token_totals"]["t1"]["inputTokens"], 3000)
            self.assertEqual(runs[0]["token_totals"]["t1"]["outputTokens"], 300)
            self.assertEqual(runs[0]["token_totals"]["t1"]["runCount"], 2)

    def test_malformed_token_jsonl_does_not_break_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            results_path = _write_results(root, today_iso, "1-1", "sqldw", {"t1": {"isPass": True}})
            (results_path.parent / "token-summary.jsonl").write_text(
                "not valid json at all\n", encoding="utf-8",
            )
            # Discovery still works; token_totals is just empty.
            runs = build_dashboard.discover_runs(root)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["token_totals"], {})


class AggregateByDateWindowTests(unittest.TestCase):
    """Reviewer comment C: pre-cutoff runs must not be reported in totals.runs."""

    def _make_run(self, days_ago: int, skill: str = "sqldw") -> dict:
        run_date = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=days_ago))
        return {
            "date": run_date.strftime("%Y-%m-%d"),
            "run_id": f"{100 + days_ago}-1",
            "gh_run_id": str(100 + days_ago),
            "skill": skill,
            "test_results": {"t": {"isPass": True}},
        }

    def test_totals_runs_counts_only_post_cutoff_runs(self) -> None:
        runs = [self._make_run(2), self._make_run(40), self._make_run(50)]
        result = build_dashboard.aggregate_by_skill(runs, window_days=30)
        # Only the days_ago=2 run is within the 30-day window.
        self.assertEqual(result["totals"]["runs"], 1)
        self.assertEqual(result["totals"]["skills"], 1)
        self.assertEqual(result["totals"]["dates"], 1)

    def test_totals_runs_is_zero_when_all_runs_are_pre_cutoff(self) -> None:
        runs = [self._make_run(60), self._make_run(90)]
        result = build_dashboard.aggregate_by_skill(runs, window_days=30)
        self.assertEqual(result["totals"]["runs"], 0)
        self.assertEqual(result["all_skills"], [])


    def test_multi_skill_same_run_counts_as_one_run(self) -> None:
        """Reviewer comment I: one workflow producing testResults.json per skill
        area must register as one run, not N."""
        # Same date + run_id, three different skill areas.
        run = self._make_run(2)
        run["run_id"] = "99999-1"
        run["gh_run_id"] = "99999"
        runs = [
            {**run, "skill": "sqldw"},
            {**run, "skill": "spark"},
            {**run, "skill": "powerbi"},
        ]
        result = build_dashboard.aggregate_by_skill(runs, window_days=30)
        self.assertEqual(result["totals"]["runs"], 1)
        self.assertEqual(result["totals"]["skills"], 3)
        self.assertEqual(result["totals"]["dates"], 1)

    def test_two_distinct_runs_same_skill_count_as_two_runs(self) -> None:
        runs = [
            self._make_run(2),  # run_id 102-1
            self._make_run(3),  # run_id 103-1
        ]
        result = build_dashboard.aggregate_by_skill(runs, window_days=30)
        self.assertEqual(result["totals"]["runs"], 2)
        self.assertEqual(result["totals"]["dates"], 2)


class AttemptOrderingTests(unittest.TestCase):
    """Reviewer comment D: rerun (higher attempt) must replace the prior attempt."""

    def setUp(self) -> None:
        # Capture today's UTC date ONCE per test to avoid a midnight-rollover
        # race between fixture creation and assertion lookup (reviewer K).
        self.today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    def _make_run(self, run_id_with_attempt: str, is_pass: bool) -> dict:
        return {
            "date": self.today_iso,
            "run_id": run_id_with_attempt,
            "gh_run_id": run_id_with_attempt.split("-", 1)[0],
            "skill": "sqldw",
            "test_results": {"t": {"isPass": is_pass}},
        }

    def test_higher_attempt_wins_for_same_run(self) -> None:
        # rglob() order is not deterministic; simulate the attempt-1 being seen first.
        runs = [
            self._make_run("12345-1", is_pass=False),
            self._make_run("12345-2", is_pass=True),
        ]
        result = build_dashboard.aggregate_by_skill(runs, window_days=30)
        latest = result["by_skill"]["sqldw"]["dates"][self.today_iso]
        self.assertEqual(latest["run_id"], "12345-2")
        self.assertEqual(latest["pass"], 1)
        self.assertEqual(latest["fail"], 0)

    def test_higher_attempt_wins_regardless_of_input_order(self) -> None:
        runs = [
            self._make_run("12345-2", is_pass=True),
            self._make_run("12345-1", is_pass=False),
        ]
        result = build_dashboard.aggregate_by_skill(runs, window_days=30)
        latest = result["by_skill"]["sqldw"]["dates"][self.today_iso]
        self.assertEqual(latest["run_id"], "12345-2")

    def test_higher_run_id_wins_across_distinct_runs(self) -> None:
        runs = [
            self._make_run("9999999-1", is_pass=False),
            self._make_run("88-1", is_pass=True),
        ]
        result = build_dashboard.aggregate_by_skill(runs, window_days=30)
        latest = result["by_skill"]["sqldw"]["dates"][self.today_iso]
        self.assertEqual(latest["run_id"], "9999999-1")


class SparklineTests(unittest.TestCase):
    def test_empty_data_returns_empty_svg(self) -> None:
        svg = build_dashboard.render_sparkline([])
        self.assertIn('class="sparkline empty"', svg)
        self.assertIn("No data", svg)

    def test_all_missing_returns_empty_svg(self) -> None:
        svg = build_dashboard.render_sparkline([None, None, None])
        self.assertIn('class="sparkline empty"', svg)

    def test_single_point_renders_circle_no_polyline(self) -> None:
        svg = build_dashboard.render_sparkline([1.0])
        self.assertIn("<circle", svg)
        self.assertNotIn("<polyline", svg)

    def test_gaps_break_polylines(self) -> None:
        svg = build_dashboard.render_sparkline([1.0, 1.0, None, 1.0, 1.0])
        # Two separate polyline segments either side of the gap.
        self.assertEqual(svg.count("<polyline"), 2)


class TokensColumnTests(unittest.TestCase):
    """Skill-row level token aggregation rendered into the new column."""

    def test_html_includes_tokens_column_header(self) -> None:
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso: {
                            "pass": 1, "fail": 0, "run_id": "1-1", "gh_run_id": "1",
                            "test_results": {"t": {"isPass": True}},
                            "token_totals": {},
                            "day_tokens": 0,
                        }
                    }
                }
            },
            "all_dates": [today_iso],
            "all_skills": ["sqldw"],
            "totals": {"runs": 1, "skills": 1, "dates": 1},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        # Header reads "Tokens (window)" and carries the num class so it
        # right-aligns the same way the cell data does.
        self.assertIn('class="num">Tokens (window)', html_str)

    def test_html_numeric_th_have_num_class(self) -> None:
        # Each numeric column header (Latest / Rate / Window pass / total /
        # Tokens) must carry class="num" so the CSS right-aligns the header
        # text. Without this, headers center-align by browser default while
        # cells right-align, producing visible misalignment under the values.
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso: {"pass": 1, "fail": 0, "run_id": "1-1", "gh_run_id": "1", "token_totals": {}, "day_tokens": 0}
                    }
                }
            },
            "all_dates": [today_iso], "all_skills": ["sqldw"],
            "totals": {"runs": 1, "skills": 1, "dates": 1},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        self.assertIn('<th class="num">Latest</th>', html_str)
        self.assertIn('<th class="num">Rate</th>', html_str)
        self.assertIn('<th class="num">Window pass / total</th>', html_str)
        self.assertIn('<th class="num">Tokens (window)</th>', html_str)

    def test_html_shows_sparkline_hint_when_single_date(self) -> None:
        # Single-date windows render sparklines as a single dot; surface that
        # to the viewer instead of leaving it as an unexplained mystery.
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso: {"pass": 1, "fail": 0, "run_id": "1-1", "gh_run_id": "1", "token_totals": {}, "day_tokens": 0}
                    }
                }
            },
            "all_dates": [today_iso], "all_skills": ["sqldw"],
            "totals": {"runs": 1, "skills": 1, "dates": 1},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        self.assertIn('class="hint"', html_str)
        self.assertIn('at least 2 dates', html_str)

    def test_html_hides_sparkline_hint_when_multiple_dates(self) -> None:
        # With 2+ dates the sparkline draws a line; no need to apologise for it.
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        yesterday_iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso: {"pass": 1, "fail": 0, "run_id": "2-1", "gh_run_id": "2", "token_totals": {}, "day_tokens": 0},
                        yesterday_iso: {"pass": 1, "fail": 0, "run_id": "1-1", "gh_run_id": "1", "token_totals": {}, "day_tokens": 0},
                    }
                }
            },
            "all_dates": [today_iso, yesterday_iso], "all_skills": ["sqldw"],
            "totals": {"runs": 2, "skills": 1, "dates": 2},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        self.assertNotIn('class="hint"', html_str)

    def test_html_renders_no_data_when_tokens_missing(self) -> None:
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso: {
                            "pass": 1, "fail": 0, "run_id": "1-1", "gh_run_id": "1",
                            "test_results": {"t": {"isPass": True}},
                        }
                    }
                }
            },
            "all_dates": [today_iso],
            "all_skills": ["sqldw"],
            "totals": {"runs": 1, "skills": 1, "dates": 1},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        # Render does not crash when token_totals/day_tokens are absent.
        self.assertIn("no data", html_str)

    def test_html_renders_total_tokens_when_present(self) -> None:
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso: {
                            "pass": 1, "fail": 0, "run_id": "1-1", "gh_run_id": "1",
                            "test_results": {"t": {"isPass": True}},
                            "token_totals": {"t": {"inputTokens": 4210, "outputTokens": 612, "cacheReadTokens": 0, "cacheWriteTokens": 0, "runCount": 1}},
                            "day_tokens": 4822,
                        }
                    }
                }
            },
            "all_dates": [today_iso],
            "all_skills": ["sqldw"],
            "totals": {"runs": 1, "skills": 1, "dates": 1},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        self.assertIn("4,822", html_str)
        # Token sparkline was removed (PR #219); cells now show a delta arrow
        # vs prior day instead. With only 1 date of data, no delta is shown.
        self.assertNotIn('class="sparkline tokens"', html_str)
        self.assertNotIn('class="token-delta', html_str)

    def test_html_renders_token_delta_up_when_latest_grew(self) -> None:
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        yesterday_iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso:     {"pass": 1, "fail": 0, "run_id": "2-1", "gh_run_id": "2", "test_results": {"t": {"isPass": True}}, "token_totals": {}, "day_tokens": 1200},
                        yesterday_iso: {"pass": 1, "fail": 0, "run_id": "1-1", "gh_run_id": "1", "test_results": {"t": {"isPass": True}}, "token_totals": {}, "day_tokens": 1000},
                    }
                }
            },
            "all_dates": [today_iso, yesterday_iso], "all_skills": ["sqldw"],
            "totals": {"runs": 2, "skills": 1, "dates": 2},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        # +20% growth -> up arrow, red class.
        self.assertIn('class="token-delta up"', html_str)
        self.assertIn("↑20%", html_str)

    def test_html_renders_token_delta_down_when_latest_shrank(self) -> None:
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        yesterday_iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso:     {"pass": 1, "fail": 0, "run_id": "2-1", "gh_run_id": "2", "test_results": {"t": {"isPass": True}}, "token_totals": {}, "day_tokens": 800},
                        yesterday_iso: {"pass": 1, "fail": 0, "run_id": "1-1", "gh_run_id": "1", "test_results": {"t": {"isPass": True}}, "token_totals": {}, "day_tokens": 1000},
                    }
                }
            },
            "all_dates": [today_iso, yesterday_iso], "all_skills": ["sqldw"],
            "totals": {"runs": 2, "skills": 1, "dates": 2},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        # -20% shrink -> down arrow, green class (declining cost is good).
        self.assertIn('class="token-delta down"', html_str)
        self.assertIn("↓20%", html_str)

    def test_html_renders_token_delta_flat_within_threshold(self) -> None:
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        yesterday_iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso:     {"pass": 1, "fail": 0, "run_id": "2-1", "gh_run_id": "2", "test_results": {"t": {"isPass": True}}, "token_totals": {}, "day_tokens": 1020},
                        yesterday_iso: {"pass": 1, "fail": 0, "run_id": "1-1", "gh_run_id": "1", "test_results": {"t": {"isPass": True}}, "token_totals": {}, "day_tokens": 1000},
                    }
                }
            },
            "all_dates": [today_iso, yesterday_iso], "all_skills": ["sqldw"],
            "totals": {"runs": 2, "skills": 1, "dates": 2},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        # +2% within the ±5% band -> flat arrow.
        self.assertIn('class="token-delta flat"', html_str)
        self.assertIn("→2%", html_str)

    def test_html_renders_no_token_delta_when_only_one_date(self) -> None:
        # With only 1 token-bearing day there is no delta to compute; cell
        # must still render the absolute number without a stray arrow.
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso: {"pass": 1, "fail": 0, "run_id": "1-1", "gh_run_id": "1", "test_results": {"t": {"isPass": True}}, "token_totals": {}, "day_tokens": 1000},
                    }
                }
            },
            "all_dates": [today_iso], "all_skills": ["sqldw"],
            "totals": {"runs": 1, "skills": 1, "dates": 1},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        self.assertIn(">1,000<", html_str)
        self.assertNotIn('class="token-delta', html_str)

    def test_html_renders_daily_history_when_multiple_dates(self) -> None:
        # Expanded view must show a per-day history table when 2+ dates exist,
        # so readers can see actual numbers per day instead of just a sparkline.
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        yesterday_iso = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso:     {"pass": 8, "fail": 2, "run_id": "2-1", "gh_run_id": "2", "test_results": {"t": {"isPass": True}}, "token_totals": {}, "day_tokens": 50000},
                        yesterday_iso: {"pass": 10, "fail": 0, "run_id": "1-1", "gh_run_id": "1", "test_results": {"t": {"isPass": True}}, "token_totals": {}, "day_tokens": 45000},
                    }
                }
            },
            "all_dates": [today_iso, yesterday_iso], "all_skills": ["sqldw"],
            "totals": {"runs": 2, "skills": 1, "dates": 2},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        self.assertIn('class="history-block"', html_str)
        self.assertIn('Daily history', html_str)
        # Both dates surfaced as rows.
        self.assertIn(today_iso, html_str)
        self.assertIn(yesterday_iso, html_str)
        # Per-day formatted numbers visible.
        self.assertIn("8 / 10", html_str)
        self.assertIn("10 / 10", html_str)
        self.assertIn("50,000", html_str)
        self.assertIn("45,000", html_str)

    def test_html_hides_daily_history_when_single_date(self) -> None:
        # Single-date case: no daily history (it would be a 1-row table that
        # is redundant with the main skill row).
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso: {"pass": 1, "fail": 0, "run_id": "1-1", "gh_run_id": "1", "test_results": {"t": {"isPass": True}}, "token_totals": {}, "day_tokens": 1000},
                    }
                }
            },
            "all_dates": [today_iso], "all_skills": ["sqldw"],
            "totals": {"runs": 1, "skills": 1, "dates": 1},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        self.assertNotIn('class="history-block"', html_str)


class HtmlEscapingTests(unittest.TestCase):
    def test_render_html_escapes_skill_names(self) -> None:
        aggregated = {
            "by_skill": {
                "sql<>injection": {
                    "dates": {
                        dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"): {
                            "pass": 1, "fail": 0, "run_id": "1-1", "gh_run_id": "1",
                            "test_results": {"t": {"isPass": True}},
                        }
                    }
                }
            },
            "all_dates": [dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")],
            "all_skills": ["sql<>injection"],
            "totals": {"runs": 1, "skills": 1, "dates": 1},
        }
        html = build_dashboard.render_html(aggregated, repo="org/repo", window_days=30)
        self.assertNotIn("<>injection</strong>", html)
        self.assertIn("&lt;&gt;injection", html)


class EmptyHtmlTests(unittest.TestCase):
    def test_empty_aggregation_renders_empty_state(self) -> None:
        aggregated = {
            "by_skill": {},
            "all_dates": [],
            "all_skills": [],
            "totals": {"runs": 0, "skills": 0, "dates": 0},
        }
        html = build_dashboard.render_html(aggregated, repo="org/repo", window_days=30)
        self.assertIn("empty-state", html)
        self.assertIn("No smoke-results artifacts found", html)


class TestDetailsRenderingTests(unittest.TestCase):
    """Per-test detail block under each skill row (the user-visible Y/F/N + duration)."""

    def _make_aggregated(self, test_results: dict) -> dict:
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        return {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso: {
                            "pass": sum(1 for v in test_results.values() if v.get("isPass")),
                            "fail": sum(1 for v in test_results.values() if not v.get("isPass")),
                            "run_id": "1-1", "gh_run_id": "1",
                            "test_results": test_results,
                        }
                    }
                }
            },
            "all_dates": [today_iso],
            "all_skills": ["sqldw"],
            "totals": {"runs": 1, "skills": 1, "dates": 1},
        }

    def test_html_includes_test_name_and_status_badge(self) -> None:
        agg = self._make_aggregated({
            "sqldw-consumption-basic-query": {"isPass": True, "rawStatus": "Y", "durationSeconds": 12.4},
        })
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        self.assertIn("sqldw-consumption-basic-query", html_str)
        self.assertIn('class="status-badge Y"', html_str)
        self.assertIn(">Y<", html_str)

    def test_html_shows_F_badge_for_flaky_pass(self) -> None:
        agg = self._make_aggregated({
            "spark-authoring-notebook-sanity": {"isPass": True, "rawStatus": "F", "flakyIssue": "https://example.test/issues/131"},
        })
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        self.assertIn('class="status-badge F"', html_str)
        self.assertIn("flaky", html_str)
        self.assertIn("https://example.test/issues/131", html_str)

    def test_html_shows_N_badge_with_missing_skills(self) -> None:
        agg = self._make_aggregated({
            "powerbi-consumption-basic": {
                "isPass": False, "rawStatus": "N",
                "missingSkills": ["semantic-model-consumption"],
                "missingResults": ["10,000"],
                "durationSeconds": 300.1,
            },
        })
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        self.assertIn('class="status-badge N"', html_str)
        self.assertIn("missing skill", html_str)
        self.assertIn("semantic-model-consumption", html_str)
        self.assertIn("missing result", html_str)
        self.assertIn("10,000", html_str)
        self.assertIn("300.1s", html_str)

    def test_html_renders_duration(self) -> None:
        agg = self._make_aggregated({
            "t": {"isPass": True, "rawStatus": "Y", "durationSeconds": 102.65},
        })
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        # Formatted with 1 decimal place.
        self.assertIn("102.7s", html_str)

    def test_html_renders_dash_when_duration_missing(self) -> None:
        agg = self._make_aggregated({
            "t": {"isPass": True, "rawStatus": "Y"},
        })
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        self.assertIn('class="duration">—</td>', html_str)

    def test_html_renders_per_test_billable_tokens(self) -> None:
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso: {
                            "pass": 1, "fail": 0, "run_id": "1-1", "gh_run_id": "1",
                            "test_results": {"t1": {"isPass": True, "rawStatus": "Y"}},
                            "token_totals": {"t1": {"inputTokens": 4210, "outputTokens": 612, "cacheReadTokens": 0, "cacheWriteTokens": 0, "runCount": 1}},
                            "day_tokens": 4822,
                        }
                    }
                }
            },
            "all_dates": [today_iso], "all_skills": ["sqldw"],
            "totals": {"runs": 1, "skills": 1, "dates": 1},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        # billable = inputTokens + outputTokens (no cache tokens) = 4210 + 612 = 4822
        # Comma-formatted for readability in the per-test row.
        self.assertIn(">4,822</td>", html_str)

    def test_html_renders_dash_when_per_test_tokens_missing(self) -> None:
        # token_totals dict missing entirely from the day record -> em-dash placeholder.
        agg = self._make_aggregated({
            "t1": {"isPass": True, "rawStatus": "Y", "durationSeconds": 12.0},
        })
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        # Expect an em-dash with the meta class in the tokens column of the test row.
        self.assertIn('class="num meta">&mdash;</td>', html_str)

    def test_html_escapes_test_names_in_detail_rows(self) -> None:
        agg = self._make_aggregated({
            "<script>alert(1)</script>": {"isPass": True, "rawStatus": "Y"},
        })
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        self.assertNotIn("<script>alert(1)</script>", html_str)
        self.assertIn("&lt;script&gt;", html_str)

    def test_html_no_details_row_when_no_test_results(self) -> None:
        # by_skill has dates but no test_results field at all
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {"dates": {today_iso: {"pass": 1, "fail": 0, "run_id": "1-1", "gh_run_id": "1"}}},
            },
            "all_dates": [today_iso],
            "all_skills": ["sqldw"],
            "totals": {"runs": 1, "skills": 1, "dates": 1},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        self.assertNotIn('class="details"', html_str)


class LatestColumnPerSkillTests(unittest.TestCase):
    """Reviewer L: 'Latest' must be per-skill, not the global newest date."""

    def test_skill_with_older_run_still_shows_latest(self) -> None:
        # Two skills: sqldw last ran today, powerbi last ran yesterday.
        # Both should show their own latest, not "—" for powerbi.
        today = dt.datetime.now(dt.timezone.utc).date()
        today_iso = today.strftime("%Y-%m-%d")
        yest_iso = (today - dt.timedelta(days=1)).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso: {
                            "pass": 1, "fail": 0, "run_id": "100-1", "gh_run_id": "100",
                            "test_results": {"t": {"isPass": True}},
                        }
                    }
                },
                "powerbi": {
                    "dates": {
                        yest_iso: {
                            "pass": 0, "fail": 1, "run_id": "99-1", "gh_run_id": "99",
                            "test_results": {"t": {"isPass": False}},
                        }
                    }
                },
            },
            "all_dates": [today_iso, yest_iso],
            "all_skills": ["powerbi", "sqldw"],
            "totals": {"runs": 2, "skills": 2, "dates": 2},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        # Both skills must have their latest summary populated (not an em-dash).
        # We check that each skill's row contains a link to its own GH run.
        self.assertIn("actions/runs/100", html_str)
        self.assertIn("actions/runs/99", html_str)
        # Verify each skill's pass-rate cell is populated (not the em-dash
        # placeholder used when latest is missing).
        # sqldw is 100% pass; powerbi is 0%.
        self.assertIn("100%", html_str)
        self.assertIn("0%", html_str)


class SafeUrlTests(unittest.TestCase):
    """Reviewer S: validate flakyIssue URL scheme to prevent javascript: injection."""

    def test_allows_https(self) -> None:
        self.assertEqual(build_dashboard._safe_url("https://example.com/issues/1"), "https://example.com/issues/1")

    def test_allows_http(self) -> None:
        self.assertEqual(build_dashboard._safe_url("http://example.com"), "http://example.com")

    def test_rejects_javascript_scheme(self) -> None:
        self.assertIsNone(build_dashboard._safe_url("javascript:alert(1)"))

    def test_rejects_data_scheme(self) -> None:
        self.assertIsNone(build_dashboard._safe_url("data:text/html,<script>alert(1)</script>"))

    def test_rejects_non_string(self) -> None:
        self.assertIsNone(build_dashboard._safe_url(None))
        self.assertIsNone(build_dashboard._safe_url(42))
        self.assertIsNone(build_dashboard._safe_url({"url": "https://example.com"}))

    def test_case_insensitive_scheme_check(self) -> None:
        self.assertEqual(build_dashboard._safe_url("HTTPS://example.com"), "HTTPS://example.com")
        # Reject mixed-case javascript:
        self.assertIsNone(build_dashboard._safe_url("JavaScript:alert(1)"))

    def test_render_html_drops_unsafe_flaky_url(self) -> None:
        today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        agg = {
            "by_skill": {
                "sqldw": {
                    "dates": {
                        today_iso: {
                            "pass": 1, "fail": 0, "run_id": "1-1", "gh_run_id": "1",
                            "test_results": {
                                "t": {
                                    "isPass": True,
                                    "rawStatus": "F",
                                    "flakyIssue": "javascript:alert(1)",
                                }
                            },
                        }
                    }
                },
            },
            "all_dates": [today_iso],
            "all_skills": ["sqldw"],
            "totals": {"runs": 1, "skills": 1, "dates": 1},
        }
        html_str = build_dashboard.render_html(agg, repo="org/repo", window_days=30)
        # The dangerous URL must not appear inside an href attribute.
        self.assertNotIn('href="javascript:', html_str)
        self.assertNotIn("href='javascript:", html_str)
        # Falls back to text rendering (escaped).
        self.assertIn("javascript:alert(1)", html_str)  # text content allowed (escaped)


class WindowedRunsAttemptDedupeTests(unittest.TestCase):
    """Reviewer T: re-runs (attempts 1 and 2 of same gh_run_id) must count as 1 run."""

    def setUp(self) -> None:
        self.today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    def _make(self, run_id: str, gh_run_id: str) -> dict:
        return {
            "date": self.today_iso,
            "run_id": run_id,
            "gh_run_id": gh_run_id,
            "skill": "sqldw",
            "test_results": {"t": {"isPass": True}},
        }

    def test_two_attempts_of_same_gh_run_count_as_one(self) -> None:
        runs = [
            self._make("12345-1", "12345"),
            self._make("12345-2", "12345"),
        ]
        result = build_dashboard.aggregate_by_skill(runs, window_days=30)
        self.assertEqual(result["totals"]["runs"], 1)

    def test_two_distinct_gh_runs_count_as_two(self) -> None:
        runs = [
            self._make("12345-1", "12345"),
            self._make("67890-1", "67890"),
        ]
        result = build_dashboard.aggregate_by_skill(runs, window_days=30)
        self.assertEqual(result["totals"]["runs"], 2)


# ---------------------------------------------------------------------------
# Full-eval support tests
# ---------------------------------------------------------------------------


def _build_telemetry(date_iso: str, plans: list[dict]) -> dict:
    """Synthesize a valid eval-run-telemetry.json payload for tests."""
    return {
        "schemaVersion": 1,
        "generatedAt": f"{date_iso}T12:34:56.7890+00:00",
        "runner": {"host": "test-runner", "repoRoot": "/repo"},
        "cleanup": {"phase": "cleanup", "status": "completed", "durationSeconds": 1.0},
        "plans": plans,
        "postProcessing": [],
    }


def _plan(plan: str, plan_path: str, status: str = "completed",
          duration: float = 100.0, input_tokens: int = 1000,
          output_tokens: int = 200, exit_code: int = 0,
          bail_code: str | None = None,
          skills_used: list[str] | None = None) -> dict:
    return {
        "plan": plan,
        "planPath": plan_path,
        "status": status,
        "durationSeconds": duration,
        "exitCode": exit_code,
        "bailOutCode": bail_code,
        "session": {
            "assistantTurnCount": 10,
            "toolCallCount": 30,
            "skillsUsed": skills_used or [plan.replace("eval-", "") + "-cli"],
            "tokenUsage": {
                "modelMetrics": {
                    "claude-opus-4.6": {
                        "usage": {
                            "inputTokens": input_tokens,
                            "outputTokens": output_tokens,
                            "cacheReadTokens": 0,
                            "cacheWriteTokens": 0,
                        }
                    }
                }
            },
        },
    }


def _write_fulleval_run(root: Path, run_id: str, telemetry: dict, results_md: str | None = None) -> Path:
    run_dir = root / f"run-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "eval-run-telemetry.json").write_text(json.dumps(telemetry), encoding="utf-8")
    if results_md is not None:
        (run_dir / "eval-results.md").write_text(results_md, encoding="utf-8")
    return run_dir


class ParseEvalResultsMdTests(unittest.TestCase):
    def test_extracts_per_skill_case_tables(self) -> None:
        md = (
            "# Header\n\n"
            "## Summary\n\n"
            "| Skill | Total |\n|-------|------:|\n| **spark-authoring-cli** | 5 |\n\n"
            "## Detailed Results by Skill\n\n"
            "### spark-authoring-cli\n\n"
            "| Case | Title | Result | Notes |\n"
            "|------|-------|--------|-------|\n"
            "| SA-01 | Create Lakehouse | ✅ PASS | All good |\n"
            "| SA-02 | Create Notebook | ❌ FAIL | Timeout |\n"
            "| SA-03 | Negative test | ⏭️ SKIP | N/A in eval |\n"
        )
        out = build_dashboard.parse_eval_results_md(md)
        self.assertIn("spark-authoring-cli", out["perSkill"])
        cases = out["perSkill"]["spark-authoring-cli"]
        self.assertEqual(len(cases), 3)
        self.assertEqual(cases[0]["case"], "SA-01")
        self.assertEqual(cases[0]["result"], "PASS")
        self.assertEqual(cases[1]["result"], "FAIL")
        self.assertEqual(cases[2]["result"], "SKIP")

    def test_returns_empty_when_no_sections(self) -> None:
        self.assertEqual(build_dashboard.parse_eval_results_md(""), {"perSkill": {}})
        self.assertEqual(build_dashboard.parse_eval_results_md("# Title only"), {"perSkill": {}})

    def test_handles_multiple_skill_sections(self) -> None:
        md = (
            "### spark-authoring-cli\n\n"
            "| Case | Title | Result | Notes |\n|------|-------|--------|-------|\n"
            "| SA-01 | A | ✅ PASS |  |\n\n"
            "### sqldw-authoring-cli\n\n"
            "| Case | Title | Result | Notes |\n|------|-------|--------|-------|\n"
            "| DW-01 | B | ❌ FAIL | err |\n"
        )
        out = build_dashboard.parse_eval_results_md(md)
        self.assertEqual(set(out["perSkill"].keys()), {"spark-authoring-cli", "sqldw-authoring-cli"})
        self.assertEqual(out["perSkill"]["sqldw-authoring-cli"][0]["notes"], "err")

    def test_skips_table_separator_and_header_rows(self) -> None:
        md = (
            "### spark-authoring-cli\n\n"
            "| Case | Title | Result | Notes |\n"
            "|------|-------|--------|-------|\n"
            "| SA-01 | Real row | ✅ PASS |  |\n"
        )
        cases = build_dashboard.parse_eval_results_md(md)["perSkill"]["spark-authoring-cli"]
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["case"], "SA-01")


class FamilyOfTests(unittest.TestCase):
    def test_combined_skills_folder_returns_cross_skill(self) -> None:
        self.assertEqual(
            build_dashboard.family_of("plan\\04-combined-skills\\eval-spark-authoring-plus-consumption.md", "eval-spark-authoring-plus-consumption"),
            "Cross-skill",
        )

    def test_foundations_folder_returns_foundation(self) -> None:
        self.assertEqual(
            build_dashboard.family_of("plan/01-foundations/eval-check-updates.md", "eval-check-updates"),
            "Foundation",
        )

    def test_spark_plan_returns_spark(self) -> None:
        self.assertEqual(
            build_dashboard.family_of("plan/03-individual-skills/eval-spark-authoring.md", "eval-spark-authoring"),
            "Spark",
        )

    def test_powerbi_resolves_before_spark(self) -> None:
        # Defensive ordering check: powerbi has no "spark" substring, but the
        # mapping must not mis-classify any other engine.
        self.assertEqual(
            build_dashboard.family_of("plan/03-individual-skills/eval-powerbi-authoring.md", "eval-powerbi-authoring"),
            "Power BI",
        )

    def test_migrations_prefix(self) -> None:
        for slug in ("eval-databricks-migration", "eval-hdinsight-migration", "eval-synapse-migration"):
            self.assertEqual(
                build_dashboard.family_of(f"plan/03-individual-skills/{slug}.md", slug),
                "Migrations",
            )

    def test_backslash_and_forward_slash_paths_equivalent(self) -> None:
        bs = build_dashboard.family_of("plan\\04-combined-skills\\x.md", "eval-medallion")
        fs = build_dashboard.family_of("plan/04-combined-skills/x.md", "eval-medallion")
        self.assertEqual(bs, fs)

    def test_unknown_returns_other(self) -> None:
        self.assertEqual(
            build_dashboard.family_of("plan/99-unknown/eval-mystery.md", "eval-mystery"),
            "Other",
        )


class PlanSlugToSkillNamesTests(unittest.TestCase):
    def test_simple_plan_maps_to_single_skill(self) -> None:
        self.assertEqual(
            build_dashboard._plan_slug_to_skill_names("eval-spark-authoring"),
            ["spark-authoring-cli"],
        )

    def test_plus_plan_maps_to_two_skills(self) -> None:
        self.assertEqual(
            build_dashboard._plan_slug_to_skill_names("eval-spark-authoring-plus-consumption"),
            ["spark-authoring-cli", "spark-consumption-cli"],
        )

    def test_handles_missing_eval_prefix(self) -> None:
        self.assertEqual(
            build_dashboard._plan_slug_to_skill_names("sqldw-consumption"),
            ["sqldw-consumption-cli"],
        )


class DiscoverFullevalRunsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    def test_returns_empty_list_when_root_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "missing"
            self.assertEqual(build_dashboard.discover_fulleval_runs(missing), [])

    def test_returns_empty_list_when_root_is_none(self) -> None:
        # Defensive: main() passes None when the CLI flag is omitted; the
        # discover function must handle that without raising AttributeError.
        self.assertEqual(build_dashboard.discover_fulleval_runs(None), [])

    def test_parses_telemetry_and_extracts_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            telemetry = _build_telemetry(self.today, [
                _plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md"),
            ])
            _write_fulleval_run(root, "555", telemetry)
            runs = build_dashboard.discover_fulleval_runs(root)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["run_id"], "555")
            self.assertEqual(runs[0]["date"], self.today)
            self.assertEqual(len(runs[0]["telemetry"]["plans"]), 1)

    def test_pairs_telemetry_with_sibling_results_md(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            telemetry = _build_telemetry(self.today, [
                _plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md"),
            ])
            md = (
                "### spark-authoring-cli\n\n"
                "| Case | Title | Result | Notes |\n|------|-------|--------|-------|\n"
                "| SA-01 | Lakehouse | ✅ PASS |  |\n"
            )
            _write_fulleval_run(root, "777", telemetry, results_md=md)
            runs = build_dashboard.discover_fulleval_runs(root)
            self.assertIn("spark-authoring-cli", runs[0]["per_skill_cases"])

    def test_skips_malformed_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "run-bad"
            run_dir.mkdir()
            (run_dir / "eval-run-telemetry.json").write_text("not json{", encoding="utf-8")
            runs = build_dashboard.discover_fulleval_runs(root)
            self.assertEqual(runs, [])


class AggregateFullEvalByPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today = dt.datetime.now(dt.timezone.utc).date()

    def _run(self, days_ago: int, run_id: str, plans: list[dict]) -> dict:
        d = (self.today - dt.timedelta(days=days_ago)).strftime("%Y-%m-%d")
        return {
            "date": d,
            "run_id": run_id,
            "telemetry": _build_telemetry(d, plans),
            "per_skill_cases": {},
        }

    def test_in_window_run_counts(self) -> None:
        runs = [self._run(2, "1", [_plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md")])]
        agg = build_dashboard.aggregate_fulleval_by_plan(runs, window_days=30)
        self.assertEqual(agg["totals"]["runs"], 1)
        self.assertEqual(agg["totals"]["plans"], 1)
        self.assertIn("eval-spark-authoring", agg["plans"])

    def test_out_of_window_run_filtered(self) -> None:
        runs = [self._run(60, "1", [_plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md")])]
        agg = build_dashboard.aggregate_fulleval_by_plan(runs, window_days=30)
        self.assertEqual(agg["totals"]["plans"], 0)

    def test_aggregates_tokens_across_models(self) -> None:
        # A real plan often exercises one model per run; the renderer must
        # sum across whatever modelMetrics are present.
        plan_entry = _plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md")
        plan_entry["session"]["tokenUsage"]["modelMetrics"]["gpt-5"] = {
            "usage": {"inputTokens": 500, "outputTokens": 100}
        }
        runs = [self._run(0, "1", [plan_entry])]
        agg = build_dashboard.aggregate_fulleval_by_plan(runs, window_days=30)
        latest = next(iter(agg["plans"]["eval-spark-authoring"]["dates"].values()))
        self.assertEqual(latest["input_tokens"], 1500)
        self.assertEqual(latest["output_tokens"], 300)

    def test_combined_plan_stitches_both_skills(self) -> None:
        runs = [{
            "date": self.today.strftime("%Y-%m-%d"),
            "run_id": "1",
            "telemetry": _build_telemetry(self.today.strftime("%Y-%m-%d"), [
                _plan(
                    "eval-spark-authoring-plus-consumption",
                    "plan/04-combined-skills/eval-spark-authoring-plus-consumption.md",
                    skills_used=["spark-authoring-cli", "spark-consumption-cli"],
                ),
            ]),
            "per_skill_cases": {
                "spark-authoring-cli": [{"case": "SA-01", "title": "X", "result": "PASS", "notes": ""}],
                "spark-consumption-cli": [{"case": "SC-01", "title": "Y", "result": "FAIL", "notes": "z"}],
            },
        }]
        agg = build_dashboard.aggregate_fulleval_by_plan(runs, window_days=30)
        rec = agg["plans"]["eval-spark-authoring-plus-consumption"]
        latest = next(iter(rec["dates"].values()))
        self.assertEqual(len(latest["cases"]), 2)
        self.assertEqual({c["skill"] for c in latest["cases"]}, {"spark-authoring-cli", "spark-consumption-cli"})
        self.assertEqual(latest["pass"], 1)
        self.assertEqual(latest["fail"], 1)
        self.assertEqual(rec["family"], "Cross-skill")

    def test_bailed_out_status_preserved(self) -> None:
        runs = [self._run(0, "1", [
            _plan("eval-sqldw-authoring", "plan/03-individual-skills/eval-sqldw-authoring.md",
                  status="bailed_out", exit_code=998, bail_code="EVAL-BAIL-003"),
        ])]
        agg = build_dashboard.aggregate_fulleval_by_plan(runs, window_days=30)
        latest = next(iter(agg["plans"]["eval-sqldw-authoring"]["dates"].values()))
        self.assertEqual(latest["status"], "bailed_out")
        self.assertEqual(latest["bail_code"], "EVAL-BAIL-003")
        self.assertEqual(latest["exit_code"], 998)


class RenderFullEvalTabTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    def _agg(self, plans: list[dict]) -> dict:
        runs = [{
            "date": self.today_iso,
            "run_id": "42",
            "telemetry": _build_telemetry(self.today_iso, plans),
            "per_skill_cases": {},
        }]
        return build_dashboard.aggregate_fulleval_by_plan(runs, window_days=30)

    def test_empty_agg_renders_in_panel_empty_state(self) -> None:
        body, counts = build_dashboard._render_fulleval_panel_inner(
            {"plans": {}, "all_dates": [], "totals": {"runs": 0, "plans": 0, "dates": 0}},
            "owner/repo", 30,
        )
        self.assertEqual(counts["plans"], 0)
        self.assertIn("empty-state", body)

    def test_renders_status_pill_class(self) -> None:
        agg = self._agg([
            _plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md", status="bailed_out", bail_code="EVAL-BAIL-001"),
        ])
        body, _ = build_dashboard._render_fulleval_panel_inner(agg, "owner/repo", 30)
        self.assertIn("plan-status bailed_out", body)
        self.assertIn("EVAL-BAIL-001", body)

    def test_escapes_plan_path(self) -> None:
        agg = self._agg([
            _plan("eval-spark-authoring", "plan/<script>alert(1)</script>/x.md"),
        ])
        body, _ = build_dashboard._render_fulleval_panel_inner(agg, "owner/repo", 30)
        self.assertNotIn("<script>", body)
        self.assertIn("&lt;script&gt;", body)

    def test_family_grouping_emits_section_headers(self) -> None:
        agg = self._agg([
            _plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md"),
            _plan("eval-eventhouse-authoring", "plan/03-individual-skills/eval-eventhouse-authoring.md"),
        ])
        body, _ = build_dashboard._render_fulleval_panel_inner(agg, "owner/repo", 30)
        self.assertIn(">Spark ", body)
        self.assertIn(">Eventhouse ", body)
        # Spark renders before Eventhouse (declared family order).
        self.assertLess(body.index(">Spark "), body.index(">Eventhouse "))

    def test_plan_status_error_counted_as_errored(self) -> None:
        # Producer (tests/run-full-tests.ps1 Get-RunStatus) emits "error" --
        # NOT "failed" -- when ExitCode != 0. If the renderer only counts
        # "failed"/"timed_out", an errored run reads "0 errored" and the
        # dashboard looks healthier than reality.
        agg = self._agg([
            _plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md", status="error", exit_code=1),
        ])
        body, _ = build_dashboard._render_fulleval_panel_inner(agg, "owner/repo", 30)
        self.assertIn(">1 errored<", body)
        self.assertIn("plan-status error", body)
        # And NOT a phantom "1 completed".
        self.assertIn(">0 completed<", body)

    def test_skipped_plan_status_summarized_when_nonzero(self) -> None:
        agg = self._agg([
            _plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md", status="skipped_warehouse"),
        ])
        body, _ = build_dashboard._render_fulleval_panel_inner(agg, "owner/repo", 30)
        self.assertIn(">1 skipped<", body)
        # Status pill on the row uses the raw class name.
        self.assertIn("plan-status skipped_warehouse", body)

    def test_skipped_chip_omitted_when_zero(self) -> None:
        agg = self._agg([
            _plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md", status="completed"),
        ])
        body, _ = build_dashboard._render_fulleval_panel_inner(agg, "owner/repo", 30)
        self.assertNotIn(">0 skipped<", body)

    def test_case_result_error_counts_against_pass_rate(self) -> None:
        # ERROR test rows are failures (infra missing / non-zero exit),
        # not skips. They must count against the executed denominator so
        # that a "5P/0F/3E" plan reads as 5/8 = 62%, not 5/5 = 100%.
        runs = [{
            "date": self.today_iso,
            "run_id": "42",
            "telemetry": _build_telemetry(self.today_iso, [
                _plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md"),
            ]),
            "per_skill_cases": {
                "spark-authoring-cli": [
                    {"case": "SA-01", "title": "t", "result": "PASS", "notes": ""},
                    {"case": "SA-02", "title": "t", "result": "PASS", "notes": ""},
                    {"case": "SA-03", "title": "t", "result": "PASS", "notes": ""},
                    {"case": "SA-04", "title": "t", "result": "PASS", "notes": ""},
                    {"case": "SA-05", "title": "t", "result": "PASS", "notes": ""},
                    {"case": "SA-06", "title": "t", "result": "ERROR", "notes": "infra"},
                    {"case": "SA-07", "title": "t", "result": "ERROR", "notes": "infra"},
                    {"case": "SA-08", "title": "t", "result": "ERROR", "notes": "infra"},
                ],
            },
        }]
        agg = build_dashboard.aggregate_fulleval_by_plan(runs, window_days=30)
        body, _ = build_dashboard._render_fulleval_panel_inner(agg, "owner/repo", 30)
        # 5 pass / 8 executed = 62% (rounded). NOT 100%.
        self.assertIn("5/8", body)
        self.assertIn("62%", body)
        self.assertNotIn("100%", body)
        # Test-level summary surfaces the error count separately.
        self.assertIn("3 error", body)

    def test_error_badge_label_distinct_from_fail(self) -> None:
        runs = [{
            "date": self.today_iso,
            "run_id": "42",
            "telemetry": _build_telemetry(self.today_iso, [
                _plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md"),
            ]),
            "per_skill_cases": {
                "spark-authoring-cli": [
                    {"case": "SA-01", "title": "t", "result": "FAIL", "notes": ""},
                    {"case": "SA-02", "title": "t", "result": "ERROR", "notes": "infra missing"},
                ],
            },
        }]
        agg = build_dashboard.aggregate_fulleval_by_plan(runs, window_days=30)
        body, _ = build_dashboard._render_fulleval_panel_inner(agg, "owner/repo", 30)
        # Both render with the "N" CSS class but distinct labels (N vs E).
        self.assertIn('status-badge N">N</span>', body)
        self.assertIn('status-badge N">E</span>', body)


class FullEvalErrorAndSkipHandlingTests(unittest.TestCase):
    """Regression coverage for rubber-duck findings: producer emits status
    "error" for non-zero exit codes (not "failed"/"timed_out"), markdown
    test rows use "ERROR" as a distinct fourth result bucket, and the
    skipped_warehouse / skipped_lakehouse variants must not lose visibility."""

    def test_normalize_eval_result_handles_error_bucket(self) -> None:
        # ERROR maps to its own bucket -- not OTHER (which would silently
        # drop ERROR rows out of every count).
        self.assertEqual(build_dashboard._normalize_eval_result("ERROR"), "ERROR")
        self.assertEqual(build_dashboard._normalize_eval_result("❌ ERROR"), "ERROR")
        self.assertEqual(build_dashboard._normalize_eval_result("EVAL-BAIL-001: ERROR"), "ERROR")
        self.assertEqual(build_dashboard._normalize_eval_result("✅ PASS"), "PASS")
        self.assertEqual(build_dashboard._normalize_eval_result("❌ FAIL"), "FAIL")
        self.assertEqual(build_dashboard._normalize_eval_result("⏭️ SKIP"), "SKIP")
        self.assertEqual(build_dashboard._normalize_eval_result("---"), "OTHER")


class FullEvalSameDayRerunOrderingTests(unittest.TestCase):
    """Regression coverage for the lex-string-compare bug: when two
    same-day runs land for the same plan, the LATER run (by numeric
    run_id) must win. String compare would let "9" beat "10" because
    "9" > "10" lexicographically."""

    def setUp(self) -> None:
        self.today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    def test_numeric_run_id_compare_picks_newer_run(self) -> None:
        # Run "10" must beat run "9" even though "9" > "10" under lex compare.
        runs = [
            {
                "date": self.today_iso,
                "run_id": "9",
                "telemetry": _build_telemetry(self.today_iso, [
                    _plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md", status="error", exit_code=1),
                ]),
                "per_skill_cases": {},
            },
            {
                "date": self.today_iso,
                "run_id": "10",
                "telemetry": _build_telemetry(self.today_iso, [
                    _plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md", status="completed"),
                ]),
                "per_skill_cases": {},
            },
        ]
        agg = build_dashboard.aggregate_fulleval_by_plan(runs, window_days=30)
        rec = agg["plans"]["eval-spark-authoring"]["dates"][self.today_iso]
        self.assertEqual(rec["run_id"], "10")
        self.assertEqual(rec["status"], "completed")

    def test_numeric_run_id_compare_preserves_iteration_order_for_ties(self) -> None:
        runs = [
            {
                "date": self.today_iso,
                "run_id": "100",
                "telemetry": _build_telemetry(self.today_iso, [
                    _plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md", status="completed"),
                ]),
                "per_skill_cases": {},
            },
            {
                "date": self.today_iso,
                "run_id": "100",
                "telemetry": _build_telemetry(self.today_iso, [
                    _plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md", status="error", exit_code=1),
                ]),
                "per_skill_cases": {},
            },
        ]
        agg = build_dashboard.aggregate_fulleval_by_plan(runs, window_days=30)
        rec = agg["plans"]["eval-spark-authoring"]["dates"][self.today_iso]
        # Tie -- existing wins (the loop sees first record first).
        self.assertEqual(rec["status"], "completed")


class DateFromGeneratedAtTests(unittest.TestCase):
    """Coverage for _date_from_generated_at: the producer can emit a few
    legitimate variants (timezone-aware, naive, 7-digit subseconds). The
    function must normalize all of them to a UTC date string or return
    None for unparseable input."""

    def test_tz_aware_iso_string(self) -> None:
        # +03:00 is 21:34 UTC on the previous date is NOT this case --
        # 12:34:56 +03:00 is 09:34:56 UTC same date.
        self.assertEqual(
            build_dashboard._date_from_generated_at("2026-05-13T12:34:56.789+03:00"),
            "2026-05-13",
        )

    def test_tz_aware_offset_rolls_date_back(self) -> None:
        # 02:34:56 in +05:00 is 21:34:56 UTC previous day.
        self.assertEqual(
            build_dashboard._date_from_generated_at("2026-05-13T02:34:56+05:00"),
            "2026-05-12",
        )

    def test_naive_iso_string_treated_as_utc(self) -> None:
        self.assertEqual(
            build_dashboard._date_from_generated_at("2026-05-13T12:34:56"),
            "2026-05-13",
        )

    def test_seven_digit_fractional_seconds(self) -> None:
        # Python 3.11+ rejects >6 digit subseconds; the helper must
        # gracefully fall back by truncating.
        self.assertEqual(
            build_dashboard._date_from_generated_at("2026-05-13T12:34:56.7890123+00:00"),
            "2026-05-13",
        )

    def test_z_suffix(self) -> None:
        # fromisoformat handles "Z" suffix on Python 3.11+.
        self.assertEqual(
            build_dashboard._date_from_generated_at("2026-05-13T12:34:56Z"),
            "2026-05-13",
        )

    def test_returns_none_for_unparseable(self) -> None:
        self.assertIsNone(build_dashboard._date_from_generated_at(""))
        self.assertIsNone(build_dashboard._date_from_generated_at(None))
        self.assertIsNone(build_dashboard._date_from_generated_at("not a date"))
        self.assertIsNone(build_dashboard._date_from_generated_at(12345))


class RenderHtmlTabUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    def _smoke_agg(self, skills_present: bool) -> dict:
        runs: list[dict] = []
        if skills_present:
            runs.append({
                "date": self.today_iso,
                "run_id": "1-1",
                "gh_run_id": "1",
                "skill": "sqldw",
                "test_results": {"t1": {"isPass": True}},
            })
        return build_dashboard.aggregate_by_skill(runs, window_days=30)

    def _fe_agg(self, plans_present: bool) -> dict:
        if not plans_present:
            return {"plans": {}, "all_dates": [], "totals": {"runs": 0, "plans": 0, "dates": 0}}
        runs = [{
            "date": self.today_iso,
            "run_id": "42",
            "telemetry": _build_telemetry(self.today_iso, [
                _plan("eval-spark-authoring", "plan/03-individual-skills/eval-spark-authoring.md"),
            ]),
            "per_skill_cases": {},
        }]
        return build_dashboard.aggregate_fulleval_by_plan(runs, window_days=30)

    def test_no_fe_arg_renders_single_tab_page(self) -> None:
        html_str = build_dashboard.render_html(self._smoke_agg(True), repo="owner/repo", window_days=30)
        self.assertNotIn('id="tab-smoke"', html_str)
        self.assertNotIn('id="tab-fulleval"', html_str)
        # Title preserves the pre-PR wording for the smoke-only page.
        self.assertIn("smoke dashboard", html_str)

    def test_fe_arg_renders_tabs(self) -> None:
        html_str = build_dashboard.render_html(
            self._smoke_agg(True), repo="owner/repo", window_days=30,
            aggregated_fulleval=self._fe_agg(True), fulleval_window_days=60,
        )
        self.assertIn('id="tab-smoke"', html_str)
        self.assertIn('id="tab-fulleval"', html_str)
        self.assertIn('id="panel-smoke"', html_str)
        self.assertIn('id="panel-fulleval"', html_str)
        # The plan slug must appear in the rendered HTML.
        self.assertIn("eval-spark-authoring", html_str)

    def test_aria_labelledby_points_at_visible_label_not_radio_input(self) -> None:
        # Regression: PR #254 bot review flagged that aria-labelledby
        # pointed at the radio input IDs (which are off-screen / presentational)
        # rather than at the visible tab labels.
        html_str = build_dashboard.render_html(
            self._smoke_agg(True), repo="owner/repo", window_days=30,
            aggregated_fulleval=self._fe_agg(True), fulleval_window_days=60,
        )
        self.assertIn('id="tab-label-smoke"', html_str)
        self.assertIn('id="tab-label-fulleval"', html_str)
        self.assertIn('aria-labelledby="tab-label-smoke"', html_str)
        self.assertIn('aria-labelledby="tab-label-fulleval"', html_str)
        # aria-controls links the label to its panel.
        self.assertIn('aria-controls="panel-smoke"', html_str)
        self.assertIn('aria-controls="panel-fulleval"', html_str)
        # And aria-labelledby must NOT point at the off-screen radio input.
        self.assertNotIn('aria-labelledby="tab-smoke"', html_str)
        self.assertNotIn('aria-labelledby="tab-fulleval"', html_str)

    def test_empty_smoke_with_fe_data_still_renders_tabs(self) -> None:
        # When fulleval data is present but smoke is empty, we should NOT
        # emit the original whole-page empty state. The reviewer should see
        # both tabs with an in-panel "no smoke data" message in the smoke tab.
        html_str = build_dashboard.render_html(
            self._smoke_agg(False), repo="owner/repo", window_days=30,
            aggregated_fulleval=self._fe_agg(True), fulleval_window_days=60,
        )
        self.assertIn('id="tab-smoke"', html_str)
        self.assertIn('id="tab-fulleval"', html_str)

    def test_empty_smoke_no_fe_returns_original_empty_state(self) -> None:
        # Backward-compat: when no fulleval input was provided, an empty
        # smoke dashboard must still render the single-page empty state.
        html_str = build_dashboard.render_html(
            self._smoke_agg(False), repo="owner/repo", window_days=30,
        )
        self.assertIn("No smoke-results artifacts found", html_str)


class CssNoDuplicateSelectorTests(unittest.TestCase):
    """Regression for PR #254 bot review: `.plan-status.timed_out` was
    defined twice in each theme block (once in a grouped selector, once
    as a standalone rule). Guard against the same regression recurring
    by counting occurrences of each `.plan-status.<x>` standalone rule
    in the CSS module string.
    """

    def test_plan_status_selectors_have_at_most_one_standalone_rule(self) -> None:
        css = build_dashboard.CSS
        # A "standalone rule" is a line starting with `.plan-status.<word>`
        # followed by whitespace and `{` -- i.e. NOT part of a grouped
        # comma-list selector. Comma-grouped rules end the line with `,`.
        import re as _re
        # Match `.plan-status.NAME{...}` rules where NAME is the last
        # selector before `{` (not in a comma group).
        # Pattern: line starts (optional whitespace) with `.plan-status.<word>`
        # and the rest of the line up to `{` contains no comma.
        statuses = ["completed", "bailed_out", "failed", "error", "timed_out",
                    "skipped", "skipped_warehouse", "skipped_lakehouse", "not_run"]
        for status in statuses:
            pattern = _re.compile(
                r"^\s*\.plan-status\." + _re.escape(status) + r"\s*\{",
                _re.MULTILINE,
            )
            matches = pattern.findall(css)
            # One match in light theme + one in dark theme = max 2.
            # Grouped selectors (`.x, .y { ... }`) don't match because
            # the line ends with `,` before reaching `{`.
            self.assertLessEqual(
                len(matches), 2,
                f"`.plan-status.{status}` standalone rule appears {len(matches)} "
                f"times in CSS; max 2 (one per theme). Likely a duplicate.",
            )


# ---------------------------------------------------------------------------
# Vally producer support: deep-link discovery, render-side disclosure, and
# back-compat snapshot for legacy-only input. Added in the vally dashboard
# ingest PR (the schema additions are OPTIONAL per docs/skill-test-result-schema.md,
# so legacy artifacts continue to render without producing any of the new DOM).
# ---------------------------------------------------------------------------


def _write_results_with_deeplinks(root: Path, date: str, run_id: str, skill: str,
                                  results: dict, deep_links: dict) -> Path:
    """Helper: write testResults.json + deepLinks.json sibling for a vally fixture."""
    skill_dir = root / date / run_id / skill
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "testResults.json").write_text(json.dumps(results), encoding="utf-8")
    (skill_dir / "deepLinks.json").write_text(json.dumps(deep_links), encoding="utf-8")
    return skill_dir / "testResults.json"


class VallyDeepLinksDiscoveryTests(unittest.TestCase):
    def test_discover_runs_reads_sibling_deeplinks_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            _write_results_with_deeplinks(
                root, today_iso, "999-1", "vally-skill",
                {"t1": {"isPass": False, "rawStatus": "N", "message": ""}},
                {
                    "runId": "999-1",
                    "jobs": {"shard1": 777},
                    "artifacts": {"smoke-results-schema-vally-999-1": 444},
                    "stimFailures": [
                        {"stim": "t1", "shard": "shard1", "grader": "verify-foo", "rootCause": "ContentMismatch", "logLineOffset": 42}
                    ],
                },
            )
            runs = build_dashboard.discover_runs(root)
            self.assertEqual(len(runs), 1)
            self.assertIsNotNone(runs[0]["deep_links"])
            self.assertEqual(runs[0]["deep_links"]["runId"], "999-1")
            self.assertEqual(runs[0]["deep_links"]["jobs"]["shard1"], 777)

    def test_deep_links_defaults_none_when_sibling_missing(self) -> None:
        # Legacy artifact has no deepLinks.json. discover_runs must default
        # deep_links to None so the renderer degrades cleanly.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            _write_results(root, today_iso, "100-1", "legacy-skill", {"t": {"isPass": True}})
            runs = build_dashboard.discover_runs(root)
            self.assertIsNone(runs[0]["deep_links"])

    def test_malformed_deeplinks_json_warns_and_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            skill_dir = root / today_iso / "1-1" / "sk"
            skill_dir.mkdir(parents=True)
            (skill_dir / "testResults.json").write_text(json.dumps({"t": {"isPass": True}}), encoding="utf-8")
            (skill_dir / "deepLinks.json").write_text("not json", encoding="utf-8")
            runs = build_dashboard.discover_runs(root)
            self.assertEqual(len(runs), 1)
            self.assertIsNone(runs[0]["deep_links"])

    def test_malformed_deeplinks_still_buckets_run_as_vally_producer(self) -> None:
        # Producer detection must key off file PRESENCE, not parse success.
        # If a vally run ships a corrupt deepLinks.json (gh API hiccup,
        # truncated upload, etc.), the run should still land in the Vally
        # tab -- malformed JSON degrades deep-link rendering only, not the
        # producer bucket itself. Otherwise corrupt-deepLinks runs would
        # vanish from the Vally tab and silently pollute the legacy tab.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            skill_dir = root / today_iso / "9-1" / "vally-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "testResults.json").write_text(json.dumps({"t": {"isPass": True}}), encoding="utf-8")
            (skill_dir / "deepLinks.json").write_text("not json", encoding="utf-8")
            runs = build_dashboard.discover_runs(root)
            self.assertEqual(len(runs), 1)
            self.assertIsNone(runs[0]["deep_links"])  # parse failure -> None data
            self.assertEqual(runs[0]["producer"], "vally")  # but still vally bucket

    def test_legacy_run_without_deeplinks_file_is_bucketed_as_legacy(self) -> None:
        # Counterpart of the test above: no deepLinks.json sibling -> legacy.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            _write_results(root, today_iso, "1-1", "legacy-skill",
                           {"t1": {"isPass": True, "message": "Smoke status: Y"}})
            runs = build_dashboard.discover_runs(root)
            self.assertEqual(runs[0]["producer"], "legacy")


class VallyDeepLinkURLCompositionTests(unittest.TestCase):
    """Per Avi's four URL patterns:
      1. skill-row run page:    /actions/runs/{run_id}
      2. failing-shard chip:    /actions/runs/{run_id}/job/{job_id}
      3. per-stim line anchor:  /actions/runs/{run_id}/job/{job_id}#step:N:LINE
      4. raw artifact page:     /actions/runs/{run_id}/artifacts/{artifact_id}
    """

    def _render(self, deep_links: dict, results: dict) -> str:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            _write_results_with_deeplinks(root, today_iso, "55555-1", "vskill",
                                          results, deep_links)
            runs = build_dashboard.discover_runs(root)
            aggregated = build_dashboard.aggregate_by_skill(runs, 30)
            return build_dashboard.render_html(aggregated, "gim-home/skills-for-fabric", 30)

    def test_skill_row_run_page_link_pattern(self) -> None:
        # Always rendered on the main skill row regardless of deep_links.
        html_str = self._render(
            {"runId": "55555-1", "jobs": {}, "artifacts": {}, "stimFailures": []},
            {"t": {"isPass": True}},
        )
        self.assertIn("https://github.com/gim-home/skills-for-fabric/actions/runs/55555", html_str)

    def test_run_links_use_logs_text_label_not_bare_arrow(self) -> None:
        # The "logs" text-label affordance replaces the prior bare-arrow
        # link. Regression-pin so a future refactor doesn't silently
        # revert to the harder-to-find icon-only form.
        html_str = self._render(
            {"runId": "55555-1", "jobs": {}, "artifacts": {}, "stimFailures": []},
            {"t": {"isPass": True}},
        )
        # New text-label affordance present + tooltip rewritten.
        self.assertIn('class="run-link"', html_str)
        self.assertIn('title="Open the GitHub Actions run"', html_str)
        self.assertIn("logs", html_str)
        # CSS class definition shipped in the stylesheet.
        self.assertIn('a.run-link {', html_str)
        # The old icon-only anchor (no class, old tooltip) should be gone.
        self.assertNotIn('title="GitHub Actions run">', html_str)

    def test_multiple_graders_render_with_status_column(self) -> None:
        # When a stim has multiple graders (passing + failing), the
        # disclosure shows ALL of them in the inline grader-grid table
        # with a Status column so the reviewer can see the triage
        # context ("3 of 8 passed, 5 failed") rather than just the
        # failure count.
        html_str = self._render(
            {
                "runId": "55555-1",
                "jobs": {},
                "artifacts": {},
                "stimGraders": [
                    {"stim": "failingTest", "shard": "shard1", "grader": "wall-time-budget",
                     "passed": False, "rootCause": "WallTimeBudget", "evidence": "Exceeded 300s"},
                    {"stim": "failingTest", "shard": "shard1", "grader": "tool-routing",
                     "passed": False, "rootCause": "Routing", "evidence": "Wrong skill loaded"},
                    {"stim": "failingTest", "shard": "shard1", "grader": "token-budget",
                     "passed": False, "rootCause": "TokenBudget", "evidence": "Exceeded 50000 tokens"},
                    {"stim": "failingTest", "shard": "shard1", "grader": "expected-output",
                     "passed": True},
                    {"stim": "failingTest", "shard": "shard1", "grader": "no-crash",
                     "passed": True},
                ],
            },
            {"failingTest": {"isPass": False, "rawStatus": "N", "message": ""}},
        )
        # Summary uses the X of Y form (3 failed out of 5 total).
        self.assertIn("3 of 5 graders failed", html_str)
        # All 5 grader names appear in the body (failing + passing).
        for grader in ("wall-time-budget", "tool-routing", "token-budget",
                       "expected-output", "no-crash"):
            self.assertIn(grader, html_str)
        # Rootcause chips appear only for the failing graders.
        for rc in ("rc-WallTimeBudget", "rc-Routing", "rc-TokenBudget"):
            self.assertIn(rc, html_str)
        # Status column shows both PASS and FAIL chips.
        self.assertIn('status-chip status-pass">PASS', html_str)
        self.assertIn('status-chip status-fail">FAIL', html_str)
        # Evidence text appears only for failing graders.
        self.assertIn("Exceeded 300s", html_str)
        self.assertIn('class="grader-grid"', html_str)
        # Failing rows are tagged so the CSS can deemphasize passing rows.
        self.assertIn('class="row-failing"', html_str)
        self.assertIn('class="row-passing"', html_str)

    def test_all_graders_failed_uses_clean_x_of_y_form(self) -> None:
        html_str = self._render(
            {
                "runId": "55555-1",
                "jobs": {},
                "artifacts": {},
                "stimGraders": [
                    {"stim": "failingTest", "shard": "shard1", "grader": "g1",
                     "passed": False, "rootCause": "Other", "evidence": "x"},
                    {"stim": "failingTest", "shard": "shard1", "grader": "g2",
                     "passed": False, "rootCause": "Other", "evidence": "y"},
                ],
            },
            {"failingTest": {"isPass": False, "rawStatus": "N", "message": ""}},
        )
        # All 2 of 2 failed.
        self.assertIn("2 of 2 graders failed", html_str)

    def test_single_grader_uses_singular_summary(self) -> None:
        html_str = self._render(
            {
                "runId": "55555-1",
                "jobs": {},
                "artifacts": {},
                "stimGraders": [
                    {"stim": "failingTest", "shard": "shard1", "grader": "one-grader",
                     "passed": False, "rootCause": "ContentMismatch", "evidence": "off by one"},
                ],
            },
            {"failingTest": {"isPass": False, "rawStatus": "N", "message": ""}},
        )
        # Singular form when total is 1.
        self.assertIn("1 of 1 grader failed", html_str)
        self.assertNotIn("1 of 1 graders failed", html_str)

    def test_back_compat_with_stim_failures_only_shape(self) -> None:
        # Older producer artifacts (or external consumers) may still ship
        # the failing-only `stimFailures` array. Renderer must fall back
        # to it and synthesise passed=False entries.
        html_str = self._render(
            {
                "runId": "55555-1",
                "jobs": {},
                "artifacts": {},
                "stimFailures": [
                    {"stim": "failingTest", "shard": "shard1", "grader": "old-format-grader",
                     "rootCause": "Other", "evidence": "from old shape"},
                ],
            },
            {"failingTest": {"isPass": False, "rawStatus": "N", "message": ""}},
        )
        # Treated as 1 of 1 failing graders (no passing context available).
        self.assertIn("1 of 1 grader failed", html_str)
        self.assertIn("old-format-grader", html_str)
        self.assertIn("from old shape", html_str)

    def test_rootcause_chip_renders_with_class(self) -> None:
        html_str = self._render(
            {
                "runId": "55555-1",
                "jobs": {"shard1": 1234},
                "artifacts": {},
                "stimGraders": [
                    {"stim": "failingTest", "shard": "shard1", "grader": "wall-time-budget",
                     "passed": False, "rootCause": "WallTimeBudget", "evidence": "x"}
                ],
            },
            {"failingTest": {"isPass": False, "rawStatus": "N", "message": ""}},
        )
        self.assertIn('class="rootcause-chip rc-WallTimeBudget"', html_str)

    def test_rootcause_unexpected_chars_are_sanitized_for_css_class(self) -> None:
        # Producer data is external; an unexpected rootCause value with
        # spaces, slashes, quotes, etc. would either break styling or
        # inject unintended CSS classes. The class token gets sanitized
        # (alphanumeric + dash + underscore only), separate from the
        # html-escaped display text.
        html_str = self._render(
            {
                "runId": "55555-1",
                "jobs": {},
                "artifacts": {},
                "stimGraders": [
                    {"stim": "failingTest", "shard": "shard1", "grader": "g",
                     "passed": False, "rootCause": "Foo bar /baz\"qux<x>",
                     "evidence": "e"},
                ],
            },
            {"failingTest": {"isPass": False, "rawStatus": "N", "message": ""}},
        )
        # Class token contains only [A-Za-z0-9_-]; unsafe chars folded to '-'.
        # No raw spaces / slashes / quotes leaking into the class attribute.
        self.assertIn('rc-Foo-bar--baz-qux-x-', html_str)
        # Class attribute does NOT contain raw whitespace from the input.
        self.assertNotIn('rc-Foo bar', html_str)
        # Display text is html-escaped (the unescaped " or < would break
        # the surrounding span attribute or open a new tag).
        self.assertNotIn('Foo bar /baz"qux<x>', html_str)

    def test_rootcause_empty_falls_back_to_other_class(self) -> None:
        html_str = self._render(
            {
                "runId": "55555-1",
                "jobs": {},
                "artifacts": {},
                "stimGraders": [
                    {"stim": "failingTest", "shard": "shard1", "grader": "g",
                     "passed": False, "rootCause": "", "evidence": "e"},
                ],
            },
            {"failingTest": {"isPass": False, "rawStatus": "N", "message": ""}},
        )
        # Empty rootCause -> renderer uses 'Other' as the default both in
        # the class token and the display chip text.
        self.assertIn('rc-Other', html_str)

    def test_failing_row_class_has_matching_css_rule(self) -> None:
        # Regression pin: the renderer emits <tr class="row-failing">
        # for each failing grader inside the disclosure. The stylesheet
        # MUST carry a matching `.grader-grid tr.row-failing` rule that
        # paints the row background -- the changeset promises "Failing
        # rows pick up a red-tint background" and there was previously
        # no CSS rule wired to the class.
        html_str = self._render(
            {
                "runId": "55555-1",
                "jobs": {},
                "artifacts": {},
                "stimGraders": [
                    {"stim": "failingTest", "shard": "shard1", "grader": "g",
                     "passed": False, "rootCause": "Other", "evidence": "x"}
                ],
            },
            {"failingTest": {"isPass": False, "rawStatus": "N", "message": ""}},
        )
        # The row carries the class...
        self.assertIn('class="row-failing"', html_str)
        # ...AND the stylesheet has a matching rule. The selector is
        # `.grader-grid tr.row-failing`; gate on the substring so a
        # whitespace-only refactor doesn't false-fail.
        self.assertIn('.grader-grid tr.row-failing', html_str)

    def test_legacy_render_failure_disclosure_function_removed(self) -> None:
        # The dead-code back-compat shim `_render_failure_disclosure`
        # had no in-repo callers and was deleted. Lock it down so a
        # future refactor doesn't accidentally bring it back without
        # a real consumer + a real test.
        self.assertFalse(
            hasattr(build_dashboard, "_render_failure_disclosure"),
            "Dead-code shim _render_failure_disclosure was deleted; if "
            "you reintroduce it, add a real caller + tests first.",
        )

    def test_aggregate_by_skill_preserves_producer_field(self) -> None:
        # Producer must flow through aggregation so render-side styling
        # can key off producer identity (not deep_links parse success).
        # Without this preservation, a vally run with corrupt deepLinks
        # silently lost vally-only styling at the render layer.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            _write_results_with_deeplinks(
                root, today_iso, "v-1", "vally-skill",
                {"t": {"isPass": True, "rawStatus": "Y"}},
                {"runId": "v-1", "jobs": {}, "artifacts": {}, "stimGraders": []},
            )
            runs = build_dashboard.discover_runs(root)
            agg = build_dashboard.aggregate_by_skill(runs, 30)
            date_entry = agg["by_skill"]["vally-skill"]["dates"][today_iso]
            self.assertEqual(date_entry["producer"], "vally",
                             "aggregate_by_skill must propagate the `producer` field "
                             "from discover_runs onto each per-date entry")

    def test_failing_row_styling_keys_off_producer_not_deep_links_parse_success(self) -> None:
        # A vally run whose deepLinks.json is present-but-malformed:
        #   - producer = "vally" (by file-presence)
        #   - deep_links = None (parse failed)
        # The renderer MUST still apply vally-only row styling
        # (tr class="failing") based on producer identity. Only the
        # disclosure CONTENT degrades on parse failure, not the
        # overall vally-only styling.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            skill_dir = root / today_iso / "v-1" / "vally-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "testResults.json").write_text(
                json.dumps({"t": {"isPass": False, "rawStatus": "N"}}), encoding="utf-8"
            )
            # Malformed JSON -> parse fails -> deep_links=None, but
            # producer should still be "vally" by file presence.
            (skill_dir / "deepLinks.json").write_text("not json", encoding="utf-8")
            runs = build_dashboard.discover_runs(root)
            self.assertEqual(runs[0]["producer"], "vally")
            self.assertIsNone(runs[0]["deep_links"])
            # Render and assert the failing row picks up the vally
            # row-styling class even though deep_links is None.
            agg_legacy = build_dashboard.aggregate_by_skill([], 30)
            agg_vally = build_dashboard.aggregate_by_skill(runs, 30)
            html_str = build_dashboard.render_html(
                agg_legacy, "owner/repo", 30, aggregated_vally=agg_vally,
            )
            # The vally row carries the failing class even with corrupt deepLinks.
            self.assertIn('<tr class="failing">', html_str)

    def test_legacy_failing_row_does_NOT_get_vally_failing_class(self) -> None:
        # Counterpart: a legacy run with a failing test must NOT get
        # the `tr class="failing"` class even though its row IS failing.
        # The class is vally-only styling; legacy rendering must stay
        # byte-stable vs the pre-PR snapshot.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            _write_results(root, today_iso, "1-1", "legacy-skill",
                           {"t1": {"isPass": False, "message": "Smoke status: N"}})
            runs = build_dashboard.discover_runs(root)
            self.assertEqual(runs[0]["producer"], "legacy")
            agg = build_dashboard.aggregate_by_skill(runs, 30)
            html_str = build_dashboard.render_html(agg, "owner/repo", 30)
            self.assertNotIn('<tr class="failing">', html_str)

    def test_disclosure_omitted_for_passing_tests(self) -> None:
        # A passing test row must NOT get a failure-disclosure block even
        # if its name appears in stimFailures (deep_links may carry stale
        # data on the rare case of a flaky stim recovery).
        html_str = self._render(
            {
                "runId": "55555-1",
                "jobs": {"shard1": 1234},
                "artifacts": {},
                "stimFailures": [
                    {"stim": "passingTest", "shard": "shard1", "grader": "g", "rootCause": "Routing"}
                ],
            },
            {"passingTest": {"isPass": True, "rawStatus": "Y", "message": ""}},
        )
        # Passing rows have no failing class and no failure-disclosure
        # DIV (the CSS class name appears in the shared stylesheet
        # unconditionally; the assertion checks for the rendered
        # element form so it doesn't accidentally match CSS rules).
        self.assertNotIn('<div class="failure-disclosure"', html_str)


class VallyOnlyAndMixedProducerTests(unittest.TestCase):
    def test_vally_only_fixture_renders_skill_row(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            _write_results_with_deeplinks(
                root, today_iso, "abc-1", "vally-only-skill",
                {"t1": {"isPass": True, "rawStatus": "Y"}, "t2": {"isPass": False, "rawStatus": "N"}},
                {"runId": "abc-1", "jobs": {"shard1": 100}, "artifacts": {}, "stimFailures": [
                    {"stim": "t2", "shard": "shard1", "grader": "g", "rootCause": "ContentMismatch"}
                ]},
            )
            runs = build_dashboard.discover_runs(root)
            aggregated = build_dashboard.aggregate_by_skill(runs, 30)
            html_str = build_dashboard.render_html(aggregated, "owner/repo", 30)
            self.assertIn("vally-only-skill", html_str)
            self.assertIn("rc-ContentMismatch", html_str)

    def test_mixed_producer_renders_legacy_and_vally_in_separate_tabs(self) -> None:
        # Both producers land under the same artifacts-in/ -- the dashboard
        # buckets them by producer (deepLinks.json sibling presence) and
        # renders separate "Smoke (legacy)" and "Vally" tabs. Users said
        # they want the tabs visually separated until the legacy harness
        # is retired; merging the two tables hid which producer owned
        # which row at a glance.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            # Legacy skill (no deepLinks.json sibling).
            _write_results(root, today_iso, "111-1", "sqldw",
                           {"t1": {"isPass": False, "rawStatus": "N", "message": "Smoke status: N"}})
            # Vally skill (deepLinks.json sibling).
            _write_results_with_deeplinks(
                root, today_iso, "222-1", "vally-skill",
                {"v1": {"isPass": False, "rawStatus": "N", "message": ""}},
                {"runId": "222-1", "jobs": {"shard1": 555}, "artifacts": {}, "stimFailures": [
                    {"stim": "v1", "shard": "shard1", "grader": "g", "rootCause": "Routing"}
                ]},
            )
            all_runs = build_dashboard.discover_runs(root)
            self.assertEqual(len(all_runs), 2)
            # Producer tagging happens in discover_runs.
            producers = {r["skill"]: r["producer"] for r in all_runs}
            self.assertEqual(producers["sqldw"], "legacy")
            self.assertEqual(producers["vally-skill"], "vally")

            legacy_runs = [r for r in all_runs if r["producer"] != "vally"]
            vally_runs = [r for r in all_runs if r["producer"] == "vally"]
            agg_legacy = build_dashboard.aggregate_by_skill(legacy_runs, 30)
            agg_vally = build_dashboard.aggregate_by_skill(vally_runs, 30)
            html_str = build_dashboard.render_html(
                agg_legacy, "owner/repo", 30, aggregated_vally=agg_vally,
            )
            # Two tabs: Smoke (legacy) + Vally.
            self.assertIn('id="tab-smoke"', html_str)
            self.assertIn('id="tab-vally"', html_str)
            self.assertIn("Smoke (legacy)", html_str)
            self.assertIn(">Vally <", html_str)  # Tab label
            # The vally tab body carries the failing-row chip.
            self.assertIn("rc-Routing", html_str)
            # Both skill names appear (each in their own tab panel body).
            self.assertIn("sqldw", html_str)
            self.assertIn("vally-skill", html_str)

    def test_legacy_only_with_no_vally_uses_plain_smoke_label(self) -> None:
        # When the vally producer hasn't run yet, the legacy smoke tab keeps
        # the plain "Smoke" label (no need to disambiguate). Same single-tab
        # back-compat layout as before this PR.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            _write_results(root, today_iso, "111-1", "sqldw",
                           {"t1": {"isPass": True, "message": "Smoke status: Y"}})
            all_runs = build_dashboard.discover_runs(root)
            agg = build_dashboard.aggregate_by_skill(all_runs, 30)
            html_str = build_dashboard.render_html(agg, "owner/repo", 30)
            # Single-panel page (no tabs).
            self.assertNotIn('id="tab-smoke"', html_str)
            self.assertNotIn('id="tab-vally"', html_str)
            self.assertIn("sqldw", html_str)

    def test_vally_only_no_legacy_no_fulleval_renders_vally_tab(self) -> None:
        # Vally producer ran but legacy hasn't. There's no legacy data, so
        # the legacy tab is omitted entirely (no empty placeholder). The
        # vally tab carries the "Vally" label directly.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            _write_results_with_deeplinks(
                root, today_iso, "v-1", "vskill",
                {"v": {"isPass": True, "rawStatus": "Y"}},
                {"runId": "v-1", "jobs": {}, "artifacts": {}, "stimFailures": []},
            )
            all_runs = build_dashboard.discover_runs(root)
            agg_legacy = build_dashboard.aggregate_by_skill([], 30)
            agg_vally = build_dashboard.aggregate_by_skill(all_runs, 30)
            html_str = build_dashboard.render_html(
                agg_legacy, "owner/repo", 30, aggregated_vally=agg_vally,
            )
            # No legacy tab (no legacy data); just the vally tab.
            self.assertNotIn('id="tab-smoke"', html_str)
            self.assertIn('id="tab-vally"', html_str)
            self.assertIn("vskill", html_str)

    def test_every_emitted_tab_id_has_matching_checked_css_rule(self) -> None:
        # Regression pin: when _wrap_n_tabbed emits a `<input id="tab-X">`,
        # the global stylesheet MUST include a `#tab-X:checked ~ #panel-X
        # { display: block; }` rule. A missing rule means the tab's
        # radio toggles but the panel never shows -- the bug we shipped
        # when first introducing the vally tab (the CSS rule list was
        # hardcoded to smoke + fulleval). This test catches it by
        # scanning the rendered HTML for tab IDs and confirming each one
        # appears in a `:checked` selector.
        import re
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            _write_results(root, today_iso, "1-1", "legacy-skill",
                           {"t1": {"isPass": True, "message": "Smoke status: Y"}})
            _write_results_with_deeplinks(
                root, today_iso, "2-1", "vally-skill",
                {"v": {"isPass": True}}, {"runId": "2-1", "jobs": {}, "artifacts": {}, "stimFailures": []},
            )
            all_runs = build_dashboard.discover_runs(root)
            legacy_runs = [r for r in all_runs if r["producer"] != "vally"]
            vally_runs = [r for r in all_runs if r["producer"] == "vally"]
            agg = build_dashboard.aggregate_by_skill(legacy_runs, 30)
            agg_v = build_dashboard.aggregate_by_skill(vally_runs, 30)
            # Also include full-eval to exercise all three tab IDs.
            agg_fe = build_dashboard.aggregate_fulleval_by_plan([], 30)
            html_str = build_dashboard.render_html(
                agg, "owner/repo", 30,
                aggregated_vally=agg_v,
                aggregated_fulleval=agg_fe,
            )
            # Extract every tab id the renderer emitted.
            tab_ids = set(re.findall(r'<input type="radio" name="tab" id="tab-([\w-]+)"', html_str))
            self.assertGreaterEqual(len(tab_ids), 2, "Expected at least 2 tabs emitted")
            for tab_id in tab_ids:
                self.assertIn(
                    f'#tab-{tab_id}:checked ~ #panel-{tab_id}', html_str,
                    f"Tab '{tab_id}' has a radio input but no matching `:checked ~ #panel-{tab_id}` CSS rule",
                )
                self.assertIn(
                    f'#tab-{tab_id}:checked ~ .tabs label[for="tab-{tab_id}"]', html_str,
                    f"Tab '{tab_id}' has a radio input but no matching `:checked ~ .tabs label` active-state rule",
                )


class LegacyOnlyEmitsNoVallyDomTest(unittest.TestCase):
    """Back-compat guarantee: a fixture containing ONLY legacy
    smoke-results-schema artifacts (no deepLinks.json) MUST render
    without producing any of the vally-only DOM. This is the
    back-compat enforcement -- the schema additions are OPTIONAL per
    docs/skill-test-result-schema.md and older in-window artifacts
    must continue to render through.

    Originally framed as a "byte-identity snapshot" but relaxed to a
    DOM-marker-absence form: we assert that the legacy-only render
    introduces ZERO new vally-only DOM markers (no .failing row class,
    no failure-disclosure block, no rootcause-chip, no evidence-preview,
    no deeplink anchors). The pre-PR HTML byte layout would change
    only with new CSS in the shared stylesheet; gating on CSS bytes
    would couple this test to unrelated theme tweaks. The DOM-level
    contract is the actual back-compat guarantee.
    """

    def test_legacy_only_emits_no_vally_specific_dom(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            # Two legacy skills, one with a failing test (to prove that
            # even failing legacy rows DO NOT pick up vally-only markup).
            _write_results(root, today_iso, "111-1", "sqldw",
                           {"t1": {"isPass": False, "rawStatus": "N", "message": "Smoke status: N"},
                            "t2": {"isPass": True, "rawStatus": "Y"}})
            _write_results(root, today_iso, "111-1", "powerbi",
                           {"t1": {"isPass": True, "rawStatus": "Y"}})

            runs = build_dashboard.discover_runs(root)
            aggregated = build_dashboard.aggregate_by_skill(runs, 30)
            html_str = build_dashboard.render_html(aggregated, "gim-home/skills-for-fabric", 30)

            # NONE of the vally-only DOM markers may appear. Check for
            # the rendered HTML element forms (NOT the CSS class names,
            # which appear unconditionally in the shared stylesheet).
            self.assertNotIn('class="failing"', html_str)
            self.assertNotIn('<div class="failure-disclosure"', html_str)
            self.assertNotIn('<span class="rootcause-chip', html_str)
            self.assertNotIn('<span class="evidence-preview"', html_str)
            self.assertNotIn('<a class="deeplink"', html_str)
            # The legacy run-page link MUST still appear (this is the only
            # deep link a legacy row exposes).
            self.assertIn(
                'https://github.com/gim-home/skills-for-fabric/actions/runs/111',
                html_str,
            )

    def test_legacy_render_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            _write_results(root, today_iso, "111-1", "sqldw",
                           {"t1": {"isPass": False, "rawStatus": "N", "message": "x"}})
            runs1 = build_dashboard.discover_runs(root)
            agg1 = build_dashboard.aggregate_by_skill(runs1, 30)
            runs2 = build_dashboard.discover_runs(root)
            agg2 = build_dashboard.aggregate_by_skill(runs2, 30)
            html_1 = build_dashboard.render_html(agg1, "gim-home/skills-for-fabric", 30)
            html_2 = build_dashboard.render_html(agg2, "gim-home/skills-for-fabric", 30)
            self.assertEqual(
                html_1, html_2,
                "render_html must be deterministic for the same legacy "
                "input -- the DOM-marker-absence back-compat contract "
                "relies on the two renders matching exactly so a stray "
                "non-deterministic surface (e.g. dict-iteration order) "
                "doesn't quietly introduce vally-only DOM markers.",
            )


class TrialVsStimSemanticsRegressionTest(unittest.TestCase):
    """Regression-pin against the trial-vs-stim conflation trap
    (called out in the vally dashboard ingest plan's Risks section).

    The dashboard treats one row per (date, test_name) = one row per
    STIM. Vally has multiple trials per stim. The producer
    (Export-VallySchemaArtifact.ps1) collapses trials to a per-stim
    binary pass before writing testResults.json. This test enforces
    that the dashboard never receives, never aggregates, and never
    renders trial-level booleans -- only stim-level ones.
    """

    def test_per_stim_pass_count_matches_testresults_keys(self) -> None:
        # The testResults.json the producer writes has ONE entry per stim.
        # Pass/fail counts derive from those keys directly; the dashboard
        # MUST NOT multiply by trial count or treat one stim's N trials
        # as N rows.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            # 3 stims; trial counts would be larger but the producer
            # has collapsed them. The dashboard MUST see exactly 3 rows.
            _write_results_with_deeplinks(
                root, today_iso, "abc-1", "spark-authoring-cli",
                {
                    "Stim A (10 trials, all passed)": {"isPass": True, "rawStatus": "Y"},
                    "Stim B (10 trials, 2 failed)":   {"isPass": False, "rawStatus": "N"},
                    "Stim C (10 trials, all passed)": {"isPass": True, "rawStatus": "Y"},
                },
                {"runId": "abc-1", "jobs": {}, "artifacts": {}, "stimFailures": [
                    {"stim": "Stim B (10 trials, 2 failed)", "shard": "shard1", "grader": "g", "rootCause": "ContentMismatch"}
                ]},
            )
            runs = build_dashboard.discover_runs(root)
            aggregated = build_dashboard.aggregate_by_skill(runs, 30)
            skill_entry = aggregated["by_skill"]["spark-authoring-cli"]
            day = list(skill_entry["dates"].values())[0]
            # 2 passing stims + 1 failing stim. NOT 20 passing trials + 2
            # failing trials. NOT 3 + 10. NOT any trial-derived number.
            self.assertEqual(day["pass"], 2)
            self.assertEqual(day["fail"], 1)
            self.assertEqual(day["pass"] + day["fail"], 3)


class VallyMalformedDeepLinksRendererTests(unittest.TestCase):
    """Fix #2: a structurally-valid-JSON deepLinks.json with wrong sub-field
    shapes (e.g. "jobs" as a string, "artifacts" as a list) must NOT crash
    the renderer. deepLinks.json is external producer data and the worst
    case should be "no deep links for this row", not "no dashboard at all".
    """

    def test_render_disclosure_handles_malformed_deeplinks(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            today_iso = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
            # jobs is a string and artifacts is a list. Both wrong shapes.
            _write_results_with_deeplinks(
                root, today_iso, "9-1", "vally-skill",
                {"failingTest": {"isPass": False, "rawStatus": "N", "message": ""}},
                {
                    "runId": "9-1",
                    "jobs": "not a dict",
                    "artifacts": [],
                    "stimFailures": [
                        {"stim": "failingTest", "shard": "shard1", "grader": "g", "rootCause": "Other"}
                    ],
                },
            )
            runs = build_dashboard.discover_runs(root)
            aggregated = build_dashboard.aggregate_by_skill(runs, 30)
            # The render must not raise. It should produce HTML (even if
            # the deep-link row has no usable job/artifact link).
            html_str = build_dashboard.render_html(aggregated, "gim-home/skills-for-fabric", 30)
            self.assertIn("vally-skill", html_str)

    def test_dict_or_empty_helper(self) -> None:
        # Lock the helper down so a future change does not silently
        # widen what counts as "dict-like".
        self.assertEqual(build_dashboard._dict_or_empty({"a": 1}), {"a": 1})
        self.assertEqual(build_dashboard._dict_or_empty(None), {})
        self.assertEqual(build_dashboard._dict_or_empty("nope"), {})
        self.assertEqual(build_dashboard._dict_or_empty([]), {})
        self.assertEqual(build_dashboard._dict_or_empty(42), {})


# File invoked via `python -m unittest tests.test_build_dashboard` in CI.
# No `if __name__ == "__main__"` block: running this file directly with
# `python tests/test_build_dashboard.py` would historically have stopped
# unittest discovery at any classes defined after the block, hiding the
# vally test additions.