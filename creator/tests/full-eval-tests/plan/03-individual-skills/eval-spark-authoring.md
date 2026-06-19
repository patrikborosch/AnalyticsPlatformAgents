# Eval Plan: spark-authoring-cli

## Skill Overview
- **Skill:** `spark-authoring-cli`
- **Category:** Spark / Data Engineering (Write)
- **Purpose:** Manage Fabric workspaces, develop notebooks, create lakehouses, design pipelines, provision infrastructure

## Pre-requisites
- Shared `{{LAKEHOUSE}}` lakehouse provisioned by runner (Phase 0b)
- Spark capacity available
- Fabric API authentication configured
- Eval datasets generated per `01-data-generation.md`

## Data Setup (run FIRST — before any test cases)

Clean up any leftover tables from a prior run to ensure a clean slate. Use plan-prefixed table names so this plan can run in parallel with other plans that share `{{LAKEHOUSE}}`:
1. Drop Delta table `eval_spark_products` in `{{LAKEHOUSE}}` (if exists) via Spark SQL: `DROP TABLE IF EXISTS {{LAKEHOUSE}}.eval_spark_products`
2. Drop Delta table `eval_spark_sales_transactions` in `{{LAKEHOUSE}}` (if exists) via Spark SQL: `DROP TABLE IF EXISTS {{LAKEHOUSE}}.eval_spark_sales_transactions`

> Note: SA-01 tests lakehouse creation — since the runner already provisioned `{{LAKEHOUSE}}`, SA-01 should verify the lakehouse exists rather than creating a duplicate. The test is still valid as it exercises the skill's create-or-verify behavior.

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Case Types

Tests are split into two categories to keep the eval fast:

- **Description tests** — invoke the skill and verify the text/plan output only. No real Fabric API calls required. Pass/fail based on content of skill response.
- **Infrastructure tests** — invoke the skill and verify real Fabric API state (workspace, lakehouse, table, notebook, session exists and has correct data).

> **Important:** For description tests, do NOT create workspaces, lakehouses, notebooks, or run Spark jobs. Just invoke the skill prompt and evaluate the response text.

## Test Cases

### SA-01: Create a Lakehouse *(infrastructure)*
- **Prompt:** "Create a new lakehouse called {{LAKEHOUSE}} in my workspace with support for schemas"
- **Expected:** Lakehouse `{{LAKEHOUSE}}` created via Fabric API
- **Pass criteria:** Lakehouse exists and is accessible
- **Metrics:** Success rate, token usage

### SA-02: Create a Notebook *(infrastructure)*
- **Prompt:** "Create a PySpark notebook that reads a CSV from Files/sales_transactions.csv and writes it as a Delta table called eval_spark_sales_transactions in the lakehouse {{LAKEHOUSE}}"
- **Expected:** Notebook created with correct PySpark code
- **Pass criteria:** Notebook artifact exists (list items); confirm `updateDefinition` returned `Succeeded` — do NOT call `getDefinition` to re-verify
- **Metrics:** Success rate, token usage

### SA-03: Create a Livy Session *(infrastructure)*
- **Prompt:** "Create a Livy session against lakehouse {{LAKEHOUSE}} using Starter Pool with Medium compute (driverMemory 56g, driverCores 8, executorMemory 56g, executorCores 8)"
- **Expected:** Livy session started and session ID returned
- **Pass criteria:** Session ID returned, session state is "idle" or "busy"
- **Body format:** Flat JSON with `name`, `driverMemory`, `driverCores`, `executorMemory`, `executorCores` — NOT wrapped in `{"payload": ...}`

### SA-04: Organize Lakehouse Tables *(infrastructure)*
- **Prompt:** "Organize the tables in {{LAKEHOUSE}} into schemas: raw for ingested data, curated for cleaned data"
- **Expected:** Schema organization applied
- **Pass criteria:** Skill executes without error

### SA-06: Spark Configuration *(description)*
- **Prompt:** "In all notebooks and livy jobs you are creating for the rest of spark authoring tests, as well as in any active livy session, set Spark configuration for {{LAKEHOUSE}}: spark.sql.shuffle.partitions=8, spark.executor.memory=56g and spark.executor.cores=8"
- **Expected:** Skill describes the correct configuration to apply
- **Pass criteria:** Response includes all 3 correct key=value pairs (`spark.sql.shuffle.partitions=8`, `spark.executor.memory=56g`, `spark.executor.cores=8`) and notes the 56g/8-core Medium tier pairing
- **Note:** Memory value 56g matches Medium compute tier (8 cores = 56g). Do not mix 28g with 8 cores — that is the Small tier (4 cores).
- **Verification:** Text response only — do NOT create sessions or modify notebooks

### SA-07: Delta Lake Table Creation via Spark *(infrastructure)*
- **Prompt:** "Using PySpark, create a Delta table called eval_spark_products with columns: product_id INT, product_name STRING, category STRING, base_price DECIMAL(10,2) in lakehouse {{LAKEHOUSE}}"
- **Expected:** Delta table created with correct schema
- **Pass criteria:** Table exists with exact column names and types

### SA-08: Write Known Data for Consistency Testing *(infrastructure)*
- **Prompt:** "Write the following 5 rows to the eval_spark_products table in {{LAKEHOUSE}}: (1,'Product_001','Electronics',9.99), (2,'Product_002','Clothing',19.98), (3,'Product_003','Food',29.97), (4,'Product_004','Home',39.96), (5,'Product_005','Sports',49.95)"
- **Expected:** 5 rows inserted
- **Pass criteria:** Row count = 5 (verified later by consumption skill)
- **Golden data:** See `evalsets/expected-results/products_5rows.json`

### SA-09: Bulk Data Load *(infrastructure)*
- **Pre-step:** Upload `evalsets/data-generation/sales_transactions_100.csv` to `Files/sales_transactions_100.csv` in `{{LAKEHOUSE}}` (via OneLake API or Fabric upload)
- **Prompt:** "I uploaded a CSV file at Files/sales_transactions_100.csv in {{LAKEHOUSE}}. Load it into a Delta table called eval_spark_sales_transactions. It has 100 rows of sales data with columns like transaction_id, customer_id, product info, categories, quantities, prices, dates, and regions."
- **Expected:** 100 rows loaded into Delta table with all specified columns
- **Pass criteria:** Table exists with 100 rows, has all 10 columns including `region`
- **Schema verification:** Must have columns: transaction_id (INT), customer_id (INT), product_id (INT), product_name (STRING), category (STRING), quantity (INT), unit_price (DECIMAL), total_amount (DECIMAL), transaction_date (DATE), region (STRING)
- **Golden data:** See `evalsets/expected-results/sales_100_golden.json`

### SA-10: Negative — Ambiguous prompt *(description)*
- **Prompt:** "Set up my data"
- **Expected:** Skill should ask for clarification or provide guidance, not fail silently
- **Pass criteria:** Agent asks clarifying questions or provides structured options
- **Verification:** Text response only — do NOT create any resources

## Write Operations (for consistency pairing)

| Write Case | Table | Rows | Paired Read Skill |
|-----------|-------|------|-------------------|
| SA-08 | eval_spark_products | 5 | spark-consumption-cli |
| SA-09 | eval_spark_sales_transactions | 100 | spark-consumption-cli |

---

## Notebook Code Authoring Tests (SA-11 to SA-23)

Added after merging `notebook-authoring-cli` into `spark-authoring-cli`. All tests below are **description tests** — evaluate response text only, no Fabric API calls.

### SA-11: Default Lakehouse — Read CSV with Relative Path *(description)*
- **Prompt:** "Write PySpark code for a Fabric notebook cell that reads Files/sales_transactions_100.csv from the default lakehouse and shows the first 10 rows"
- **Expected:** Uses relative path `Files/`, pre-existing `spark` session, `spark.read.csv`
- **Pass criteria:** (1) path starts with `Files/` not ABFSS, (2) no `SparkSession.builder`, (3) uses `spark.read.csv` or `spark.read.format("csv")`

### SA-12: Non-Default Lakehouse — ABFSS Path + Schema *(description)*
- **Prompt:** "Write a notebook cell to read Delta table 'products' from a non-default schema-enabled lakehouse (workspace ID 'ws-123', lakehouse ID 'lh-456', schema 'dbo') using PySpark"
- **Expected:** ABFSS path with dynamic endpoint, schema segment `Tables/dbo/products`
- **Pass criteria:** (1) uses `notebookutils.conf.get("trident.onelake.endpoint")`, (2) path includes `/Tables/dbo/products`, (3) no hardcoded `onelake.dfs.fabric.microsoft.com`

### SA-13: Spark SQL — Cross-Lakehouse 4-Part Name *(description)*
- **Prompt:** "Write a %%sql cell to query table 'sales_transactions' in schema 'dbo' from lakehouse 'AnalyticsLH' in workspace 'DataTeam'"
- **Expected:** `%%sql` magic, fully-qualified 4-part dotted name with backticks
- **Pass criteria:** (1) `%%sql` at cell start, (2) 4-part reference `` `DataTeam`.`AnalyticsLH`.`dbo`.`sales_transactions` ``

### SA-14: %%configure — Memory + Lakehouse Binding *(description)*
- **Prompt:** "Write a %%configure cell to set driver and executor memory to 56g with 8 cores, enable native execution, and attach default lakehouse 'eval_sales_lh'"
- **Expected:** `%%configure -f` JSON with resources, `spark.native.enabled`, and `defaultLakehouse`
- **Pass criteria:** (1) `%%configure -f`, (2) memory=56g cores=8, (3) `spark.native.enabled`, (4) `defaultLakehouse` block with `name`, (5) notes must be first cell

### SA-15: NotebookUtils — Builtin Resource + file: Prefix *(description)*
- **Prompt:** "Write notebook code to read a CSV config file from the notebook's builtin resource folder using both Spark and pandas"
- **Expected:** Spark path uses `file:{notebookutils.nbResPath}/builtin/...`, pandas uses `{notebookutils.nbResPath}/builtin/...` without `file:`
- **Pass criteria:** (1) uses `notebookutils.nbResPath`, (2) Spark path has `file:` prefix, (3) pandas path does not have `file:` prefix

### SA-16: NotebookUtils — Run Child Notebook with Parameters *(description)*
- **Prompt:** "Write notebook code to run a child notebook called 'process_sales' with parameters region='East' and year=2025, capture its exit value"
- **Expected:** Uses `notebookutils.notebook.run()` with arguments dict, captures return value
- **Pass criteria:** (1) `notebookutils.notebook.run("process_sales", ...)`, (2) passes `{"region": "East", "year": "2025"}`, (3) captures exit value

### SA-17: NotebookUtils — Mount + Credentials *(description)*
- **Prompt:** "Write notebook code to: (1) get a secret from Azure Key Vault, (2) mount an ADLS Gen2 container using AAD token, (3) read a parquet file from the mount point"
- **Expected:** Uses `getSecret` for Key Vault, `fs.mount` with AAD auth, reads from mount path
- **Pass criteria:** (1) `notebookutils.credentials.getSecret(...)`, (2) `notebookutils.fs.mount(...)` with ABFSS source, (3) reads from mount point, (4) no hardcoded secrets

### SA-18: NotebookUtils — Variable Library *(description)*
- **Prompt:** "Write notebook code to read a lakehouse name and a feature flag from a Variable Library called 'AppConfig', and use them to conditionally load data"
- **Expected:** Uses `getLibrary()` with dot-notation property access, string comparison for boolean
- **Pass criteria:** (1) `notebookutils.variableLibrary.getLibrary("AppConfig")`, (2) property access (e.g., `lib.lakehouse_name`), (3) string comparison for boolean (not `bool()`)

### SA-19: NotebookUtils — Runtime Context *(description)*
- **Prompt:** "Write notebook code that checks if the notebook is running in a pipeline, and if so, logs the notebook name and workspace ID"
- **Expected:** Uses `notebookutils.runtime.context` to check `isForPipeline` and access metadata
- **Pass criteria:** (1) `notebookutils.runtime.context`, (2) checks `isForPipeline`, (3) accesses `currentNotebookName` and `currentWorkspaceId`

### SA-20: PySpark — Filter + Aggregate + Write Delta *(description)*
- **Prompt:** "Write a notebook cell that reads the sales_transactions table from the default lakehouse, filters rows where quantity > 5 and region = 'East', groups by category with average total_amount, and saves the result as a Delta table called 'east_sales_summary'"
- **Expected:** Complete PySpark pipeline: read → filter → groupBy → agg → write delta
- **Pass criteria:** (1) reads from `sales_transactions`, (2) filters `quantity > 5` AND `region == 'East'`, (3) `groupBy("category")`, (4) uses `avg`, (5) writes as delta

### SA-21: Anti-Pattern — No Standalone App *(description)*
- **Prompt:** "Create a Spark application to process sales data in Fabric"
- **Expected:** Uses pre-existing `spark` session, never `SparkSession.builder`
- **Pass criteria:** (1) does NOT contain `SparkSession.builder`, (2) uses built-in `spark` variable
- **Note:** Negative test

### SA-22: Anti-Pattern — No Hardcoded Endpoint *(description)*
- **Prompt:** "Write PySpark code to read a parquet file from a non-default lakehouse using ABFSS path"
- **Expected:** Dynamic endpoint retrieval, not hardcoded
- **Pass criteria:** (1) does NOT contain literal `onelake.dfs.fabric.microsoft.com`, (2) uses `notebookutils.conf.get`
- **Note:** Negative test

### SA-23: NotebookUtils — Run Multiple Notebooks with DAG *(description)*
- **Prompt:** "Write notebook code to run three notebooks in parallel: 'prep_customers', 'prep_products', 'prep_regions', then after all three finish, run 'build_summary' that depends on them"
- **Expected:** Uses `notebookutils.notebook.runMultiple()` with DAG structure defining dependencies
- **Pass criteria:** (1) `notebookutils.notebook.runMultiple(...)`, (2) DAG JSON has 4 entries, (3) `build_summary` depends on the other 3, (4) first 3 have no dependencies (parallel)

---

## Connection Template Tests (SA-24 to SA-27)

Tests covering external data source access patterns from `connections.md` (common/notebook-authoring). All **description tests**.

### SA-24: External DB Connection — PostgreSQL *(description)*
- **Prompt:** "Write notebook code to connect to a PostgreSQL database using a Fabric connection and query a table into a DataFrame"
- **Expected:** Uses `notebookutils.connections.getCredential(...)`, extracts username/password, connects via psycopg2 or PySpark JDBC
- **Pass criteria:** (1) `notebookutils.connections.getCredential(...)`, (2) extracts `username` and `password` from credential, (3) uses `psycopg2` or JDBC, (4) no hardcoded credentials

### SA-25: External DB Connection — Azure SQL *(description)*
- **Prompt:** "Write notebook code to connect to an Azure SQL Database using a Fabric connection and read data into a Spark DataFrame"
- **Expected:** Uses `notebookutils.connections.getCredential(...)`, JDBC URL pattern for Azure SQL
- **Pass criteria:** (1) `notebookutils.connections.getCredential(...)`, (2) JDBC connection string with `sqlserver://` or `ODBC Driver`, (3) no hardcoded credentials

### SA-26: Cloud Storage — S3 Access *(description)*
- **Prompt:** "Write notebook code to read a CSV file from Amazon S3 using boto3 with credentials from a Fabric connection"
- **Expected:** Uses `notebookutils.connections.getCredential(...)`, boto3 client with extracted key/secret
- **Pass criteria:** (1) `notebookutils.connections.getCredential(...)`, (2) uses `boto3`, (3) extracts key/secret from credential object

### SA-27: Secrets Management — Key Vault Direct *(description)*
- **Prompt:** "Write notebook code to retrieve a secret named 'api-key' from Azure Key Vault and use it to configure an API client"
- **Expected:** Uses `notebookutils.credentials.getSecret(...)` with vault URL and secret name
- **Pass criteria:** (1) `notebookutils.credentials.getSecret("https://{vaultName}.vault.azure.net/", "api-key")`, (2) no hardcoded secrets, (3) uses retrieved secret value

---

## Spark SQL DDL/DML Tests (SA-28 to SA-30)

Tests covering Spark SQL DDL/DML operations from `lakehouse-tables.md` (common/notebook-authoring). All **description tests**.

### SA-28: Spark SQL DDL — Create Schema + Table *(description)*
- **Prompt:** "Write a %%sql cell to create a schema called 'analytics' and a Delta table 'monthly_sales' with columns month STRING, total DECIMAL(10,2) in the default lakehouse"
- **Expected:** `%%sql` magic, `CREATE SCHEMA IF NOT EXISTS`, `CREATE TABLE ... USING DELTA`
- **Pass criteria:** (1) `%%sql` at cell start, (2) `CREATE SCHEMA IF NOT EXISTS analytics`, (3) `CREATE TABLE IF NOT EXISTS` with correct columns, (4) `USING DELTA`

### SA-29: Spark SQL DML — MERGE/Upsert *(description)*
- **Prompt:** "Write a %%sql cell to perform a MERGE (upsert) into target table 'products' from source table 'staging_products' matching on product_id"
- **Expected:** `%%sql` with MERGE INTO ... USING ... ON syntax
- **Pass criteria:** (1) `%%sql` at cell start, (2) `MERGE INTO`, (3) `USING ... ON`, (4) `WHEN MATCHED THEN UPDATE`, (5) `WHEN NOT MATCHED THEN INSERT`

### SA-30: Delta Time Travel — Version Query *(description)*
- **Prompt:** "Write Spark SQL to query version 3 of the 'sales_transactions' table and also show its full change history"
- **Expected:** Uses `VERSION AS OF` and `DESCRIBE HISTORY`
- **Pass criteria:** (1) `VERSION AS OF 3`, (2) `DESCRIBE HISTORY`, (3) correct table reference syntax

---

## Schema Discovery Test (SA-31)

### SA-31: Schema Discovery — List Schemas and Tables *(description)*
- **Prompt:** "Write notebook code to list all schemas in the default lakehouse, then list all tables in the 'dbo' schema"
- **Expected:** Uses `SHOW SCHEMAS` and `SHOW TABLES IN dbo` or equivalent
- **Pass criteria:** (1) `SHOW SCHEMAS` or `spark.catalog` equivalent, (2) `SHOW TABLES IN dbo` or filtered catalog call, (3) handles schema-enabled lakehouse assumption

---

## Non-Python Language Tests (SA-32 to SA-33)

Tests verifying correct language magic usage for non-Python cells. All **description tests**.

### SA-32: Scala Cell — Read Delta Table *(description)*
- **Prompt:** "Write a Scala cell (%%spark) to read the 'products' Delta table from the default lakehouse and display the first 10 rows"
- **Expected:** Uses `%%spark` magic, Scala syntax, pre-existing `spark` session
- **Pass criteria:** (1) `%%spark` magic at cell start, (2) uses `spark.read` or `spark.table` in Scala syntax, (3) does NOT contain `SparkSession.builder`, (4) uses `.show(10)` or equivalent

### SA-33: SparkR Cell — Simple Aggregation *(description)*
- **Prompt:** "Write a SparkR cell to read the 'sales_transactions' table and compute average total_amount by region"
- **Expected:** Uses `%%sparkr` magic, SparkR API
- **Pass criteria:** (1) `%%sparkr` magic at cell start, (2) uses SparkR functions (e.g., `SparkR::sql`, `read.df`, or `tableToDF`), (3) aggregation by region

---

## NotebookUtils.fs Operations (SA-34 to SA-35)

### SA-34: NotebookUtils.fs — Copy and List Files *(description)*
- **Prompt:** "Write notebook code to list all CSV files in the default lakehouse Files/ folder, then copy a specific file to a subfolder called 'archive/'"
- **Expected:** Uses `notebookutils.fs.ls(...)` and `notebookutils.fs.cp(...)`
- **Pass criteria:** (1) `notebookutils.fs.ls("Files/")` or similar, (2) `notebookutils.fs.cp(...)` with source and destination, (3) correct lakehouse paths

### SA-35: NotebookUtils.fs — fastcp for Large Files *(description)*
- **Prompt:** "Write notebook code to copy a large parquet file from one lakehouse to another using the fastest available method"
- **Expected:** Uses `notebookutils.fs.fastcp(...)` with ABFSS paths
- **Pass criteria:** (1) uses `notebookutils.fs.fastcp(...)`, (2) ABFSS paths for both source and destination, (3) dynamic endpoint retrieval

---

## Metadata & Anti-Pattern Tests (SA-36 to SA-39)

### SA-36: Runtime Context — Lakehouse Metadata *(description)*
- **Prompt:** "Write notebook code to retrieve and print the default lakehouse name, ID, and workspace ID using the runtime context API"
- **Expected:** Uses `notebookutils.runtime.context` to access lakehouse metadata keys
- **Pass criteria:** (1) `notebookutils.runtime.context`, (2) accesses `defaultLakehouseName`, (3) accesses `defaultLakehouseId`, (4) accesses `defaultLakehouseWorkspaceId`

### SA-37: Anti-Pattern — No Mixed IDs/Names in ABFSS *(description)*
- **Prompt:** "Write PySpark code to read a Delta table from a non-default lakehouse. I know the workspace ID is 'ws-abc-123' and the lakehouse name is 'SalesLH'"
- **Expected:** Does NOT produce ABFSS path mixing workspace ID with lakehouse name; either asks for the lakehouse ID or uses an all-names approach
- **Pass criteria:** (1) does NOT produce `abfss://ws-abc-123@.../SalesLH/...` (mixed pattern), (2) either requests lakehouse ID, or uses all-names with `.Lakehouse` suffix, or uses dynamic resolution, (3) uses dynamic endpoint
- **Note:** Negative test — verifying the "never mix IDs and names" rule

### SA-38: NotebookUtils — Session Stop with Pipeline Check *(description)*
- **Prompt:** "Write notebook code that safely stops the Spark session only when NOT running in a Fabric pipeline"
- **Expected:** Checks `isForPipeline` from runtime context before stopping
- **Pass criteria:** (1) `notebookutils.runtime.context`, (2) checks `isForPipeline`, (3) conditionally calls `notebookutils.session.stop()`, (4) does NOT call stop when in pipeline mode

### SA-39: Unsupported Language — C# Request *(description)*
- **Prompt:** "Write a C# notebook cell in Fabric to process a Delta table"
- **Expected:** Informs user that C# is not a supported notebook language in Fabric
- **Pass criteria:** (1) does NOT generate C# code, (2) mentions that C# is not supported in Fabric notebooks, (3) suggests supported alternatives (Python/PySpark, Scala, SparkR, SQL)
- **Note:** Negative test

## Materialized Lake View Tests (SA-40 to SA-44)

Tests covering MLV authoring and incremental-refresh readiness from [`skills/spark-authoring-cli/resources/materialized-lake-view-patterns.md`](../../../../skills/spark-authoring-cli/resources/materialized-lake-view-patterns.md) and [`skills/spark-authoring-cli/resources/mlv-incremental-refresh-patterns.md`](../../../../skills/spark-authoring-cli/resources/mlv-incremental-refresh-patterns.md). All **description tests**.

### SA-40: MLV — Create Silver Cleansing MLV *(description)*
- **Prompt:** "Write Spark SQL to create a Materialized Lake View called silver.orders_clean that selects order_id, customer_id, product_id, order_date, and amount (cast to DECIMAL) from bronze.orders. Use data quality constraints to reject rows where order_id is null or amount is not positive. Partition by order_date."
- **Expected:** Uses `CREATE OR REPLACE MATERIALIZED LAKE VIEW`, quality constraints with `ON MISMATCH DROP`, `PARTITIONED BY`
- **Pass criteria:** (1) `CREATE OR REPLACE MATERIALIZED LAKE VIEW silver.orders_clean`, (2) `CONSTRAINT` with `ON MISMATCH DROP` for null check and positive amount, (3) `PARTITIONED BY (order_date)`, (4) `CAST(amount AS DECIMAL(...))` — any valid precision/scale accepted
- **Verification:** Text response only — no API calls needed

### SA-41: MLV — Design Denormalized Silver Join *(description)*
- **Prompt:** "Design a Materialized Lake View that joins silver.orders_clean with silver.customers_clean on customer_id and silver.products_clean on product_id to create a denormalized silver.order_details view. Include order_id, order_date, amount, customer_name, region, and category."
- **Expected:** Uses `CREATE OR REPLACE MATERIALIZED LAKE VIEW` with `INNER JOIN`, selects columns from all three sources
- **Pass criteria:** (1) `CREATE OR REPLACE MATERIALIZED LAKE VIEW silver.order_details`, (2) two `INNER JOIN` clauses on `customer_id` and `product_id`, (3) selects columns from all three tables, (4) does NOT use `RIGHT JOIN` or `FULL OUTER JOIN`
- **Verification:** Text response only — no API calls needed

### SA-42: MLV — Gold Aggregate Layer *(description)*
- **Prompt:** "Write Spark SQL for a Gold-layer Materialized Lake View called gold.daily_revenue that aggregates silver.order_details by order_date and region, computing total revenue and order count."
- **Expected:** Uses `CREATE OR REPLACE MATERIALIZED LAKE VIEW`, `GROUP BY`, `SUM`, `COUNT`
- **Pass criteria:** (1) `CREATE OR REPLACE MATERIALIZED LAKE VIEW gold.daily_revenue`, (2) `SUM(amount)` or similar for revenue, (3) `COUNT(*)` or `COUNT(order_id)` for order count, (4) `GROUP BY order_date, region`, (5) does NOT use `COUNT(DISTINCT ...)` (forces full refresh; other aggregates like `AVG`/`MIN`/`MAX` are IR-eligible when source tables are partitioned on the GROUP BY column, so they're not asserted against here)
- **Verification:** Text response only — no API calls needed

### SA-43: MLV — Incremental Refresh Readiness Review *(description)*
- **Prompt:** "Review this MLV definition for incremental refresh readiness: CREATE MATERIALIZED LAKE VIEW silver.deduped AS SELECT customer_id, customer_name FROM (SELECT customer_id, customer_name, ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC) AS rn FROM bronze.customers) sub WHERE sub.rn = 1"
- **Expected:** Skill identifies hard blockers: `ROW_NUMBER()` window function, effective deduplication via subquery; recommends full refresh or safe rewrite
- **Pass criteria:** (1) flags `ROW_NUMBER()` as a window-function blocker, (2) identifies the query as not incremental-refresh-safe, (3) recommends full refresh or suggests a rewrite without blockers, (4) does NOT claim the query is incremental-refresh-safe
- **Verification:** Text response only — no API calls needed

### SA-44: MLV — Refresh Command and Lifecycle *(description)*
- **Prompt:** "Explain how to refresh a Materialized Lake View called silver.orders_clean. Include the SQL command, when to use manual vs scheduled refresh, and how to check refresh status."
- **Expected:** Shows `REFRESH MATERIALIZED LAKE VIEW silver.orders_clean FULL` command, explains refresh strategies, points to the Lakehouse **Materialized lake views → Manage → Recent runs** UI for refresh status (Fabric does not expose a SQL command for MLV refresh status)
- **Pass criteria:** (1) `REFRESH MATERIALIZED LAKE VIEW silver.orders_clean FULL`, (2) mentions manual full-refresh use cases (troubleshooting / after correction), (3) mentions scheduled refresh via the lakehouse Manage view (with lineage), (4) references the Manage / Recent runs UI (or equivalent) for checking refresh status — does NOT fabricate a SQL staleness API
- **Verification:** Text response only — no API calls needed

---

## Data Teardown (run LAST — after all test cases)

Clean up data objects created by this plan. Do NOT drop the shared `{{LAKEHOUSE}}` lakehouse.
1. Drop Delta table `eval_spark_products` via Spark SQL: `DROP TABLE IF EXISTS {{LAKEHOUSE}}.eval_spark_products`
2. Drop Delta table `eval_spark_sales_transactions` via Spark SQL: `DROP TABLE IF EXISTS {{LAKEHOUSE}}.eval_spark_sales_transactions`
3. Clean up any notebooks created during the eval (list workspace items of type Notebook with name containing "eval", delete them)

## Expected Token Range
- 1500–4000 tokens per invocation (infrastructure tests)
- 1000–3000 tokens per invocation (description tests)
