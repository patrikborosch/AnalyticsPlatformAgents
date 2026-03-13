# Microsoft Fabric Artifacts Reference

## Complete Artifact Type Catalogue

### Storage Items

#### Lakehouse
- **Engine:** Apache Spark (PySpark, SparkSQL, Scala, R)
- **Storage:** Delta Lake tables + unstructured Files in OneLake
- **Access:** Spark API (read/write), SQL Analytics Endpoint (read-only T-SQL)
- **Key Features:**
  - Delta Lake format: ACID transactions, MERGE, schema evolution, time travel
  - Files section: store raw files (CSV, JSON, Parquet, Excel, XML) before processing into tables
  - Tables section: managed Delta Lake tables
  - Automatic V-Order optimization on write
  - SQL Analytics Endpoint auto-generated for every table (read-only)
- **Use Cases:** L0 landing (files + initial tables), L1 persistence (SCD2, incremental), data engineering
- **Limits:** No referential integrity enforcement, no stored procedures, write through Spark only

#### Warehouse
- **Engine:** Distributed T-SQL engine (MPP)
- **Storage:** Delta Lake (managed by SQL engine) in OneLake
- **Access:** T-SQL (full DML: SELECT, INSERT, UPDATE, DELETE, MERGE)
- **Key Features:**
  - T-SQL stored procedures, views, functions
  - Schemas for logical grouping
  - Cross-database queries to Lakehouse SQL Endpoints
  - Automatic clustered columnstore index
  - Nonclustered indexes for point lookups
  - Statistics auto-created
  - CLONE TABLE for zero-copy clones
- **Use Cases:** L2 presentation (star schema), metadata repository, consumption layer
- **Limits:** No Spark access (T-SQL only), no real-time streaming ingestion

#### Eventhouse
- **Engine:** Kusto (KQL — Kusto Query Language)
- **Storage:** Kusto-optimized columnar store
- **Access:** KQL queries, KQL Queryset, Real-Time Dashboards
- **Key Features:**
  - Contains one or more KQL Databases
  - Optimized for time-series and log analytics
  - Native streaming ingestion (sub-second latency)
  - Ingestion from Eventstreams, Event Hubs, Kafka
  - Materialized Views for pre-aggregation
  - Update policies for transform-on-ingest
  - Retention policies per table
  - OneLake availability (query Delta tables via shortcuts)
- **Use Cases:** L4 real-time, IoT telemetry, log analytics, operational dashboards
- **Limits:** Not designed for traditional DWH query patterns, no MERGE/UPDATE

#### KQL Database
- Individual database within an Eventhouse
- Separate namespace for tables, functions, materialized views
- Independent retention and caching policies

### Processing Items

#### Notebook
- **Languages:** PySpark, SparkSQL, Scala, R, Python (no Spark)
- **Attached Resources:** Must attach to a Lakehouse (default Lakehouse for table resolution)
- **Key Features:**
  - Parameterized execution (from Pipelines or other Notebooks)
  - Session-scoped Spark configuration
  - Magic commands: `%%sql`, `%%pyspark`, `%%scala`, `%%r`
  - mssparkutils for file operations, credentials, notebook orchestration
  - Can read/write Delta tables, files, and external sources via JDBC/ODBC
  - Can query Warehouse via JDBC (for metadata reads)
  - Supports `%run` for shared utility Notebooks
- **Use Cases:** L0 ingestion, L1 SCD2 merge, quality checks, data transformations

#### Spark Job Definition
- Scheduled/parameterized Spark job (PySpark .py file or .jar)
- Alternative to Notebook for production batch jobs
- Better for CI/CD integration (code in Git, no notebook UI)

#### Dataflow Gen2
- **Engine:** Power Query (M language)
- **Key Features:**
  - 300+ connectors (no-code/low-code)
  - Staging via Lakehouse (for performance)
  - Output to Lakehouse tables, Warehouse tables, or other destinations
  - Fast Copy for high-volume loads
- **Use Cases:** Simple source-to-landing for supported connectors, non-technical users
- **Limits:** Not suitable for complex SCD2 logic, limited programmability

#### Stored Procedure (Warehouse)
- T-SQL stored procedures within a Warehouse
- Full DML support: INSERT, UPDATE, DELETE, MERGE
- TRY/CATCH error handling
- Can reference tables in other Warehouses or Lakehouse SQL Endpoints via three-part naming

### Orchestration Items

#### Data Pipeline
- **Engine:** ADF-compatible orchestration engine
- **Key Activities:**
  - **Copy Data:** Move data from 100+ connectors to Lakehouse/Warehouse
  - **Notebook:** Execute a Notebook with parameters
  - **Stored Procedure:** Execute a Warehouse stored procedure
  - **Dataflow:** Execute a Dataflow Gen2
  - **ForEach:** Loop over an array of items
  - **If Condition:** Conditional branching
  - **Switch:** Multi-branch conditional
  - **Set Variable / Append Variable:** Pipeline variable management
  - **Lookup:** Query a table and return results as pipeline variable
  - **Get Metadata:** Get file/folder metadata
  - **Wait:** Pause pipeline
  - **Web:** Call HTTP endpoints
  - **Fail:** Explicitly fail the pipeline
  - **Script:** Execute SQL scripts (alternative to Stored Procedure)
- **Error Handling:** Per-activity success/failure/completion paths, retry policies
- **Parameterization:** Pipeline parameters passed to child activities
- **Scheduling:** Cron-based or event-based triggers

### Streaming Items

#### Eventstream
- Ingest from: Event Hubs, Kafka, Azure IoT Hub, Custom App, Amazon Kinesis
- Route to: KQL Database (Eventhouse), Lakehouse, Warehouse, Custom App
- Transformations: Filter, Manage Fields, Group By (windowed), Union, Join
- Serialization: JSON, Avro, CSV

### Consumption Items

#### Semantic Model (Power BI Dataset)
- **Storage Modes:**
  - **DirectLake:** Reads Delta/Parquet files directly from OneLake (best performance)
  - **Import:** Copies data into model (scheduled refresh)
  - **DirectQuery:** Live queries to source (no caching)
- **Features:** DAX measures, calculated columns, RLS, relationships, hierarchies
- **Best Practice:** Use DirectLake on Warehouse/Lakehouse tables for zero-copy BI

#### Report (Power BI)
- Visualizations connected to a Semantic Model
- Can be deployed independently from Semantic Model

#### SQL Analytics Endpoint
- Auto-generated for every Lakehouse
- Read-only T-SQL access to Delta tables
- Used by: Warehouse cross-queries, BI tools, external T-SQL clients

#### Shortcuts
- **OneLake Shortcuts:** Point to data in another Lakehouse, Warehouse, or external storage (ADLS, S3)
- **Zero-copy:** No data movement — metadata pointer only
- **Use Case:** Cross-layer access (L1 Lakehouse → L2 Warehouse), cross-workspace sharing

### Governance Items

#### Workspace
- Top-level container for all Fabric items
- Security boundary (RBAC: Admin, Member, Contributor, Viewer)
- Assigned to a Fabric Capacity
- Can contain items of any type mix

#### Domain
- Logical grouping of related workspaces
- Scopes governance policies and endorsement
- Maps to business domains (Sales, Finance, Operations)

#### Endorsement
- **Promoted:** Team recommends this artifact
- **Certified:** Organization certifies this artifact as trusted
- Applied to Semantic Models, Lakehouses, Warehouses, etc.

## Fabric Capacity & Licensing Notes

| SKU | CU/s | Suitable For |
|---|---|---|
| F2 | 2 | Dev/test, small workloads |
| F4 | 4 | Small production |
| F8 | 8 | Medium workloads |
| F16 | 16 | Medium-large |
| F32 | 32 | Large production |
| F64+ | 64+ | Enterprise-scale |

- All Fabric items consume Capacity Units (CUs)
- Spark Notebooks and Pipelines consume CUs during execution
- Warehouse queries consume CUs during execution
- Semantic Model DirectLake queries consume CUs during query
- Eventstream ingestion consumes CUs continuously while active
