# Unit tests for tests/testdata/setup_test_env.py focused on the
# capacity-rotation safety surface added 2026-05-25.
#
# Why these tests:
#   The rotation loop in main() distinguishes "CapacityLimitExceeded" (rotate)
#   from "other HTTP error" (fail loud) by reading _LAST_API_ERROR after each
#   api() call. If api() ever forgets to update that record, or updates it
#   incorrectly, the rotation will either mask real auth/payload bugs or
#   abort prematurely on a fixable throttle. These tests pin that contract.

import importlib.util
import io
import json
import sys
import unittest
import unittest.mock
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


SCRIPT_PATH = (Path(__file__).resolve().parent / "testdata" / "setup_test_env.py")


def load_setup_module():
    """Load setup_test_env.py as an importable module without running main()."""
    spec = importlib.util.spec_from_file_location("setup_test_env", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["setup_test_env"] = module
    spec.loader.exec_module(module)
    return module


def _make_http_error(status: int, body: str, headers: dict | None = None) -> HTTPError:
    """Build an HTTPError whose .read() returns the given body.

    Optional `headers` dict surfaces as `e.headers.get(...)` so tests can
    cover the Retry-After branch in api()'s throttle handler.
    """
    return HTTPError(
        url="https://api.fabric.microsoft.com/v1/test",
        code=status,
        msg="error",
        hdrs=headers or {},
        fp=io.BytesIO(body.encode("utf-8")),
    )


class FakeResponse:
    """Minimal stand-in for urlopen's context-managed response."""

    def __init__(self, status=200, body=b'{"id": "abc"}', headers=None):
        self.status = status
        self._body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


class ApiErrorTrackingTests(unittest.TestCase):
    """Verify _LAST_API_ERROR is updated correctly by api() on every code path."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_setup_module()

    def setUp(self):
        self.mod._LAST_API_ERROR.update({"status": 0, "body": "", "throttled": False})

    def test_success_clears_throttled_flag(self):
        with patch.object(self.mod, "urlopen", return_value=FakeResponse(200, b'{"id": "ws1"}')):
            result = self.mod.api("get", "/workspaces", "token")
        self.assertEqual(result, {"id": "ws1"})
        self.assertFalse(self.mod._LAST_API_ERROR["throttled"])
        self.assertEqual(self.mod._LAST_API_ERROR["status"], 200)

    def test_capacity_limit_exceeded_marks_throttled(self):
        # No retries left so the throttle path returns immediately and records state.
        body = '{"errorCode":"CapacityLimitExceeded","message":"throttled"}'
        err = _make_http_error(429, body)
        with patch.object(self.mod, "urlopen", side_effect=err):
            result = self.mod.api("post", "/workspaces/abc/items", "token", body={}, retries=1)
        self.assertIsNone(result)
        self.assertTrue(self.mod._LAST_API_ERROR["throttled"])
        self.assertEqual(self.mod._LAST_API_ERROR["status"], 429)

    def test_non_throttle_error_does_not_mark_throttled(self):
        body = '{"errorCode":"Unauthorized","message":"bad token"}'
        err = _make_http_error(401, body)
        with patch.object(self.mod, "urlopen", side_effect=err):
            result = self.mod.api("post", "/workspaces", "token", body={}, retries=1)
        self.assertIsNone(result)
        self.assertFalse(self.mod._LAST_API_ERROR["throttled"])
        self.assertEqual(self.mod._LAST_API_ERROR["status"], 401)

    def test_retries_exhausted_marks_throttled(self):
        # All retries hit throttle. The "exhausted" final state must still be
        # marked throttled so the rotation loop rotates instead of failing loud.
        body = '{"errorCode":"CapacityLimitExceeded","message":"throttled"}'

        def make_err(*a, **kw):
            raise _make_http_error(429, body)

        with patch.object(self.mod, "urlopen", side_effect=make_err), \
             patch.object(self.mod.time, "sleep"):
            result = self.mod.api("post", "/workspaces", "token", body={}, retries=2)
        self.assertIsNone(result)
        self.assertTrue(self.mod._LAST_API_ERROR["throttled"])

    def test_expected_error_still_records_status(self):
        # Expected (idempotent) errors must NOT trip the throttled flag and
        # should record the actual status for any caller that inspects it.
        body = '{"errorCode":"PrincipalAlreadyHasWorkspaceRolePermissions"}'
        err = _make_http_error(409, body)
        with patch.object(self.mod, "urlopen", side_effect=err):
            result = self.mod.api("post", "/workspaces/abc/roleAssignments", "token",
                                  body={}, retries=1,
                                  expected_errors=("PrincipalAlreadyHasWorkspaceRolePermissions",))
        self.assertIsNone(result)
        self.assertFalse(self.mod._LAST_API_ERROR["throttled"])
        self.assertEqual(self.mod._LAST_API_ERROR["status"], 409)

    def test_retries_below_one_fails_honestly(self):
        # api() must reject retries < 1 without making any request, and must
        # NOT report the failure as a throttle (would falsely trigger rotation).
        # Pin this contract so a regression cannot reintroduce the misleading
        # synthetic 429 the bot reviewer flagged on PR #263.
        with patch.object(self.mod, "urlopen") as fake_urlopen:
            result = self.mod.api("get", "/workspaces", "token", retries=0)
        self.assertIsNone(result)
        self.assertFalse(self.mod._LAST_API_ERROR["throttled"])
        fake_urlopen.assert_not_called()

    def test_http_430_marks_throttled_regardless_of_body(self):
        # PR #234: Spark Livy returns HTTP 430 with errorCode "430"
        # and a TooManyRequestsForCapacity message, NOT the control-plane
        # CapacityLimitExceeded string. Before this change, api() would not
        # retry and the smoke would fail-fast. After this change, status 430
        # always counts as throttle so the retry-with-backoff loop fires.
        livy_throttle_body = (
            '{"requestId":"24139a1e-7c6f-47bc-957f-0f5c1ad638db",'
            '"errorCode":"430",'
            '"message":"[TooManyRequestsForCapacity] HTTP Response code 430: '
            'This Spark job can\'t be run because you\'ve hit a Spark compute '
            'or API rate limit. ..."}'
        )
        err = _make_http_error(430, livy_throttle_body)
        with patch.object(self.mod, "urlopen", side_effect=err):
            result = self.mod.api("post", "/workspaces/abc/lakehouses/xyz/livyApi/.../sessions",
                                  "token", body={}, retries=1)
        self.assertIsNone(result)
        self.assertTrue(self.mod._LAST_API_ERROR["throttled"])
        self.assertEqual(self.mod._LAST_API_ERROR["status"], 430)

    def test_body_throttle_codes_mark_throttled_on_non_throttle_status(self):
        # Some Fabric endpoints return throttle as 503 or 400 with the throttle
        # error code in the body. api() must still recognise these so the
        # rotation loop rotates instead of failing on a transient throttle.
        for status, body_code in [
            (503, "RequestThrottled"),
            (400, "BurstThrottle"),
            (500, "TooManyRequestsForCapacity"),
        ]:
            with self.subTest(status=status, body_code=body_code):
                self.mod._LAST_API_ERROR.update({"status": 0, "body": "", "throttled": False})
                body = f'{{"errorCode":"{body_code}","message":"throttled"}}'
                err = _make_http_error(status, body)
                with patch.object(self.mod, "urlopen", side_effect=err):
                    result = self.mod.api("post", "/workspaces", "token", body={}, retries=1)
                self.assertIsNone(result)
                self.assertTrue(self.mod._LAST_API_ERROR["throttled"],
                                f"status={status} body={body_code} should be throttle")
                self.assertEqual(self.mod._LAST_API_ERROR["status"], status)

    def test_body_throttle_code_match_is_case_insensitive(self):
        # If Fabric changes the casing of an error code (e.g. lowercases it),
        # api() must still recognise it as a throttle. Status code is 503 so
        # only the body-code path can trigger throttle detection.
        for variant in ["capacitylimitexceeded", "CAPACITYLIMITEXCEEDED", "CapacityLimitExceeded"]:
            with self.subTest(variant=variant):
                self.mod._LAST_API_ERROR.update({"status": 0, "body": "", "throttled": False})
                body = f'{{"errorCode":"{variant}","message":"throttled"}}'
                err = _make_http_error(503, body)
                with patch.object(self.mod, "urlopen", side_effect=err):
                    result = self.mod.api("post", "/workspaces", "token", body={}, retries=1)
                self.assertIsNone(result)
                self.assertTrue(self.mod._LAST_API_ERROR["throttled"],
                                f"body code variant {variant!r} should match case-insensitively")

    def test_retry_after_header_honored_over_exponential_backoff(self):
        # When the server provides a Retry-After header, api() must use it
        # instead of the default exponential backoff. This avoids over-waiting
        # when the server tells us exactly when capacity will be available.
        body = '{"errorCode":"CapacityLimitExceeded"}'
        sleep_args: list = []

        def fake_sleep(seconds):
            sleep_args.append(seconds)

        err_with_header = _make_http_error(429, body, headers={"Retry-After": "15"})
        with patch.object(self.mod, "urlopen", side_effect=err_with_header), \
             patch.object(self.mod.time, "sleep", side_effect=fake_sleep):
            result = self.mod.api("post", "/workspaces", "token", body={},
                                  retries=2, backoff=99)  # backoff=99 to distinguish from 15
        self.assertIsNone(result)
        # Server hint (15s) used once before retries=2 exhausts; exponential default would be 99s.
        self.assertEqual(sleep_args, [15])

    def test_retry_after_malformed_falls_back_to_exponential_backoff(self):
        # A non-integer Retry-After value (HTTP-date form, garbled, negative)
        # must NOT crash api() and must NOT be silently honored. Fall back to
        # the default exponential backoff so the retry still happens.
        body = '{"errorCode":"CapacityLimitExceeded"}'
        sleep_args: list = []

        def fake_sleep(seconds):
            sleep_args.append(seconds)

        for bad_value in ["Wed, 21 Oct 2026 07:28:00 GMT", "-5", "not-a-number", ""]:
            with self.subTest(retry_after=bad_value):
                sleep_args.clear()
                self.mod._LAST_API_ERROR.update({"status": 0, "body": "", "throttled": False})
                err = _make_http_error(429, body, headers={"Retry-After": bad_value})
                with patch.object(self.mod, "urlopen", side_effect=err), \
                     patch.object(self.mod.time, "sleep", side_effect=fake_sleep):
                    self.mod.api("post", "/workspaces", "token", body={},
                                 retries=2, backoff=7)
                # backoff=7, first retry attempt index 0 -> 7 * 2^0 = 7.
                self.assertEqual(sleep_args, [7],
                                 f"Retry-After={bad_value!r} should fall back to exponential")


class TransientBackend5xxRetryTests(unittest.TestCase):
    """Verify api() retries transient backend 5xx (e.g. PowerBISqlCommandTimeout)
    on a tighter independent budget from throttles, and that _LAST_API_ERROR
    surfaces the `transient` flag so the rotation loop can decide whether to
    rotate or fail loud."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_setup_module()

    def setUp(self):
        self.mod._LAST_API_ERROR.update({"status": 0, "body": "", "throttled": False, "transient": False})

    def test_is_transient_5xx_matches_powerbi_sql_command_timeout(self):
        # The exact error shape observed during multi-shard provisioning load
        # on 2026-06-03 (PR #301 shard run 26867322584): HTTP 500 with this
        # error code in the body. Pin the detection so a regression cannot
        # silently classify it as non-retriable.
        body = ('{"requestId":"cb544985-7a8e-4e62-9015-21f67a87e0ed",'
                '"errorCode":"PowerBISqlCommandTimeout",'
                '"message":"An error occurred while processing the operation",'
                '"isRetriable":false}')
        self.assertTrue(self.mod._is_transient_5xx(500, body))

    def test_is_transient_5xx_rejects_non_5xx_with_transient_code(self):
        # A 4xx body that happens to mention a transient code (e.g. a 400 bad
        # request that surfaces "PowerBISqlCommandTimeout" in a nested message)
        # must NOT trigger the transient retry path -- the status-code gate
        # closes the door first. 4xx is a client bug; retrying would mask it.
        # Use the ACTUAL active transient code in _TRANSIENT_BODY_CODES so
        # this test genuinely exercises the status gate, not a degenerate
        # "body doesn't match anyway" path.
        for status in [400, 401, 403, 404, 409]:
            with self.subTest(status=status):
                body = '{"errorCode":"PowerBISqlCommandTimeout"}'
                # Sanity: confirm the body WOULD match if status were 5xx, so
                # the rejection truly comes from the status-code gate.
                self.assertTrue(self.mod._is_transient_5xx(500, body),
                                "test invariant: body should match at 500")
                self.assertFalse(self.mod._is_transient_5xx(status, body),
                                 f"{status} with transient code must not classify as transient")

    def test_is_transient_5xx_rejects_plain_500_without_known_code(self):
        # 500 alone is not enough -- we only retry well-known transient codes
        # to avoid masking genuine backend bugs. Generic 500 falls through to
        # the existing "fail loud" path.
        body = '{"errorCode":"UnknownInternalFailure","message":"oops"}'
        self.assertFalse(self.mod._is_transient_5xx(500, body))

    def test_transient_5xx_triggers_retry_and_eventual_success(self):
        # First two attempts fail with PowerBISqlCommandTimeout; third
        # succeeds. api() must transparently return the success result.
        body = '{"errorCode":"PowerBISqlCommandTimeout","message":"timeout"}'
        responses = [
            _make_http_error(500, body),
            _make_http_error(500, body),
            FakeResponse(200, b'{"id": "ws_after_retry"}'),
        ]
        sleep_args: list = []

        def fake_urlopen(*a, **kw):
            r = responses.pop(0)
            if isinstance(r, HTTPError):
                raise r
            return r

        # Pin jitter to 1.0 (no-op multiplier) so the sleep schedule is
        # deterministic for the equality assertion below. Jitter behaviour
        # itself is verified by a dedicated test below.
        with patch.object(self.mod, "urlopen", side_effect=fake_urlopen), \
             patch.object(self.mod.time, "sleep", side_effect=lambda s: sleep_args.append(s)), \
             patch.object(self.mod.random, "uniform", return_value=1.0):
            result = self.mod.api("post", "/workspaces", "token", body={}, retries=1)
        self.assertEqual(result, {"id": "ws_after_retry"})
        # Two retries fired with the documented exponential backoff: 15s, 30s.
        self.assertEqual(sleep_args, [15, 30])
        # Success clears the transient flag.
        self.assertFalse(self.mod._LAST_API_ERROR["transient"])
        self.assertFalse(self.mod._LAST_API_ERROR["throttled"])
        self.assertEqual(self.mod._LAST_API_ERROR["status"], 200)

    def test_transient_5xx_exhausted_marks_transient_flag(self):
        # All 3 attempts (1 + 2 retries) fail. The "exhausted" final state
        # must mark transient=True so the rotation loop rotates to another
        # capacity instead of failing loud.
        body = '{"errorCode":"PowerBISqlCommandTimeout","message":"timeout"}'

        def make_err(*a, **kw):
            raise _make_http_error(500, body)

        with patch.object(self.mod, "urlopen", side_effect=make_err), \
             patch.object(self.mod.time, "sleep"):
            result = self.mod.api("post", "/workspaces", "token", body={}, retries=1)
        self.assertIsNone(result)
        self.assertTrue(self.mod._LAST_API_ERROR["transient"])
        self.assertFalse(self.mod._LAST_API_ERROR["throttled"])
        self.assertEqual(self.mod._LAST_API_ERROR["status"], 500)

    def test_transient_retry_budget_is_independent_of_throttle_retries(self):
        # Even if caller passes retries=10 (throttle budget), transient 5xx
        # is still capped at _MAX_TRANSIENT_RETRIES (default 2). This prevents
        # a long throttle budget from translating into 11 attempts on a
        # backend-timeout endpoint that is genuinely down.
        body = '{"errorCode":"PowerBISqlCommandTimeout"}'
        sleep_args: list = []

        def make_err(*a, **kw):
            raise _make_http_error(500, body)

        # Pin jitter to 1.0 so the sleep schedule is deterministic for the
        # equality assertion below.
        with patch.object(self.mod, "urlopen", side_effect=make_err), \
             patch.object(self.mod.time, "sleep", side_effect=lambda s: sleep_args.append(s)), \
             patch.object(self.mod.random, "uniform", return_value=1.0):
            self.mod.api("post", "/workspaces", "token", body={}, retries=10)
        # 2 retries (3 attempts total). Sleeps: 15s, 30s.
        self.assertEqual(len(sleep_args), self.mod._MAX_TRANSIENT_RETRIES)
        self.assertEqual(sleep_args, [15, 30])

    def test_transient_honors_retry_after_header_over_exponential_backoff(self):
        # Symmetric with the throttle Retry-After behaviour: when the server
        # provides Retry-After (RFC 7231 7.1.3 permits it on 503; Power BI
        # control-plane sometimes surfaces it on backend overload), api() must
        # honor it instead of the default jittered exponential backoff. Avoids
        # compounding pressure on a recovering backend by retrying faster than
        # asked.
        body = '{"errorCode":"PowerBISqlCommandTimeout"}'
        sleep_args: list = []

        # Build a FRESH HTTPError on each call. HTTPError reads its body from
        # a BytesIO buffer that is consumed on first read; reusing the same
        # instance would surface an empty body on attempt 2 and cause
        # _is_transient_5xx() to mis-classify the second response as a real
        # error (no retry).
        def make_err(*a, **kw):
            raise _make_http_error(500, body, headers={"Retry-After": "45"})

        with patch.object(self.mod, "urlopen", side_effect=make_err), \
             patch.object(self.mod.time, "sleep", side_effect=lambda s: sleep_args.append(s)), \
             patch.object(self.mod.random, "uniform", return_value=1.0):  # jitter pinned to no-op
            self.mod.api("post", "/workspaces", "token", body={}, retries=1)
        # Both retries used the server hint (45s) instead of jittered exp
        # (15s, 30s). Server hint takes precedence on every retry, not just
        # the first.
        self.assertEqual(sleep_args, [45, 45],
                         f"transient retry must honor Retry-After; got {sleep_args}")

    def test_transient_retry_after_cap_at_600_seconds(self):
        # Misbehaving endpoints sometimes return Retry-After: 86400 (24h),
        # which would blow the shard timeout budget. Symmetric with the
        # throttle cap, the transient branch caps at 600s (10 min).
        body = '{"errorCode":"PowerBISqlCommandTimeout"}'
        sleep_args: list = []

        def make_err(*a, **kw):
            raise _make_http_error(500, body, headers={"Retry-After": "86400"})

        with patch.object(self.mod, "urlopen", side_effect=make_err), \
             patch.object(self.mod.time, "sleep", side_effect=lambda s: sleep_args.append(s)):
            self.mod.api("post", "/workspaces", "token", body={}, retries=1)
        self.assertEqual(sleep_args, [600, 600],
                         f"transient Retry-After must cap at 600s; got {sleep_args}")

    def test_transient_jitter_applied_when_no_retry_after(self):
        # When no server hint, each retry wait is randomised within
        # +/-20% of the exponential baseline so N shards hitting the same
        # transient error do not retry in lockstep. The thundering-herd
        # mitigation is the explicit goal of the jitter; pin the contract.
        #
        # Mock random.uniform to return a known non-1.0 value and verify the
        # sleep was scaled by it (not just the unmocked baseline). Two
        # assertions catch both "jitter not applied at all" and "jitter
        # multiplier hardcoded to 1.0".
        body = '{"errorCode":"PowerBISqlCommandTimeout"}'
        sleep_args: list = []

        # First retry: uniform returns 1.2 -> wait = 15 * 1.2 = 18s
        # Second retry: uniform returns 0.8 -> wait = 30 * 0.8 = 24s
        uniform_returns = iter([1.2, 0.8])

        def make_err(*a, **kw):
            raise _make_http_error(500, body)

        with patch.object(self.mod, "urlopen", side_effect=make_err), \
             patch.object(self.mod.time, "sleep", side_effect=lambda s: sleep_args.append(s)), \
             patch.object(self.mod.random, "uniform", side_effect=lambda lo, hi: next(uniform_returns)):
            self.mod.api("post", "/workspaces", "token", body={}, retries=1)
        self.assertEqual(sleep_args, [18, 24],
                         f"jitter not applied to transient backoff; got {sleep_args}")

    def test_transient_jitter_bounds_within_20_percent(self):
        # Stress-test the jitter range. Across N invocations, every observed
        # sleep value must be within +/-20% of the baseline. Catches a
        # regression that widens the jitter (e.g. random.uniform(0.5, 1.5)
        # would let waits drift into a range that disrupts the documented
        # ~45s worst-case budget).
        body = '{"errorCode":"PowerBISqlCommandTimeout"}'

        def make_err(*a, **kw):
            raise _make_http_error(500, body)

        observed_first_retry = []
        for _ in range(50):
            self.mod._LAST_API_ERROR.update({"status": 0, "body": "", "throttled": False, "transient": False})
            sleeps: list = []
            with patch.object(self.mod, "urlopen", side_effect=make_err), \
                 patch.object(self.mod.time, "sleep", side_effect=lambda s: sleeps.append(s)):
                self.mod.api("post", "/workspaces", "token", body={}, retries=1)
            observed_first_retry.append(sleeps[0])
        baseline = self.mod._TRANSIENT_BACKOFF_BASE  # 15
        # Allow inclusive bounds at 0.8*15=12 and 1.2*15=18.
        for s in observed_first_retry:
            self.assertGreaterEqual(s, int(baseline * 0.8),
                                    f"jittered wait {s}s below baseline*0.8={baseline*0.8}s")
            self.assertLessEqual(s, int(baseline * 1.2),
                                 f"jittered wait {s}s above baseline*1.2={baseline*1.2}s")

    def test_throttle_takes_precedence_over_transient_when_both_match(self):
        # A 500 body containing BOTH a throttle code (TooManyRequestsForCapacity)
        # AND a transient code (PowerBISqlCommandTimeout) is theoretically
        # possible if a Fabric endpoint surfaces a throttle that was triggered
        # by a backend timeout. Both helpers would return True independently.
        # api() must classify it as throttle (longer retry budget, 5 attempts)
        # rather than transient (shorter budget, 3 attempts), because throttles
        # legitimately persist for minutes. Pin that ordering so a future
        # re-ordering of the checks does not silently shorten the retry budget
        # for these cases.
        #
        # The retries=5 + sleep-count assertion is what actually pins the
        # budget delta: a precedence inversion would deliver 2 sleeps
        # (transient budget) instead of 4 (throttle budget). retries=1 would
        # only verify the flag, missing the budget regression entirely.
        body = ('{"errorCode":"TooManyRequestsForCapacity",'
                '"message":"Backend response: PowerBISqlCommandTimeout occurred during throttle"}')
        # Sanity: confirm both helpers DO match this body so the test actually
        # exercises the precedence path rather than a degenerate single-match case.
        self.assertTrue(self.mod._is_throttle(500, body))
        self.assertTrue(self.mod._is_transient_5xx(500, body))

        sleeps: list = []

        def make_err(*a, **kw):
            raise _make_http_error(500, body)

        with patch.object(self.mod, "urlopen", side_effect=make_err), \
             patch.object(self.mod.time, "sleep", side_effect=lambda s: sleeps.append(s)):
            self.mod.api("post", "/workspaces", "token", body={}, retries=5)
        self.assertTrue(self.mod._LAST_API_ERROR["throttled"])
        self.assertFalse(self.mod._LAST_API_ERROR["transient"])
        # Throttle budget (5 attempts) -> 4 sleeps. Transient budget
        # (_MAX_TRANSIENT_RETRIES + 1 = 3 attempts) would give 2 sleeps. The
        # delta is the real precedence assertion.
        self.assertEqual(len(sleeps), 4,
                         f"must use throttle budget (4 sleeps), got {len(sleeps)} -- "
                         f"a transient classification would deliver "
                         f"{self.mod._MAX_TRANSIENT_RETRIES} sleeps")


class WorkspaceCreateRotateOnTransientTests(unittest.TestCase):
    """Verify main()'s capacity-rotation loop also rotates on transient backend
    5xx (not just throttle). Covers the user-facing payoff of the transient
    retry feature: when a transient error exhausts in-call retries on capacity
    A, main() must try capacity B before failing loud. A typo (e.g. "transient_"
    vs "transient", or an accidental "and" between the throttle/transient
    branches) would silently regress this behaviour and not be caught by the
    api()-level tests above."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_setup_module()

    def setUp(self):
        self.mod._LAST_API_ERROR.update({"status": 0, "body": "", "throttled": False, "transient": False})

    def _read_source(self) -> str:
        return SCRIPT_PATH.read_text(encoding="utf-8")

    def test_workspace_create_rotates_on_transient(self):
        # Pin the source-level shape rather than executing main() end-to-end
        # (main() needs az login, capacity discovery, real argparse, etc.).
        # Two assertions:
        #   1. The workspace-create branch contains BOTH a throttle check AND
        #      a transient check that `continue` to the next capacity.
        #   2. The non-rotate exit message no longer says "non-throttle"
        #      (would imply transient errors fall through to the exit branch).
        # Use unique anchors (the print() lines, not the bare "Step N:" string
        # which appears in BOTH the comment and the print statement) so the
        # split correctly extracts the rotation block.
        src = self._read_source()
        ws_block = (
            src.split('print(f"=== Step 3: Create workspace')[1]
               .split('# Step 4: Create lakehouse')[0]
        )
        self.assertIn('_LAST_API_ERROR.get("throttled")', ws_block,
                      "workspace-create branch must check throttled flag for rotation")
        self.assertIn('_LAST_API_ERROR.get("transient")', ws_block,
                      "workspace-create branch must check transient flag for rotation "
                      "(otherwise transient backend errors fail loud instead of rotating)")
        # The `continue` keyword should appear at least twice in this block:
        # once for throttle, once for transient.
        self.assertGreaterEqual(
            ws_block.count("continue"), 2,
            "workspace-create branch should have at least two `continue` statements "
            "(throttle path + transient path) for capacity rotation")
        # Non-retriable exit message should be "non-retriable", not "non-throttle"
        # (the latter wording would imply only throttles trigger rotation).
        self.assertIn("non-retriable error", ws_block,
                      "exit message should say 'non-retriable error' to reflect "
                      "that both throttle AND transient trigger rotation; only "
                      "real client errors (auth/payload) hit the exit branch")
        self.assertNotIn("non-throttle error", ws_block,
                         "exit message wording 'non-throttle error' was the pre-PR "
                         "shape; should be 'non-retriable error' now")

    def test_lakehouse_create_rotates_on_transient(self):
        # Same shape assertion for the lakehouse-create branch ~80 lines below
        # the workspace-create branch in main(). Critical: the condition is
        # `not (throttled OR transient)` -- a typo to `not throttled AND not
        # transient` would have different short-circuit semantics, and a typo
        # to `not throttled OR transient` would always exit (since transient
        # is False on success). The text assertion below catches all three
        # mis-typings.
        src = self._read_source()
        lh_block = (
            src.split('print(f"=== Step 4: Create lakehouse')[1]
               .split("if not workspace_id or not lakehouse_id")[0]
        )
        self.assertIn('_LAST_API_ERROR.get("throttled")', lh_block)
        self.assertIn('_LAST_API_ERROR.get("transient")', lh_block)
        # The exact rotation-guard shape: `not (throttled OR transient)`.
        # Match flexibly across whitespace.
        import re
        guard_rx = re.compile(
            r'not\s*\(\s*_LAST_API_ERROR\.get\("throttled"\)\s+or\s+'
            r'_LAST_API_ERROR\.get\("transient"\)\s*\)',
            re.DOTALL
        )
        self.assertRegex(lh_block, guard_rx,
                         "lakehouse-create exit guard must be `not (throttled OR transient)` "
                         "so transient errors trigger rotation (continue), not exit")


class CapacityRotationStartIndexTests(unittest.TestCase):
    """Verify the hash-based start-index rotation is deterministic per workspace name."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_setup_module()

    def test_start_index_within_bounds(self):
        # For 6 candidate capacities, every workspace name should yield
        # a start index in [0, 6).
        import hashlib
        for name in ["smoke-2026-05-25-aaaa", "smoke-2026-05-25-bbbb",
                     "smoke-2026-05-25-cccc", "FullEval-20260525091607"]:
            idx = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % 6
            self.assertGreaterEqual(idx, 0)
            self.assertLess(idx, 6)

    def test_start_index_deterministic(self):
        # Same workspace name must always pick the same start index, so a
        # re-run of a failed harness picks the same capacity (predictable).
        import hashlib
        name = "smoke-2026-05-25-aaaa"
        idx1 = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % 6
        idx2 = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % 6
        self.assertEqual(idx1, idx2)


class CapacityIdOverrideTests(unittest.TestCase):
    """Verify --capacity-id wiring: argparse accepts the flag, and the source
    contains the override branch that bypasses /capacities discovery.

    Why both:
        The argparse check proves the wrappers can call
            python setup_test_env.py --capacity-id <guid>
        without an "unrecognized arguments" failure (the failure mode if PR
        #263's flag is reverted by a future rebase).
        The source-level check proves the branch that USES args.capacity_id
        still exists and still bypasses the discovery API call. These two
        together cover the contract that run-smoke-tests.ps1 / run-full-tests.ps1
        and the fabric-smoke-ephemeral.yml / fabric-full-eval-ephemeral.yml
        workflows rely on when FABRIC_CAPACITY_ID is set.
    """

    def test_argparse_accepts_capacity_id_flag(self):
        # Use --help (which exits 0 and prints usage) to confirm argparse
        # has the flag wired. Avoids refactoring main() just for the test.
        import subprocess
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, msg=f"--help exited {result.returncode}: {result.stderr}")
        self.assertIn("--capacity-id", result.stdout,
                      msg="--capacity-id flag is missing from argparse; wrappers will break.")

    def test_source_has_capacity_id_override_branch(self):
        # Read the source verbatim and assert the override branch is intact.
        # If this test fails, the workflows that pass FABRIC_CAPACITY_ID will
        # silently fall back to discovery (which is what the pin tries to avoid).
        # We assert on the STRUCTURAL assignment (not the human-readable
        # displayName marker) so a harmless rewording of the marker text does
        # not break CI -- only a real behavioral change does.
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn("if args.capacity_id:", source,
                      msg="The args.capacity_id override branch is missing from setup_test_env.py.")
        self.assertIn('candidate_capacities = [{"id": args.capacity_id',
                      source,
                      msg="The pinned-capacity assignment "
                          "(candidate_capacities = [{\"id\": args.capacity_id, ...}]) is missing; "
                          "rotation may not be disabled on the pinned path.")


class WorkspaceNameSuffixTests(unittest.TestCase):
    """Verify --name-suffix wiring so the vally smoke matrix can give each
    shard a unique workspace name.

    Why:
        CI run 26707615444 shard 3 failed at provisioning with HTTP 409
        WorkspaceNameAlreadyExists because all 5 shards call setup_test_env.py
        within a 1-3s window and the workspace name is generated from
        strftime('%Y%m%d-%H%M%S') -- single-second resolution collides. The
        --name-suffix arg (default empty) lets each shard request a unique
        name (-shard0, -shard1, ...) without changing the legacy single
        workspace harness. These tests pin both the suffix and default-empty
        contracts.
    """

    @classmethod
    def setUpClass(cls):
        cls.mod = load_setup_module()

    def _run_dry_run(self, argv_extra):
        """Run main() in --dry-run with a pinned timestamp; return printed lines."""
        argv = ["setup_test_env.py", "--tenant", "foo", "--dry-run"] + argv_extra
        captured = io.StringIO()
        fake_datetime = unittest.mock.MagicMock()
        fake_datetime.now.return_value.strftime.return_value = "FIXED"
        with patch.object(self.mod, "datetime", fake_datetime), \
             patch.object(sys, "argv", argv), \
             patch("sys.stdout", captured):
            self.mod.main()
        return captured.getvalue()

    def test_name_suffix_appended_to_workspace_name(self):
        # The vally workflow passes the suffix in --opt=value form because the
        # value starts with '-' (e.g. -shard0); argparse would otherwise treat
        # it as an unknown flag. Pin that exact invocation shape.
        out = self._run_dry_run(["--name-suffix=-shardX"])
        self.assertIn("Workspace: skills-for-fabric-test-FIXED-shardX", out)

    def test_default_empty_suffix_preserves_legacy_name(self):
        out = self._run_dry_run([])
        self.assertIn("Workspace: skills-for-fabric-test-FIXED", out)
        self.assertNotIn("skills-for-fabric-test-FIXED-", out)


class FailingNotebookFixtureTests(unittest.TestCase):
    """Cover the spark_operations_failing_notebook fixture helpers (Bucket 1)
    that feed the spark-operations 'Diagnose failed notebook run' eval."""

    @classmethod
    def setUpClass(cls):
        cls.mod = load_setup_module()

    def test_failing_notebook_ipynb_raises_documented_runtime_error(self):
        doc = json.loads(
            self.mod._build_failing_notebook_ipynb("ws1", "lh1", "Lakehouse1"))
        self.assertEqual(doc["nbformat"], 4)
        self.assertEqual(len(doc["cells"]), 1)
        source = "".join(doc["cells"][0]["source"])
        # The error message is the documented SO-01 pass-criteria string; the
        # diagnose-failed-notebook evals look for it in the agent's output.
        self.assertIn("raise RuntimeError('spark operations eval failure')", source)
        self.assertIn("spark.range(1).count()", source)

    def test_failing_notebook_attaches_lakehouse_when_provided(self):
        doc = json.loads(
            self.mod._build_failing_notebook_ipynb("ws1", "lh1", "Lakehouse1"))
        trident = doc["metadata"]["trident"]["lakehouse"]
        self.assertEqual(trident["default_lakehouse"], "lh1")
        self.assertEqual(trident["default_lakehouse_name"], "Lakehouse1")
        self.assertEqual(trident["default_lakehouse_workspace_id"], "ws1")
        self.assertEqual(trident["known_lakehouses"], [{"id": "lh1"}])

    def test_failing_notebook_omits_trident_without_lakehouse(self):
        doc = json.loads(
            self.mod._build_failing_notebook_ipynb("ws1", None, None))
        self.assertNotIn("trident", doc["metadata"])

    def test_start_notebook_run_returns_location_on_202(self):
        loc = "https://api.fabric.microsoft.com/v1/workspaces/ws1/items/nb1/jobs/instances/abc-123"
        resp = FakeResponse(202, b"", headers={"Location": loc})
        with patch.object(self.mod, "urlopen", return_value=resp):
            result = self.mod._start_notebook_run("ws1", "nb1", "token")
        self.assertEqual(result, loc)

    def test_start_notebook_run_retries_throttle_then_succeeds(self):
        loc = "https://poll/instances/1"
        throttled = _make_http_error(429, '{"error":"throttled"}',
                                     headers={"Retry-After": "1"})
        ok = FakeResponse(202, b"", headers={"Location": loc})
        sleeps: list = []
        with patch.object(self.mod, "urlopen", side_effect=[throttled, ok]), \
             patch.object(self.mod.time, "sleep", side_effect=lambda s: sleeps.append(s)), \
             patch("sys.stderr", io.StringIO()):
            result = self.mod._start_notebook_run("ws1", "nb1", "token")
        self.assertEqual(result, loc)
        self.assertEqual(sleeps, [1])  # honored Retry-After

    def test_start_notebook_run_ignores_negative_retry_after(self):
        # A negative Retry-After must not reach time.sleep (which would raise
        # ValueError); _parse_retry_after_seconds rejects it and we fall back to
        # exponential backoff, keeping the kick-off non-fatal.
        loc = "https://poll/instances/1"
        throttled = _make_http_error(429, "{}", headers={"Retry-After": "-1"})
        ok = FakeResponse(202, b"", headers={"Location": loc})
        sleeps: list = []
        with patch.object(self.mod, "urlopen", side_effect=[throttled, ok]), \
             patch.object(self.mod.time, "sleep", side_effect=lambda s: sleeps.append(s)), \
             patch("sys.stderr", io.StringIO()):
            result = self.mod._start_notebook_run("ws1", "nb1", "token", backoff=15)
        self.assertEqual(result, loc)
        self.assertEqual(sleeps, [15])  # fell back to backoff*2**0, not sleep(-1)

    def test_start_notebook_run_gives_up_after_retries(self):
        calls = {"n": 0}

        def always_503(req):
            calls["n"] += 1
            raise _make_http_error(503, "{}")

        with patch.object(self.mod, "urlopen", side_effect=always_503), \
             patch.object(self.mod.time, "sleep", lambda s: None), \
             patch("sys.stderr", io.StringIO()):
            result = self.mod._start_notebook_run("ws1", "nb1", "token", retries=3)
        self.assertIsNone(result)
        self.assertEqual(calls["n"], 3)  # initial + 2 retries, then give up

    def test_start_notebook_run_does_not_retry_non_transient(self):
        calls = {"n": 0}

        def always_403(req):
            calls["n"] += 1
            raise _make_http_error(403, '{"error":"Forbidden"}')

        with patch.object(self.mod, "urlopen", side_effect=always_403), \
             patch("sys.stderr", io.StringIO()):
            result = self.mod._start_notebook_run("ws1", "nb1", "token")
        self.assertIsNone(result)
        self.assertEqual(calls["n"], 1)  # 403 is permanent, no retry

    def test_start_notebook_run_returns_none_without_location(self):
        resp = FakeResponse(202, b"", headers={})
        with patch.object(self.mod, "urlopen", return_value=resp), \
             patch("sys.stderr", io.StringIO()):
            result = self.mod._start_notebook_run("ws1", "nb1", "token")
        self.assertIsNone(result)

    def test_start_notebook_run_swallows_http_error(self):
        err = _make_http_error(403, '{"error":"Forbidden"}')
        with patch.object(self.mod, "urlopen", side_effect=err), \
             patch("sys.stderr", io.StringIO()):
            result = self.mod._start_notebook_run("ws1", "nb1", "token")
        self.assertIsNone(result)

    def test_await_failing_run_returns_failed_status(self):
        resp = FakeResponse(200, b'{"status": "Failed"}')
        with patch.object(self.mod, "urlopen", return_value=resp):
            status = self.mod._await_failing_run(
                "https://poll/instances/1", "token", timeout=30, interval=1)
        self.assertEqual(status, "Failed")

    def test_await_failing_run_times_out_returns_none(self):
        resp = FakeResponse(200, b'{"status": "InProgress"}')
        sleeps: list = []
        with patch.object(self.mod, "urlopen", return_value=resp), \
             patch.object(self.mod.time, "sleep", side_effect=lambda s: sleeps.append(s)):
            status = self.mod._await_failing_run(
                "https://poll/instances/1", "token", timeout=3, interval=1)
        self.assertIsNone(status)
        self.assertGreaterEqual(len(sleeps), 1)

    def test_await_failing_run_none_url_returns_none(self):
        self.assertIsNone(self.mod._await_failing_run(None, "token"))

    def test_provision_resolves_real_id_when_lro_returns_operation_payload(self):
        # api_lro can return the LRO operation payload (operation id, no
        # type=Notebook) instead of the created item; the run must target the
        # real notebook id resolved by display name, not the operation id.
        started_with = {}

        def fake_start(ws, nb_id, tok):
            started_with["id"] = nb_id
            return "https://poll/instances/1"

        with patch.object(self.mod, "api_lro",
                          return_value={"id": "operation-id", "status": "Succeeded"}), \
             patch.object(self.mod, "api", return_value={"value": [
                 {"displayName": self.mod.FAILING_NOTEBOOK_NAME, "id": "real-nb-id"}]}), \
             patch.object(self.mod, "_start_notebook_run", side_effect=fake_start), \
             patch("sys.stdout", io.StringIO()):
            result = self.mod._provision_failing_notebook("ws1", "token")
        self.assertEqual(started_with.get("id"), "real-nb-id")
        self.assertEqual(result, "https://poll/instances/1")

    def test_provision_returns_none_when_api_lro_raises(self):
        # A transport/parse error in api_lro must not abort env setup.
        with patch.object(self.mod, "api_lro", side_effect=RuntimeError("boom")), \
             patch("sys.stderr", io.StringIO()):
            result = self.mod._provision_failing_notebook("ws1", "token")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
