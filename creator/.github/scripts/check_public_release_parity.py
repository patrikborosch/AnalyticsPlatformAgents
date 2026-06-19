#!/usr/bin/env python3
"""Verify the public repo's shipped version has a matching published GitHub Release.

Detects the recurring "Phase 2 skipped" failure mode: ``PublishToPublic.ps1``
Phase 1 (the content PR) merges to ``microsoft/skills-for-fabric``, but Phase 2
(``-PublishRelease`` -- which creates the tag + GitHub Release) is never run, so
the public repo ships content for a version with no corresponding release/tag.
This happened for v0.3.2 and v0.3.3.

Run on a schedule from the internal repo. The script reads the PUBLIC repo's
``package.json`` version (on its default branch) and its published releases; if
the shipped version has no matching ``v<version>`` release, it files (or reuses)
a label-deduped tracking issue on the CURRENT repo and exits non-zero -- unless
``--no-fail-on-gap`` is set (the weekly job uses it to stay green while still
filing the issue). When parity is healthy it auto-closes any open tracking issue
and exits zero.

Two call sites share this one detector (single source of truth):
  - Weekly workflow (the safety net for the LATEST release) runs it with
    ``--no-fail-on-gap``: it opens/auto-closes the tracking issue but stays green.
  - ``ReleaseScripts/PublishToPublic.ps1`` Phase 1 runs it with ``--no-issue`` as a
    synchronous gate: detect-only, and the non-zero exit (``2`` = gap) blocks the
    next publish until the prior release is published. The exit codes (0 ok, 2 gap,
    1 script/API error) are a contract the PS1 gate depends on -- see EXIT_* below.

Reads of the public repo work with the workflow's default ``GITHUB_TOKEN`` (public
data is readable by any valid token) or unauthenticated. Filing/closing the
tracking issue needs ``issues: write`` on the current repo (the default token has
this). No public push and no extra secrets are required -- this is a detector, not
an auto-healer.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_ROOT = "https://api.github.com"

# REST status codes we treat as transient (worth retrying). Mirrors the policy in
# .github/scripts/vally_nightly_alert.py so behaviour is consistent across scripts.
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 2.0

LABEL = "public-release-parity"
TITLE_PREFIX = "[public-release-parity] Missing public release"

# Exit codes: 0 = parity OK, 2 = parity gap detected, 1 = script/API error.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_GAP = 2


class GitHubApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"GitHub API request failed with status {status}: {body[:500]}")
        self.status = status
        self.body = body


def github_request(method: str, path_or_url: str, token: str, payload: dict[str, Any] | None = None) -> Any:
    """GitHub REST call with bounded retry on transient (5xx / 429 / network) failures.

    Non-retryable 4xx (auth, validation, not-found) raise GitHubApiError immediately
    so callers can branch on ``.status`` (e.g. the 422 already-exists path in
    ``ensure_label``).
    """
    url = path_or_url if path_or_url.startswith("https://") else f"{API_ROOT}{path_or_url}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "skills-for-fabric-public-release-parity",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"

    last_err: Exception | None = None
    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if exc.code not in _RETRYABLE_STATUSES or attempt == _RETRY_MAX_ATTEMPTS:
                raise GitHubApiError(exc.code, raw) from exc
            last_err = GitHubApiError(exc.code, raw)
            print(f"[github_request] attempt {attempt}/{_RETRY_MAX_ATTEMPTS} got HTTP {exc.code} on {method} {url}; retrying")
        except urllib.error.URLError as exc:
            if attempt == _RETRY_MAX_ATTEMPTS:
                raise GitHubApiError(0, f"network error after {_RETRY_MAX_ATTEMPTS} attempts on {method} {url}: {exc}") from exc
            last_err = exc
            print(f"[github_request] attempt {attempt}/{_RETRY_MAX_ATTEMPTS} got network error on {method} {url}: {exc}; retrying")
        time.sleep(_RETRY_BASE_DELAY_S * (2 ** (attempt - 1)))

    raise last_err if last_err else RuntimeError("github_request exhausted retries without an outcome")


# ---------------------------------------------------------------------------
# Pure logic (unit-tested -- no network)
# ---------------------------------------------------------------------------

def normalize_tag(version: str) -> str:
    """Return the canonical ``vX.Y.Z`` tag for a version string ('0.3.3' -> 'v0.3.3')."""
    version = (version or "").strip()
    return version if version.startswith("v") else f"v{version}"


def parse_package_version(package_json_text: str) -> str:
    """Extract the ``version`` field from package.json text."""
    data = json.loads(package_json_text)
    if not isinstance(data, dict):
        raise ValueError("package.json did not decode to a JSON object")
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("package.json has no non-empty string 'version' field")
    return version.strip()


def released_tag_names(releases: Any) -> set[str]:
    """Set of ``tag_name`` values from a ``/releases`` payload, excluding drafts.

    Drafts are excluded because end users never see them; a draft release is not
    parity. (For the public repo our token has no push, so the API would already
    omit drafts -- the guard is belt-and-suspenders for authenticated reruns.)
    """
    names: set[str] = set()
    if not isinstance(releases, list):
        return names
    for rel in releases:
        if not isinstance(rel, dict) or rel.get("draft"):
            continue
        tag = rel.get("tag_name")
        if tag:
            names.add(str(tag))
    return names


def find_missing_release(content_version: str, released_tags: set[str]) -> str | None:
    """Return the expected tag if the shipped version has no published release, else None."""
    expected = normalize_tag(content_version)
    return None if expected in released_tags else expected


def build_issue_body(public_repo: str, ref: str, content_version: str, missing_tag: str) -> str:
    """Actionable tracking-issue body. ASCII-only; no personal account names."""
    version_no_v = missing_tag[1:] if missing_tag.startswith("v") else missing_tag
    return (
        f"The public repo `{public_repo}` has shipped content for **{content_version}** "
        f"(its `package.json` on `{ref}`), but there is no published GitHub Release for "
        f"**{missing_tag}**.\n\n"
        "This is the \"Phase 2 skipped\" failure mode: the content PR "
        "(`PublishToPublic.ps1` Phase 1) merged, but the tag + GitHub Release step "
        "(Phase 2, `-PublishRelease`) was never run.\n\n"
        f"### How to fix (needs an account with push access to `{public_repo}`)\n\n"
        f"- If `{missing_tag}` corresponds to the current `{ref}` HEAD release merge:\n"
        f"  ```\n  .\\ReleaseScripts\\PublishToPublic.ps1 -PublishRelease -Version {version_no_v}\n  ```\n"
        f"- If `{ref}` has advanced past this version, create the release on its historical "
        f"merge commit and mark it not-latest:\n"
        f"  ```\n  gh release create {missing_tag} --repo {public_repo} --target <merge-sha> "
        f"--notes-file <notes> --latest=false\n  ```\n"
        "  (see the Phase 2 precondition guidance in `ReleaseScripts/PublishToPublic.ps1`).\n\n"
        "This issue auto-closes on the next scheduled run once a matching release exists.\n\n"
        "_Filed by `.github/scripts/check_public_release_parity.py` (Public Release Parity workflow)._"
    )


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def get_public_content_version(public_repo: str, ref: str, token: str) -> str:
    """Read package.json on the public repo's ``ref`` and return its version."""
    path = f"/repos/{public_repo}/contents/package.json?ref={urllib.parse.quote(ref)}"
    resp = github_request("GET", path, token)
    content_b64 = resp.get("content", "") if isinstance(resp, dict) else ""
    if not content_b64:
        raise ValueError(f"No package.json content returned for {public_repo}@{ref}")
    text = base64.b64decode(content_b64).decode("utf-8", errors="replace")
    return parse_package_version(text)


def get_public_release_tags(public_repo: str, token: str) -> set[str]:
    # Releases come back newest-first, so the current package.json version's release
    # (the only one this guard checks) is always on page 1 -- no pagination needed
    # even once the repo accrues more than 100 historical releases.
    releases = github_request("GET", f"/repos/{public_repo}/releases?per_page=100", token)
    return released_tag_names(releases)


def ensure_label(repo: str, token: str) -> None:
    payload = {
        "name": LABEL,
        "color": "B60205",
        "description": "Public repo shipped a version with no matching GitHub Release",
    }
    try:
        github_request("POST", f"/repos/{repo}/labels", token, payload)
    except GitHubApiError as exc:
        if exc.status != 422:  # 422 == label already exists
            raise


def list_open_labeled_issues(repo: str, token: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"state": "open", "labels": LABEL, "per_page": "100"})
    issues = github_request("GET", f"/repos/{repo}/issues?{query}", token)
    if not isinstance(issues, list):
        return []
    return [issue for issue in issues if isinstance(issue, dict) and "pull_request" not in issue]


def open_tracking_issue(repo: str, token: str, missing_tag: str, body: str) -> str:
    """Create the tracking issue, or reuse the existing one for this tag (no spam)."""
    ensure_label(repo, token)
    title = f"{TITLE_PREFIX} {missing_tag}"
    for issue in list_open_labeled_issues(repo, token):
        if str(issue.get("title", "")) == title:
            return str(issue.get("html_url"))
    issue = github_request(
        "POST", f"/repos/{repo}/issues", token,
        {"title": title, "body": body, "labels": [LABEL]},
    )
    return str(issue.get("html_url"))


def reconcile_tracking_issues(repo: str, token: str, released_tags: set[str]) -> list[int]:
    """Close every open parity issue whose version now has a published release.

    Called on EVERY managed run (gap or not), so a tracking issue filed for an
    older version that has since been released is closed even while a newer
    version still has its own open gap issue. Issues whose tag is still missing
    (or whose title does not parse to a tag) are left open. Returns the numbers
    of the issues that were closed.
    """
    closed: list[int] = []
    for issue in list_open_labeled_issues(repo, token):
        title = str(issue.get("title", ""))
        if not title.startswith(TITLE_PREFIX):
            continue
        tag = title[len(TITLE_PREFIX):].strip()
        if not tag or tag not in released_tags:
            # Unparseable title, or this version is still unreleased -- leave open.
            continue
        number = issue.get("number")
        if number is None:
            continue
        github_request(
            "POST", f"/repos/{repo}/issues/{number}/comments", token,
            {"body": "Public release parity restored -- the shipped version now has a matching GitHub Release. Auto-closing."},
        )
        github_request("PATCH", f"/repos/{repo}/issues/{number}", token, {"state": "closed"})
        closed.append(int(number))
    return closed


def append_step_summary(message: str) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(message + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-repo", default="microsoft/skills-for-fabric",
                        help="owner/name of the public repo to check (default: microsoft/skills-for-fabric)")
    parser.add_argument("--public-ref", default="main",
                        help="branch/ref whose package.json is the shipped version (default: main)")
    parser.add_argument("--no-issue", action="store_true",
                        help="skip filing/closing the tracking issue (local/dry runs)")
    parser.add_argument("--no-fail-on-gap", action="store_true",
                        help="exit 0 even when a parity gap is found (issue is still filed)")
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    manage_issue = not args.no_issue and bool(token) and bool(repo)
    if not args.no_issue and not manage_issue:
        print("[parity] GITHUB_TOKEN/GITHUB_REPOSITORY not set -- running detection only (no issue management).")

    try:
        content_version = get_public_content_version(args.public_repo, args.public_ref, token)
        released = get_public_release_tags(args.public_repo, token)
    except (GitHubApiError, ValueError) as exc:
        print(f"[parity] ERROR: could not evaluate parity for {args.public_repo}@{args.public_ref}: {exc}")
        append_step_summary(f"## Public release parity check errored\n\n{exc}")
        return EXIT_ERROR

    missing = find_missing_release(content_version, released)
    if missing is None:
        print(f"[parity] OK: {args.public_repo}@{args.public_ref} ships {content_version} and "
              f"{normalize_tag(content_version)} has a published release.")
        append_step_summary(
            f"## Public release parity: OK\n\n`{args.public_repo}` ships **{content_version}** "
            f"and **{normalize_tag(content_version)}** has a published release."
        )
        if manage_issue:
            closed = reconcile_tracking_issues(repo, token, released)
            if closed:
                print(f"[parity] closed restored tracking issue(s): {closed}")
        return EXIT_OK

    print(f"[parity] GAP: {args.public_repo} ships {content_version} but {missing} has no published release.")
    body = build_issue_body(args.public_repo, args.public_ref, content_version, missing)
    append_step_summary(
        f"## Public release parity: GAP\n\n`{args.public_repo}` ships **{content_version}** "
        f"but **{missing}** has no published GitHub Release (Phase 2 likely skipped).\n\n{body}"
    )
    if manage_issue:
        # Close any now-released older version's issue, then open/reuse this one.
        closed = reconcile_tracking_issues(repo, token, released)
        if closed:
            print(f"[parity] closed restored tracking issue(s): {closed}")
        url = open_tracking_issue(repo, token, missing, body)
        print(f"[parity] tracking issue: {url}")

    return EXIT_OK if args.no_fail_on_gap else EXIT_GAP


if __name__ == "__main__":
    sys.exit(main())
