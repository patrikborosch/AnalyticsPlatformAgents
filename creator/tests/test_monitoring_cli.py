"""
CLI smoke tests for sqldw-operations-cli.
Validates the skill structure, query references, and content alignment.
No external dependencies or MCP server required.
"""
import pytest
from pathlib import Path


@pytest.fixture(scope="module")
def skill_content():
    """Load sqldw-operations-cli SKILL.md content."""
    skill_path = Path(__file__).resolve().parent.parent / "skills" / "sqldw-operations-cli" / "SKILL.md"
    return skill_path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def query_reference_content():
    """Load sqldw-operations-cli query-reference.md content."""
    ref_path = Path(__file__).resolve().parent.parent / "skills" / "sqldw-operations-cli" / "references" / "query-reference.md"
    return ref_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

EXPECTED_QUERYINSIGHTS_VIEWS = [
    "queryinsights.long_running_queries",
    "queryinsights.exec_requests_history",
    "queryinsights.sql_pool_insights",
]

EXPECTED_ANALYSIS_SECTIONS = [
    "Long-Running Queries",
    "Top Resource Consumers",
    "Top Users Insights",
    "Compare Recent vs Baseline",
    "Cache Warmth",
    "Cluster Key",
    "Pressure Window",
]


@pytest.mark.semantic
class TestSkillStructure:
    """Verify the CLI skill has proper structure."""

    def test_skill_file_exists(self, skill_content):
        assert len(skill_content) > 0

    def test_query_reference_exists(self, query_reference_content):
        assert len(query_reference_content) > 0

    def test_uses_sqlcmd(self, skill_content):
        assert "sqlcmd" in skill_content, "Skill should reference sqlcmd for CLI execution"

    def test_no_mcp_references(self, skill_content):
        assert "MCP" not in skill_content, "CLI skill should not reference MCP server"
        assert "mcp" not in skill_content.lower().replace("approx_count", ""), \
            "CLI skill should not reference MCP server"

    def test_uses_queryinsights(self, skill_content):
        for view in EXPECTED_QUERYINSIGHTS_VIEWS:
            assert view in skill_content, f"Skill should reference {view}"


@pytest.mark.semantic
class TestAnalysisCoverage:
    """Verify all analysis types are covered in the skill."""

    def test_all_sections_present(self, skill_content):
        for section in EXPECTED_ANALYSIS_SECTIONS:
            assert section in skill_content, f"Missing analysis section: {section}"

    def test_all_sections_in_reference(self, query_reference_content):
        for section in EXPECTED_ANALYSIS_SECTIONS:
            assert section in query_reference_content, f"Missing reference section: {section}"


@pytest.mark.semantic
class TestFabricConstraints:
    """Verify the skill documents Fabric DW constraints."""

    def test_constraints_section(self, skill_content):
        assert "Fabric DW Constraints" in skill_content

    def test_no_unsupported_recommendations(self, skill_content):
        assert "Do NOT Recommend" in skill_content or "NEVER recommend" in skill_content

    def test_ctas_for_clustering(self, skill_content):
        assert "CLUSTER BY" in skill_content
        assert "CTAS" in skill_content or "CREATE TABLE" in skill_content
