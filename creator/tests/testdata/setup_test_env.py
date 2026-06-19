#!/usr/bin/env python3
"""
End-to-end smoke test environment setup.

1. Interactive login to the test tenant
2. Discover available Fabric capacity
3. Create a timestamped workspace
4. Create a lakehouse in the workspace
5. Create a test notebook attached to the lakehouse
5b. Create a deterministically-failing notebook and run it (spark-operations fixture)
6. Upload sample data and load into Delta table
7. Create a Direct Lake semantic model
8. Create an Eventhouse with KQL database and load Storm Events data
9. Create a Dataflow Gen2 with a simple Power Query M definition
10. Create a baseline Activator / Reflex item for smoke tests

Usage:
    python setup_test_env.py
    python setup_test_env.py --tenant E2EAPIMSIT2.onmicrosoft.com
    python setup_test_env.py --tenant E2EAPIMSIT2.onmicrosoft.com --skip-login
    python setup_test_env.py --capacity-id <guid>  # skip capacity discovery
"""

import argparse
import base64
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# On Windows, az CLI is az.cmd — need shell=True for subprocess
_SHELL = os.name == "nt"
FABRIC_API = "https://api.fabric.microsoft.com/v1"
FABRIC_RESOURCE = "https://api.fabric.microsoft.com"
KUSTO_RESOURCE = "https://kusto.kusto.windows.net"
TABLE_NAME = "nyctlc"
WEATHER_TABLE = "Weather"
STORM_EVENTS_URL = "https://kustosamples.blob.core.windows.net/samplefiles/StormEvents.csv"
NOTEBOOK_NAME = "sparkauthoring_notebook_check"
FAILING_NOTEBOOK_NAME = "spark_operations_failing_notebook"
SEMANTIC_MODEL_NAME = "nyctaxi_yellow_directlake"
DATAFLOW_NAME = "SkillsTestDataflow"
ACTIVATOR_NAME = "SkillsTestActivator"
WAREHOUSE_NAME = "SkillsTestWarehouse"


def _build_notebook_ipynb(workspace_id: str, lakehouse_id: str, lakehouse_name: str) -> str:
    """Return a .ipynb JSON string for the test notebook."""
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "language_info": {"name": "python"},
            "trident": {
                "lakehouse": {
                    "default_lakehouse": lakehouse_id,
                    "default_lakehouse_name": lakehouse_name,
                    "default_lakehouse_workspace_id": workspace_id,
                    "known_lakehouses": [{"id": lakehouse_id}],
                }
            },
        },
        "cells": [
            {
                "cell_type": "code",
                "source": [
                    "df = spark.table('nyctlc')\n",
                    "df_filtered = df.filter('trip_distance > 1000')\n",
                    "df_sample = df_filtered.limit(100)\n",
                    "print(f'Sanity check complete. Sampled {df_sample.count()} records.')",
                ],
                "metadata": {},
                "outputs": [],
                "execution_count": None,
            }
        ],
    }
    return json.dumps(notebook)


def _build_failing_notebook_ipynb(workspace_id: str, lakehouse_id: str | None,
                                  lakehouse_name: str | None) -> str:
    """Return a .ipynb JSON string for a notebook that deterministically fails.

    The spark-operations diagnostics evals need a real failed job instance to
    diagnose. The cell runs a trivial Spark statement, then raises
    RuntimeError("spark operations eval failure"). When a lakehouse is available
    the notebook is attached to it via trident metadata, matching the normal
    test notebook and the documented full-eval plan
    (full-eval-tests/plan/03-individual-skills/eval-spark-operations.md).
    """
    metadata = {"language_info": {"name": "python"}}
    if lakehouse_id:
        metadata["trident"] = {
            "lakehouse": {
                "default_lakehouse": lakehouse_id,
                "default_lakehouse_name": lakehouse_name,
                "default_lakehouse_workspace_id": workspace_id,
                "known_lakehouses": [{"id": lakehouse_id}],
            }
        }
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": metadata,
        "cells": [
            {
                "cell_type": "code",
                "source": [
                    # The RuntimeError message is the SO-01 pass-criteria string
                    # in full-eval-tests/plan/03-individual-skills/
                    # eval-spark-operations.md; keep the two in sync.
                    "spark.range(1).count()\n",
                    "raise RuntimeError('spark operations eval failure')",
                ],
                "metadata": {},
                "outputs": [],
                "execution_count": None,
            }
        ],
    }
    return json.dumps(notebook)


def _start_notebook_run(workspace_id: str, notebook_id: str, token: str,
                        retries: int = 4, backoff: int = 15) -> str | None:
    """Trigger an on-demand RunNotebook job, retrying on throttle/5xx.

    Returns the 202 Location header (the job-instance poll URL) or None. Retries
    429/430/5xx responses, honoring the Retry-After header when present, so a
    transient throttle on the shared tenant does not silently leave the fixture
    with a created-but-never-run notebook. Never raises: a kick-off failure only
    degrades the spark-operations eval, it must not abort environment setup.
    """
    url = (f"{FABRIC_API}/workspaces/{workspace_id}/items/{notebook_id}"
           "/jobs/instances?jobType=RunNotebook")
    for attempt in range(retries):
        try:
            req = Request(url, method="POST",
                          headers={"Authorization": f"Bearer {token}"})
            with urlopen(req) as resp:
                location = resp.headers.get("Location")
                resp.read()
                if resp.status in (200, 201, 202) and location:
                    return location
                print(f"  WARNING: RunNotebook returned HTTP {resp.status} "
                      f"(location={location!r}).", file=sys.stderr)
                return None
        except HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:300]
            is_transient = e.code in (429, 430) or 500 <= e.code < 600
            if is_transient and attempt < retries - 1:
                server_hint = _parse_retry_after_seconds(
                    (e.headers or {}).get("Retry-After"))
                wait = (min(server_hint, 600) if server_hint is not None
                        else backoff * (2 ** attempt))
                print(f"  RunNotebook throttled/5xx (HTTP {e.code}); retrying in "
                      f"{wait}s (attempt {attempt + 1}/{retries}).", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"  WARNING: RunNotebook failed: HTTP {e.code} {body}",
                  file=sys.stderr)
            return None
        except Exception as e:  # noqa: BLE001 - setup must never abort on a run kick-off
            print(f"  WARNING: RunNotebook failed: {e}", file=sys.stderr)
            return None
    return None


def _await_failing_run(poll_url: str | None, token: str, timeout: int = 600,
                       interval: int = 15) -> str | None:
    """Poll a RunNotebook job instance until it reaches a terminal state.

    Returns the final status string (expected 'Failed' for the diagnostics
    fixture); None on timeout or polling error. Never raises -- a missing failed
    run only degrades the spark-operations eval, it must not abort setup.
    """
    if not poll_url:
        return None
    terminal = {"Completed", "Failed", "Cancelled", "Deduped"}
    elapsed = 0
    while elapsed < timeout:
        try:
            req = Request(poll_url, method="GET",
                          headers={"Authorization": f"Bearer {token}"})
            with urlopen(req) as resp:
                body = resp.read().decode("utf-8")
            status = (json.loads(body) if body.strip() else {}).get("status", "")
            if status in terminal:
                return status
        except Exception as e:  # noqa: BLE001 - poll is best-effort
            print(f"  WARNING: polling failing-notebook run: {e}", file=sys.stderr)
        time.sleep(interval)
        elapsed += interval
    return None


def _provision_failing_notebook(workspace_id: str, token: str,
                                lakehouse_id: str | None = None,
                                lakehouse_name: str | None = None) -> str | None:
    """Create spark_operations_failing_notebook and kick off a run that fails.

    Returns the job-instance poll URL (await later via _await_failing_run) or
    None. Non-fatal throughout: this fixture only feeds the spark-operations
    diagnostics evals, so any failure here warns and returns None rather than
    aborting the whole environment setup.
    """
    try:
        payload = base64.b64encode(
            _build_failing_notebook_ipynb(workspace_id, lakehouse_id, lakehouse_name)
            .encode("utf-8")).decode("utf-8")
        nb = api_lro("post", f"/workspaces/{workspace_id}/items", token, {
            "displayName": FAILING_NOTEBOOK_NAME,
            "type": "Notebook",
            "definition": {"format": "ipynb", "parts": [
                {"path": "notebook-content.ipynb", "payload": payload,
                 "payloadType": "InlineBase64"}]},
        })
        # Validate the returned object is the created Notebook item before trusting
        # its id: api_lro may return the LRO operation payload (whose id is the
        # operation id, not the item id) when the result fetch fails.
        notebook_id = None
        if nb and nb.get("id") and nb.get("type") == "Notebook":
            notebook_id = nb["id"]
        if not notebook_id:
            existing = api("get", f"/workspaces/{workspace_id}/items?type=Notebook",
                           token, retries=1)
            for item in (existing or {}).get("value", []):
                if item.get("displayName") == FAILING_NOTEBOOK_NAME:
                    notebook_id = item.get("id")
                    break
        if not notebook_id:
            print(f"  WARNING: could not create/resolve {FAILING_NOTEBOOK_NAME}; "
                  "spark-operations 'Diagnose failed notebook run' eval will fail.",
                  file=sys.stderr)
            return None
        print(f"  Created: {FAILING_NOTEBOOK_NAME}")
        poll_url = _start_notebook_run(workspace_id, notebook_id, token)
        if poll_url:
            print(f"  Started failing run for {FAILING_NOTEBOOK_NAME}.")
        return poll_url
    except Exception as e:  # noqa: BLE001 - fixture provisioning must never abort setup
        print(f"  WARNING: provisioning {FAILING_NOTEBOOK_NAME} failed: {e}; "
              "spark-operations 'Diagnose failed notebook run' eval will fail.",
              file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_az(*args, check=True) -> subprocess.CompletedProcess:
    """Run an az CLI command."""
    cmd = ["az"] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, check=check, shell=_SHELL)


def get_token() -> str:
    """Get Fabric API access token."""
    result = run_az("account", "get-access-token", "--resource", FABRIC_RESOURCE)
    return json.loads(result.stdout)["accessToken"]


# Module-level record of the most recent api() failure. Populated by api()
# on every non-2xx (or post-retry-exhaustion) outcome and cleared on success.
# Lets callers distinguish throttle (rotate to another capacity, where rotation
# applies) and transient backend 5xx (also rotation-eligible) from
# auth/payload/permission errors (fail loud, do not rotate).
_LAST_API_ERROR: dict = {"status": 0, "body": "", "throttled": False, "transient": False}

# HTTP status codes that ALWAYS indicate a throttle regardless of body shape.
#   429 = standard "Too Many Requests" (control-plane throttle).
#   430 = Fabric-specific Spark/Trial-SKU throttle (e.g. TooManyRequestsForCapacity).
#         Surfaced by Livy session create and Spark statement submission when CU
#         smoothing trips. Body wording varies; status code is the reliable signal.
_THROTTLE_STATUS_CODES = frozenset({429, 430})

# Error codes that, when present in the response body, indicate a throttle even
# if the status code is not in _THROTTLE_STATUS_CODES (some Fabric endpoints
# return throttle as 503 or 400 with the error code in the body). Compared
# case-insensitively against the decoded response body so a server-side casing
# tweak (e.g. `capacitylimitexceeded`) does not silently regress.
_THROTTLE_BODY_CODES = (
    "CapacityLimitExceeded",       # control-plane workspace/lakehouse provisioning
    "TooManyRequestsForCapacity",  # Spark/Livy CU-smoothing throttle (PR #234)
    "RequestThrottled",            # generic Fabric REST throttle
    "BurstThrottle",               # short-burst limiter
)

# Error codes / status classes that indicate a TRANSIENT backend issue (not a
# throttle, not a client bug). These are usually Fabric/Power BI control-plane
# timeouts or internal hiccups that recover within seconds. Retrying is safe
# and effective; rotating to a different capacity may also help if the backend
# overload is capacity-scoped rather than tenant-wide.
#
# PowerBISqlCommandTimeout: observed during multi-shard ephemeral workspace
#   provisioning when the shared tenant is under cross-PR load. Returns HTTP
#   500 with isRetriable=false in the body, but is empirically retriable on a
#   30-60s timescale (the "isRetriable" hint is the backend's hot-path advice,
#   not a permanent verdict).
#
# Codes added here MUST be specific enough to avoid false-positive matches
# against nested message fields of NON-transient errors. Generic phrases like
# "ServiceUnavailable" or "InternalServerError" deliberately not included --
# they would silently match permanent errors whose `message` field happens to
# mention upstream service state (e.g.
# `{"errorCode":"DataMovementError","message":"detected ServiceUnavailable
# upstream"}`), causing wasted CI time and misleading log lines. Add new
# entries only when (a) the code is empirically observed transient and
# (b) the token is specific enough that an accidental substring match is
# extremely unlikely.
_TRANSIENT_BODY_CODES = (
    "PowerBISqlCommandTimeout",
)

# Transient 5xx retry budget. 3 attempts total (1 initial + 2 retries) with
# exponential backoff base 15s. Wall-clock added before giving up depends on
# the wait source:
#   - No server hint: jittered exp backoff (+/-20%). Worst case ~18s + ~36s
#     = ~54s wall-clock added.
#   - Server-hinted Retry-After honored, capped at 600s (10 min). Worst case
#     2 x 600s = 1200s = 20 min wall-clock added when the backend keeps
#     sending Retry-After: >=600 on every response. The 600s cap exists
#     specifically to protect against pathological server hints like
#     Retry-After: 86400 that would otherwise blow the 70-min shard timeout.
# 3 attempts is generous enough to absorb >95% of transient backend
# timeouts based on the empirical PowerBISqlCommandTimeout recovery window
# (30-60s); throttles keep the original 5-attempt budget because rate-limit
# windows legitimately persist for minutes.
_MAX_TRANSIENT_RETRIES = 2
_TRANSIENT_BACKOFF_BASE = 15


def _is_throttle(status: int, body: str) -> bool:
    """Return True if an HTTP error represents a retryable throttle."""
    if status in _THROTTLE_STATUS_CODES:
        return True
    body_lower = (body or "").lower()
    return any(code.lower() in body_lower for code in _THROTTLE_BODY_CODES)


def _is_transient_5xx(status: int, body: str) -> bool:
    """Return True if an HTTP error represents a transient backend 5xx that is
    safe to retry. Distinct from throttle: transient 5xx is the backend being
    overloaded or briefly broken; throttle is the backend deliberately rate-
    limiting us. Both are retriable; both can rotate-capacity-eligible; the
    retry budget and backoff differ."""
    if not (500 <= status < 600):
        return False
    body_lower = (body or "").lower()
    return any(code.lower() in body_lower for code in _TRANSIENT_BODY_CODES)


def _parse_retry_after_seconds(value: str | None) -> int | None:
    """Parse a Retry-After header into a non-negative integer seconds value.

    Returns None for missing, non-integer, or negative values so the caller
    falls back to exponential backoff. HTTP-date form (RFC 7231) is not
    supported on purpose -- Fabric returns delta-seconds in practice, and
    silently accepting a malformed date would mask a server-side change."""
    if not value:
        return None
    stripped = value.strip()
    if not stripped.isdigit():
        return None
    try:
        parsed = int(stripped)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def api(method: str, path: str, token: str, body: dict = None,
        retries: int = 5, backoff: int = 30,
        expected_errors: tuple = ()) -> dict | None:
    """Call Fabric REST API with retry on throttling and transient backend 5xx.

    Args:
        retries: max attempts for THROTTLE responses (429/430 + body-coded
            throttles like CapacityLimitExceeded). Each retry uses exponential
            backoff (`backoff * 2**n`) capped by server-provided Retry-After
            when present. Default 5 attempts (~7.5 min worst-case wall-clock).
            NOTE: this budget does NOT apply to transient backend 5xx errors
            (PowerBISqlCommandTimeout etc.), which use an independent, tighter
            budget of `_MAX_TRANSIENT_RETRIES + 1 = 3` attempts. Wall-clock
            added by transient retries depends on the wait source: ~54s
            worst-case with jittered exp backoff when no server hint;
            up to ~20 min when honoring repeated Retry-After hints at the
            600s cap. Permanent errors (auth, payload, 4xx) fail on the
            first attempt regardless of `retries`.
        backoff: base seconds for the throttle exponential-backoff schedule
            (`backoff * 2**n`). The transient-5xx schedule uses an independent
            base (`_TRANSIENT_BACKOFF_BASE`) and is not configurable per call.
        expected_errors: A tuple of error-code substrings (e.g.
            ("PrincipalAlreadyHasWorkspaceRolePermissions",)) that callers
            expect to encounter. When the API returns a non-2xx whose body
            contains any of these substrings, the error is logged as INFO
            (not error) so CI logs stay clean for idempotent operations.
    """
    if retries < 1:
        # Programming error: api() must make at least one attempt.
        # Record honestly so callers checking _LAST_API_ERROR.throttled
        # don't see a stale or synthetic value.
        _LAST_API_ERROR.update({"status": 0, "body": f"retries={retries} (< 1)", "throttled": False, "transient": False})
        print(f"ERROR: api() called with retries={retries} (< 1); no attempts made.", file=sys.stderr)
        return None

    url = f"{FABRIC_API}{path}" if path.startswith("/") else path

    # Per-category retry counters: throttle uses the caller-provided `retries`
    # budget (default 5, ~7.5 min worst-case wall-clock); transient 5xx uses a
    # tighter independent budget (_MAX_TRANSIENT_RETRIES + 1 attempts, ~54s
    # worst-case with jitter, up to ~20 min worst-case when Retry-After is
    # honored at the 600s cap) so a backend-overload spike does not multiply
    # against a long throttle budget.
    #
    # Outer-loop bound derivation:
    #   The function returns the moment a single iteration falls through to
    #   the error path (either category's gate FALSE, or a non-retriable
    #   error). Therefore only ONE per-category budget can fully exhaust
    #   (sleeps + 1 fall-through) in a single call; the OTHER category can
    #   only be partially consumed (sleeps without fall-through). Worst-case
    #   total iterations in a mixed throttle/transient call:
    #     full-exhaust(throttle)=retries + partial(transient)=_MAX_TRANSIENT_RETRIES
    #   = retries + _MAX_TRANSIENT_RETRIES.
    #   The trailing +1 is purely defensive: it gives the loop a safety
    #   margin if a future change widens either gate condition. Costs nothing
    #   in the happy path (the extra iteration is never reached today).
    #
    # The loop index is unused (timing is driven by the per-category counters,
    # not the index) -- bound via `_` so a future reader does not accidentally
    # read the wrong counter.
    throttle_retries_used = 0
    transient_retries_used = 0
    max_attempts = retries + _MAX_TRANSIENT_RETRIES + 1

    for _ in range(max_attempts):
        data = json.dumps(body).encode("utf-8") if body else None
        req = Request(url, data=data, method=method.upper(),
                      headers={"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json"})

        try:
            with urlopen(req) as resp:
                resp_body = resp.read().decode("utf-8")
                _LAST_API_ERROR.update({"status": resp.status, "body": "", "throttled": False, "transient": False})
                return json.loads(resp_body) if resp_body.strip() else {}
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            is_throttle = _is_throttle(e.code, error_body)
            is_transient = (not is_throttle) and _is_transient_5xx(e.code, error_body)

            if is_throttle and throttle_retries_used < retries - 1:
                # Honor server-provided Retry-After when present (Fabric sometimes
                # sends it on 429/430). Otherwise exponential backoff from `backoff`.
                # Cap server-provided value at 10 minutes to keep CI within the
                # job timeout when a misbehaving endpoint returns Retry-After: 86400.
                server_hint = _parse_retry_after_seconds(
                    e.headers.get("Retry-After") if e.headers else None
                )
                wait = min(server_hint, 600) if server_hint is not None else backoff * (2 ** throttle_retries_used)
                throttle_retries_used += 1
                total_throttle_attempts = throttle_retries_used + 1
                print(f"  Throttled (HTTP {e.code}). Retrying in {wait}s (throttle attempt {total_throttle_attempts}/{retries})...")
                time.sleep(wait)
                continue

            if is_transient and transient_retries_used < _MAX_TRANSIENT_RETRIES:
                # Transient backend 5xx (e.g. PowerBISqlCommandTimeout): retry on
                # a short exponential schedule. Independent of throttle backoff
                # because backend timeouts recover on a faster timescale than
                # rate-limit windows.
                #
                # Symmetric with throttle: honor server-provided Retry-After
                # when present (RFC 7231 7.1.3 permits it on 503; Power BI
                # control-plane sometimes surfaces it on backend overload).
                # Cap at 10 minutes to keep CI within the job timeout when a
                # misbehaving endpoint returns Retry-After: 86400.
                #
                # When no server hint, apply +/-20% jitter to the exponential
                # backoff. The scenario this PR is hardening for is N shards
                # hitting the same transient 5xx at roughly the same wall-
                # clock; deterministic 15s/30s waits would cause all N shards
                # to slam the recovering backend simultaneously at t=15s, then
                # again at t=45s -- the textbook thundering-herd pattern that
                # the new retry was supposed to mitigate. Jitter spreads the
                # retry wave across a window so the backend can recover.
                server_hint = _parse_retry_after_seconds(
                    e.headers.get("Retry-After") if e.headers else None
                )
                if server_hint is not None:
                    wait = min(server_hint, 600)
                else:
                    base_wait = _TRANSIENT_BACKOFF_BASE * (2 ** transient_retries_used)
                    wait = max(1, int(base_wait * random.uniform(0.8, 1.2)))
                transient_retries_used += 1
                total_transient_attempts = transient_retries_used + 1
                print(f"  Transient backend error (HTTP {e.code}). Retrying in {wait}s (transient attempt {total_transient_attempts}/{_MAX_TRANSIENT_RETRIES + 1})...")
                time.sleep(wait)
                continue

            _LAST_API_ERROR.update({
                "status": e.code,
                "body": error_body,
                "throttled": is_throttle,
                "transient": is_transient,
            })
            if any(expected in error_body for expected in expected_errors):
                # Caller marked this error as expected (idempotent operation).
                # Log at INFO level so CI doesn't surface a scary stderr.
                print(f"  Note ({e.code}): {error_body.strip()[:200]} (expected per caller)")
            else:
                print(f"  API error ({e.code}): {error_body.strip()}", file=sys.stderr)
            return None

    # Defensive: every iteration of the loop above either returns (on success
    # or on the last attempt's HTTPError) or continues (on retriable throttle
    # or transient with attempts remaining). The function should not reach this
    # point for retries >= 1; _LAST_API_ERROR is already populated by the last
    # iteration.
    return None


def api_lro(method: str, path: str, token: str, body: dict = None,
            timeout: int = 300) -> dict | None:
    """Call Fabric REST API that returns a 202 Long-Running Operation.

    Polls the operation Location URL until completion, then returns
    the operation result.
    """
    url = f"{FABRIC_API}{path}" if path.startswith("/") else path
    data = json.dumps(body).encode("utf-8") if body else None
    req = Request(url, data=data, method=method.upper(),
                  headers={"Authorization": f"Bearer {token}",
                           "Content-Type": "application/json"})

    try:
        with urlopen(req) as resp:
            # 201 = created directly (no LRO)
            if resp.status == 201:
                rb = resp.read().decode("utf-8")
                return json.loads(rb) if rb.strip() and rb.strip() != "null" else {}

            # 202 = Long-Running Operation
            location = resp.headers.get("Location")
            retry_after = int(resp.headers.get("Retry-After", "5"))
            resp.read()  # drain body

            if not location:
                _LAST_API_ERROR.update({
                    "status": resp.status,
                    "body": "202 Accepted but no Location header",
                    "throttled": False,
                    "transient": False,
                })
                print("  WARNING: 202 response but no Location header.", file=sys.stderr)
                return {}

            # Poll operation status
            elapsed = 0
            while elapsed < timeout:
                time.sleep(retry_after)
                elapsed += retry_after
                poll_req = Request(location, method="GET",
                                   headers={"Authorization": f"Bearer {token}"})
                try:
                    with urlopen(poll_req) as poll_resp:
                        poll_body = poll_resp.read().decode("utf-8")
                        result = json.loads(poll_body) if poll_body.strip() and poll_body.strip() != "null" else {}
                        status = result.get("status", "")
                        if status == "Succeeded":
                            # Try to get the created resource from the operation result URL
                            result_url = location.rstrip("/") + "/result"
                            try:
                                res_req = Request(result_url, method="GET",
                                                  headers={"Authorization": f"Bearer {token}"})
                                with urlopen(res_req) as res_resp:
                                    res_body = res_resp.read().decode("utf-8")
                                    if res_body.strip() and res_body.strip() != "null":
                                        return json.loads(res_body)
                            except HTTPError:
                                pass
                            return result
                        elif status in ("Failed", "Cancelled"):
                            error = result.get("error", {})
                            _LAST_API_ERROR.update({
                                "status": 0,
                                "body": json.dumps(error) if error else f"LRO {status}",
                                "throttled": False,
                                "transient": False,
                            })
                            print(f"  LRO {status}: {error}", file=sys.stderr)
                            return None
                        # else Running — keep polling
                except HTTPError as e:
                    e.read()
                    # Transient error during poll — keep trying
                    continue

            print(f"  LRO timed out after {timeout}s.", file=sys.stderr)
            _LAST_API_ERROR.update({
                "status": 0,
                "body": f"LRO timed out after {timeout}s",
                "throttled": False,
                "transient": True,
            })
            return None

    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        _LAST_API_ERROR.update({
            "status": e.code,
            "body": error_body,
            "throttled": e.code == 429,
            "transient": e.code in (500, 502, 503, 504),
        })
        print(f"  API error ({e.code}): {error_body[:500]}", file=sys.stderr)
        return None


def wait_for_capacity_assignment(workspace_id: str, token: str, timeout: int = 120) -> bool:
    """Wait for workspace capacity assignment to complete."""
    for _ in range(timeout // 5):
        ws = api("get", f"/workspaces/{workspace_id}", token, retries=1)
        if ws and ws.get("capacityAssignmentProgress") == "Completed":
            return True
        print("  Waiting for capacity assignment...")
        time.sleep(5)
    return False


def get_kusto_token() -> str:
    """Get Kusto data-plane access token."""
    result = run_az("account", "get-access-token", "--resource", KUSTO_RESOURCE)
    return json.loads(result.stdout)["accessToken"]


def kql_execute(query_uri: str, database: str, command: str, kusto_token: str,
                endpoint: str = "mgmt") -> dict | None:
    """Execute a KQL management command or query via the Kusto REST API."""
    url = f"{query_uri}/v1/rest/{endpoint}"
    body = json.dumps({"db": database, "csl": command}).encode("utf-8")
    req = Request(url, data=body, method="POST",
                  headers={"Authorization": f"Bearer {kusto_token}",
                           "Content-Type": "application/json"})
    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  KQL error ({e.code}): {error_body[:500]}", file=sys.stderr)
        return None


def _build_model_bim(sql_connection_string: str, lakehouse_name: str) -> str:
    """Return TMSL model.bim JSON for a Direct Lake semantic model over the nyctlc table."""
    model = {
        "compatibilityLevel": 1604,
        "model": {
            "culture": "en-US",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "expressions": [
                {
                    "name": "DatabaseQuery",
                    "kind": "m",
                    "expression": [
                        "let",
                        f'    database = Sql.Database("{sql_connection_string}", "{lakehouse_name}")',
                        "in",
                        "    database",
                    ],
                }
            ],
            "tables": [
                {
                    "name": "nyctlc",
                    "columns": [
                        {"name": "vendor_id", "dataType": "int64", "sourceColumn": "vendor_id", "summarizeBy": "none"},
                        {"name": "tpep_pickup_datetime", "dataType": "dateTime", "sourceColumn": "tpep_pickup_datetime", "summarizeBy": "none"},
                        {"name": "tpep_dropoff_datetime", "dataType": "dateTime", "sourceColumn": "tpep_dropoff_datetime", "summarizeBy": "none"},
                        {"name": "passenger_count", "dataType": "double", "sourceColumn": "passenger_count", "summarizeBy": "sum"},
                        {"name": "trip_distance", "dataType": "double", "sourceColumn": "trip_distance", "summarizeBy": "sum"},
                        {"name": "ratecode_id", "dataType": "double", "sourceColumn": "ratecode_id", "summarizeBy": "none"},
                        {"name": "store_and_fwd_flag", "dataType": "string", "sourceColumn": "store_and_fwd_flag", "summarizeBy": "none"},
                        {"name": "pu_location_id", "dataType": "int64", "sourceColumn": "pu_location_id", "summarizeBy": "none"},
                        {"name": "do_location_id", "dataType": "int64", "sourceColumn": "do_location_id", "summarizeBy": "none"},
                        {"name": "payment_type", "dataType": "int64", "sourceColumn": "payment_type", "summarizeBy": "none"},
                        {"name": "fare_amount", "dataType": "double", "sourceColumn": "fare_amount", "summarizeBy": "sum"},
                        {"name": "extra", "dataType": "double", "sourceColumn": "extra", "summarizeBy": "sum"},
                        {"name": "mta_tax", "dataType": "double", "sourceColumn": "mta_tax", "summarizeBy": "sum"},
                        {"name": "tip_amount", "dataType": "double", "sourceColumn": "tip_amount", "summarizeBy": "sum"},
                        {"name": "tolls_amount", "dataType": "double", "sourceColumn": "tolls_amount", "summarizeBy": "sum"},
                        {"name": "improvement_surcharge", "dataType": "double", "sourceColumn": "improvement_surcharge", "summarizeBy": "sum"},
                        {"name": "total_amount", "dataType": "double", "sourceColumn": "total_amount", "summarizeBy": "sum"},
                        {"name": "congestion_surcharge", "dataType": "double", "sourceColumn": "congestion_surcharge", "summarizeBy": "sum"},
                        {"name": "airport_fee", "dataType": "double", "sourceColumn": "airport_fee", "summarizeBy": "sum"},
                    ],
                    "partitions": [
                        {
                            "name": "nyctlc-partition",
                            "mode": "directLake",
                            "source": {
                                "type": "entity",
                                "entityName": "nyctlc",
                                "expressionSource": "DatabaseQuery",
                                "schemaName": "dbo",
                            },
                        }
                    ],
                    "measures": [
                        {
                            "name": "Total Trips",
                            "expression": "COUNTROWS(nyctlc)",
                            "formatString": "#,##0",
                        },
                        {
                            "name": "Average Fare",
                            "expression": "AVERAGE(nyctlc[fare_amount])",
                            "formatString": "$#,##0.00",
                        },
                        {
                            "name": "Average Trip Distance",
                            "expression": "AVERAGE(nyctlc[trip_distance])",
                            "formatString": "#,##0.00",
                        },
                    ],
                }
            ],
        },
    }
    return json.dumps(model)


def _load_lakehouse_data(workspace_id: str, lakehouse_id: str, csv_path, token: str) -> bool:
    """Upload CSV to OneLake and load into Delta table via Livy/Spark.

    Returns True if data was loaded successfully, False otherwise.
    """
    if not csv_path.exists():
        print(f"WARNING: Sample CSV not found: {csv_path}")
        print("  Skipping data load. Run generate_nyctlc_sample.py first.")
        return False

    print(f"=== Step 6: Upload and load data ===\n")

    # 5a: Upload CSV to OneLake Files
    storage_token_result = run_az("account", "get-access-token",
                                  "--resource", "https://storage.azure.com", check=False)
    if storage_token_result.returncode != 0:
        print(f"  Failed to get OneLake token: {storage_token_result.stderr.strip()}", file=sys.stderr)
        return False
    storage_token = json.loads(storage_token_result.stdout)["accessToken"]

    ws_info = api("get", f"/workspaces/{workspace_id}", token)
    onelake_dfs = "https://onelake.dfs.fabric.microsoft.com"
    if ws_info and "oneLakeEndpoints" in ws_info:
        onelake_dfs = ws_info["oneLakeEndpoints"].get("dfsEndpoint", onelake_dfs)

    onelake_url = f"{onelake_dfs}/{workspace_id}/{lakehouse_id}/Files/{csv_path.name}"
    print(f"  Uploading {csv_path.name} to OneLake...")

    try:
        req = Request(f"{onelake_url}?resource=file", method="PUT",
                      headers={"Authorization": f"Bearer {storage_token}"})
        urlopen(req)
    except HTTPError as e:
        print(f"  Upload create failed: {e.code} {e.reason}", file=sys.stderr)
        return False

    file_data = csv_path.read_bytes()
    file_size = len(file_data)
    try:
        req = Request(f"{onelake_url}?position=0&action=append", data=file_data, method="PATCH",
                      headers={"Authorization": f"Bearer {storage_token}",
                               "Content-Type": "application/octet-stream",
                               "Content-Length": str(file_size)})
        urlopen(req)
    except HTTPError as e:
        print(f"  Upload append failed: {e.code} {e.reason}", file=sys.stderr)
        return False

    try:
        req = Request(f"{onelake_url}?position={file_size}&action=flush", method="PATCH",
                      headers={"Authorization": f"Bearer {storage_token}"})
        urlopen(req)
    except HTTPError as e:
        print(f"  Upload flush failed: {e.code} {e.reason}", file=sys.stderr)
        return False

    print(f"  Uploaded ({file_size / 1024:.1f} KB)\n")

    # 5b: Load into Delta table via Livy/Spark
    print("  Creating Livy session...")
    livy_base = (f"{FABRIC_API}/workspaces/{workspace_id}/lakehouses/{lakehouse_id}"
                 "/livyApi/versions/2023-12-01/sessions")
    session = api("post", livy_base, token, {"kind": "pyspark"})
    if not session or "id" not in session:
        print(f"  Failed to create Livy session: {session}", file=sys.stderr)
        return False

    session_id = session["id"]
    session_url = f"{livy_base}/{session_id}"

    for _ in range(60):
        status = api("get", session_url, token, retries=1)
        if status and status.get("state") == "idle":
            break
        print("  Waiting for Livy session to start...")
        time.sleep(5)
    else:
        print("  Livy session did not start in time.", file=sys.stderr)
        api("delete", session_url, token, retries=1)
        return False

    print("  Livy session ready. Running Spark load...")

    spark_code = (
        f'csv_path = "abfss://{workspace_id}@onelake.dfs.fabric.microsoft.com'
        f'/{lakehouse_id}/Files/{csv_path.name}"\n'
        f'df = spark.read.option("header", "true").option("inferSchema", "true").csv(csv_path)\n'
        f'df.write.mode("overwrite").format("delta").saveAsTable("{TABLE_NAME}")\n'
        f'print(f"Loaded {{df.count()}} rows into {TABLE_NAME}")\n'
    )

    stmt = api("post", f"{session_url}/statements", token, {"code": spark_code, "kind": "pyspark"})
    if not stmt or "id" not in stmt:
        print(f"  Failed to submit Spark statement: {stmt}", file=sys.stderr)
        api("delete", session_url, token, retries=1)
        return False

    stmt_url = f"{session_url}/statements/{stmt['id']}"

    loaded = False
    for _ in range(120):
        result = api("get", stmt_url, token, retries=1)
        if result and result.get("state") == "available":
            output = result.get("output", {})
            if output.get("status") == "ok":
                text = output.get("data", {}).get("text/plain", "")
                print(f"  Spark output: {text.strip()}")
                loaded = True
            else:
                traceback_lines = output.get("traceback", [])
                print(f"  Spark error: {output.get('status')}", file=sys.stderr)
                for line in traceback_lines[:10]:
                    print(f"    {line}", file=sys.stderr)
            break
        time.sleep(3)

    api("delete", session_url, token, retries=1)
    print("  Livy session closed.\n")
    return loaded


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Setup smoke test environment")
    parser.add_argument("--tenant", default="E2EAPIMSIT2.onmicrosoft.com",
                        help="Azure AD tenant for login")
    parser.add_argument("--skip-login", action="store_true",
                        help="Skip interactive login (reuse existing session)")
    parser.add_argument("--capacity-id", help="Fabric capacity ID (skip discovery)")
    parser.add_argument("--lakehouse-name", default="LSEGDemo",
                        help="Lakehouse name to create")
    parser.add_argument("--eventhouse-name", default="SkillsTestEventhouse",
                        help="Eventhouse / KQL database name to create")
    parser.add_argument("--csv", type=Path,
                        default=Path(__file__).parent / "nyctlc_sample.csv",
                        help="Path to sample CSV")
    parser.add_argument("--sp-object-id",
                        help="Optional service principal object ID to grant Contributor on the created workspace (for CI flows where smoke runs as an SP).")
    parser.add_argument("--dry-run", action="store_true", help="Print plan only")
    parser.add_argument("--name-suffix", default="",
                        help="Suffix appended to the generated workspace name. "
                             "Used by the vally smoke matrix to give each shard a unique workspace "
                             "(e.g. --name-suffix '-shard0' -> 'skills-for-fabric-test-YYYYMMDD-HHMMSS-shard0').")
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = args.name_suffix or ""

    workspace_name = f"skills-for-fabric-test-{timestamp}{suffix}"

    if args.dry_run:
        print("DRY RUN:")
        print(f"  Tenant: {args.tenant}")
        print(f"  Workspace: {workspace_name}")
        print(f"  Lakehouse: {args.lakehouse_name}")
        print(f"  Eventhouse: {args.eventhouse_name}")
        print(f"  CSV: {args.csv}")
        return

    # ------------------------------------------------------------------
    # Step 1: Interactive login
    # ------------------------------------------------------------------
    if not args.skip_login:
        print(f"=== Step 1: Login to {args.tenant} ===\n")
        result = run_az("login", "--tenant", args.tenant, check=False)
        if result.returncode != 0:
            print(f"Login failed: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        print("  Logged in successfully.\n")
    else:
        print("=== Step 1: Login (skipped) ===\n")

    token = get_token()
    print(f"  Token acquired.\n")

    # ------------------------------------------------------------------
    # Step 2: Discover capacity (collect ALL active capacities for rotation)
    # ------------------------------------------------------------------
    # Rationale: CapacityLimitExceeded throttles can persist for hours on a single
    # capacity (observed 3.5h+ in production). Trying multiple active capacities
    # in sequence is faster than waiting for any one capacity to recover, since
    # the throttle is typically per-capacity (CU smoothing) rather than tenant-wide.
    print("=== Step 2: Discover Fabric capacity ===\n")
    candidate_capacities = []

    if args.capacity_id:
        # Explicit override: caller pinned a specific capacity. Disable rotation.
        candidate_capacities = [{"id": args.capacity_id, "displayName": "(explicit override)"}]
    else:
        caps = api("get", "/capacities", token)
        if not caps or "value" not in caps or not caps["value"]:
            print("ERROR: No Fabric capacities found for this account.", file=sys.stderr)
            print("The test user needs access to at least one Fabric capacity.", file=sys.stderr)
            sys.exit(1)

        for cap in caps["value"]:
            state = cap.get("state", "Unknown")
            print(f"  Found: {cap['displayName']} (id={cap['id']}, sku={cap.get('sku', '?')}, state={state})")
            if state == "Active":
                candidate_capacities.append({"id": cap["id"], "displayName": cap["displayName"]})

        if not candidate_capacities:
            print("ERROR: No active capacity found.", file=sys.stderr)
            sys.exit(1)

        # Rotate the starting index by workspace-name hash so concurrent CI runs
        # do not all hammer the same first capacity. If that capacity is throttled,
        # different runs will pick different starting points and find a free one
        # without paying the full first-capacity retry delay.
        if len(candidate_capacities) > 1:
            start_idx = int(hashlib.md5(workspace_name.encode("utf-8")).hexdigest(), 16) % len(candidate_capacities)
            candidate_capacities = candidate_capacities[start_idx:] + candidate_capacities[:start_idx]
            print(f"  Starting rotation at index {start_idx} (hashed from workspace name).")

    print(f"  {len(candidate_capacities)} active capacity/capacities available for rotation.\n")

    # ------------------------------------------------------------------
    # Steps 3 + 3b + 4: Provision workspace + SP role + lakehouse, rotating
    # to a backup capacity ONLY when a provisioning step inside the loop
    # (workspace creation OR lakehouse creation) hits CapacityLimitExceeded.
    # ------------------------------------------------------------------
    # Workspace and lakehouse failures that are NOT throttle (auth/payload/
    # permission bugs) fail loud without rotation. SP role assignment errors
    # are treated as best-effort and never trigger rotation. This ensures we
    # never mask real configuration errors by trying a different capacity.
    # First capacity attempt uses the default retry budget (5 retries, ~7.5 min
    # worst case). Subsequent attempts use a shorter budget (2 retries, ~30s worst
    # case) for fail-fast rotation. Bounded total scales with active capacity count.
    workspace_id = None
    lakehouse_id = None
    used_capacity = None

    for attempt_idx, cap in enumerate(candidate_capacities):
        cap_id = cap["id"]
        cap_name = cap["displayName"]
        attempt_retries = 5 if attempt_idx == 0 else 2
        print(f"--- Capacity attempt {attempt_idx + 1}/{len(candidate_capacities)}: '{cap_name}' (id={cap_id}) ---\n")

        # Step 3: Create workspace
        print(f"=== Step 3: Create workspace '{workspace_name}' ===\n")
        ws = api("post", "/workspaces", token, {
            "displayName": workspace_name,
            "capacityId": cap_id,
        }, retries=attempt_retries)
        if not ws or "id" not in ws:
            if _LAST_API_ERROR.get("throttled"):
                print(f"  Workspace creation throttled on capacity '{cap_name}'. Trying next capacity...", file=sys.stderr)
                continue
            if _LAST_API_ERROR.get("transient"):
                # Transient 5xx (e.g. PowerBISqlCommandTimeout) exhausted in-call
                # retries. Rotating to another capacity may help if the overload
                # is capacity-scoped; if it is tenant-wide, the next capacity
                # will also fail and the loop will exit cleanly below.
                print(f"  Workspace creation hit transient backend error on capacity '{cap_name}'. Trying next capacity...", file=sys.stderr)
                continue
            # Non-throttle, non-transient failure: do not rotate. Auth/payload/
            # permission bugs repeat on every capacity and would only mask the
            # real cause.
            print(f"ERROR: Workspace creation failed with non-retriable error (status={_LAST_API_ERROR.get('status')}). See api() output above.", file=sys.stderr)
            sys.exit(1)

        attempt_workspace_id = ws["id"]
        print(f"  Created: {workspace_name}")
        print(f"  ID: {attempt_workspace_id}")

        # Wait for capacity assignment
        if not wait_for_capacity_assignment(attempt_workspace_id, token):
            print("WARNING: Capacity assignment not confirmed. Proceeding anyway...")
        else:
            print(f"  Capacity assigned.\n")

        # Step 3b: Grant SP Contributor (optional, for CI flows)
        if args.sp_object_id:
            print(f"=== Step 3b: Grant SP {args.sp_object_id} Contributor on workspace ===\n")
            # Best-effort: try the grant and tolerate non-2xx. When the SP creates the
            # workspace itself, Fabric auto-grants Admin and a subsequent Contributor
            # grant correctly returns 409 PrincipalAlreadyHasWorkspaceRolePermissions
            # (the SP already has access; role may even be higher than Contributor).
            # We pass that error code as `expected_errors` so api() logs it as INFO
            # instead of an `API error (...)` stderr message; keeps CI logs clean
            # for the common idempotent case. Truly unexpected non-2xx errors still
            # surface normally.
            try:
                result = api("post", f"/workspaces/{attempt_workspace_id}/roleAssignments", token, {
                    "principal": {"id": args.sp_object_id, "type": "ServicePrincipal"},
                    "role": "Contributor",
                }, expected_errors=("PrincipalAlreadyHasWorkspaceRolePermissions",))
                if result is None:
                    # api() already logged the situation appropriately.
                    print(f"  (See log above. Smoke run will fail-fast if SP actually lacks access.)\n")
                else:
                    print(f"  Granted Contributor to SP {args.sp_object_id}\n")
            except Exception as exc:
                print(f"WARNING: Failed to grant SP Contributor role: {exc}", file=sys.stderr)
                print("Smoke runs as the SP will not see this workspace until the role is assigned manually.\n", file=sys.stderr)

        # Step 4: Create lakehouse
        print(f"=== Step 4: Create lakehouse '{args.lakehouse_name}' ===\n")
        lh = api("post", f"/workspaces/{attempt_workspace_id}/items", token, {
            "displayName": args.lakehouse_name,
            "type": "Lakehouse",
        }, retries=attempt_retries)
        if lh and "id" in lh:
            workspace_id = attempt_workspace_id
            lakehouse_id = lh["id"]
            used_capacity = cap
            print(f"  Created: {args.lakehouse_name}")
            print(f"  ID: {lakehouse_id}\n")
            if attempt_idx > 0:
                print(f"NOTE: Provisioned on backup capacity '{cap_name}' after primary capacity was throttled.\n", file=sys.stderr)
            break

        # Lakehouse creation failed. Rotate ONLY on throttle or transient 5xx;
        # fail loud otherwise.
        if not (_LAST_API_ERROR.get("throttled") or _LAST_API_ERROR.get("transient")):
            print(f"ERROR: Lakehouse creation failed with non-retriable error (status={_LAST_API_ERROR.get('status')}). See api() output above.", file=sys.stderr)
            # Best-effort cleanup of the orphaned workspace before exiting.
            cleanup_result = api("delete", f"/workspaces/{attempt_workspace_id}", token, retries=2)
            if cleanup_result is None:
                print(f"WARNING: Could not delete orphaned workspace {attempt_workspace_id} (status={_LAST_API_ERROR.get('status')}). Nightly cleanup will reap it.", file=sys.stderr)
            sys.exit(1)

        # Throttled or transient: delete the partial workspace and rotate to next capacity.
        reason = "throttled" if _LAST_API_ERROR.get("throttled") else "transient backend error"
        print(f"  Lakehouse creation {reason} on capacity '{cap_name}'. Deleting partial workspace and trying next capacity...", file=sys.stderr)
        try:
            delete_result = api("delete", f"/workspaces/{attempt_workspace_id}", token, retries=2)
            if delete_result is None:
                # api() already logged the failure to stderr. Workspace may leak;
                # nightly cleanup will reap it. Continue rotation regardless.
                print(f"  WARNING: Could not delete partial workspace {attempt_workspace_id} (status={_LAST_API_ERROR.get('status')}). May leak; nightly cleanup will reap.", file=sys.stderr)
            else:
                print(f"  Deleted workspace {attempt_workspace_id}.", file=sys.stderr)
        except Exception as exc:
            print(f"WARNING: Failed to delete partial workspace {attempt_workspace_id}: {exc}", file=sys.stderr)

    if not workspace_id or not lakehouse_id:
        last_status = _LAST_API_ERROR.get("status")
        last_body_snippet = (_LAST_API_ERROR.get("body") or "")[:200]
        last_kind = "transient backend error" if _LAST_API_ERROR.get("transient") else "throttling"
        if args.capacity_id:
            print(f"ERROR: Pinned capacity '{args.capacity_id}' hit {last_kind} (last status={last_status}, body={last_body_snippet!r}).", file=sys.stderr)
            print("Unset --capacity-id (or the FABRIC_CAPACITY_ID repo variable when running in CI) to fall back to discovery + rotation, or wait and re-run.", file=sys.stderr)
        else:
            print(f"ERROR: Exhausted all {len(candidate_capacities)} active capacities. All hit {last_kind} (last status={last_status}, body={last_body_snippet!r}).", file=sys.stderr)
            print("This indicates a sustained tenant-wide Fabric throttle or backend outage. Re-run later (typically resolves within 1-24h).", file=sys.stderr)
        sys.exit(1)

    print(f"Provisioning complete. Using capacity: '{used_capacity['displayName']}' (id={used_capacity['id']})\n")

    # ------------------------------------------------------------------
    # Step 5: Create test notebook
    # ------------------------------------------------------------------
    print(f"=== Step 5: Create notebook '{NOTEBOOK_NAME}' ===\n")
    nb_content = _build_notebook_ipynb(workspace_id, lakehouse_id, args.lakehouse_name)
    nb_payload = base64.b64encode(nb_content.encode("utf-8")).decode("utf-8")

    nb = api_lro("post", f"/workspaces/{workspace_id}/items", token, {
        "displayName": NOTEBOOK_NAME,
        "type": "Notebook",
        "definition": {
            "format": "ipynb",
            "parts": [
                {
                    "path": "notebook-content.ipynb",
                    "payload": nb_payload,
                    "payloadType": "InlineBase64",
                }
            ],
        },
    })
    if nb is not None:
        print(f"  Created: {NOTEBOOK_NAME}\n")
    else:
        print(f"  WARNING: Failed to create notebook.", file=sys.stderr)

    # ------------------------------------------------------------------
    # Step 5b: Create a deterministically-failing notebook and kick off a run
    # so the spark-operations 'Diagnose failed notebook run' eval has a real
    # failed job instance to diagnose. The run is awaited near the end of setup
    # (below) so it overlaps the remaining provisioning steps.
    # ------------------------------------------------------------------
    print(f"\n=== Step 5b: Create failing notebook '{FAILING_NOTEBOOK_NAME}' ===\n")
    failing_run_poll_url = _provision_failing_notebook(
        workspace_id, token, lakehouse_id, args.lakehouse_name)

    # ------------------------------------------------------------------
    # Step 6: Generate sample CSV if missing, then upload and load
    # ------------------------------------------------------------------
    if not args.csv.exists():
        print(f"  Sample CSV not found at {args.csv}, generating...")
        gen_script = Path(__file__).parent / "generate_nyctlc_sample.py"
        gen_result = subprocess.run(
            [sys.executable, str(gen_script)],
            cwd=str(gen_script.parent),
        )
        if gen_result.returncode != 0:
            print("WARNING: generate_nyctlc_sample.py failed. Data will not be loaded.")
        elif not args.csv.exists():
            print("WARNING: generate script succeeded but CSV still missing.")

    loaded = _load_lakehouse_data(workspace_id, lakehouse_id, args.csv, token)

    # Wait for SQL endpoint to sync the new table
    if loaded:
        print("  Waiting for SQL endpoint to discover table...")
        lh_detail = api("get", f"/workspaces/{workspace_id}/lakehouses/{lakehouse_id}", token)
        sql_conn = None
        if lh_detail:
            sql_props = lh_detail.get("properties", {}).get("sqlEndpointProperties", {})
            sql_conn = sql_props.get("connectionString")

        if sql_conn:
            for attempt in range(36):  # up to ~3 minutes
                try:
                    probe = subprocess.run(
                        ["sqlcmd", "-S", sql_conn, "-d", args.lakehouse_name, "-G",
                         "-Q", f"SET NOCOUNT ON; SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = '{TABLE_NAME}'",
                         "-W", "-h", "-1"],
                        capture_output=True, text=True, timeout=15, shell=_SHELL,
                    )
                    count = probe.stdout.strip()
                    if count == "1":
                        print(f"  SQL endpoint synced — {TABLE_NAME} visible.\n")
                        break
                except Exception:
                    pass
                time.sleep(5)
            else:
                print("  WARNING: SQL endpoint did not sync within timeout. Tests may be flaky.\n")
        else:
            print("  WARNING: Could not get SQL connection string. Skipping sync check.\n")

    # ------------------------------------------------------------------
    # Step 7: Create Direct Lake semantic model
    # ------------------------------------------------------------------
    semantic_model_id = None
    if loaded:
        print(f"=== Step 7: Create semantic model '{SEMANTIC_MODEL_NAME}' ===\n")

        # Get SQL endpoint connection string
        lh_detail = api("get", f"/workspaces/{workspace_id}/lakehouses/{lakehouse_id}", token)
        sm_sql_conn = None
        if lh_detail:
            sm_sql_props = lh_detail.get("properties", {}).get("sqlEndpointProperties", {})
            sm_sql_conn = sm_sql_props.get("connectionString")

        if sm_sql_conn:
            model_bim = _build_model_bim(sm_sql_conn, args.lakehouse_name)
            pbism = json.dumps({
                "version": "4.0",
                "settings": {},
            })

            sm_payload = {
                "displayName": SEMANTIC_MODEL_NAME,
                "description": "NYC Yellow Taxi trip data (Direct Lake over lakehouse delta table)",
                "definition": {
                    "parts": [
                        {
                            "path": "model.bim",
                            "payload": base64.b64encode(model_bim.encode()).decode(),
                            "payloadType": "InlineBase64",
                        },
                        {
                            "path": "definition.pbism",
                            "payload": base64.b64encode(pbism.encode()).decode(),
                            "payloadType": "InlineBase64",
                        },
                    ]
                },
            }

            sm = api_lro("post", f"/workspaces/{workspace_id}/semanticModels", token, sm_payload)
            if sm and "id" in sm:
                semantic_model_id = sm["id"]
                print(f"  Created: {SEMANTIC_MODEL_NAME}")
                print(f"  ID: {semantic_model_id}\n")
            elif sm is not None:
                # LRO succeeded but didn't return the item — look it up
                items = api("get", f"/workspaces/{workspace_id}/semanticModels", token)
                if items and "value" in items:
                    for item in items["value"]:
                        if item.get("displayName") == SEMANTIC_MODEL_NAME:
                            semantic_model_id = item["id"]
                            break
                if semantic_model_id:
                    print(f"  Created: {SEMANTIC_MODEL_NAME}")
                    print(f"  ID: {semantic_model_id}\n")
                else:
                    print("  WARNING: Semantic model created but could not find ID.\n", file=sys.stderr)
            else:
                print(f"  WARNING: Failed to create semantic model.\n", file=sys.stderr)
        else:
            print("  WARNING: No SQL endpoint connection string. Skipping semantic model.\n")
    else:
        print("\n  Skipping semantic model creation (no data loaded).\n")

    # ------------------------------------------------------------------
    # Step 8: Create Eventhouse and load Storm Events data
    # ------------------------------------------------------------------
    eventhouse_name = args.eventhouse_name
    eventhouse_id = None
    kql_db_name = None
    weather_loaded = False

    print(f"=== Step 8: Create Eventhouse '{eventhouse_name}' ===\n")

    # 6a: Create Eventhouse item
    eh = api("post", f"/workspaces/{workspace_id}/items", token, {
        "displayName": eventhouse_name,
        "type": "Eventhouse",
    })
    if not eh or "id" not in eh:
        print(f"ERROR: Failed to create eventhouse: {eh}", file=sys.stderr)
        print_summary(workspace_name, workspace_id, args.lakehouse_name,
                      lakehouse_id, loaded, semantic_model_id,
                      eventhouse_name, None, None, False)
        return

    eventhouse_id = eh["id"]
    print(f"  Created: {eventhouse_name}")
    print(f"  ID: {eventhouse_id}\n")

    # 6b: Wait for KQL database to be provisioned
    print("  Waiting for KQL database to provision...")
    query_uri = None
    for _ in range(60):
        dbs = api("get", f"/workspaces/{workspace_id}/kqlDatabases", token, retries=1)
        if dbs and "value" in dbs:
            for db in dbs["value"]:
                props = db.get("properties", {})
                parent = props.get("parentEventhouseItemId", "")
                if parent == eventhouse_id or db.get("displayName") == eventhouse_name:
                    query_uri = props.get("queryServiceUri")
                    kql_db_name = props.get("databaseName") or db.get("displayName")
                    break
        if query_uri:
            break
        time.sleep(5)

    if not query_uri:
        print("ERROR: KQL database did not provision in time.", file=sys.stderr)
        print_summary(workspace_name, workspace_id, args.lakehouse_name,
                      lakehouse_id, loaded, semantic_model_id,
                      eventhouse_name, eventhouse_id, None, False)
        return

    print(f"  KQL database: {kql_db_name}")
    print(f"  Query URI: {query_uri}\n")

    # 6c: Get Kusto token
    kusto_token = get_kusto_token()

    # 6d: Create Weather table and load data using externaldata operator
    # The StormEvents CSV has 22 columns; we define only the first 11 so extras
    # are ignored.  The where clause filters to year 2007 (59,066 rows).
    print(f"  Creating and loading {WEATHER_TABLE} table from Azure samples blob...")
    ingest_cmd = (
        f".set-or-replace {WEATHER_TABLE} <|\n"
        "externaldata(\n"
        "    StartTime: datetime, EndTime: datetime, EpisodeId: int, EventId: int,\n"
        "    State: string, EventType: string, InjuriesDirect: int, InjuriesIndirect: int,\n"
        "    DeathsDirect: int, DeathsIndirect: int, DamageProperty: int\n"
        ")\n"
        f"[h'{STORM_EVENTS_URL}']\n"
        "with (format='csv', ignoreFirstRecord=true)\n"
        "| where StartTime >= datetime(2007-01-01) and StartTime < datetime(2008-01-01)"
    )
    result = kql_execute(query_uri, kql_db_name, ingest_cmd, kusto_token)
    if not result:
        print("ERROR: Failed to load Weather data.", file=sys.stderr)
        print_summary(workspace_name, workspace_id, args.lakehouse_name,
                      lakehouse_id, loaded, semantic_model_id,
                      eventhouse_name, eventhouse_id, kql_db_name, False)
        return

    # 6e: Verify row count
    print("  Verifying row count...")
    count_result = kql_execute(query_uri, kql_db_name,
                               f"{WEATHER_TABLE} | count", kusto_token,
                               endpoint="query")
    row_count = 0
    if count_result:
        try:
            rows = count_result.get("Tables", [{}])[0].get("Rows", [])
            if rows:
                row_count = rows[0][0]
        except (IndexError, KeyError, TypeError):
            pass

    if row_count > 0:
        print(f"  {WEATHER_TABLE} table loaded: {row_count:,} rows\n")
        weather_loaded = True
    else:
        print(f"WARNING: {WEATHER_TABLE} row count is {row_count}. Data may not have loaded.", file=sys.stderr)

    # ------------------------------------------------------------------
    # Step 9: Create a Dataflow Gen2 with a simple Power Query M definition
    # ------------------------------------------------------------------
    dataflow_id = None
    print(f"=== Step 9: Create Dataflow Gen2 '{DATAFLOW_NAME}' ===\n")

    df = api("post", f"/workspaces/{workspace_id}/items", token, {
        "displayName": DATAFLOW_NAME,
        "type": "Dataflow",
        "description": "Test dataflow for smoke tests",
    })
    if df and "id" in df:
        dataflow_id = df["id"]
        print(f"  Created: {DATAFLOW_NAME}")
        print(f"  ID: {dataflow_id}")

        # Now update definition with Power Query M content
        mashup_pq = (
            'section Section1;\n'
            'shared Output = let\n'
            '    Source = #table(type table [City = text, Population = number],\n'
            '        {{"Seattle", 749256}, {"Portland", 652573}, {"Vancouver", 702000}})\n'
            'in Source;'
        )
        query_metadata = json.dumps({
            "formatVersion": "202502",
            "name": DATAFLOW_NAME,
            "queryGroups": [],
            "documentLocale": "en-US",
            "queriesMetadata": {
                "Output": {
                    "queryId": "00000000-0000-0000-0000-000000000001",
                    "queryName": "Output",
                    "loadEnabled": True,
                }
            }
        })
        platform_json = json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {
                "type": "Dataflow",
                "displayName": DATAFLOW_NAME,
            },
            "config": {
                "version": "2.0",
                "logicalId": "00000000-0000-0000-0000-000000000000",
            },
        })

        update_payload = {
            "definition": {
                "parts": [
                    {
                        "path": "mashup.pq",
                        "payload": base64.b64encode(mashup_pq.encode()).decode(),
                        "payloadType": "InlineBase64",
                    },
                    {
                        "path": "queryMetadata.json",
                        "payload": base64.b64encode(query_metadata.encode()).decode(),
                        "payloadType": "InlineBase64",
                    },
                    {
                        "path": ".platform",
                        "payload": base64.b64encode(platform_json.encode()).decode(),
                        "payloadType": "InlineBase64",
                    },
                ]
            },
        }

        upd = api_lro("post",
                       f"/workspaces/{workspace_id}/dataflows/{dataflow_id}/updateDefinition",
                       token, update_payload)
        if upd is not None:
            print(f"  Definition updated with Power Query M content.\n")
        else:
            print(f"  WARNING: Failed to update dataflow definition. Dataflow exists but is empty.\n",
                  file=sys.stderr)
    else:
        print(f"  WARNING: Failed to create dataflow.\n", file=sys.stderr)

    # ------------------------------------------------------------------
    # Step 10: Create baseline Activator / Reflex item for smoke tests
    # ------------------------------------------------------------------
    activator_id = None
    print(f"=== Step 10: Create Activator '{ACTIVATOR_NAME}' ===\n")

    activator = api_lro("post", f"/workspaces/{workspace_id}/reflexes", token, {
        "displayName": ACTIVATOR_NAME,
        "description": "Baseline Activator item for smoke tests",
    })
    if activator and "id" in activator:
        activator_id = activator["id"]
        print(f"  Created: {ACTIVATOR_NAME}")
        print(f"  ID: {activator_id}\n")
    else:
        print("  WARNING: Failed to create baseline Activator.\n", file=sys.stderr)
        existing_activators = api("get", f"/workspaces/{workspace_id}/reflexes", token, retries=1)
        for item in (existing_activators or {}).get("value", []):
            if item.get("displayName") == ACTIVATOR_NAME:
                activator_id = item.get("id")
                print(f"  Found existing Activator: {ACTIVATOR_NAME}")
                print(f"  ID: {activator_id}\n")
                break
        if not activator_id:
            print("  WARNING: Could not resolve an existing baseline Activator by name.\n",
                  file=sys.stderr)

    # ------------------------------------------------------------------
    # Step 11: Create baseline Warehouse item for smoke tests
    # ------------------------------------------------------------------
    # Required by the dataflows-authoring-cli output-destination-warehouse smoke
    # test, which expects to find a Warehouse in the workspace to bind as an
    # output destination. Provisioning is best-effort: Warehouse creation
    # requires a Fabric capacity that supports it (F2+); if it fails (typically
    # InsufficientSKU on under-sized capacities), we log and continue so the
    # rest of the smoke suite still runs.
    warehouse_id = None
    print(f"=== Step 11: Create Warehouse '{WAREHOUSE_NAME}' ===\n")

    wh = api_lro("post", f"/workspaces/{workspace_id}/items", token, {
        "displayName": WAREHOUSE_NAME,
        "type": "Warehouse",
        "description": "Baseline Warehouse for smoke tests (output destination target).",
    })
    if wh and wh.get("id") and wh.get("type") == "Warehouse":
        warehouse_id = wh["id"]
        print(f"  Created: {WAREHOUSE_NAME}")
        print(f"  ID: {warehouse_id}\n")
    else:
        # Capture the real api_lro() failure details NOW, before the fallback
        # GET below — that GET succeeds (HTTP 200) and resets _LAST_API_ERROR,
        # which would otherwise make the warning print "status=200, body=''"
        # instead of the actual create failure (e.g. InsufficientSKU).
        create_status = _LAST_API_ERROR.get("status")
        create_body_snippet = (_LAST_API_ERROR.get("body") or "")[:200]
        # Idempotency / robustness fallback: resolve the Warehouse by name. This
        # covers two cases: (a) a previous run already created it on this
        # workspace, and (b) api_lro() fell back to returning the LRO *operation*
        # payload (whose `id` is the operation id, not the Warehouse item id) when
        # the /result fetch failed — so we never trust an unvalidated id here.
        existing_items = api("get", f"/workspaces/{workspace_id}/items?type=Warehouse",
                             token, retries=1)
        for item in (existing_items or {}).get("value", []):
            if item.get("displayName") == WAREHOUSE_NAME:
                warehouse_id = item.get("id")
                print(f"  Found existing Warehouse: {WAREHOUSE_NAME}")
                print(f"  ID: {warehouse_id}\n")
                break
        if not warehouse_id:
            print(f"  WARNING: Failed to create Warehouse (status={create_status}, body={create_body_snippet!r}). "
                  "output-destination-warehouse smoke test will fail until a Warehouse exists in this workspace.\n",
                  file=sys.stderr)

    # Await the spark_operations_failing_notebook run started in Step 5b so its
    # failed job instance exists before the eval suite runs. Best-effort: a
    # timeout or unexpected non-Failed terminal state only warns.
    if failing_run_poll_url:
        print(f"=== Awaiting failing run for '{FAILING_NOTEBOOK_NAME}' ===\n")
        final_status = _await_failing_run(failing_run_poll_url, token)
        if final_status == "Failed":
            print(f"  {FAILING_NOTEBOOK_NAME} run Failed as expected (fixture ready).\n")
        elif final_status is None:
            print(f"  WARNING: {FAILING_NOTEBOOK_NAME} run did not reach a terminal "
                  "state in time; the diagnose-failed-notebook eval may be flaky this run.\n",
                  file=sys.stderr)
        else:
            print(f"  WARNING: {FAILING_NOTEBOOK_NAME} run ended '{final_status}', "
                  "expected 'Failed'; the diagnose-failed-notebook eval may fail.\n",
                  file=sys.stderr)

    print_summary(workspace_name, workspace_id, args.lakehouse_name,
                  lakehouse_id, loaded, semantic_model_id,
                  eventhouse_name, eventhouse_id, kql_db_name, weather_loaded,
                  dataflow_name=DATAFLOW_NAME, dataflow_id=dataflow_id,
                  activator_name=ACTIVATOR_NAME, activator_id=activator_id,
                  warehouse_name=WAREHOUSE_NAME, warehouse_id=warehouse_id)


def print_summary(ws_name, ws_id, lh_name, lh_id, loaded, sm_id=None,
                  eh_name=None, eh_id=None, kql_db_name=None, weather_loaded=False,
                  dataflow_name=None, dataflow_id=None,
                  activator_name=None, activator_id=None,
                  warehouse_name=None, warehouse_id=None):
    """Print a machine-parseable summary."""
    print("=" * 50)
    print("SETUP SUMMARY")
    print("=" * 50)
    print(f"  Workspace:  {ws_name}")
    print(f"  Workspace ID: {ws_id}")
    print(f"  Lakehouse:  {lh_name}")
    print(f"  Lakehouse ID: {lh_id}")
    print(f"  Data loaded: {'YES' if loaded else 'NO'}")
    print(f"  Table: {TABLE_NAME}")
    if sm_id:
        print(f"  Semantic Model: {SEMANTIC_MODEL_NAME}")
        print(f"  Semantic Model ID: {sm_id}")
    if eh_name:
        print(f"  Eventhouse: {eh_name}")
        print(f"  Eventhouse ID: {eh_id}")
        print(f"  KQL Database: {kql_db_name}")
        print(f"  Weather loaded: {'YES' if weather_loaded else 'NO'}")
    if dataflow_name:
        print(f"  Dataflow: {dataflow_name}")
        print(f"  Dataflow ID: {dataflow_id or 'N/A'}")
    if activator_name:
        print(f"  Activator: {activator_name}")
        print(f"  Activator ID: {activator_id or 'N/A'}")
    if warehouse_name:
        print(f"  Warehouse: {warehouse_name}")
        print(f"  Warehouse ID: {warehouse_id or 'N/A'}")

    # Write output JSON for downstream scripts
    output = {
        "workspace_name": ws_name,
        "workspace_id": ws_id,
        "lakehouse_name": lh_name,
        "lakehouse_id": lh_id,
        "data_loaded": loaded,
        "table_name": TABLE_NAME,
        "eventhouse_name": eh_name,
        "eventhouse_id": eh_id,
        "kql_database_name": kql_db_name,
        "weather_loaded": weather_loaded,
        "dataflow_name": dataflow_name,
        "dataflow_id": dataflow_id,
        "activator_name": activator_name,
        "activator_id": activator_id,
        "warehouse_name": warehouse_name,
        "warehouse_id": warehouse_id,
    }
    out_path = Path(__file__).parent / "last_setup.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Output written to: {out_path}")


if __name__ == "__main__":
    main()
