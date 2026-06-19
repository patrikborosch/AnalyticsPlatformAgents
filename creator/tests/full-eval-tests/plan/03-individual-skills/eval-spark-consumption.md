# Eval Plan: spark-consumption-cli

## Skill Overview
- **Skill:** `spark-consumption-cli`
- **Category:** Spark / Analytics (Read)
- **Purpose:** Analyze lakehouse data via Livy sessions, PySpark/Spark SQL, DataFrames

## Pre-requisites
- Shared `{{LAKEHOUSE}}` lakehouse provisioned by runner (Phase 0b)
- Livy session available or will be created by skill

## Data Setup (run FIRST — before any test cases)

This plan provisions its own data. Do NOT depend on spark-authoring having run first. Use a plan-prefixed table name so this plan can run in parallel with other plans that share `{{LAKEHOUSE}}`.

> **Data source:** All pre-generated data files are in `evalsets/data-generation/`. Use those files instead of generating data inline. The files are produced by `evalsets/data-generation/generate.py` and match the spec in `plan/01-data-generation.md`.

1. Drop Delta table `eval_spark_sales_transactions` in `{{LAKEHOUSE}}` (if exists) to ensure clean state
2. Upload `evalsets/data-generation/sales_transactions_100.csv` to `Files/sales_transactions_100.csv` in `{{LAKEHOUSE}}` (via OneLake API or Fabric upload)
3. Load it into a Delta table called `eval_spark_sales_transactions` using PySpark (read CSV with header, infer schema, overwrite the table)

Expected schema: `transaction_id INT, customer_id INT, product_id INT, product_name STRING, category STRING, quantity INT, unit_price DECIMAL(10,2), total_amount DECIMAL(10,2), transaction_date DATE, region STRING`

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.


## Test Cases

### SC-01: Simple Row Count
- **Prompt:** "Using PySpark, count the rows in the eval_spark_sales_transactions table in {{LAKEHOUSE}}"
- **Expected result:** 100
- **Pass criteria:** Exact match to expected row count

### SC-02: Filtered Query
- **Prompt:** "Using Spark SQL, find all sales transactions in the Electronics category from eval_spark_sales_transactions in {{LAKEHOUSE}}"
- **Expected result:** 20 rows (for 100-row dataset, every 5th row)
- **Pass criteria:** Row count = 20, all rows have category = "Electronics"

### SC-03: Aggregation
- **Prompt:** "Using PySpark DataFrames, calculate total sales amount per region from eval_spark_sales_transactions in {{LAKEHOUSE}}"
- **Expected result:** 4 rows (East, West, North, South), amounts match golden results
- **Pass criteria:** 4 regions, amounts match pre-computed values


## Data Teardown (run LAST — after all test cases)

Clean up data objects created by this plan. Do NOT drop the shared `{{LAKEHOUSE}}` lakehouse.
1. Drop Delta table `eval_spark_sales_transactions` via Spark SQL: `DROP TABLE IF EXISTS {{LAKEHOUSE}}.eval_spark_sales_transactions`

## Consistency Test Matrix

| Read Case | Data Source | Table | Verification |
|-----------|------------|-------|-------------|
| SC-01 | Data Setup (step 3) | eval_spark_sales_transactions | Row count = 100 |
| SC-02 | Data Setup (step 3) | eval_spark_sales_transactions | Electronics count = 20 (deterministic: rows where i%5==0) |
| SC-03 | Data Setup (step 3) | eval_spark_sales_transactions | 4 regions: East(25), West(25), North(25), South(25) |

## Expected Token Range
- 1500–3500 tokens per invocation
