# Combined Eval: Spark Authoring + Consumption

## Purpose
Verify that data written by `spark-authoring-cli` is exactly retrievable by every applicable consumption skill.

## Flow
```
spark-authoring-cli (WRITE) → Lakehouse Delta Table → spark-consumption-cli (READ)
                                                    → sqldw-consumption-cli (READ via SQL Endpoint)
```

## Pre-requisites
- Shared `{{LAKEHOUSE}}` lakehouse provisioned by runner (Phase 0b)
- Spark capacity available
- SQL Endpoint enabled on the lakehouse

## Data Setup (run FIRST)

Clean up any leftover data from a prior run:
1. Drop Delta table `eval_products` in `{{LAKEHOUSE}}` (if exists)

## Data Teardown (run LAST)

Clean up data objects. Do NOT drop the shared `{{LAKEHOUSE}}` lakehouse.
1. Drop Delta table `eval_products` via Spark SQL

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

<!--
## SQL Endpoint Metadata Sync — Important

> **⚠️ Known Issue:** Delta tables written by Spark are NOT immediately visible via the Lakehouse SQL Endpoint.
> The SQL endpoint requires a metadata sync to discover new tables, which can take **5–60+ minutes** depending
> on the Fabric environment (MSIT environments may be slower).
>
> **Required approach for the T-SQL read step (SAC-03):**
> 1. After the Spark write, wait **at least 30 seconds** before the first T-SQL query attempt.
> 2. If the table is not found (`Invalid object name`), retry with 10-second intervals.
> 3. Maximum retry duration: **3 minutes**.
> 4. If the table is still not visible after 3 minutes, mark the T-SQL read as `FAIL_SYNC_DELAY`
>    (distinct from a logic failure) and continue to the next test.
-->

## Test Cases

### SAC-01: Write 5 Known Rows via Spark Authoring
- **Prompt:** "Create a Delta table called eval_products in {{LAKEHOUSE}} and insert 5 rows: (1,'Product_001','Electronics',9.99), (2,'Product_002','Clothing',19.98), (3,'Product_003','Food',29.97), (4,'Product_004','Home',39.96), (5,'Product_005','Sports',49.95)"
- **Expected:** Delta table `eval_products` created with 5 rows
- **Pass criteria:** Table exists, row count = 5
- **Golden data:** See `evalsets/expected-results/products_5rows.json`

### SAC-02: Read Back via Spark Consumption (PySpark)
- **Prompt:** "Using PySpark, read all rows from eval_products in {{LAKEHOUSE}} ordered by product_id"
- **Expected:** Exactly 5 rows matching SAC-01 write data
- **Pass criteria:**
  - Row count = 5
  - product_id: [1, 2, 3, 4, 5]
  - product_name: ["Product_001", "Product_002", "Product_003", "Product_004", "Product_005"]
  - category: ["Electronics", "Clothing", "Food", "Home", "Sports"]
  - base_price: [9.99, 19.98, 29.97, 39.96, 49.95] — exact decimal match
  - **EXACT MATCH required — this is a consistency test**

<!-- ### SAC-03: Read Back via SQL DW Consumption (T-SQL via SQL Endpoint)
- **Prompt:** "Query all rows from eval_products via the SQL endpoint of {{LAKEHOUSE}} ordered by product_id"
- **Expected:** Exactly 5 rows matching SAC-01 write data
- **Pass criteria:**
  - Row count = 5
  - All cell values match SAC-02 results exactly
  - Decimal precision preserved (9.99 not 9.990000)
  - **EXACT MATCH required — this is a cross-engine consistency test** -->

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
- 3000–6000 tokens per combined test (write + read + verify)

---

## Notebook Code Authoring → Execute → Verify (SAC-04)

Added after merging `notebook-authoring-cli` into `spark-authoring-cli`. Tests that generated notebook code is executable and produces correct results.

### SAC-04: Notebook Code Gen → Run → Read Back *(infrastructure)*
- **Prompt (Step 1 — Generate):** "Write a PySpark notebook cell that creates a Delta table called eval_notebook_test with columns id INT and value STRING in eval_sales_lh, and inserts 3 rows: (1,'alpha'), (2,'beta'), (3,'gamma')"
- **Prompt (Step 2 — Execute):** "Create a notebook with this code in my workspace and run it"
- **Prompt (Step 3 — Verify):** "Using PySpark, read all rows from eval_notebook_test in eval_sales_lh ordered by id"
- **Expected:** Table exists with exactly 3 rows matching the inserted data
- **Pass criteria:**
  - Step 1: Generated code uses `spark` (no `SparkSession.builder`), correct Delta write
  - Step 2: Notebook created and run succeeds
  - Step 3: Row count = 3, values match: [(1,'alpha'), (2,'beta'), (3,'gamma')]
  - **EXACT MATCH required — this is a code generation + execution consistency test**
