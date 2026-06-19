# Metrics Definition & Collection

## Metrics

### 1. Success Rate

**Definition:** Whether the skill executed the requested operation correctly and produced the expected outcome.

**Measurement:**
```
success_rate = (passed_test_cases / total_test_cases) * 100
```

**Grading per test case:**

| Grade | Criteria |
|-------|----------|
| PASS | Skill invoked correctly, output matches expected result |
| FAIL_INVOCATION | Wrong skill invoked, or skill not invoked at all |
| FAIL_EXECUTION | Skill invoked but errored (API failure, syntax error, etc.) |
| FAIL_RESULT | Skill completed but output does not match expected result |

**Collection:** After each eval prompt, the evaluating agent records:
```json
{
  "eval_id": "spark-auth-01",
  "skill": "spark-authoring-cli",
  "test_case": "create-lakehouse",
  "grade": "PASS",
  "error_message": null,
  "actual_output_summary": "Lakehouse 'eval_lh' created successfully"
}
```

### 2. Token Usage

**Definition:** Total input + output tokens consumed by the agent to complete one eval prompt.

**Measurement:**
- Record token counts from the Copilot CLI session shutdown metrics in
  `~/.copilot/session-state/<session-id>/events.jsonl` when available
- If a run ends before shutdown metrics are written, leave token fields null
  instead of silently estimating them

**Collection:**
```json
{
  "eval_id": "spark-auth-01",
  "input_tokens": 1250,
  "output_tokens": 830,
  "total_tokens": 2080,
  "num_tool_calls": 3,
  "num_agent_turns": 2
}
```

**Analysis:**
- Compute mean, median, p95 token usage per skill
- Flag outliers (>2x median) for investigation
- Compare across skills to identify expensive operations

**Follow-up metric:** v1 telemetry does not yet derive first-correct-route
timing from session events. Add that later when efficiency budgets are layered
on top of the current telemetry artifact.

### 3. Read/Write Consistency

**Definition:** Data written by an authoring skill must be exactly retrievable by the corresponding consumption skill.

**Measurement:**
```
For each write→read pair:
  1. Write known data (schema + rows) using authoring skill
  2. Read back using consumption skill
  3. Compare: schema match, row count match, cell-level exact match
```

**Consistency checks:**

| Check | Rule |
|-------|------|
| Schema match | Column names and types are identical |
| Row count | `COUNT(*)` matches expected |
| Cell-level | Every cell value matches exactly (including NULLs, decimals, dates) |
| Order stability | ORDER BY queries return rows in expected sequence |
| Type fidelity | DECIMAL precision preserved, dates not truncated, strings not trimmed |

**Collection:**
```json
{
  "eval_id": "consistency-sqldw-01",
  "write_skill": "sqldw-authoring-cli",
  "read_skill": "sqldw-consumption-cli",
  "dataset": "sales_transactions_small",
  "schema_match": true,
  "row_count_match": true,
  "row_count_expected": 100,
  "row_count_actual": 100,
  "cell_mismatches": 0,
  "total_cells_checked": 1000,
  "consistency_score": 1.0
}
```

## Aggregation

After all evals complete, produce a summary report:

```
╔═══════════════════════════════╦═══════════╦═══════════╦═════════════╗
║ Skill                         ║ Success % ║ Avg Tokens║ Consistency ║
╠═══════════════════════════════╬═══════════╬═══════════╬═════════════╣
║ check-updates                 ║  95%      ║  800      ║ N/A         ║
║ spark-authoring-cli           ║  90%      ║  2500     ║ N/A (write) ║
║ spark-consumption-cli         ║  92%      ║  2200     ║ 100%        ║
║ sqldw-authoring-cli           ║  93%      ║  1800     ║ N/A (write) ║
║ sqldw-consumption-cli         ║  95%      ║  1500     ║ 100%        ║
║ e2e-medallion-architecture    ║  88%      ║  4000     ║ 100%        ║
╠═══════════════════════════════╬═══════════╬═══════════╬═════════════╣
║ Combined: sqldw write→read    ║  90%      ║  3200     ║ 100%        ║
║ Combined: spark write→read    ║  88%      ║  4500     ║ 100%        ║
║ Combined: cross-engine        ║  85%      ║  5000     ║ 100%        ║
║ Combined: full pipeline       ║  82%      ║  8000     ║ 100%        ║
╚═══════════════════════════════╩═══════════╩═══════════╩═════════════╝
```

## Results Storage

All eval results should be stored as JSON files in `evalsets/expected-results/` and optionally loaded into a SQLite database for querying:

```sql
CREATE TABLE eval_results (
  eval_id TEXT PRIMARY KEY,
  skill TEXT,
  test_case TEXT,
  grade TEXT,
  input_tokens INT,
  output_tokens INT,
  total_tokens INT,
  consistency_score REAL,
  error_message TEXT,
  timestamp TEXT
);
```
