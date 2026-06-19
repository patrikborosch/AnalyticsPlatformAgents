"""Guard against re-arming legacy smoke auto-fire triggers after the
Vally cutover. Vally is the primary CI harness; legacy smoke workflows
must stay manual-dispatch break-glass only.

Run locally:
    python -m unittest tests/test_workflow_triggers.py -v
"""
from __future__ import annotations

import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
LEGACY_SMOKE_WORKFLOWS = [
    ".github/workflows/fabric-smoke-ephemeral.yml",
    ".github/workflows/fabric-smoke-pr-touched.yml",
]
FORBIDDEN_TRIGGERS = {"schedule", "pull_request", "pull_request_target"}


def _workflow_triggers(path: Path) -> dict:
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    triggers = data.get("on", {})
    if isinstance(triggers, str):
        return {triggers: None}
    if isinstance(triggers, list):
        return {name: None for name in triggers}
    return triggers or {}


class LegacySmokeTriggerTests(unittest.TestCase):
    """One subTest per legacy smoke workflow so failures pinpoint the file."""

    def test_legacy_smoke_workflows_stay_manual_only(self):
        for rel_path in LEGACY_SMOKE_WORKFLOWS:
            with self.subTest(workflow=rel_path):
                triggers = _workflow_triggers(ROOT / rel_path)
                self.assertIn(
                    "workflow_dispatch",
                    triggers,
                    f"{rel_path}: workflow_dispatch entry-point removed; "
                    "legacy smoke must keep the manual break-glass path.",
                )
                forbidden_present = FORBIDDEN_TRIGGERS & set(triggers)
                self.assertFalse(
                    forbidden_present,
                    f"{rel_path}: re-armed forbidden auto-fire triggers "
                    f"{sorted(forbidden_present)}. Vally is the primary CI "
                    "harness; legacy smoke is manual-dispatch only.",
                )

    def test_legacy_workflows_retain_dispatch_so_revert_is_runnable(self):
        """Positive-presence guard (strictly stronger than the forbidden-
        absence check above): each legacy smoke file must keep
        ``workflow_dispatch`` AND expose no auto-fire trigger beyond the
        manual/callable pair {workflow_dispatch, workflow_call}.

        Rationale: the break-glass runbook in
        docs/legacy-smoke-break-glass.md assumes these workflows have a
        dispatch button to click. A typo on the key (e.g. ``workflow_disptach``)
        would leave the file with no usable trigger and silently break the
        runbook; a future auto-fire trigger (``push``, ``issue_comment``, ...)
        not enumerated in FORBIDDEN_TRIGGERS would re-arm the smoke harness the
        Vally cutover retired. Allowing ``workflow_call`` keeps the files
        reusable as composable callees without re-arming auto-fire.
        """
        allowed = {"workflow_dispatch", "workflow_call"}
        for rel_path in LEGACY_SMOKE_WORKFLOWS:
            with self.subTest(workflow=rel_path):
                triggers = _workflow_triggers(ROOT / rel_path)
                self.assertIn(
                    "workflow_dispatch",
                    triggers,
                    f"{rel_path}: lost workflow_dispatch; the break-glass "
                    "runbook in docs/legacy-smoke-break-glass.md no longer has "
                    "a dispatch surface to click.",
                )
                unexpected = set(triggers) - allowed
                self.assertFalse(
                    unexpected,
                    f"{rel_path}: declares non-manual trigger(s) "
                    f"{sorted(unexpected)}. Legacy smoke must stay "
                    "manual/callable only (workflow_dispatch + optional "
                    "workflow_call) after the Vally cutover.",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)

