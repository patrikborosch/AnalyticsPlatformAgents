# Eval Plan: semantic-model-consumption

## Skill Overview
- **Skill:** `semantic-model-consumption`
- **Category:** Power BI Semantic Model Consumption (Read)
- **Purpose:** Execute read-only DAX queries via MCP server ExecuteQuery tool to discover semantic model metadata (tables, columns, measures, relationships) and retrieve data from a semantic model

## Pre-requisites
- Fabric workspace with capacity assigned — uses `EVAL_WORKSPACE` from Phase 0
- Authentication configured (`az login`)
- Shared `{{LAKEHOUSE}}` lakehouse provisioned by runner (Phase 0b)
- MCP server with `ExecuteQuery` capability available

## Data Setup (run FIRST — before any test cases)

This plan provisions its own semantic model. Do NOT depend on powerbi-authoring having run first. Use plan-prefixed Delta table names so this plan can run in parallel with other plans that share `{{LAKEHOUSE}}`.

1. Ensure Delta tables exist in `{{LAKEHOUSE}}`:
   - `eval_powerbi_sales_transactions` (100 rows) — upload from `evalsets/data-generation/sales_transactions_100.csv` and load as Delta table (overwrite)
   - `eval_powerbi_products` (5 rows) — create with: (1,'Product_001','Electronics',9.99), (2,'Product_002','Clothing',19.98), (3,'Product_003','Food',29.97), (4,'Product_004','Home',39.96), (5,'Product_005','Sports',49.95) (overwrite)
2. Delete semantic model `eval_sales_directlake` if pre-existing
3. Create semantic model `eval_sales_directlake` (Direct Lake) connected to `{{LAKEHOUSE}}` in workspace `{{WORKSPACE}}`:
   - Tables: SalesTransactions (maps to eval_powerbi_sales_transactions, 10 columns), Products (maps to eval_powerbi_products, 4 columns)
   - Measures: `Total Revenue` = SUM(SalesTransactions[total_amount]) format $#,##0.00, `Average Price` = AVERAGE(SalesTransactions[unit_price]) format $#,##0.00
   - Relationship: SalesTransactions[product_id] → Products[product_id], many-to-one, single cross-filter
4. Verify model is queryable (wait for refresh if needed)

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### PC-01: List Tables via INFO.VIEW.TABLES
- **Prompt:** "List all tables in the eval_sales_directlake semantic model in workspace {{WORKSPACE}}"
- **Expected:** INFO.VIEW.TABLES() query returns SalesTransactions and Products
- **Pass criteria:** Output includes tables named `SalesTransactions` and `Products`; query executes without error

### PC-02: List Columns for SalesTransactions Table
- **Prompt:** "Show all columns of the SalesTransactions table in eval_sales_directlake"
- **Expected:** INFO.VIEW.COLUMNS() filtered to SalesTransactions table returns all 10 columns
- **Pass criteria:** Columns listed: transaction_id (int64, key), customer_id (int64), product_id (int64), product_name (string), category (string), quantity (int64), unit_price (decimal), total_amount (decimal), transaction_date (dateTime), region (string) with correct data types

### PC-03: List Columns for Products Table
- **Prompt:** "Show all columns of the Products table in eval_sales_directlake"
- **Expected:** INFO.VIEW.COLUMNS() filtered to Products table returns all 4 columns
- **Pass criteria:** Columns listed: product_id (int64, key), product_name (string), category (string), base_price (decimal) with correct data types

### PC-04: List Measures with Expressions
- **Prompt:** "What measures exist in eval_sales_directlake? Show their names, expressions, and format strings"
- **Expected:** INFO.VIEW.MEASURES() returns both measures with DAX expressions
- **Pass criteria:**
  - `Total Revenue` with expression `SUM(SalesTransactions[total_amount])` and format `$#,##0.00`
  - `Average Price` with expression `AVERAGE(SalesTransactions[unit_price])` and format `$#,##0.00`

### PC-05: Discover Relationships
- **Prompt:** "Show the relationships in eval_sales_directlake semantic model"
- **Expected:** INFO.VIEW.RELATIONSHIPS() returns the SalesTransactions-to-Products relationship
- **Pass criteria:** One relationship from SalesTransactions[product_id] to Products[product_id]; cardinality = many-to-one; cross-filter direction = single

### PC-06: Scope Estimation — Count Tables, Columns, Measures
- **Prompt:** "How many tables, columns, and measures are in eval_sales_directlake?"
- **Expected:** Scope estimation queries return counts: 2 tables (SalesTransactions, Products), 14 columns (10 SalesTransactions + 4 Products), 2 measures
- **Pass criteria:** Counts match expected values

### PC-07: Data Query — EVALUATE with SUMMARIZECOLUMNS
- **Prompt:** "Run a DAX query on eval_sales_directlake to show Total Revenue by category"
- **Expected:** SUMMARIZECOLUMNS query with SalesTransactions[category] and [Total Revenue]
- **Pass criteria:** DAX query executes without error; results show 5 categories with correct revenue amounts: Home = $40,959.00, Food = $34,365.60, Clothing = $28,171.80, Electronics = $22,377.60, Sports = $17,982.00

### PC-08: Negative — Ambiguous Prompt
- **Prompt:** "Query my Power BI data"
- **Expected:** Skill asks for clarification — which semantic model, what data or metadata to retrieve
- **Pass criteria:** Agent does not fail silently or make assumptions; asks the user for missing details (model name, query intent)

## Data Teardown (run LAST — after all test cases)

Clean up objects created by this plan. Do NOT drop the shared `{{LAKEHOUSE}}` lakehouse.
1. Delete semantic model `eval_sales_directlake`
2. Drop Delta tables `eval_powerbi_sales_transactions` and `eval_powerbi_products` from `{{LAKEHOUSE}}`

## Consistency Test Matrix

| Read Case | Data Source | Verification |
|-----------|------------|--------------|
| PC-01 | Data Setup (step 3) | SalesTransactions and Products tables exist |
| PC-02 | Data Setup (step 3) | 10 columns with correct types |
| PC-03 | Data Setup (step 3) | 4 columns with correct types |
| PC-04 | Data Setup (step 3) | 2 measures with correct expressions |
| PC-05 | Data Setup (step 3) | SalesTransactions[product_id] → Products[product_id] |

## Expected Token Range
- 800–3000 tokens per invocation
