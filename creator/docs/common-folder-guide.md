# Common Folder Guide

The `common/` folder contains shared reference documents that multiple skills can include. This guide explains what belongs here and how to use it.

In the repository layering model, common content sits under orchestration and skill layers:
**Agents → Skills → Common**.

## Purpose

The `common/` folder serves as a **shared knowledge base** for AI assistants. Instead of duplicating information across skills, we centralize:

- Fabric-wide concepts (authentication, APIs, topology)
- Language-agnostic patterns (REST specifications, error codes)
- Implementation patterns (CLI recipes, SDK patterns)

## File Naming Convention

| Pattern | Purpose | Audience |
|---------|---------|----------|
| `COMMON-CORE.md` | Fabric-wide concepts applicable to all skills | All skills |
| `COMMON-CLI.md` | CLI implementation patterns (az, curl, jq) | CLI skills |
| `{ENDPOINT}-AUTHORING-CORE.md` | Authoring patterns for a specific endpoint | Authoring skills |
| `{ENDPOINT}-CONSUMPTION-CORE.md` | Consumption patterns for a specific endpoint | Consumption skills |

### Current Files

```
common/
├── COMMON-CORE.md              # Fabric topology, auth, REST API patterns
├── COMMON-CLI.md               # az rest, curl, jq recipes
├── EVENTHOUSE-AUTHORING-CORE.md       # KQL management commands, table/policy/function authoring
├── EVENTHOUSE-CONSUMPTION-CORE.md     # KQL query patterns, time-series, performance best practices
├── SPARK-AUTHORING-CORE.md     # Spark job development, notebooks, CI/CD
├── SPARK-CONSUMPTION-CORE.md   # Livy sessions, interactive Spark
├── SQLDW-AUTHORING-CORE.md     # T-SQL DDL/DML, COPY INTO, transactions
└── SQLDW-CONSUMPTION-CORE.md   # SELECT patterns, DMVs, Query Insights
```

## CORE vs CLI Pattern

### CORE Documents (Language-Agnostic)

CORE documents describe **what** to do without specifying **how**:

```markdown
# SQLDW-AUTHORING-CORE.md

## 3. COPY INTO

COPY INTO is the highest-throughput ingestion method.

### Syntax
POST {endpoint}/v1/workspaces/{wsId}/warehouses/{whId}/...

### Parameters
| Parameter | Type | Description |
|-----------|------|-------------|
| FILE_TYPE | string | PARQUET, CSV, JSON |
| ...
```

### CLI Documents (Implementation-Specific)

CLI documents show **how** to invoke patterns from CORE docs:

```markdown
# sqldw-authoring-cli/SKILL.md

## 4. Data Ingestion via CLI

### 4.1 COPY INTO
```bash
$SQLCMD -Q "
COPY INTO dbo.FactSales
FROM 'https://storage.dfs.core.windows.net/container/sales/*.parquet'
WITH (FILE_TYPE = 'PARQUET')"
```
```

## When to Add to Common

### ✅ Add to Common When:

1. **Multiple skills need the same information**
   - Authentication patterns → COMMON-CORE.md
   - Token acquisition → COMMON-CLI.md

2. **Content is reference material, not how-to**
   - API specifications
   - Error code tables
   - Platform limitations

3. **Content is stable and rarely changes**
   - REST endpoint URLs
   - Supported data types

### ❌ Keep in Skill When:

1. **Skill-specific workflow**
   - Step-by-step tutorials
   - Agentic exploration patterns

2. **Tool-specific invocation**
   - CLI command examples
   - SDK code samples

3. **Frequently updated content**
   - Workarounds for current limitations

## How Skills Reference Common

Skills reference common documents in their **Prerequisite Knowledge** section:

```markdown
---
name: sqldw-authoring-cli
description: ...
---

# SQL Endpoint Authoring — CLI Skill

## Prerequisite Knowledge

Read these companion documents:

- [COMMON-CORE.md](../../common/COMMON-CORE.md) — Fabric REST API patterns
- [COMMON-CLI.md](../../common/COMMON-CLI.md) — CLI implementation (az, curl, jq)
- [SQLDW-AUTHORING-CORE.md](../../common/SQLDW-AUTHORING-CORE.md) — T-SQL authoring patterns

This skill adds: **how to invoke** all authoring scenarios from CLI.
```

## Adding a New Common Document

### Choose the Right Type

| If your content is... | Create... |
|----------------------|-----------|
| Fabric-wide, applies to all skills | Add to `COMMON-CORE.md` |
| CLI patterns for all endpoints | Add to `COMMON-CLI.md` |
| Specific to one endpoint | `{ENDPOINT}-{AUTHORING|CONSUMPTION}-CORE.md` |

### Follow the Structure

```markdown
# {ENDPOINT}-{AUTHORING|CONSUMPTION}-CORE.md

> **Purpose**: Brief description of what this document covers.

## 1. First Major Topic

### 1.1 Subtopic

| Table | Of | Information |
|-------|----|-----------  |

### 1.2 Another Subtopic

## 2. Second Major Topic

...

## N. Gotchas and Limitations

| Issue | Workaround |
|-------|------------|
```

### Keep It Language-Agnostic

CORE documents should describe REST APIs, not language bindings:

```markdown
# ✅ Good (language-agnostic)
POST /v1/workspaces/{wsId}/items
Content-Type: application/json
{
  "type": "Lakehouse",
  "displayName": "MyLakehouse"
}

# ❌ Bad (implementation-specific)
az rest --method post --url "..."
```

### Update Skills That Should Reference It

After adding a new common document, update relevant skills to reference it in their Prerequisite Knowledge section.

## Token Size Considerations

Common documents can be large. Consider:

1. **Split by topic** if a document exceeds 10K tokens
2. **Move reference tables** to a separate `references/` subfolder
3. **Skills should summarize, not duplicate** common content

## Cross-Reference Validation

The quality checker validates all relative links. Ensure:

- Paths use `../../common/` from skills
- File names match exactly (case-sensitive on Linux)
- No broken links

```bash
# Run quality check to validate references
python .github/workflows/quality_checker.py
```
