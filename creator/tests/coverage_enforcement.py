#!/usr/bin/env python3
"""
Enforce new-skill ownership and coverage policy with governed allow-missing debt.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON_REPORT = REPO_ROOT / "coverage-enforcement.json"
DEFAULT_POLICY_PATH = REPO_ROOT / ".github" / "coverage-policy.yml"
ALLOWED_ALLOW_MISSING_STATUSES = {"debt", "exempt"}
COVERAGE_KINDS = ("smoke", "vallyEval", "individualEval", "combinedEval")
COVERAGE_LABELS = {
    "smoke": "smoke coverage",
    "vallyEval": "Vally eval coverage",
    "individualEval": "individual eval coverage",
    "combinedEval": "combined eval coverage",
}
GUIDANCE_PATHS = {
    "ownership": ".github/skill-ownership.yml",
    "smoke": "tests/tests.json",
    "vallyEval": "tests/evals/",
    "individualEval": "tests/full-eval-tests/plan/03-individual-skills/",
    "combinedEval": "tests/full-eval-tests/plan/04-combined-skills/",
}


sys.path.insert(0, str(Path(__file__).parent))

from coverage_gap_report import (  # noqa: E402
    build_combined_eval_index,
    build_individual_eval_index,
    build_smoke_index,
    build_vally_eval_index,
    categorize_skill,
    discover_skills,
)
from skill_ownership_manifest import load_skill_ownership_manifest  # noqa: E402


def write_text_file(path: Path, content: str) -> None:
    """Write UTF-8 text output, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_git(repo_root: Path, args: list[str]) -> str:
    """Run git and return stdout or raise a useful error."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed with exit code {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    """Validate that a YAML object is a mapping."""
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping.")
    return value


def load_coverage_policy(policy_path: Path) -> dict[str, Any]:
    """Load and validate coverage policy YAML."""
    raw = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    policy = raw if isinstance(raw, dict) else {}

    defaults = _require_mapping(policy.get("defaults", {}), "defaults")
    allow_missing = _require_mapping(policy.get("allowMissing", {}), "allowMissing")

    validated_allow_missing: dict[str, dict[str, dict[str, str]]] = {}
    for kind in COVERAGE_KINDS:
        kind_entries = _require_mapping(allow_missing.get(kind, {}), f"allowMissing.{kind}")
        validated_kind_entries: dict[str, dict[str, str]] = {}
        for skill_name, entry in kind_entries.items():
            entry_mapping = _require_mapping(entry, f"allowMissing.{kind}.{skill_name}")
            status = entry_mapping.get("status")
            reason = str(entry_mapping.get("reason", "")).strip()
            if status not in ALLOWED_ALLOW_MISSING_STATUSES:
                raise ValueError(
                    f"allowMissing.{kind}.{skill_name}.status must be one of "
                    f"{sorted(ALLOWED_ALLOW_MISSING_STATUSES)}."
                )
            if not reason:
                raise ValueError(f"allowMissing.{kind}.{skill_name}.reason must be non-empty.")
            validated_kind_entries[str(skill_name)] = {
                "status": str(status),
                "reason": reason,
            }
        validated_allow_missing[kind] = validated_kind_entries

    return {
        "schemaVersion": policy.get("schemaVersion"),
        "description": str(policy.get("description", "")).strip(),
        "defaults": {
            "requireSmokeForNewSkills": bool(defaults.get("requireSmokeForNewSkills", False)),
            "requireVallyEvalForNewSkills": bool(
                defaults.get("requireVallyEvalForNewSkills", True)
            ),
            "requireIndividualEvalForNewSkills": bool(
                defaults.get("requireIndividualEvalForNewSkills", True)
            ),
            "requireCombinedEvalWhenPairedSkillExists": bool(
                defaults.get("requireCombinedEvalWhenPairedSkillExists", True)
            ),
        },
        "allowMissing": validated_allow_missing,
    }


def discover_skills_at_ref(repo_root: Path, git_ref: str) -> list[str]:
    """Return skill names present at a given git ref."""
    output = _run_git(repo_root, ["ls-tree", "-r", "--name-only", git_ref, "--", "skills"])
    skills = {
        parts[1]
        for raw_path in output.splitlines()
        for parts in [PurePosixPath(raw_path).parts]
        if len(parts) >= 3 and parts[0] == "skills" and parts[-1] == "SKILL.md"
    }
    return sorted(skills)


def discover_changed_skills(repo_root: Path, base_ref: str, current_skill_names: list[str]) -> list[str]:
    """Return current skill names whose folders changed since base_ref."""
    output = _run_git(repo_root, ["diff", "--name-only", f"{base_ref}...HEAD", "--", "skills"])
    current_skill_set = set(current_skill_names)
    changed = {
        parts[1]
        for raw_path in output.splitlines()
        for parts in [PurePosixPath(raw_path).parts]
        if len(parts) >= 2 and parts[0] == "skills" and parts[1] in current_skill_set
    }
    return sorted(changed)


def paired_skill_name(skill_name: str) -> str | None:
    """Return the paired authoring/consumption skill name when applicable."""
    if "-authoring-" in skill_name:
        return skill_name.replace("-authoring-", "-consumption-", 1)
    if "-consumption-" in skill_name:
        return skill_name.replace("-consumption-", "-authoring-", 1)
    if "-operations-" in skill_name:
        return None  # operations skills have no automatic pair
    return None


def load_coverage_inventory(repo_root: Path) -> dict[str, Any]:
    """Collect coverage indexes and manifest metadata for the current repo state."""
    skill_names = discover_skills(repo_root / "skills")
    smoke_index, _ = build_smoke_index(skill_names, repo_root / "tests" / "tests.json")
    vally_index, _ = build_vally_eval_index(skill_names, repo_root / "tests" / "evals")
    individual_index, _ = build_individual_eval_index(
        skill_names, repo_root / "tests" / "full-eval-tests" / "plan" / "03-individual-skills"
    )
    combined_index, _ = build_combined_eval_index(
        skill_names, repo_root / "tests" / "full-eval-tests" / "plan" / "04-combined-skills"
    )
    manifest = load_skill_ownership_manifest(repo_root / ".github" / "skill-ownership.yml")

    manifest_skills = manifest.get("skills", {})
    if not isinstance(manifest_skills, dict):
        manifest_skills = {}

    return {
        "skillNames": skill_names,
        "smokeIndex": smoke_index,
        "vallyIndex": vally_index,
        "individualIndex": individual_index,
        "combinedIndex": combined_index,
        "manifestSkills": manifest_skills,
    }


def _missing_guidance(kind: str, skill_name: str) -> str:
    """Return contributor guidance for a missing requirement."""
    if kind == "smoke":
        return (
            f"Add a smoke case for `{skill_name}` in `{GUIDANCE_PATHS['smoke']}` or record an "
            f"explicit exempt entry in `.github/coverage-policy.yml`."
        )
    if kind == "vallyEval":
        return (
            f"Add a Vally eval for `{skill_name}` at "
            f"`{GUIDANCE_PATHS['vallyEval']}{skill_name}/eval.yaml` (see `tests/evals/README.md`) "
            f"or record an explicit exempt entry in `.github/coverage-policy.yml`."
        )
    if kind == "individualEval":
        return (
            f"Add an individual eval plan for `{skill_name}` under "
            f"`{GUIDANCE_PATHS['individualEval']}`."
        )
    if kind == "combinedEval":
        return (
            f"Add a combined eval plan for the paired workflow under "
            f"`{GUIDANCE_PATHS['combinedEval']}` or record an explicit exempt entry in "
            f"`.github/coverage-policy.yml`."
        )
    raise ValueError(f"Unsupported coverage kind: {kind}")


def _evaluate_coverage_requirement(
    *,
    kind: str,
    skill_name: str,
    has_coverage: bool,
    required: bool,
    allow_missing_entries: dict[str, dict[str, str]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Evaluate one coverage requirement for a skill.

    ``required`` already folds in new-skill status (the caller passes
    ``require_<kind> and is_new_skill``), so the stale-on-arrival and
    new-debt guardrails below gate on ``required``: they apply only to a new
    skill of a kind that is actually required, and never to an advisory kind.
    """
    label = COVERAGE_LABELS[kind]
    allowance = allow_missing_entries.get(skill_name)
    violations: list[dict[str, str]] = []

    if has_coverage:
        result = {
            "required": required,
            "status": "present",
            "path": GUIDANCE_PATHS[kind],
            "message": f"`{skill_name}` has {label}.",
        }
        # If a NEW skill of a REQUIRED kind ships with coverage AND an
        # allow-missing entry, the entry is stale on arrival -- it should never
        # have been added. The baseline stale check filters new skills out (they
        # aren't in base_ref yet), so without this check the issue silently
        # merges and breaks subsequent PRs once the skill is part of the base
        # ref. Skipped when the kind is not required (advisory): an advisory
        # kind enforces no baseline, so an inert allow-missing entry is harmless.
        if required and skill_name in allow_missing_entries:
            violations.append(
                {
                    "scope": "changed-skill",
                    "skill": skill_name,
                    "kind": kind,
                    "message": (
                        f"`{skill_name}` is a new skill that already has {label} -- "
                        f"remove its `allowMissing.{kind}` entry from "
                        f"`.github/coverage-policy.yml`."
                    ),
                }
            )
        return result, violations

    if allowance:
        allowance_status = allowance["status"]
        message = (
            f"`{skill_name}` is allowed to miss {label} as {allowance_status}: {allowance['reason']}"
        )
        result = {
            "required": required,
            "status": allowance_status,
            "path": GUIDANCE_PATHS[kind],
            "message": message,
        }
        if required and allowance_status == "debt":
            violations.append(
                {
                    "scope": "changed-skill",
                    "skill": skill_name,
                    "kind": kind,
                    "message": (
                        f"`{skill_name}` is a new skill and cannot add {label} debt. "
                        f"{_missing_guidance(kind, skill_name)}"
                    ),
                }
            )
        return result, violations

    if not required:
        return (
            {
                "required": False,
                "status": "not-required",
                "path": GUIDANCE_PATHS[kind],
                "message": f"`{skill_name}` is not required to add {label} under current policy.",
            },
            violations,
        )

    violations.append(
        {
            "scope": "changed-skill",
            "skill": skill_name,
            "kind": kind,
            "message": f"`{skill_name}` is missing required {label}. {_missing_guidance(kind, skill_name)}",
        }
    )
    return (
        {
            "required": True,
            "status": "missing",
            "path": GUIDANCE_PATHS[kind],
            "message": f"`{skill_name}` is missing required {label}.",
        },
        violations,
    )


def _build_baseline_section(
    *,
    kind: str,
    current_missing: list[str],
    allow_missing_entries: dict[str, dict[str, str]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Validate that current repo gaps are governed by allow-missing entries."""
    current_missing_set = set(current_missing)
    tracked_set = set(allow_missing_entries.keys())
    untracked = sorted(current_missing_set - tracked_set)
    stale = sorted(tracked_set - current_missing_set)

    violations = [
        {
            "scope": "baseline",
            "skill": skill_name,
            "kind": kind,
            "message": (
                f"`{skill_name}` is currently missing {COVERAGE_LABELS[kind]} but is not tracked in "
                f"`.github/coverage-policy.yml`."
            ),
        }
        for skill_name in untracked
    ]
    violations.extend(
        {
            "scope": "baseline",
            "skill": skill_name,
            "kind": kind,
            "message": (
                f"`{skill_name}` no longer needs its tracked {COVERAGE_LABELS[kind]} allowance in "
                f"`.github/coverage-policy.yml`."
            ),
        }
        for skill_name in stale
    )

    return (
        {
            "currentMissing": current_missing,
            "trackedAllowMissing": sorted(tracked_set),
            "untrackedMissing": untracked,
            "staleAllowMissing": stale,
        },
        violations,
    )


def build_enforcement_report(
    repo_root: Path = REPO_ROOT,
    *,
    base_ref: str | None = None,
    policy_path: Path | None = None,
) -> dict[str, Any]:
    """Build the repo coverage enforcement report."""
    repo_root = repo_root.resolve()
    resolved_policy_path = policy_path.resolve() if policy_path else repo_root / ".github" / "coverage-policy.yml"
    policy = load_coverage_policy(resolved_policy_path)
    inventory = load_coverage_inventory(repo_root)
    skill_names = inventory["skillNames"]
    smoke_index = inventory["smokeIndex"]
    vally_index = inventory["vallyIndex"]
    individual_index = inventory["individualIndex"]
    combined_index = inventory["combinedIndex"]
    manifest_skills = inventory["manifestSkills"]

    base_skill_names = discover_skills_at_ref(repo_root, base_ref) if base_ref else skill_names
    changed_skill_names = (
        discover_changed_skills(repo_root, base_ref, skill_names) if base_ref else []
    )
    base_skill_set = set(base_skill_names)
    changed_skill_set = set(changed_skill_names)
    new_skill_set = changed_skill_set - base_skill_set

    require_smoke = policy["defaults"]["requireSmokeForNewSkills"]
    require_vally = policy["defaults"]["requireVallyEvalForNewSkills"]
    require_individual = policy["defaults"]["requireIndividualEvalForNewSkills"]

    smoke_allow_missing = policy["allowMissing"]["smoke"]
    vally_allow_missing = policy["allowMissing"]["vallyEval"]
    individual_allow_missing = policy["allowMissing"]["individualEval"]
    combined_allow_missing = policy["allowMissing"]["combinedEval"]

    current_missing_smoke = sorted(
        skill_name
        for skill_name in skill_names
        if skill_name in base_skill_set and not smoke_index[skill_name]
    )
    current_missing_vally = sorted(
        skill_name
        for skill_name in skill_names
        if skill_name in base_skill_set and not vally_index[skill_name]
    )
    current_missing_individual = sorted(
        skill_name
        for skill_name in skill_names
        if skill_name in base_skill_set and not individual_index[skill_name]
    )

    baseline_smoke, baseline_smoke_violations = _build_baseline_section(
        kind="smoke",
        current_missing=current_missing_smoke,
        allow_missing_entries={
            skill_name: entry
            for skill_name, entry in smoke_allow_missing.items()
            if skill_name in base_skill_set
        },
    )
    baseline_vally, baseline_vally_violations = _build_baseline_section(
        kind="vallyEval",
        current_missing=current_missing_vally,
        allow_missing_entries={
            skill_name: entry
            for skill_name, entry in vally_allow_missing.items()
            if skill_name in base_skill_set
        },
    )
    baseline_individual, baseline_individual_violations = _build_baseline_section(
        kind="individualEval",
        current_missing=current_missing_individual,
        allow_missing_entries={
            skill_name: entry
            for skill_name, entry in individual_allow_missing.items()
            if skill_name in base_skill_set
        },
    )

    # Baseline debt for a coverage kind is enforced only while that kind is
    # required. This keeps an advisory kind (e.g. smoke after the Vally cutover,
    # requireSmokeForNewSkills=false) from turning into a baseline landmine:
    # new skills merge without it, then trip an untracked-baseline violation on
    # the next unrelated PR.
    violations: list[dict[str, Any]] = []
    if require_smoke:
        violations.extend(baseline_smoke_violations)
    if require_vally:
        violations.extend(baseline_vally_violations)
    if require_individual:
        violations.extend(baseline_individual_violations)
    changed_skills: list[dict[str, Any]] = []

    for skill_name in changed_skill_names:
        is_new_skill = skill_name in new_skill_set
        counterpart_name = paired_skill_name(skill_name)
        counterpart_exists = bool(counterpart_name and counterpart_name in skill_names)
        combined_required = (
            policy["defaults"]["requireCombinedEvalWhenPairedSkillExists"] and counterpart_exists
        )

        metadata = manifest_skills.get(skill_name)
        ownership_present = (
            isinstance(metadata, dict)
            and bool(metadata.get("owningTeam"))
            and bool(metadata.get("area"))
        )
        ownership = {
            "required": is_new_skill,
            "status": "present" if ownership_present else "missing",
            "path": GUIDANCE_PATHS["ownership"],
            "message": (
                f"`{skill_name}` is present in `.github/skill-ownership.yml`."
                if ownership_present
                else f"`{skill_name}` is missing from `.github/skill-ownership.yml`."
            ),
        }
        if is_new_skill and not ownership_present:
            violations.append(
                {
                    "scope": "changed-skill",
                    "skill": skill_name,
                    "kind": "ownership",
                    "message": (
                        f"`{skill_name}` is a new skill and must be added to "
                        f"`{GUIDANCE_PATHS['ownership']}` with `owningTeam` and `area`."
                    ),
                }
            )

        smoke, smoke_violations = _evaluate_coverage_requirement(
            kind="smoke",
            skill_name=skill_name,
            has_coverage=bool(smoke_index[skill_name]),
            required=bool(require_smoke and is_new_skill),
            allow_missing_entries=smoke_allow_missing,
        )
        vally_eval, vally_eval_violations = _evaluate_coverage_requirement(
            kind="vallyEval",
            skill_name=skill_name,
            has_coverage=bool(vally_index[skill_name]),
            required=bool(require_vally and is_new_skill),
            allow_missing_entries=vally_allow_missing,
        )
        individual_eval, individual_eval_violations = _evaluate_coverage_requirement(
            kind="individualEval",
            skill_name=skill_name,
            has_coverage=bool(individual_index[skill_name]),
            required=bool(require_individual and is_new_skill),
            allow_missing_entries=individual_allow_missing,
        )
        combined_eval, combined_eval_violations = _evaluate_coverage_requirement(
            kind="combinedEval",
            skill_name=skill_name,
            has_coverage=bool(combined_index[skill_name]),
            required=bool(combined_required and is_new_skill),
            allow_missing_entries=combined_allow_missing,
        )

        skill_violations = [
            *smoke_violations,
            *vally_eval_violations,
            *individual_eval_violations,
            *combined_eval_violations,
        ]
        violations.extend(skill_violations)

        changed_skills.append(
            {
                "name": skill_name,
                "category": categorize_skill(skill_name),
                "isNew": is_new_skill,
                "pairedSkill": counterpart_name if counterpart_exists else None,
                "ownership": ownership,
                "smoke": smoke,
                "vallyEval": vally_eval,
                "individualEval": individual_eval,
                "combinedEval": combined_eval,
                "blockingViolationCount": len(skill_violations)
                + int(is_new_skill and not ownership_present),
            }
        )

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "overallStatus": "FAILED" if violations else "PASSED",
        "baseRef": base_ref,
        "policy": policy,
        "changedSkills": changed_skills,
        "summary": {
            "skillCount": len(skill_names),
            "changedSkillCount": len(changed_skill_names),
            "newSkillCount": len(new_skill_set),
            "violationCount": len(violations),
        },
        "baseline": {
            "smoke": baseline_smoke,
            "vallyEval": baseline_vally,
            "individualEval": baseline_individual,
        },
        "violations": violations,
    }


def render_text_report(report: dict[str, Any]) -> str:
    """Render a concise text summary for local CLI use."""
    summary = report["summary"]
    lines = [
        "Coverage enforcement report",
        "===========================",
        f"Status: {report['overallStatus']}",
        f"Base ref: {report['baseRef'] or '<none>'}",
        f"Skills audited: {summary['skillCount']}",
        f"Changed skills: {summary['changedSkillCount']}",
        f"New skills: {summary['newSkillCount']}",
        f"Violations: {summary['violationCount']}",
        "",
        "Baseline",
        "--------",
        (
            f"Smoke allow-missing: {len(report['baseline']['smoke']['trackedAllowMissing'])} tracked, "
            f"{len(report['baseline']['smoke']['untrackedMissing'])} untracked, "
            f"{len(report['baseline']['smoke']['staleAllowMissing'])} stale"
        ),
        (
            "Vally eval allow-missing: "
            f"{len(report['baseline']['vallyEval']['trackedAllowMissing'])} tracked, "
            f"{len(report['baseline']['vallyEval']['untrackedMissing'])} untracked, "
            f"{len(report['baseline']['vallyEval']['staleAllowMissing'])} stale"
        ),
        (
            "Individual eval allow-missing: "
            f"{len(report['baseline']['individualEval']['trackedAllowMissing'])} tracked, "
            f"{len(report['baseline']['individualEval']['untrackedMissing'])} untracked, "
            f"{len(report['baseline']['individualEval']['staleAllowMissing'])} stale"
        ),
    ]

    if report["changedSkills"]:
        lines.extend(["", "Changed skills", "--------------"])
        for skill in report["changedSkills"]:
            prefix = "[new]" if skill["isNew"] else "[existing]"
            lines.append(
                " ".join(
                    [
                        prefix,
                        skill["name"],
                        f"ownership={skill['ownership']['status']}",
                        f"smoke={skill['smoke']['status']}",
                        f"vally={skill['vallyEval']['status']}",
                        f"individual={skill['individualEval']['status']}",
                        f"combined={skill['combinedEval']['status']}",
                    ]
                )
            )

    if report["violations"]:
        lines.extend(["", "Violations", "----------"])
        for violation in report["violations"]:
            lines.append(f"- {violation['message']}")

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser(
        description="Enforce skills-for-fabric ownership and coverage policy."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Path to the repository root.",
    )
    parser.add_argument(
        "--base-ref",
        help="Optional git ref used to detect changed and new skills.",
    )
    parser.add_argument(
        "--policy-path",
        type=Path,
        default=None,
        help="Path to the coverage policy YAML.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=DEFAULT_JSON_REPORT,
        help="Where to write the JSON report.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print the text summary to stdout.",
    )
    return parser.parse_args()


def build_degraded_report(*, base_ref: str | None, error_message: str) -> dict[str, Any]:
    """Build a degraded report when enforcement cannot run (e.g. git failure).

    The shape mirrors the fields the sticky-comment renderer in
    ``quality-check.yml`` reads, so it can render a coherent message instead
    of cascading on a missing file.
    """
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "overallStatus": "ERROR",
        "error": error_message,
        "baseRef": base_ref,
        "policy": None,
        "changedSkills": [],
        "summary": {
            "skillCount": 0,
            "changedSkillCount": 0,
            "newSkillCount": 0,
            "violationCount": 0,
        },
        "baseline": None,
        "violations": [],
    }


def main() -> int:
    """CLI entrypoint."""
    args = parse_args()
    try:
        report = build_enforcement_report(
            args.repo_root.resolve(),
            base_ref=args.base_ref,
            policy_path=args.policy_path,
        )
    except (RuntimeError, OSError) as exc:
        error_message = str(exc)
        degraded = build_degraded_report(base_ref=args.base_ref, error_message=error_message)
        print(
            f"ERROR: coverage enforcement could not run: {error_message}",
            file=sys.stderr,
        )
        if args.json_output:
            write_text_file(args.json_output.resolve(), json.dumps(degraded, indent=2))
            print(
                f"Degraded JSON report saved to: {args.json_output.resolve()}",
                file=sys.stderr,
            )
        return 1

    text_report = render_text_report(report)

    if not args.quiet:
        print(text_report, end="")

    if args.json_output:
        write_text_file(args.json_output.resolve(), json.dumps(report, indent=2))
        print(f"JSON report saved to: {args.json_output.resolve()}")

    return 1 if report["overallStatus"] == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
