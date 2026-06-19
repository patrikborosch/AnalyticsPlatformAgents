"""
Semantic tests for Eventstream skills.

These tests validate skill quality without external dependencies.
Run with: pytest -m semantic -v
"""
import re
import pytest
from pathlib import Path


EVENTSTREAM_SKILLS = ["eventstream-authoring-cli", "eventstream-consumption-cli"]

EVENTSTREAM_CORE_DOCS = [
    "EVENTSTREAM-AUTHORING-CORE.md",
    "EVENTSTREAM-CONSUMPTION-CORE.md",
]


# =============================================================================
# 1. Frontmatter Quality
# =============================================================================


class TestFrontmatter:
    """Validate YAML frontmatter for Eventstream skills."""

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_skill_exists(self, all_skills, skill_name):
        """Skill must be loaded from the skills directory."""
        assert skill_name in all_skills, f"Skill {skill_name} not found"

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_name_matches_folder(self, all_skills, skill_name):
        """Frontmatter 'name' must match the folder name."""
        skill = all_skills[skill_name]
        assert skill["name"] == skill_name

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_description_length(self, all_skills, skill_name):
        """Description must be ≤ 1023 characters."""
        desc = all_skills[skill_name]["description"]
        assert len(desc) <= 1023, f"Description is {len(desc)} chars (max 1023)"

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_description_not_empty(self, all_skills, skill_name):
        """Description must not be empty."""
        desc = all_skills[skill_name]["description"].strip()
        assert len(desc) > 0

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_description_starts_with_verb(self, all_skills, skill_name):
        """Description should start with an action verb."""
        desc = all_skills[skill_name]["description"].strip()
        first_word = desc.split()[0].rstrip(",").lower()
        action_verbs = {
            "create", "build", "deploy", "configure", "manage", "execute",
            "list", "inspect", "monitor", "discover", "query", "check",
            "validate", "show", "get", "find", "read", "write", "update",
            "delete", "add", "remove", "set", "run", "generate", "export",
        }
        assert first_word in action_verbs, (
            f"Description starts with '{first_word}', expected an action verb"
        )

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_description_has_triggers(self, all_skills, skill_name):
        """Description must contain trigger phrases."""
        desc = all_skills[skill_name]["description"]
        assert "Triggers:" in desc or "triggers:" in desc, (
            "Description must include 'Triggers:' section"
        )


# =============================================================================
# 2. Structural Completeness
# =============================================================================


class TestStructure:
    """Validate required structural elements in Eventstream skills."""

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_has_update_notice(self, all_skills, skill_name):
        """Must include the mandatory update check notice."""
        content = all_skills[skill_name]["content"]
        assert "Update Check" in content, "Missing mandatory Update Check notice"

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_has_critical_notes(self, all_skills, skill_name):
        """Must include CRITICAL NOTES section."""
        content = all_skills[skill_name]["content"]
        assert "CRITICAL NOTES" in content

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_has_toc(self, all_skills, skill_name):
        """Must include a Table of Contents."""
        content = all_skills[skill_name]["content"]
        assert "## Table of Contents" in content or "| Task | Reference | Notes |" in content

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_has_must_do_section(self, all_skills, skill_name):
        """Must include MUST DO section."""
        content = all_skills[skill_name]["content"]
        assert "### MUST DO" in content

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_has_prefer_section(self, all_skills, skill_name):
        """Must include PREFER section."""
        content = all_skills[skill_name]["content"]
        assert "### PREFER" in content

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_has_avoid_section(self, all_skills, skill_name):
        """Must include AVOID section."""
        content = all_skills[skill_name]["content"]
        assert "### AVOID" in content

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_has_jmespath_note(self, all_skills, skill_name):
        """Must reference JMESPath filtering for workspace/item discovery."""
        content = all_skills[skill_name]["content"]
        assert "JMESPath" in content

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_has_disambiguation_note(self, all_skills, skill_name):
        """Must disambiguate Eventstream from Eventhouse."""
        content = all_skills[skill_name]["content"]
        assert "Eventhouse" in content, (
            "Skill should mention Eventhouse to disambiguate"
        )


# =============================================================================
# 3. Cross-Reference Integrity
# =============================================================================


class TestCrossReferences:
    """Validate that all cross-references resolve to real files and headings."""

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_common_file_refs_exist(self, all_skills, skill_name, common_dir):
        """All ../../common/*.md references must point to existing files."""
        content = all_skills[skill_name]["content"]
        refs = re.findall(r'\]\((\.\./\.\./common/[^)#]+)', content)
        for ref in refs:
            # Resolve from skill directory
            skill_dir = all_skills[skill_name]["path"].parent
            resolved = (skill_dir / ref).resolve()
            assert resolved.exists(), f"Cross-reference broken: {ref}"

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_common_heading_refs_exist(self, all_skills, skill_name, common_dir):
        """All ../../common/*.md#heading references must point to existing headings."""
        content = all_skills[skill_name]["content"]
        refs = re.findall(r'\]\(\.\./\.\./common/([^)]+)#([^)]+)\)', content)
        for filename, heading_slug in refs:
            filepath = common_dir / filename
            if not filepath.exists():
                continue  # File existence checked separately
            file_content = filepath.read_text(encoding="utf-8")
            # Convert heading to slug using GitHub's algorithm:
            # 1. lowercase  2. strip non-alphanum (keep spaces/dashes)
            # 3. replace each space with hyphen (1:1, not collapsed)
            headings = re.findall(r'^##+ (.+)$', file_content, re.MULTILINE)
            slugs = []
            for h in headings:
                slug = h.lower().strip()
                # Remove backticks and non-alphanum except spaces/dashes
                slug = re.sub(r'[^\w\s-]', '', slug)
                # Replace each space with a single dash (preserves double-dash from & removal)
                slug = slug.replace(' ', '-')
                slug = slug.strip('-')
                slugs.append(slug)
            assert heading_slug in slugs, (
                f"Heading #{heading_slug} not found in {filename}. "
                f"Available: {slugs}"
            )

    @pytest.mark.semantic
    @pytest.mark.parametrize("core_doc", EVENTSTREAM_CORE_DOCS)
    def test_core_doc_exists(self, common_dir, core_doc):
        """CORE docs must exist in the common/ directory."""
        assert (common_dir / core_doc).exists(), f"Missing CORE doc: {core_doc}"


# =============================================================================
# 4. Code Block Hygiene
# =============================================================================


class TestCodeBlocks:
    """Validate code block formatting."""

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_code_blocks_have_language_tags(self, all_skills, skill_name):
        """All opening code fences must have a language tag."""
        content = all_skills[skill_name]["content"]
        lines = content.split("\n")
        in_code_block = False
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("```"):
                if in_code_block:
                    in_code_block = False  # closing fence
                else:
                    in_code_block = True
                    lang = stripped[3:].strip()
                    assert lang, f"Code block at line {i} missing language tag"

    @pytest.mark.semantic
    @pytest.mark.parametrize("core_doc", EVENTSTREAM_CORE_DOCS)
    def test_core_code_blocks_have_language_tags(self, common_dir, core_doc):
        """All code blocks in CORE docs must have language tags."""
        content = (common_dir / core_doc).read_text(encoding="utf-8")
        lines = content.split("\n")
        in_code_block = False
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("```"):
                if in_code_block:
                    in_code_block = False
                else:
                    in_code_block = True
                    lang = stripped[3:].strip()
                    assert lang, (
                        f"Code block at line {i} in {core_doc} missing language tag"
                    )


# =============================================================================
# 5. Token Budget
# =============================================================================


class TestTokenBudget:
    """Validate token counts are within limits."""

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_skill_under_max_tokens(self, all_skills, skill_name):
        """Skill content must be under 15K tokens (chars/4 estimate)."""
        full_path = all_skills[skill_name]["path"]
        full_content = full_path.read_text(encoding="utf-8")
        est_tokens = len(full_content) // 4
        assert est_tokens < 15000, (
            f"Skill is ~{est_tokens} tokens (max 15000)"
        )

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_skill_under_ideal_tokens(self, all_skills, skill_name):
        """Skill content should ideally be under 10K tokens."""
        full_path = all_skills[skill_name]["path"]
        full_content = full_path.read_text(encoding="utf-8")
        est_tokens = len(full_content) // 4
        if est_tokens >= 10000:
            pytest.skip(f"~{est_tokens} tokens — over ideal but under max")


# =============================================================================
# 6. Routing Disambiguation (Jaccard)
# =============================================================================


class TestRoutingDisambiguation:
    """Validate that Eventstream skills don't conflict with Eventhouse skills."""

    @staticmethod
    def _tokenize(text):
        return set(re.findall(r'[a-z]+', text.lower()))

    @staticmethod
    def _jaccard(set_a, set_b):
        inter = set_a & set_b
        union = set_a | set_b
        return len(inter) / len(union) if union else 0

    ALLOWED_GENERIC_OVERLAP = {
        ("eventstream-consumption-cli", "powerbi-report-management"),
        ("eventstream-consumption-cli", "search-consumption-cli"),
    }

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_jaccard_below_threshold(self, all_skills, skill_name):
        """Jaccard similarity vs every other skill must be <= 0.20, except
        same-domain eventstream pairs and the allow-listed generic overlaps
        (Power BI report management, Search consumption)."""
        desc = all_skills[skill_name]["description"]
        tokens = self._tokenize(desc)
        for other_name, other_data in all_skills.items():
            if other_name == skill_name:
                continue
            if "eventstream" in other_name:
                continue  # Same-domain pair is expected to be higher
            if (skill_name, other_name) in self.ALLOWED_GENERIC_OVERLAP:
                continue
            other_tokens = self._tokenize(other_data["description"])
            j = self._jaccard(tokens, other_tokens)
            assert j <= 0.20, (
                f"Jaccard({skill_name}, {other_name}) = {j:.3f} (must be <= 0.20)"
            )

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_no_eventhouse_triggers(self, all_skills, skill_name):
        """Eventstream triggers must NOT include Eventhouse-specific terms."""
        desc = all_skills[skill_name]["description"]
        # Extract the Triggers: section
        triggers_match = re.search(r'Triggers:\s*(.+)', desc, re.DOTALL)
        if not triggers_match:
            pytest.skip("No Triggers section found")
        triggers_text = triggers_match.group(1).lower()
        forbidden = ["kql", "kusto", "eventhouse query", "kql database"]
        for term in forbidden:
            assert term not in triggers_text, (
                f"Trigger contains forbidden Eventhouse term: '{term}'"
            )


# =============================================================================
# 7. CORE Doc Completeness
# =============================================================================


class TestCoreDocCompleteness:
    """Validate CORE docs have proper structure and are referenced by skills."""

    @pytest.mark.semantic
    @pytest.mark.parametrize("core_doc", EVENTSTREAM_CORE_DOCS)
    def test_core_has_purpose_blockquote(self, common_dir, core_doc):
        """CORE doc must start with a Purpose blockquote."""
        content = (common_dir / core_doc).read_text(encoding="utf-8")
        assert "> **Purpose**" in content

    @pytest.mark.semantic
    @pytest.mark.parametrize("core_doc", EVENTSTREAM_CORE_DOCS)
    def test_core_has_gotchas(self, common_dir, core_doc):
        """CORE doc must have a Gotchas section."""
        content = (common_dir / core_doc).read_text(encoding="utf-8")
        assert "Gotcha" in content, "Missing Gotchas section"

    @pytest.mark.semantic
    def test_authoring_core_headings_in_skill_toc(self, all_skills, common_dir):
        """All ## headings in AUTHORING-CORE must appear in authoring skill TOC."""
        core_content = (common_dir / "EVENTSTREAM-AUTHORING-CORE.md").read_text(
            encoding="utf-8"
        )
        skill_content = all_skills["eventstream-authoring-cli"]["content"]

        headings = re.findall(r'^## (.+)$', core_content, re.MULTILINE)
        for heading in headings:
            slug = heading.lower().strip()
            slug = re.sub(r'[^\w\s-]', '', slug)
            slug = re.sub(r'[\s]+', '-', slug)
            slug = slug.strip('-')
            assert slug in skill_content.lower().replace(' ', '-') or heading in skill_content, (
                f"CORE heading '{heading}' not referenced in authoring skill TOC"
            )

    @pytest.mark.semantic
    def test_consumption_core_headings_in_skill_toc(self, all_skills, common_dir):
        """All ## headings in CONSUMPTION-CORE must appear in consumption skill TOC."""
        core_content = (common_dir / "EVENTSTREAM-CONSUMPTION-CORE.md").read_text(
            encoding="utf-8"
        )
        skill_content = all_skills["eventstream-consumption-cli"]["content"]

        headings = re.findall(r'^## (.+)$', core_content, re.MULTILINE)
        for heading in headings:
            slug = heading.lower().strip()
            slug = re.sub(r'[^\w\s-]', '', slug)
            slug = re.sub(r'[\s]+', '-', slug)
            slug = slug.strip('-')
            assert slug in skill_content.lower().replace(' ', '-') or heading in skill_content, (
                f"CORE heading '{heading}' not referenced in consumption skill TOC"
            )


# =============================================================================
# 8. Naming Conventions
# =============================================================================


class TestNamingConventions:
    """Validate skill naming follows repo conventions."""

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_follows_naming_pattern(self, skill_name):
        """Skill name must follow {workload}-{authoring|consumption}-cli pattern."""
        pattern = r'^eventstream-(authoring|consumption)-cli$'
        assert re.match(pattern, skill_name), (
            f"Skill name '{skill_name}' doesn't match expected pattern"
        )

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_skill_folder_has_skill_md(self, skills_dir, skill_name):
        """Skill folder must contain SKILL.md."""
        skill_md = skills_dir / skill_name / "SKILL.md"
        assert skill_md.exists()


# =============================================================================
# 9. Eventstream-Specific Checks
# =============================================================================


class TestEventstreamSpecific:
    """Eventstream domain-specific validations."""

    @pytest.mark.semantic
    def test_authoring_covers_source_types(self, all_skills, common_dir):
        """Authoring CORE must document the 25 API-supported source types."""
        content = (common_dir / "EVENTSTREAM-AUTHORING-CORE.md").read_text(
            encoding="utf-8"
        )
        key_sources = [
            "AzureEventHub", "AzureIoTHub", "AzureSQLDBCDC", "ApacheKafka",
            "ConfluentCloud", "AmazonKinesis", "GooglePubSub", "SampleData",
            "CustomEndpoint", "AzureDataExplorer", "AzureEventGridNamespace",
            "RealTimeWeather", "SolacePubSub", "Mqtt",
        ]
        for src in key_sources:
            assert src in content, f"Source type '{src}' missing from AUTHORING-CORE"

    @pytest.mark.semantic
    def test_authoring_covers_operators(self, all_skills, common_dir):
        """Authoring CORE must document all 8 API-supported operators."""
        content = (common_dir / "EVENTSTREAM-AUTHORING-CORE.md").read_text(
            encoding="utf-8"
        )
        operators = ["Filter", "Aggregate", "GroupBy", "Join", "ManageFields", "Union", "Expand", "SQL"]
        for op in operators:
            assert op in content, f"Operator '{op}' missing from AUTHORING-CORE"

    @pytest.mark.semantic
    def test_authoring_covers_destinations(self, all_skills, common_dir):
        """Authoring CORE must document all 4 API-supported destinations."""
        content = (common_dir / "EVENTSTREAM-AUTHORING-CORE.md").read_text(
            encoding="utf-8"
        )
        destinations = ["Lakehouse", "Eventhouse", "Activator", "CustomEndpoint"]
        for dest in destinations:
            assert dest in content, f"Destination '{dest}' missing from AUTHORING-CORE"

    @pytest.mark.semantic
    def test_authoring_covers_streams(self, all_skills, common_dir):
        """Authoring CORE must document both stream types."""
        content = (common_dir / "EVENTSTREAM-AUTHORING-CORE.md").read_text(
            encoding="utf-8"
        )
        assert "DefaultStream" in content
        assert "DerivedStream" in content

    @pytest.mark.semantic
    def test_authoring_covers_base64_pattern(self, all_skills, common_dir):
        """Authoring CORE must document the base64 encoding pattern."""
        content = (common_dir / "EVENTSTREAM-AUTHORING-CORE.md").read_text(
            encoding="utf-8"
        )
        assert "base64" in content.lower()

    @pytest.mark.semantic
    def test_consumption_covers_discovery(self, all_skills, common_dir):
        """Consumption CORE must document listing and discovery patterns."""
        content = (common_dir / "EVENTSTREAM-CONSUMPTION-CORE.md").read_text(
            encoding="utf-8"
        )
        assert "List Eventstreams" in content or "Listing" in content

    @pytest.mark.semantic
    def test_consumption_covers_topology_inspection(self, all_skills, common_dir):
        """Consumption CORE must document topology inspection."""
        content = (common_dir / "EVENTSTREAM-CONSUMPTION-CORE.md").read_text(
            encoding="utf-8"
        )
        assert "topology" in content.lower()

    @pytest.mark.semantic
    def test_authoring_skill_mentions_api_resource(self, all_skills):
        """Authoring skill must reference the Fabric API resource URL."""
        content = all_skills["eventstream-authoring-cli"]["content"]
        assert "api.fabric.microsoft.com" in content

    @pytest.mark.semantic
    def test_consumption_skill_mentions_api_resource(self, all_skills):
        """Consumption skill must reference the Fabric API resource URL."""
        content = all_skills["eventstream-consumption-cli"]["content"]
        assert "api.fabric.microsoft.com" in content

    @pytest.mark.semantic
    @pytest.mark.parametrize("skill_name", EVENTSTREAM_SKILLS)
    def test_skill_mentions_eventstream_not_event_stream(self, all_skills, skill_name):
        """Should use 'Eventstream' (one word), not 'Event Stream' (two words)."""
        desc = all_skills[skill_name]["description"]
        # Check description specifically for "Event Stream" (two words, both capitalized)
        assert "Event Stream" not in desc, (
            "Use 'Eventstream' (one word), not 'Event Stream' (two words)"
        )
