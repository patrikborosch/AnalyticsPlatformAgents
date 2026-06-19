"""
Routing tests for FabricSkills.
Validates that user prompts route to the correct skill based on trigger keywords
and description matching. No external dependencies required.
"""
import pytest
import json
import re
from pathlib import Path


@pytest.fixture(scope="module")
def test_cases():
    """Load test cases from tests.json."""
    tests_json = Path(__file__).parent / "tests.json"
    return json.loads(tests_json.read_text(encoding="utf-8"))


def _score_skill(prompt: str, skill_data: dict) -> float:
    """Score how well a prompt matches a skill's description and content."""
    prompt_lower = prompt.lower()
    desc = skill_data["description"].lower()
    content = skill_data["content"].lower()

    score = 0.0

    # Extract trigger phrases from description (text after "Triggers:")
    trigger_match = re.search(r'triggers?:\s*(.+?)(?:\.\s*$|\Z)', desc, re.DOTALL)
    if trigger_match:
        trigger_text = trigger_match.group(1)
        triggers = [t.strip().strip('"').strip("'") for t in trigger_text.split(",")]
        for trigger in triggers:
            trigger_words = trigger.strip().split()
            matches = sum(1 for w in trigger_words if w in prompt_lower)
            if matches == len(trigger_words):
                score += 10.0  # Full trigger match
            elif matches > 0:
                score += matches * 2.0  # Partial trigger match

    # Check description keywords
    desc_words = set(re.findall(r'\b[a-z]{3,}\b', desc))
    prompt_words = set(re.findall(r'\b[a-z]{3,}\b', prompt_lower))
    overlap = desc_words & prompt_words
    score += len(overlap) * 0.5

    # Skill name tokens in prompt
    name_tokens = skill_data["name"].replace("-", " ").split()
    name_matches = sum(1 for t in name_tokens if t in prompt_lower)
    score += name_matches * 1.0

    return score


def _route_prompt(prompt: str, all_skills: dict) -> list[str]:
    """Route a prompt to the best matching skill(s)."""
    scores = {}
    for skill_name, data in all_skills.items():
        scores[skill_name] = _score_skill(prompt, data)

    if not scores:
        return []

    max_score = max(scores.values())
    if max_score == 0:
        return []

    # Return skills within 80% of the top score
    threshold = max_score * 0.8
    return sorted(
        [name for name, s in scores.items() if s >= threshold],
        key=lambda n: scores[n],
        reverse=True,
    )


# =============================================================================
# Routing Accuracy Tests
# =============================================================================

@pytest.mark.semantic
class TestPromptRouting:
    """Verify prompts from tests.json route to their expected skills."""

    # Prompts that are ambiguous for a simple keyword router (would need LLM)
    KNOWN_HARD = {
        "spark-consumption-livy-sanity",  # "Livy" not unique enough vs authoring
        "eventhouse-consumption-basic-query",  # keyword router scores fabriciq higher (large skill body)
        "eventhouse-consumption-analytical-query",  # same -- generic query words inflate fabriciq score
        "synapse-migration-lake-database-routing",  # generic SQL/lake terms confuse the keyword router
        "spark-authoring-notebook-code-sql-crosslh",  # SQL terms score sqldw-consumption higher
        "eventstream-authoring-create-basic",  # generic create wording scores activator higher
        "search-consumption-find-lakehouse",  # generic workspace/item terms score activator higher
        "powerbi-report-planning-basic",  # report planning is not separable by keyword overlap alone
        "powerbi-report-management-publish-local-pbip",  # report/semantic-model overlap is expected
    }

    def test_routing_accuracy(self, all_skills, test_cases):
        """Each test case prompt should route to its expected skill."""
        failures = []
        for tc in test_cases:
            if tc["name"] in self.KNOWN_HARD:
                continue
            expected = tc.get("expectedSkills", [])
            if not expected:
                continue  # Skip tests without expected skills (e.g., agent tests)
            routed = _route_prompt(tc["prompt"], all_skills)
            for exp_skill in expected:
                if exp_skill not in routed[:3]:
                    failures.append(
                        f"  {tc['name']}: expected '{exp_skill}' in top-3 but got {routed[:3]}"
                    )
        assert not failures, "Routing failures:\n" + "\n".join(failures)


@pytest.mark.semantic
class TestMonitoringCliRouting:
    """Verify monitoring-specific prompts route to sqldw-operations-cli."""

    MONITORING_PROMPTS = [
        "What are the slowest queries in my warehouse?",
        "Analyze execution plans for long-running queries",
        "Which DW queries consumed the most CPU based on queryinsights?",
        "Run a DW performance baseline comparison for my warehouse",
        "Were there any SQL pool pressure events in my warehouse?",
        "Which tables should I cluster for better performance?",
        "Get Fabric DW best practices for ingestion",
        "Show me cache warmth analysis for my warehouse",
    ]
    KNOWN_HARD = {
        "Analyze execution plans for long-running queries",
    }

    def test_monitoring_prompts_route_correctly(self, all_skills):
        """Monitoring-themed prompts should route to sqldw-operations-cli."""
        failures = []
        for prompt in self.MONITORING_PROMPTS:
            if prompt in self.KNOWN_HARD:
                continue
            routed = _route_prompt(prompt, all_skills)
            if "sqldw-operations-cli" not in routed[:3]:
                failures.append(f"  '{prompt}' -> {routed[:3]}")
        assert not failures, (
            "Prompts not routed to sqldw-operations-cli:\n" + "\n".join(failures)
        )


@pytest.mark.semantic
class TestSparkOperationsRouting:
    """Verify diagnostic prompts route to spark-operations-cli."""

    DIAGNOSTIC_PROMPTS = [
        "My Fabric notebook run failed; debug the Spark job and show the failure reason.",
        "Check Spark session health because my Livy session is stuck in starting.",
        "Diagnose a slow Spark query with Spark Advisor and resource usage metrics.",
        "Analyze Spark shuffle spill and data skew for a failed notebook execution.",
        "Diagnose the most recent failed pipeline run and identify which Spark activity caused the failure.",
        "Review the health and diagnose failures across the past operation runs for my lakehouse.",
        "Set up a local Spark History Server to inspect DAG and SQL plans for a Fabric Spark session.",
    ]

    def test_diagnostic_prompts_route_correctly(self, all_skills):
        """Diagnostic prompts should route to spark-operations-cli."""
        failures = []
        for prompt in self.DIAGNOSTIC_PROMPTS:
            routed = _route_prompt(prompt, all_skills)
            if "spark-operations-cli" not in routed[:3]:
                failures.append(f"  '{prompt}' -> {routed[:3]}")
        assert not failures, (
            "Prompts not routed to spark-operations-cli:\n" + "\n".join(failures)
        )


@pytest.mark.semantic
class TestDataflowsAuthoringRouting:
    """Verify connection-creation and preview-before-save prompts route to dataflows-authoring-cli."""

    CONNECTION_CREATION_PROMPTS = [
        "Create a Fabric data source connection for a SQL Server using az rest",
        "How do I author a Fabric dataflow connection programmatically using POST /v1/connections?",
        "Show me the supportedConnectionTypes recipe for binding a connection to a Dataflow Gen2",
        "Generate a Fabric connection request body with passwordReference for a Power Query M dataflow",
    ]

    # Author-time preview prompts. Each must use authoring-specific phrasing
    # (preview-before-save, customMashupDocument, before updateDefinition) so that
    # the consumption skill's executeQuery recipes do not steal the route.
    PREVIEW_BEFORE_SAVE_PROMPTS = [
        "Preview my Power Query M mashup before save via updateDefinition for my Dataflow Gen2",
        "Test the candidate customMashupDocument with executeQuery before I call updateDefinition on the dataflow",
        "Walk me through the author-preview-save loop for editing a Dataflow Gen2 mashup",
        "Validate my Power Query M section document against the bound connections before persisting the new dataflow definition",
    ]

    def test_connection_creation_prompts_route_correctly(self, all_skills):
        """Connection-creation prompts should route to dataflows-authoring-cli."""
        failures = []
        for prompt in self.CONNECTION_CREATION_PROMPTS:
            routed = _route_prompt(prompt, all_skills)
            if not routed or routed[0] != "dataflows-authoring-cli":
                failures.append(f"  '{prompt}' -> {routed[:3]}")
        assert not failures, (
            "Prompts not routed to dataflows-authoring-cli:\n" + "\n".join(failures)
        )

    def test_preview_before_save_prompts_route_correctly(self, all_skills):
        """Preview-before-save prompts (author-time executeQuery loop) should route to dataflows-authoring-cli, not consumption."""
        failures = []
        for prompt in self.PREVIEW_BEFORE_SAVE_PROMPTS:
            routed = _route_prompt(prompt, all_skills)
            if not routed or routed[0] != "dataflows-authoring-cli":
                failures.append(f"  '{prompt}' -> {routed[:3]}")
        assert not failures, (
            "Author-time preview prompts not routed to dataflows-authoring-cli:\n" + "\n".join(failures)
        )

    OUTPUT_DESTINATION_PROMPTS = [
        "Configure a dataflow output destination to write results to a Lakehouse table",
        "How do I set up a DataDestinations annotation for a Dataflow Gen2 writing to ADX?",
        "Create a dataflow that writes to a Warehouse table using az rest",
        "Set up a dataflow to write query results to a file in Lakehouse Files",
    ]

    def test_output_destination_prompts_route_correctly(self, all_skills):
        """Output-destination prompts should route to dataflows-authoring-cli."""
        failures = []
        for prompt in self.OUTPUT_DESTINATION_PROMPTS:
            routed = _route_prompt(prompt, all_skills)
            if not routed or routed[0] != "dataflows-authoring-cli":
                failures.append(f"  '{prompt}' -> {routed[:3]}")
        assert not failures, (
            "OD prompts not routed to dataflows-authoring-cli:\n" + "\n".join(failures)
        )


@pytest.mark.semantic
class TestDataflowsConsumptionRouting:
    """Verify executeQuery / Arrow / inspection prompts route to dataflows-consumption-cli, not authoring."""

    # Ad-hoc query execution and Arrow parsing prompts. Phrased to be clearly
    # *consumption* (fetch rows / parse Arrow response) — no author-time
    # update / customMashupDocument-before-save semantics — so the
    # dataflows-authoring-cli preview-before-save recipes don't steal the route.
    EXECUTE_QUERY_PROMPTS = [
        "Execute the dataflow query 'Customers' and parse the Apache Arrow response into rows and columns",
        "Run executeQuery against my existing Dataflow Gen2 to retrieve the rows of the Sales query",
        "Use the dataflows executeQuery endpoint to fetch data from a Dataflow Gen2 and decode the Arrow IPC stream",
        "Parse the dataflow Arrow response from executeQuery into a CSV for downstream analysis",
    ]

    # Monitoring / inspection prompts (refresh history, definition decode).
    INSPECTION_PROMPTS = [
        "Show me the refresh history for my Fabric Dataflow Gen2 and the last refresh status",
        "List all dataflows in my Fabric workspace and report their parameters",
        "Inspect a Dataflow Gen2 definition and decode the Power Query M mashup",
    ]

    def test_execute_query_prompts_route_correctly(self, all_skills):
        """executeQuery / Arrow consumption prompts should route to dataflows-consumption-cli."""
        failures = []
        for prompt in self.EXECUTE_QUERY_PROMPTS:
            routed = _route_prompt(prompt, all_skills)
            if "dataflows-consumption-cli" not in routed[:3]:
                failures.append(f"  '{prompt}' -> {routed[:3]}")
        assert not failures, (
            "executeQuery / Arrow consumption prompts not routed to dataflows-consumption-cli:\n" + "\n".join(failures)
        )

    def test_inspection_prompts_route_correctly(self, all_skills):
        """Dataflow monitoring / inspection prompts should route to dataflows-consumption-cli."""
        failures = []
        for prompt in self.INSPECTION_PROMPTS:
            routed = _route_prompt(prompt, all_skills)
            if "dataflows-consumption-cli" not in routed[:3]:
                failures.append(f"  '{prompt}' -> {routed[:3]}")
        assert not failures, (
            "Dataflow inspection prompts not routed to dataflows-consumption-cli:\n" + "\n".join(failures)
        )


@pytest.mark.semantic
class TestNoRoutingCollisions:
    """Verify that monitoring-cli and consumption-cli have distinct routing."""

    CLI_ONLY_PROMPTS = [
        "Run a SELECT query against my warehouse",
        "Connect to my Fabric lakehouse SQL endpoint with sqlcmd",
        "Show me the schema of nyctlc table using CLI",
    ]

    def test_cli_prompts_dont_route_to_monitoring(self, all_skills):
        """CLI consumption prompts should not route to the monitoring skill."""
        for prompt in self.CLI_ONLY_PROMPTS:
            routed = _route_prompt(prompt, all_skills)
            if routed and routed[0] == "sqldw-operations-cli":
                pytest.fail(
                    f"CLI prompt incorrectly routed to monitoring: '{prompt}' → {routed[:3]}"
                )


@pytest.mark.semantic
class TestFabricIQvsSemanticModelRouting:
    """Verify fabriciq and semantic-model-consumption route to different targets."""

    # Prompts that should route to fabriciq (natural-language business questions)
    FABRICIQ_PROMPTS = [
        "Ask Power BI what were the top 5 products by revenue last quarter",
        "Show me the data from the SalesBenchmark report",
        "Discover my Power BI report and tell me the total sales",
    ]

    # Prompts that should route to semantic-model-consumption (raw DAX / metadata)
    SEMANTIC_MODEL_PROMPTS = [
        "Run this DAX query: EVALUATE SUMMARIZECOLUMNS('Product'[Category], 'Sales'[Amount])",
        "List the semantic model tables using INFO.VIEW.TABLES",
        "Execute EVALUATE ROW against the model to get the average fare",
    ]

    def test_fabriciq_positive_routing(self, all_skills):
        """fabriciq prompts should route to fabriciq."""
        failures = []
        for prompt in self.FABRICIQ_PROMPTS:
           routed = _route_prompt(prompt, all_skills)
           if not routed or routed[0] != "fabriciq":
               failures.append(f"  '{prompt}' → {routed[:3]}")
        assert not failures, (
           "Prompts not routed to fabriciq:\n" + "\n".join(failures)
        )

    def test_semantic_model_positive_routing(self, all_skills):
        """semantic-model-consumption prompts should route to semantic-model-consumption."""
        failures = []
        for prompt in self.SEMANTIC_MODEL_PROMPTS:
           routed = _route_prompt(prompt, all_skills)
           if not routed or routed[0] != "semantic-model-consumption":
               failures.append(f"  '{prompt}' → {routed[:3]}")
        assert not failures, (
           "Prompts not routed to semantic-model-consumption:\n" + "\n".join(failures)
        )

    def test_fabriciq_does_not_steal_semantic_model_prompts(self, all_skills):
        """semantic-model-consumption prompts should not route to fabriciq."""
        for prompt in self.SEMANTIC_MODEL_PROMPTS:
           routed = _route_prompt(prompt, all_skills)
           if routed and routed[0] == "fabriciq":
               pytest.fail(
                   f"DAX prompt incorrectly routed to fabriciq: '{prompt}' → {routed[:3]}"
               )

    def test_semantic_model_does_not_steal_fabriciq_prompts(self, all_skills):
        """fabriciq prompts should not route to semantic-model-consumption."""
        for prompt in self.FABRICIQ_PROMPTS:
           routed = _route_prompt(prompt, all_skills)
           if routed and routed[0] == "semantic-model-consumption":
               pytest.fail(
                   f"Business question incorrectly routed to semantic-model-consumption: '{prompt}' → {routed[:3]}"
               )

