# Combined Eval: Eventhouse Authoring + Consumption

## Purpose
Verify that data written by `eventhouse-authoring-cli` is exactly retrievable by `eventhouse-consumption-cli`.

## Flow
```
eventhouse-authoring-cli (WRITE) → Eventhouse KQL Table → eventhouse-consumption-cli (READ)
```

## Pre-requisites
- Shared `{{EVENTHOUSE}}` with KQL Database `{{KQLDB}}` provisioned by runner (Phase 0b)

## Data Setup (run FIRST)

Clean up any leftover data from a prior run:
1. `.drop table eval_consistency ifexists` in `{{KQLDB}}`

## Data Teardown (run LAST)

Clean up KQL objects. Do NOT drop the shared `{{EVENTHOUSE}}` or `{{KQLDB}}`.
1. `.drop table eval_consistency ifexists`

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### KAC-01: Write 3 Known Rows via Eventhouse Authoring
- **Prompt:** "Create a KQL table eval_consistency in my Eventhouse with columns: id (long), name (string), value (real), event_time (datetime) and ingest inline: (1,'Alpha',100.50,datetime(2025-01-01)), (2,'Beta',200.75,datetime(2025-01-02)), (3,'Gamma',300.00,datetime(2025-01-03))"
- **Expected:** Table `eval_consistency` created with 3 rows ingested
- **Pass criteria:** Table exists, `eval_consistency | count` returns 3

### KAC-02: Read Back via Eventhouse Consumption (KQL)
- **Prompt:** "Query all rows from eval_consistency in my Eventhouse ordered by id"
- **Expected:** Exactly 3 rows matching KAC-01 inline data
- **Pass criteria:**
  - Row count = 3
  - id: [1, 2, 3]
  - name: ["Alpha", "Beta", "Gamma"]
  - value: [100.50, 200.75, 300.00] — exact real-number match
  - event_time: ["2025-01-01", "2025-01-02", "2025-01-03"]
  - **EXACT MATCH required — this is a consistency test**

## Consistency Scoring

For each read test case, compute:
```
schema_match  = (all column names and types match) ? 1 : 0
row_count_ok  = (actual count == expected count) ? 1 : 0
cell_accuracy = (matching cells / total cells)
consistency   = (schema_match + row_count_ok + cell_accuracy) / 3
```

**Pass threshold:** consistency = 1.0 for all test cases

## Expected Token Range
- 2500–5500 tokens per combined test (write + read + verify)
