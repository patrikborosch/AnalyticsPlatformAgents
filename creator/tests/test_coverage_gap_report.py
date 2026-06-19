"""
Unit tests for the advisory coverage-gap report.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent))

import coverage_gap_report


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class CoverageGapReportTests(unittest.TestCase):
    def test_report_detects_missing_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)

            for skill_name in (
                "check-updates",
                "eventhouse-authoring-cli",
                "eventhouse-consumption-cli",
                "e2e-demo",
                "synapse-migration",
            ):
                write_file(repo_root / "skills" / skill_name / "SKILL.md", f"# {skill_name}\n")

            write_file(
                repo_root / "tests" / "tests.json",
                json.dumps(
                    [
                        {
                            "name": "eventhouse-authoring-smoke",
                            "expectedSkills": ["eventhouse-authoring-cli"],
                        },
                        {
                            "name": "eventhouse-consumption-smoke",
                            "expectedSkills": ["eventhouse-consumption-cli"],
                        },
                        {
                            "name": "unmapped-agent-smoke",
                            "expectedSkills": [],
                        },
                    ]
                ),
            )

            write_file(
                repo_root / "tests" / "full-eval-tests" / "plan" / "03-individual-skills" / "eval-eventhouse-authoring.md",
                "# Eval Plan: eventhouse-authoring-cli\n\n- **Skill:** `eventhouse-authoring-cli`\n",
            )
            write_file(
                repo_root / "tests" / "full-eval-tests" / "plan" / "03-individual-skills" / "eval-eventhouse-consumption.md",
                "# Eval Plan: eventhouse-consumption-cli\n\n- **Skill:** `eventhouse-consumption-cli`\n",
            )
            write_file(
                repo_root / "tests" / "full-eval-tests" / "plan" / "03-individual-skills" / "eval-e2e-demo.md",
                "# Eval Plan: e2e-demo\n\n- **Skill:** `e2e-demo`\n",
            )
            write_file(
                repo_root / "tests" / "full-eval-tests" / "plan" / "04-combined-skills" / "eval-eventhouse-authoring-plus-consumption.md",
                (
                    "# Eval Plan: eventhouse authoring + consumption\n\n"
                    "Verify `eventhouse-authoring-cli` works with `eventhouse-consumption-cli`.\n"
                ),
            )

            report = coverage_gap_report.build_coverage_report(repo_root)

            self.assertEqual(
                report["gaps"]["missingSmoke"],
                ["check-updates", "e2e-demo", "synapse-migration"],
            )
            self.assertEqual(
                report["gaps"]["missingIndividualEval"],
                ["check-updates", "synapse-migration"],
            )
            self.assertEqual(
                report["combinedCoverage"]["notParticipatingSkills"],
                ["check-updates", "e2e-demo", "synapse-migration"],
            )
            self.assertEqual(report["unmappedSmokeCases"][0]["name"], "unmapped-agent-smoke")


if __name__ == "__main__":
    unittest.main()
