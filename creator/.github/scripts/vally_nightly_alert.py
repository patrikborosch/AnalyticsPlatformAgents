#!/usr/bin/env python3
"""Open or update the scheduled vally failure issue."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# The [model-name] bracket between eval name and `score:` / `grader(s) failed`
# is OPTIONAL: vally 0.5.0 emits it for some invocations and omits it for
# others on identical wrapper invocations. The earlier regex required it and
# silently parsed zero scores when vally omitted it -- producing incomplete
# issue bodies on nightly alerts.
#
# The eval-name capture deliberately does NOT require a `-eval` suffix:
# vally's eval-name is whatever the eval.yaml's `name:` field says, and
# nothing in the framework guarantees that suffix. A future eval ship that
# drops it would silently fall off this regex and yield an empty per-eval
# table -- the same silent-zero-scores failure mode the bracket fix was
# written to prevent. The `(?m)^` anchor + the bullet/icon prefix do
# the disambiguation work the suffix used to.
SCORE_RE = re.compile(r"(?m)^\s*[\u2713\u2714\u2717\u2718]?\s*([\w-]+)\s+(?:\[[^\]]*\]\s+)?score:\s*([\d.]+)%\s*\(threshold:\s*([\d.]+)%\)")
CRASH_RE = re.compile(r"(?m)^\s*[\u2713\u2714\u2717\u2718]?\s*([\w-]+)\s+(?:\[[^\]]*\]\s+)?grader\(s\) failed")
WALL_RE = re.compile(r"Wall time\s+([\d.]+)s")
SHARD_RE = re.compile(r"shard(\d+)", re.IGNORECASE)

# GitHub REST API status codes we treat as transient (worth retrying).
# 5xx: server-side blip. 429: rate-limit (Retry-After header would be ideal
# but a simple bounded retry is enough for our scale).
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 2.0


class GitHubApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"GitHub API request failed with status {status}: {body[:500]}")
        self.status = status
        self.body = body


def github_request(method: str, path_or_url: str, token: str, payload: dict[str, Any] | None = None) -> Any:
    """GitHub REST call with bounded retry on transient failures.

    Retries up to _RETRY_MAX_ATTEMPTS times with exponential backoff on
    5xx / 429 / network errors. Other 4xx (auth, validation, not-found)
    raise GitHubApiError immediately so the caller can branch on .status
    (the existing 422-already-exists branch in ensure_label still works).
    """
    return _github_request_with_response(method, path_or_url, token, payload)[0]


def _github_request_with_response(
    method: str, path_or_url: str, token: str, payload: dict[str, Any] | None = None
) -> tuple[Any, dict[str, str]]:
    """Same as github_request but also returns response headers (for Link pagination)."""
    import time

    url = path_or_url if path_or_url.startswith("https://") else f"https://api.github.com{path_or_url}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "skills-for-fabric-vally-nightly-alert",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"

    last_err: Exception | None = None
    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8", errors="replace")
                response_headers = {k.lower(): v for k, v in response.getheaders()}
                return (json.loads(raw) if raw else {}), response_headers
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if exc.code not in _RETRYABLE_STATUSES or attempt == _RETRY_MAX_ATTEMPTS:
                raise GitHubApiError(exc.code, raw) from exc
            last_err = GitHubApiError(exc.code, raw)
            print(f"[github_request] attempt {attempt}/{_RETRY_MAX_ATTEMPTS} got HTTP {exc.code} on {method} {url}; retrying")
        except urllib.error.URLError as exc:
            # Network-level error (DNS, connection refused, timeout). Treat as transient.
            # On exhaustion, wrap in GitHubApiError(status=0) so callers that
            # branch on `except GitHubApiError` (notably main()'s
            # step-summary fallback) receive the same exception type for
            # every retry-exhaustion path, network or HTTP.
            if attempt == _RETRY_MAX_ATTEMPTS:
                raise GitHubApiError(0, f"network error after {_RETRY_MAX_ATTEMPTS} attempts on {method} {url}: {exc}") from exc
            last_err = exc
            print(f"[github_request] attempt {attempt}/{_RETRY_MAX_ATTEMPTS} got network error on {method} {url}: {exc}; retrying")
        time.sleep(_RETRY_BASE_DELAY_S * (2 ** (attempt - 1)))

    # Defensive: loop should always return or raise above. If we somehow exit
    # the loop without returning, surface the last error so the failure isn't
    # silent.
    raise last_err if last_err else RuntimeError("github_request exhausted retries without an outcome")


def increment(stats: dict[str, dict[str, int]], eval_name: str, passed: bool) -> None:
    row = stats.setdefault(eval_name, {"total": 0, "passed": 0, "failed": 0})
    row["total"] += 1
    if passed:
        row["passed"] += 1
    else:
        row["failed"] += 1


def eval_name_for_results(path: pathlib.Path) -> str:
    parent = path.parent.name
    if re.match(r"^\d{4}-\d{2}-\d{2}", parent) and path.parent.parent.name not in ("", ".vally-results"):
        return path.parent.parent.name
    return parent or "unknown"


def merge_stats(target: dict[str, dict[str, int]], fragment: dict[str, dict[str, int]]) -> None:
    for name, row in fragment.items():
        dest = target.setdefault(name, {"total": 0, "passed": 0, "failed": 0})
        dest["total"] += row["total"]
        dest["passed"] += row["passed"]
        dest["failed"] += row["failed"]


def parse_shard_jsonl(shard_dir: pathlib.Path) -> tuple[dict[str, dict[str, int]], int]:
    """Parse every results.jsonl under one shard directory."""
    fragment: dict[str, dict[str, int]] = {}
    count = 0
    for result_file in sorted(shard_dir.rglob("results.jsonl")):
        count += 1
        eval_name = eval_name_for_results(result_file)
        for line in result_file.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip().startswith("{"):
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            grade = entry.get("gradeResult") or {}
            if "passed" not in grade:
                continue
            increment(fragment, eval_name, bool(grade.get("passed")))
    return fragment, count


def parse_shard_log_scores(text: str) -> dict[str, dict[str, int]]:
    """Recover per-eval pass/fail from a vally-run.log when jsonl is absent.

    If neither SCORE_RE nor CRASH_RE matched anything, emit a loud warning
    so a future vally output-format change surfaces as a build log signal
    (instead of silently producing an empty per-eval table in the alert).
    """
    fragment: dict[str, dict[str, int]] = {}
    for score_match in SCORE_RE.finditer(text):
        score = float(score_match.group(2))
        threshold = float(score_match.group(3))
        increment(fragment, score_match.group(1), score >= threshold)
    for crash_match in CRASH_RE.finditer(text):
        increment(fragment, crash_match.group(1), False)
    if not fragment and text.strip():
        # Non-empty log but neither regex matched: most likely a vally output
        # format change. Print to step log so the build flags it.
        print("[parse_shard_log_scores] no eval names matched in non-empty log; vally output format may have changed.")
    return fragment


def parse_artifacts(root: pathlib.Path) -> tuple[dict[str, dict[str, int]], dict[str, float | None], int]:
    stats: dict[str, dict[str, int]] = {}
    # A shard whose log was present but had no parseable Wall time lines is
    # recorded as None (not 0.0). Keeping the shard key in either case is
    # intentional: an operator needs to see "shardN ran but produced no
    # wall-time data" as a distinct row from "shardN didn't run at all"
    # (the latter is signalled by the absence of the key entirely).
    # Rendering a missing-data shard as `0.0` reads as "shard hung at
    # zero seconds" -- misleading at 3am.
    wall_times: dict[str, float | None] = {}
    jsonl_count = 0
    log_count = 0
    if root.exists():
        shard_dirs = [path for path in sorted(root.iterdir()) if path.is_dir()]
        if not shard_dirs:
            # No per-shard subdirectories (flat artifact layout); treat the whole
            # root as a single shard so top-level files still parse. This doubles
            # as the final safety net when artifact download collapsed the tree.
            shard_dirs = [root]

        for shard_dir in shard_dirs:
            shard_fragment, shard_jsonl_count = parse_shard_jsonl(shard_dir)
            jsonl_count += shard_jsonl_count

            # Collect this shard's logs once: wall-times are always taken from
            # them, but per-eval recovery only runs when jsonl is missing/empty.
            shard_logs: list[str] = []
            for log_file in sorted(shard_dir.rglob("vally-run.log")):
                log_count += 1
                text = ANSI_RE.sub("", log_file.read_text(encoding="utf-8", errors="replace"))
                shard_logs.append(text)
                shard_match = SHARD_RE.search(str(log_file))
                shard_name = f"shard{shard_match.group(1)}" if shard_match else log_file.parent.name
                # Accumulate matches into a local; only commit a float when the
                # inner loop matched at least one Wall time line. Otherwise
                # record None so rendering shows "-" (not "0.0") for the shard.
                shard_walltime = 0.0
                shard_matched = False
                for wall_match in WALL_RE.finditer(text):
                    shard_matched = True
                    shard_walltime += float(wall_match.group(1))
                if shard_name in wall_times and wall_times[shard_name] is not None:
                    # Multiple log files in the same shard dir (rglob can pick
                    # up nested logs); aggregate into the existing float total
                    # rather than overwriting.
                    if shard_matched:
                        wall_times[shard_name] = (wall_times[shard_name] or 0.0) + shard_walltime
                else:
                    wall_times[shard_name] = shard_walltime if shard_matched else None

            if shard_fragment:
                merge_stats(stats, shard_fragment)
                print(f"[parse_artifacts] {shard_dir.name}: source=results.jsonl")
                continue

            # Per-shard fallback: this shard produced no parseable results.jsonl
            # (EBUSY race, crash before finalisation, ...). Recover from its own
            # log so its failures are not silently dropped from the issue body.
            log_fragment: dict[str, dict[str, int]] = {}
            for text in shard_logs:
                merge_stats(log_fragment, parse_shard_log_scores(text))
            if log_fragment:
                merge_stats(stats, log_fragment)
                print(f"[parse_artifacts] {shard_dir.name}: source=vally-run.log (fallback)")
            else:
                # Neither source produced data; surface it for debugging instead
                # of silently omitting the shard.
                print(f"[parse_artifacts] {shard_dir.name}: source=no parseable data")

    # 0 or 1 -- consumers only use this as a "did we parse anything?" presence
    # signal, never as a count. Returning a true count was misleading.
    artifact_signals = 1 if (jsonl_count > 0 or log_count > 0) else 0
    return stats, wall_times, artifact_signals


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def build_issue_body(artifacts_dir: pathlib.Path, label: str) -> str:
    stats, wall_times, artifact_signals = parse_artifacts(artifacts_dir)
    repo = os.environ["GITHUB_REPOSITORY"]
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_id = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    sha = os.environ["GITHUB_SHA"]
    run_url = f"{server}/{repo}/actions/runs/{run_id}"
    total = sum(row["total"] for row in stats.values())
    passed = sum(row["passed"] for row in stats.values())
    failed = sum(row["failed"] for row in stats.values())

    lines = [
        "## Scheduled vally smoke failure",
        "",
        f"- Run: {run_url}",
        f"- Attempt: {attempt}",
        f"- Commit: `{sha}`",
        f"- Label: `{label}`",
        f"- Artifact signals parsed: {artifact_signals}",
        f"- Job results: setup={os.environ.get('SETUP_RESULT', 'unknown')}, detect={os.environ.get('DETECT_RESULT', 'unknown')}, shard={os.environ.get('SHARD_RESULT', 'unknown')}, summarise={os.environ.get('SUMMARISE_RESULT', 'unknown')}",
        "",
        "### Per-eval pass/fail",
        "",
    ]
    if stats:
        rows = [
            [name, str(row["total"]), str(row["passed"]), str(row["failed"])]
            for name, row in sorted(stats.items())
        ]
        rows.append(["TOTAL", str(total), str(passed), str(failed)])
        lines.append(markdown_table(["Eval", "Total", "Passed", "Failed"], rows))
    else:
        lines.append("No per-eval results were available. Check setup/auth logs and shard artifacts.")

    lines.extend(["", "### Per-shard wall-times", ""])
    if wall_times:
        # "-" for shards that produced a log but no parseable Wall time data
        # so the operator sees "shard ran but had no measurements" as distinct
        # from "shard wall time was 0 seconds".
        present = [v for v in wall_times.values() if v is not None]
        rows = [
            [name, f"{seconds:.1f}" if seconds is not None else "-"]
            for name, seconds in sorted(wall_times.items())
        ]
        if present:
            rows.append([
                "min / max / avg",
                f"{min(present):.1f} / {max(present):.1f} / {sum(present) / len(present):.1f}",
            ])
        lines.append(markdown_table(["Shard", "Wall time (s, sum of stim wall times)"], rows))
        missing = [name for name, seconds in wall_times.items() if seconds is None]
        if missing:
            lines.extend([
                "",
                f"_Note: {len(missing)} shard(s) produced a log but no parseable `Wall time` lines: {', '.join(sorted(missing))}._",
            ])
    else:
        lines.append("No shard wall-time lines were available.")

    lines.extend([
        "",
        "This alert is intentionally GitHub-issue only; webhook routing and recipient policy are separate decisions.",
    ])
    return "\n".join(lines)


def ensure_label(repo: str, token: str, label: str) -> None:
    payload = {
        "name": label,
        "color": "B60205",
        "description": "Scheduled vally smoke failure alert",
    }
    try:
        github_request("POST", f"/repos/{repo}/labels", token, payload)
    except GitHubApiError as exc:
        if exc.status != 422:
            raise


def list_open_labeled_issues(repo: str, token: str, label: str) -> list[dict[str, Any]]:
    """Return every open issue with the given label.

    Follows the Link: rel="next" header so dedup still finds older matches
    when more than `per_page` issues accumulate. Same pagination shape used
    by cleanup_stale_fabric_workspaces.list_workspaces.
    """
    issues: list[dict[str, Any]] = []
    query = urllib.parse.urlencode({"state": "open", "labels": label, "per_page": "100"})
    url = f"/repos/{repo}/issues?{query}"
    # Safety cap so a runaway pagination cannot loop forever (10k issues).
    for _ in range(100):
        page, headers = _github_request_with_response("GET", url, token)
        if isinstance(page, list):
            issues.extend(issue for issue in page if "pull_request" not in issue)
        next_url = _parse_link_next(headers.get("link") or headers.get("Link") or "")
        if not next_url:
            break
        url = next_url
    return issues


def _parse_link_next(link_header: str) -> str | None:
    """Extract the `rel=next` URL from an RFC 5988 Link header, or None."""
    if not link_header:
        return None
    for chunk in link_header.split(","):
        if 'rel="next"' not in chunk:
            continue
        start = chunk.find("<")
        end = chunk.find(">", start)
        if start != -1 and end != -1:
            return chunk[start + 1 : end].strip()
    return None


def make_title_prefix(title_date: str) -> str:
    """Single source of truth for the issue-title prefix used by dedup.

    Both create_or_update_issue (when matching existing issues) and main
    (when minting a new title) build the same string. Drift between them
    would silently break dedup (every nightly creates a new issue).
    """
    return f"[vally-nightly] Failure on {title_date} "


def make_title(title_date: str, short_sha: str) -> str:
    """Full issue title for a new issue. Prefix matches make_title_prefix."""
    return f"{make_title_prefix(title_date)}(commit {short_sha})"


def create_or_update_issue(repo: str, token: str, label: str, title_date: str, title: str, body: str) -> str:
    ensure_label(repo, token, label)
    prefix = make_title_prefix(title_date)
    existing = [issue for issue in list_open_labeled_issues(repo, token, label) if str(issue.get("title", "")).startswith(prefix)]
    if existing:
        issue = sorted(existing, key=lambda item: int(item.get("number", 0)))[0]
        comment_body = f"Additional scheduled failure for {title_date}:\n\n{body}"
        github_request("POST", f"/repos/{repo}/issues/{issue['number']}/comments", token, {"body": comment_body})
        return str(issue.get("html_url"))
    issue = github_request("POST", f"/repos/{repo}/issues", token, {"title": title, "body": body, "labels": [label]})
    return str(issue.get("html_url"))


def append_step_summary(message: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(message + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--label", default="nightly-vally-fail")
    args = parser.parse_args(argv)

    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")

    now = dt.datetime.now(dt.timezone.utc)
    title_date = now.strftime("%Y-%m-%d")
    sha = os.environ["GITHUB_SHA"]
    short_sha = sha[:7]
    title = make_title(title_date, short_sha)
    body = build_issue_body(pathlib.Path(args.artifacts_dir), args.label)
    try:
        issue_url = create_or_update_issue(repo, token, args.label, title_date, title, body)
    except GitHubApiError as exc:
        # The alerter's whole purpose is to surface failures. If the GitHub
        # Issues API is itself unavailable / misconfigured / rate-limited,
        # dump the would-be issue body into the step summary so an on-call
        # checking the workflow page still gets the per-eval breakdown,
        # then re-raise so the step turns red and surfaces the alerter
        # failure in the workflow UI.
        fallback_lines = [
            f"## Alerter could not file an issue (GitHub API error {exc.status})",
            "",
            "The scheduled vally failure couldn't be turned into a GitHub issue. ",
            "Body that would have been posted:",
            "",
            body,
            "",
            f"GitHub API response (first 500 chars): `{exc.body[:500]}`",
        ]
        append_step_summary("\n".join(fallback_lines))
        raise
    print(f"Nightly failure issue: {issue_url}")
    append_step_summary(f"Nightly failure issue: {issue_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
