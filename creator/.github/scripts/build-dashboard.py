#!/usr/bin/env python3
"""Build a static HTML dashboard from skill-test result artifacts.

Reads the schema-compliant tree documented in
`docs/skill-test-result-schema.md` (one or more `${date}/${run-id}/${skill}/`
trees) and emits a single self-contained `index.html` per-skill trend table.

Inputs:
    --input-root PATH   Directory containing one or more schema-compliant
                        `${date}/${run-id}/${skill}/` trees, typically produced
                        by downloading `smoke-results-schema-*` artifacts via
                        `gh run download`.
    --output-dir PATH   Directory to write `index.html` (and per-skill pages
                        if --per-skill-pages is set).
    --repo OWNER/NAME   Repo name for run-URL construction. Defaults to env
                        GITHUB_REPOSITORY.
    --window-days N     Aggregation window in days (default 30).

Output:
    index.html          Single-page dashboard with per-skill rows.

The output is intentionally minimalist: no JS frameworks, no Chart.js, no
build step. Sparklines are inline SVG. Total HTML payload is typically
< 50 KB for ~30 skills and ~30 days of runs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import sys
from collections import defaultdict
from pathlib import Path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "gim-home/skills-for-fabric"))
    parser.add_argument("--window-days", type=int, default=30)
    # Optional full-eval inputs. When omitted, the dashboard renders a single
    # smoke-only tab (backward compatible with the pre-PR behaviour). When
    # provided, a second "Full evals" tab is added with per-plan rows grouped
    # by skill family. Full-eval runs are nightly + sparser + larger, so a
    # wider default window (60 days) avoids a near-empty trend on day 1.
    parser.add_argument("--fulleval-input-root", type=Path, default=None,
                        help="Directory containing `full-eval-results-*` artifact contents (eval-run-telemetry.json + eval-results.md). When omitted, no full-eval tab is emitted.")
    parser.add_argument("--fulleval-window-days", type=int, default=60,
                        help="Aggregation window for the full-eval tab (days). Default 60 because full-evals run nightly, are sparser, and have 90-day artifact retention.")
    return parser.parse_args(argv)


def discover_runs(input_root: Path) -> list[dict]:
    """Walk input_root and return a list of run records.

    Returns:
        list of {date, run_id, skill, test_results: dict, run_url: str}
    """
    runs: list[dict] = []
    if not input_root.exists():
        print(f"warning: input root does not exist: {input_root}", file=sys.stderr)
        return runs

    # Expected layout: <input_root>/<...>/${date}/${run_id}/${skill}/testResults.json
    # The <...> prefix may exist when artifacts are downloaded into per-artifact subdirs.
    for results_path in input_root.rglob("testResults.json"):
        # Walk up: results_path / skill / run_id / date
        skill_dir = results_path.parent
        run_dir = skill_dir.parent
        date_dir = run_dir.parent
        skill = skill_dir.name
        run_id = run_dir.name
        date = date_dir.name

        # Skip directories that don't look like our schema (date should be yyyy-mm-dd).
        try:
            dt.datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            continue

        try:
            test_results = json.loads(results_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"warning: skipping malformed {results_path}: {e}", file=sys.stderr)
            continue

        # testResults.json carries a reserved top-level `schemaVersion` int
        # (the on-disk contract version) alongside the per-stim entries. The
        # dashboard iterates stim rows only, so drop any non-object top-level
        # value so a metadata field cannot be mistaken for a test case. See
        # docs/skill-test-result-schema.md.
        if isinstance(test_results, dict):
            test_results = {k: v for k, v in test_results.items() if isinstance(v, dict)}

        # Sibling token-summary.jsonl (optional). One JSON object per line per
        # agent run; aggregate to per-test totals.
        token_summary_path = skill_dir / "token-summary.jsonl"
        token_totals: dict[str, dict[str, int]] = {}
        if token_summary_path.exists():
            try:
                for line in token_summary_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    name = rec.get("testName")
                    if not name:
                        continue
                    if name not in token_totals:
                        token_totals[name] = {"inputTokens": 0, "outputTokens": 0, "cacheReadTokens": 0, "cacheWriteTokens": 0, "runCount": 0}
                    for k in ("inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens"):
                        v = rec.get(k)
                        if isinstance(v, (int, float)):
                            token_totals[name][k] += int(v)
                    token_totals[name]["runCount"] += 1
            except (json.JSONDecodeError, OSError) as e:
                print(f"warning: skipping malformed {token_summary_path}: {e}", file=sys.stderr)

        # Sibling deepLinks.json (optional, vally producer only). When absent
        # (legacy smoke-results-schema-* artifacts) the renderer falls back to
        # the existing top-level run link only. Shape is documented in
        # docs/skill-test-result-schema.md (rootCause + deepLinks are OPTIONAL
        # fields so older in-window artifacts don't poison the dashboard).
        deep_links: dict | None = None
        deep_links_path = skill_dir / "deepLinks.json"
        if deep_links_path.exists():
            try:
                deep_links = json.loads(deep_links_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                print(f"warning: skipping malformed {deep_links_path}: {e}", file=sys.stderr)
                deep_links = None

        # run_id may include an attempt suffix `<id>-<attempt>`; first segment is the run id
        # used for GH Actions URL construction.
        gh_run_id = run_id.split("-", 1)[0]
        # Producer detection: presence of the deepLinks.json sibling
        # FILE means the vally producer wrote this run. Legacy
        # `fabric-smoke-ephemeral.yml` (smoke harness) never writes that
        # sibling, so its absence == legacy. Using file presence (not
        # parse success) so a vally run with a malformed/corrupt
        # deepLinks.json still lands in the Vally bucket -- malformed
        # JSON should degrade deep-link rendering, NOT mis-bucket the
        # whole run as legacy and hide its column in the Vally tab.
        producer = "vally" if deep_links_path.exists() else "legacy"
        runs.append({
            "date": date,
            "run_id": run_id,
            "gh_run_id": gh_run_id,
            "skill": skill,
            "test_results": test_results,
            "token_totals": token_totals,
            "deep_links": deep_links,
            "producer": producer,
            "results_path": str(results_path),
        })

    return runs


def aggregate_by_skill(runs: list[dict], window_days: int) -> dict:
    """Aggregate runs into a per-skill / per-date grid.

    Returns:
        {
            "by_skill": {skill: {"dates": {date: {"pass": int, "fail": int, "run_id": str}}}},
            "all_dates": sorted list of date strings (newest first),
            "all_skills": sorted list of skill names,
            "totals": {"runs": int, "skills": int, "dates": int},
                # runs counts only the runs that survived the window cutoff
                # (the caller may have downloaded a wider horizon for safety).
        }
    """
    today = dt.datetime.now(dt.timezone.utc).date()
    cutoff = today - dt.timedelta(days=window_days)

    by_skill: dict[str, dict] = defaultdict(lambda: {"dates": {}})
    all_dates: set[str] = set()
    all_skills: set[str] = set()
    # A "run" is one pipeline invocation = one (date, run_id) pair. The schema
    # produces one testResults.json per skill area under the same RUN_ID, so
    # counting raw file records would overcount a multi-skill nightly. Track
    # the unique (date, run_id) set instead.
    windowed_runs: set[tuple[str, str]] = set()

    def _attempt_key(run_id_str: str) -> tuple[int, int]:
        """Parse a run_id like '25858392829-1' into a (run, attempt) tuple of ints.

        Used to compare attempts within the same GitHub Actions run; without
        the attempt component, a re-run of the same workflow would lose to
        whichever attempt rglob() happened to encounter first.
        """
        parts = run_id_str.split("-", 1)
        try:
            run_int = int(parts[0])
        except ValueError:
            run_int = 0
        attempt_int = 0
        if len(parts) > 1:
            try:
                attempt_int = int(parts[1])
            except ValueError:
                attempt_int = 0
        return (run_int, attempt_int)

    for run in runs:
        run_date = dt.datetime.strptime(run["date"], "%Y-%m-%d").date()
        if run_date < cutoff:
            continue
        # A "run" is one pipeline invocation. Key by (date, gh_run_id) -- NOT
        # run_id-with-attempt -- so a re-run (attempts 1 and 2 of the same
        # workflow_run id) counts as one dashboard run, matching what the
        # per-skill grid below de-dupes to (latest attempt wins).
        windowed_runs.add((run["date"], run["gh_run_id"]))
        all_dates.add(run["date"])
        all_skills.add(run["skill"])

        pass_count = sum(1 for v in run["test_results"].values() if v.get("isPass"))
        fail_count = sum(1 for v in run["test_results"].values() if not v.get("isPass"))

        # If multiple runs landed for the same skill on the same date, keep the
        # one with the highest (run_id, attempt). Comparing as a tuple of ints
        # ensures a workflow re-run wins over the original attempt.
        prior = by_skill[run["skill"]]["dates"].get(run["date"])
        if not prior or _attempt_key(run["run_id"]) > _attempt_key(prior["run_id"]):
            # Compute per-day total tokens for the trend sparkline (sum across
            # all tests in this skill for this date).
            day_tokens = 0
            for tt in run.get("token_totals", {}).values():
                day_tokens += int(tt.get("inputTokens", 0)) + int(tt.get("outputTokens", 0))
            by_skill[run["skill"]]["dates"][run["date"]] = {
                "pass": pass_count,
                "fail": fail_count,
                "run_id": run["run_id"],
                "gh_run_id": run["gh_run_id"],
                "test_results": run["test_results"],
                "token_totals": run.get("token_totals", {}),
                "day_tokens": day_tokens,
                "deep_links": run.get("deep_links"),
                # Preserve `producer` (tagged by discover_runs) so render-side
                # decisions can distinguish vally vs legacy independently of
                # deep_links parse success. Without this, a vally run with
                # corrupt deepLinks.json (producer="vally", deep_links=None)
                # would lose vally-only row styling even though it's still
                # rendered in the Vally tab.
                "producer": run.get("producer", "legacy"),
            }

    return {
        "by_skill": dict(by_skill),
        "all_dates": sorted(all_dates, reverse=True),
        "all_skills": sorted(all_skills),
        "totals": {
            "runs": len(windowed_runs),
            "skills": len(all_skills),
            "dates": len(all_dates),
        },
    }


def render_sparkline(daily_pass_rates: list[float | None], width: int = 80, height: int = 20) -> str:
    """Render an inline SVG sparkline of pass rates (0.0..1.0, or None for missing).

    Missing days render as gaps; line connects only adjacent present points.
    """
    if not daily_pass_rates or all(v is None for v in daily_pass_rates):
        return f'<svg width="{width}" height="{height}" class="sparkline empty"><title>No data</title></svg>'

    step_x = width / max(1, len(daily_pass_rates) - 1)
    points: list[tuple[float, float]] = []
    for i, v in enumerate(daily_pass_rates):
        if v is None:
            points.append(None)  # type: ignore
        else:
            x = i * step_x
            y = height - (v * (height - 2)) - 1  # 1px padding top/bottom
            points.append((x, y))

    # Build polylines for contiguous runs of present points.
    polylines: list[str] = []
    current: list[str] = []
    for p in points:
        if p is None:
            if len(current) >= 2:
                polylines.append(f'<polyline points="{" ".join(current)}" />')
            current = []
        else:
            current.append(f"{p[0]:.1f},{p[1]:.1f}")
    if len(current) >= 2:
        polylines.append(f'<polyline points="{" ".join(current)}" />')

    # Dots for each present point.
    dots: list[str] = []
    for p in points:
        if p is not None:
            dots.append(f'<circle cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="1.5" />')

    return (
        f'<svg width="{width}" height="{height}" class="sparkline" '
        f'preserveAspectRatio="none" viewBox="0 0 {width} {height}">'
        f'{"".join(polylines)}{"".join(dots)}</svg>'
    )


CSS = """
/* Lightweight Fabric-flavored theme. Uses Microsoft's Segoe UI Variable
   typography and a subset of Fabric brand tokens (the brand teal accent
   and brand-fill background tints). NOT a full Fluent UI adoption — see
   the README's "Styling" section if a richer adoption becomes warranted. */
:root {
  color-scheme: light dark;
  /* Fabric brand tokens (light) */
  --fabric-accent:        #117865;          /* Fabric brand teal */
  --fabric-accent-hover:  #0d6655;
  --bg:                   #ffffff;
  --bg-muted:             #faf9fb;          /* very light lavender tint */
  --bg-elevated:          #ffffff;
  --fg:                   #242424;
  --fg-muted:             #616161;
  --border:               #e6e4ec;
  --shadow-card:          0 1px 2px rgba(33, 31, 42, 0.06), 0 0 0 1px var(--border);
}
@media (prefers-color-scheme: dark) {
  :root {
    --fabric-accent:        #5fd2c5;
    --fabric-accent-hover:  #82e0d5;
    --bg:                   #0b0a0d;
    --bg-muted:             #161419;
    --bg-elevated:          #1a181f;
    --fg:                   #f5f5f5;
    --fg-muted:             #adacb1;
    --border:               #2c2832;
    --shadow-card:          0 1px 2px rgba(0, 0, 0, 0.5), 0 0 0 1px var(--border);
  }
}
* { box-sizing: border-box; }
body {
  font: 14px/1.5 "Segoe UI Variable", "Segoe UI", -apple-system, system-ui, sans-serif;
  font-feature-settings: "ss01";
  max-width: 1200px; margin: 0 auto; padding: 2em 1.5em;
  background: var(--bg); color: var(--fg);
}
h1 { font: 600 22px/1.2 "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif; margin: 0 0 0.25em 0; letter-spacing: -0.01em; }
h1::before { content: "🧪"; margin-right: 0.4em; font-size: 0.85em; vertical-align: -1px; }
.subtitle { color: var(--fg-muted); margin: 0 0 1.5em 0; font-size: 13px; }
.summary {
  margin: 1.5em 0; padding: 0.9em 1.1em;
  background: var(--bg-muted); border-radius: 8px;
  box-shadow: var(--shadow-card);
}
a { color: var(--fabric-accent); text-decoration: none; }
a:hover { color: var(--fabric-accent-hover); text-decoration: underline; }
table { border-collapse: separate; border-spacing: 0; width: 100%; margin-top: 1em; font-size: 13px; background: var(--bg-elevated); border-radius: 8px; overflow: hidden; box-shadow: var(--shadow-card); }
th, td { padding: 0.55em 0.9em; border-bottom: 1px solid var(--border); text-align: left; vertical-align: middle; }
tr:last-child td { border-bottom: none; }
th { background: var(--bg-muted); position: sticky; top: 0; font-weight: 600; font-size: 12px; text-transform: uppercase; letter-spacing: 0.03em; color: var(--fg-muted); }
th.num, td.num { text-align: right; font-variant-numeric: tabular-nums; }
.hint { margin-top: 0.4em; font-size: 12px; color: var(--fg-muted); font-style: italic; }
.pass-rate { font-variant-numeric: tabular-nums; font-weight: 600; }
.pass-rate.ok   { color: #117865; }
.pass-rate.warn { color: #b58300; }
.pass-rate.bad  { color: #c50f1f; }
.sparkline { display: inline-block; vertical-align: middle; }
.sparkline polyline { fill: none; stroke: #117865; stroke-width: 1.5; stroke-linejoin: round; stroke-linecap: round; }
.sparkline circle { fill: #117865; }
.sparkline.empty { opacity: 0.3; }
.tokens-cell { font-size: 13px; line-height: 1.3; }
.tokens-cell .meta { color: var(--fg-muted); }
.token-delta { font-size: 11px; font-weight: 600; margin-left: 0.4em; font-variant-numeric: tabular-nums; }
.token-delta.up   { color: #c50f1f; }
.token-delta.down { color: #117865; }
.token-delta.flat { color: var(--fg-muted); }
@media (prefers-color-scheme: dark) {
  .token-delta.up   { color: #ff6b76; }
  .token-delta.down { color: #5fd2c5; }
}
.history-block { padding: 0.6em 0.9em 0.2em; background: var(--bg-elevated); }
.history-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--fg-muted); margin-bottom: 0.4em; }
.history-grid { width: auto; min-width: 50%; border-collapse: collapse; font-size: 12px; margin-bottom: 0.6em; background: transparent; box-shadow: none; }
.history-grid th, .history-grid td { padding: 0.3em 0.9em; border: none; border-bottom: 1px solid var(--border); background: transparent; }
.history-grid tr:last-child td { border-bottom: none; }
.history-grid th { background: transparent; position: static; }
.history-date { font-variant-numeric: tabular-nums; }
footer { margin-top: 3em; color: var(--fg-muted); font-size: 12px; }
.empty-state { text-align: center; padding: 3em; color: var(--fg-muted); }

/* Per-test detail rows (expandable under each skill row). */
tr.details td { background: var(--bg-muted); padding: 0; }
details.skill-details { margin: 0; padding: 0; }
details.skill-details > summary { cursor: pointer; padding: 0.5em 0.9em; color: var(--fg-muted); font-size: 12px; user-select: none; list-style: none; }
details.skill-details > summary::-webkit-details-marker { display: none; }
details.skill-details > summary::before { content: "▸ "; display: inline-block; transition: transform 0.15s; }
details.skill-details[open] > summary::before { content: "▾ "; }
.test-grid { width: 100%; border-collapse: collapse; font-size: 12px; background: var(--bg-elevated); }
.test-grid td { border: none; padding: 0.35em 0.9em; vertical-align: top; }
.test-grid tr + tr td { border-top: 1px solid var(--border); }
.test-grid tr:nth-child(even) td { background: var(--bg-muted); }
.status-badge { display: inline-block; min-width: 1.4em; text-align: center; padding: 0.05em 0.45em; border-radius: 4px; font-weight: 600; font-variant-numeric: tabular-nums; font-size: 11px; }
.status-badge.Y { background: #dff6dd; color: #0e7032; }
.status-badge.F { background: #fff4ce; color: #855700; }
.status-badge.N { background: #fde7e9; color: #a01f23; }
@media (prefers-color-scheme: dark) {
  .pass-rate.ok   { color: #6ccb8f; }
  .pass-rate.warn { color: #e8c466; }
  .pass-rate.bad  { color: #ff6b76; }
  .sparkline polyline { stroke: #6ccb8f; }
  .sparkline circle { fill: #6ccb8f; }
  .status-badge.Y { background: #0a3a16; color: #6ccb8f; }
  .status-badge.F { background: #3a2a00; color: #e8c466; }
  .status-badge.N { background: #4a0a14; color: #ff6b76; }
}
.test-grid .test-name { font-family: ui-monospace, "Cascadia Code", Consolas, "SF Mono", monospace; word-break: break-word; }
.test-grid .duration { color: var(--fg-muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.test-grid .meta { color: var(--fg-muted); font-size: 11px; margin-top: 0.2em; }
.test-grid .meta .miss { color: #c50f1f; }
.test-grid .meta .flaky { color: #b58300; }
@media (prefers-color-scheme: dark) {
  .test-grid .meta .miss { color: #ff6b76; }
  .test-grid .meta .flaky { color: #e8c466; }
}

/* ============================================================
 * Tab UI + full-eval-specific styles. Added when the full-eval
 * tab is enabled (via --fulleval-input-root). All styles here
 * are scoped via class names so a smoke-only render is unaffected.
 * ============================================================ */

/* Pure-CSS tabs (radio inputs hidden, labels styled as tabs). No JS so
   the page renders identically with JavaScript disabled. The inputs are
   positioned off-screen rather than `display: none` so checked state still
   takes effect for the sibling-selector rules below. */
.tabs { display: flex; gap: 4px; margin: 1.5em 0 0 0; border-bottom: 1px solid var(--border); }
input[type="radio"][name="tab"] { position: absolute; left: -9999px; }
.tabs label {
  padding: 0.55em 1.1em;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  color: var(--fg-muted);
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  user-select: none;
  letter-spacing: 0.01em;
}
.tabs label:hover { color: var(--fg); }
.tabs label .count {
  display: inline-block;
  margin-left: 0.4em;
  padding: 0.05em 0.45em;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 600;
  background: var(--bg-muted);
  color: var(--fg-muted);
  vertical-align: 1px;
}
.tab-panel { display: none; padding-top: 0.5em; }
#tab-smoke:checked ~ .tabs label[for="tab-smoke"],
#tab-vally:checked ~ .tabs label[for="tab-vally"],
#tab-fulleval:checked ~ .tabs label[for="tab-fulleval"] {
  color: var(--fabric-accent);
  border-bottom-color: var(--fabric-accent);
}
#tab-smoke:checked ~ #panel-smoke,
#tab-vally:checked ~ #panel-vally,
#tab-fulleval:checked ~ #panel-fulleval { display: block; }

/* Full-eval section headers (skill-family grouping inside the tab). */
.fe-section {
  margin-top: 1.5em;
  font: 600 12px/1 "Segoe UI Variable", "Segoe UI", system-ui, sans-serif;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--fg-muted);
  padding-bottom: 0.4em;
}
.fe-section .count {
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0;
  margin-left: 0.4em;
}

/* Plan status pill in the full-eval tab. */
.plan-status {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 0.15em 0.55em;
  border-radius: 10px;
  letter-spacing: 0.02em;
}
.plan-status.completed  { background: #dff6dd; color: #0e7032; }
.plan-status.bailed_out { background: #fff4ce; color: #855700; }
.plan-status.failed,
.plan-status.error,
.plan-status.timed_out  { background: #fde7e9; color: #a01f23; }
.plan-status.skipped,
.plan-status.skipped_warehouse,
.plan-status.skipped_lakehouse { background: #ebf3ff; color: #1a4480; }
.plan-status.not_run    { background: var(--bg-muted); color: var(--fg-muted); }
@media (prefers-color-scheme: dark) {
  .plan-status.completed  { background: #0a3a16; color: #6ccb8f; }
  .plan-status.bailed_out { background: #3a2a00; color: #e8c466; }
  .plan-status.failed,
  .plan-status.error,
  .plan-status.timed_out  { background: #4a0a14; color: #ff6b76; }
  .plan-status.skipped,
  .plan-status.skipped_warehouse,
  .plan-status.skipped_lakehouse { background: #0a2540; color: #7fb2ff; }
}

/* Expanded full-eval plan detail: telemetry chips above the case table. */
.fe-detail-chips { display: flex; flex-wrap: wrap; gap: 0.8em; padding: 0.4em 0.9em 0.6em; font-size: 12px; color: var(--fg-muted); background: var(--bg-elevated); }
.fe-detail-chips .chip strong { color: var(--fg); font-variant-numeric: tabular-nums; }
.fe-detail-chips .chip.bailout strong { color: #b58300; }
.fe-detail-chips .chip.failed strong  { color: #c50f1f; }
@media (prefers-color-scheme: dark) {
  .fe-detail-chips .chip.bailout strong { color: #e8c466; }
  .fe-detail-chips .chip.failed strong  { color: #ff6b76; }
}
.plan-name { font-family: ui-monospace, "Cascadia Code", Consolas, "SF Mono", monospace; }

/* ============================================================
 * Vally deep-link disclosure (per-failing-test). Hidden entirely
 * when the producer is legacy / no deep_links attached, so
 * legacy-only renders carry none of the vally-only DOM markers
 * (the back-compat test pins this absence at the DOM level; the
 * CSS lives in the global stylesheet but emits no markup in the
 * legacy-only case).
 * ============================================================ */
.test-grid tr.failing { background: rgba(197, 15, 31, 0.06); }
@media (prefers-color-scheme: dark) {
  .test-grid tr.failing { background: rgba(255, 107, 118, 0.10); }
}
.failure-disclosure { margin-top: 0.3em; }
.failure-details > summary { cursor: pointer; color: var(--fg-muted); font-size: 11px; user-select: none; list-style: none; padding: 0.15em 0; }
.failure-details > summary::-webkit-details-marker { display: none; }
.failure-details > summary::before { content: "▸ "; display: inline-block; transition: transform 0.15s; }
.failure-details[open] > summary::before { content: "▾ "; }
.failure-details > summary:hover { color: var(--fg); }
.grader-grid {
  width: 100%;
  border-collapse: collapse;
  margin-top: 0.25em;
  font-size: 11px;
}
.grader-grid th {
  text-align: left;
  font-weight: 600;
  color: var(--fg-muted);
  border-bottom: 1px solid var(--border);
  padding: 0.25em 0.6em 0.25em 0;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 10px;
}
.grader-grid td {
  padding: 0.3em 0.6em 0.3em 0;
  vertical-align: top;
  border-bottom: 1px solid var(--border);
}
.grader-grid tr:last-child td { border-bottom: none; }
.grader-grid td.grader-name {
  font-family: ui-monospace, "Cascadia Code", Consolas, "SF Mono", monospace;
  white-space: nowrap;
  color: var(--fg);
}
.grader-grid td.rootcause-cell { white-space: nowrap; }
.grader-grid td.evidence-cell {
  font-family: ui-monospace, "Cascadia Code", Consolas, "SF Mono", monospace;
  font-size: 10.5px;
  color: var(--fg-muted);
}
.grader-grid tr.row-passing td.grader-name { color: var(--fg-muted); }
.grader-grid tr.row-passing { opacity: 0.75; }
.grader-grid tr.row-failing { background: rgba(220, 53, 69, 0.08); }
@media (prefers-color-scheme: dark) {
  .grader-grid tr.row-failing { background: rgba(255, 107, 118, 0.10); }
}
.status-chip {
  display: inline-block;
  padding: 0.05em 0.5em;
  border-radius: 4px;
  font-weight: 700;
  font-size: 10px;
  letter-spacing: 0.05em;
}
.status-chip.status-pass { background: #dff6dd; color: #0e7032; }
.status-chip.status-fail { background: #fde7e9; color: #a01f23; }
@media (prefers-color-scheme: dark) {
  .status-chip.status-pass { background: #0a3a16; color: #6ccb8f; }
  .status-chip.status-fail { background: #4a0a14; color: #ff6b76; }
}
.rootcause-chip {
  display: inline-block;
  padding: 0.05em 0.45em;
  border-radius: 8px;
  font-weight: 600;
  background: var(--bg-muted);
  color: var(--fg);
  letter-spacing: 0.01em;
}
.rootcause-chip.rc-WallTimeBudget,
.rootcause-chip.rc-TokenBudget,
.rootcause-chip.rc-TurnBudget,
.rootcause-chip.rc-SessionIdle  { background: #fff4ce; color: #855700; }
.rootcause-chip.rc-AuthOrSetup,
.rootcause-chip.rc-ToolError,
.rootcause-chip.rc-HarnessCrash { background: #fde7e9; color: #a01f23; }
.rootcause-chip.rc-Routing,
.rootcause-chip.rc-ContentMismatch,
.rootcause-chip.rc-EvalThreshold { background: #ebf3ff; color: #1a4480; }
.rootcause-chip.rc-Other        { background: var(--bg-muted); color: var(--fg-muted); }
@media (prefers-color-scheme: dark) {
  .rootcause-chip.rc-WallTimeBudget,
  .rootcause-chip.rc-TokenBudget,
  .rootcause-chip.rc-TurnBudget,
  .rootcause-chip.rc-SessionIdle  { background: #3a2a00; color: #e8c466; }
  .rootcause-chip.rc-AuthOrSetup,
  .rootcause-chip.rc-ToolError,
  .rootcause-chip.rc-HarnessCrash { background: #4a0a14; color: #ff6b76; }
  .rootcause-chip.rc-Routing,
  .rootcause-chip.rc-ContentMismatch,
  .rootcause-chip.rc-EvalThreshold { background: #0a2540; color: #7fb2ff; }
}
.evidence-preview {
  display: inline-block;
  font-family: ui-monospace, "Cascadia Code", Consolas, "SF Mono", monospace;
  font-size: 10.5px;
  color: var(--fg-muted);
  background: var(--bg-muted);
  padding: 0.1em 0.4em;
  border-radius: 4px;
  max-width: 60ch;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
a.deeplink {
  display: inline-block;
  padding: 0.05em 0.45em;
  border-radius: 4px;
  background: var(--bg-muted);
  color: var(--fabric-accent);
  font-weight: 600;
  letter-spacing: 0.01em;
}
a.deeplink:hover { background: var(--fabric-accent); color: #fff; text-decoration: none; }
/* Compact chip-style anchor for opening the GitHub Actions run from
 * a table cell. Adds a "logs" text label next to the arrow glyph so
 * the affordance is obvious vs the prior bare-arrow approach. */
a.run-link {
  display: inline-block;
  margin-left: 0.35em;
  padding: 0.05em 0.45em;
  border-radius: 4px;
  background: var(--bg-muted);
  color: var(--fabric-accent);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-decoration: none;
  vertical-align: 1px;
}
a.run-link:hover { background: var(--fabric-accent); color: #fff; text-decoration: none; }
"""


def _dict_or_empty(value: object) -> dict:
    """Return ``value`` when it is a dict; otherwise return an empty dict.

    Used to guard sub-fields of ``deepLinks.json`` (an external producer
    artifact) so a malformed-but-valid-JSON shape (e.g. ``"jobs": "x"`` or
    ``"artifacts": []``) does not crash the renderer with an AttributeError
    on ``.get``/``.items``. Worst case: that row gets no deep links.
    """
    return value if isinstance(value, dict) else {}


def _sanitize_css_token(raw: str, max_len: int = 64) -> str:
    """Coerce a producer-supplied string into a safe CSS class-token suffix.

    Producer data lands in CSS class attributes via ``rc-{token}``. A
    raw producer value containing spaces, slashes, quotes, or other
    non-token characters would either break styling (``rc-Foo bar``
    becomes TWO classes) or inject unintended class attributes. Keep
    only ``[A-Za-z0-9_-]``; replace everything else with ``-``; cap
    length so a pathological producer can't grow the HTML unboundedly.
    """
    import re
    s = re.sub(r'[^A-Za-z0-9_-]', '-', (raw or '').strip())[:max_len]
    return s or 'Other'


def _safe_url(raw: object) -> str | None:
    """Return ``raw`` if it's a string starting with ``http://`` or ``https://``.

    Used to validate URLs coming from artifact data before placing them in an
    ``<a href="...">``: a malicious or buggy ``flakyIssue`` value of
    ``javascript:alert(1)`` would otherwise execute when a reviewer clicks the
    link, even with HTML attribute escaping. Returns ``None`` for any value
    that doesn't look like a plain web URL; callers render the value as text
    in that case.
    """
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if s.lower().startswith("http://") or s.lower().startswith("https://"):
        return s
    return None


def _render_token_delta(dates_data: dict) -> str:
    """Render an inline `↑3%` / `↓5%` / `→0%` indicator next to a window-total
    token count.

    Compares the latest day with token data to the next-most-recent day with
    token data. Returns empty string when fewer than 2 token-bearing days exist
    (graceful degradation on day 1 of a fresh window). Sign convention:
    rising tokens is BAD (skill is growing in cost), falling is good.
    Threshold is ±5%; within that band we show a neutral `→` indicator so the
    viewer knows we checked, not "couldn't compute".
    """
    days_with_tokens = sorted(
        [d for d, day in dates_data.items() if isinstance(day.get("day_tokens"), (int, float)) and day["day_tokens"] > 0],
        reverse=True,  # newest first
    )
    if len(days_with_tokens) < 2:
        return ""

    latest = int(dates_data[days_with_tokens[0]]["day_tokens"])
    prior  = int(dates_data[days_with_tokens[1]]["day_tokens"])
    if prior <= 0:
        return ""
    pct = (latest - prior) / prior * 100.0

    if pct > 5:
        arrow, klass = "↑", "up"
    elif pct < -5:
        arrow, klass = "↓", "down"
    else:
        arrow, klass = "→", "flat"
    return f' <span class="token-delta {klass}" title="latest day vs prior day">{arrow}{abs(pct):.0f}%</span>'


def _render_daily_history(dates_data: dict, repo: str) -> str:
    """Render a small per-day breakdown table for one skill, newest first.

    Surfaces actual numbers per day (date · pass/total · tokens · run link)
    so viewers can read the history without inferring from a sparkline shape.
    Only renders when 2+ dates exist; single-day skills get nothing (the main
    row already covers that case).
    """
    if not dates_data or len(dates_data) < 2:
        return ""

    rows: list[str] = []
    for date in sorted(dates_data.keys(), reverse=True):
        day = dates_data[date]
        pass_count = int(day.get("pass") or 0)
        fail_count = int(day.get("fail") or 0)
        total = pass_count + fail_count
        day_tokens = int(day.get("day_tokens") or 0)
        tokens_str = f"{day_tokens:,}" if day_tokens > 0 else "—"
        rate_str = f"{int(round(pass_count / total * 100))}%" if total else "—"
        gh_run_id = day.get("gh_run_id")
        if gh_run_id:
            # Mirror the URL escape pattern used by the main skill-row link:
            # assemble first, then html.escape the whole href. This keeps both
            # call sites consistent so a future contributor doesn't have to
            # reason about which approach is in play here.
            run_url = f"https://github.com/{repo}/actions/runs/{gh_run_id}"
            # `run-link` text-label affordance (vs the bare arrow glyph
            # the prior render used) so a triager glancing at the row
            # can spot "logs" rather than hunting for a small icon.
            link = f' <a class="run-link" href="{html.escape(run_url)}" title="Open the GitHub Actions run">logs &#x2197;</a>'
        else:
            link = ""
        rows.append(
            "<tr>"
            f'<td class="history-date">{html.escape(date)}{link}</td>'
            f'<td class="num">{pass_count} / {total}</td>'
            f'<td class="num">{rate_str}</td>'
            f'<td class="num">{tokens_str}</td>'
            "</tr>"
        )

    return (
        '<div class="history-block">'
        '<div class="history-label">Daily history</div>'
        '<table class="history-grid">'
        '<thead><tr>'
        '<th>Date</th>'
        '<th class="num">Pass / total</th>'
        '<th class="num">Rate</th>'
        '<th class="num">Tokens</th>'
        '</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
        '</div>'
    )


def _render_test_details(test_results: dict, token_totals: dict | None = None,
                         daily_history_html: str = "",
                         deep_links: dict | None = None,
                         repo: str = "",
                         gh_run_id: str = "",
                         producer: str = "legacy") -> str:
    """Render a collapsible per-test details block for one skill row.

    `test_results` is the inner object of a per-skill testResults.json:
    {test_name: {isPass, message, rawStatus?, durationSeconds?,
                 foundSkills?, foundResults?, missingSkills?,
                 missingResults?, flakyIssue?, warnings?}}

    `token_totals` is the per-test token usage rollup from token-summary.jsonl:
    {test_name: {inputTokens, outputTokens, cacheReadTokens, cacheWriteTokens, runCount}}
    Missing or empty token_totals results in an em-dash placeholder per row.

    `deep_links` is the optional sibling `deepLinks.json` for this skill
    (vally producer only). When present + the row has a failing test
    that appears in `stimGraders`, the renderer emits a per-stim
    grader-disclosure block: a collapsible table showing every grader
    that ran on the failing stim (passing + failing), with a Status
    column, RootCause chip, and truncated Evidence preview. Outbound
    deep-link anchors (job pages, raw artifacts) are intentionally NOT
    rendered in the disclosure -- the `deepLinks.json` artifact still
    carries job + artifact IDs for downstream consumers (Power BI
    ingester, alerting), but the in-page UX focuses on the grader
    breakdown. The `repo` and `gh_run_id` parameters are kept for
    forward-compat with a future iteration that adds a secondary
    links footer.

    Legacy (smoke-producer) artifacts have no deep_links -- the
    renderer degrades silently to the existing top-level row link.
    The DOM-level back-compat contract (none of the vally-only markup
    classes leak into a legacy-only render) is pinned by the back-compat
    test in tests/test_build_dashboard.py.
    """
    if not test_results:
        return ""

    token_totals = token_totals or {}
    deep_links = deep_links if isinstance(deep_links, dict) else None

    # Pre-index stimGraders from deepLinks by stim name so per-row lookup
    # is O(1) inside the rows loop. A single stim has multiple graders
    # (passing + failing); we collect them all and surface the union so
    # the disclosure can show "N of M graders failed" rather than just
    # "N graders failed" with no denominator. Back-compat: also accept
    # the older `stimFailures` array shape (failing-only) if that's all
    # the producer wrote.
    graders_by_stim: dict[str, list[dict]] = {}
    if deep_links:
        raw_graders = deep_links.get("stimGraders")
        if not isinstance(raw_graders, list):
            # Fallback to the older stimFailures-only shape. Each entry
            # there represents a failing grader; treat them as passed=False.
            raw_graders = []
            for sf in (deep_links.get("stimFailures") or []):
                if not isinstance(sf, dict):
                    continue
                raw_graders.append({**sf, "passed": False})
        for g in raw_graders:
            if not isinstance(g, dict):
                continue
            stim_name = g.get("stim") or ""
            if not stim_name:
                continue
            graders_by_stim.setdefault(stim_name, []).append(g)

    rows: list[str] = []
    for name, t in test_results.items():
        raw_status = t.get("rawStatus") or ("Y" if t.get("isPass") else "N")
        badge_class = raw_status if raw_status in ("Y", "F", "N") else "N"
        is_failing = not bool(t.get("isPass"))
        duration = t.get("durationSeconds")
        duration_html = f'<td class="duration">{duration:.1f}s</td>' if isinstance(duration, (int, float)) else '<td class="duration">—</td>'

        meta_parts: list[str] = []
        found_skills = t.get("foundSkills") or []
        if found_skills:
            meta_parts.append("✓ skill: " + ", ".join(html.escape(s) for s in found_skills))
        found_results = t.get("foundResults") or []
        if found_results:
            meta_parts.append("✓ result: " + ", ".join(html.escape(r) for r in found_results))
        missing_skills = t.get("missingSkills") or []
        if missing_skills:
            meta_parts.append('<span class="miss">✗ missing skill: ' + ", ".join(html.escape(s) for s in missing_skills) + "</span>")
        missing_results = t.get("missingResults") or []
        if missing_results:
            meta_parts.append('<span class="miss">✗ missing result: ' + ", ".join(html.escape(r) for r in missing_results) + "</span>")
        warnings = t.get("warnings") or []
        if warnings:
            meta_parts.append('<span class="miss">⚠ ' + "; ".join(html.escape(w) for w in warnings) + "</span>")
        flaky_issue = t.get("flakyIssue")
        if flaky_issue:
            safe_flaky = _safe_url(flaky_issue)
            if safe_flaky:
                meta_parts.append(f'<span class="flaky">🟡 flaky: <a href="{html.escape(safe_flaky)}">issue</a></span>')
            else:
                meta_parts.append(f'<span class="flaky">🟡 flaky: {html.escape(str(flaky_issue))}</span>')

        # Vally grader disclosure for failing rows that have grader
        # metadata (any-grader-failed gates the disclosure; the disclosure
        # body shows the full passing+failing grader breakdown for triage).
        deep_disclosure_html = ""
        if is_failing and deep_links and name in graders_by_stim:
            deep_disclosure_html = _render_grader_disclosure(
                stim_name=name,
                graders=graders_by_stim[name],
            )

        meta_html = ('<br>' + '<br>'.join(meta_parts)) if meta_parts else ""
        meta_cell = f'<div class="meta">{meta_html}</div>' if meta_html else ""
        if deep_disclosure_html:
            meta_cell = (meta_cell or "") + deep_disclosure_html

        # Per-test token rollup (sum of inputTokens + outputTokens across runs
        # of this test in the window). cache-read / cache-write are tracked but
        # not surfaced in the cell - they're noise for "is this skill drifting?".
        token_rec = token_totals.get(name) or {}
        billable = int(token_rec.get("inputTokens") or 0) + int(token_rec.get("outputTokens") or 0)
        if billable > 0:
            tokens_html = f'<td class="num">{billable:,}</td>'
        else:
            tokens_html = '<td class="num meta">&mdash;</td>'

        # Red-row highlight class for failing rows. Keys off producer
        # (vally vs legacy) NOT deep_links parse success -- a vally run
        # with a present-but-malformed deepLinks.json still belongs in
        # the Vally tab and should get vally-only row styling, even
        # though deep_links parsing failed (only the disclosure content
        # degrades on parse failure, not the row tint). Legacy rows
        # never get the failing tint -- preserves byte-identity vs the
        # pre-PR snapshot for legacy-only inputs.
        row_class = ' class="failing"' if (is_failing and producer == "vally") else ''
        rows.append(
            f"<tr{row_class}>"
            f'<td><span class="status-badge {badge_class}">{badge_class}</span></td>'
            f'<td class="test-name">{html.escape(name)}{meta_cell}</td>'
            f"{duration_html}"
            f"{tokens_html}"
            "</tr>"
        )

    count = len(test_results)
    return (
        '<tr class="details"><td colspan="6">'
        '<details class="skill-details">'
        f'<summary>Show {count} test{"s" if count != 1 else ""}</summary>'
        f'{daily_history_html}'
        '<table class="test-grid">'
        f'{"".join(rows)}'
        "</table>"
        "</details>"
        "</td></tr>"
    )


def _render_grader_disclosure(stim_name: str, graders: list[dict]) -> str:
    """Render the per-failing-stim disclosure block.

    Shows ALL graders that ran on this stim (passing + failing) as rows
    in a small inline table:

        Grader  |  Status  |  Root cause  |  Evidence

    Rationale: a single failing grader on a 10-grader stim ("9 of 10
    passed, 1 failed wall-time") is operationally different from a
    full-stim crash ("0 of 10 passed, harness died"). The disclosure
    only fires for failing stims (any-grader-failed gates it), but
    the body shows full triage context so the reader can scan the
    failure surface area without leaving the dashboard page.

    Graders are sorted: failing first (so the reader scans the failures
    immediately), then passing (alphabetical within group). Summary
    text uses the format "<failed> of <total> graders failed".

    Each entry should be a dict with at minimum:
      - grader: str
      - passed: bool
    Plus, for failing entries only:
      - rootCause: str (defaults to "Other" if missing)
      - evidence: str (already redacted upstream, capped at 500 chars)
    """
    rows: list[str] = []
    failing: list[dict] = []
    passing: list[dict] = []
    for g in graders:
        if g.get("passed"):
            passing.append(g)
        else:
            failing.append(g)

    if not failing and not passing:
        return ""

    failing.sort(key=lambda x: str(x.get("grader") or ""))
    passing.sort(key=lambda x: str(x.get("grader") or ""))

    for g in failing + passing:
        grader = str(g.get("grader") or "").strip()
        passed = bool(g.get("passed"))
        grader_cell = html.escape(grader) if grader else '<span class="meta">(unnamed)</span>'

        if passed:
            status_cell = '<span class="status-chip status-pass">PASS</span>'
            rc_cell = '<span class="meta">-</span>'
            evidence_cell = '<span class="meta">-</span>'
        else:
            status_cell = '<span class="status-chip status-fail">FAIL</span>'
            rc_raw = str(g.get("rootCause") or "").strip() or "Other"
            # Two separate sanitizations:
            #   - rc_class: must be a safe CSS class token (alphanumeric +
            #     dash only). Producer data is external; an emitted value
            #     with spaces / slashes / quotes would either break styling
            #     ("rc-Foo bar" becomes two classes) or inject unintended
            #     class attributes. Coerce non-token chars to '-'; cap len.
            #   - rc_display: html.escape() the human-readable text;
            #     never the class.
            rc_class = _sanitize_css_token(rc_raw)
            rc_display = html.escape(rc_raw)
            rc_cell = f'<span class="rootcause-chip rc-{rc_class}">{rc_display}</span>'
            evidence_raw = str(g.get("evidence") or "")
            if evidence_raw:
                preview = evidence_raw if len(evidence_raw) <= 180 else (evidence_raw[:179] + "\u2026")
                evidence_cell = f'<span class="evidence-preview" title="{html.escape(evidence_raw)}">{html.escape(preview)}</span>'
            else:
                evidence_cell = '<span class="meta">(no evidence)</span>'

        row_class = ' class="row-failing"' if not passed else ' class="row-passing"'
        rows.append(
            f"<tr{row_class}>"
            f'<td class="grader-name">{grader_cell}</td>'
            f'<td class="status-cell">{status_cell}</td>'
            f'<td class="rootcause-cell">{rc_cell}</td>'
            f'<td class="evidence-cell">{evidence_cell}</td>'
            "</tr>"
        )

    total = len(graders)
    fcount = len(failing)
    summary = f'{fcount} of {total} grader{"s" if total != 1 else ""} failed'

    return (
        '<div class="failure-disclosure">'
        '<details class="failure-details">'
        f'<summary>{summary}</summary>'
        '<table class="grader-grid">'
        '<thead><tr><th>Grader</th><th>Status</th><th>Root cause</th><th>Evidence</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody>'
        '</table>'
        '</details>'
        '</div>'
    )


def render_html(aggregated: dict, repo: str, window_days: int,
                aggregated_fulleval: dict | None = None,
                fulleval_window_days: int | None = None,
                aggregated_vally: dict | None = None) -> str:
    """Render the aggregated data into a single index.html.

    Three optional aggregates feed the layout decision:

    - ``aggregated`` : legacy smoke harness runs (the producer of
      ``smoke-results-schema-*`` artifacts that lack ``deepLinks.json``).
      This is the original Smoke panel.
    - ``aggregated_vally`` : vally harness runs (artifacts that contain
      ``deepLinks.json`` siblings). Rendered as its own tab so the two
      producers don't visually merge into one table while both still ship
      (the user's display preference until the legacy smoke harness is
      retired). Once legacy retires this tab takes over the "Smoke" slot.
    - ``aggregated_fulleval`` : the nightly full-eval tab.

    Back-compat: when ``aggregated_vally`` and ``aggregated_fulleval`` are
    both None, the renderer emits the pre-PR single-panel smoke page
    (preserves the byte layout legacy tests pin).
    """
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    skills = aggregated["all_skills"]

    has_vally = aggregated_vally is not None
    has_fulleval = aggregated_fulleval is not None
    vally_skills = aggregated_vally["all_skills"] if has_vally else []

    # Backward compat: no full-eval, no vally, no legacy skills -> the
    # original whole-page empty state.
    if not has_fulleval and not has_vally and not skills:
        return _empty_html(generated, window_days)

    smoke_body = _render_smoke_panel_inner(aggregated, repo, window_days)

    # No tabs at all (only legacy smoke data, no vally, no full-eval) -> the
    # pre-PR single-panel layout. Preserves the legacy snapshot test.
    if not has_fulleval and not has_vally:
        return _wrap_single_smoke(smoke_body, generated, repo, window_days)

    # Build the tab list dynamically. Order: Smoke | Vally | Full evals.
    # Label changes from "Smoke" to "Smoke (legacy)" when the vally tab is
    # also present so the two are unambiguous. The legacy tab itself is
    # omitted ONLY when vally is present and has no legacy data -- in the
    # legacy-only path we still show the empty-smoke tab beside full-eval
    # so reviewers can tell "no smoke runs in this window" rather than
    # "the tab was removed".
    tabs: list[tuple[str, str, str, int]] = []
    show_smoke_tab = bool(skills) or not has_vally
    if show_smoke_tab:
        smoke_label = "Smoke (legacy)" if has_vally else "Smoke"
        tabs.append(("smoke", smoke_label, smoke_body, len(skills)))
    if has_vally:
        vally_body = _render_smoke_panel_inner(aggregated_vally, repo, window_days)
        tabs.append(("vally", "Vally", vally_body, len(vally_skills)))
    if has_fulleval:
        fe_window = fulleval_window_days if fulleval_window_days is not None else window_days
        fe_body, fe_counts = _render_fulleval_panel_inner(aggregated_fulleval, repo, fe_window)
        tabs.append(("fulleval", "Full evals", fe_body, fe_counts["plans"]))

    fe_window = fulleval_window_days if fulleval_window_days is not None else window_days
    return _wrap_n_tabbed(tabs, generated, repo, window_days, fe_window if has_fulleval else None)


def _render_smoke_panel_inner(aggregated: dict, repo: str, window_days: int) -> str:
    """Render the smoke panel inner HTML (summary box + per-skill table).

    Returns just the inner content - no `<html>`, `<head>`, or `<body>` wrap -
    so the same string can be used as the single-page body or as the contents
    of the smoke tab panel.

    Returns an in-panel empty state when ``aggregated`` has no skills.
    """
    by_skill = aggregated["by_skill"]
    all_dates_sorted = sorted(aggregated["all_dates"])  # oldest first for sparkline
    skills = aggregated["all_skills"]
    totals = aggregated["totals"]

    if not skills:
        return (
            '<div class="empty-state">'
            '<p>No smoke-results artifacts found yet for this window.</p>'
            '<p>The first results will appear here after a smoke run uploads a <code>smoke-results-schema-*</code> artifact.</p>'
            '</div>'
        )

    rows_html: list[str] = []
    for skill in skills:
        dates_data = by_skill[skill]["dates"]

        # Pass rate per day, in chronological order (oldest -> newest) for sparkline.
        daily_rates: list[float | None] = []
        for d in all_dates_sorted:
            day = dates_data.get(d)
            if day is None:
                daily_rates.append(None)
            else:
                total = day["pass"] + day["fail"]
                daily_rates.append(day["pass"] / total if total else None)

        # Latest day for THIS skill -- not the newest date across the whole
        # dashboard. If a smoke run only covers one skill today, every other
        # skill's row should still show its most recent in-window result
        # rather than ""—"" (no data).
        skill_dates = sorted(dates_data.keys(), reverse=True) if dates_data else []
        latest_day_str = skill_dates[0] if skill_dates else None
        latest = dates_data.get(latest_day_str) if latest_day_str else None
        latest_summary = "—"
        latest_link = ""
        rate_class = ""
        rate_str = "—"
        if latest:
            total = latest["pass"] + latest["fail"]
            rate = latest["pass"] / total if total else 0
            rate_class = "ok" if rate >= 0.9 else ("warn" if rate >= 0.5 else "bad")
            rate_str = f"{rate * 100:.0f}%"
            latest_summary = f"{latest['pass']}/{total}"
            run_url = f"https://github.com/{repo}/actions/runs/{latest['gh_run_id']}"
            latest_link = f' <a class="run-link" href="{html.escape(run_url)}" title="Open the GitHub Actions run">logs &#x2197;</a>'

        # Window totals.
        win_pass = sum(d["pass"] for d in dates_data.values())
        win_fail = sum(d["fail"] for d in dates_data.values())
        win_total = win_pass + win_fail
        win_rate = win_pass / win_total if win_total else None

        # Tokens cell = window-total tokens + a delta-vs-prior-day indicator
        # (latest day with tokens vs the next-most-recent day with tokens).
        # The delta -- not the line shape -- is what answers Shay's "track
        # tokens over time" guardrail; an inline sparkline competed visually
        # with the pass-rate trend column and added nothing once you knew the
        # direction. With <2 days of token data the delta degrades silently
        # (no arrow appended) so the cell still renders cleanly on day 1.
        win_tokens = sum(int(d.get("day_tokens") or 0) for d in dates_data.values())
        if win_tokens > 0:
            tokens_cell = f"{win_tokens:,}{_render_token_delta(dates_data)}"
        else:
            tokens_cell = '<span class="meta">no data</span>'

        rows_html.append(
            f"<tr>"
            f'<td><strong>{html.escape(skill)}</strong></td>'
            f'<td class="num">{latest_summary}{latest_link}</td>'
            f'<td class="pass-rate {rate_class}">{rate_str}</td>'
            f'<td>{render_sparkline(daily_rates)}</td>'
            f'<td class="num">{win_pass} / {win_total}</td>'
            f'<td class="num tokens-cell">{tokens_cell}</td>'
            f"</tr>"
        )
        # Expandable per-test details under the skill row, populated from
        # the latest day's enriched test_results (rawStatus / duration /
        # found+missing skills + results when present). Also surface per-test
        # billable tokens (inputTokens + outputTokens summed over the window)
        # from the day's token_totals rollup -- helps spot which specific test
        # is driving the skill's window-total token cost. The expanded view
        # also includes a per-day breakdown table when 2+ dates exist, so
        # viewers can read actual numbers instead of interpreting a sparkline.
        if latest and latest.get("test_results"):
            daily_history_html = _render_daily_history(dates_data, repo)
            rows_html.append(_render_test_details(
                latest["test_results"],
                latest.get("token_totals", {}),
                daily_history_html,
                deep_links=latest.get("deep_links"),
                repo=repo,
                gh_run_id=latest.get("gh_run_id") or "",
                producer=latest.get("producer", "legacy"),
            ))

    # Compute the sparkline-hint banner outside the f-string for readability:
    # avoids nested ternaries inside a multi-line template and keeps the
    # template's interpolation slots one-name-each.
    if totals['dates'] < 2:
        sparkline_hint = '<div class="hint">Trend sparklines render as a single dot until at least 2 dates of data accumulate. Tokens show a delta arrow vs the prior day once a second day arrives; the per-skill expanded view also gains a daily history table.</div>'
    else:
        sparkline_hint = ''

    return f"""<div class="summary">
  <strong>Window totals.</strong>
  {totals['runs']} run(s) across {totals['skills']} skill(s) over {totals['dates']} date(s).
  {sparkline_hint}
</div>

<table>
<thead>
<tr><th>Skill area</th><th class="num">Latest</th><th class="num">Rate</th><th>Trend (last {window_days}d)</th><th class="num">Window pass / total</th><th class="num">Tokens (window)</th></tr>
</thead>
<tbody>
{chr(10).join(rows_html)}
</tbody>
</table>
"""


def _wrap_single_smoke(smoke_body: str, generated: str, repo: str, window_days: int) -> str:
    """Wrap the smoke panel inner HTML in a full single-tab HTML document."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>skills-for-fabric — smoke dashboard</title>
<style>{CSS}</style>
</head>
<body>
<h1>skills-for-fabric smoke dashboard</h1>
<p class="subtitle">Generated {html.escape(generated)} from the last {window_days} day(s) of smoke runs.
Schema: <code>docs/skill-test-result-schema.md</code>.</p>

{smoke_body}

<footer>
Static dashboard built by <code>.github/scripts/build-dashboard.py</code>.
Source: <a href="https://github.com/{html.escape(repo)}">{html.escape(repo)}</a>.
</footer>
</body>
</html>
"""


def _wrap_tabbed(smoke_body: str, fe_body: str, generated: str, repo: str,
                 smoke_window_days: int, fulleval_window_days: int,
                 smoke_count: int, fe_count: int) -> str:
    """Legacy 2-tab wrapper (smoke + full-eval). Kept for callers that pass
    the old signature; new code uses `_wrap_n_tabbed` to handle the
    smoke/vally/full-eval split."""
    tabs = [
        ("smoke", "Smoke", smoke_body, smoke_count),
        ("fulleval", "Full evals", fe_body, fe_count),
    ]
    return _wrap_n_tabbed(tabs, generated, repo, smoke_window_days, fulleval_window_days)


def _wrap_n_tabbed(tabs: list[tuple[str, str, str, int]], generated: str,
                   repo: str, smoke_window_days: int,
                   fulleval_window_days: int | None) -> str:
    """Generic N-tab wrapper. `tabs` is a list of (id, label, body, count).

    First tab is `checked`. Each tab is a pure-CSS radio group; sibling
    selectors in the stylesheet show the matching panel. No JS, so the
    page renders identically with JS disabled. Same accessibility contract
    as the 2-tab version: visible label carries the `id` that the panel's
    `aria-labelledby` points at.
    """
    if not tabs:
        return _empty_html(generated, smoke_window_days)

    fe_window_blurb = ""
    if fulleval_window_days is not None:
        fe_window_blurb = f" Full-eval window: last {fulleval_window_days} day(s)."

    radio_inputs = []
    labels = []
    panels = []
    for i, (tab_id, label, body, count) in enumerate(tabs):
        checked = " checked" if i == 0 else ""
        radio_inputs.append(f'<input type="radio" name="tab" id="tab-{tab_id}"{checked}>')
        labels.append(
            f'<label id="tab-label-{tab_id}" for="tab-{tab_id}" role="tab" '
            f'aria-controls="panel-{tab_id}">{html.escape(label)} '
            f'<span class="count">{count}</span></label>'
        )
        panels.append(
            f'<section id="panel-{tab_id}" class="tab-panel" role="tabpanel" '
            f'aria-labelledby="tab-label-{tab_id}">{body}</section>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>skills-for-fabric — evaluation dashboard</title>
<style>{CSS}</style>
</head>
<body>
<h1>skills-for-fabric evaluation dashboard</h1>
<p class="subtitle">Generated {html.escape(generated)} from recent nightly runs. Smoke window: last {smoke_window_days} day(s).{fe_window_blurb}</p>

{''.join(radio_inputs)}
<div class="tabs" role="tablist">
  {''.join(labels)}
</div>
{''.join(panels)}

<footer>
Static dashboard built by <code>.github/scripts/build-dashboard.py</code>.
Source: <a href="https://github.com/{html.escape(repo)}">{html.escape(repo)}</a>.
</footer>
</body>
</html>
"""


def _empty_html(generated: str, window_days: int) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>skills-for-fabric — smoke dashboard</title>
<style>{CSS}</style>
</head>
<body>
<h1>skills-for-fabric smoke dashboard</h1>
<p class="subtitle">Generated {html.escape(generated)}. Window: last {window_days} day(s).</p>
<div class="empty-state">
  <p>No smoke-results artifacts found yet for this window.</p>
  <p>The first results will appear here after a smoke run uploads a <code>smoke-results-schema-*</code> artifact.</p>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Full-eval support
#
# A full-eval RUN downloads to a tree with one or more sibling files:
#     eval-run-telemetry.json   - canonical run metadata (plans[], session
#                                 token usage, exit codes, bail codes)
#     eval-results.md            - human-readable rollup with `## Summary`
#                                  per-skill table and `### <skill>` per-case
#                                  tables.
# Producer: .github/workflows/fabric-full-eval-ephemeral.yml
# Artifact name: full-eval-results-{run_id}
#
# These functions parse both formats, aggregate per-plan across the window,
# and render the "Full evals" tab.
# ---------------------------------------------------------------------------

# Maps plan-folder prefix (under tests/full-eval-tests/plan/...) to a
# user-visible family label. Order matters: families with overlapping prefixes
# must be ordered most-specific first (none today, but keep the dict-walk
# defensive in case folders are added later).
_PLAN_FOLDER_FAMILY: tuple[tuple[str, str], ...] = (
    ("04-combined-skills", "Cross-skill"),
    ("01-foundations", "Foundation"),
    ("02-cross-skill", "Cross-skill"),
)

# Maps a plan-slug-fragment to a family label. Used when the plan lives under
# 03-individual-skills (or has no folder hint). First match wins; ordered so
# specific multi-word prefixes resolve before single tokens (e.g. "powerbi"
# before "spark"-anything).
_PLAN_SLUG_FAMILY: tuple[tuple[str, str], ...] = (
    ("databricks-migration", "Migrations"),
    ("hdinsight-migration", "Migrations"),
    ("synapse-migration", "Migrations"),
    ("medallion", "Cross-skill"),
    ("foundation", "Foundation"),
    ("powerbi", "Power BI"),
    ("eventhouse", "Eventhouse"),
    ("eventstream", "Eventstream"),
    ("dataflows", "Dataflows"),
    ("activator", "Activator"),
    ("sqldw", "SQL DW"),
    ("spark", "Spark"),
)

# Render order for family sections. Families not listed here fall to the end
# in alphabetical order (defensive: keeps a never-mapped family visible
# rather than dropping it).
_FAMILY_ORDER: tuple[str, ...] = (
    "Spark", "SQL DW", "Eventhouse", "Dataflows", "Power BI",
    "Activator", "Eventstream", "Migrations", "Foundation", "Cross-skill",
)


def family_of(plan_path: str | None, plan_slug: str = "") -> str:
    """Classify a plan into a family label.

    Uses the folder prefix from ``plan_path`` first (so a plan moved into
    ``04-combined-skills/`` is grouped under Cross-skill regardless of its
    slug), then falls back to a slug-keyword scan.
    """
    path_norm = (plan_path or "").replace("\\", "/").lower()
    for prefix, family in _PLAN_FOLDER_FAMILY:
        if f"/{prefix}/" in f"/{path_norm}/" or path_norm.startswith(f"{prefix}/") or path_norm.startswith(f"plan/{prefix}/"):
            return family
    slug = (plan_slug or "").lower()
    # Strip a leading "eval-" prefix (str.startswith, not lstrip(), so we
    # do not nibble individual e/v/a/l characters from genuine slugs like
    # "eval-eventhouse-authoring" -> "enthouse-authoring").
    if slug.startswith("eval-"):
        slug = slug[len("eval-"):]
    for keyword, family in _PLAN_SLUG_FAMILY:
        if keyword in slug:
            return family
    return "Other"


def _plan_slug_to_skill_names(plan_slug: str) -> list[str]:
    """Map a plan slug to one or more `<skill>-cli` section names.

    Examples:
        eval-spark-authoring -> ["spark-authoring-cli"]
        eval-spark-authoring-plus-consumption -> ["spark-authoring-cli", "spark-consumption-cli"]
        eval-medallion -> ["medallion"]  # no -cli suffix; may match no section
        eval-databricks-migration -> ["databricks-migration"]
    """
    s = (plan_slug or "").strip()
    if s.startswith("eval-"):
        s = s[len("eval-"):]
    if "-plus-" in s:
        # eval-spark-authoring-plus-consumption -> ["spark-authoring", "spark-consumption"]
        # The token to the left of "-plus-" is the family-prefixed pair head;
        # the token after is the second half (consumption / authoring).
        head, _, tail = s.partition("-plus-")
        # Determine the family prefix by stripping the trailing role from head.
        # e.g. "spark-authoring" -> family="spark", second_role=tail.
        last_dash = head.rfind("-")
        if last_dash > 0:
            family_prefix = head[:last_dash]
            return [f"{head}-cli", f"{family_prefix}-{tail}-cli"]
        return [f"{head}-cli", f"{tail}-cli"]
    return [f"{s}-cli"]


# Per-case markdown rows in the form
# `| Case | Title | Result | Notes |`.
_RE_CASE_ROW = __import__("re").compile(
    r"^\|\s*(?P<case>[^|]+?)\s*\|\s*(?P<title>[^|]+?)\s*\|\s*(?P<result>[^|]+?)\s*\|\s*(?P<notes>[^|]*?)\s*\|\s*$",
    __import__("re").MULTILINE,
)


def parse_eval_results_md(text: str) -> dict:
    """Parse an `eval-results.md` file.

    Returns:
        {
            "perSkill": {
                "<skill-name>": [
                    {"case": str, "title": str, "result": "PASS"|"FAIL"|"SKIP"|other, "notes": str},
                    ...
                ],
                ...
            },
        }

    The summary table is intentionally NOT parsed - the per-plan telemetry
    JSON is the authoritative pass/fail/skip source. The markdown is read
    only for the per-case detail block.
    """
    import re

    per_skill: dict[str, list[dict]] = {}
    if not text:
        return {"perSkill": per_skill}

    # Find each `### <skill>` section and the markdown body between it and
    # the next H2/H3 / EOF.
    headings = list(re.finditer(r"^(?P<level>#{2,3})\s+(?P<title>.+?)\s*$", text, re.MULTILINE))
    for i, m in enumerate(headings):
        if m.group("level") != "###":
            continue
        skill_name = m.group("title").strip()
        body_start = m.end()
        body_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[body_start:body_end]

        cases: list[dict] = []
        for row in _RE_CASE_ROW.finditer(body):
            case = row.group("case").strip()
            title = row.group("title").strip()
            result_raw = row.group("result").strip()
            notes = row.group("notes").strip()
            # Skip the header row and the markdown table separator (`---`).
            if case.lower() == "case" or set(case.replace(":", "").replace("-", "")) <= {""}:
                continue
            if "---" in case:
                continue
            cases.append({
                "case": case,
                "title": title,
                "result": _normalize_eval_result(result_raw),
                "result_raw": result_raw,
                "notes": notes,
            })

        if cases:
            per_skill[skill_name] = cases

    return {"perSkill": per_skill}


def _normalize_eval_result(raw: str) -> str:
    """Map a raw markdown result cell to one of: PASS, FAIL, ERROR, SKIP, OTHER.

    The producer emits ``✅ PASS`` / ``❌ FAIL`` / ``❌ ERROR`` / ``⏭️ SKIP`` etc.
    We map on substring so future emoji/format tweaks don't break parsing.
    Order matters: check ERROR before FAIL (some emitters write "ERROR" in
    a cell that also contains the word "fail" via context).
    """
    s = (raw or "").upper()
    if "PASS" in s:
        return "PASS"
    if "ERROR" in s:
        return "ERROR"
    if "FAIL" in s:
        return "FAIL"
    if "SKIP" in s:
        return "SKIP"
    return "OTHER"


def discover_fulleval_runs(input_root: Path) -> list[dict]:
    """Walk ``input_root`` for full-eval artifact contents.

    Each downloaded ``full-eval-results-*`` artifact gives us a tree with
    (at least) an ``eval-run-telemetry.json`` somewhere inside it. We
    associate each telemetry file with the nearest sibling ``eval-results.md``
    (if any) and tag each run with a date derived from the telemetry's
    ``generatedAt`` field (UTC).

    Returns:
        list of run records, one per telemetry file found:
            {
                "date": "YYYY-MM-DD",       # from generatedAt (UTC)
                "run_id": str,              # from path (run-<id>) or generatedAt fallback
                "telemetry": dict,          # parsed JSON
                "per_skill_cases": dict,    # from sibling eval-results.md
            }

    Missing or malformed telemetry files are skipped (with a print warning).
    """
    if not input_root or not input_root.exists():
        return []

    out: list[dict] = []
    for tel_path in input_root.rglob("eval-run-telemetry.json"):
        try:
            telemetry = json.loads(tel_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"WARNING: skipping malformed telemetry at {tel_path}: {exc}", file=sys.stderr)
            continue

        generated_at = telemetry.get("generatedAt")
        date_str = _date_from_generated_at(generated_at)
        if not date_str:
            print(f"WARNING: skipping telemetry without parseable generatedAt at {tel_path}: {generated_at!r}", file=sys.stderr)
            continue

        # Find a sibling eval-results.md - look in the same directory first,
        # then walk up to the artifact root. There is exactly one md per run
        # in the producer's upload step.
        results_md_path = _find_sibling(tel_path, "eval-results.md", input_root)
        per_skill_cases: dict[str, list[dict]] = {}
        if results_md_path is not None:
            try:
                md_text = results_md_path.read_text(encoding="utf-8")
                per_skill_cases = parse_eval_results_md(md_text).get("perSkill", {})
            except OSError as exc:
                print(f"WARNING: failed to read {results_md_path}: {exc}", file=sys.stderr)

        # Derive a run_id from the artifact folder name (the workflow
        # downloads each artifact into `run-<id>`). Fall back to the
        # generatedAt timestamp if we can't find it.
        run_id = _derive_run_id_from_path(tel_path, input_root) or generated_at or "unknown"

        out.append({
            "date": date_str,
            "run_id": str(run_id),
            "telemetry": telemetry,
            "per_skill_cases": per_skill_cases,
        })
    return out


def _date_from_generated_at(generated_at: object) -> str | None:
    """Parse ``2026-04-12T17:23:12.4573390+03:00`` -> ``2026-04-12`` (UTC)."""
    if not isinstance(generated_at, str) or not generated_at:
        return None
    try:
        # fromisoformat handles offset suffixes from Python 3.11+.
        parsed = dt.datetime.fromisoformat(generated_at)
    except ValueError:
        # Try to strip subsecond precision past 6 digits (some emitters
        # produce 7-digit fractional seconds which 3.11 rejects).
        import re
        cleaned = re.sub(r"(\.\d{6})\d+", r"\1", generated_at)
        try:
            parsed = dt.datetime.fromisoformat(cleaned)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%d")


def _find_sibling(start_path: Path, name: str, root: Path) -> Path | None:
    """Walk up from ``start_path`` (exclusive) looking for a sibling ``name``."""
    parent = start_path.parent
    root_resolved = root.resolve()
    while True:
        candidate = parent / name
        if candidate.exists() and candidate.is_file():
            return candidate
        if parent.resolve() == root_resolved:
            return None
        if parent.parent == parent:  # filesystem root
            return None
        parent = parent.parent


def _derive_run_id_from_path(tel_path: Path, root: Path) -> str | None:
    """Look for a ``run-<id>`` directory name in the path relative to root."""
    try:
        rel = tel_path.relative_to(root)
    except ValueError:
        return None
    for part in rel.parts:
        if part.startswith("run-") and len(part) > 4:
            return part[4:]
    return None


def _fulleval_run_key(run_id_str: object) -> tuple[int, str]:
    """Parse a run_id for ordering. Returns ``(int_part, original)``.

    Used to compare two same-day full-eval runs. String compare is wrong
    here -- ``"9" >= "10"`` is True under lex compare, which would let an
    older same-day run beat a newer one when their IDs differ in length.
    GitHub Actions run IDs are numeric (e.g. ``"25988928060"``). The
    original string is kept as a stable tiebreaker for non-numeric IDs.
    """
    s = str(run_id_str or "")
    try:
        return (int(s), s)
    except ValueError:
        return (0, s)


def aggregate_fulleval_by_plan(runs: list[dict], window_days: int) -> dict:
    """Aggregate per-plan results across all in-window full-eval runs.

    Returns:
        {
            "plans": {plan_slug: {
                "plan": str,
                "planPath": str,
                "family": str,
                "dates": {date: {  # one entry per (plan, date)
                    "run_id": str,
                    "status": "completed"|"bailed_out"|"error"|"failed"|"timed_out"|"skipped"|"skipped_warehouse"|"skipped_lakehouse",
                    "duration_seconds": float|None,
                    "input_tokens": int,
                    "output_tokens": int,
                    "cache_read_tokens": int,
                    "cache_write_tokens": int,
                    "bail_code": str|None,
                    "exit_code": int|None,
                    "skills_used": list[str],
                    "assistant_turns": int|None,
                    "tool_calls": int|None,
                    "cases": list[dict],   # from results.md for this plan's skill(s)
                    "pass": int, "fail": int, "error": int, "skip": int,
                }},
            }},
            "all_dates": sorted desc list of date strings,
            "totals": {"runs": int, "plans": int, "dates": int},
        }
    """
    today = dt.datetime.now(dt.timezone.utc).date()
    cutoff = today - dt.timedelta(days=window_days)

    plans_by_slug: dict[str, dict] = {}
    all_dates: set[str] = set()
    windowed_runs: set[str] = set()

    for run in runs:
        try:
            run_date = dt.datetime.strptime(run["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if run_date < cutoff:
            continue

        windowed_runs.add(run.get("run_id") or run["date"])
        all_dates.add(run["date"])

        telemetry = run.get("telemetry") or {}
        per_skill_cases = run.get("per_skill_cases") or {}

        for plan_entry in telemetry.get("plans") or []:
            slug = (plan_entry.get("plan") or "").strip()
            if not slug:
                continue
            plan_path = (plan_entry.get("planPath") or "").replace("\\", "/")
            family = family_of(plan_path, slug)

            rec = plans_by_slug.setdefault(slug, {
                "plan": slug,
                "planPath": plan_path,
                "family": family,
                "dates": {},
            })
            # If we already have an entry for this plan on this date from a
            # different run_id (rare but possible if two runs landed on the
            # same day), keep the most recent by NUMERIC run_id compare.
            # String compare is wrong: "9" >= "10" is True lex, so an older
            # same-day run would beat a newer one if ID lengths differ.
            existing = rec["dates"].get(run["date"])
            if existing and _fulleval_run_key(existing.get("run_id", "")) >= _fulleval_run_key(run["run_id"]):
                continue

            # Collect token usage across all models exercised by this plan.
            input_t = output_t = cache_r = cache_w = 0
            session = plan_entry.get("session") or {}
            metrics = ((session.get("tokenUsage") or {}).get("modelMetrics") or {})
            for model_metrics in metrics.values():
                usage = (model_metrics or {}).get("usage") or {}
                input_t += int(usage.get("inputTokens") or 0)
                output_t += int(usage.get("outputTokens") or 0)
                cache_r += int(usage.get("cacheReadTokens") or 0)
                cache_w += int(usage.get("cacheWriteTokens") or 0)

            # Stitch per-skill cases from the markdown. A plan may exercise
            # multiple skills (combined plans). Concatenate the case lists in
            # source order so the expanded view shows them grouped by skill.
            case_rows: list[dict] = []
            for skill_name in _plan_slug_to_skill_names(slug):
                cases = per_skill_cases.get(skill_name) or []
                for c in cases:
                    case_rows.append({**c, "skill": skill_name})

            pass_count = sum(1 for c in case_rows if c.get("result") == "PASS")
            fail_count = sum(1 for c in case_rows if c.get("result") == "FAIL")
            error_count = sum(1 for c in case_rows if c.get("result") == "ERROR")
            skip_count = sum(1 for c in case_rows if c.get("result") == "SKIP")

            rec["dates"][run["date"]] = {
                "run_id": run["run_id"],
                "status": plan_entry.get("status") or "skipped",
                "duration_seconds": plan_entry.get("durationSeconds"),
                "input_tokens": input_t,
                "output_tokens": output_t,
                "cache_read_tokens": cache_r,
                "cache_write_tokens": cache_w,
                "bail_code": plan_entry.get("bailOutCode"),
                "exit_code": plan_entry.get("exitCode"),
                "skills_used": list(session.get("skillsUsed") or []),
                "assistant_turns": session.get("assistantTurnCount"),
                "tool_calls": session.get("toolCallCount"),
                "cases": case_rows,
                "pass": pass_count,
                "fail": fail_count,
                "error": error_count,
                "skip": skip_count,
            }

    return {
        "plans": plans_by_slug,
        "all_dates": sorted(all_dates, reverse=True),
        "totals": {
            "runs": len(windowed_runs),
            "plans": len(plans_by_slug),
            "dates": len(all_dates),
        },
    }


def _family_sort_key(family: str) -> tuple[int, str]:
    """Stable family ordering: known families first (in declared order),
    unknown families alphabetical at the end.
    """
    try:
        return (_FAMILY_ORDER.index(family), family)
    except ValueError:
        return (len(_FAMILY_ORDER), family)


def _render_fulleval_panel_inner(aggregated_fulleval: dict, repo: str, window_days: int) -> tuple[str, dict]:
    """Render the full-eval tab inner HTML (summary + family-grouped tables).

    Returns ``(html, counts)`` where ``counts`` is a small dict the tab
    UI uses for the badge next to the tab label.
    """
    plans = aggregated_fulleval.get("plans") or {}
    all_dates_sorted = sorted(aggregated_fulleval.get("all_dates") or [])  # oldest first
    totals = aggregated_fulleval.get("totals") or {}

    if not plans:
        empty = (
            '<div class="empty-state">'
            '<p>No full-eval artifacts found yet for this window.</p>'
            '<p>The first results will appear here after a nightly run uploads a <code>full-eval-results-*</code> artifact.</p>'
            '</div>'
        )
        return empty, {"plans": 0}

    # Group by family.
    families: dict[str, list[dict]] = defaultdict(list)
    for slug in sorted(plans.keys()):
        rec = plans[slug]
        families[rec["family"]].append(rec)

    completed_total = bailed_total = errored_total = skipped_total = 0
    pass_total = fail_total = error_total = skip_total = 0
    sections_html: list[str] = []

    for family in sorted(families.keys(), key=_family_sort_key):
        plan_recs = families[family]
        rows: list[str] = []
        for rec in plan_recs:
            dates_data = rec["dates"]
            if not dates_data:
                continue
            latest_date = sorted(dates_data.keys(), reverse=True)[0]
            latest = dates_data[latest_date]

            status = latest["status"]
            if status == "completed":
                completed_total += 1
            elif status == "bailed_out":
                bailed_total += 1
            elif status in ("error", "failed", "timed_out"):
                # The producer (tests/run-full-tests.ps1 Get-RunStatus)
                # emits "error" -- not "failed"/"timed_out" -- for any
                # non-zero exit code. Bucket all three together so a
                # genuine plan-level failure is never reported as 0.
                errored_total += 1
            elif status.startswith("skipped"):
                # Covers "skipped", "skipped_warehouse", "skipped_lakehouse".
                skipped_total += 1
            pass_total += latest["pass"]
            fail_total += latest["fail"]
            error_total += latest.get("error", 0)
            skip_total += latest["skip"]

            # Pass-rate trend across in-window dates for this plan
            # (chronological oldest -> newest for the sparkline). The
            # denominator includes ERROR test results -- they're failures,
            # not skips, even when the cause is infrastructure missing.
            daily_rates: list[float | None] = []
            for d in all_dates_sorted:
                day = dates_data.get(d)
                if day is None:
                    daily_rates.append(None)
                else:
                    exec_count = day["pass"] + day["fail"] + day.get("error", 0)
                    daily_rates.append(day["pass"] / exec_count if exec_count else None)

            executed = latest["pass"] + latest["fail"] + latest.get("error", 0)
            rate = (latest["pass"] / executed) if executed else None
            if rate is None:
                rate_class = "warn"
                rate_str = "—"
            else:
                rate_class = "ok" if rate >= 0.9 else ("warn" if rate >= 0.5 else "bad")
                rate_str = f"{rate * 100:.0f}%"

            tokens_total = latest["input_tokens"] + latest["output_tokens"]
            tokens_cell = f"{tokens_total:,}" if tokens_total > 0 else '<span class="meta">—</span>'

            duration_s = latest.get("duration_seconds")
            if isinstance(duration_s, (int, float)) and duration_s > 0:
                duration_str = f"{duration_s / 60:.1f}m"
            else:
                duration_str = "—"

            run_link = ""
            if latest.get("run_id") and str(latest["run_id"]).isdigit():
                run_url = f"https://github.com/{repo}/actions/runs/{latest['run_id']}"
                run_link = f' <a class="run-link" href="{html.escape(run_url)}" title="Open the GitHub Actions run">logs &#x2197;</a>'

            status_label = status.replace("_", " ")
            # Surface error count separately in the "Latest pass" cell so a
            # row reading "5/10 (2 skip)" + 3 errors doesn't look like 5/10
            # pass when it's really 5/(5+2+3)=50%, not 5/10=50% by accident.
            extras: list[str] = []
            if latest["skip"]:
                extras.append(f'{latest["skip"]} skip')
            if latest.get("error", 0):
                extras.append(f'{latest["error"]} error')
            extras_html = ""
            if extras:
                extras_html = f' <span class="meta" style="color:var(--fg-muted)">({", ".join(extras)})</span>'

            rows.append(
                "<tr>"
                f'<td><span class="plan-name">{html.escape(rec["plan"])}</span>{run_link}</td>'
                f'<td><span class="plan-status {html.escape(status)}">{html.escape(status_label)}</span></td>'
                f'<td class="num">{latest["pass"]}/{executed}{extras_html}</td>'
                f'<td class="pass-rate {rate_class}">{rate_str}</td>'
                f'<td>{render_sparkline(daily_rates)}</td>'
                f'<td class="num">{duration_str}</td>'
                f'<td class="num tokens-cell">{tokens_cell}</td>'
                "</tr>"
            )
            rows.append(_render_fulleval_details(rec, latest))

        plan_count = len(plan_recs)
        sections_html.append(
            f'<div class="fe-section">{html.escape(family)} '
            f'<span class="count">({plan_count} plan{"s" if plan_count != 1 else ""})</span></div>'
            '<table>'
            '<thead>'
            f'<tr><th>Plan</th><th>Status</th><th class="num">Latest pass</th><th class="num">Rate</th>'
            f'<th>Trend (last {window_days}d)</th><th class="num">Duration</th><th class="num">Tokens</th></tr>'
            '</thead>'
            f'<tbody>{chr(10).join(rows)}</tbody>'
            '</table>'
        )

    executed_total = pass_total + fail_total + error_total
    overall_rate = (pass_total / executed_total) if executed_total else None
    if overall_rate is None:
        overall_rate_class = "warn"
        overall_rate_str = "—"
    else:
        overall_rate_class = "ok" if overall_rate >= 0.9 else ("warn" if overall_rate >= 0.5 else "bad")
        overall_rate_str = f"{overall_rate * 100:.1f}%"

    sparkline_hint = ""
    if (totals.get("dates") or 0) < 2:
        sparkline_hint = '<span class="hint" style="display:block; margin-top:0.4em;">Trend sparklines render as a single dot until at least 2 dates of data accumulate.</span>'

    # Build summary chip list dynamically so we don't show "0 skipped" noise
    # on healthy runs, but DO surface a skipped chip when one or more plans
    # were skipped (so the run doesn't look like it had nothing to do).
    plan_chips: list[str] = [
        f'<span class="plan-status completed">{completed_total} completed</span>',
        f'<span class="plan-status bailed_out">{bailed_total} bailed</span>',
        f'<span class="plan-status error">{errored_total} errored</span>',
    ]
    if skipped_total:
        plan_chips.append(f'<span class="plan-status skipped">{skipped_total} skipped</span>')

    # Same logic for test-level chips.
    case_parts: list[str] = [
        f'<strong>{pass_total}</strong> pass',
        f'{fail_total} fail',
    ]
    if error_total:
        case_parts.append(f'{error_total} error')
    case_parts.append(f'{skip_total} skip')

    summary_html = (
        '<div class="summary">'
        f'<strong>Latest nightly.</strong> '
        f'{len(plans)} plan(s): '
        f'{" ".join(plan_chips)}. '
        f'Test-level: {" / ".join(case_parts)} '
        f'(<span class="pass-rate {overall_rate_class}">{overall_rate_str}</span> over executed). '
        f'Window: last {window_days} day(s) across {totals.get("dates", 0)} date(s).'
        f'{sparkline_hint}'
        '</div>'
    )

    return summary_html + "\n" + "\n".join(sections_html), {"plans": len(plans)}


def _render_fulleval_details(plan_rec: dict, latest: dict) -> str:
    """Render the expandable per-plan detail row: telemetry chips + case table."""
    plan_slug = plan_rec.get("plan", "")
    plan_path = plan_rec.get("planPath", "")

    chips: list[str] = []
    if plan_path:
        chips.append(f'<span class="chip">Plan path: <strong class="plan-name">{html.escape(plan_path)}</strong></span>')
    duration_s = latest.get("duration_seconds")
    if isinstance(duration_s, (int, float)) and duration_s > 0:
        chips.append(f'<span class="chip">Duration: <strong>{duration_s:.1f}s</strong></span>')
    if latest.get("input_tokens"):
        chips.append(f'<span class="chip">Input tokens: <strong>{latest["input_tokens"]:,}</strong></span>')
    if latest.get("output_tokens"):
        chips.append(f'<span class="chip">Output tokens: <strong>{latest["output_tokens"]:,}</strong></span>')
    if latest.get("cache_read_tokens"):
        chips.append(f'<span class="chip">Cache reads: <strong>{latest["cache_read_tokens"]:,}</strong></span>')
    bail_code = latest.get("bail_code")
    if bail_code:
        chips.append(f'<span class="chip bailout">Bail code: <strong>{html.escape(str(bail_code))}</strong></span>')
    exit_code = latest.get("exit_code")
    if exit_code is not None and exit_code != 0:
        # Status "error" comes from Get-RunStatus when ExitCode != 0;
        # "failed"/"timed_out" are not currently emitted by the producer
        # but are accepted for forward compatibility.
        cls = "failed" if latest.get("status") in ("error", "failed", "timed_out") else "bailout"
        chips.append(f'<span class="chip {cls}">Exit code: <strong>{html.escape(str(exit_code))}</strong></span>')
    # assistant_turns and tool_calls come from the producer's JSON
    # telemetry. Even though they're documented as ints, an upstream
    # type mismatch (string from JSON) would inject raw HTML. Coerce
    # via html.escape(str(...)) for defense in depth.
    if latest.get("assistant_turns") is not None:
        chips.append(f'<span class="chip">Assistant turns: <strong>{html.escape(str(latest["assistant_turns"]))}</strong></span>')
    if latest.get("tool_calls") is not None:
        chips.append(f'<span class="chip">Tool calls: <strong>{html.escape(str(latest["tool_calls"]))}</strong></span>')

    cases = latest.get("cases") or []
    case_rows: list[str] = []
    last_skill = None
    for c in cases:
        skill = c.get("skill") or ""
        # Insert a thin per-skill divider row when combined plans show two
        # skills back-to-back.
        if skill and skill != last_skill:
            case_rows.append(
                '<tr><td colspan="3" class="meta" style="background: var(--bg-muted); '
                f'font-weight: 600;">{html.escape(skill)}</td></tr>'
            )
            last_skill = skill
        result = c.get("result", "OTHER")
        if result == "PASS":
            badge_class, label = "Y", "Y"
        elif result == "FAIL":
            badge_class, label = "N", "N"
        elif result == "ERROR":
            # ERROR is a failure category too -- same visual treatment as
            # FAIL so it can't be overlooked, distinct label so the cause
            # (infra missing / non-zero exit) is identifiable at a glance.
            badge_class, label = "N", "E"
        elif result == "SKIP":
            badge_class, label = "skip", "—"
        else:
            badge_class, label = "F", "?"
        case_id = c.get("case") or ""
        title = c.get("title") or ""
        notes = c.get("notes") or ""
        meta = f'<div class="meta">{html.escape(notes)}</div>' if notes else ""
        case_rows.append(
            "<tr>"
            f'<td><span class="status-badge {badge_class}">{label}</span></td>'
            f'<td class="test-name">{html.escape(case_id)}</td>'
            f'<td>{html.escape(title)}{meta}</td>'
            "</tr>"
        )

    case_count = len(cases)
    case_table = ""
    if case_count > 0:
        case_table = f'<table class="test-grid">{"".join(case_rows)}</table>'

    summary_label = f'Show telemetry'
    if case_count > 0:
        summary_label = f'Show {case_count} case{"s" if case_count != 1 else ""} + telemetry'

    return (
        '<tr class="details"><td colspan="7">'
        '<details class="skill-details">'
        f'<summary>{summary_label}</summary>'
        f'<div class="fe-detail-chips">{"".join(chips)}</div>'
        f'{case_table}'
        '</details></td></tr>'
    )


# Class-style alias kept ASCII-clean even with non-ASCII characters above
# (no impact on runtime; just a header for the next section).


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    all_runs = discover_runs(args.input_root)
    legacy_runs = [r for r in all_runs if r.get("producer") != "vally"]
    vally_runs = [r for r in all_runs if r.get("producer") == "vally"]
    print(
        f"Discovered {len(all_runs)} smoke run record(s) in {args.input_root} "
        f"({len(legacy_runs)} legacy + {len(vally_runs)} vally)"
    )

    aggregated = aggregate_by_skill(legacy_runs, args.window_days)
    print(
        f"Aggregated legacy smoke: {aggregated['totals']['runs']} runs, "
        f"{aggregated['totals']['skills']} skills, "
        f"{aggregated['totals']['dates']} dates within last {args.window_days} day(s)"
    )

    # Always aggregate vally separately so the renderer can decide whether
    # to surface its tab. None means "no vally artifacts existed at all";
    # an aggregated-but-empty bucket means "vally producer ran but the
    # window dropped all rows" (still surface the tab + empty state).
    aggregated_vally = None
    if vally_runs:
        aggregated_vally = aggregate_by_skill(vally_runs, args.window_days)
        print(
            f"Aggregated vally smoke: {aggregated_vally['totals']['runs']} runs, "
            f"{aggregated_vally['totals']['skills']} skills, "
            f"{aggregated_vally['totals']['dates']} dates within last {args.window_days} day(s)"
        )

    aggregated_fulleval = None
    if args.fulleval_input_root is not None:
        fe_runs = discover_fulleval_runs(args.fulleval_input_root)
        print(f"Discovered {len(fe_runs)} full-eval run record(s) in {args.fulleval_input_root}")
        aggregated_fulleval = aggregate_fulleval_by_plan(fe_runs, args.fulleval_window_days)
        print(
            f"Aggregated full-eval: {aggregated_fulleval['totals']['runs']} runs, "
            f"{aggregated_fulleval['totals']['plans']} plans, "
            f"{aggregated_fulleval['totals']['dates']} dates within last {args.fulleval_window_days} day(s)"
        )

    html_str = render_html(
        aggregated,
        repo=args.repo,
        window_days=args.window_days,
        aggregated_fulleval=aggregated_fulleval,
        fulleval_window_days=args.fulleval_window_days,
        aggregated_vally=aggregated_vally,
    )
    out_index = args.output_dir / "index.html"
    out_index.write_text(html_str, encoding="utf-8")
    print(f"Wrote {out_index} ({len(html_str)} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
