"""
Unit tests for the enforced coverage policy.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).parent))

import coverage_enforcement  # noqa: E402


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed with exit code {result.returncode}: {result.stderr}"
        )
    return result.stdout


def init_repo(repo_root: Path) -> None:
    run_git(repo_root, "init")
    run_git(repo_root, "config", "user.name", "Test User")
    run_git(repo_root, "config", "user.email", "test@example.com")
    run_git(repo_root, "branch", "-M", "main")


def write_manifest(repo_root: Path, skills: list[str]) -> None:
    lines = [
        "schemaVersion: 1",
        "teams:",
        "  platform:",
        "    displayName: Platform",
        "    scope: Validation tests",
        "skills:",
    ]
    for skill in skills:
        lines.extend(
            [
                f"  {skill}:",
                "    owningTeam: platform",
                "    area: test",
            ]
        )
    write_file(repo_root / ".github" / "skill-ownership.yml", "\n".join(lines) + "\n")


def write_policy(
    repo_root: Path,
    *,
    smoke: dict[str, dict[str, str]] | None = None,
    vally: dict[str, dict[str, str]] | None = None,
    individual: dict[str, dict[str, str]] | None = None,
    combined: dict[str, dict[str, str]] | None = None,
    require_smoke: bool = True,
    require_vally: bool = True,
) -> None:
    policy = {
        "schemaVersion": 1,
        "description": "Test policy",
        "defaults": {
            "requireSmokeForNewSkills": require_smoke,
            "requireVallyEvalForNewSkills": require_vally,
            "requireIndividualEvalForNewSkills": True,
            "requireCombinedEvalWhenPairedSkillExists": True,
        },
        "allowMissing": {
            "smoke": smoke or {},
            "vallyEval": vally or {},
            "individualEval": individual or {},
            "combinedEval": combined or {},
        },
    }
    lines = json.dumps(policy)
    write_file(repo_root / ".github" / "coverage-policy.yml", lines)


def write_repo_state(
    repo_root: Path,
    *,
    skills: list[str],
    smoke_skills: list[str] | None = None,
    vally_eval_skills: list[str] | None = None,
    individual_eval_skills: list[str] | None = None,
    combined_pairs: list[tuple[str, str]] | None = None,
    smoke_allow_missing: dict[str, dict[str, str]] | None = None,
    vally_allow_missing: dict[str, dict[str, str]] | None = None,
    individual_allow_missing: dict[str, dict[str, str]] | None = None,
    combined_allow_missing: dict[str, dict[str, str]] | None = None,
    require_smoke: bool = True,
    require_vally: bool = True,
) -> None:
    smoke_skills = smoke_skills or []
    vally_eval_skills = vally_eval_skills or []
    individual_eval_skills = individual_eval_skills or []
    combined_pairs = combined_pairs or []

    for skill_name in skills:
        write_file(repo_root / "skills" / skill_name / "SKILL.md", f"# {skill_name}\n")

    smoke_cases = [
        {
            "name": f"{skill_name}-smoke",
            "expectedSkills": [skill_name],
        }
        for skill_name in smoke_skills
    ]
    write_file(repo_root / "tests" / "tests.json", json.dumps(smoke_cases))

    for skill_name in vally_eval_skills:
        write_file(
            repo_root / "tests" / "evals" / skill_name / "eval.yaml",
            f"skill: {skill_name}\nstimuli: []\n",
        )

    for skill_name in individual_eval_skills:
        write_file(
            repo_root
            / "tests"
            / "full-eval-tests"
            / "plan"
            / "03-individual-skills"
            / f"eval-{skill_name}.md",
            f"# Eval Plan: {skill_name}\n\n- **Skill:** `{skill_name}`\n",
        )

    for authoring_skill, consumption_skill in combined_pairs:
        write_file(
            repo_root
            / "tests"
            / "full-eval-tests"
            / "plan"
            / "04-combined-skills"
            / f"eval-{authoring_skill}-plus-{consumption_skill}.md",
            (
                f"# Eval Plan: {authoring_skill} + {consumption_skill}\n\n"
                f"Verify `{authoring_skill}` works with `{consumption_skill}`.\n"
            ),
        )

    write_manifest(repo_root, skills)
    write_policy(
        repo_root,
        smoke=smoke_allow_missing,
        vally=vally_allow_missing,
        individual=individual_allow_missing,
        combined=combined_allow_missing,
        require_smoke=require_smoke,
        require_vally=require_vally,
    )


class CoverageEnforcementTests(unittest.TestCase):
    maxDiff = None

    def test_new_skill_requires_smoke_and_individual_eval(self) -> None:
        # require_vally=False isolates the smoke+individual-required engine path;
        # Vally is covered by test_new_skill_requires_vally_eval.
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            init_repo(repo_root)
            write_repo_state(
                repo_root,
                skills=["alpha-authoring-cli"],
                smoke_skills=["alpha-authoring-cli"],
                individual_eval_skills=["alpha-authoring-cli"],
                require_vally=False,
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "base")

            write_repo_state(
                repo_root,
                skills=["alpha-authoring-cli", "beta-migration"],
                smoke_skills=["alpha-authoring-cli"],
                individual_eval_skills=["alpha-authoring-cli"],
                require_vally=False,
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "add beta")

            report = coverage_enforcement.build_enforcement_report(repo_root, base_ref="HEAD~1")

            self.assertEqual(report["overallStatus"], "FAILED")
            violation_messages = [item["message"] for item in report["violations"]]
            self.assertTrue(
                any("beta-migration" in message and "smoke coverage" in message for message in violation_messages)
            )
            self.assertTrue(
                any("beta-migration" in message and "individual eval coverage" in message for message in violation_messages)
            )

    def test_new_skill_requires_vally_eval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            init_repo(repo_root)
            write_repo_state(
                repo_root,
                skills=["alpha-authoring-cli"],
                vally_eval_skills=["alpha-authoring-cli"],
                individual_eval_skills=["alpha-authoring-cli"],
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "base")

            # New skill ships with an individual eval plan but no Vally eval.
            write_repo_state(
                repo_root,
                skills=["alpha-authoring-cli", "kappa-authoring-cli"],
                vally_eval_skills=["alpha-authoring-cli"],
                individual_eval_skills=["alpha-authoring-cli", "kappa-authoring-cli"],
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "add kappa without vally eval")

            report = coverage_enforcement.build_enforcement_report(repo_root, base_ref="HEAD~1")

            self.assertEqual(report["overallStatus"], "FAILED")
            self.assertTrue(
                any(
                    violation["skill"] == "kappa-authoring-cli"
                    and violation["kind"] == "vallyEval"
                    for violation in report["violations"]
                ),
                msg=f"Expected vallyEval violation; got: {report['violations']}",
            )
            kappa = next(skill for skill in report["changedSkills"] if skill["name"] == "kappa-authoring-cli")
            self.assertEqual(kappa["vallyEval"]["status"], "missing")

    def test_smoke_not_required_when_policy_disables_it(self) -> None:
        """With requireSmokeForNewSkills disabled (the post-Vally-cutover repo
        default), a new skill with a Vally eval but no smoke case is clean."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            init_repo(repo_root)
            write_repo_state(
                repo_root,
                skills=["alpha-authoring-cli"],
                vally_eval_skills=["alpha-authoring-cli"],
                individual_eval_skills=["alpha-authoring-cli"],
                require_smoke=False,
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "base")

            # New skill has Vally + individual coverage but no smoke entry.
            write_repo_state(
                repo_root,
                skills=["alpha-authoring-cli", "lambda-operations-cli"],
                vally_eval_skills=["alpha-authoring-cli", "lambda-operations-cli"],
                individual_eval_skills=["alpha-authoring-cli", "lambda-operations-cli"],
                require_smoke=False,
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "add lambda without smoke")

            report = coverage_enforcement.build_enforcement_report(repo_root, base_ref="HEAD~1")

            self.assertEqual(report["overallStatus"], "PASSED")
            self.assertFalse(
                any(violation["kind"] == "smoke" for violation in report["violations"]),
                msg=f"Smoke must not be required; got: {report['violations']}",
            )
            lambda_skill = next(
                skill for skill in report["changedSkills"] if skill["name"] == "lambda-operations-cli"
            )
            self.assertEqual(lambda_skill["smoke"]["status"], "not-required")

    def test_advisory_smoke_allow_missing_on_new_skill_does_not_block(self) -> None:
        """When smoke is advisory (requireSmokeForNewSkills=false), a new skill
        that carries a smoke allowMissing entry must NOT trip the stale-on-arrival
        or new-debt guardrails -- an advisory kind produces no blocking violation.
        Regression guard for the 'smoke advisory still blocks' gap."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            init_repo(repo_root)
            write_repo_state(
                repo_root,
                skills=["alpha-authoring-cli"],
                vally_eval_skills=["alpha-authoring-cli"],
                individual_eval_skills=["alpha-authoring-cli"],
                require_smoke=False,
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "base")

            # New skill ships smoke coverage AND a (now-pointless) smoke debt
            # entry. Under a required kind this would be a stale/debt violation;
            # for advisory smoke it must be silently inert.
            write_repo_state(
                repo_root,
                skills=["alpha-authoring-cli", "mu-operations-cli"],
                smoke_skills=["mu-operations-cli"],
                vally_eval_skills=["alpha-authoring-cli", "mu-operations-cli"],
                individual_eval_skills=["alpha-authoring-cli", "mu-operations-cli"],
                require_smoke=False,
                smoke_allow_missing={
                    "mu-operations-cli": {
                        "status": "debt",
                        "reason": "Leftover smoke entry; smoke is advisory so this must not block.",
                    }
                },
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "add mu with advisory smoke entry")

            report = coverage_enforcement.build_enforcement_report(repo_root, base_ref="HEAD~1")

            self.assertEqual(report["overallStatus"], "PASSED")
            self.assertFalse(
                any(violation["kind"] == "smoke" for violation in report["violations"]),
                msg=f"Advisory smoke must never block; got: {report['violations']}",
            )

    def test_new_paired_skill_requires_combined_eval(self) -> None:
        # require_vally=False isolates the combined-eval-required path.
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            init_repo(repo_root)
            write_repo_state(
                repo_root,
                skills=["gamma-authoring-cli"],
                smoke_skills=["gamma-authoring-cli"],
                individual_eval_skills=["gamma-authoring-cli"],
                require_vally=False,
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "base")

            write_repo_state(
                repo_root,
                skills=["gamma-authoring-cli", "gamma-consumption-cli"],
                smoke_skills=["gamma-authoring-cli", "gamma-consumption-cli"],
                individual_eval_skills=["gamma-authoring-cli", "gamma-consumption-cli"],
                require_vally=False,
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "add gamma consumption")

            report = coverage_enforcement.build_enforcement_report(repo_root, base_ref="HEAD~1")

            self.assertEqual(report["overallStatus"], "FAILED")
            self.assertTrue(
                any(
                    violation["skill"] == "gamma-consumption-cli"
                    and violation["kind"] == "combinedEval"
                    for violation in report["violations"]
                )
            )

    def test_new_skill_can_use_explicit_exemption(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            init_repo(repo_root)
            write_repo_state(
                repo_root,
                skills=["alpha-authoring-cli"],
                smoke_skills=["alpha-authoring-cli"],
                vally_eval_skills=["alpha-authoring-cli"],
                individual_eval_skills=["alpha-authoring-cli"],
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "base")

            write_repo_state(
                repo_root,
                skills=["alpha-authoring-cli", "delta-migration"],
                smoke_skills=["alpha-authoring-cli"],
                vally_eval_skills=["alpha-authoring-cli"],
                individual_eval_skills=["alpha-authoring-cli", "delta-migration"],
                smoke_allow_missing={
                    "delta-migration": {
                        "status": "exempt",
                        "reason": "Fast smoke coverage is intentionally not required for this migration skill.",
                    }
                },
                vally_allow_missing={
                    "delta-migration": {
                        "status": "exempt",
                        "reason": "Cross-platform migration guidance skill; no stable Fabric runtime action for a Vally stimulus.",
                    }
                },
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "add delta")

            report = coverage_enforcement.build_enforcement_report(repo_root, base_ref="HEAD~1")

            self.assertEqual(report["overallStatus"], "PASSED")
            delta = next(skill for skill in report["changedSkills"] if skill["name"] == "delta-migration")
            self.assertEqual(delta["smoke"]["status"], "exempt")
            self.assertEqual(delta["vallyEval"]["status"], "exempt")

    def test_new_skill_cannot_add_debt(self) -> None:
        # require_vally=False isolates the smoke-debt guardrail.
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            init_repo(repo_root)
            write_repo_state(
                repo_root,
                skills=["alpha-authoring-cli"],
                smoke_skills=["alpha-authoring-cli"],
                individual_eval_skills=["alpha-authoring-cli"],
                require_vally=False,
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "base")

            write_repo_state(
                repo_root,
                skills=["alpha-authoring-cli", "theta-migration"],
                smoke_skills=["alpha-authoring-cli"],
                individual_eval_skills=["alpha-authoring-cli", "theta-migration"],
                require_vally=False,
                smoke_allow_missing={
                    "theta-migration": {
                        "status": "debt",
                        "reason": "This should fail because new skills cannot add debt.",
                    }
                },
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "add theta")

            report = coverage_enforcement.build_enforcement_report(repo_root, base_ref="HEAD~1")

            self.assertEqual(report["overallStatus"], "FAILED")
            self.assertTrue(
                any(
                    violation["skill"] == "theta-migration"
                    and "cannot add smoke coverage debt" in violation["message"]
                    for violation in report["violations"]
                )
            )

    def test_new_skill_with_coverage_cannot_keep_allow_missing_entry(self) -> None:
        """A new skill that already has coverage must not also carry an
        `allowMissing` entry — the entry would be stale on arrival.

        The baseline stale check only considers entries whose skill exists in
        the base ref, so without this check a rename PR can land both a new
        skill name AND a stale exemption for it, then break every subsequent
        PR (the exemption becomes visible to the baseline check only after
        the PR is merged into base).

        Regression guard for the issue first observed in
        gim-home/skills-for-fabric#138 (spark-diagnostics-cli ->
        spark-operations-cli rename, which kept the exemption while also
        adding three smoke tests).
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            init_repo(repo_root)
            write_repo_state(
                repo_root,
                skills=["alpha-authoring-cli"],
                smoke_skills=["alpha-authoring-cli"],
                individual_eval_skills=["alpha-authoring-cli"],
                require_vally=False,
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "base")

            write_repo_state(
                repo_root,
                skills=["alpha-authoring-cli", "epsilon-operations-cli"],
                smoke_skills=["alpha-authoring-cli", "epsilon-operations-cli"],
                individual_eval_skills=["alpha-authoring-cli", "epsilon-operations-cli"],
                require_vally=False,
                smoke_allow_missing={
                    "epsilon-operations-cli": {
                        "status": "exempt",
                        "reason": "Stale-on-arrival entry — this skill already has smoke coverage.",
                    }
                },
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "add epsilon-operations-cli with smoke + stale exemption")

            report = coverage_enforcement.build_enforcement_report(repo_root, base_ref="HEAD~1")

            self.assertEqual(report["overallStatus"], "FAILED")
            self.assertTrue(
                any(
                    violation["skill"] == "epsilon-operations-cli"
                    and violation["kind"] == "smoke"
                    and "remove its `allowMissing.smoke` entry" in violation["message"]
                    for violation in report["violations"]
                ),
                msg=f"Expected stale-on-arrival smoke violation; got: {report['violations']}",
            )

    def test_baseline_requires_tracked_existing_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            write_repo_state(
                repo_root,
                skills=["omega-migration"],
                smoke_skills=[],
                individual_eval_skills=["omega-migration"],
                require_vally=False,
            )

            report = coverage_enforcement.build_enforcement_report(repo_root)

            self.assertEqual(report["overallStatus"], "FAILED")
            self.assertEqual(report["baseline"]["smoke"]["untrackedMissing"], ["omega-migration"])

    def test_main_writes_degraded_report_when_git_fails(self) -> None:
        """When `git diff base...HEAD` fails (e.g. no merge base for a conflicting fork PR),
        `main()` must still write a parseable JSON report so downstream steps
        can render a coherent failure instead of cascading on FileNotFoundError.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            init_repo(repo_root)
            write_repo_state(
                repo_root,
                skills=["alpha-authoring-cli"],
                smoke_skills=["alpha-authoring-cli"],
                individual_eval_skills=["alpha-authoring-cli"],
            )
            run_git(repo_root, "add", ".")
            run_git(repo_root, "commit", "-m", "base")

            json_output = repo_root / "coverage-enforcement.json"
            with mock.patch(
                "sys.argv",
                [
                    "coverage_enforcement.py",
                    "--repo-root",
                    str(repo_root),
                    "--base-ref",
                    "definitely-not-a-real-ref",
                    "--json-output",
                    str(json_output),
                    "--quiet",
                ],
            ):
                exit_code = coverage_enforcement.main()

            self.assertEqual(exit_code, 1)
            self.assertTrue(json_output.is_file())
            payload = json.loads(json_output.read_text(encoding="utf-8"))
            self.assertEqual(payload["overallStatus"], "ERROR")
            self.assertIn("error", payload)
            self.assertTrue(payload["error"])
            self.assertEqual(payload["baseRef"], "definitely-not-a-real-ref")
            self.assertEqual(payload["changedSkills"], [])
            self.assertEqual(payload["violations"], [])

    def test_build_degraded_report_shape_matches_downstream_consumers(self) -> None:
        """The degraded report must include the keys the sticky-comment renderer
        reads, so it does not cascade on `KeyError`."""
        degraded = coverage_enforcement.build_degraded_report(
            base_ref="origin/main",
            error_message="git diff failed: no merge base",
        )
        # Keys read by .github/workflows/quality-check.yml sticky comment renderer
        self.assertIn("summary", degraded)
        self.assertIn("violationCount", degraded["summary"])
        self.assertIn("changedSkillCount", degraded["summary"])
        self.assertIn("changedSkills", degraded)
        self.assertIn("violations", degraded)
        self.assertEqual(degraded["overallStatus"], "ERROR")
        self.assertIn("error", degraded)


if __name__ == "__main__":
    unittest.main()
