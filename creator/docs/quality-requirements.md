# Quality Requirements

This document explains the quality standards for skills-for-fabric and what the automated checks validate.

Scope note: this checker currently validates content under `skills/`. Agent quality should follow the same core standards (clear purpose, no overlap, valid references, token discipline) while agent-specific automation evolves.

## Overview

Every skill must pass quality checks before merging. The quality checker validates:

1. **Structural compliance** — Required sections and formatting
2. **Semantic disambiguation** — Triggers don't conflict with other skills
3. **Content quality** — Descriptions, examples, code blocks
4. **Cross-references** — All links resolve to existing files
5. **Common-infra compliance** — Generic auth/token/tooling guidance is rooted in `common/`

## Structural Requirements

### Required Elements

| Element | Required | Checked |
|---------|----------|---------|
| YAML frontmatter with `name` and `description` | ✅ Critical | Blocks PR |
| Description length ≤ 1023 characters | ✅ Critical | Blocks PR |
| Update notice blockquote | ✅ Critical (except check-updates) | Blocks PR |
| Markdown files are valid UTF-8 and free of high-confidence mojibake markers | ✅ Critical | Blocks PR |
| Generic auth/token/sqlcmd setup guidance must reference `common/` | ✅ Critical | Blocks PR |
| Explicit `Triggers:` field in description (except check-updates) | ⚠️ Warning | Review recommended |
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

### Encoding Integrity

Skill markdown must be saved as valid UTF-8 and stay free of obvious mojibake sequences
such as corrupted em dashes or section signs. The checker looks for a short list of
high-confidence corruption markers like `ΓÇö`, `ΓÇô`, `ΓåÆ`, and `┬º` so it can block
broken rendering without flagging normal Unicode punctuation.

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

### Anti-Trigger Overlap (advisory)

A Sensei-inspired heuristic compares the `Triggers:` field token sets of every skill pair. Pairs whose smaller trigger set is more than half-contained in the other (`|A ∩ B| / min(|A|, |B|) > 0.5`) are reported as `trigger_overlaps` in `quality-report.json`.

| Setting | Default |
|---|---|
| Threshold | overlap > 0.5 |
| Minimum trigger-set size | 3 (smaller sets are skipped to avoid noise) |
| Severity | WARNING — never blocks merge |
| Storage | top-level `trigger_overlaps` (separate from `semantic_conflicts` so the existing CRITICAL contract is preserved) |

A reported overlap is **signal**, not a failure: two skills may legitimately cover the same domain. Treat each pair as a prompt to verify the routing intent.

The existing `find_ambiguous_triggers` check runs at the *phrase* granularity (single trigger matches multiple skills). `find_trigger_overlap` runs at the *set* granularity. The whole-description Jaccard similarity matrix runs at the *prose* granularity. All three are useful at different layers — `find_trigger_overlap` catches near-duplicate trigger sets the prose-level matrix demonstrably misses.

Provenance: inspired by the [Sensei skill auto-improver](https://github.com/Azure/azure-sdk-tools/tree/main/.github/skills/sensei). We intentionally adopt only the anti-trigger detector — not the Ralph loop, autonomous mutation, or a description-rubric scorer (the original PR shipped a 5-axis rubric too, but the stylistic axes produced false positives against legitimate descriptions; the one structural axis was folded into the `has_triggers_field` check below).

### Triggers Field Required (warning)

Every skill description (except `check-updates`) must include an explicit `Triggers:` field -- skill routers index on it directly. A description that says "the user can trigger this skill when ..." in prose **does not** satisfy this check; the field must be present verbatim.

The check accepts both the plural `Triggers:` (preferred, used everywhere in this doc) and the legacy singular `Trigger:` (a few older skills still use it). Both pass the check; new skills should use the plural form.

```yaml
# Good (preferred plural form)
description: >
  Execute T-SQL against Fabric Data Warehouse.
  Use when the user wants to run queries.
  Triggers: "create warehouse table", "load from ADLS", "COPY INTO".

# Also accepted (legacy singular form, present in a few older skills)
description: >
  Execute T-SQL against Fabric Data Warehouse.
  Trigger: "create warehouse table", "load from ADLS", "COPY INTO".

# Missing field -- emits structural WARNING
description: >
  Execute T-SQL against Fabric Data Warehouse. The agent should
  trigger this skill when the user wants to query a warehouse.
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

## Common-Infra Compliance

Shared setup belongs in `common/`. Skills can keep endpoint-specific commands and workflows, but generic auth, token, and shared tool guidance must point back to the common docs instead of standing alone.

### Blocking Scope

The current blocking checks focus on two high-drift areas:

1. **Authentication and token guidance**
   - Examples: `az login`, `az account get-access-token`, generic token-acquisition notes
   - Must reference shared auth guidance from `COMMON-CORE.md` and `COMMON-CLI.md`
2. **Shared SQL tooling setup**
   - Examples: `winget install sqlcmd`, `sqlcmd --version`, "`sqlcmd` not found"
   - Must reference `COMMON-CLI.md` SQL / TDS guidance

### Examples

```markdown
# ✅ Good
- [COMMON-CORE.md](../../common/COMMON-CORE.md) — authentication, token audiences
- [COMMON-CLI.md](../../common/COMMON-CLI.md) — `az rest`, `az login`, token acquisition

### MUST DO
- Run `az login` before using CLI auth flows
```

```markdown
# ❌ Bad
### Authentication
- Run `az login`
- Acquire a token with `az account get-access-token`
```

```markdown
# ❌ Bad
| `sqlcmd` | `winget install sqlcmd` |
> sqlcmd --version 2>/dev/null || echo "INSTALL: winget install sqlcmd"
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
