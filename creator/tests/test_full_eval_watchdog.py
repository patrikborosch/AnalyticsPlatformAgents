"""Unit tests for the full-eval per-plan watchdog decision logic.

The watchdog lives in ``tests/copilot-invoke.ps1`` (``Get-CopilotWatchdogVerdict``)
and decides when a single Copilot plan invocation should be terminated. The
design intent is that a healthy-but-slow plan is NEVER cut: the cut fires only
on SUSTAINED inactivity (no run-log growth for the stall window) or a generous
absolute ceiling -- never on a flat wall-clock timer. These tests pin that
contract so a future refactor cannot silently reintroduce a premature cut.

The verdict function is pure PowerShell, so we exercise it by shelling to
``pwsh``. The test skips (does not fail) when pwsh is unavailable, so Linux
contributors without PowerShell are not blocked; CI runs it on the
PowerShell-equipped runners.

Run with: python -m unittest tests/test_full_eval_watchdog.py -v
"""

from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
INVOKE_PS1 = REPO_ROOT / "tests" / "copilot-invoke.ps1"
PWSH = shutil.which("pwsh") or shutil.which("powershell")


def _run_verdict(idle_seconds: float, elapsed_seconds: float, stall_seconds: int, ceiling_seconds: int) -> dict:
    """Invoke Get-CopilotWatchdogVerdict via pwsh and return its result object."""
    ps = (
        f". '{INVOKE_PS1.as_posix()}'; "
        f"$v = Get-CopilotWatchdogVerdict -IdleSeconds {idle_seconds} "
        f"-ElapsedSeconds {elapsed_seconds} -StallSeconds {stall_seconds} "
        f"-CeilingSeconds {ceiling_seconds}; "
        # Emit a stable JSON shape regardless of $null Reason/Code.
        "[pscustomobject]@{ TimedOut = [bool]$v.TimedOut; "
        "Reason = [string]$v.Reason; Code = [string]$v.Code } | ConvertTo-Json -Compress"
    )
    proc = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command", ps],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise AssertionError(f"pwsh verdict call failed (rc={proc.returncode}):\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}")
    # ConvertTo-Json may print a banner-free single line; take the last JSON line.
    # Guard the no-JSON case explicitly: a rc=0 run that emitted only
    # non-terminating errors to stderr would otherwise raise a bare IndexError
    # that hides the real pwsh output.
    json_lines = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")]
    if not json_lines:
        raise AssertionError(
            "pwsh verdict call returned no JSON payload (rc=0).\n"
            f"STDOUT:{proc.stdout}\nSTDERR:{proc.stderr}"
        )
    return json.loads(json_lines[-1])


@unittest.skipUnless(PWSH, "pwsh/powershell not available on this host")
class WatchdogVerdictTests(unittest.TestCase):
    STALL = 1200    # 20 min idle window
    CEILING = 3600  # 60 min hard ceiling

    def test_active_session_is_not_cut(self):
        v = _run_verdict(30, 60, self.STALL, self.CEILING)
        self.assertFalse(v["TimedOut"], "an active session (recent log growth) must never be cut")

    def test_just_under_stall_is_not_cut(self):
        # One second below the stall window -> still healthy. Guards against an
        # off-by-one that would cut a plan a tick early.
        v = _run_verdict(self.STALL - 1, self.STALL - 1, self.STALL, self.CEILING)
        self.assertFalse(v["TimedOut"])

    def test_sustained_silence_cuts_as_stall(self):
        v = _run_verdict(self.STALL, self.STALL, self.STALL, self.CEILING)
        self.assertTrue(v["TimedOut"])
        self.assertEqual(v["Reason"], "stall")
        self.assertEqual(v["Code"], "EVAL-TIMEOUT-001")

    def test_hard_ceiling_cuts_even_when_active(self):
        # Busy-loop backstop: log keeps growing (idle small) but total runtime
        # exceeds the ceiling.
        v = _run_verdict(10, self.CEILING, self.STALL, self.CEILING)
        self.assertTrue(v["TimedOut"])
        self.assertEqual(v["Reason"], "ceiling")
        self.assertEqual(v["Code"], "EVAL-TIMEOUT-002")

    def test_stall_takes_precedence_over_ceiling(self):
        v = _run_verdict(self.STALL + 100, self.CEILING + 400, self.STALL, self.CEILING)
        self.assertEqual(v["Code"], "EVAL-TIMEOUT-001")

    def test_stall_arm_can_be_disabled(self):
        # StallSeconds <= 0 disables the idle check; only the ceiling applies.
        v = _run_verdict(99999, 100, 0, self.CEILING)
        self.assertFalse(v["TimedOut"])

    def test_ceiling_still_applies_when_stall_disabled(self):
        v = _run_verdict(99999, self.CEILING, 0, self.CEILING)
        self.assertTrue(v["TimedOut"])
        self.assertEqual(v["Code"], "EVAL-TIMEOUT-002")


if __name__ == "__main__":
    unittest.main()
