# Eval Plan: sqldw-authoring-cli

## Skill Overview
- **Skill:** `sqldw-authoring-cli`
- **Category:** SQL Data Warehouse (Write)
- **Purpose:** Execute DDL, DML, data ingestion (COPY INTO), transactions, stored procedures, schema evolution, time travel against Fabric Data Warehouse

## Pre-requisites
- Shared `{{WAREHOUSE}}` provisioned by runner (Phase 0b)
- ADLS/OneLake path accessible for COPY INTO testing
- Eval CSV datasets uploaded to Files/ or ADLS
- Fabric API authentication configured

## Data Setup (run FIRST — before any test cases)

Before running any test cases, drop any leftover objects from a prior run to ensure a clean slate:
1. `DROP VIEW IF EXISTS eval.vw_sales_by_region` in `{{WAREHOUSE}}`
2. `DROP TABLE IF EXISTS eval.sales_transactions` in `{{WAREHOUSE}}`
3. `DROP SCHEMA IF EXISTS eval` in `{{WAREHOUSE}}`

This ensures the plan is self-contained regardless of execution order.

Warehouse tables (`eval.sales_transactions`, `eval.customers`, `eval.vw_sales_by_region`) are chain-shared with `eval-sqldw-consumption` and `eval-sqldw-authoring-plus-consumption` -- the runner serializes all sqldw plans into one chain so the un-prefixed names never collide in parallel (see [00-overview.md Parallel-Safety Contract rule #1, chain-serialized exception](../00-overview.md#parallel-safety-contract-informational-runner-enforced)).

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### DWA-01: Create Schema
- **Prompt:** "Create a schema called eval in my Fabric warehouse"
- **Expected:** Schema `eval` created
- **Pass criteria:** `SELECT * FROM sys.schemas WHERE name='eval'` returns 1 row

### DWA-02: Create Table
- **Prompt:** "Create a table eval.sales_transactions in my warehouse with columns: transaction_id INT NOT NULL, customer_id INT, product_id INT, product_name VARCHAR(100), category VARCHAR(50), quantity INT, unit_price DECIMAL(10,2), total_amount DECIMAL(10,2), transaction_date DATE, region VARCHAR(20)"
- **Expected:** Table created with exact schema
- **Pass criteria:** Table exists with all 10 columns and correct types

### DWA-03: Insert Known Data (Consistency Test Anchor)
- **Prompt:** "Insert these 5 rows into eval.sales_transactions in my warehouse: (1,1,1,'Product_001','Electronics',2,9.99,19.98,'2025-01-01','East'), (2,2,2,'Product_002','Clothing',3,19.98,59.94,'2025-01-02','West'), (3,3,3,'Product_003','Food',4,29.97,119.88,'2025-01-03','North'), (4,4,4,'Product_004','Home',5,39.96,199.80,'2025-01-04','South'), (5,5,5,'Product_005','Sports',6,49.95,299.70,'2025-01-05','East')"
- **Expected:** 5 rows inserted
- **Pass criteria:** Row count = 5 (verified by sqldw-consumption-cli)
- **Golden data:** See `evalsets/expected-results/sales_5rows.json`

### DWA-04: COPY INTO from CSV
- **Prompt:** "Load data from Files/sales_transactions_100.csv into eval.sales_transactions in my warehouse using COPY INTO"
- **Expected:** 100 rows loaded
- **Pass criteria:** Row count = 100

### DWA-05: MERGE / Upsert
- **Prompt:** "Merge into eval.sales_transactions from a staging table: update total_amount where transaction_id matches, insert new rows where no match"
- **Expected:** MERGE statement executed
- **Pass criteria:** Skill generates valid MERGE T-SQL and executes it

### DWA-06: Create View
- **Prompt:** "Create a view eval.vw_sales_by_region that shows region, count of transactions, and total amount from eval.sales_transactions"
- **Expected:** View created
- **Pass criteria:** View returns correct aggregation

### DWA-07: Warehouse Time Travel
- **Prompt:** "Query eval.sales_transactions as of 1 hour ago from my warehouse"
- **Expected:** Time travel query executed
- **Pass criteria:** Skill uses `FOR TIMESTAMP AS OF` syntax

### DWA-08: Transaction with Rollback
- **Prompt:** "In my warehouse, start a transaction, delete all rows from eval.sales_transactions where category='Food', then rollback"
- **Expected:** Transaction rolled back, no rows deleted
- **Pass criteria:** Row count unchanged after rollback

### DWA-12: Drop Cleanup
- **Prompt:** "Drop table eval.sales_transactions and schema eval from my warehouse"
- **Expected:** Objects dropped
- **Pass criteria:** Objects no longer exist

## Write Operations (for consistency pairing)

| Write Case | Table | Rows | Paired Read Skill |
|-----------|-------|------|-------------------|
| DWA-03 | eval.sales_transactions | 5 | sqldw-consumption-cli |
| DWA-04 | eval.sales_transactions | 100 | sqldw-consumption-cli |

## Data Teardown (run LAST — after all test cases)

Clean up all data objects created by this plan. Do NOT drop the shared `{{WAREHOUSE}}`.
1. `DROP VIEW IF EXISTS eval.vw_sales_by_region`
2. `DROP TABLE IF EXISTS eval.sales_transactions`
3. `DROP SCHEMA IF EXISTS eval`

> Note: DWA-12 already tests drop operations. If DWA-12 passed, these may already be gone. The teardown is defensive.

## Expected Token Range
- 1200–3000 tokens per invocation
