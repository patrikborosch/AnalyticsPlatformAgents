#!/usr/bin/env python3
"""
Generate an advisory coverage-gap report for Vally, smoke, and full-eval assets.

This is intentionally non-blocking. It surfaces current coverage gaps so the
repo can track debt and later turn explicit policy into CI enforcement.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
SMOKE_TESTS_PATH = REPO_ROOT / "tests" / "tests.json"
INDIVIDUAL_EVALS_DIR = REPO_ROOT / "tests" / "full-eval-tests" / "plan" / "03-individual-skills"
COMBINED_EVALS_DIR = REPO_ROOT / "tests" / "full-eval-tests" / "plan" / "04-combined-skills"
VALLY_EVALS_DIR = REPO_ROOT / "tests" / "evals"
DEFAULT_JSON_REPORT = REPO_ROOT / "coverage-gap-report.json"


def discover_skills(skills_dir: Path) -> list[str]:
    """Return all skill folder names that contain a SKILL.md."""
    return sorted(
        skill_dir.name
        for skill_dir in skills_dir.iterdir()
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists()
    )


def categorize_skill(skill_name: str) -> str:
    """Classify a skill into the current repository taxonomy buckets."""
    if skill_name == "check-updates":
        return "utility"
    if skill_name.startswith("e2e-"):
        return "e2e"
    if skill_name.endswith("-migration"):
        return "migration"
    if "-authoring-" in skill_name:
        return "authoring"
    if "-consumption-" in skill_name:
        return "consumption"
    return "other"


def build_smoke_index(skill_names: list[str], smoke_tests_path: Path) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    """Map each skill to the smoke test cases that explicitly expect it."""
    smoke_index = {skill_name: [] for skill_name in skill_names}
    raw_cases = json.loads(smoke_tests_path.read_text(encoding="utf-8"))
    unmapped_cases: list[dict[str, Any]] = []

    for case in raw_cases:
        case_name = str(case.get("name", "<unnamed-case>"))
        expected_skills = case.get("expectedSkills", [])
        matched_any_skill = False

        if not isinstance(expected_skills, list):
            expected_skills = []

        for skill_name in expected_skills:
            if skill_name in smoke_index:
                smoke_index[skill_name].append(case_name)
                matched_any_skill = True

        if not expected_skills or not matched_any_skill:
            unmapped_cases.append(
                {
                    "name": case_name,
                    "expectedSkills": expected_skills,
                }
            )

    return smoke_index, unmapped_cases


def build_vally_eval_index(
    skill_names: list[str], vally_evals_dir: Path
) -> tuple[dict[str, list[str]], list[dict[str, str]]]:
    """Map each skill to its Vally eval asset (``tests/evals/<skill>/eval.yaml``).

    Vally is the primary behavior-testing surface after the #322 cutover. A
    skill is considered covered when ``tests/evals/<skill>/eval.yaml`` exists.
    ``unknown_dirs`` lists eval folders that do not correspond to a current
    skill (e.g. agent or isolated-variant fixtures) so callers can surface
    drift without treating them as skill coverage.
    """
    vally_index = {skill_name: [] for skill_name in skill_names}
    skill_name_set = set(skill_names)
    unknown_dirs: list[dict[str, str]] = []

    if not vally_evals_dir.is_dir():
        return vally_index, unknown_dirs

    for eval_dir in sorted(p for p in vally_evals_dir.iterdir() if p.is_dir()):
        if not (eval_dir / "eval.yaml").is_file():
            continue
        if eval_dir.name in skill_name_set:
            vally_index[eval_dir.name].append("eval.yaml")
        else:
            unknown_dirs.append({"dir": eval_dir.name})

    return vally_index, unknown_dirs


def extract_individual_eval_skill(plan_path: Path) -> str | None:
    """Extract the skill name from an individual eval plan."""
    content = plan_path.read_text(encoding="utf-8")
    for line in content.splitlines():
        if line.startswith("- **Skill:** `") and line.endswith("`"):
            return line[len("- **Skill:** `") : -1]
    return None


def build_individual_eval_index(
    skill_names: list[str], individual_evals_dir: Path
) -> tuple[dict[str, list[str]], list[dict[str, str]]]:
    """Map each skill to its individual eval plans."""
    individual_index = {skill_name: [] for skill_name in skill_names}
    unknown_plans: list[dict[str, str]] = []

    for plan_path in sorted(individual_evals_dir.glob("eval-*.md")):
        skill_name = extract_individual_eval_skill(plan_path)
        if not skill_name or skill_name not in individual_index:
            unknown_plans.append(
                {
                    "plan": plan_path.name,
                    "skill": skill_name or "<missing-skill-metadata>",
                }
            )
            continue

        individual_index[skill_name].append(plan_path.name)

    return individual_index, unknown_plans


def build_combined_eval_index(
    skill_names: list[str], combined_evals_dir: Path
) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    """Map each skill to the combined eval plans that mention it."""
    combined_index = {skill_name: [] for skill_name in skill_names}
    unknown_plans: list[dict[str, Any]] = []

    for plan_path in sorted(combined_evals_dir.glob("eval-*.md")):
        content = plan_path.read_text(encoding="utf-8")
        participants = [skill_name for skill_name in skill_names if skill_name in content]

        if not participants:
            unknown_plans.append(
                {
                    "plan": plan_path.name,
                    "participants": [],
                }
            )
            continue

        for skill_name in participants:
            combined_index[skill_name].append(plan_path.name)

    return combined_index, unknown_plans


def build_coverage_report(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Collect smoke, Vally, and eval coverage signals for every checked-in skill."""
    skills_dir = repo_root / "skills"
    smoke_tests_path = repo_root / "tests" / "tests.json"
    vally_evals_dir = repo_root / "tests" / "evals"
    individual_evals_dir = repo_root / "tests" / "full-eval-tests" / "plan" / "03-individual-skills"
    combined_evals_dir = repo_root / "tests" / "full-eval-tests" / "plan" / "04-combined-skills"

    skill_names = discover_skills(skills_dir)
    smoke_index, unmapped_smoke_cases = build_smoke_index(skill_names, smoke_tests_path)
    vally_index, unknown_vally_dirs = build_vally_eval_index(skill_names, vally_evals_dir)
    individual_index, unknown_individual_plans = build_individual_eval_index(skill_names, individual_evals_dir)
    combined_index, unknown_combined_plans = build_combined_eval_index(skill_names, combined_evals_dir)

    skill_rows: list[dict[str, Any]] = []
    for skill_name in skill_names:
        category = categorize_skill(skill_name)
        smoke_cases = smoke_index[skill_name]
        vally_assets = vally_index[skill_name]
        individual_plans = individual_index[skill_name]
        combined_plans = combined_index[skill_name]

        skill_rows.append(
            {
                "name": skill_name,
                "category": category,
                "smokeCovered": bool(smoke_cases),
                "smokeCases": smoke_cases,
                "vallyEvalCovered": bool(vally_assets),
                "vallyEvalAssets": vally_assets,
                "individualEvalCovered": bool(individual_plans),
                "individualEvalPlans": individual_plans,
                "combinedEvalCovered": bool(combined_plans),
                "combinedEvalPlans": combined_plans,
            }
        )

    missing_smoke = [row["name"] for row in skill_rows if not row["smokeCovered"]]
    missing_vally = [row["name"] for row in skill_rows if not row["vallyEvalCovered"]]
    missing_individual = [row["name"] for row in skill_rows if not row["individualEvalCovered"]]
    combined_participating = [row["name"] for row in skill_rows if row["combinedEvalCovered"]]
    combined_not_participating = [row["name"] for row in skill_rows if not row["combinedEvalCovered"]]

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "combinedEvalStatus": (
                "Combined eval policy is not yet encoded in the report. "
                "The report inventories current participation only and does not classify missing combined evals as debt."
            ),
        },
        "summary": {
            "skillsAudited": len(skill_rows),
            "smokeCasesAudited": len(json.loads(smoke_tests_path.read_text(encoding="utf-8"))),
            "vallyEvalsAudited": sum(len(row["vallyEvalAssets"]) for row in skill_rows),
            "individualEvalPlansAudited": len(list(individual_evals_dir.glob("eval-*.md"))),
            "combinedEvalPlansAudited": len(list(combined_evals_dir.glob("eval-*.md"))),
            "smokeCoveredCount": len(skill_rows) - len(missing_smoke),
            "smokeMissingCount": len(missing_smoke),
            "vallyEvalCoveredCount": len(skill_rows) - len(missing_vally),
            "vallyEvalMissingCount": len(missing_vally),
            "individualEvalCoveredCount": len(skill_rows) - len(missing_individual),
            "individualEvalMissingCount": len(missing_individual),
            "combinedEvalParticipatingCount": len(combined_participating),
            "combinedEvalNotParticipatingCount": len(combined_not_participating),
        },
        "gaps": {
            "missingSmoke": missing_smoke,
            "missingVallyEval": missing_vally,
            "missingIndividualEval": missing_individual,
        },
        "combinedCoverage": {
            "participatingSkills": combined_participating,
            "notParticipatingSkills": combined_not_participating,
        },
        "unmappedSmokeCases": unmapped_smoke_cases,
        "unknownVallyEvalDirs": unknown_vally_dirs,
        "unknownIndividualEvalPlans": unknown_individual_plans,
        "unknownCombinedEvalPlans": unknown_combined_plans,
        "skills": skill_rows,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render the coverage report as a concise markdown document."""
    summary = report["summary"]
    gaps = report["gaps"]
    lines = [
        "# Coverage Gap Report",
        "",
        f"**Generated:** {report['generatedAt']}",
        f"**Skills audited:** {summary['skillsAudited']}",
        f"**Smoke cases audited:** {summary['smokeCasesAudited']}",
        f"**Vally evals audited:** {summary['vallyEvalsAudited']}",
        f"**Individual eval plans audited:** {summary['individualEvalPlansAudited']}",
        f"**Combined eval plans audited:** {summary['combinedEvalPlansAudited']}",
        "",
        f"**Combined eval status:** {report['policy']['combinedEvalStatus']}",
        "",
        "## Summary",
        "",
        "| Coverage type | Covered | Missing |",
        "|---|---:|---:|",
        f"| Vally eval | {summary['vallyEvalCoveredCount']} | {summary['vallyEvalMissingCount']} |",
        f"| Individual eval | {summary['individualEvalCoveredCount']} | {summary['individualEvalMissingCount']} |",
        f"| Combined eval participation | {summary['combinedEvalParticipatingCount']} | {summary['combinedEvalNotParticipatingCount']} |",
        f"| Smoke (advisory) | {summary['smokeCoveredCount']} | {summary['smokeMissingCount']} |",
        "",
        "## Missing Vally eval coverage",
        "",
    ]

    if gaps["missingVallyEval"]:
        lines.extend(f"- `{skill_name}`" for skill_name in gaps["missingVallyEval"])
    else:
        lines.append("- None")

    lines.extend(["", "## Missing individual eval coverage", ""])
    if gaps["missingIndividualEval"]:
        lines.extend(f"- `{skill_name}`" for skill_name in gaps["missingIndividualEval"])
    else:
        lines.append("- None")

    lines.extend(["", "## Missing smoke coverage (advisory)", ""])
    if gaps["missingSmoke"]:
        lines.extend(f"- `{skill_name}`" for skill_name in gaps["missingSmoke"])
    else:
        lines.append("- None")

    lines.extend(["", "## Skills without combined eval participation (informational only)", ""])
    if report["combinedCoverage"]["notParticipatingSkills"]:
        lines.extend(f"- `{skill_name}`" for skill_name in report["combinedCoverage"]["notParticipatingSkills"])
    else:
        lines.append("- None")

    lines.extend(["", "## Smoke cases without explicit skill mapping", ""])
    if report["unmappedSmokeCases"]:
        lines.extend(f"- `{case['name']}`" for case in report["unmappedSmokeCases"])
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Per-skill coverage",
            "",
            "| Skill | Category | Vally | Individual | Combined | Smoke (advisory) |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in report["skills"]:
        lines.append(
            "| `{name}` | {category} | {vally} | {individual} | {combined} | {smoke} |".format(
                name=row["name"],
                category=row["category"],
                vally="Yes" if row["vallyEvalCovered"] else "No",
                individual="Yes" if row["individualEvalCovered"] else "No",
                combined="Yes" if row["combinedEvalCovered"] else "No",
                smoke="Yes" if row["smokeCovered"] else "No",
            )
        )

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description="Generate the skills-for-fabric coverage gap report.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Path to the repository root.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=DEFAULT_JSON_REPORT,
        help="Where to write the JSON report.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        help="Optional path for a markdown copy of the report.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print the markdown summary to stdout.",
    )
    return parser.parse_args()


def write_text_file(path: Path, content: str) -> None:
    """Write a UTF-8 text file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    """CLI entrypoint."""
    args = parse_args()
    report = build_coverage_report(args.repo_root.resolve())
    markdown = render_markdown_report(report)

    if not args.quiet:
        print(markdown, end="")

    if args.json_output:
        write_text_file(args.json_output.resolve(), json.dumps(report, indent=2))
        print(f"\nJSON report saved to: {args.json_output.resolve()}")

    if args.markdown_output:
        write_text_file(args.markdown_output.resolve(), markdown)
        print(f"Markdown report saved to: {args.markdown_output.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
