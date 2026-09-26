# Migration Orchestrator — Databricks → Fabric

Automated end-to-end migration workflow for porting Databricks workspaces to Microsoft Fabric.

> **Script pattern**: Sections show function signatures and key logic outlines. Generate the full runnable script on demand — this keeps the resource compact and reduces token load.

---

## Required Inputs

Collect these from the user before starting:

| Input | Example | How to Obtain |
|---|---|---|
| Databricks workspace URL | `https://adb-1234567890123456.12.azuredatabricks.net` | User provides |
| Databricks auth | Personal access token or OAuth | `databricks auth login` or user provides PAT |
| Fabric workspace name or ID | `Migration-Target` | User provides |
| Migration strategy | `lift-and-shift` or `migrate-and-modernize` | Ask user |

### Derived Values (Auto-Discovered)

| Value | Derived From |
|---|---|
| Databricks workspace ID | Parse from URL (`adb-{workspaceId}`) or `databricks workspace get-status /` |
| Fabric workspace ID | `GET /v1/workspaces` → filter by `displayName` |
| Databricks catalog/schema list | `databricks catalogs list` / `databricks schemas list <catalog>` |
| Notebook inventory | `databricks workspace list --recursive /` |
| Job inventory | `databricks jobs list --all` |

---

## Orchestration Flow

```
Phase 0: Inventory & Assessment
├── Enumerate notebooks, jobs, DLT pipelines, clusters, secrets, libraries
├── Classify each item by migration complexity (severity matrix)
└── Generate migration manifest with namespace mapping

Phase 1: Environment Setup
├── Create Fabric Lakehouse(s) — one schema-enabled Lakehouse per Unity Catalog catalog
├── Create Fabric Environment(s) — map cluster libraries
└── Create OneLake Shortcuts for external data (ADLS, S3)

Phase 2: Notebook Migration
├── Export notebooks from Databricks workspace
├── Apply code transforms (dbutils→notebookutils, namespace, paths)
├── Deploy to Fabric workspace via REST API
└── Per-notebook validation checkpoint

Phase 3: Job & Orchestration Migration
├── Map single-task Jobs → Spark Job Definitions
├── Map multi-task Jobs → Fabric Data Pipelines
├── Map DLT Pipelines → Notebook + Pipeline combinations
└── Schedule trigger migration

Phase 4: Validation & Cutover
├── Execute migrated notebooks (dry run)
├── Compare outputs where applicable
├── Generate migration report
└── Flag any unresolved blockers
```

---

## Phase 0: Inventory & Assessment

### Step 0.1: Enumerate All Workspace Items

Use Databricks CLI to build a complete inventory:

```
databricks workspace list / --recursive --output json
databricks jobs list --all --output json
databricks clusters list --output json
databricks pipelines list-pipelines --output json
databricks secrets list-scopes --output json
```

For Unity Catalog assets:

```
# Requires Databricks CLI v0.205 or newer. The legacy `databricks unity-catalog ...`
# command group has been removed; use the catalogs/schemas/tables commands below.
databricks catalogs list --output json
databricks schemas list <catalog> --output json
databricks tables list <catalog> <schema> --output json
```

### Step 0.2: Classify Items by Migration Severity

Apply severity to each item based on its migration complexity:

| Severity | Criteria | Action |
|---|---|---|
| **Blocker** | Cannot run in Fabric without redesign or user decision | Stop — surface to user |
| **Warning** | Migratable but requires validation/performance review | Migrate with review flag |
| **Info** | Direct substitution-level change (e.g., `dbutils.fs.ls` → `notebookutils.fs.ls`) | Auto-migrate |

#### Blocker Patterns

| Pattern Detected | Why It Blocks | Resolution |
|---|---|---|
| Delta Live Tables (DLT) pipeline | No DLT equivalent in Fabric | Rewrite as parameterized notebooks + Pipeline orchestration |
| `dbutils.widgets.*` (interactive widgets) | No direct equivalent | Redesign as parameters cells + `notebookutils.notebook.run(name, arguments={})` |
| Unity Catalog namespace collision (**only** under user-elected multi-catalog consolidation) | Two different `catalog.schema.table` paths would collapse to the same `schema.table` in one Lakehouse | **User must supply mapping policy** — do not auto-resolve. Default one-Lakehouse-per-catalog mapping has no collision |
| JDBC/native dependencies installed by `init_scripts` at the OS level | Fabric Environments support Maven and custom JAR libraries, but not arbitrary OS packages, daemon setup, or native system configuration | Move supported JAR/Maven dependencies into the Environment; redesign only the unsupported OS/native setup |
| Databricks-specific Spark configs (`spark.databricks.*`) | Proprietary — ignored or errors in Fabric | Remove; substitute Fabric equivalents where they exist |

#### Warning Patterns

| Pattern Detected | Why It Warns | Resolution |
|---|---|---|
| Scala notebooks (`%scala`) | Fabric supports Spark/Scala, but Databricks-specific APIs and libraries may differ, and cell magics change (`%scala` → `%%spark`) | Validate runtime/library compatibility; rewrite Databricks-specific APIs and swap cell magics |
| R notebooks (`%r`) | Fabric supports SparkR, but package availability may differ, and cell magics change (`%r` → `%%sparkr`) | Validate packages via Fabric Environment; rewrite Databricks-specific APIs and swap cell magics |
| `%pip install` without version pins | May install incompatible versions on Fabric Runtime | Pin versions in Fabric Environment |
| `dbutils.fs.mount(...)` usage | Fabric supports `notebookutils.fs.mount()` but prefers Shortcuts for persistence | Migrate to `notebookutils.fs.mount()` + recommend Shortcut |
| Photon-optimized queries | NEE covers most cases but not all Photon behaviors | Test with NEE enabled; benchmark |
| MLflow `set_tracking_uri("databricks")` | Must remove for Fabric | Auto-remove (Info if standalone) |
| Cluster autoscale with 20+ workers | Fabric Custom Pools may have different capacity limits | Verify Fabric capacity SKU supports equivalent scale |

#### Info Patterns (Auto-Migratable)

| Pattern Detected | Transformation |
|---|---|
| `dbutils.fs.ls/cp/rm/mkdirs/put/head` | → `notebookutils.fs.ls/cp/rm/mkdirs/put/head` |
| `dbutils.notebook.run(path, timeout)` | → `notebookutils.notebook.run(name, timeout)` |
| `dbutils.notebook.exit(value)` | → `notebookutils.notebook.exit(value)` |
| `dbutils.secrets.get(scope, key)` | → `notebookutils.credentials.getSecret(kvUrl, secretName)` |
| `spark.read.table("catalog.schema.table")` | → `spark.read.table("schema.table")` (with Lakehouse context) |
| `SparkSession.builder.getOrCreate()` | Remove — `spark` is pre-instantiated in Fabric |

### Step 0.3: Namespace Mapping

Unity Catalog uses 3-level naming (`catalog.schema.table`). A **schema-enabled** Fabric Lakehouse preserves both lower levels (`schema.table`), and the Lakehouse itself stands in for the catalog — yielding the full `workspace.lakehouse.schema.table` path. There is **no inherent level collapse**.

**Default mapping (no collision):** create **one schema-enabled Lakehouse per Databricks catalog**. Schemas and table names are preserved verbatim. This is the recommended structure and requires no renaming.

**Optional consolidation (collision risk):** collisions only become possible if the user explicitly elects to consolidate multiple catalogs into a *single* Lakehouse — then two `catalog.schema.table` paths can map to the same `schema.table`.

**Collision detection (consolidation path only):**

```
For each (catalog, schema, table) triple targeted at the SAME Lakehouse:
  target_key = f"{schema}.{table}"
  If target_key already seen from a DIFFERENT catalog:
    → Mark as COLLISION (Blocker)
    → Record: both source catalog paths map to same Fabric target
```

**Resolution strategies (only when consolidating):**

| Strategy | When to Use |
|---|---|
| **One schema-enabled Lakehouse per catalog** (default) | Clean isolation — schemas and table names preserved, no collision |
| **Prefix schema with catalog name** | Consolidating catalogs with overlapping schema names → `prod_silver.customers`, `dev_silver.customers` |
| **Drop non-production catalogs** | Only migrate `prod` catalog; skip `dev`/`staging` |

> ⚠️ **Never auto-resolve namespace collisions.** When the user elects consolidation, surface collisions with the available strategies and let them decide. Silent resolution risks incorrect data bindings.

### Step 0.4: Generate Migration Manifest

Output a structured manifest summarizing the assessment:

```
migration_manifest:
  workspace: <databricks_workspace_url>
  target_fabric_workspace: <fabric_workspace_id>
  strategy: lift-and-shift | migrate-and-modernize
  
  items:
    - path: /Users/alice/ETL/bronze_ingest
      type: notebook
      language: python
      severity: Info
      transforms: [dbutils_fs, namespace_map]
      target: notebooks/bronze_ingest
      
    - path: /Users/alice/ETL/silver_transform  
      type: notebook
      language: python
      severity: Warning
      transforms: [dbutils_fs, dbutils_widgets, namespace_map]
      blockers: []
      warnings: [widgets_require_parameters_cell]
      target: notebooks/silver_transform

  collisions:
    - target_key: silver.customers
      sources: [prod.silver.customers, staging.silver.customers]
      resolution: PENDING_USER_INPUT

  blockers_summary:
    total: 2
    items: [/Shared/DLT/pipeline_config, /Shared/cluster-init/install-drivers.sh]
    
  stats:
    total_items: 47
    auto_migratable: 38
    warnings: 7
    blockers: 2
```

---

## Phase 1: Environment Setup

### Step 1.1: Create Fabric Lakehouses

Create one **schema-enabled** Lakehouse per Databricks catalog (default), or per the user's consolidation choice. Use the dedicated Lakehouse endpoint with `enableSchemas: true` — the generic `/items` endpoint creates a **schema-less** Lakehouse that cannot preserve Unity Catalog schemas:

```
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/lakehouses
{
  "displayName": "{lakehouse_name}",
  "description": "Schema-enabled target Lakehouse for Databricks migration",
  "creationPayload": {
    "enableSchemas": true
  }
}
```

Poll for creation completion via Long-Running Operation (LRO) pattern.

### Step 1.2: Create Fabric Environments

Map Databricks cluster libraries to Fabric Environment specifications:

| Databricks Source | Fabric Environment Target |
|---|---|
| `%pip install` lines in notebooks | `Libraries/PublicLibraries/environment.yml` (PyPI / conda dependencies); compute settings live in `Setting/Sparkcompute.yml` |
| Cluster library list (PyPI) | Fabric Environment PyPI libraries |
| `init_scripts` with `pip install` | Fabric Environment PyPI libraries |
| Maven/JAR libraries | ✅ Supported — upload custom `.jar` files or add Maven coordinates (POM) to the Fabric Environment; validate runtime compatibility |
| Custom wheel files | Upload to Environment as custom library |

> **Only** cluster **init scripts that install OS-level/system packages** remain a hard blocker (Fabric Environments support PyPI, conda, custom `.jar`/wheel, and Maven — not arbitrary system installs).

### Step 1.3: Create OneLake Shortcuts

For external data currently accessed via DBFS mounts or external locations:

| Databricks Pattern | Fabric Shortcut Target |
|---|---|
| `dbutils.fs.mount("wasbs://container@account.blob.core.windows.net/")` | OneLake Shortcut → ADLS Gen2 |
| External location pointing to S3 | OneLake Shortcut → Amazon S3 |
| External location pointing to ADLS | OneLake Shortcut → ADLS Gen2 |

---

## Phase 2: Notebook Migration

### Step 2.1: Multi-Notebook Protocol

For workspaces with >3 notebooks or individual notebooks >5KB:

1. **Enumerate** — List all notebooks with path, language, and approximate size. Do not read full bodies yet.
2. **Process one-at-a-time** — For each notebook:
   a. Export full source from Databricks (`databricks workspace export <path> --format SOURCE --file <local-path>` — without `--file` the source is written to stdout)
   b. Apply code transforms (see severity matrix above)
   c. Record structured summary:
      - `notebook_path` (relative)
      - `detected_patterns[]` (pattern IDs)
      - `severity` (max severity across all patterns)
      - `transforms_applied[]`
      - `unresolved_blockers[]`
   d. Deploy to Fabric workspace
3. **Synthesize** — After all notebooks processed, produce unified migration report from summaries.

### Step 2.2: Code Transformation Pipeline

Apply transforms in this order (order matters for correctness):

1. Remove `SparkSession.builder.getOrCreate()` — `spark` is pre-instantiated
2. Replace `dbutils.*` calls → `notebookutils.*` (see [dbutils-to-notebookutils.md](dbutils-to-notebookutils.md))
3. Map 3-level namespace → schema-enabled Lakehouse `schema.table` (default one Lakehouse per catalog; apply prefixing only under user-elected consolidation)
4. Replace DBFS/mount paths with OneLake-relative paths (`Files/...` or `Tables/...`)
5. Replace `dbutils.widgets` with parameters cells + `notebookutils.notebook.run(name, arguments={})`
6. Remove `mlflow.set_tracking_uri("databricks")` lines
7. Remove/adjust proprietary Spark configs (`spark.databricks.*`)
8. Flag remaining blockers (DLT, custom JVM/JDBC data sources, OS-level init scripts)

### Step 2.3: Deploy Notebooks to Fabric

```
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/items
{
  "displayName": "{notebook_name}",
  "type": "Notebook",
  "definition": {
    "format": "ipynb",
    "parts": [
      {
        "path": "notebook-content.ipynb",
        "payload": "<base64-encoded-notebook-content>",
        "payloadType": "InlineBase64"
      }
    ]
  }
}
```

---

## Phase 3: Job & Orchestration Migration

### Single-Task Jobs → Spark Job Definitions

```
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/items
{
  "displayName": "{job_name}",
  "type": "SparkJobDefinition"
}
```

> **Note:** The `POST /items` call above creates an **empty** SJD shell. It has no executable definition until you follow up with `POST .../items/{sjdId}/updateDefinition`, supplying a base64-encoded `SparkJobDefinitionV1.json` part that references the migrated notebook/main file and default Lakehouse. Alternatively, include the `definition` inline on the initial create (as shown for notebooks in Step 2.3).

Then update the definition to reference the migrated notebook and default Lakehouse.

### Multi-Task Jobs → Fabric Data Pipelines

Map the Databricks job DAG to Pipeline activities:

| Databricks Task Type | Fabric Pipeline Activity |
|---|---|
| `notebook_task` | Notebook activity |
| `spark_python_task` | Notebook activity (wrap .py as notebook) |
| `sql_task` | Stored Procedure activity or Script activity |
| `dbt_task` | ⚠️ No direct equivalent — use Notebook activity with dbt-fabric |
| `pipeline_task` (DLT) | **Blocker** — rewrite as chained Notebook activities |

### Schedule Migration

| Databricks Schedule | Fabric Equivalent |
|---|---|
| Cron trigger (`quartz_cron_expression`) | Pipeline schedule trigger (recurrence) |
| File arrival trigger | Pipeline event-based trigger (storage events) |
| Continuous trigger | Pipeline tumbling window or scheduled recurrence |

---

## Phase 4: Validation & Cutover

See [validation-testing.md](validation-testing.md) for full validation workflow.

### Quick Validation Checklist

| Check | Method | Gate |
|---|---|---|
| Environments published | `GET /v1/workspaces/{id}/environments/{envId}` → status = "Success" | Phase 1 gate |
| Notebooks deploy without error | LRO completes with 200 | Phase 2 gate |
| Critical notebooks execute | Run via Fabric REST API → check cell outputs | Phase 3 gate |
| Data row counts match | Compare Databricks `spark.table(...).count()` vs Fabric equivalent | Cutover gate |
| No unresolved blockers | All Blocker items either resolved or explicitly excluded | Cutover gate |

---

## Failure Reporting

When the migration cannot complete (Blockers with no workaround, permissions failures, or repeated errors), generate a structured failure report:

```
failure_report:
  workspace: <source_url>
  target: <fabric_workspace>
  phase_reached: <0|1|2|3|4>
  
  blockers:
    - item: /Shared/DLT/pipeline_config
      pattern: delta_live_tables
      severity: Blocker
      reason: "No DLT equivalent in Fabric"
      recommendation: "Rewrite as parameterized notebooks + Pipeline orchestration"
      
    - item: /Shared/cluster-init/install-drivers.sh
      pattern: init_script_system_package
      severity: Blocker
      reason: "Init script installs OS-level packages; Fabric Environments support only PyPI/conda, custom .jar/wheel, and Maven"
      recommendation: "Use a pure-Python alternative, or move the workload to a containerized/Azure ML approach"
  
  partial_success:
    migrated: 38
    skipped: 2
    failed: 0
    
  next_steps:
    - "Resolve 2 blockers manually (DLT rewrite + init-script dependency)"
    - "Exclude the two blocked items from the approved migration batch, then rerun the remaining phases"
```

### Stopping Conditions

Do not attempt workarounds — surface to user and stop:

- Permission failures on Databricks workspace or Fabric workspace
- Blocker patterns with no known resolution (DLT rewrite required, custom Spark data sources requiring JVM access, OS-level init-script dependencies)
- Namespace collisions without user-provided resolution strategy
- Repeated API failures (5+ retries with no progress)
- Items that exceed Fabric REST API size limits (10MB notebook upload limit)
