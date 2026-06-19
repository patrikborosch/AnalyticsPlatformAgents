# Combined Eval: SQL DW Authoring + Consumption

## Purpose
Verify that data written by `sqldw-authoring-cli` is exactly retrievable by every applicable consumption skill.

## Flow
```
sqldw-authoring-cli (WRITE) → Warehouse Table → sqldw-consumption-cli (READ via T-SQL)
                                               → spark-consumption-cli (READ via PySpark)
```

## Pre-requisites
- Shared `{{WAREHOUSE}}` provisioned by runner (Phase 0b)
- Spark capacity available for PySpark cross-engine read

## Data Setup (run FIRST)

Clean up any leftover data from a prior run:
1. `DROP TABLE IF EXISTS eval.consistency_test` in `{{WAREHOUSE}}`

## Data Teardown (run LAST)

Clean up all data objects. Do NOT drop the shared `{{WAREHOUSE}}`.
1. `DROP TABLE IF EXISTS eval.consistency_test`
2. `DROP SCHEMA IF EXISTS eval`

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### DWC-01: Write 3 Known Rows via SQL DW Authoring
- **Prompt:** "Create table eval.consistency_test (id INT, name VARCHAR(50), amount DECIMAL(10,2), created_date DATE) in my warehouse and insert: (1,'Alpha',100.50,'2025-01-01'), (2,'Beta',200.75,'2025-01-02'), (3,'Gamma',300.00,'2025-01-03')"
- **Expected:** Table `eval.consistency_test` created with 3 rows
- **Pass criteria:** Table exists, row count = 3
- **Golden data:** See `evalsets/expected-results/consistency_3rows.json`

### DWC-02: Read Back via SQL DW Consumption (T-SQL)
- **Prompt:** "Query all rows from eval.consistency_test in my warehouse ordered by id"
- **Expected:** Exactly 3 rows matching DWC-01 write data
- **Pass criteria:**
  - Row count = 3
  - id: [1, 2, 3]
  - name: ["Alpha", "Beta", "Gamma"]
  - amount: [100.50, 200.75, 300.00] — exact decimal match
  - created_date: ["2025-01-01", "2025-01-02", "2025-01-03"]
  - **EXACT MATCH required — this is a consistency test**

### DWC-03: Read Back via Spark Consumption (PySpark)
- **Prompt:** "Using PySpark, read all rows from eval.consistency_test in the warehouse and show all values ordered by id"
- **Expected:** Exactly 3 rows matching DWC-01 write data
- **Pass criteria:**
  - Row count = 3
  - All cell values match DWC-02 results exactly
  - DECIMAL(10,2) precision preserved
  - DATE type mapped correctly
  - **EXACT MATCH required — this is a cross-engine consistency test**

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
- 2500–5000 tokens per combined test (write + read + verify)
