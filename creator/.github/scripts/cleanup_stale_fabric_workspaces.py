#!/usr/bin/env python3
"""Delete stale Fabric smoke-test workspaces by safe name prefix."""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterator

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
DEFAULT_PREFIX = "skills-for-fabric-test-"
DEFAULT_CUTOFF_HOURS = 6.0
# Minimum cutoff guards against a fat-fingered `--cutoff-hours 0.1` from
# workflow_dispatch widening the deletion window to recently-provisioned
# workspaces. The prefix filter is broadly safe, but a 6-minute-old
# workspace from a concurrent smoke run on another branch matches the
# timestamp gate. 1 hour is the smallest value that still gives any
# in-flight smoke run a comfortable safety margin.
MIN_CUTOFF_HOURS = 1.0


class FabricApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"Fabric API request failed with status {status}: {body[:500]}")
        self.status = status
        self.body = body


# Inline retry policy for transient Fabric API blips. Matches the policy in
# vally_nightly_alert.py::_github_request_with_response: same retryable status
# set, same attempt count, same exponential backoff. Both files keep their own
# retry block (rather than importing a shared module) because they target
# different APIs with different error shapes; sharing would mean a generic
# wrapper that drops the per-API status-classification logic.
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 2.0


def _fabric_url(path_or_url: str) -> str:
    if path_or_url.startswith("https://"):
        return path_or_url
    if path_or_url.startswith("/v1/"):
        return f"https://api.fabric.microsoft.com{path_or_url}"
    return f"{FABRIC_API_BASE}{path_or_url}"


def fabric_request(method: str, path_or_url: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Issue a Fabric REST call with bounded retry on transient failures.

    Retries up to _RETRY_MAX_ATTEMPTS on 5xx / 429 / network errors. Other
    4xx (auth, not-found) raise immediately so the caller can branch on
    .status (notably the 404-as-already-gone branch in main()). A persistent
    URLError on exhaustion is wrapped in FabricApiError(status=0, ...) so
    every retry-exhaustion path raises the same exception type.
    """
    import time

    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"

    last_err: Exception | None = None
    for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
        request = urllib.request.Request(_fabric_url(path_or_url), data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8", errors="replace")
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if exc.code not in _RETRYABLE_STATUSES or attempt == _RETRY_MAX_ATTEMPTS:
                raise FabricApiError(exc.code, raw) from exc
            last_err = FabricApiError(exc.code, raw)
            print(f"[fabric_request] attempt {attempt}/{_RETRY_MAX_ATTEMPTS} got HTTP {exc.code} on {method} {path_or_url}; retrying")
        except urllib.error.URLError as exc:
            if attempt == _RETRY_MAX_ATTEMPTS:
                raise FabricApiError(0, f"network error after {_RETRY_MAX_ATTEMPTS} attempts on {method} {path_or_url}: {exc}") from exc
            last_err = exc
            print(f"[fabric_request] attempt {attempt}/{_RETRY_MAX_ATTEMPTS} got network error on {method} {path_or_url}: {exc}; retrying")
        time.sleep(_RETRY_BASE_DELAY_S * (2 ** (attempt - 1)))

    raise last_err if last_err else RuntimeError("fabric_request exhausted retries without an outcome")


def list_workspaces(token: str) -> Iterator[dict[str, Any]]:
    """Yield all Fabric workspaces visible to the service principal.

    Safety cap at 500 pages (~100k workspaces at ~200/page) so a buggy API
    returning a self-referential continuation token cannot loop forever and
    occupy the runner until the access token expires.
    """
    next_path = "/workspaces"
    for _ in range(500):
        if not next_path:
            break
        data = fabric_request("GET", next_path, token)
        for workspace in data.get("value", []):
            yield workspace
        continuation_uri = data.get("continuationUri")
        continuation_token = data.get("continuationToken")
        if continuation_uri:
            next_path = continuation_uri
        elif continuation_token:
            token_qs = urllib.parse.quote(str(continuation_token), safe="")
            next_path = f"/workspaces?continuationToken={token_qs}"
        else:
            next_path = ""
    else:
        # for-else: ran 500 iterations without breaking, meaning the API kept
        # producing continuations. Surface this loudly rather than silently
        # truncating; an operator can re-run with a tighter prefix filter.
        print("[list_workspaces] hit 500-page pagination safety cap; remaining workspaces not enumerated.")


def delete_workspace_by_id(workspace_id: str, token: str) -> None:
    """Delete a Fabric workspace by immutable workspace ID."""
    workspace_id_path = urllib.parse.quote(workspace_id, safe="")
    fabric_request("DELETE", f"/workspaces/{workspace_id_path}", token)


def parse_created_from_smoke_name(name: str, prefix: str) -> dt.datetime | None:
    if not fnmatch.fnmatchcase(name, f"{prefix}*"):
        return None
    match = re.match(r"^" + re.escape(prefix) + r"(\d{8}-\d{6})(?:-.+)?$", name)
    if not match:
        return None
    stamp = match.group(1)
    try:
        return dt.datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def format_age(hours: float) -> str:
    return f"{hours:.2f}h"


def get_fabric_token() -> str:
    explicit = os.environ.get("FABRIC_ACCESS_TOKEN", "").strip()
    if explicit:
        return explicit
    # The workflow logs in with the smoke service principal first. Asking az for
    # a Fabric token here avoids storing another secret and keeps the script local.
    result = subprocess.run(
        [
            "az",
            "account",
            "get-access-token",
            "--resource",
            "https://api.fabric.microsoft.com",
            "--query",
            "accessToken",
            "-o",
            "tsv",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("az account get-access-token returned an empty Fabric token")
    return token


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cutoff-hours", type=float, default=DEFAULT_CUTOFF_HOURS)
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.cutoff_hours < MIN_CUTOFF_HOURS:
        raise SystemExit(
            f"--cutoff-hours must be at least {MIN_CUTOFF_HOURS} "
            f"(got {args.cutoff_hours}); smaller values risk deleting actively-provisioning workspaces."
        )
    if not args.prefix.endswith("-"):
        raise SystemExit("--prefix must end with '-' so safety matching cannot be widened accidentally")

    now = dt.datetime.now(dt.timezone.utc)
    cutoff = float(args.cutoff_hours)
    token = get_fabric_token()

    scanned = matched = eligible = deleted = already_gone = failed = 0
    for workspace in list_workspaces(token):
        scanned += 1
        name = str(workspace.get("displayName") or "")
        workspace_id = str(workspace.get("id") or "")
        if not fnmatch.fnmatchcase(name, f"{args.prefix}*"):
            continue
        matched += 1
        created = parse_created_from_smoke_name(name, args.prefix)
        if created is None:
            print(f"Skipping matched workspace with unparseable timestamp: name={name!r} id={workspace_id}")
            continue
        age_hours = (now - created).total_seconds() / 3600.0
        if age_hours < cutoff:
            print(f"Keeping workspace name={name} id={workspace_id} age={format_age(age_hours)} cutoff={format_age(cutoff)}")
            continue
        eligible += 1
        if not workspace_id:
            print(f"ERROR: Cannot delete matched workspace without id: name={name}", file=sys.stderr)
            failed += 1
            continue
        if args.dry_run:
            print(f"DRY-RUN delete workspace name={name} id={workspace_id} age={format_age(age_hours)}")
            continue
        try:
            delete_workspace_by_id(workspace_id, token)
            deleted += 1
            print(f"Deleted workspace name={name} id={workspace_id} age={format_age(age_hours)}")
        except FabricApiError as exc:
            # 404 means the workspace is already gone -- benign race when the
            # daily cron meets a per-shard cleanup or a concurrent dispatch.
            # Treat as success so a "previous cleanup actually worked" outcome
            # doesn't turn the cron red. Any other status is a real failure.
            # Turning a benign race into a red cron trains operators to
            # ignore the alert, which defeats its purpose.
            if exc.status == 404:
                already_gone += 1
                print(f"Already gone (404, benign race) workspace name={name} id={workspace_id} age={format_age(age_hours)}")
            else:
                failed += 1
                print(f"ERROR: Delete failed name={name} id={workspace_id} age={format_age(age_hours)} status={exc.status} body={exc.body[:500]}", file=sys.stderr)

    print(
        "Cleanup summary: "
        f"scanned={scanned} matched={matched} eligible={eligible} deleted={deleted} "
        f"already_gone={already_gone} dry_run={str(args.dry_run).lower()} failed={failed} cutoff_hours={cutoff}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
