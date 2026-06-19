"""
Semantic validation tests for skill metadata and structure.
"""

import importlib.util
import sys
from textwrap import dedent

import pytest

from skill_validation import (
    analyze_common_infra_compliance,
    analyze_naming_convention,
    analyze_structural_compliance,
    detect_encoding_corruption,
    find_duplicate_triggers,
    find_semantic_conflicts,
)


@pytest.fixture(scope="module")
def structural_checks(all_skills):
    """Collect structural checks once per module for assertion messages."""
    return [
        (
            skill_name,
            analyze_structural_compliance(
                skill_data["content"],
                skill_data["frontmatter"],
                skill_name,
            ),
        )
        for skill_name, skill_data in sorted(all_skills.items())
    ]


@pytest.fixture(scope="module")
def common_infra_checks(all_skills):
    """Collect common-infra checks once per module for assertion messages."""
    return [
        (
            skill_name,
            analyze_common_infra_compliance(skill_data["content"]),
        )
        for skill_name, skill_data in sorted(all_skills.items())
    ]


@pytest.mark.semantic
def test_skill_names_match_general_pattern(all_skills):
    invalid_names = [
        skill_name
        for skill_name in sorted(all_skills)
        if not analyze_naming_convention(skill_name)["matches_general_pattern"]
    ]

    assert not invalid_names, f"Invalid skill names: {', '.join(invalid_names)}"


@pytest.mark.semantic
def test_skill_files_have_required_frontmatter(structural_checks):
    failures = []
    for skill_name, checks in structural_checks:
        missing = []
        for field in ("has_frontmatter", "has_name", "has_description"):
            if not checks[field]:
                missing.append(field)
        if missing:
            failures.append(f"{skill_name}: missing {', '.join(missing)}")

    assert not failures, "\n".join(failures)


@pytest.mark.semantic
def test_non_utility_skills_include_update_notice(structural_checks):
    missing_update_notice = [
        skill_name
        for skill_name, checks in structural_checks
        if skill_name != "check-updates" and not checks["has_update_notice"]
    ]

    assert not missing_update_notice, (
        "Missing update notice: " + ", ".join(missing_update_notice)
    )


@pytest.mark.semantic
def test_key_structure_sections_exist(structural_checks):
    failures = []
    for skill_name, checks in structural_checks:
        missing = []
        if not checks["has_must_prefer_avoid"]:
            missing.append("Must/Prefer/Avoid or equivalent sections")
        if not checks["has_examples"]:
            missing.append("examples")
        if missing:
            failures.append(f"{skill_name}: {', '.join(missing)}")

    assert not failures, "\n".join(failures)


@pytest.mark.semantic
def test_skills_reference_common_infra_guidance(common_infra_checks):
    failures = []
    for skill_name, checks in common_infra_checks:
        for issue in checks["issues"]:
            failures.append(f"{skill_name}: {issue['message']}")

    assert not failures, "\n".join(failures)


@pytest.mark.semantic
def test_trigger_phrases_are_unique(skill_index):
    duplicates = find_duplicate_triggers(skill_index)
    assert not duplicates, f"Duplicate triggers found: {duplicates}"


@pytest.mark.semantic
def test_skill_descriptions_stay_below_similarity_threshold(skill_index):
    conflicts = find_semantic_conflicts(skill_index)
    assert not conflicts, f"Semantic conflicts found: {conflicts}"


def test_common_infra_check_flags_missing_auth_references():
    content = dedent(
        """
        ## Tool Stack

        - Run `az login`
        - Acquire a token with `az account get-access-token`
        """
    )

    checks = analyze_common_infra_compliance(content)

    assert [issue["rule"] for issue in checks["issues"]] == ["auth_token_guidance"]


def test_common_infra_check_allows_shared_auth_references():
    content = dedent(
        """
        ## Prerequisite Knowledge

        - [COMMON-CORE.md](../../common/COMMON-CORE.md) — authentication, token audiences, item discovery
        - [COMMON-CLI.md](../../common/COMMON-CLI.md) — `az rest`, `az login`, token acquisition

        ### MUST DO
        - Run `az login` before using CLI auth flows
        """
    )

    checks = analyze_common_infra_compliance(content)

    assert not checks["issues"]


def test_common_infra_check_flags_missing_sqlcmd_references():
    content = dedent(
        """
        ## Tool Stack

        | Tool | Install |
        |---|---|
        | `sqlcmd` | `winget install sqlcmd` |

        > sqlcmd --version 2>/dev/null || echo "INSTALL: winget install sqlcmd"
        """
    )

    checks = analyze_common_infra_compliance(content)

    assert [issue["rule"] for issue in checks["issues"]] == ["sqlcmd_tooling_guidance"]


def test_detect_encoding_corruption_flags_mojibake_markers():
    markers = detect_encoding_corruption("# Spark \u0393\u00c7\u00f6 CLI Skill")

    assert markers == ["\u0393\u00c7\u00f6"]


def test_detect_encoding_corruption_allows_clean_utf8_punctuation():
    markers = detect_encoding_corruption("# Spark \u2014 CLI Skill")

    assert not markers


def test_quality_checker_flags_mojibake_in_nested_skill_markdown(tmp_path, repo_root, monkeypatch):
    quality_checker_path = repo_root / ".github" / "workflows" / "quality_checker.py"
    monkeypatch.setattr(sys, "platform", "linux")
    spec = importlib.util.spec_from_file_location("quality_checker_module", quality_checker_path)
    quality_checker_module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(quality_checker_module)

    skill_dir = tmp_path / "skills" / "dummy-encoding-cli"
    references_dir = skill_dir / "references"
    references_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text(
        dedent(
            """
            ---
            name: dummy-encoding-cli
            description: >
              Run a synthetic Fabric validation workflow for a dummy CLI skill.
              Use when the user wants to: (1) validate a placeholder Fabric workflow.
              Triggers: "dummy encoding"
            ---

            > **Update Check — ONCE PER SESSION (mandatory)**
            > Run the **check-updates** skill before proceeding.

            ## Must
            - Keep the output synthetic.

            ## Prefer
            - Prefer concise examples.

            ## Examples
            ```text
            User: run the dummy encoding workflow
            Assistant: provide a placeholder response
            ```
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (references_dir / "broken.md").write_text(
        "# Spark \u0393\u00c7\u00f6 Broken Heading\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    checker = quality_checker_module.QualityChecker()
    checker.scan_repository()

    messages = [issue["message"] for issue in checker.results["structural_issues"]]
    assert any("suspect encoding corruption markers" in message for message in messages)


def test_quality_checker_fails_invalid_utf8_skill_markdown(tmp_path, repo_root, monkeypatch):
    quality_checker_path = repo_root / ".github" / "workflows" / "quality_checker.py"
    monkeypatch.setattr(sys, "platform", "linux")
    spec = importlib.util.spec_from_file_location("quality_checker_module", quality_checker_path)
    quality_checker_module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(quality_checker_module)

    skill_dir = tmp_path / "skills" / "dummy-invalid-utf8-cli"
    skill_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_bytes(
        b"---\nname: dummy-invalid-utf8-cli\ndescription: test\n---\n\xff\n"
    )

    monkeypatch.chdir(tmp_path)
    checker = quality_checker_module.QualityChecker()
    passed = checker.scan_repository()

    messages = [issue["message"] for issue in checker.results["structural_issues"]]
    assert not passed
    assert checker.results["critical_count"] == 1
    assert any("SKILL.md" in message and "not valid UTF-8" in message for message in messages)


# =============================================================================
# Monitoring Skill — Domain-Specific Checks
# =============================================================================

@pytest.mark.semantic
class TestMonitoringCliSkill:
    """Validate sqldw-operations-cli covers the required queryinsights domain."""

    def test_skill_exists(self, all_skills):
        assert "sqldw-operations-cli" in all_skills

    def test_references_queryinsights_views(self, all_skills):
        content = all_skills["sqldw-operations-cli"]["content"]
        expected_views = [
            "queryinsights.exec_requests_history",
            "queryinsights.long_running_queries",
        ]
        for view in expected_views:
            assert view in content, f"Missing queryinsights view: {view}"

    def test_has_fabric_constraints_section(self, all_skills):
        content = all_skills["sqldw-operations-cli"]["content"]
        assert "Fabric DW Constraints" in content

    def test_has_agentic_workflows(self, all_skills):
        content = all_skills["sqldw-operations-cli"]["content"]
        assert "Agentic Workflows" in content
