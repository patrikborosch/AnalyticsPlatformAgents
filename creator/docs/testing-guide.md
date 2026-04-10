# Testing Guide

This guide explains how to test skills-for-fabric before submitting changes.

## Test Suite Overview

| Test | File | Purpose |
|------|------|---------|
| Quality Checker | `.github/workflows/quality_checker.py` | Structural and semantic validation |
| Semantic Tests | `tests/test_semantic.py` | Naming, similarity, description quality |
| Routing Tests | `tests/test_skill_routing.py` | Prompts route to correct skills |

> Current automated tests target `skills/` content. Agent definitions should still be validated manually for routing boundaries, reference integrity, and delegation clarity.

## Quick Start

### Install Dependencies

```bash
pip install PyYAML requests pytest
```

### Run All Checks

```bash
# Quality checker
python .github/workflows/quality_checker.py

# Pytest tests
pytest tests/ -v
```

## Quality Checker

The quality checker (`quality_checker.py`) validates every skill in `skills/`:

### What It Checks

| Category | Checks |
|----------|--------|
| **Structure** | YAML frontmatter, name/description fields, update notice |
| **Content** | Must/Prefer/Avoid sections, examples, code block tags |
| **Semantics** | Trigger uniqueness, description similarity (Jaccard) |
| **References** | Cross-reference link validation |
| **Quality** | Description starts with action verb, mentions technologies |

### Running Locally

```bash
python .github/workflows/quality_checker.py
```

### Sample Output

```
📋 skills-for-fabric QUALITY CHECK
==================================================

📂 Scanning: check-updates
📂 Scanning: spark-authoring-cli
📂 Scanning: sqldw-authoring-cli

🔄 Running cross-skill analysis...

==================================================
📊 QUALITY CHECK SUMMARY
Files scanned: 5
Critical issues: 0
Warnings: 2

⚠️  Semantically ambiguous triggers: 2

   | Trigger Phrase | Matches These Skills                    | Ambiguity |
   |----------------|----------------------------------------|-----------|
   | run sql        | spark-consumption-cli, sqldw-consumption-cli | 2 skills |

✅ RESULT: PASSED with 2 warning(s)
📄 Report saved to: quality-report.json
```

### Understanding Results

| Status | Meaning | Action |
|--------|---------|--------|
| `PASSED` | All checks passed | Ready to submit |
| `PASSED with warnings` | Non-blocking issues found | Review and consider fixing |
| `CRITICAL` | Blocking issues found | Must fix before merge |

## Pytest Tests

### Test Categories

```bash
# Run all tests
pytest tests/ -v

# Run only semantic tests
pytest tests/test_semantic.py -v

# Run only routing tests
pytest tests/test_skill_routing.py -v

# Run by marker
pytest tests/ -v -m semantic
pytest tests/ -v -m routing
```

### Semantic Tests (`test_semantic.py`)

Validates skill semantics:

| Test Class | Purpose |
|------------|---------|
| `TestTriggerUniqueness` | No duplicate triggers, ambiguous triggers have qualifiers |
| `TestDescriptionSimilarity` | Jaccard similarity < 30% between skills |
| `TestNamingConventions` | Names follow `{endpoint}-{authoring|consumption}-cli` pattern |
| `TestDescriptionQuality` | Descriptions start with action verbs, mention technologies |

### Routing Tests (`test_skill_routing.py`)

Validates that user prompts route to the correct skill:

```python
@pytest.mark.parametrize("prompt", [
    "show me all tables in my warehouse",
    "query my warehouse to get top 10 products",
    "run a T-SQL query against Fabric",
])
def test_routes_to_sql_consumption(self, prompt, all_skills):
    """Prompt should route to sqldw-consumption-cli."""
    skill, score = route_prompt(prompt, all_skills)
    assert skill == "sqldw-consumption-cli"
```

### Adding New Routing Tests

When adding a new skill, add routing tests:

```python
# tests/test_skill_routing.py

@pytest.mark.routing
class TestMyNewSkillRouting:
    """Test prompts that should route to my-new-skill."""
    
    @pytest.mark.parametrize("prompt", [
        "prompt that should trigger my skill",
        "another triggering prompt",
    ])
    def test_routes_to_my_skill(self, prompt, all_skills):
        """Prompt should route to my-new-skill."""
        skill, score = route_prompt(prompt, all_skills)
        assert skill == "my-new-skill"
```

## Pre-commit Hook

### Installation

```bash
# Windows (PowerShell)
Copy-Item .github\hooks\pre-commit .git\hooks\pre-commit

# macOS/Linux
cp .github/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

### What It Does

Before each commit, the hook:

1. Runs the quality checker on changed skill files
2. Blocks commit if critical issues are found
3. Shows warnings but allows commit

### Bypassing (Not Recommended)

```bash
git commit --no-verify -m "message"
```

## CI/CD Workflow

### Pull Request Checks

When you push changes to a PR that modifies `skills/**/*.md`:

1. **Quality Check** (`quality-check.yml`)
   - Runs `quality_checker.py`
   - Posts results as PR comment
   - Uploads `quality-report.json` as artifact

2. **Security Audit** (`security-audit.yml`)
   - Scans for secrets and sensitive data
   - Validates security guidelines

### Workflow Triggers

```yaml
on:
  pull_request:
    branches: [ main, master ]
    paths: 
      - 'skills/**/*.md'
  push:
    branches: [ main, master ]
    paths:
      - 'skills/**/*.md'
```

## Testing Locally with Copilot CLI

### Symlink Your Skill

```bash
# Windows (PowerShell as Admin)
New-Item -ItemType SymbolicLink `
  -Path "$env:USERPROFILE\.copilot\skills\my-new-skill" `
  -Target ".\skills\my-new-skill"

# macOS/Linux
ln -s $(pwd)/skills/my-new-skill ~/.copilot/skills/my-new-skill
```

### Verify Loading

Start a new Copilot CLI session:

```
/skills list
```

Your skill should appear in the list.

### Test Prompts

Try prompts that should trigger your skill and verify correct routing.

## Test File Structure

```
tests/
├── conftest.py              # Shared fixtures (all_skills, etc.)
├── README.md                # Test documentation
├── requirements-dev.txt     # Test dependencies
├── test_semantic.py         # Semantic validation tests
└── test_skill_routing.py    # Routing tests
```

### Shared Fixtures (`conftest.py`)

```python
@pytest.fixture
def all_skills():
    """Load all skills from skills/ folder."""
    skills = {}
    skills_dir = Path(__file__).parent.parent / "skills"
    
    for skill_folder in skills_dir.iterdir():
        skill_md = skill_folder / "SKILL.md"
        if skill_md.exists():
            # Parse frontmatter and add to skills dict
            ...
    
    return skills
```

## Debugging Test Failures

### Quality Checker Failures

1. Read the specific error message
2. Check `quality-report.json` for details
3. Common fixes:
   - Add missing frontmatter fields
   - Add update notice
   - Tag code blocks with language
   - Fix broken cross-references

### Routing Test Failures

```
AssertionError: Expected sqldw-consumption-cli but got spark-consumption-cli
```

1. Check your skill's triggers in the description
2. Add more specific trigger phrases
3. Ensure triggers don't overlap with other skills

### Semantic Test Failures

```
Skills with similarity >= 30%: [{'skills': ('skill-a', 'skill-b'), 'similarity': 35.2}]
```

1. Differentiate descriptions between the two skills
2. Use more specific terminology
3. Clarify distinct use cases

## Best Practices

1. **Run tests before every commit** — Use the pre-commit hook
2. **Add routing tests for new skills** — Verify correct routing
3. **Check quality report** — Review `quality-report.json` for details
4. **Test locally first** — Don't rely only on CI/CD
5. **Keep tests updated** — When adding triggers, add corresponding tests

## Next Steps

- [Quality Requirements](quality-requirements.md) — What the tests check
- [Skill Authoring Guide](skill-authoring-guide.md) — How to create skills
