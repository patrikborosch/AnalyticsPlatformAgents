"""Integration tests for native Vally MCP staging.

Exercises `tests/run-vally-eval.ps1` in `-DryRun` mode (stages eval.yaml
files to `tests/.vally-staging/` and exits before Vally starts) to verify
the CI MCP overlay behaviour the wrapper inherits from Option C:

  - Local dev (CI_MCP_OVERLAY unset): staged eval.yaml keeps the
    interactive args, no --authmode=serviceprincipal, no AZURE_* env block.
  - CI mode + valid SP env: staged eval.yaml gains
    --authmode=serviceprincipal --skipconfirmation + AZURE_* env block.
  - CI mode + missing cert: wrapper fails fast before any vally process
    spawns; error mentions AZURE_CLIENT_CERTIFICATE_PATH.
  - CI mode + non-MCP eval: staging completes cleanly even when the AZURE_*
    env vars are absent, because the helper is a no-op on evals without
    powerbi-modeling-mcp.

The wrapper needs Node 22+ even in -DryRun (it node-checks before staging).
Tests skip cleanly when Node is unavailable or the wrong version.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = REPO_ROOT / "tests" / "run-vally-eval.ps1"
STAGING_DIR = REPO_ROOT / "tests" / ".vally-staging"


def _node_22_plus() -> bool:
    try:
        out = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    if out.returncode != 0:
        return False
    ver = out.stdout.strip().lstrip("v")
    try:
        major = int(ver.split(".")[0])
    except (ValueError, IndexError):
        return False
    return major >= 22


def _which_pwsh() -> str | None:
    # Intentionally NOT falling back to Windows PowerShell 5.1 ('powershell'):
    # tests/run-vally-eval.ps1 uses PowerShell 7+ syntax (param attributes, -e
    # expansion in here-strings, etc.) and will fail to parse under 5.1. Boxes
    # without pwsh installed should SKIP this test, not run it against a wrong
    # interpreter.
    return shutil.which("pwsh")


def _run_wrapper(env_overrides: dict, skill: str) -> subprocess.CompletedProcess:
    pwsh = _which_pwsh()
    assert pwsh is not None
    env = dict(os.environ)
    # Wipe any inherited CI_MCP_OVERLAY / AZURE_* so each test sees a clean slate.
    for k in ("CI_MCP_OVERLAY", "AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_CERTIFICATE_PATH"):
        env.pop(k, None)
    env.update(env_overrides)
    return subprocess.run(
        [
            pwsh, "-NoLogo", "-NoProfile",
            "-File", str(WRAPPER),
            "-Workspace", "native-mcp-test",
            "-Skill", skill,
            "-DryRun",
        ],
        capture_output=True, text=True, cwd=str(REPO_ROOT), env=env, timeout=120,
    )


@unittest.skipUnless(_which_pwsh() and _node_22_plus(),
                     "pwsh + Node 22+ required (wrapper node-checks before staging)")
class VallyNativeMcpStagingTests(unittest.TestCase):
    """End-to-end staging behavior. See module docstring for the 4 scenarios."""

    @classmethod
    def setUpClass(cls):
        if STAGING_DIR.exists():
            shutil.rmtree(STAGING_DIR)

    def tearDown(self):
        if STAGING_DIR.exists():
            shutil.rmtree(STAGING_DIR, ignore_errors=True)

    def _staged_content(self, skill: str) -> str:
        path = STAGING_DIR / skill / "eval.yaml"
        self.assertTrue(path.exists(), f"Expected staged eval at {path}; got stdout/stderr in prior assert")
        return path.read_text(encoding="utf-8")

    def test_local_dev_keeps_interactive_mcp(self):
        """No CI_MCP_OVERLAY -> committed YAML staged unchanged."""
        r = _run_wrapper({}, "semantic-model-authoring")
        self.assertEqual(r.returncode, 0, f"wrapper exited {r.returncode}; stderr=\n{r.stderr}")
        c = self._staged_content("semantic-model-authoring")
        self.assertIn("powerbi-modeling-mcp", c)
        self.assertIn("--start", c)
        self.assertNotIn("--authmode=serviceprincipal", c,
                         "local-dev path must NOT inject SP cert auth args")
        self.assertNotIn("--skipconfirmation", c)
        self.assertNotIn("AZURE_CLIENT_ID", c,
                         "local-dev path must NOT inject AZURE_* env block")

    def test_ci_mode_injects_sp_auth_for_mcp_eval(self):
        """CI_MCP_OVERLAY=true + valid env -> staged YAML gains SP args + env block."""
        with tempfile.TemporaryDirectory() as td:
            cert_path = Path(td) / "cert.pem"
            cert_path.write_text("dummy-cert-bytes", encoding="utf-8")
            r = _run_wrapper(
                {
                    "CI_MCP_OVERLAY": "true",
                    "AZURE_CLIENT_ID": "app-id-9999",
                    "AZURE_TENANT_ID": "tenant-id-8888",
                    "AZURE_CLIENT_CERTIFICATE_PATH": str(cert_path),
                },
                "semantic-model-authoring",
            )
            self.assertEqual(r.returncode, 0, f"wrapper exited {r.returncode}; stderr=\n{r.stderr}")
            c = self._staged_content("semantic-model-authoring")
            self.assertIn("--authmode=serviceprincipal", c)
            self.assertIn("--skipconfirmation", c)
            self.assertIn("AZURE_CLIENT_ID: 'app-id-9999'", c)
            self.assertIn("AZURE_TENANT_ID: 'tenant-id-8888'", c)
            self.assertIn("AZURE_CLIENT_CERTIFICATE_PATH:", c)
            # The exact cert path should appear (single-quoted by the YAML helper)
            self.assertIn(str(cert_path), c.replace("''", "'"))

    def test_ci_mode_missing_cert_fails_for_mcp_eval(self):
        """CI_MCP_OVERLAY=true + cert path that does not exist -> wrapper fails fast."""
        r = _run_wrapper(
            {
                "CI_MCP_OVERLAY": "true",
                "AZURE_CLIENT_ID": "app-id",
                "AZURE_TENANT_ID": "tenant-id",
                "AZURE_CLIENT_CERTIFICATE_PATH": "/definitely/does/not/exist/cert.pem",
            },
            "semantic-model-authoring",
        )
        self.assertNotEqual(r.returncode, 0,
                            f"wrapper should have failed; stdout=\n{r.stdout}\nstderr=\n{r.stderr}")
        self.assertIn("AZURE_CLIENT_CERTIFICATE_PATH", r.stderr + r.stdout,
                      "error message should name AZURE_CLIENT_CERTIFICATE_PATH")

    def test_ci_mode_non_mcp_eval_does_not_require_env(self):
        """CI_MCP_OVERLAY=true on an eval without powerbi-modeling-mcp -> no-op,
        no AZURE_* required, wrapper succeeds and stages the eval unchanged.
        """
        r = _run_wrapper(
            {"CI_MCP_OVERLAY": "true"},  # no AZURE_* env at all
            "eventhouse-consumption-cli",
        )
        self.assertEqual(r.returncode, 0,
                         f"wrapper should have succeeded for non-MCP eval; stderr=\n{r.stderr}")
        c = self._staged_content("eventhouse-consumption-cli")
        self.assertNotIn("powerbi-modeling-mcp", c)
        self.assertNotIn("AZURE_CLIENT_ID", c)


class VallyMcpArgsContractTests(unittest.TestCase):
    """Node-free contract pins for the canonical powerbi-modeling-mcp args
    block that tests/run-vally-eval.ps1 exact-matches before injecting the CI
    service-principal auth overlay (Add-CiPowerBiMcpAuthToStagedEval).

    The wrapper rewrites a staged eval.yaml by an exact-string Replace of the
    interactive args block with the SP-auth block. If a committed eval reformats
    that block (indent / quote-style / flag order / re-flow to inline YAML), the
    Replace would silently no-op and the CI run would execute WITHOUT auth -- so
    the wrapper throws instead. The behaviour tests above exercise that throw
    end-to-end but SKIP when Node 22+ is unavailable. These tests give the same
    contract a fast local signal with no Node/pwsh dependency by pinning:

      1. Every eval that declares powerbi-modeling-mcp carries the canonical
         args block verbatim, so the wrapper's exact-match Replace fires.
      2. The wrapper's canonical block still has the expected shape (catches an
         accidental empty / truncated here-string capture).
      3. The mismatch branch THROWS (hard fail), never soft-returns the content
         unchanged -- a soft return would drop the overlay and run CI
         unauthenticated, the exact silent-failure mode Avi flagged.
    """

    WRAPPER = REPO_ROOT / "tests" / "run-vally-eval.ps1"
    EVALS_DIR = REPO_ROOT / "tests" / "evals"

    @classmethod
    def setUpClass(cls):
        cls.wrapper_text = cls.WRAPPER.read_text(encoding="utf-8")
        m = re.search(r"\$baseArgs = @'\r?\n(.*?)\r?\n'@", cls.wrapper_text, re.DOTALL)
        assert m, "Could not locate the $baseArgs here-string in run-vally-eval.ps1"
        cls.canonical_block = m.group(1).replace("\r\n", "\n")

    def _mcp_evals(self) -> list[Path]:
        return [
            p
            for p in sorted(self.EVALS_DIR.glob("*/eval.yaml"))
            if "powerbi-modeling-mcp" in p.read_text(encoding="utf-8")
        ]

    def test_at_least_one_mcp_eval_exists(self):
        self.assertTrue(
            self._mcp_evals(),
            "No eval.yaml declares powerbi-modeling-mcp; the contract tests "
            "below would vacuously pass. If the native-MCP cutover was reverted, "
            "remove these tests with it.",
        )

    def test_every_mcp_eval_carries_canonical_args_block(self):
        for path in self._mcp_evals():
            with self.subTest(eval=str(path.relative_to(REPO_ROOT))):
                content = path.read_text(encoding="utf-8").replace("\r\n", "\n")
                self.assertIn(
                    self.canonical_block,
                    content,
                    f"{path.relative_to(REPO_ROOT)} declares powerbi-modeling-mcp "
                    "but does not carry the canonical args block verbatim. The CI "
                    "staging rewrite in run-vally-eval.ps1 exact-matches this block; "
                    "reformatting it (indent / quotes / flag order) makes the wrapper "
                    "throw at CI time. Keep the block byte-identical to $baseArgs.",
                )

    def test_canonical_block_has_expected_shape(self):
        for needle in ('- "-y"', "@microsoft/powerbi-modeling-mcp@latest", '- "--start"'):
            self.assertIn(
                needle,
                self.canonical_block,
                f"Canonical $baseArgs block is missing {needle!r}; the here-string "
                "capture in setUpClass likely drifted -- re-check run-vally-eval.ps1.",
            )

    def test_mismatch_path_throws_not_soft_returns(self):
        # The exact-match guard must HARD fail (throw), never return the content
        # unchanged -- a soft return would silently drop the SP-auth overlay and
        # run CI unauthenticated. Pin both the guard->throw adjacency and the
        # canonical error phrase the operator greps for.
        self.assertRegex(
            self.wrapper_text,
            r"if \(-not \$contentLF\.Contains\(\$baseArgsLF\)\)\s*\{\s*\r?\n\s*throw ",
            "run-vally-eval.ps1: the canonical-args mismatch branch no longer throws "
            "immediately; a soft return here would drop the CI auth overlay silently.",
        )
        self.assertIn(
            "was not found verbatim",
            self.wrapper_text,
            "run-vally-eval.ps1: canonical throw message changed; update this contract "
            "test and the 3-edit docstring in test_eval_yaml_mcp_servers.py.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)