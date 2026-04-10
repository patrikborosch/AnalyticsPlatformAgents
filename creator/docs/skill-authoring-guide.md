# Skill Authoring Guide

This guide explains how to create high-quality skills-for-fabric. Follow these patterns to ensure your skill is discoverable, focused, and maintainable.

## Skill Structure

Every skill lives in its own folder under `skills/` with a `SKILL.md` file:

```
skills/
└── my-new-skill/
    ├── SKILL.md              # Required: main skill definition
    └── references/           # Optional: supporting files
        └── templates.md
```

## SKILL.md Format

### Required Sections

```markdown
---
name: my-skill-name
description: >
  Action-verb description mentioning technologies. Use when the user wants to:
  (1) first use case, (2) second use case. Triggers: "phrase1", "phrase2".
---

> **Update Check — ONCE PER SESSION (mandatory)**
> The first time this skill is used in a session, run the **check-updates** skill...
> [Full update notice - see template below]

# Skill Title

## Prerequisite Knowledge
- Links to common/ documents this skill depends on

## Must/Prefer/Avoid

### MUST DO
- Critical requirements

### PREFER
- Best practices

### AVOID
- Anti-patterns

## [Topic Sections]
Your skill content...

## Examples
Code examples or prompt/response pairs
```

### YAML Frontmatter

```yaml
---
name: sqldw-authoring-cli          # Must match folder name
description: >
  Execute authoring T-SQL (DDL, DML, data ingestion) against Microsoft Fabric
  Data Warehouse from CLI environments. Use when the user wants to:
  (1) create/alter tables, (2) insert/update data, (3) run COPY INTO.
  Triggers: "create table in warehouse", "insert data via T-SQL".
---
```

**Description requirements:**
- Start with an action verb (Execute, Create, Run, Explore, Query)
- Mention specific technologies (T-SQL, PySpark, Livy, sqlcmd)
- Include "Use when the user wants to:" with numbered use cases
- Include "Triggers:" with quoted trigger phrases

### Update Notice (Required)

Every skill except `check-updates` must include this notice:

```markdown
> **Update Check — ONCE PER SESSION (mandatory)**
> The first time this skill is used in a session, run the **check-updates** skill before proceeding.
> - **GitHub Copilot CLI / VS Code**: invoke the `check-updates` skill (e.g., `/fabric-skills:check-updates`).
> - **Claude Code / Cowork / Cursor / Windsurf / Codex**: read the local `package.json` version, then compare it against the remote version via `git fetch origin main --quiet && git show origin/main:package.json` (or the GitHub API). If the remote version is newer, show the changelog and update instructions.
> - Skip if the check was already performed earlier in this session.
```

## Naming Conventions

### Pattern

```
{endpoint_or_engine}-{authoring|consumption}-{access_method}
```

| Component | Options | Examples |
|-----------|---------|----------|
| endpoint_or_engine | `sqldw`, `spark`, `eventhouse`, `pbi` | SQL Data Warehouse, Spark, Eventhouse, Power BI |
| authoring/consumption | `authoring`, `consumption` | Developer vs. interactive use |
| access_method | `cli`, `sdk`, `mcp` | CLI tools, SDK, MCP server |

### Examples

| Skill Name | Purpose |
|------------|---------|
| `sqldw-authoring-cli` | Create/modify warehouse objects via CLI |
| `sqldw-consumption-cli` | Query warehouse data via CLI |
| `spark-authoring-cli` | Develop Spark jobs and notebooks |
| `spark-consumption-cli` | Interactive Spark exploration |

### Special Cases

| Pattern | Use For |
|---------|---------|
| `agents/{persona}.agent.md` | Cross-endpoint orchestration (e.g., `agents/FabricDataEngineer.agent.md`, `agents/FabricAdmin.agent.md`) |
| `e2e-{pattern}` | End-to-end cross-cutting patterns (e.g., `e2e-medallion-architecture`) |
| `check-updates` | Utility skills |

## Skill vs Agent: When to Build Which

Use this framework before creating new content:

1. **Single endpoint + single persona** → create/update a **skill**
2. **Cross-endpoint or cross-cutting workflow** → create/update an **agent**
3. **End-to-end pattern** spanning a single workload (e.g., medallion architecture) → create/update an **e2e skill**
4. **Utility behavior** (session checks/tooling) → create/update a **utility skill**
5. **Reference-only shared content** → place in `common/`

### Two-Endpoint Test

If the workflow requires knowledge of **2+ workload endpoints** to be useful, prefer an agent.

Do not count authentication and workspace/catalog discovery in this threshold because those are shared prerequisites across all skills.

## Authoring vs. Consumption

### Authoring Skills (`-authoring-`)

Target: **Developers writing code**

Content focus:
- DDL/DML operations (CREATE, ALTER, INSERT, UPDATE, DELETE)
- CI/CD and automation
- Infrastructure-as-code
- SDK and API usage
- Job deployment

### Consumption Skills (`-consumption-`)

Target: **Users exploring data interactively**

Content focus:
- Read-only queries (SELECT)
- Schema discovery
- Data exploration
- Monitoring and diagnostics
- Ad-hoc analysis

## Writing Good Descriptions

### ✅ Good Description

```yaml
description: >
  Execute authoring T-SQL (DDL, DML, data ingestion, transactions) against 
  Microsoft Fabric Data Warehouse from CLI environments. Use when the user 
  wants to: (1) create/alter tables, (2) insert/update/delete data, 
  (3) run COPY INTO ingestion, (4) manage transactions. Triggers: "create 
  table in warehouse", "insert data via T-SQL", "COPY INTO", "upsert".
```

**Why it's good:**
- Starts with action verb ("Execute")
- Mentions technologies (T-SQL, DDL, DML, CLI)
- Lists specific use cases
- Includes trigger phrases

### ❌ Bad Description

```yaml
description: >
  Help with Fabric Warehouse operations.
```

**Why it's bad:**
- No action verb
- No specific technologies
- No use cases
- No triggers
- Too vague to route correctly

## Must/Prefer/Avoid Sections

These sections guide AI behavior:

```markdown
## Must/Prefer/Avoid

### MUST DO
- Always use `-G` flag for Entra ID authentication
- Always specify `-d <DatabaseName>`
- Run `az login` before first SQL operation

### PREFER
- `sqlcmd (Go) -G` over curl+token for SQL queries
- `-i file.sql` for complex queries
- Piped input for multi-statement batches

### AVOID
- ODBC sqlcmd (`/opt/mssql-tools/bin/sqlcmd`) — requires driver
- Hardcoded FQDNs — discover via REST API
- DML on Lakehouse SQL Endpoint — it's read-only
```

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

# ❌ Bad
```
az login
```
```

Common language tags: `bash`, `powershell`, `sql`, `python`, `json`, `text`

## Skill Philosophy: Guidance Over Code

**Skills provide principles and patterns, not implementation code.**

The LLM should generate code on-demand based on your guidance. Skills should contain:
- ✅ **Must/Prefer/Avoid** principles
- ✅ **When to use** different approaches
- ✅ **Best practices** and guardrails
- ✅ **Conceptual patterns** with explanations
- ❌ **NOT complete implementations** to copy-paste

### ✅ Good: Skill Guidance Pattern

```markdown
## Data Ingestion Principles

**When to define explicit schemas:**
- Production pipelines where data types must be consistent
- Large files where inferSchema would add overhead
- When source schema is known and stable

**Guide LLM to generate:**
- StructType definitions with nullable constraints
- Validation logic using .filter() for required fields
- Error handling with try-except blocks
```

### ❌ Bad: Implementation Code Pattern

```markdown
## Data Ingestion Implementation

```python
# Complete 100-line Python class with:
class DataIngestionPipeline:
    def __init__(self, spark_session):
        # Full implementation...
    def read_source_data(self, file_pattern, schema=None):
        # Full implementation...
```
```

For resource files in `resources/` subfolder, follow the same principle: guidance and patterns, not complete implementations.

### ❌ Don't Create Overly Long Skills

Skills over ~10K tokens become unwieldy. Signs your skill is too long:

- Quality checker warns about token count
- Skill covers multiple distinct workflows
- Users need to scroll extensively

**Solution:** Split into focused skills or move reference material to `common/`.

### ❌ Don't Overlap with Other Skills

Avoid trigger phrases that match multiple skills:

```yaml
# ❌ Bad: "query" matches both SQL and Spark skills
Triggers: "query", "sql"

# ✅ Good: Specific triggers
Triggers: "T-SQL query", "query warehouse with sqlcmd"
```

See: [Quality Requirements](quality-requirements.md)

### ❌ Don't Duplicate Common Content

If content applies to multiple skills, put it in `common/`:

```markdown
# ❌ Bad: Copy authentication docs into every skill

# ✅ Good: Reference common
## Prerequisite Knowledge
- [COMMON-CLI.md](../../common/COMMON-CLI.md) — Authentication patterns
```

## Referencing Prerequisites

Link to common documents that provide foundational knowledge:

```markdown
## Prerequisite Knowledge

Read these companion documents:

- [COMMON-CORE.md](../../common/COMMON-CORE.md) — Fabric REST API patterns
- [COMMON-CLI.md](../../common/COMMON-CLI.md) — CLI implementation (az, curl, jq)
- [SQLDW-AUTHORING-CORE.md](../../common/SQLDW-AUTHORING-CORE.md) — T-SQL patterns

This skill adds: **how to invoke** these patterns from an agentic terminal.
```

## Adding a New Skill

### Step-by-Step

1. **Create folder**: `skills/my-skill-name/`

2. **Create SKILL.md** with required sections

3. **Run quality check**:
   ```bash
   python .github/workflows/quality_checker.py
   ```

4. **Fix any issues** reported by the checker

5. **Add to plugin.json** (if applicable):
   ```json
   // plugins/authoring/plugin.json
   {
     "skills": [
       "../../skills/my-skill-name"
     ]
   }
   ```

6. **Update CHANGELOG.md**

7. **Submit PR**

### Checklist

- [ ] Folder name matches `name` in frontmatter
- [ ] Description starts with action verb
- [ ] Description includes triggers
- [ ] Update notice is present
- [ ] Must/Prefer/Avoid sections included
- [ ] Code blocks have language tags
- [ ] Cross-references use valid relative paths
- [ ] Quality check passes

## Updating Existing Skills

When updating a skill:

1. **Run quality check before and after**
2. **Update CHANGELOG.md** with your changes
3. **Verify cross-references still work**
4. **Check that triggers don't now conflict** with other skills

## Examples Section

Include practical examples showing the skill in action:

```markdown
## Examples

### Query Top Products by Revenue
```bash
$SQLCMD -Q "
SELECT TOP 10 ProductName, SUM(Amount) AS Revenue
FROM dbo.FactSales fs
JOIN dbo.DimProduct dp ON fs.ProductID = dp.ProductID
GROUP BY ProductName
ORDER BY Revenue DESC" -W
```

### Export to CSV
```bash
$SQLCMD -Q "SELECT * FROM dbo.FactSales" -W -s"," -o sales.csv
```
```

## Next Steps

- [Quality Requirements](quality-requirements.md) — Understand quality rules
- [Testing Guide](testing-guide.md) — How to validate your skill
- [Skill Catalog](skill-catalog.md) — See existing skills as examples
