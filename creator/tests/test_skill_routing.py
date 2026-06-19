"""
Routing tests for skills-for-fabric.

Validates that user prompts route to the correct skill based on
description matching (Jaccard similarity on trigger phrases).
"""
import re
import pytest


def tokenize(text: str) -> set[str]:
    """Lowercase tokenize, strip punctuation."""
    return set(re.findall(r"[a-z0-9%%]+", text.lower()))


def route_prompt(prompt: str, all_skills: dict) -> tuple[str, float]:
    """Route a prompt to the best-matching skill using Jaccard similarity."""
    prompt_tokens = tokenize(prompt)
    best_skill = None
    best_score = -1.0

    for skill_name, skill_data in all_skills.items():
        desc = skill_data.get("description", "")
        desc_tokens = tokenize(desc)
        if not desc_tokens:
            continue
        intersection = prompt_tokens & desc_tokens
        union = prompt_tokens | desc_tokens
        score = len(intersection) / len(union) if union else 0.0
        if score > best_score:
            best_score = score
            best_skill = skill_name

    return best_skill, best_score


# =============================================================================
# Spark Authoring — Notebook Code Authoring Routing (merged from notebook-authoring-cli)
# =============================================================================


@pytest.mark.routing
class TestSparkAuthoringNotebookRouting:
    """Prompts for notebook code authoring must route to spark-authoring-cli."""

    @pytest.mark.parametrize("prompt", [
        "Write PySpark code in a notebook cell to read a CSV file",
        "Write notebook code using notebookutils to mount ADLS Gen2 storage",
        "Write a %%sql cell to query a lakehouse table in a Fabric notebook",
        "Write a %%configure cell for a Fabric notebook with Spark development settings",
        "Write notebook code to run a child notebook with parameters",
        "Develop a PySpark notebook for Spark data engineering in Fabric",
        "Write notebook code to access resource files in a Fabric notebook cell",
        "Run notebook in Fabric workspace for data engineering",
        "Notebook deployment to a Fabric workspace",
    ])
    def test_routes_to_spark_authoring(self, prompt, all_skills):
        """Notebook code authoring prompts should route to spark-authoring-cli."""
        skill, score = route_prompt(prompt, all_skills)
        assert skill == "spark-authoring-cli", (
            f"Prompt '{prompt}' routed to '{skill}' (score={score:.3f}), "
            f"expected 'spark-authoring-cli'"
        )


# =============================================================================
# Spark Authoring — Original Infrastructure Routing
# =============================================================================


@pytest.mark.routing
class TestSparkAuthoringInfraRouting:
    """Prompts for Spark infrastructure management must route to spark-authoring-cli."""

    @pytest.mark.parametrize("prompt", [
        "Manage Fabric workspace resources and create a lakehouse for Spark development",
        "Develop a Spark notebook for data engineering workflows",
        "Spark development workspace setup with lakehouse configuration",
        "Pipeline design for data engineering orchestration in Fabric",
    ])
    def test_routes_to_spark_authoring(self, prompt, all_skills):
        """Spark infra prompts should route to spark-authoring-cli."""
        skill, score = route_prompt(prompt, all_skills)
        assert skill == "spark-authoring-cli", (
            f"Prompt '{prompt}' routed to '{skill}' (score={score:.3f}), "
            f"expected 'spark-authoring-cli'"
        )


# =============================================================================
# Boundary Tests — Must NOT route to spark-authoring-cli
# =============================================================================


@pytest.mark.routing
class TestSparkAuthoringBoundary:
    """Prompts for other skills must NOT route to spark-authoring-cli."""

    @pytest.mark.parametrize("prompt,expected_skill", [
        ("Show warehouse tables and run a T-SQL SELECT query to explore data", "sqldw-consumption-cli"),
        ("Run a KQL query against my Eventhouse database", "eventhouse-consumption-cli"),
        ("Execute a DAX query on a Power BI semantic model", {"semantic-model-consumption", "fabriciq"}),
        ("Analyze lakehouse data with PySpark DataFrames using a Livy session", "spark-consumption-cli"),
    ])
    def test_does_not_route_to_spark_authoring(self, prompt, expected_skill, all_skills):
        """Non-authoring prompts should route to their respective skills."""
        skill, score = route_prompt(prompt, all_skills)
        expected = expected_skill if isinstance(expected_skill, set) else {expected_skill}
        assert skill in expected, (
            f"Prompt '{prompt}' routed to '{skill}' (score={score:.3f}), "
            f"expected one of {sorted(expected)}"
        )

    def test_bare_mlv_acronym_does_not_misroute(self, all_skills):
        """Bare 'MLV' acronym (no Fabric/materialized/lake context) must score LOW on
        spark-authoring-cli. Guards against the theoretical concern that 'MLV' could
        false-positive route non-Fabric prompts that happen to use the same acronym
        (e.g. Multi-Level Verification, Mean Lethal Volume).

        Asserts on spark-authoring-cli's *direct score* rather than the winner — this
        contract holds regardless of what other skills score, so the test is stable
        against future skill additions or tokenizer evolution.
        """
        # Compute spark-authoring-cli's score directly for each non-Fabric MLV prompt.
        # Threshold of 0.05 chosen empirically:
        #   - Non-Fabric MLV prompts measured at ~0.04
        #   - Fabric MLV prompts measured at >= 0.08
        # A score < 0.05 means MLV-acronym overlap alone isn't enough to win routing
        # over any reasonably matched sibling skill.
        spark_authoring_only = {"spark-authoring-cli": all_skills["spark-authoring-cli"]}
        non_fabric_mlv_prompts = [
            "What is the MLV (Mean Lethal Volume) calculation for this dataset",
            "Calculate the MLV for a multi-level verification protocol in our QA process",
        ]
        for prompt in non_fabric_mlv_prompts:
            skill, score = route_prompt(prompt, spark_authoring_only)
            assert skill == "spark-authoring-cli", (
                f"route_prompt returned unexpected skill '{skill}' from single-skill map"
            )
            assert score < 0.05, (
                f"Bare 'MLV' acronym in non-Fabric context scores {score:.4f} on "
                f"spark-authoring-cli (must be < 0.05 to avoid false-positive risk) "
                f"for prompt: {prompt!r}. If this fails, the spark-authoring-cli "
                f"description has gained too many tokens that overlap with generic "
                f"non-Fabric MLV-acronym usage."
            )


# =============================================================================
# Spark Authoring — Materialized Lake View Routing
# =============================================================================


@pytest.mark.routing
class TestSparkAuthoringMLVRouting:
    """Prompts for Materialized Lake View authoring must route to spark-authoring-cli."""

    @pytest.mark.parametrize("prompt", [
        "Create a materialized lake view in my Fabric lakehouse using Spark SQL",
        "Write CREATE MATERIALIZED LAKE VIEW SQL for a silver layer aggregation",
        "How do I set up an MLV with incremental refresh in Fabric?",
        "Review my materialized lake view query for incremental refresh readiness",
        "Write PySpark code to create a materialized lake view with full refresh",
        "Is my MLV eligible for incremental refresh?",
        "Rewrite my MLV query to be incremental refresh friendly",
        "What is the refresh policy for my materialized lake view?",
    ])
    def test_mlv_routes_to_spark_authoring(self, prompt, all_skills):
        """MLV prompts should route to spark-authoring-cli."""
        skill, score = route_prompt(prompt, all_skills)
        assert skill == "spark-authoring-cli", (
            f"Prompt '{prompt}' routed to '{skill}' (score={score:.3f}), "
            f"expected 'spark-authoring-cli'"
        )

    def test_mlv_trigger_tokens_present_in_description(self, all_skills):
        """The spark-authoring-cli description must contain the MLV trigger phrases that
        drive MLV routing. Uses the SAME tokenize() the router uses (so this test verifies
        the actual routing contract, not raw substring presence) and checks that every
        token in each required phrase is present in tokenize(description).
        """
        desc = all_skills["spark-authoring-cli"].get("description", "")
        desc_tokens = tokenize(desc)
        # The MLV routing phrases this PR committed to. Each phrase is verified at the
        # token level (same tokenization the router uses), so this test won't false-pass
        # on substring accidents nor false-fail on punctuation / line-break differences.
        required_phrases = [
            "materialized lake view",
            "MLV",
            "CREATE MATERIALIZED LAKE VIEW",
            "MLV incremental refresh",
            "review MLV for incremental refresh",
            "MLV refresh policy",
            "schedule MLV refresh",
        ]
        missing = {}
        for phrase in required_phrases:
            phrase_tokens = tokenize(phrase)
            absent = phrase_tokens - desc_tokens
            if absent:
                # Sort for deterministic assertion output (sets have no stable ordering).
                missing[phrase] = sorted(absent)
        assert not missing, (
            f"spark-authoring-cli description is missing tokens for required MLV "
            f"trigger phrases (tokenize-based check, mirrors router contract): {missing}. "
            f"Without these, MLV prompts may route to a sibling skill."
        )
