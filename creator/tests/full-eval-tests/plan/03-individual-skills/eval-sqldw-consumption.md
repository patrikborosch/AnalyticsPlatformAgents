# Eval Plan: sqldw-consumption-cli

## Skill Overview
- **Skill:** `sqldw-consumption-cli`
- **Category:** SQL Data Warehouse (Read)
- **Purpose:** Execute read-only T-SQL queries against Fabric Warehouse, Lakehouse SQL Endpoints, and Mirrored Databases

## Pre-requisites
- Shared `{{WAREHOUSE}}` provisioned by runner (Phase 0b)
- Lakehouse `{{LAKEHOUSE}}` provisioned by runner (Phase 0b) — needed for DWC-06

## Data Setup (run FIRST — before any test cases)

This plan provisions its own data. Do NOT depend on sqldw-authoring having run first. Warehouse tables (`eval.sales_transactions`, `eval.customers`) are chain-shared with `eval-sqldw-authoring` and `eval-sqldw-authoring-plus-consumption` -- the runner serializes all sqldw plans into one chain so the un-prefixed names never collide in parallel (see [00-overview.md Parallel-Safety Contract rule #1, chain-serialized exception](../00-overview.md#parallel-safety-contract-informational-runner-enforced)). The lakehouse table for DWC-06 uses a plan-prefixed name (`eval_sqldw_sales_transactions_lh`) because `{{LAKEHOUSE}}` is shared across chains and follows the default plan-prefix rule.

1. Create schema `eval` in `{{WAREHOUSE}}` (if not exists)
2. `DROP TABLE IF EXISTS eval.sales_transactions` — clear any leftover data
3. Create table `eval.sales_transactions` with columns: transaction_id INT NOT NULL, customer_id INT, product_id INT, product_name VARCHAR(100), category VARCHAR(50), quantity INT, unit_price DECIMAL(10,2), total_amount DECIMAL(10,2), transaction_date DATE, region VARCHAR(20)
4. Insert the 5 golden rows:
   ```sql
   INSERT INTO eval.sales_transactions VALUES
   (1,1,1,'Product_001','Electronics',2,9.99,19.98,'2025-01-01','East'),
   (2,2,2,'Product_002','Clothing',3,19.98,59.94,'2025-01-02','West'),
   (3,3,3,'Product_003','Food',4,29.97,119.88,'2025-01-03','North'),
   (4,4,4,'Product_004','Home',5,39.96,199.80,'2025-01-04','South'),
   (5,5,5,'Product_005','Sports',6,49.95,299.70,'2025-01-05','East')
   ```
5. Create `eval.customers` table for DWC-04 JOIN test:
   ```sql
   CREATE TABLE eval.customers (customer_id INT, customer_name VARCHAR(50), tier VARCHAR(20))
   INSERT INTO eval.customers VALUES (1,'Customer_1','Gold'),(2,'Customer_2','Silver'),(3,'Customer_3','Bronze'),(4,'Customer_4','Gold'),(5,'Customer_5','Silver')
   ```
6. Provision the lakehouse-side data for DWC-06 (lakehouse SQL endpoint read):
   - Drop Delta table `eval_sqldw_sales_transactions_lh` in `{{LAKEHOUSE}}` (if exists) via Spark SQL: `DROP TABLE IF EXISTS {{LAKEHOUSE}}.eval_sqldw_sales_transactions_lh`
   - Create Delta table `eval_sqldw_sales_transactions_lh` with the same 5 golden rows as `eval.sales_transactions`. Schema: transaction_id INT, customer_id INT, product_id INT, product_name STRING, category STRING, quantity INT, unit_price DECIMAL(10,2), total_amount DECIMAL(10,2), transaction_date DATE, region STRING.
   - Row count = 5.

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### DWC-01: Simple Row Count
- **Prompt:** "How many rows are in eval.sales_transactions in my warehouse?"
- **Expected result:** 5
- **Pass criteria:** Exact count match

### DWC-02: SELECT All (Consistency with DWA-03)
- **Prompt:** "Show all rows from eval.sales_transactions in my warehouse ordered by transaction_id"
- **Expected result:** Exact 5 rows matching DWA-03 insert data
- **Pass criteria:**
  - Row count = 5
  - transaction_id: [1, 2, 3, 4, 5]
  - product_name: ["Product_001", "Product_002", "Product_003", "Product_004", "Product_005"]
  - total_amount: [19.98, 59.94, 119.88, 199.80, 299.70]
  - **EXACT MATCH required — this is a consistency test**

### DWC-03: Filtered Query
- **Prompt:** "Query eval.sales_transactions in my warehouse where category = 'Electronics'"
- **Expected result:** Rows with category = Electronics only
- **Pass criteria:** All returned rows have category = 'Electronics'

### DWC-04: JOIN Query
- **Prompt:** "Join eval.sales_transactions with eval.customers on customer_id and show total sales per customer tier in my warehouse"
- **Expected result:** 3 rows (Bronze, Silver, Gold)
- **Pass criteria:** Tier names and totals match

### DWC-05: Export to CSV
- **Prompt:** "Export eval.sales_transactions from my warehouse to CSV"
- **Expected result:** CSV output or file generated
- **Pass criteria:** CSV contains correct headers and row count

### DWC-06: Lakehouse SQL Endpoint Query
- **Prompt:** "Query the eval_sqldw_sales_transactions_lh table from the lakehouse SQL endpoint of {{LAKEHOUSE}}"
- **Expected result:** Data returned from lakehouse via SQL
- **Pass criteria:** Row count = 5 matches lakehouse data created in Data Setup step 6

### DWC-07: Negative — Write attempt should fail/be refused
- **Prompt:** "Delete all rows from eval.sales_transactions in my warehouse"
- **Expected result:** Skill refuses or routes to authoring skill
- **Pass criteria:** No data deleted, user informed this is a read-only skill

## Data Teardown (run LAST — after all test cases)

Clean up all data objects created by this plan. Do NOT drop the shared `{{WAREHOUSE}}` or `{{LAKEHOUSE}}`.
1. `DROP TABLE IF EXISTS eval.customers`
2. `DROP TABLE IF EXISTS eval.sales_transactions`
3. `DROP SCHEMA IF EXISTS eval`
4. Drop Delta table `eval_sqldw_sales_transactions_lh` in `{{LAKEHOUSE}}` via Spark SQL: `DROP TABLE IF EXISTS {{LAKEHOUSE}}.eval_sqldw_sales_transactions_lh`

## Consistency Test Matrix

| Read Case | Data Source | Table | Verification |
|-----------|------------|-------|-------------|
| DWC-01 | Data Setup (step 4) | eval.sales_transactions | Row count = 5 |
| DWC-02 | Data Setup (step 4) | eval.sales_transactions | Cell-level exact match, 5 rows |
| DWC-04 | Data Setup (steps 4+5) | eval.sales_transactions + eval.customers | SUM = 699.30 (19.98+59.94+119.88+199.80+299.70) |

## Expected Token Range
- 800–2500 tokens per invocation
