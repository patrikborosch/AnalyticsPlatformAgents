<!--
  AUTO-GENERATED FILE - DO NOT EDIT MANUALLY

  This file is regenerated from skills/*/SKILL.md frontmatter.
  Maintainers refresh it manually via:

    python .github/scripts/generate_skill_catalog.py

  Contributors do NOT regenerate in feature PRs (it produces diffs that
  conflict between concurrent skill PRs).
-->

# Skill Catalog

This catalog lists all available skills-for-fabric with their purpose and triggers.

> **This file is auto-generated.** Do not edit manually.
>
> Maintainers refresh by running `python .github/scripts/generate_skill_catalog.py` from the repo root.

## Overview

| Skill | Type | Purpose |
|-------|------|---------|
| [activator-authoring-cli](#activator-authoring-cli) | Authoring | Create alerts, notifications, and automated actions on Fabri... |
| [activator-consumption-cli](#activator-consumption-cli) | Consumption | Inspect existing alerts, notifications, and automated action... |
| [check-updates](#check-updates) | Utility | Check for skills-for-fabric marketplace updates at session s... |
| [databricks-migration](#databricks-migration) | General | Port Databricks notebooks and jobs to Microsoft Fabric. Prov... |
| [dataflows-authoring-cli](#dataflows-authoring-cli) | Authoring | Create, update, delete, and refresh Fabric Dataflows Gen2 vi... |
| [dataflows-consumption-cli](#dataflows-consumption-cli) | Consumption | Monitor, inspect, and query saved Fabric Dataflows Gen2 via ... |
| [dataflows-save-as-authoring-cli](#dataflows-save-as-authoring-cli) | Authoring | Assess, plan, and execute dataflow Gen1 → Gen2.1 CI/CD save-... |
| [e2e-medallion-architecture](#e2e-medallion-architecture) | End-to-End | Implement end-to-end Medallion Architecture (Bronze/Silver/G... |
| [eventhouse-authoring-cli](#eventhouse-authoring-cli) | Authoring | Execute KQL management commands (table management, ingestion... |
| [eventhouse-consumption-cli](#eventhouse-consumption-cli) | Consumption | Run KQL queries against Fabric Eventhouse for real-time inte... |
| [eventstream-authoring-cli](#eventstream-authoring-cli) | Authoring | Create, wire, and publish Microsoft Fabric Eventstream real-... |
| [eventstream-consumption-cli](#eventstream-consumption-cli) | Consumption | List, inspect, and monitor Microsoft Fabric Eventstream real... |
| [fabriciq](#fabriciq) | Consumption | Answer business questions by querying Power BI reports and d... |
| [hdinsight-migration](#hdinsight-migration) | Authoring | Port Azure HDInsight Spark clusters and Hive workloads to Mi... |
| [pipeline-migration](#pipeline-migration) | General | Migrate Synapse Data Factory pipeline artifacts to Microsoft... |
| [powerbi-report-authoring](#powerbi-report-authoring) | Authoring | Create and modify Power BI report files in PBIR/PBIP format ... |
| [powerbi-report-design](#powerbi-report-design) | Authoring | Generate Power BI report visual design guidance before PBIR ... |
| [powerbi-report-management](#powerbi-report-management) | Authoring | Manage Power BI report workspace items in Microsoft Fabric v... |
| [powerbi-report-planning](#powerbi-report-planning) | Authoring | Build a guided requirements-to-implementation workflow for n... |
| [search-consumption-cli](#search-consumption-cli) | Consumption | Find and discover Microsoft Fabric items across workspaces w... |
| [semantic-model-authoring](#semantic-model-authoring) | Authoring | Develops and manages Power BI semantic models across Desktop... |
| [semantic-model-consumption](#semantic-model-consumption) | Consumption | Execute raw DAX queries and inspect metadata of Microsoft Fa... |
| [spark-authoring-cli](#spark-authoring-cli) | Authoring | Develop Microsoft Fabric Spark/data engineering workflows an... |
| [spark-consumption-cli](#spark-consumption-cli) | Consumption | Analyze lakehouse data interactively using Fabric Lakehouse ... |
| [spark-operations-cli](#spark-operations-cli) | Operations | Diagnose failed Spark jobs, unhealthy Livy sessions, and per... |
| [sqldw-authoring-cli](#sqldw-authoring-cli) | Authoring | Execute authoring T-SQL (DDL, DML, data ingestion, transacti... |
| [sqldw-consumption-cli](#sqldw-consumption-cli) | Consumption | Execute read-only T-SQL queries against Fabric Data Warehous... |
| [sqldw-operations-cli](#sqldw-operations-cli) | Operations | Analyze Fabric Data Warehouse performance via CLI using sqlc... |
| [synapse-migration](#synapse-migration) | General | Port Azure Synapse Analytics Spark workloads to Microsoft Fa... |

---

## activator-authoring-cli

**Type:** Authoring

**Purpose:** Create alerts, notifications, and automated actions on Fabric data and events via Fabric REST API and `az rest` CLI. **Invoke this skill** whenever the user wants to: (1) create, update, or delete an alert or notification flow, (2) send a Teams message, email, or run a Fabric item when something happens, (3) connect alert logic to Eventhouse, Eventstream, Real-time Hub, or DTB / Ontology data, (4) adjust thresholds, filters, event triggers, or actions, (5) troubleshoot or change an existing Activator/Reflex definition. Invoke this skill **before** asking clarifying questions — clarification is part of this skill, not a preamble to it.

**Location:** `skills/activator-authoring-cli/`

---

## activator-consumption-cli

**Type:** Consumption

**Purpose:** Inspect existing alerts, notifications, and automated actions in Fabric via read-only REST API calls using `az rest` CLI. **Invoke this skill** whenever the user wants to: (1) list existing alerts in a workspace, (2) inspect how an alert or notification is configured, (3) read and decode an Activator/Reflex definition (ReflexEntities.json), (4) list rules, sources, and actions behind an alert, (5) understand why an alert fires or what action it takes. **Invoke this skill before answering questions** about an Activator/Reflex item in a Fabric workspace — the listing, lookup, and decoding workflows are part of this skill, not preamble to it.

**Location:** `skills/activator-consumption-cli/`

---

## check-updates

**Type:** Utility

**Purpose:** Check for skills-for-fabric marketplace updates at session start. Compares local version  against GitHub releases and shows changelog if updates are available.

**Location:** `skills/check-updates/`

---

## databricks-migration

**Type:** General

**Purpose:** Port Databricks notebooks and jobs to Microsoft Fabric. Provides an exhaustive dbutils to notebookutils substitution table: fs operations (mount removal via OneLake Shortcuts), secret scope to Key Vault URL conversion, notebook run and exit, widget replacement with parameter-tagged cells, and library install replacement with Fabric Environments. Covers Unity Catalog three-level namespace reduction to Lakehouse two-level schemas, DBFS path conversion to OneLake, Databricks Jobs to Spark Job Definitions, MLflow tracking URI removal, and Photon to Native Execution Engine substitution.

**Location:** `skills/databricks-migration/`

---

## dataflows-authoring-cli

**Type:** Authoring

**Purpose:** Create, update, delete, and refresh Fabric Dataflows Gen2 via write-side CLI against Fabric Items and Connections APIs. Builds mashup.pq + queryMetadata definitions, triggers parameterized refreshes, manages connections, and configures output destinations (Lakehouse, Warehouse, ADX, Azure SQL). Includes preview-driven authoring loop (executeQuery + customMashupDocument). Lists `supportedConnectionTypes`/`credentialType` per connector. For executing saved queries or reading refresh status, use `dataflows-consumption-cli`.

**Location:** `skills/dataflows-authoring-cli/`

---

## dataflows-consumption-cli

**Type:** Consumption

**Purpose:** Monitor, inspect, and query saved Fabric Dataflows Gen2 via read-only CLI. List dataflows, decode base64 definitions (mashup.pq, queryMetadata.json, .platform), discover parameters, retrieve refresh status and job history, classify queries by staging, and execute queries against saved dataflows via the read-side `executeQuery` mashup engine (Arrow IPC response). Runs persisted or ad-hoc read-only executeQuery requests; parses/renders Arrow results. For previewing candidate M before persisting, or for `supportedConnectionTypes`/`credentialType` discovery and connection configuration, use `dataflows-authoring-cli` (not this skill).

**Location:** `skills/dataflows-consumption-cli/`

---

## dataflows-save-as-authoring-cli

**Type:** Authoring

**Purpose:** Assess, plan, and execute dataflow Gen1 → Gen2.1 CI/CD save-as operations via CLI (az rest / curl) against Power BI REST and Fabric REST APIs. Scan workspaces or entire tenants for Gen1 dataflows, evaluate save-as readiness with seven risk signals (incremental refresh, BYOSA storage, Power Automate triggers, pipeline dependencies, linked entities, DirectQuery, caller-not-owner), produce a Save-As Readiness Snapshot (markdown + JSON), and invoke the SaveAsNativeArtifact API to create upgraded Gen2.1 copies of Gen1 dataflows. **Invoke this skill** whenever the user wants to: (1) discover Gen1 dataflows in a workspace or tenant, (2) assess save-as readiness and risk signals, (3) upgrade or migrate Gen1 into a Gen2.1 copy, (4) validate post-save-as data integrity, (5) detect residual Gen1 references.

**Location:** `skills/dataflows-save-as-authoring-cli/`

---

## e2e-medallion-architecture

**Type:** End-to-End

**Purpose:** Implement end-to-end Medallion Architecture (Bronze/Silver/Gold) lakehouse patterns in Microsoft Fabric using PySpark, Delta Lake, and Fabric Pipelines.

**Location:** `skills/e2e-medallion-architecture/`

---

## eventhouse-authoring-cli

**Type:** Authoring

**Purpose:** Execute KQL management commands (table management, ingestion, policies, functions, materialized views) against Fabric Eventhouse and KQL Databases via CLI.

**Location:** `skills/eventhouse-authoring-cli/`

---

## eventhouse-consumption-cli

**Type:** Consumption

**Purpose:** Run KQL queries against Fabric Eventhouse for real-time intelligence and time-series analytics using `az rest` against the Kusto REST API. Covers KQL operators (where, summarize, join, render), Eventhouse schema discovery (.show tables), time-series patterns with bin(), and ingestion monitoring.

**Location:** `skills/eventhouse-consumption-cli/`

---

## eventstream-authoring-cli

**Type:** Authoring

**Purpose:** Create, wire, and publish Microsoft Fabric Eventstream real-time event streaming topologies via the Fabric Items REST API. Build graph-based definitions with 25 source types (Event Hubs, IoT Hub, CDC connectors, Kafka, SampleData), 8 transformation operators (Filter, Aggregate, GroupBy, Join, ManageFields, Union, Expand, SQL), 4 destination types (Lakehouse Delta, Eventhouse, Activator, Custom Endpoint), and DefaultStream/DerivedStream routing.

**Location:** `skills/eventstream-authoring-cli/`

---

## eventstream-consumption-cli

**Type:** Consumption

**Purpose:** List, inspect, and monitor Microsoft Fabric Eventstream real-time event ingestion pipelines via the Fabric Items REST API. Discover Eventstreams across workspaces, decode base64-encoded graph topologies to trace event flow from source through operators to destination nodes. Validate source connection IDs, destination wiring, retention policies (1-90 days), and throughput levels.

**Location:** `skills/eventstream-consumption-cli/`

---

## fabriciq

**Type:** Consumption

**Purpose:** Answer business questions by querying Power BI reports and dashboards through the FabricIQ MCP endpoint. Orchestrates: discover Power BI artifacts, inspect report/model schemas, resolve entity values, generate DAX, execute queries. Returns plain-language answers from Power BI semantic models.

**Location:** `skills/fabriciq/`

---

## hdinsight-migration

**Type:** Authoring

**Purpose:** Port Azure HDInsight Spark clusters and Hive workloads to Microsoft Fabric. Removes legacy HiveContext and standalone SparkContext constructors, replacing them with the pre-instantiated SparkSession. Converts WASB and ABFS storage paths to OneLake abfss URLs via Shortcuts. Transforms Hive DDL (STORED AS ORC, external tables) to Delta Lake schemas inside Fabric Lakehouse. Maps Oozie workflow actions — spark, hive, shell, sqoop, coordinator — to Fabric Pipeline activities and schedule triggers. Introduces notebookutils for file and credential operations previously handled via subprocess or HDFS client calls.

**Location:** `skills/hdinsight-migration/`

---

## pipeline-migration

**Type:** General

**Purpose:** Migrate Synapse Data Factory pipeline artifacts to Microsoft Fabric Data Factory. Handles: linked services → Fabric connections, dataset definitions inlined into pipeline activities, global parameters → Variable Libraries, SynapseNotebook activities → TridentNotebook. SSIS, SHIR-only, and Databricks activities are parked.

**Location:** `skills/pipeline-migration/`

---

## powerbi-report-authoring

**Type:** Authoring

**Purpose:** Create and modify Power BI report files in PBIR/PBIP format using the `powerbi-report-author` and `powerbi-desktop` CLIs.

**Location:** `skills/powerbi-report-authoring/`

---

## powerbi-report-design

**Type:** Authoring

**Purpose:** Generate Power BI report visual design guidance before PBIR files are written.

**Location:** `skills/powerbi-report-design/`

---

## powerbi-report-management

**Type:** Authoring

**Purpose:** Manage Power BI report workspace items in Microsoft Fabric via `az rest` CLI against the Fabric REST API.

**Triggers:**
- "upload Power BI report"
- "download PBIR definition"
- "publish Power BI report to Fabric"
- "manage Power BI reports."

**Location:** `skills/powerbi-report-management/`

---

## powerbi-report-planning

**Type:** Authoring

**Purpose:** Build a guided requirements-to-implementation workflow for new Power BI reports and dashboards from semantic models, datasets, or PBIP projects.

**Location:** `skills/powerbi-report-planning/`

---

## search-consumption-cli

**Type:** Consumption

**Purpose:** Find and discover Microsoft Fabric items across workspaces when the workspace is unknown.

**Location:** `skills/search-consumption-cli/`

---

## semantic-model-authoring

**Type:** Authoring

**Purpose:** Develops and manages Power BI semantic models across Desktop, PBIP projects, and Fabric Service. Handles: (1) creating new models (Import, DirectQuery, Direct Lake), (2) editing existing models (e.g. measures, tables, columns, relationships), (3) deploying models to Fabric workspaces, (4) working with PBIP project files, (5) refreshing semantic models, (6) configuring data sources and permissions, (7) DAX performance optimization. Supports both Power BI Desktop and Fabric Service development workflows. For read-only DAX queries, use `semantic-model-consumption`. Does NOT handle report layout/visual authoring, workspace administration, or RLS/OLS role membership management.

**Location:** `skills/semantic-model-authoring/`

---

## semantic-model-consumption

**Type:** Consumption

**Purpose:** Execute raw DAX queries and inspect metadata of Microsoft Fabric Power BI semantic models via the MCP server ExecuteQuery tool.

**Location:** `skills/semantic-model-consumption/`

---

## spark-authoring-cli

**Type:** Authoring

**Purpose:** Develop Microsoft Fabric Spark/data engineering workflows and write code in Fabric Notebook cells with intelligent routing to specialized resources. Provides workspace/lakehouse management, notebook code authoring (PySpark, Scala, SparkR, SQL), and Materialized Lake View (MLV) authoring (Spark SQL MLVs support incremental refresh; PySpark is full-refresh only). Routes to data engineering patterns, development workflow, or infrastructure orchestration.

**Location:** `skills/spark-authoring-cli/`

---

## spark-consumption-cli

**Type:** Consumption

**Purpose:** Analyze lakehouse data interactively using Fabric Lakehouse Livy API sessions and PySpark/Spark SQL for advanced analytics, DataFrames, cross-lakehouse joins, Delta time-travel, and unstructured/JSON data.

**Location:** `skills/spark-consumption-cli/`

---

## spark-operations-cli

**Type:** Operations

**Purpose:** Diagnose failed Spark jobs, unhealthy Livy sessions, and performance bottlenecks in Microsoft Fabric via read-only CLI triage.

**Location:** `skills/spark-operations-cli/`

---

## sqldw-authoring-cli

**Type:** Authoring

**Purpose:** Execute authoring T-SQL (DDL, DML, data ingestion, transactions, schema changes) against Microsoft Fabric Data Warehouse and SQL endpoints from agentic CLI environments.

**Location:** `skills/sqldw-authoring-cli/`

---

## sqldw-consumption-cli

**Type:** Consumption

**Purpose:** Execute read-only T-SQL queries against Fabric Data Warehouse, Lakehouse SQL Endpoints, and Mirrored Databases via CLI. Default skill for any lakehouse data query (row counts, SELECT, filtering, aggregation) unless the user explicitly requests PySpark or Spark DataFrames.

**Location:** `skills/sqldw-consumption-cli/`

---

## sqldw-operations-cli

**Type:** Operations

**Purpose:** Analyze Fabric Data Warehouse performance via CLI using sqlcmd and queryinsights views. Diagnose slow queries, SQL pool pressure, cache coldness, and recommend clustering keys.

**Location:** `skills/sqldw-operations-cli/`

---

## synapse-migration

**Type:** General

**Purpose:** Port Azure Synapse Analytics Spark workloads to Microsoft Fabric. Translates mssparkutils calls to notebookutils (including the env→runtime namespace change), replaces Linked Services with Fabric Data Connections and OneLake Shortcuts. Covers Spark Pools, Lake Databases, Notebooks, and Spark Job Definitions.

**Location:** `skills/synapse-migration/`

---

## Skill Categories

### By Type

| Type | Skills |
|------|--------|
| Authoring | activator-authoring-cli, dataflows-authoring-cli, dataflows-save-as-authoring-cli, eventhouse-authoring-cli, eventstream-authoring-cli, hdinsight-migration, powerbi-report-authoring, powerbi-report-design, powerbi-report-management, powerbi-report-planning, semantic-model-authoring, spark-authoring-cli, sqldw-authoring-cli |
| Consumption | activator-consumption-cli, dataflows-consumption-cli, eventhouse-consumption-cli, eventstream-consumption-cli, fabriciq, search-consumption-cli, semantic-model-consumption, spark-consumption-cli, sqldw-consumption-cli |
| End-to-End | e2e-medallion-architecture |
| General | databricks-migration, pipeline-migration, synapse-migration |
| Operations | spark-operations-cli, sqldw-operations-cli |
| Utility | check-updates |

---

## Next Steps

- [Skill Authoring Guide](skill-authoring-guide.md) — Create a new skill
- [Architecture Overview](architecture-overview.md) — Understand the repo structure
