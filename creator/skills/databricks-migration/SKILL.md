---
name: databricks-migration
description: "Ports existing Databricks notebooks and jobs to Fabric, covering dbutils to notebookutils, secret scopes to Key Vault, DBFS to OneLake, Unity Catalog mapping to schema-enabled Lakehouses, Jobs and Delta Live Tables to Spark Job Definitions and Pipelines, and Photon to the Native Execution Engine. Use whenever Databricks code has to be converted. For Fabric notebook code that is not being migrated, use spark-cli."
---

> **Telemetry — MANDATORY.** Every `api.fabric.microsoft.com` call must carry
> `x-ms-fabric-skill: databricks-migration` (`az rest`: `--headers "x-ms-fabric-skill=databricks-migration"`),
> including every LRO poll, `fabric_lro` and retry. Snippets omit it — add it anyway.

> **CRITICAL NOTES**
> 1. To find workspace details (including its ID) from a workspace name: list all workspaces, then use JMESPath filtering
> 2. To find item details (including its ID) from workspace ID, item type, and item name: list all items of that type in that workspace, then use JMESPath filtering
> 3. `dbutils.widgets` has **no direct equivalent** in Fabric — use notebook parameters (cell tag `parameters`); `notebookutils.runtime.context` is execution metadata, not parameter storage. If showing context fields, use documented names such as `currentWorkspaceId`, `currentWorkspaceName`, `currentNotebookId`, `currentNotebookName`, `isForPipeline`, and `isForInteractive`; `activityId` is the Livy job ID
> 4. `dbutils.library` (runtime library install) has **no equivalent** — use Fabric Environments for reproducible library management
> 5. Map each Unity Catalog catalog to a schema-enabled Lakehouse by default. This preserves the source `schema.table` hierarchy, with the Lakehouse representing the catalog; collisions arise only if multiple catalogs are intentionally consolidated into one Lakehouse
> 6. For an under-specified workspace-wide migration, ask focused questions about inventory, workload topology, security, data locations, and runtime constraints before recommending a Fabric topology
> 7. A completed Fabric migration must not retain executable `dbutils.*` calls in dual-runtime branches or `try/except` guards — replace the calls and Databricks paths outright

# Databricks → Microsoft Fabric Migration

## Prerequisite Knowledge

Read these companion documents before executing migration tasks:

- [COMMON-CORE.md](../../common/COMMON-CORE.md) — Fabric REST API patterns, authentication, token audiences, item discovery
- [COMMON-CLI.md](../../common/COMMON-CLI.md) — `az rest`, `az login`, token acquisition, Fabric REST via CLI
- [SPARK-AUTHORING-CORE.md](../../common/SPARK-AUTHORING-CORE.md) — Notebook deployment, lakehouse creation, Spark job execution

For notebook and Lakehouse creation, see [spark-cli](../spark-cli/SKILL.md).
For Fabric Warehouse DDL/DML authoring, see [sqldw-cli](../sqldw-cli/SKILL.md).

---

## Table of Contents

| Topic | Reference |
|---|---|
| **Migration Orchestrator** | [migration-orchestrator.md](resources/migration-orchestrator.md) |
| Migration Workload Map | [§ Migration Workload Map](#migration-workload-map) |
| Complete `dbutils` → `notebookutils` Mapping | [dbutils-to-notebookutils.md](resources/dbutils-to-notebookutils.md) |
| Unity Catalog → Fabric Lakehouse Schemas | [catalog-migration.md](resources/catalog-migration.md) |
| Before/After Code Patterns | [code-patterns.md](resources/code-patterns.md) |
| Cluster Config → Fabric Spark Pools | [§ Cluster Config → Fabric Spark Pools](#cluster-config--fabric-spark-pools) |
| Databricks Jobs → Spark Job Definitions | [§ Databricks Jobs → Spark Job Definitions](#databricks-jobs--spark-job-definitions) |
| Delta Sharing → Fabric External Data Sharing and OneLake Shortcuts | [§ Delta Sharing → Fabric External Data Sharing and OneLake Shortcuts](#delta-sharing--fabric-external-data-sharing-and-onelake-shortcuts) |
| MLflow → Fabric ML Experiments | [§ MLflow → Fabric ML Experiments](#mlflow--fabric-ml-experiments) |
| Post-Migration Validation & Testing | [validation-testing.md](resources/validation-testing.md) |
| Migration Gotchas & Troubleshooting | [migration-gotchas.md](resources/migration-gotchas.md) |
| Multi-Notebook Migration Protocol | [§ Multi-Notebook Migration Protocol](#multi-notebook-migration-protocol) |
| Failure Reporting | [§ Failure Reporting](#failure-reporting) |
| Must / Prefer / Avoid | [§ Must / Prefer / Avoid](#must--prefer--avoid) |
| Authentication & Token Acquisition | [COMMON-CORE.md § Authentication](../../common/COMMON-CORE.md#authentication--token-acquisition) |
| Lakehouse Management | [SPARK-AUTHORING-CORE.md § Lakehouse Management](../../common/SPARK-AUTHORING-CORE.md#lakehouse-management) |
| Notebook Management | [SPARK-AUTHORING-CORE.md § Notebook Management](../../common/SPARK-AUTHORING-CORE.md#notebook-management) |

### Context Loading Guide

> **IMPORTANT — Load only what you need.** Do NOT read all resource files upfront. Load the specific file for the phase you are executing:

| When | Read This File |
|---|---|
| User asks to migrate a workspace (full orchestration) | [migration-orchestrator.md](resources/migration-orchestrator.md) |
| Applying code transforms (dbutils, namespaces, paths) | [dbutils-to-notebookutils.md](resources/dbutils-to-notebookutils.md) + [code-patterns.md](resources/code-patterns.md) |
| Resolving Unity Catalog namespace collisions | [catalog-migration.md](resources/catalog-migration.md) |
| Post-migration verification | [validation-testing.md](resources/validation-testing.md) |
| Troubleshooting failures or known issues | [migration-gotchas.md](resources/migration-gotchas.md) |

---

## Migration Workload Map

| Databricks Component | Fabric Target | Severity | Notes |
|---|---|---|---|
| **All-purpose cluster** (notebooks, REPL) | Fabric Notebook (Starter Pool or Custom Pool) | Info | No persistent cluster — Fabric provisions compute on session start |
| **Job cluster** (automated jobs) | **Spark Job Definition (SJD)** | Info | SJD maps one-to-one with Databricks Jobs on job clusters |
| **Unity Catalog** | **Fabric Lakehouse** (schema-enabled, one per catalog) | Info | Schema-enabled Lakehouse preserves `schema.table`; default one-Lakehouse-per-catalog has no collision — see [catalog-migration.md](resources/catalog-migration.md) |
| **Databricks Repos** (Git-backed notebooks) | **Fabric Git Integration** | Info | Connect workspace to Azure DevOps or GitHub; notebooks are synced |
| **Delta Live Tables (DLT)** | **Fabric Notebooks** + **Data Pipelines** | Blocker | No DLT equivalent — rewrite DLT datasets as parameterized notebook cells with pipeline orchestration |
| **Databricks SQL Warehouses** | **Fabric Warehouse** or **Lakehouse SQL Endpoint** | Info | SQL warehouse sessions → Warehouse (for write) or SQL Endpoint (for read-only) |
| **MLflow Tracking** | **Fabric ML Experiments** | Info | MLflow SDK is supported in Fabric — see [§ MLflow](#mlflow--fabric-ml-experiments) |
| **Delta Sharing** | **OneLake Shortcuts** + **Fabric external data sharing** | Warning | See [§ Delta Sharing → Fabric External Data Sharing and OneLake Shortcuts](#delta-sharing--fabric-external-data-sharing-and-onelake-shortcuts) |
| **Databricks Feature Store** | **Feature engineering on Lakehouse/Delta tables** + MLflow | Warning | Fabric has no drop-in managed Feature Store; recreate feature tables as Delta tables in a Lakehouse and manage features via notebooks/MLflow. Verify current Fabric feature-store roadmap before committing an approach |
| **dbutils** (all sub-modules) | **`notebookutils`** (most sub-modules) | Info | See [dbutils-to-notebookutils.md](resources/dbutils-to-notebookutils.md) for full mapping |
| **Scala notebooks** | Fabric Notebook (Spark/Scala) | Warning | Scala is supported; swap cell magic `%scala` → `%%spark` and rewrite Databricks-specific APIs/libraries |
| **R notebooks** | Fabric Notebook (SparkR) | Warning | SparkR is supported; swap cell magic `%r` → `%%sparkr`, validate package availability, rewrite Databricks-specific APIs |

### Severity Definitions

| Level | Meaning | Action |
|---|---|---|
| **Blocker** | Cannot run in Fabric without redesign or user decision | Stop — surface to user, require resolution |
| **Warning** | Migratable but requires validation or architectural decision | Migrate with review flag |
| **Info** | Direct substitution-level change | Auto-migrate |

---

## `dbutils` → `notebookutils` Quick Reference

The complete side-by-side API table is in [dbutils-to-notebookutils.md](resources/dbutils-to-notebookutils.md). The key mappings are:

| `dbutils` Call | `notebookutils` Equivalent | Compatibility Note |
|---|---|---|
| `dbutils.fs.ls(path)` | `notebookutils.fs.ls(path)` | **Direct replacement** |
| `dbutils.fs.cp(src, dest)` | `notebookutils.fs.cp(src, dest)` | **Direct replacement** |
| `dbutils.fs.mv(src, dest)` | `notebookutils.fs.mv(src, dest, create_path, overwrite=False)` | ⚠️ Signature differs — see [dbutils-to-notebookutils.md](resources/dbutils-to-notebookutils.md) |
| `dbutils.fs.rm(path, recurse)` | `notebookutils.fs.rm(path, recurse)` | **Direct replacement** |
| `dbutils.fs.mkdirs(path)` | `notebookutils.fs.mkdirs(path)` | **Direct replacement** |
| `dbutils.fs.put(path, contents)` | `notebookutils.fs.put(path, contents)` | **Direct replacement** |
| `dbutils.fs.head(path, maxBytes)` | `notebookutils.fs.head(path, max_bytes)` | ⚠️ Default differs — Python/Scala 100 KB, R 64 KB. See [dbutils-to-notebookutils.md](resources/dbutils-to-notebookutils.md) |
| `dbutils.fs.mount(...)` | `notebookutils.fs.mount(source, mountPoint, extraConfigs=None)` | ✅ **Supported** — Microsoft Entra (default), `accountKey`, or `sasToken` auth. For cross-workspace / persistent sharing, prefer **OneLake Shortcuts** |
| `dbutils.secrets.get(scope, key)` | `notebookutils.credentials.getSecret(keyVaultUrl, secretName)` | Scope → Key Vault URL; key → secret name |
| `dbutils.notebook.run(path, timeout, args)` | `notebookutils.notebook.run(name, timeout, args)` | `path` → notebook `name` (relative to workspace) |
| `dbutils.notebook.exit(value)` | `notebookutils.notebook.exit(value)` | **Direct replacement** |
| `dbutils.widgets.get(name)` | See [§ Widgets Migration](#widgets-migration) | No direct equivalent |
| `dbutils.library.install(...)` | **Not available at runtime** — use **Fabric Environments** | `dbutils.library.restartPython()` → `notebookutils.session.restartPython()` |
| `dbutils.data.summarize(df)` | `display(df.summary())` | Use `display()` or pandas `describe()` |

### Widgets Migration

`dbutils.widgets` has no direct equivalent in Fabric. Use these patterns instead:

| Use Case | Fabric Pattern |
|---|---|
| Pass parameter from parent notebook | Mark a cell in the child notebook as a **parameters cell** (notebook UI: cell "..." menu → "Mark cell as parameters"). The parent calls `notebookutils.notebook.run("child", arguments={"param": "value"})` — at runtime the engine inserts a new cell beneath the parameters cell that overrides the defaults |
| Pipeline-driven parameterization | Same parameters-cell mechanism; the Fabric Pipeline notebook activity supplies override values via its **Base parameters** setting |
| Centralized cross-notebook config | Use `notebookutils.variableLibrary.getLibrary("<name>")` to read values from a Variable Library item (deployment pipelines activate the right value set per stage) |
| Interactive selection in notebook | Use `display()` with input cells, IPython widgets (Python only), or Fabric Data Activator |

> Note: `notebookutils.runtime.context` does **not** expose parameter values. It's for execution metadata (workspace/notebook/activity/user IDs, pipeline-vs-interactive flags, etc.). See [dbutils-to-notebookutils.md § Runtime Context](resources/dbutils-to-notebookutils.md#runtime-context).

---

## Cluster Config → Fabric Spark Pools

| Databricks Cluster Concept | Fabric Spark Equivalent | Notes |
|---|---|---|
| All-purpose cluster (interactive) | **Starter Pool** | Auto-provisioned; no config; ideal for notebooks |
| Job cluster (single-use for jobs) | **Custom Pool** (or Starter Pool) attached to SJD | Configure node size, autoscale in Fabric capacity settings |
| Node type (e.g., `Standard_DS3_v2`) | **Fabric node size** (Small/Medium/Large/X-Large/XX-Large) | Map by vCore/memory ratio |
| Autoscale min/max workers | Custom Pool **min/max node** settings | Available in workspace Spark settings |
| `spark.conf` in cluster settings | **Fabric Environment** Spark properties | Move to Environment item; attach to workspace or notebook |
| `init_scripts` (cluster init) | **Fabric Environment** install script | Not fully equivalent — only library installs are supported |
| Databricks Runtime version | **Fabric Runtime** (1.1 = Spark 3.3, 1.2 = Spark 3.4, 1.3 = Spark 3.5) | Choose matching Spark version; test deprecated APIs |
| Photon accelerator | **Fabric Native Execution Engine (NEE)** | Enable in workspace Spark settings; vectorized execution similar to Photon |

---

## Databricks Jobs → Spark Job Definitions

| Databricks Jobs Concept | Fabric SJD Equivalent | Notes |
|---|---|---|
| Job with single notebook task | **SJD** referencing a notebook | Attach a default Lakehouse; pass parameters via SJD args |
| Multi-task job (DAG of tasks) | **Fabric Data Pipeline** orchestrating multiple SJDs/notebooks | Pipeline activities map to job tasks; dependencies = activity dependencies |
| Job schedule (cron) | **Pipeline schedule trigger** | Cron expression → recurrence trigger in pipeline |
| Job parameters | **SJD default arguments** or **notebook cell parameters** | Parameters cell in notebook is injected at runtime |
| Job clusters per task | **Pool attached to SJD** | Each SJD can specify its Spark pool independently |
| Databricks Workflows | **Fabric Data Pipelines** | Full DAG orchestration with conditions, loops, and failure branches |

> **Delegate to `spark-cli`** for SJD creation and notebook deployment.

---

## Delta Sharing → Fabric External Data Sharing and OneLake Shortcuts

| Databricks Delta Sharing Pattern | Fabric Equivalent |
|---|---|
| Provider publishes a Delta share | Fabric **external data sharing** for cross-tenant Fabric data, or a OneLake Shortcut to ADLS Gen2 where the Delta data resides |
| Recipient reads shared data | Accept the external data share into a Lakehouse (Fabric creates a read-only OneLake Shortcut), or create a direct **OneLake Shortcut** to accessible ADLS Gen2 data |
| Cross-workspace table sharing within org | **OneLake Shortcuts** pointing to another workspace's Lakehouse tables — no data copy |
| Cross-tenant sharing | Fabric **external data sharing** — live, read-only, in-place access through a shortcut in the recipient tenant |

When producing a migration workload map, include both paths: direct OneLake Shortcuts for accessible ADLS or same-tenant OneLake data, and Fabric external data sharing for native cross-tenant recipient sharing.

---

## MLflow → Fabric ML Experiments

Fabric ML Experiments are built on the MLflow SDK — most code is directly portable:

| Databricks MLflow Pattern | Fabric Equivalent | Migration Action |
|---|---|---|
| `mlflow.set_tracking_uri("databricks")` | Remove — Fabric tracking is automatic | Delete this line in Fabric notebooks |
| `mlflow.set_experiment("/path/exp")` | `mlflow.set_experiment("experiment_name")` | Use name only (not path); Fabric creates the Experiment item |
| `mlflow.log_metric(...)` | `mlflow.log_metric(...)` — **identical** | No change |
| `mlflow.log_artifact(...)` | `mlflow.log_artifact(...)` — **identical** | No change |
| `mlflow.autolog()` | `mlflow.autolog()` — **identical** | No change |
| `mlflow.register_model(...)` | `mlflow.register_model(...)` — **identical** | Model Registry is available in Fabric ML |
| Databricks Model Serving | **Azure ML Online Endpoints** or **Fabric Data Activator** | No direct Fabric model serving yet — use Azure ML |

---

## Must / Prefer / Avoid

### MUST DO
- **Inventory before prescribing a workspace topology** — for workspace-wide requests that omit workload inventory, dependencies, security requirements, data locations, or runtime constraints, ask focused clarifying questions and present conditional choices before selecting a Fabric design
- **Replace all `dbutils.*` calls** using the mapping in [dbutils-to-notebookutils.md](resources/dbutils-to-notebookutils.md) — `dbutils` is not available in Fabric notebooks
- **Migrate `dbutils.fs.mount()` to `notebookutils.fs.mount()`** (✅ supported — Microsoft Entra default, or `accountKey` / `sasToken` from Key Vault). For cross-workspace or persistent sharing, prefer **OneLake Shortcuts** instead. Always pair `mount()` with `unmount()` in `try/finally` — Fabric mounts are not released automatically on session end
- **Replace `dbutils.secrets.get(scope, key)`** with `notebookutils.credentials.getSecret(keyVaultUrl, secretName)` — secret scopes map to Azure Key Vault URLs
- **Redesign widget-based parameter passing** using notebook **parameters cells** (cell "..." menu → "Mark cell as parameters"); use `notebookutils.variableLibrary` for centralized cross-notebook config. `notebookutils.runtime.context` does **not** expose parameter values
- **Replace `dbutils.library.install*()`** with Fabric **Environments** — runtime library installs are not supported in production. `dbutils.library.restartPython()` maps to `notebookutils.session.restartPython()` (Python / PySpark only)
- **Map Unity Catalog namespaces deliberately** — default to one schema-enabled Lakehouse per catalog so `schema.table` is preserved; require a user-approved naming policy only when consolidating multiple catalogs into one Lakehouse. See [catalog-migration.md](resources/catalog-migration.md)
- **Map Databricks cluster init scripts** to Fabric Environments — cluster-level library installs must move to Environment items

### PREFER
- **Fabric Native Execution Engine (NEE)** as the Photon equivalent — enable in workspace Spark settings for vectorized execution on Delta Lake
- **OneLake Shortcuts** over data copy for Delta tables that already exist in ADLS Gen2 — point directly without re-ingesting
- **Fabric Git Integration** as the replacement for Databricks Repos — connect workspace to ADO or GitHub for notebook version control
- **Fabric ML Experiments** for direct MLflow continuity — tracking code requires minimal changes (remove `set_tracking_uri`)
- **Medallion architecture** when restructuring migrated Databricks catalogs — align `bronze`, `silver`, `gold` Unity Catalog schemas to separate Fabric Lakehouses
- **Starter Pool** for migrating interactive notebook workflows — eliminates cluster startup time that was a common pain point in Databricks job clusters

### AVOID
- **Do not prescribe a one-size-fits-all workspace topology** when the source inventory and migration constraints are missing
- **Do not import `dbutils` or attempt `dbutils = ...` assignments** in Fabric notebooks — import attempts fail with `ModuleNotFoundError`, while unresolved `dbutils` references raise `NameError`; always use `notebookutils`
- **Do not retain `dbutils.*` calls behind runtime-detection guards** (`try/except`, `if IS_DATABRICKS`) — replace the calls and Databricks paths outright with `notebookutils` and Fabric paths
- **Do not assume Unity Catalog governance policies transfer automatically** — RBAC, row-level security, and column masking must be reconfigured in Fabric using workspace roles and Lakehouse permissions
- **Do not use `%pip install` in production Fabric notebooks** at runtime — use Fabric Environments for stable, versioned library management
- **Do not attempt to port Delta Live Tables (DLT) pipelines verbatim** — DLT has no Fabric equivalent; rewrite as parameterized notebooks orchestrated by Fabric Pipelines
- **Do not rely on Databricks-specific Spark configurations** (e.g., `spark.databricks.*`) — these are proprietary and will be silently ignored or raise errors in Fabric
- **Do not use DBFS paths** (`dbfs:/...`) — there is no DBFS in Fabric; all paths must use OneLake `abfss://` or Lakehouse-relative paths

---

## Multi-Notebook Migration Protocol

For workspaces with >3 notebooks or individual notebooks >5KB, process **one notebook at a time** (enumerate → export → transform → summarize → deploy → release) to avoid context overflow. Track each notebook through a status lifecycle (`inventory` → `analyzed` → `converted` → `deployed` → `validated`, or `failed`).

> Full protocol, status definitions, and per-notebook summary schema: [migration-orchestrator.md § Phase 2](resources/migration-orchestrator.md#phase-2-notebook-migration).

---

## Failure Reporting

When migration cannot complete (permission failures, unresolvable Blockers such as DLT or OS-level init scripts, namespace collisions with no user-chosen policy, or repeated API failures), emit a **structured failure report** — do not abandon silently. The report captures `phase_reached`, `blockers[]` (item / pattern / reason / recommendation), `partial_success` counts, and `next_steps`.

> Full report schema and stopping conditions: [migration-orchestrator.md § Failure Reporting](resources/migration-orchestrator.md#failure-reporting).

---

## Examples

See [dbutils-to-notebookutils.md](resources/dbutils-to-notebookutils.md) and [code-patterns.md](resources/code-patterns.md) for the full mapping. Key quick references:

**`dbutils.fs` → `notebookutils.fs`**

```python
# Databricks
dbutils.fs.ls("/mnt/bronze/orders/")
dbutils.fs.cp("/mnt/raw/file.csv", "/mnt/archive/file.csv")

# Fabric (replace DBFS/mount paths with OneLake relative paths)
notebookutils.fs.ls("Files/bronze/orders/")
notebookutils.fs.cp("Files/raw/file.csv", "Files/archive/file.csv")
```

**`dbutils.secrets` → `notebookutils.credentials`**

```python
# Databricks
pwd = dbutils.secrets.get(scope="prod", key="db-password")

# Fabric (scope → Key Vault URL, key → secret name)
pwd = notebookutils.credentials.getSecret("https://myvault.vault.azure.net/", "db-password")
```

**Unity Catalog namespace → Lakehouse schema**

```python
# Databricks
df = spark.read.table("prod.silver.customers")

# Fabric (ProdLakehouse represents the source catalog and is attached as context)
df = spark.read.table("silver.customers")
```
