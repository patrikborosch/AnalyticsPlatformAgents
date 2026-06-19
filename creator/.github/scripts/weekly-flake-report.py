#!/usr/bin/env python3
"""Weekly flake report for skills-for-fabric smoke health.

Reads the last N completed smoke runs on `main`, downloads the schema-format
artifacts, computes per-test pass/fail patterns over the window, joins them
against the per-team contact info in `.github/skill-ownership.yml` (the
single source of truth for skill ownership) and the current `flaky` field
in `tests/tests.json`, and emits a single markdown report.

The report is meant to be reviewed by the eval team. For each team it
includes:
  - per-test "last N runs" outcome string (Y/F/N characters, oldest -> newest)
  - "Likely cause" hypothesis (see classify_cause() for taxonomy)
  - drafted GitHub-issue comment body and email body (to be sent manually by
    the eval-team owner, NOT auto-posted)
  - flag-removal candidates (tests with the flaky.githubIssue field set that
    have N consecutive passes in this window)

Tests are routed to teams via `tests.json::expectedSkills[i]` ->
`skill-ownership.yml::skills[<skill>].owningTeam` -> team.contact. Tests with
empty expectedSkills (e.g., persona/agent tests) are bucketed under a
single 'unmapped' section with TBD owner.

The script does NOT post comments, open issues, or send email. It writes a
markdown file. The eval team owner reviews it and decides which actions to
take, one at a time.

Usage:
  python .github/scripts/weekly-flake-report.py --runs 5 --output reports/weekly-2026-05-20.md

  # Cross-repo / fork usage:
  python .github/scripts/weekly-flake-report.py --runs 5 --output report.md --repo my-org/my-fork

Requirements:
  - `gh` CLI authenticated with read access to the repo
  - Python 3.10+
  - PyYAML (the manifest loader requires it)
  - Run from the repo root (uses tests/tests.json + .github/skill-ownership.yml)

By default, the script targets gim-home/skills-for-fabric. Override with
--repo or the GITHUB_REPOSITORY env var (matching the GH Actions convention).
The selected repo is passed to every gh command, so the tool is safe to run
from any working directory.

The 'Likely cause' values emitted by classify_cause() include (this list is the
canonical taxonomy; keep in sync with the function):
  - "stable"
  - "no-data" / "no-data (test absent from all runs)"
  - "known-flaky (flaky issue is referenced) -- check issue status"
  - "consistently N (flaky flag references an issue but window is all unexpected fails -- check whether the flaky issue is resolved or whether a different bug surfaced)"
  - "consistently broken (no flaky flag -- needs triage / new issue)"
  - "intermittent (flaky-flagged; partial passes this window)"
  - "intermittent / flake"
  - "mixed F+N -- multiple causes; review per-test output"
  - "unclear"
These hints are coarse; the eval team refines during review.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

# Manifest loader lives under tests/ (shared with coverage_enforcement.py and
# the manifest validator). Path-extending this way keeps a single owner.
_REPO_ROOT_GUESS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT_GUESS / "tests"))
from skill_ownership_manifest import (  # noqa: E402
    get_team_contact,
    load_skill_ownership_manifest,
)

DEFAULT_REPO = "gim-home/skills-for-fabric"
SMOKE_WORKFLOW = "fabric-smoke-ephemeral.yml"
UNMAPPED_SECTION = "<unmapped>"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runs", type=int, default=5, help="Number of most-recent completed smoke runs on main to include")
    p.add_argument("--output", type=Path, required=True, help="Path to write the report markdown")
    p.add_argument("--repo", type=str,
                   default=os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO),
                   help=f"Target repo (owner/name). Defaults to $GITHUB_REPOSITORY when set, "
                        f"otherwise '{DEFAULT_REPO}'. The chosen value is passed to every gh "
                        f"command so the tool is safe to run from forks or other repos.")
    p.add_argument("--repo-root", type=Path, default=None,
                   help="Repo root for reading tests/tests.json + .github/skill-ownership.yml. "
                        "Defaults to the script's auto-resolved repo root (computed from __file__) "
                        "so the tool works from any cwd. Pass an explicit path to override -- e.g. "
                        "when running against a checkout other than the one this script lives in. "
                        "Independent from --repo: --repo-root selects the LOCAL filesystem checkout; "
                        "--repo selects the REMOTE repository that gh commands target.")
    p.add_argument("--keep-artifacts", action="store_true", help="Don't delete downloaded artifacts")
    p.add_argument("--flag-removal-min-passes", type=int, default=3,
                   help="Min consecutive Y outcomes for a flaky-flagged test to be flagged as a removal candidate")
    return p.parse_args(argv)


def gh(args: list[str], capture: bool = True) -> str:
    """Run `gh` and return stdout. Raise on non-zero exit."""
    result = subprocess.run(["gh", *args], capture_output=capture, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def discover_runs(n: int, repo: str) -> list[dict]:
    """Return the most recent `n` completed smoke runs on main, oldest -> newest."""
    raw = gh([
        "run", "list",
        "--repo", repo,
        "--workflow", SMOKE_WORKFLOW,
        "--branch", "main",
        "--status", "completed",
        "--limit", str(n),
        "--json", "databaseId,createdAt,conclusion,event",
    ])
    runs = json.loads(raw)
    # gh returns newest -> oldest; reverse so we go oldest -> newest (matches dashboard)
    runs.reverse()
    return runs


def download_schema_artifact(run_id: int, dest: Path, repo: str) -> Path | None:
    """Download the `smoke-results-schema-*` artifact for a given run.

    Returns the directory the artifact was unpacked into, or None if no schema
    artifact exists for this run (legacy / startup-failure runs).
    """
    artifact_list_raw = gh([
        "api", f"repos/{repo}/actions/runs/{run_id}/artifacts",
        "--jq", '.artifacts[] | select(.name | startswith("smoke-results-schema-")) | .name',
    ])
    artifact_names = [n.strip() for n in artifact_list_raw.splitlines() if n.strip()]
    if not artifact_names:
        return None
    run_dest = dest / f"run-{run_id}"
    run_dest.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "gh", "run", "download", str(run_id),
        "--repo", repo,
        "--pattern", "smoke-results-schema-*",
        "--dir", str(run_dest),
    ], check=True)
    return run_dest


def parse_test_results_for_run(run_dir: Path) -> dict[str, dict]:
    """Walk the schema layout under run_dir and return {test_name: {area, isPass, rawStatus}}.

    Schema layout per docs/skill-test-result-schema.md:
      <download_root>/smoke-results-schema-*/<date>/<run_id>/<area>/testResults.json

    Each testResults.json contains:
      { "<test_name>": {"isPass": bool, "rawStatus": "Y"|"F"|"N", ...}, ... }
    """
    results: dict[str, dict] = {}
    for testresults_path in run_dir.rglob("testResults.json"):
        area = testresults_path.parent.name
        try:
            data = json.loads(testresults_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        # testResults.json carries a reserved top-level `schemaVersion` int
        # (the on-disk contract version) alongside the per-stim entries. Drop
        # any non-object top-level value so a metadata field is never treated
        # as a test case (`.get()` on an int would raise). See
        # docs/skill-test-result-schema.md.
        data = {k: v for k, v in data.items() if isinstance(v, dict)}
        for test_name, test_info in data.items():
            results[test_name] = {
                "area": area,
                "isPass": bool(test_info.get("isPass")),
                "rawStatus": test_info.get("rawStatus", "?"),
            }
    return results


def load_ownership(manifest_path: Path) -> dict:
    """Load .github/skill-ownership.yml as the single source of truth.

    Returns a dict with two keys for callers:
      - manifest:     the raw parsed YAML (used to render team displayName)
      - skill_to_team: {skill_name: team_name} for fast lookup. Includes
                       only skills with an owningTeam set.

    The team contact is fetched lazily via get_team_contact(manifest, team).
    """
    manifest = load_skill_ownership_manifest(manifest_path)
    skill_to_team: dict[str, str] = {}
    for skill_name, meta in (manifest.get("skills") or {}).items():
        if isinstance(meta, dict):
            team = meta.get("owningTeam")
            if team:
                skill_to_team[skill_name] = team
    return {
        "manifest": manifest,
        "skill_to_team": skill_to_team,
    }


def resolve_test_team(test_entry: dict, skill_to_team: dict[str, str]) -> str:
    """Return the owning team for a test, or UNMAPPED_SECTION.

    Rules:
      - tests with empty/missing expectedSkills -> UNMAPPED_SECTION
      - tests whose first expectedSkill maps to a team in the manifest -> that team
      - tests whose first expectedSkill is unknown to the manifest -> the team
        of the next known skill, falling back to UNMAPPED_SECTION
    """
    expected = test_entry.get("expectedSkills") or []
    if not expected:
        return UNMAPPED_SECTION
    for skill in expected:
        team = skill_to_team.get(skill)
        if team:
            return team
    return UNMAPPED_SECTION


def load_tests_json(path: Path) -> dict[str, dict]:
    """Load tests/tests.json into a test_name -> entry dict."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {entry["name"]: entry for entry in raw}


def classify_cause(outcome_str: str, tests_entry: dict | None) -> str:
    """Simple heuristic classification of likely cause from outcome pattern.

    Considers only the runs the test was actually present in (filters out '-'
    placeholders for runs where the test was absent / artifact missing).
    NOT authoritative -- eval team refines during weekly review.
    """
    if not outcome_str:
        return "no-data"
    present = outcome_str.replace("-", "")
    if not present:
        return "no-data (test absent from all runs)"
    y_count = present.count("Y")
    f_count = present.count("F")
    n_count = present.count("N")
    total = len(present)
    has_flaky_flag = bool(tests_entry and tests_entry.get("flaky", {}).get("githubIssue"))

    if y_count == total:
        return "stable"
    if y_count == 0 and f_count == total:
        return "known-flaky (flaky issue is referenced) -- check issue status"
    if y_count == 0 and n_count == total:
        if has_flaky_flag:
            return "consistently N (flaky flag references an issue but window is all unexpected fails -- check whether the flaky issue is resolved or whether a different bug surfaced)"
        return "consistently broken (no flaky flag -- needs triage / new issue)"
    if y_count > 0 and (f_count > 0 or n_count > 0):
        if has_flaky_flag:
            return "intermittent (flaky-flagged; partial passes this window)"
        return "intermittent / flake"
    if f_count > 0 and n_count > 0:
        return "mixed F+N -- multiple causes; review per-test output"
    return "unclear"


def build_outcome_string(test_name: str, per_run_results: list[dict]) -> str:
    """Build a string like 'YYNFY' (oldest -> newest) for one test across the runs.

    rawStatus is treated as the authoritative per-run character (Y/F/N). When
    rawStatus is missing (older artifacts or partial schema producers), fall
    back to deriving the character from isPass -- matching how
    build-dashboard.py treats the same field. This keeps outcome strings and
    classify_cause() stable across artifact format drift.
    """
    chars = []
    for run_results in per_run_results:
        info = run_results.get(test_name)
        if info is None:
            chars.append("-")  # test absent from this run
            continue
        raw = info.get("rawStatus")
        if raw in ("Y", "F", "N"):
            chars.append(raw)
        else:
            # Fallback: derive Y/N from isPass. F is a smoke-only "flaky-pass"
            # downgrade flag, never inferable from isPass alone.
            chars.append("Y" if info.get("isPass") else "N")
    return "".join(chars)


def trailing_y_count(outcome: str) -> int:
    """Count trailing 'Y' characters in an outcome string, ignoring '-'.

    Counts run from the right. '-' placeholders are skipped (they represent
    runs where the test was absent from the artifact -- a cancelled or
    startup-failed run that produced no schema data). 'F' or 'N' break the
    count. Used by the flag-removal candidate logic in render_report() to
    decide whether a flaky-flagged test has been passing long enough that
    the flag may be safely removed.
    """
    count = 0
    for ch in reversed(outcome):
        if ch == "-":
            continue
        if ch == "Y":
            count += 1
        else:
            break
    return count


def render_report(args, runs: list[dict], per_run_results: list[dict],
                   ownership: dict, tests_map: dict[str, dict]) -> str:
    """Compose the markdown report."""
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Aggregate per-test outcomes across the window
    all_test_names: set[str] = set()
    for run_results in per_run_results:
        all_test_names.update(run_results.keys())

    manifest = ownership["manifest"]
    skill_to_team = ownership["skill_to_team"]

    # Group tests by owning team (via expectedSkills). Test entries missing
    # from tests.json (defensive: smoke artifacts shouldn't include unknown
    # tests, but a stale tests.json after a delete could) fall through to
    # UNMAPPED_SECTION so they don't silently disappear.
    team_to_tests: dict[str, list[str]] = defaultdict(list)
    for test_name in sorted(all_test_names):
        entry = tests_map.get(test_name, {})
        team = resolve_test_team(entry, skill_to_team)
        team_to_tests[team].append(test_name)

    teams_block = manifest.get("teams") or {}

    # Begin markdown rendering
    lines = []
    lines.append(f"# Weekly Smoke Flake Report - {now}")
    lines.append("")
    lines.append(f"**Window:** {len(runs)} most-recent completed smoke runs on `main` of `{args.repo}`.")
    lines.append("")
    lines.append("**Runs included (oldest -> newest):**")
    lines.append("")
    lines.append("| Run | Date | Conclusion | Event |")
    lines.append("|---|---|---|---|")
    for r in runs:
        lines.append(f"| [{r['databaseId']}](https://github.com/{args.repo}/actions/runs/{r['databaseId']}) | {r['createdAt'][:10]} | {r['conclusion']} | {r['event']} |")
    lines.append("")
    lines.append("## How to read this")
    lines.append("")
    lines.append("- **Last-N outcomes** column reads oldest -> newest. `Y` = pass, `F` = known-flaky-fail (test has `flaky.githubIssue`), `N` = unexpected fail (no issue), `-` = test absent from that run.")
    lines.append("- **Likely cause** is a coarse first-pass hint. The eval team refines during review. Team owners are encouraged to push back if a finding sits in our infra (test prompt, fixture, harness) rather than their skill.")
    lines.append("- **Flag-removal candidates** are tests carrying a stale `flaky.githubIssue` reference that have passed consistently in this window -- ready for a small follow-up PR removing the flag once the underlying issue is verified closed.")
    lines.append("- **Owner routing** is computed from `tests/tests.json::expectedSkills[i]` -> `.github/skill-ownership.yml::skills[<skill>].owningTeam` -> `teams[<team>].contact`. Tests with no expectedSkills are grouped under 'Unmapped'.")
    lines.append("")

    # Flag-removal candidates (top of report -- most actionable)
    removal_candidates = []
    for test_name in sorted(all_test_names):
        entry = tests_map.get(test_name)
        if not entry or not entry.get("flaky"):
            continue
        outcome = build_outcome_string(test_name, per_run_results)
        trailing_y = trailing_y_count(outcome)
        if trailing_y >= args.flag_removal_min_passes:
            removal_candidates.append((test_name, outcome, entry["flaky"]["githubIssue"], trailing_y))

    lines.append("## Flag-removal candidates")
    lines.append("")
    if removal_candidates:
        lines.append(f"_Tests carrying a `flaky.githubIssue` reference that have passed {args.flag_removal_min_passes}+ consecutive runs in the window:_")
        lines.append("")
        lines.append("| Test | Outcomes | Trailing Y | Linked issue |")
        lines.append("|---|---|---|---|")
        for tn, oc, issue, ty in removal_candidates:
            lines.append(f"| `{tn}` | `{oc}` | {ty} | {issue} |")
    else:
        lines.append("_No flag-removal candidates this week._")
    lines.append("")

    # Per-team sections (sorted, with the unmapped bucket pinned at the bottom)
    lines.append("## Per-team status")
    lines.append("")
    sorted_teams = [t for t in sorted(team_to_tests.keys()) if t != UNMAPPED_SECTION]
    if UNMAPPED_SECTION in team_to_tests:
        sorted_teams.append(UNMAPPED_SECTION)

    for team in sorted_teams:
        test_names = team_to_tests[team]
        contact = get_team_contact(manifest, team) if team != UNMAPPED_SECTION else None
        team_meta = teams_block.get(team, {}) if team != UNMAPPED_SECTION else {}
        display_name = team_meta.get("displayName") or team
        section_header = display_name if team != UNMAPPED_SECTION else "Unmapped (no expectedSkills)"

        owner_line = ""
        if contact:
            github_handle = f"@{contact['github']}" if contact.get("github") else "(GitHub handle: lookup needed)"
            owner_line = f"Owner: **{contact['name']}** ({contact['email']}) {github_handle}"
        elif team == UNMAPPED_SECTION:
            owner_line = "Owner: **TBD** -- tests in this section have no `expectedSkills`. Add expectedSkills or route to a `platform` team test owner."

        lines.append(f"### {section_header} ({len(test_names)} tests)")
        lines.append("")
        if owner_line:
            lines.append(owner_line)
            lines.append("")
        lines.append("| Test | Outcomes | Likely cause | Issue |")
        lines.append("|---|---|---|---|")
        any_problem = False
        for test_name in sorted(test_names):
            outcome = build_outcome_string(test_name, per_run_results)
            entry = tests_map.get(test_name)
            cause = classify_cause(outcome, entry)
            issue_ref = ""
            if entry and entry.get("flaky", {}).get("githubIssue"):
                issue_url = entry["flaky"]["githubIssue"]
                issue_num = issue_url.rstrip("/").split("/")[-1]
                issue_ref = f"[#{issue_num}]({issue_url})"
            problematic = ("Y" not in outcome) or ("F" in outcome) or ("N" in outcome)
            if problematic:
                any_problem = True
            lines.append(f"| `{test_name}` | `{outcome}` | {cause} | {issue_ref} |")
        lines.append("")
        if any_problem and contact:
            github_handle = contact.get("github")
            draft_comment = render_draft_comment(display_name, test_names, per_run_results, tests_map, github_handle)
            draft_email = render_draft_email(display_name, test_names, per_run_results, tests_map, contact, args.repo)
            lines.append("#### Drafts for review (do NOT post until approved)")
            lines.append("")
            lines.append("<details><summary>Drafted GitHub issue comment</summary>")
            lines.append("")
            lines.append("```markdown")
            lines.append(draft_comment)
            lines.append("```")
            lines.append("</details>")
            lines.append("")
            lines.append("<details><summary>Drafted email body</summary>")
            lines.append("")
            lines.append("```")
            lines.append(draft_email)
            lines.append("```")
            lines.append("</details>")
            lines.append("")

    return "\n".join(lines)


def render_draft_comment(team_label: str, test_names: list[str], per_run_results: list[dict],
                        tests_map: dict[str, dict], github_handle: str | None) -> str:
    handle_str = f"@{github_handle}" if github_handle else f"@{team_label}-owner"
    lines = [f"Weekly smoke health check for the **{team_label}** team (window: last {len(per_run_results)} runs on main).",
             "",
             "Current state of tests in your area:",
             "",
             "| Test | Outcomes (oldest -> newest) | Status |",
             "|---|---|---|"]
    for tn in sorted(test_names):
        outcome = build_outcome_string(tn, per_run_results)
        entry = tests_map.get(tn)
        status = classify_cause(outcome, entry)
        lines.append(f"| `{tn}` | `{outcome}` | {status} |")
    lines.append("")
    lines.append(f"{handle_str} -- could you take a look at the tests showing F or N? If the failure looks like a test-prompt / fixture / harness issue (i.e., on our side), please push back; we'll fix it in the infra. If it's a skill behaviour issue, the test output is linked from the dashboard at https://fuzzy-carnival-p3m764k.pages.github.io/.")
    lines.append("")
    lines.append("This comment will be refreshed next week with updated outcomes.")
    return "\n".join(lines)


def render_draft_email(team_label: str, test_names: list[str], per_run_results: list[dict],
                      tests_map: dict[str, dict], contact: dict, repo: str) -> str:
    return f"""To: {contact['email']}
Subject: skills-for-fabric weekly smoke health -- {team_label}

Hi {contact['name'].split()[0]},

This is the weekly smoke health snapshot for the {team_label} team in skills-for-fabric.

Tests currently flagged in your area (last {len(per_run_results)} runs on main):

""" + "\n".join(
    f"  - {tn}: {build_outcome_string(tn, per_run_results)}"
    for tn in sorted(test_names)
) + f"""

Detailed report (with drafted GitHub-comment text for the team tracker issue):
https://github.com/{repo}/blob/main/reports/weekly-<DATE>.md  (link to be filled in by sender)

If anything in the "Likely cause" column looks like our infra rather than your skill, push back -- we'll fix it.

Thanks,
Matan (skills-for-fabric eval team)
"""


def main() -> int:
    args = parse_args(sys.argv[1:])
    # If --repo-root was not passed, fall back to the script's own repo root
    # (computed from __file__). This makes the tool work from any cwd. Doing
    # the fallback HERE rather than in parse_args() keeps the default visible
    # to test helpers that import parse_args() with an empty argv.
    repo_root = (args.repo_root or _REPO_ROOT_GUESS).resolve()

    manifest_path = repo_root / ".github" / "skill-ownership.yml"
    tests_path = repo_root / "tests" / "tests.json"
    if not manifest_path.exists():
        print(f"ERROR: ownership manifest not found at {manifest_path}", file=sys.stderr)
        return 2
    if not tests_path.exists():
        print(f"ERROR: tests.json not found at {tests_path}", file=sys.stderr)
        return 2

    ownership = load_ownership(manifest_path)
    tests_map = load_tests_json(tests_path)

    print(f"Discovering last {args.runs} smoke runs on {args.repo} (branch=main)...", file=sys.stderr)
    runs = discover_runs(args.runs, args.repo)
    if not runs:
        print("ERROR: no completed smoke runs found on main", file=sys.stderr)
        return 3
    print(f"  Found {len(runs)} runs: {[r['databaseId'] for r in runs]}", file=sys.stderr)

    tmp_root = Path(tempfile.mkdtemp(prefix="weekly-flake-"))
    print(f"Downloading schema artifacts to {tmp_root}...", file=sys.stderr)
    per_run_results: list[dict] = []
    for r in runs:
        run_dir = download_schema_artifact(r["databaseId"], tmp_root, args.repo)
        if run_dir is None:
            print(f"  Run {r['databaseId']}: no schema artifact (skipping)", file=sys.stderr)
            per_run_results.append({})
            continue
        results = parse_test_results_for_run(run_dir)
        per_run_results.append(results)
        print(f"  Run {r['databaseId']}: {len(results)} test results", file=sys.stderr)

    print("Rendering report...", file=sys.stderr)
    report = render_report(args, runs, per_run_results, ownership, tests_map)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Wrote {args.output}", file=sys.stderr)

    if not args.keep_artifacts:
        shutil.rmtree(tmp_root, ignore_errors=True)
    else:
        print(f"Kept artifacts at {tmp_root}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
