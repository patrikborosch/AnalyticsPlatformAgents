# Eval Plan: sqldw-operations-cli

## Skill Overview
- **Skill:** `sqldw-operations-cli`
- **Category:** SQL DW Performance & Diagnostics (Read)
- **Purpose:** Analyze Fabric Data Warehouse performance, diagnose slow queries, and get optimization recommendations via CLI using sqlcmd and queryinsights views

## Pre-requisites
- Fabric Data Warehouse with recent query history (queries executed in the last 24–48 hours)
- Fabric API authentication configured
- Eval datasets loaded into the warehouse (at least `sales_transactions` table with query activity)

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### SM-01: Find Slow Queries
- **Prompt:** "What are the 5 slowest queries in my warehouse?"
- **Expected:** Skill runs a query against `queryinsights.long_running_queries` via sqlcmd and returns query summaries with elapsed times
- **Pass criteria:** Output contains up to 5 queries with elapsed time and run count; uses sqlcmd and queryinsights views

### SM-02: Identify Resource-Heavy Queries
- **Prompt:** "Which queries consumed the most CPU in the last 2 hours?"
- **Expected:** Skill queries `queryinsights.exec_requests_history` filtered to the last 2 hours, ordered by CPU
- **Pass criteria:** Output includes CPU time, data scanned metrics, and any performance recommendations

### SM-03: Compare Performance Against Baseline
- **Prompt:** "Has my warehouse performance degraded compared to last week?"
- **Expected:** Skill runs the baseline comparison query (recent 1h vs 7-day baseline)
- **Pass criteria:** Output shows recent vs baseline metrics for elapsed time, CPU, and data scanned with percent changes

### SM-04: Analyze Long-Running Queries
- **Prompt:** "Analyze the slowest queries and recommend optimizations"
- **Expected:** Skill queries long-running queries from exec_requests_history and provides analysis guidance
- **Pass criteria:** Output includes query details and Fabric-valid recommendations (no unsupported features like nonclustered indexes)

### SM-05: Diagnose Pressure Windows
- **Prompt:** "Were there any periods of high concurrent load in the last 24 hours? What caused them?"
- **Expected:** Skill runs the pressure window analysis query (15-min buckets) and drills into high-load periods
- **Pass criteria:** Output describes pressure windows (if any) and identifies contributing queries

### SM-06: Analyze Cache Behavior
- **Prompt:** "Which queries are suffering from cold cache and not benefiting from caching?"
- **Expected:** Skill runs the cache warmth analysis query and identifies queries with high remote storage reads
- **Pass criteria:** Output distinguishes cold vs warm cache queries and identifies caching inefficiencies

### SM-07: Recommend Clustering Keys
- **Prompt:** "Which tables in my warehouse should I cluster, and on which columns?"
- **Expected:** Skill runs cluster key recommendation queries (query patterns + table sizes) and presents recommendations
- **Pass criteria:** Output includes table names, recommended columns, and uses CTAS syntax (not ALTER TABLE)

### SM-08: Get Best Practices for Ingestion
- **Prompt:** "What are the best practices for loading data into my Fabric warehouse?"
- **Expected:** Skill presents the ingestion best practices section
- **Pass criteria:** Output covers COPY INTO, file sizing (100 MB–1 GB), batch operations, and avoids recommending unsupported features

### SM-09: Search Query Patterns
- **Prompt:** "Find all historical query patterns that reference the FactSales table"
- **Expected:** Skill runs the query pattern search with `LIKE '%FactSales%'`
- **Pass criteria:** Output includes matched patterns with execution counts and timing statistics

### SM-10: User Activity Analysis
- **Prompt:** "Show me which users are running the most queries and their patterns"
- **Expected:** Skill runs the top users insights query for the last 24 hours
- **Pass criteria:** Output includes per-user query counts and activity patterns

### SM-11: Negative — Ambiguous Optimization Request
- **Prompt:** "Make my warehouse faster"
- **Expected:** Skill asks for clarification or provides a structured investigation workflow rather than guessing
- **Pass criteria:** Agent does not recommend unsupported features (no indexes, no materialized views); either asks for specifics or follows the "Why is my warehouse slow?" agentic workflow

## Write Operations (for consistency pairing)

_None — all queries in this skill are read-only._

## Expected Token Range
- 1000–3000 tokens per invocation
