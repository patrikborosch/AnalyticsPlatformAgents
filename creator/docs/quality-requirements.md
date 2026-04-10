# Quality Requirements

This document explains the quality standards for skills-for-fabric and what the automated checks validate.

Scope note: this checker currently validates content under `skills/`. Agent quality should follow the same core standards (clear purpose, no overlap, valid references, token discipline) while agent-specific automation evolves.

## Overview

Every skill must pass quality checks before merging. The quality checker validates:

1. **Structural compliance** — Required sections and formatting
2. **Semantic disambiguation** — Triggers don't conflict with other skills
3. **Content quality** — Descriptions, examples, code blocks
4. **Cross-references** — All links resolve to existing files

## Structural Requirements

### Required Elements

| Element | Required | Checked |
|---------|----------|---------|
| YAML frontmatter with `name` and `description` | ✅ Critical | Blocks PR |
| Description length ≤ 1023 characters | ✅ Critical | Blocks PR |
| Update notice blockquote | ✅ Critical (except check-updates) | Blocks PR |
| Must/Prefer/Avoid sections | ⚠️ Warning | Review recommended |
| Examples section | ⚠️ Warning | Review recommended |
| Code blocks with language tags | ⚠️ Warning | Review recommended |
| Description length ≥ 900 characters | ⚠️ Warning | Review recommended |

### YAML Frontmatter

```yaml
---
name: skill-name          # Must match folder name
description: >            # Multi-line description
  Action verb description...
---
```

**Validation:**
- `name` must be present and match folder name
- `description` must be present and non-empty

### Update Notice

Required format (blockquote starting with "Update Check"):

```markdown
> **Update Check — ONCE PER SESSION (mandatory)**
> The first time this skill is used in a session, run the **check-updates** skill...
```

## Semantic Disambiguation

### Trigger Phrase Uniqueness

Trigger phrases should not match multiple skills. The quality checker detects:

| Issue | Severity | Example |
|-------|----------|---------|
| Exact duplicate trigger | Critical | Two skills with `Triggers: "run sql"` |
| Semantically ambiguous trigger | Warning | "query" matches SQL and Spark skills |

### Description Similarity (Jaccard)

The checker calculates Jaccard similarity between skill descriptions:

```
Jaccard = |words in common| / |all unique words|
```

| Similarity | Status | Action |
|------------|--------|--------|
| < 20% | ✅ Good | No action needed |
| 20-30% | ⚠️ Review | Consider differentiating descriptions |
| ≥ 30% | 🚨 Critical | Must differentiate before merge |

**Example:**
```
sqldw-authoring-cli vs sqldw-consumption-cli: 25% similarity
→ Acceptable (same technology, different personas)

skill-a vs skill-b: 45% similarity
→ Too similar, differentiate descriptions
```

### Fixing Ambiguous Triggers

Add technology qualifiers to make triggers unique:

```yaml
# ❌ Ambiguous: matches multiple skills
Triggers: "query", "sql", "explore"

# ✅ Specific: routes correctly
Triggers: "T-SQL query", "query warehouse with sqlcmd", "explore warehouse schema"
```

## Token Size Limits

### Why Token Size Matters

Large skills consume AI context window, reducing capacity for user interactions and responses.

| Token Count | Status | Recommendation |
|-------------|--------|----------------|
| < 5,000 | ✅ Good | Ideal size |
| 5,000 - 10,000 | ⚠️ Acceptable | Consider if all content is needed |
| 10,000 - 15,000 | ⚠️ Large | Look for content to move to common/ |
| > 15,000 | 🚨 Too Large | Must split or refactor |

### How to Reduce Size

1. **Move reference material to `common/`**
   ```markdown
   # Instead of duplicating auth docs:
   See [COMMON-CLI.md](../../common/COMMON-CLI.md) for authentication.
   ```

2. **Move templates to `references/` subfolder**
   ```
   skills/my-skill/
   ├── SKILL.md              # Focused skill content
   └── references/
       └── script-templates.md  # Detailed templates
   ```

3. **Split into multiple skills**
   - If a skill covers distinct use cases, create separate skills
   - Example: `spark-authoring-cli` could split into `spark-jobs-cli` and `spark-notebooks-cli`

4. **Remove redundant content**
   - Don't repeat what's in common/
   - Don't include complete API references (link instead)

## Description Quality

### Action Verb Requirement

Descriptions should start with an action verb:

```yaml
# ✅ Good
description: Execute authoring T-SQL against Fabric Data Warehouse...
description: Run interactive queries against SQL endpoints...
description: Create and deploy Spark notebooks...

# ❌ Bad
description: This skill helps with warehouse operations...
description: Fabric Warehouse skill for data work...
```

**Recognized action verbs:** Execute, Run, Create, Develop, Build, Deploy, Manage, Explore, Query, Analyze, Check, Validate, Monitor, Generate, Automate, Implement, Configure

### Technology Mentions

Descriptions should mention specific technologies:

```yaml
# ✅ Good: mentions technologies
description: >
  Execute authoring T-SQL (DDL, DML) against Microsoft Fabric Data Warehouse
  from CLI environments using sqlcmd...

# ❌ Bad: too vague
description: >
  Help with database operations in Fabric...
```

**Expected keywords:** spark, pyspark, livy, t-sql, tsql, sql, sqlcmd, fabric, lakehouse, warehouse, notebook, pipeline, rest, api, cli, terminal

## Code Block Requirements

All code blocks must have language tags:

```markdown
# ✅ Good
```bash
az login
```

```sql
SELECT * FROM dbo.FactSales
```

```python
df = spark.table("sales")
```

# ❌ Bad (untagged)
```
az login
```
```

## Cross-Reference Validation

All relative links must resolve to existing files:

```markdown
# ✅ Valid
See [COMMON-CLI.md](../../common/COMMON-CLI.md)

# ❌ Invalid (wrong path)
See [COMMON-CLI.md](../common/COMMON-CLI.md)

# ❌ Invalid (file doesn't exist)
See [MISSING.md](../../common/MISSING.md)
```

## Running Quality Checks

### Local Check

```bash
# Install dependencies
pip install PyYAML requests

# Run quality checker
python .github/workflows/quality_checker.py
```

### Output

```
📋 skills-for-fabric QUALITY CHECK
==================================================

📂 Scanning: sqldw-authoring-cli

📂 Scanning: spark-consumption-cli

🔄 Running cross-skill analysis...

==================================================
📊 QUALITY CHECK SUMMARY
Files scanned: 5
Critical issues: 0
Warnings: 3

✅ QUALITY CHECK COMPLETE
```

### Quality Report

Results are saved to `quality-report.json`:

```json
{
  "overall_status": "WARNING",
  "files_scanned": 5,
  "critical_count": 0,
  "warning_count": 3,
  "similarity_matrix": {...},
  "ambiguous_triggers": [...],
  "skills": {
    "sqldw-authoring-cli": {
      "has_frontmatter": true,
      "has_update_notice": true,
      "has_must_prefer_avoid": true,
      "has_examples": true,
      "code_blocks_tagged": true
    }
  }
}
```

## CI/CD Integration

### Pull Request Checks

When you submit a PR that modifies `skills/**/*.md`:

1. Quality checker runs automatically
2. Results are posted as a PR comment
3. Critical issues block merge
4. Warnings are displayed for review

### Pre-commit Hook

Install the pre-commit hook to catch issues before pushing:

```bash
# Windows
Copy-Item .github\hooks\pre-commit .git\hooks\pre-commit

# macOS/Linux
cp .github/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Quality Checklist

Before submitting a PR:

- [ ] Folder name matches `name` in frontmatter
- [ ] Description starts with action verb
- [ ] Description mentions specific technologies
- [ ] Triggers don't conflict with other skills
- [ ] Update notice is present
- [ ] Must/Prefer/Avoid sections included
- [ ] Code blocks have language tags
- [ ] All cross-references resolve
- [ ] Token count < 15,000
- [ ] Quality check passes locally

## Next Steps

- [Testing Guide](testing-guide.md) — How to run tests
- [Skill Authoring Guide](skill-authoring-guide.md) — How to create skills
