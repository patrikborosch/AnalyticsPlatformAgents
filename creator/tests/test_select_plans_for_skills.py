"""Unit tests for ``tests/select_plans_for_skills.py``.

Run with: python -m unittest tests/test_select_plans_for_skills.py -v

The helper is exercised by the PR-touched full-eval workflow
(.github/workflows/fabric-full-eval-pr-touched.yml) to map touched skills
to the per-skill eval plans that exercise them. These tests cover:
  - Individual plan -> single skill extraction (via ``**Skill:**`` marker).
  - Combined plan -> multi-skill participation (skill names in body).
  - Touched skills -> matched plans mapping.
  - Unmatched skills (touched skill has no eval coverage).
  - Infrastructure escalation (common/, plugins/, full-eval-tests/, build_plugins.py).
  - Empty inputs.
  - CLI surface (``--skills`` flag emits JSON with all expected keys).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tests"))

import select_plans_for_skills as helper  # noqa: E402


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class SelectPlansForSkillsTests(unittest.TestCase):
    """Exercise the helper's pure functions against tempdir fixtures.

    The module reads ``SKILLS_DIR`` / ``INDIVIDUAL_EVALS_DIR`` /
    ``COMBINED_EVALS_DIR`` from ``coverage_gap_report`` (absolute paths
    rooted at the repo). To keep tests hermetic we patch those constants
    in both modules during ``setUp`` and restore them in ``tearDown``.
    """

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tempdir.name)

        self.skills_dir = self.repo_root / "skills"
        self.individual_dir = (
            self.repo_root / "tests" / "full-eval-tests" / "plan" / "03-individual-skills"
        )
        self.combined_dir = (
            self.repo_root / "tests" / "full-eval-tests" / "plan" / "04-combined-skills"
        )
        self.skills_dir.mkdir(parents=True)
        self.individual_dir.mkdir(parents=True)
        self.combined_dir.mkdir(parents=True)

        import coverage_gap_report as cgr

        self._orig_skills_dir = cgr.SKILLS_DIR
        self._orig_individual_dir = cgr.INDIVIDUAL_EVALS_DIR
        self._orig_combined_dir = cgr.COMBINED_EVALS_DIR
        self._orig_repo_root = cgr.REPO_ROOT
        self._orig_helper_skills_dir = helper.SKILLS_DIR
        self._orig_helper_individual_dir = helper.INDIVIDUAL_EVALS_DIR
        self._orig_helper_combined_dir = helper.COMBINED_EVALS_DIR
        self._orig_helper_repo_root = helper.REPO_ROOT

        cgr.SKILLS_DIR = self.skills_dir
        cgr.INDIVIDUAL_EVALS_DIR = self.individual_dir
        cgr.COMBINED_EVALS_DIR = self.combined_dir
        cgr.REPO_ROOT = self.repo_root
        helper.SKILLS_DIR = self.skills_dir
        helper.INDIVIDUAL_EVALS_DIR = self.individual_dir
        helper.COMBINED_EVALS_DIR = self.combined_dir
        helper.REPO_ROOT = self.repo_root

    def tearDown(self) -> None:
        import coverage_gap_report as cgr

        cgr.SKILLS_DIR = self._orig_skills_dir
        cgr.INDIVIDUAL_EVALS_DIR = self._orig_individual_dir
        cgr.COMBINED_EVALS_DIR = self._orig_combined_dir
        cgr.REPO_ROOT = self._orig_repo_root
        helper.SKILLS_DIR = self._orig_helper_skills_dir
        helper.INDIVIDUAL_EVALS_DIR = self._orig_helper_individual_dir
        helper.COMBINED_EVALS_DIR = self._orig_helper_combined_dir
        helper.REPO_ROOT = self._orig_helper_repo_root

        self._tempdir.cleanup()

    def _seed_skill(self, name: str) -> None:
        write_file(self.skills_dir / name / "SKILL.md", f"# {name}\n")

    def _seed_individual_plan(self, basename: str, skill: str) -> None:
        write_file(
            self.individual_dir / f"{basename}.md",
            f"# Eval Plan: {skill}\n\n- **Skill:** `{skill}`\n",
        )

    def _seed_combined_plan(self, basename: str, skills: list[str]) -> None:
        body_lines = [f"# Eval Plan: combined {basename}", ""]
        for skill in skills:
            body_lines.append(f"- **Skill:** `{skill}`")
        write_file(
            self.combined_dir / f"{basename}.md",
            "\n".join(body_lines) + "\n",
        )

    # ---- Plan-index extraction --------------------------------------

    def test_individual_plan_maps_to_named_skill(self) -> None:
        self._seed_skill("dataflows-authoring-cli")
        self._seed_skill("dataflows-consumption-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")

        skills = ["dataflows-authoring-cli", "dataflows-consumption-cli"]
        plan_by_skill, all_known = helper.build_plan_index(skills)

        self.assertEqual(plan_by_skill["dataflows-authoring-cli"], ["eval-dataflows-authoring"])
        self.assertEqual(plan_by_skill["dataflows-consumption-cli"], [])
        self.assertIn("eval-dataflows-authoring", all_known)

    def test_combined_plan_participants_extracted_from_body(self) -> None:
        self._seed_skill("dataflows-authoring-cli")
        self._seed_skill("dataflows-consumption-cli")
        self._seed_combined_plan(
            "eval-dataflows-authoring-plus-consumption",
            ["dataflows-authoring-cli", "dataflows-consumption-cli"],
        )

        skills = ["dataflows-authoring-cli", "dataflows-consumption-cli"]
        plan_by_skill, all_known = helper.build_plan_index(skills)

        self.assertIn(
            "eval-dataflows-authoring-plus-consumption",
            plan_by_skill["dataflows-authoring-cli"],
        )
        self.assertIn(
            "eval-dataflows-authoring-plus-consumption",
            plan_by_skill["dataflows-consumption-cli"],
        )
        self.assertIn("eval-dataflows-authoring-plus-consumption", all_known)

    # ---- main() integration via direct call -------------------------

    def _run_main(self, argv: list[str]) -> dict:
        """Invoke ``helper.main()`` with argv and capture stdout JSON.

        Side effect: ``self.last_stderr`` is set to the stderr text emitted
        during the call. Tests that exercise the stderr warning surface read
        it via ``self.last_stderr`` after the call.
        """
        import io

        saved_argv = sys.argv
        saved_stdout = sys.stdout
        saved_stderr = sys.stderr
        try:
            sys.argv = ["select_plans_for_skills.py", *argv]
            buf = io.StringIO()
            err = io.StringIO()
            sys.stdout = buf
            sys.stderr = err
            rc = helper.main()
            self.assertEqual(rc, 0)
            self.last_stderr = err.getvalue()
            return json.loads(buf.getvalue())
        finally:
            sys.argv = saved_argv
            sys.stdout = saved_stdout
            sys.stderr = saved_stderr

    def test_touched_skills_map_to_matched_plans(self) -> None:
        self._seed_skill("dataflows-authoring-cli")
        self._seed_skill("dataflows-consumption-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-consumption", "dataflows-consumption-cli")

        result = self._run_main(["--skills", "dataflows-authoring-cli"])

        self.assertEqual(result["matched_plans"], ["eval-dataflows-authoring"])
        self.assertEqual(result["unmatched_skills"], [])
        self.assertEqual(result["touched_skills"], ["dataflows-authoring-cli"])
        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(result["infrastructure_files"], [])
        self.assertEqual(
            result["participant_skills"]["eval-dataflows-authoring"],
            ["dataflows-authoring-cli"],
        )

    def test_unmatched_skill_when_no_plan_covers_it(self) -> None:
        self._seed_skill("dataflows-authoring-cli")
        self._seed_skill("lonely-skill")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")

        result = self._run_main(["--skills", "lonely-skill"])

        self.assertEqual(result["matched_plans"], [])
        self.assertEqual(result["unmatched_skills"], ["lonely-skill"])
        self.assertEqual(result["touched_skills"], ["lonely-skill"])
        self.assertFalse(result["infrastructure_change"])

    def test_combined_plan_picked_up_when_either_skill_touched(self) -> None:
        self._seed_skill("dataflows-authoring-cli")
        self._seed_skill("dataflows-consumption-cli")
        self._seed_combined_plan(
            "eval-dataflows-authoring-plus-consumption",
            ["dataflows-authoring-cli", "dataflows-consumption-cli"],
        )

        result = self._run_main(["--skills", "dataflows-consumption-cli"])

        self.assertIn(
            "eval-dataflows-authoring-plus-consumption",
            result["matched_plans"],
        )
        self.assertEqual(result["unmatched_skills"], [])

    def test_infrastructure_change_escalates_to_run_all(self) -> None:
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")

        # An infrastructure path under ``common/`` should set
        # infrastructure_change=True and leave matched_plans empty (the
        # workflow then chooses to run all plans via empty plan-filter).
        changed_files = self.repo_root / "changed-files.txt"
        write_file(changed_files, "common/scripts/example.ps1\n")

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertTrue(result["infrastructure_change"])
        self.assertEqual(result["infrastructure_files"], ["common/scripts/example.ps1"])
        self.assertEqual(result["matched_plans"], [])
        self.assertEqual(result["touched_skills"], [])
        # all_known_plans should still be populated so the caller can choose
        # "all" if it interprets infrastructure_change=True as run-all.
        self.assertIn("eval-dataflows-authoring", result["all_known_plans"])

    def test_build_plugins_py_is_classified_as_infrastructure(self) -> None:
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")

        changed_files = self.repo_root / "changed-files.txt"
        write_file(changed_files, "build/build_plugins.py\n")

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertTrue(result["infrastructure_change"])
        self.assertEqual(result["infrastructure_files"], ["build/build_plugins.py"])

    def test_empty_skills_input_yields_empty_matched_plans(self) -> None:
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")

        result = self._run_main(["--skills", ""])

        self.assertEqual(result["matched_plans"], [])
        self.assertEqual(result["touched_skills"], [])
        self.assertEqual(result["unmatched_skills"], [])
        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(result["infrastructure_files"], [])

    def test_empty_changed_files_yields_empty_outputs(self) -> None:
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")

        changed_files = self.repo_root / "changed-files.txt"
        write_file(changed_files, "")

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertEqual(result["matched_plans"], [])
        self.assertEqual(result["touched_skills"], [])
        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(result["infrastructure_files"], [])

    def test_changed_files_extracts_skill_from_skill_md_path(self) -> None:
        # Closes the gap flagged on tests/select_plans_for_skills.py:162: the
        # workflow exercises the helper via --changed-files (not --skills), so
        # regressions in extract_touched_skills_from_paths through the
        # changed-files surface must be caught by unit tests too.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")

        changed_files = self.repo_root / "changed-files.txt"
        write_file(changed_files, "skills/dataflows-authoring-cli/SKILL.md\n")

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertEqual(result["touched_skills"], ["dataflows-authoring-cli"])
        self.assertEqual(result["matched_plans"], ["eval-dataflows-authoring"])
        self.assertFalse(result["infrastructure_change"])

    def test_changed_files_extracts_skill_from_nested_resource_path(self) -> None:
        # Touched file under skills/<name>/resources/<sub>/x.md must still
        # resolve to the right skill folder; the workflow sees full paths.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")

        changed_files = self.repo_root / "changed-files.txt"
        write_file(changed_files, "skills/dataflows-authoring-cli/resources/api-reference.md\n")

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertEqual(result["touched_skills"], ["dataflows-authoring-cli"])
        self.assertEqual(result["matched_plans"], ["eval-dataflows-authoring"])

    def test_changed_files_extracts_multiple_skills_from_mixed_paths(self) -> None:
        # Mixed touched files: two skill folders + one unrelated path. Both
        # skills must appear in touched_skills and map to their plans.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_skill("dataflows-consumption-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-consumption", "dataflows-consumption-cli")

        changed_files = self.repo_root / "changed-files.txt"
        write_file(
            changed_files,
            "skills/dataflows-authoring-cli/SKILL.md\n"
            "skills/dataflows-consumption-cli/SKILL.md\n"
            "docs/unrelated.md\n",
        )

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertEqual(
            sorted(result["touched_skills"]),
            ["dataflows-authoring-cli", "dataflows-consumption-cli"],
        )
        self.assertEqual(
            sorted(result["matched_plans"]),
            ["eval-dataflows-authoring", "eval-dataflows-consumption"],
        )
        self.assertFalse(result["infrastructure_change"])

    # ---- #3: eval plan-file edits do not escalate to run-all -----------

    def test_individual_plan_file_edit_does_not_escalate_to_run_all(self) -> None:
        # Editing only an individual eval plan file (no skills/ change) must
        # NOT be treated as infrastructure: it maps to the plan's skill and
        # runs that skill's plans, instead of escalating the whole suite.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")

        changed_files = self.repo_root / "changed-files.txt"
        write_file(
            changed_files,
            "tests/full-eval-tests/plan/03-individual-skills/eval-dataflows-authoring.md\n",
        )

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(result["infrastructure_files"], [])
        self.assertEqual(result["touched_skills"], ["dataflows-authoring-cli"])
        self.assertEqual(result["matched_plans"], ["eval-dataflows-authoring"])

    def test_combined_plan_file_edit_maps_to_participant_skills(self) -> None:
        # A combined plan-file edit maps to every skill named in its body and
        # runs those skills' plans -- still no run-all escalation.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_skill("dataflows-consumption-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-consumption", "dataflows-consumption-cli")
        self._seed_combined_plan(
            "eval-dataflows-authoring-plus-consumption",
            ["dataflows-authoring-cli", "dataflows-consumption-cli"],
        )

        changed_files = self.repo_root / "changed-files.txt"
        write_file(
            changed_files,
            "tests/full-eval-tests/plan/04-combined-skills/"
            "eval-dataflows-authoring-plus-consumption.md\n",
        )

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(
            sorted(result["touched_skills"]),
            ["dataflows-authoring-cli", "dataflows-consumption-cli"],
        )
        self.assertIn(
            "eval-dataflows-authoring-plus-consumption", result["matched_plans"]
        )

    def test_skill_plus_its_plan_file_no_escalation_no_dup(self) -> None:
        # Reproduces PR #283: a skill edit bundled with that skill's plan-file
        # edit must run only the skill's plans (no infra escalation, no dup).
        self._seed_skill("spark-authoring-cli")
        self._seed_individual_plan("eval-spark-authoring", "spark-authoring-cli")

        changed_files = self.repo_root / "changed-files.txt"
        write_file(
            changed_files,
            "skills/spark-authoring-cli/SKILL.md\n"
            "tests/full-eval-tests/plan/03-individual-skills/eval-spark-authoring.md\n",
        )

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(result["touched_skills"], ["spark-authoring-cli"])
        self.assertEqual(result["matched_plans"], ["eval-spark-authoring"])

    def test_non_eval_file_under_plan_dir_still_infrastructure(self) -> None:
        # Only eval-<x>.md files are carved out. A README or a shared phase
        # file under tests/full-eval-tests/ still escalates to run-all.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")

        changed_files = self.repo_root / "changed-files.txt"
        write_file(
            changed_files,
            "tests/full-eval-tests/plan/03-individual-skills/README.md\n"
            "tests/full-eval-tests/plan/00-overview.md\n",
        )

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertTrue(result["infrastructure_change"])

    # ---- #3b: unresolvable plan-file edits escalate to run-all (F3) ----

    def test_individual_plan_file_with_no_skill_metadata_escalates_to_infra(self) -> None:
        # F3: a plan-file edit that breaks/removes the **Skill:** metadata must
        # NOT silently skip eval -- it escalates to run-all (infrastructure).
        self._seed_skill("dataflows-authoring-cli")
        write_file(
            self.individual_dir / "eval-orphan.md",
            "# Eval Plan: orphan\n\nNo skill metadata here.\n",
        )
        changed_files = self.repo_root / "changed-files.txt"
        write_file(
            changed_files,
            "tests/full-eval-tests/plan/03-individual-skills/eval-orphan.md\n",
        )

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertTrue(result["infrastructure_change"])
        self.assertIn(
            "tests/full-eval-tests/plan/03-individual-skills/eval-orphan.md",
            result["infrastructure_files"],
        )

    def test_deleted_plan_file_escalates_to_infra(self) -> None:
        # F3: a touched plan-file path with no file on disk (deleted in the PR)
        # is unresolvable -> escalate to run-all rather than skip eval.
        self._seed_skill("dataflows-authoring-cli")
        changed_files = self.repo_root / "changed-files.txt"
        write_file(
            changed_files,
            "tests/full-eval-tests/plan/03-individual-skills/eval-deleted.md\n",
        )

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertTrue(result["infrastructure_change"])

    def test_combined_plan_file_naming_no_known_skill_escalates(self) -> None:
        self._seed_skill("dataflows-authoring-cli")
        write_file(
            self.combined_dir / "eval-mystery.md",
            "# Eval Plan: combined mystery\n\nMentions nothing known.\n",
        )
        changed_files = self.repo_root / "changed-files.txt"
        write_file(
            changed_files,
            "tests/full-eval-tests/plan/04-combined-skills/eval-mystery.md\n",
        )

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertTrue(result["infrastructure_change"])

    def test_mixed_resolved_and_unresolved_plan_files_escalate(self) -> None:
        # One resolvable + one unresolvable plan file -> escalate (safe): a
        # broken plan file anywhere in the change set runs the whole suite.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")
        write_file(self.individual_dir / "eval-orphan2.md", "# no skill line\n")
        changed_files = self.repo_root / "changed-files.txt"
        write_file(
            changed_files,
            "tests/full-eval-tests/plan/03-individual-skills/eval-dataflows-authoring.md\n"
            "tests/full-eval-tests/plan/03-individual-skills/eval-orphan2.md\n",
        )

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertTrue(result["infrastructure_change"])

    def test_malformed_utf8_individual_plan_escalates_not_crash(self) -> None:
        # A non-UTF-8 (malformed / accidentally-binary) individual plan file must
        # NOT crash the selector with UnicodeDecodeError -- it is treated as
        # unresolved and escalates to run-all.
        self._seed_skill("dataflows-authoring-cli")
        (self.individual_dir / "eval-binary.md").write_bytes(b"\xff\xfe\x00\x01 not utf-8 \x80\x81")
        changed_files = self.repo_root / "changed-files.txt"
        write_file(
            changed_files,
            "tests/full-eval-tests/plan/03-individual-skills/eval-binary.md\n",
        )

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertTrue(result["infrastructure_change"])
        self.assertIn(
            "tests/full-eval-tests/plan/03-individual-skills/eval-binary.md",
            result["infrastructure_files"],
        )

    def test_malformed_utf8_combined_plan_escalates_not_crash(self) -> None:
        self._seed_skill("dataflows-authoring-cli")
        (self.combined_dir / "eval-binary-combined.md").write_bytes(b"\xff\xfe bad bytes \x80")
        changed_files = self.repo_root / "changed-files.txt"
        write_file(
            changed_files,
            "tests/full-eval-tests/plan/04-combined-skills/eval-binary-combined.md\n",
        )

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertTrue(result["infrastructure_change"])

    # ---- #4: gate_scope_plans (PR-touched hard-fail scope) -------------
    def test_gate_scope_equals_matched_plans_on_normal_run(self) -> None:
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")

        changed_files = self.repo_root / "changed-files.txt"
        write_file(changed_files, "skills/dataflows-authoring-cli/SKILL.md\n")

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(result["gate_scope_plans"], result["matched_plans"])
        self.assertEqual(result["gate_scope_plans"], ["eval-dataflows-authoring"])

    def test_gate_scope_plans_computed_on_infra_change(self) -> None:
        # On a real infra change that ALSO touches a skill, matched_plans is
        # emptied (run-all) but gate_scope_plans still names the touched
        # skill's plans so the PR gate hard-fails only on those.
        self._seed_skill("spark-authoring-cli")
        self._seed_individual_plan("eval-spark-authoring", "spark-authoring-cli")

        changed_files = self.repo_root / "changed-files.txt"
        write_file(
            changed_files,
            "common/COMMON-CLI.md\n"
            "skills/spark-authoring-cli/SKILL.md\n",
        )

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertTrue(result["infrastructure_change"])
        self.assertEqual(result["matched_plans"], [])
        self.assertEqual(result["gate_scope_plans"], ["eval-spark-authoring"])

    def test_gate_scope_plans_empty_on_pure_infra_change(self) -> None:
        # Pure infra change (no skill touched) -> empty gate scope -> the
        # workflow gate falls back to whole-suite gating.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")

        changed_files = self.repo_root / "changed-files.txt"
        write_file(changed_files, "common/COMMON-CLI.md\n")

        result = self._run_main(["--changed-files", str(changed_files)])

        self.assertTrue(result["infrastructure_change"])
        self.assertEqual(result["gate_scope_plans"], [])

    def test_cli_surface_emits_all_top_level_keys(self) -> None:
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")

        result = self._run_main(["--skills", "dataflows-authoring-cli"])

        expected_keys = {
            "matched_plans",
            "participant_skills",
            "unmatched_skills",
            "plugin_skills_without_eval",
            "touched_skills",
            "touched_plugins",
            "plugin_skills",
            "infrastructure_change",
            "infrastructure_files",
            "force_run_all",
            "force_run_all_reason",
            "gate_scope_plans",
            "all_known_plans",
        }
        self.assertEqual(set(result.keys()), expected_keys)
        # --skills path: force_run_all is always False (we have an explicit
        # skill list; no plugin manifest is consulted).
        self.assertFalse(result["force_run_all"])
        self.assertEqual(result["force_run_all_reason"], "")


class SelectPlansForSkillsCliSubprocessTest(unittest.TestCase):
    """Confirm the real CLI surface works end-to-end against the real repo.

    Uses the live repo's skills/ + plan/ tree so it doubles as a smoke test
    that ``--skills`` parses argv correctly, the helper exits 0, and stdout
    is valid JSON with the documented top-level keys. We do NOT assert on
    specific plan names (those evolve with the repo).
    """

    def test_cli_subprocess_emits_valid_json_with_all_keys(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tests" / "select_plans_for_skills.py"),
                "--skills",
                "dataflows-authoring-cli",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        expected_keys = {
            "matched_plans",
            "participant_skills",
            "unmatched_skills",
            "plugin_skills_without_eval",
            "touched_skills",
            "touched_plugins",
            "plugin_skills",
            "infrastructure_change",
            "infrastructure_files",
            "force_run_all",
            "force_run_all_reason",
            "gate_scope_plans",
            "all_known_plans",
        }
        self.assertEqual(set(payload.keys()), expected_keys)
        self.assertEqual(payload["touched_skills"], ["dataflows-authoring-cli"])
        self.assertFalse(payload["infrastructure_change"])
        self.assertFalse(payload["force_run_all"])


class PluginNarrowEscalationTests(unittest.TestCase):
    """Cover the plugins/<name>/... narrowing path.

    Background: before this change, any plugins/<name>/... change escalated
    to run-all-plans because plugins/ was in INFRA_PREFIXES. On a busy
    shared-tenant capacity this took ~3-4h and starved the queue. The
    helper now reads the touched plugin's current manifest and adds the
    listed skills to touched_skills so they flow through the per-skill
    plan-mapping path.

    Scenarios covered here:
    - Single plugin manifest change -> only that plugin's skills get plans.
    - Plugin manifest change + direct skill change -> union (no dup).
    - Multiple plugins touched -> union of skill lists.
    - Missing manifest -> graceful skip (no error, no plans).
    - Malformed manifest JSON -> graceful skip.
    - plugins/ change still NOT classified as infrastructure_change=True
      (regression guard for the INFRA_PREFIXES split).
    """

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tempdir.name)
        self.skills_dir = self.repo_root / "skills"
        self.individual_dir = (
            self.repo_root / "tests" / "full-eval-tests" / "plan" / "03-individual-skills"
        )
        self.combined_dir = (
            self.repo_root / "tests" / "full-eval-tests" / "plan" / "04-combined-skills"
        )
        self.plugins_dir = self.repo_root / "plugins"
        self.skills_dir.mkdir(parents=True)
        self.individual_dir.mkdir(parents=True)
        self.combined_dir.mkdir(parents=True)
        self.plugins_dir.mkdir(parents=True)

        import coverage_gap_report as cgr

        self._orig = (
            cgr.SKILLS_DIR, cgr.INDIVIDUAL_EVALS_DIR, cgr.COMBINED_EVALS_DIR, cgr.REPO_ROOT,
            helper.SKILLS_DIR, helper.INDIVIDUAL_EVALS_DIR, helper.COMBINED_EVALS_DIR, helper.REPO_ROOT,
        )
        cgr.SKILLS_DIR = self.skills_dir
        cgr.INDIVIDUAL_EVALS_DIR = self.individual_dir
        cgr.COMBINED_EVALS_DIR = self.combined_dir
        cgr.REPO_ROOT = self.repo_root
        helper.SKILLS_DIR = self.skills_dir
        helper.INDIVIDUAL_EVALS_DIR = self.individual_dir
        helper.COMBINED_EVALS_DIR = self.combined_dir
        helper.REPO_ROOT = self.repo_root

    def tearDown(self) -> None:
        import coverage_gap_report as cgr
        (cgr.SKILLS_DIR, cgr.INDIVIDUAL_EVALS_DIR, cgr.COMBINED_EVALS_DIR, cgr.REPO_ROOT,
         helper.SKILLS_DIR, helper.INDIVIDUAL_EVALS_DIR, helper.COMBINED_EVALS_DIR,
         helper.REPO_ROOT) = self._orig
        self._tempdir.cleanup()

    def _seed_skill(self, name: str) -> None:
        write_file(self.skills_dir / name / "SKILL.md", f"# {name}\n")

    def _seed_individual_plan(self, basename: str, skill: str) -> None:
        write_file(
            self.individual_dir / f"{basename}.md",
            f"# Eval Plan: {skill}\n\n- **Skill:** `{skill}`\n",
        )

    def _seed_plugin_manifest(self, plugin: str, skills: list[str]) -> None:
        manifest = {
            "name": plugin,
            "version": "0.0.1",
            "skills": [f"./skills/{s}" for s in skills],
        }
        write_file(
            self.plugins_dir / plugin / ".github" / "plugin" / "plugin.json",
            json.dumps(manifest, indent=2),
        )

    def _run_main(self, argv: list[str]) -> dict:
        """Invoke ``helper.main()`` with argv. Side effect: self.last_stderr."""
        import io
        saved_argv = sys.argv
        saved_stdout = sys.stdout
        saved_stderr = sys.stderr
        try:
            sys.argv = ["select_plans_for_skills.py", *argv]
            buf = io.StringIO()
            err = io.StringIO()
            sys.stdout = buf
            sys.stderr = err
            rc = helper.main()
            self.assertEqual(rc, 0)
            self.last_stderr = err.getvalue()
            return json.loads(buf.getvalue())
        finally:
            sys.argv = saved_argv
            sys.stdout = saved_stdout
            sys.stderr = saved_stderr

    def test_plugin_manifest_change_alone_expands_to_listed_skills(self) -> None:
        # The PR-touched-only-plugin-manifest case. Before: run-all (35
        # plans). After: matches the manifest's listed skills only.
        for s in ("skill-a", "skill-b", "skill-c"):
            self._seed_skill(s)
            self._seed_individual_plan(f"eval-{s}", s)
        self._seed_skill("skill-unrelated")
        self._seed_individual_plan("eval-skill-unrelated", "skill-unrelated")
        self._seed_plugin_manifest("my-plugin", ["skill-a", "skill-b", "skill-c"])

        changed = self.repo_root / "changed-files.txt"
        write_file(changed, "plugins/my-plugin/.github/plugin/plugin.json\n")

        result = self._run_main(["--changed-files", str(changed)])

        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(result["touched_plugins"], ["my-plugin"])
        self.assertEqual(
            sorted(result["plugin_skills"]),
            ["skill-a", "skill-b", "skill-c"],
        )
        self.assertEqual(
            sorted(result["touched_skills"]),
            ["skill-a", "skill-b", "skill-c"],
        )
        self.assertEqual(
            sorted(result["matched_plans"]),
            ["eval-skill-a", "eval-skill-b", "eval-skill-c"],
        )
        self.assertNotIn("eval-skill-unrelated", result["matched_plans"])

    def test_plugin_change_plus_direct_skill_change_unions_without_dup(self) -> None:
        # Mirrors PR #307: a plugin manifest tweak alongside a direct edit
        # on one of the plugin's skills. The skill should appear once in
        # touched_skills (not duplicated) and its plans should match.
        for s in ("semantic-model-authoring", "check-updates", "powerbi-report-design"):
            self._seed_skill(s)
            self._seed_individual_plan(f"eval-{s}", s)
        self._seed_plugin_manifest(
            "powerbi-authoring",
            ["semantic-model-authoring", "check-updates", "powerbi-report-design"],
        )

        changed = self.repo_root / "changed-files.txt"
        write_file(
            changed,
            "plugins/powerbi-authoring/.github/plugin/plugin.json\n"
            "skills/semantic-model-authoring/SKILL.md\n",
        )

        result = self._run_main(["--changed-files", str(changed)])

        self.assertFalse(result["infrastructure_change"])
        # touched_skills: direct first, then plugin extras, no duplicates.
        self.assertEqual(
            result["touched_skills"],
            ["semantic-model-authoring", "check-updates", "powerbi-report-design"],
        )
        self.assertEqual(
            sorted(result["matched_plans"]),
            ["eval-check-updates", "eval-powerbi-report-design", "eval-semantic-model-authoring"],
        )

    def test_multiple_plugins_touched_unions_skill_lists(self) -> None:
        for s in ("a-skill", "b-skill", "shared-skill"):
            self._seed_skill(s)
            self._seed_individual_plan(f"eval-{s}", s)
        self._seed_plugin_manifest("plugin-alpha", ["a-skill", "shared-skill"])
        self._seed_plugin_manifest("plugin-beta", ["b-skill", "shared-skill"])

        changed = self.repo_root / "changed-files.txt"
        write_file(
            changed,
            "plugins/plugin-alpha/.github/plugin/plugin.json\n"
            "plugins/plugin-beta/.github/plugin/plugin.json\n",
        )

        result = self._run_main(["--changed-files", str(changed)])

        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(sorted(result["touched_plugins"]), ["plugin-alpha", "plugin-beta"])
        # shared-skill must appear once, not twice.
        self.assertEqual(
            sorted(result["touched_skills"]),
            ["a-skill", "b-skill", "shared-skill"],
        )
        self.assertEqual(
            sorted(result["matched_plans"]),
            ["eval-a-skill", "eval-b-skill", "eval-shared-skill"],
        )

    def test_missing_plugin_manifest_skips_gracefully(self) -> None:
        # Plugin folder exists in the diff but the manifest file isn't there
        # (typo, pre-creation, or deleted). The helper must NOT crash. With
        # Avi F-R1 / F-S1: it now warns to stderr AND sets force_run_all=True
        # so the workflow escalates to run-all (defensive). Before that fix,
        # this case fell through to "no plans" with a misleading skip-reason.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")

        changed = self.repo_root / "changed-files.txt"
        write_file(changed, "plugins/missing-plugin/README.md\n")

        result = self._run_main(["--changed-files", str(changed)])

        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(result["touched_plugins"], ["missing-plugin"])
        self.assertEqual(result["plugin_skills"], [])
        self.assertEqual(result["touched_skills"], [])
        self.assertEqual(result["matched_plans"], [])
        # Defensive escalation: touched plugin + zero skills + no direct
        # skill change -> force_run_all.
        self.assertTrue(result["force_run_all"])
        self.assertIn("missing-plugin", result["force_run_all_reason"])
        # Stderr warning surfaces the specific cause (F-S1 supportability).
        self.assertIn("WARNING", self.last_stderr)
        self.assertIn("missing-plugin", self.last_stderr)
        self.assertIn("no manifest", self.last_stderr)

    def test_malformed_plugin_manifest_skips_gracefully(self) -> None:
        # Manifest exists but is not valid JSON. Same contract as missing:
        # don't crash. Now also: warn to stderr + force_run_all=True.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")
        write_file(
            self.plugins_dir / "broken-plugin" / ".github" / "plugin" / "plugin.json",
            "{not-valid-json,",
        )

        changed = self.repo_root / "changed-files.txt"
        write_file(changed, "plugins/broken-plugin/.github/plugin/plugin.json\n")

        result = self._run_main(["--changed-files", str(changed)])

        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(result["touched_plugins"], ["broken-plugin"])
        self.assertEqual(result["plugin_skills"], [])
        self.assertEqual(result["touched_skills"], [])
        self.assertEqual(result["matched_plans"], [])
        self.assertTrue(result["force_run_all"])
        self.assertIn("broken-plugin", result["force_run_all_reason"])
        self.assertIn("WARNING", self.last_stderr)
        self.assertIn("broken-plugin", self.last_stderr)
        self.assertIn("not valid JSON", self.last_stderr)

    def test_plugins_no_longer_classified_as_infrastructure(self) -> None:
        # Regression guard: before this change, plugins/ was in
        # INFRA_PREFIXES and any plugin path set infrastructure_change=True.
        # The split must keep plugins/ OUT of that bucket so a plugin tweak
        # never escalates to run-all.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_plugin_manifest("any-plugin", ["dataflows-authoring-cli"])

        changed = self.repo_root / "changed-files.txt"
        write_file(changed, "plugins/any-plugin/anything.txt\n")

        result = self._run_main(["--changed-files", str(changed)])

        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(result["infrastructure_files"], [])

    def test_plugin_expansion_skipped_on_infra_change(self) -> None:
        # Bot finding: mixed change (common/ + plugins/<name>/) shouldn't
        # pollute touched_skills + plugin_skills with plugin-bundled skills
        # when infra is the actual driver. On infra change, plugin expansion
        # is skipped so the step-summary table shows only the direct skill
        # touches (here: empty) and infrastructure_files explains the
        # escalation.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_skill("skill-a")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")
        self._seed_individual_plan("eval-skill-a", "skill-a")
        self._seed_plugin_manifest("my-plugin", ["skill-a"])

        changed = self.repo_root / "changed-files.txt"
        write_file(
            changed,
            "common/some-shared.md\n"
            "plugins/my-plugin/.github/plugin/plugin.json\n",
        )

        result = self._run_main(["--changed-files", str(changed)])

        self.assertTrue(result["infrastructure_change"])
        self.assertEqual(result["infrastructure_files"], ["common/some-shared.md"])
        # Plugin expansion was skipped: plugin_skills empty, touched_skills
        # empty (no direct skills/<name>/ edits on this fixture).
        self.assertEqual(result["plugin_skills"], [])
        self.assertEqual(result["touched_skills"], [])
        # touched_plugins still records the plugin so the orchestrator can
        # log it (diagnostic), but plugins do not drive the gate decision
        # on an infra-change PR.
        self.assertEqual(result["touched_plugins"], ["my-plugin"])
        # matched_plans empty -> orchestrator runs all plans (infra wins).
        self.assertEqual(result["matched_plans"], [])

    def test_plugin_expansion_with_direct_skill_on_infra_change(self) -> None:
        # Edge of the F2 fix: when the author touches BOTH a real skill AND
        # an infra path AND a plugin, direct skill touches survive into
        # touched_skills (they're the author's own work) but plugin-bundled
        # extras are still suppressed (infra wins).
        self._seed_skill("direct-skill")
        self._seed_skill("plugin-extra-skill")
        self._seed_individual_plan("eval-direct-skill", "direct-skill")
        self._seed_individual_plan("eval-plugin-extra-skill", "plugin-extra-skill")
        self._seed_plugin_manifest("my-plugin", ["direct-skill", "plugin-extra-skill"])

        changed = self.repo_root / "changed-files.txt"
        write_file(
            changed,
            "common/some-shared.md\n"
            "skills/direct-skill/SKILL.md\n"
            "plugins/my-plugin/.github/plugin/plugin.json\n",
        )

        result = self._run_main(["--changed-files", str(changed)])

        self.assertTrue(result["infrastructure_change"])
        # Direct touch survives even on infra change (author's own edit).
        self.assertEqual(result["touched_skills"], ["direct-skill"])
        # Plugin-extra-skill suppressed: the plugin tweak rode along but
        # infra is the real escalation reason.
        self.assertEqual(result["plugin_skills"], [])
        self.assertEqual(result["touched_plugins"], ["my-plugin"])
        # matched_plans still empty -> infra wins -> run all.
        self.assertEqual(result["matched_plans"], [])

    def test_unmatched_skills_excludes_plugin_bundled_skills(self) -> None:
        # Bot finding: pre-fix, unmatched_skills leaked plugin-bundled
        # uncovered skills into the PR sticky as if the author "touched"
        # them. Now plugin-bundled uncovered skills go in a separate
        # diagnostic bucket (plugin_skills_without_eval) and unmatched_skills
        # only carries skills the author DIRECTLY edited.
        self._seed_skill("covered-skill")
        self._seed_skill("bundle-uncovered-skill")
        self._seed_skill("direct-uncovered-skill")
        self._seed_individual_plan("eval-covered-skill", "covered-skill")
        # bundle-uncovered-skill + direct-uncovered-skill have NO eval plan.
        self._seed_plugin_manifest(
            "my-plugin",
            ["covered-skill", "bundle-uncovered-skill"],
        )

        changed = self.repo_root / "changed-files.txt"
        write_file(
            changed,
            "skills/direct-uncovered-skill/SKILL.md\n"
            "plugins/my-plugin/.github/plugin/plugin.json\n",
        )

        result = self._run_main(["--changed-files", str(changed)])

        self.assertFalse(result["infrastructure_change"])
        # The author saw direct-uncovered-skill -- they touched it themselves
        # and it has no eval coverage. THIS gets surfaced as a warning.
        self.assertEqual(result["unmatched_skills"], ["direct-uncovered-skill"])
        # bundle-uncovered-skill is plugin-bundled and uncovered. The author
        # did NOT touch it directly; surfacing it as "Touched skills with
        # no eval coverage" on the sticky would mislead them. Goes into the
        # diagnostic bucket instead.
        self.assertEqual(result["plugin_skills_without_eval"], ["bundle-uncovered-skill"])
        # covered-skill (plugin-bundled, has plan) flows through normally.
        self.assertIn("eval-covered-skill", result["matched_plans"])

    def test_unmatched_skills_in_plugin_skills_only_bucket(self) -> None:
        # Pure plugin-only change: skills with no coverage go to the
        # diagnostic bucket, NOT to unmatched_skills (which would
        # incorrectly accuse the author of "touching" them).
        self._seed_skill("uncovered-a")
        self._seed_skill("uncovered-b")
        self._seed_plugin_manifest("plugin-x", ["uncovered-a", "uncovered-b"])

        changed = self.repo_root / "changed-files.txt"
        write_file(changed, "plugins/plugin-x/.github/plugin/plugin.json\n")

        result = self._run_main(["--changed-files", str(changed)])

        self.assertEqual(result["unmatched_skills"], [])
        self.assertEqual(
            sorted(result["plugin_skills_without_eval"]),
            ["uncovered-a", "uncovered-b"],
        )
        self.assertEqual(result["matched_plans"], [])


    def test_unicode_decode_error_in_manifest_skips_gracefully(self) -> None:
        # Bot finding: read_text(encoding="utf-8") can raise UnicodeDecodeError
        # on a manifest with invalid UTF-8 bytes. The selector must NOT crash
        # (a crash would block the gate). Write raw non-UTF-8 bytes (Latin-1
        # 0xE9 in a position where UTF-8 expects a continuation byte) and
        # confirm the helper falls through cleanly. With Avi F-R1/F-S1:
        # warns to stderr + force_run_all=True.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")
        manifest_path = self.plugins_dir / "binary-plugin" / ".github" / "plugin" / "plugin.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        # 0xC3 starts a 2-byte UTF-8 sequence but 0x28 isn't a valid
        # continuation byte (continuation must be 0x80-0xBF). Crashes utf-8
        # decode.
        manifest_path.write_bytes(b'{"skills": ["./skills/dataflows-authoring-cli"\xc3\x28]}')

        changed = self.repo_root / "changed-files.txt"
        write_file(changed, "plugins/binary-plugin/.github/plugin/plugin.json\n")

        result = self._run_main(["--changed-files", str(changed)])

        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(result["touched_plugins"], ["binary-plugin"])
        # Skipped silently in the helper, but force_run_all + stderr surface
        # the failure mode so the gate decision is auditable.
        self.assertEqual(result["plugin_skills"], [])
        self.assertEqual(result["touched_skills"], [])
        self.assertEqual(result["matched_plans"], [])
        self.assertTrue(result["force_run_all"])
        self.assertIn("WARNING", self.last_stderr)
        self.assertIn("binary-plugin", self.last_stderr)
        self.assertIn("not valid UTF-8", self.last_stderr)

    def test_non_list_skills_field_skips_gracefully(self) -> None:
        # Bot finding: manifest.get("skills", []) or [] only handles None /
        # empty. A wrong-type value (string / dict / int) is truthy and
        # would either iterate as characters (string) or by key (dict),
        # producing garbage matches. Reject anything that isn't a list.
        # With Avi F-R1/F-S1: warns to stderr per plugin + force_run_all.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")
        # Three pathological manifests in three sibling plugins. All must
        # be skipped without contributing any skills.
        for name, skills_value in (
            ("string-skills", '"./skills/dataflows-authoring-cli"'),
            ("dict-skills", '{"foo": "./skills/dataflows-authoring-cli"}'),
            ("number-skills", '42'),
        ):
            write_file(
                self.plugins_dir / name / ".github" / "plugin" / "plugin.json",
                '{"skills": ' + skills_value + '}',
            )

        changed = self.repo_root / "changed-files.txt"
        write_file(
            changed,
            "plugins/string-skills/.github/plugin/plugin.json\n"
            "plugins/dict-skills/.github/plugin/plugin.json\n"
            "plugins/number-skills/.github/plugin/plugin.json\n",
        )

        result = self._run_main(["--changed-files", str(changed)])

        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(
            sorted(result["touched_plugins"]),
            ["dict-skills", "number-skills", "string-skills"],
        )
        # All three plugins had a non-list skills field. Nothing extracted.
        self.assertEqual(result["plugin_skills"], [])
        self.assertEqual(result["touched_skills"], [])
        self.assertEqual(result["matched_plans"], [])
        # All three failures escalate jointly.
        self.assertTrue(result["force_run_all"])
        # Stderr names each affected plugin with the wrong type.
        self.assertIn("string-skills", self.last_stderr)
        self.assertIn("dict-skills", self.last_stderr)
        self.assertIn("number-skills", self.last_stderr)
        self.assertIn("not list", self.last_stderr)


    # ---- Avi F-R1/F-S1/F-C2: defensive escalation + supportability ----

    def test_empty_skills_array_forces_run_all(self) -> None:
        # Avi F-R1 PoC: a well-formed manifest with an empty skills array
        # yields zero skills (refactor accident, e.g. last skill removed).
        # Pre-fix: 0 plans run, sticky says "PR touched only non-skill
        # files" (misleading). Post-fix: force_run_all=True so the gate
        # runs all plans defensively.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_individual_plan("eval-dataflows-authoring", "dataflows-authoring-cli")
        write_file(
            self.plugins_dir / "empty-plugin" / ".github" / "plugin" / "plugin.json",
            json.dumps({"name": "empty-plugin", "version": "0.0.1", "skills": []}),
        )

        changed = self.repo_root / "changed-files.txt"
        write_file(changed, "plugins/empty-plugin/.github/plugin/plugin.json\n")

        result = self._run_main(["--changed-files", str(changed)])

        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(result["touched_plugins"], ["empty-plugin"])
        self.assertEqual(result["plugin_skills"], [])
        self.assertEqual(result["touched_skills"], [])
        self.assertEqual(result["matched_plans"], [])
        self.assertTrue(result["force_run_all"])
        self.assertIn("empty-plugin", result["force_run_all_reason"])

    def test_missing_skills_key_forces_run_all(self) -> None:
        # Avi F-R1 PoC variant: manifest has no `skills` key at all.
        # `manifest.get("skills", [])` returns [] -> zero skills extracted.
        # Same defensive escalation as the empty-array case.
        self._seed_skill("dataflows-authoring-cli")
        write_file(
            self.plugins_dir / "noskills-plugin" / ".github" / "plugin" / "plugin.json",
            json.dumps({"name": "noskills-plugin", "version": "0.0.1"}),
        )

        changed = self.repo_root / "changed-files.txt"
        write_file(changed, "plugins/noskills-plugin/.github/plugin/plugin.json\n")

        result = self._run_main(["--changed-files", str(changed)])

        self.assertFalse(result["infrastructure_change"])
        self.assertEqual(result["touched_plugins"], ["noskills-plugin"])
        self.assertEqual(result["plugin_skills"], [])
        self.assertEqual(result["touched_skills"], [])
        self.assertTrue(result["force_run_all"])
        self.assertIn("noskills-plugin", result["force_run_all_reason"])

    def test_skill_md_entry_warns_and_is_skipped(self) -> None:
        # Avi F-C2 PoC: an entry that targets a file inside a skill folder
        # (e.g. ./skills/foo/SKILL.md) instead of the folder itself is
        # silently rejected by the existing regex. With F-S1: emits a
        # stderr WARNING naming the bad entry so the contributor can fix
        # it. Today no production manifest hits this; the test is a
        # regression guard for the supportability surface.
        self._seed_skill("dataflows-authoring-cli")
        self._seed_skill("foo")
        self._seed_individual_plan("eval-foo", "foo")
        write_file(
            self.plugins_dir / "subpath-plugin" / ".github" / "plugin" / "plugin.json",
            json.dumps({
                "name": "subpath-plugin",
                "skills": [
                    "./skills/foo/SKILL.md",
                    "./skills/foo/manifest.json",
                    "./skills/foo/sub/path",
                ],
            }),
        )

        changed = self.repo_root / "changed-files.txt"
        write_file(changed, "plugins/subpath-plugin/.github/plugin/plugin.json\n")

        result = self._run_main(["--changed-files", str(changed)])

        # All three entries rejected -> zero skills extracted.
        self.assertEqual(result["plugin_skills"], [])
        # Defensive escalation kicks in (no skills + no direct touch).
        self.assertTrue(result["force_run_all"])
        # Stderr names each bad entry + cites the expected folder form.
        self.assertIn("SKILL.md", self.last_stderr)
        self.assertIn("manifest.json", self.last_stderr)
        self.assertIn("sub/path", self.last_stderr)
        self.assertIn("folder form", self.last_stderr)

    def test_direct_skill_change_overrides_force_run_all(self) -> None:
        # When a plugin is touched AND its manifest yields zero skills
        # AND the author also directly touched a skill folder, we have an
        # explicit signal (the direct touch). force_run_all stays False
        # and the gate runs only the plans covering the directly-touched
        # skill -- no over-coverage.
        self._seed_skill("direct-skill")
        self._seed_individual_plan("eval-direct-skill", "direct-skill")
        write_file(
            self.plugins_dir / "empty-plugin" / ".github" / "plugin" / "plugin.json",
            json.dumps({"name": "empty-plugin", "skills": []}),
        )

        changed = self.repo_root / "changed-files.txt"
        write_file(
            changed,
            "skills/direct-skill/SKILL.md\n"
            "plugins/empty-plugin/.github/plugin/plugin.json\n",
        )

        result = self._run_main(["--changed-files", str(changed)])

        self.assertFalse(result["infrastructure_change"])
        self.assertFalse(result["force_run_all"])
        self.assertEqual(result["force_run_all_reason"], "")
        self.assertEqual(result["touched_skills"], ["direct-skill"])
        # Only the direct-skill plan ran (no run-all).
        self.assertEqual(result["matched_plans"], ["eval-direct-skill"])

    def test_one_plugin_with_skills_other_empty_does_not_force_run_all(self) -> None:
        # Multi-plugin case: one plugin's manifest yields skills, another's
        # yields zero. We have a signal (the first plugin's skills), so
        # force_run_all stays False. The empty plugin still warns to
        # stderr -- the contributor may want to know about it -- but the
        # gate runs only the matched plans.
        self._seed_skill("real-skill")
        self._seed_individual_plan("eval-real-skill", "real-skill")
        self._seed_plugin_manifest("plugin-with-skills", ["real-skill"])
        write_file(
            self.plugins_dir / "plugin-empty" / ".github" / "plugin" / "plugin.json",
            json.dumps({"name": "plugin-empty", "skills": []}),
        )

        changed = self.repo_root / "changed-files.txt"
        write_file(
            changed,
            "plugins/plugin-with-skills/.github/plugin/plugin.json\n"
            "plugins/plugin-empty/.github/plugin/plugin.json\n",
        )

        result = self._run_main(["--changed-files", str(changed)])

        self.assertFalse(result["infrastructure_change"])
        self.assertFalse(result["force_run_all"])
        self.assertEqual(result["plugin_skills"], ["real-skill"])
        self.assertEqual(result["matched_plans"], ["eval-real-skill"])

    def test_infra_change_with_empty_plugin_manifest_does_not_double_signal(self) -> None:
        # Infra precedence: when a true-infra path is also touched, infra
        # wins and force_run_all stays False (no double-signal). The
        # workflow renders one reason in the sticky, not both.
        self._seed_skill("any-skill")
        self._seed_individual_plan("eval-any-skill", "any-skill")
        write_file(
            self.plugins_dir / "empty-plugin" / ".github" / "plugin" / "plugin.json",
            json.dumps({"name": "empty-plugin", "skills": []}),
        )

        changed = self.repo_root / "changed-files.txt"
        write_file(
            changed,
            "common/shared.md\n"
            "plugins/empty-plugin/.github/plugin/plugin.json\n",
        )

        result = self._run_main(["--changed-files", str(changed)])

        # Infra wins.
        self.assertTrue(result["infrastructure_change"])
        # force_run_all stays False so the workflow's infra branch fires,
        # not the force_run_all branch.
        self.assertFalse(result["force_run_all"])
        self.assertEqual(result["force_run_all_reason"], "")


if __name__ == "__main__":
    unittest.main()
