# Migration Gotchas — Databricks → Fabric

Known pitfalls, edge cases, and troubleshooting guidance for Databricks to Microsoft Fabric migrations.

---

## Critical Gotchas

### 1. Delta Live Tables (DLT) Has No Fabric Equivalent

**Symptom**: User expects to port DLT pipeline definitions directly.

**Reality**: Fabric has no declarative pipeline framework equivalent to DLT. The `CREATE STREAMING TABLE`, `CREATE LIVE TABLE`, `APPLY CHANGES INTO`, and `@dlt.table()` decorators do not exist in Fabric.

**Resolution**:
- Rewrite each DLT dataset as a parameterized notebook cell
- Use Fabric Data Pipelines for orchestration (dependency ordering, scheduling)
- Implement data quality checks using `assert` statements or the `great_expectations` library in place of DLT expectations (`CONSTRAINT ... EXPECT`)
- For streaming DLT, use Spark Structured Streaming with `availableNow=True` trigger in notebooks

**Severity**: Blocker — requires manual rewrite.

---

### 2. Unity Catalog Namespace Mapping (Collision Only Under Consolidation)

**Symptom**: User worries that collapsing 3-level `catalog.schema.table` into Fabric forces name collisions.

**Reality**: A **schema-enabled** Fabric Lakehouse preserves `schema.table`, and the Lakehouse stands in for the catalog — giving the full `workspace.lakehouse.schema.table` path. With the recommended **one Lakehouse per catalog** mapping, schemas and table names are preserved verbatim and there is **no collision**. Collisions only arise if the user deliberately consolidates multiple catalogs into a single Lakehouse (e.g., mapping both `prod.silver.orders` and `dev.silver.orders` into one Lakehouse's `silver.orders`).

**Resolution**:
- **Default**: create one schema-enabled Lakehouse per catalog (isolation, no renaming)
- Under elected consolidation with overlapping schema names, prefix schemas with the catalog name: `prod_silver.orders` / `dev_silver.orders`
- Or only migrate the production catalog; skip dev/staging

**Severity**: Info by default (one Lakehouse per catalog); Blocker only if the user consolidates catalogs and real collisions exist — then require a mapping policy.

---

### 3. `dbutils.widgets` Has No Direct Equivalent

**Symptom**: Notebooks that use `dbutils.widgets.get("param")`, `dbutils.widgets.text(...)`, or `dbutils.widgets.dropdown(...)` fail with `NameError`.

**Reality**: Fabric does not have an interactive widget system. The closest pattern is notebook parameters cells.

**Resolution**:
- Mark a cell as a "parameters cell" (contains default values)
- Parent notebooks pass overrides via `notebookutils.notebook.run("child", arguments={"param": "value"})`
- Pipelines pass overrides via the notebook activity's "Base parameters" setting
- For centralized config, use `notebookutils.variableLibrary.getLibrary("<name>")`

**Severity**: Warning — functional alternative exists but requires restructuring.

---

### 4. Photon-Specific Optimizations May Not Transfer to NEE

**Symptom**: Queries that were tuned for Photon's vectorized engine run slower or produce different execution plans on Fabric Native Execution Engine.

**Reality**: NEE covers most Photon capabilities. Support has broadened — Python and Scala UDFs and complex/nested types now work under NEE. The remaining gaps are narrower:
- NEE supports: scan, filter, project, aggregation, hash join, sort, plus UDFs and complex types
- Real limitations to watch: structured streaming, some data sources (e.g., JSON/XML readers), ANSI mode behaviors, and minor rounding/timezone differences vs Photon
- Fallback behavior: NEE falls back to Spark vanilla for unsupported operations (no error, just slower)

**Resolution**:
- Enable NEE in workspace Spark settings
- Benchmark critical queries; compare execution time
- If specific queries regress, check Spark UI for "fallback to non-native" indicators
- Accept that some Photon-specific micro-optimizations may not have exact NEE equivalents

**Severity**: Warning — usually acceptable; benchmark for critical paths.

---

### 5. DBFS Paths Do Not Exist in Fabric

**Symptom**: Any code referencing `dbfs:/`, `/dbfs/`, or `file:///dbfs/` fails.

**Reality**: Fabric has no DBFS. All storage is OneLake-based.

**Resolution**:
| Databricks Path Pattern | Fabric Equivalent |
|---|---|
| `dbfs:/mnt/bronze/data.parquet` | `Files/bronze/data.parquet` (Lakehouse-relative) |
| `/dbfs/tmp/checkpoint/` | `/tmp/checkpoint/` (local session disk) |
| `dbfs:/FileStore/...` | Upload to Lakehouse `Files/` folder or use OneLake Shortcut |
| `abfss://container@account.dfs.core.windows.net/path` | OneLake Shortcut → same ADLS path, then access via `Files/shortcut_name/path` |

**Severity**: Blocker for persistent data paths; Info for temp paths.

---

### 6. Databricks-Specific Spark Configs Are Silently Ignored

**Symptom**: `spark.conf.set("spark.databricks.delta.optimizeWrite.enabled", "true")` silently does nothing.

**Reality**: All `spark.databricks.*` configurations are proprietary and have no effect in Fabric. Some have Fabric equivalents, most don't.

**Resolution**:
| Databricks Config | Fabric Equivalent |
|---|---|
| `spark.databricks.delta.optimizeWrite.enabled` | **Automatic** in Fabric — no config needed |
| `spark.databricks.delta.autoCompact.enabled` | **Automatic** in Fabric via V-Order |
| `spark.databricks.delta.retentionDurationCheck.enabled` | Standard Delta: `delta.deletedFileRetentionDuration` |
| `spark.databricks.adaptive.autoOptimizeShuffle.enabled` | **Automatic** in Fabric |
| `spark.databricks.io.cache.enabled` | Not applicable — Fabric uses OneLake caching |
| `spark.databricks.passthrough.enabled` | Not applicable — use Fabric workspace identity |

**Severity**: Info (silently ignored) but can cause confusion if users expect behavior changes.

---

### 7. Init Scripts Cannot Install Arbitrary System Packages

**Symptom**: Databricks clusters using init scripts with `apt-get install`, `pip install`, or custom binaries.

**Reality**: Fabric Environments support PyPI and Conda packages but not arbitrary system-level installs.

**Resolution**:
- Move Python packages to Fabric Environment PyPI dependencies
- For system packages (e.g., `libgdal`, `poppler`), check if a pure-Python alternative exists
- If system packages are truly required, consider Azure ML compute or a containerized approach outside Fabric

**Severity**: Warning (PyPI packages migrate cleanly) or Blocker (system-level dependencies).

---

### 8. `dbutils.library.restartPython()` Behavior Difference

**Symptom**: Code that installs a library at runtime and restarts the Python process.

**Reality**: `notebookutils.session.restartPython()` exists in Fabric but the recommended pattern is different — Fabric strongly prefers all libraries to be pre-installed via Environments.

**Resolution**:
- Add libraries to Fabric Environment (preferred — deterministic, versioned)
- Use `%pip install` + `notebookutils.session.restartPython()` only for development/experimentation
- Never use runtime install in production SJDs or pipelines

**Severity**: Warning — functional but anti-pattern in production.

---

### 9. Databricks Repos ≠ Fabric Git Integration (Subtle Differences)

**Symptom**: User expects identical Git-backed notebook behavior.

**Key differences**:
| Databricks Repos | Fabric Git Integration |
|---|---|
| Notebooks stored as source files (.py, .ipynb) | Notebooks stored as Fabric items (JSON-based) |
| Direct branch switching in workspace | Sync workspace to/from branch |
| `%run ./relative_path` works naturally | Relative references require same workspace structure |
| Arbitrary folder nesting | Flat or shallow structure recommended |

**Resolution**:
- Restructure notebook hierarchy if deeply nested
- Test `%run` / `notebookutils.notebook.run()` paths after migration
- Verify Git sync works end-to-end before cutover

**Severity**: Info — usually works but test the integration.

---

### 10. Streaming Jobs Need Trigger Rewrite

**Symptom**: Streaming notebooks that run continuously on Databricks don't have a direct equivalent pattern in Fabric.

**Reality**: Fabric Spark does support Structured Streaming, but:
- Continuous processing triggers are not supported
- Long-running streaming jobs consume capacity units continuously
- The recommended pattern for batch-oriented streaming is `trigger(availableNow=True)`

**Resolution**:
| Databricks Streaming Pattern | Fabric Pattern |
|---|---|
| `trigger(processingTime="10 seconds")` — continuous | Schedule a notebook via Pipeline to run every N minutes with `trigger(availableNow=True)` |
| `trigger(continuous="1 second")` | Not supported — use `trigger(availableNow=True)` with scheduled runs |
| `trigger(once=True)` | `trigger(availableNow=True)` — equivalent semantics |
| `trigger(availableNow=True)` | ✅ Direct equivalent |

**Severity**: Warning — requires architectural decision for continuous streaming workloads.

---

## Quick Reference: Severity Summary

| Gotcha | Severity |
|---|---|
| DLT has no equivalent | Blocker |
| Namespace mapping | Info (one Lakehouse per catalog) / Blocker (only if user consolidates catalogs) |
| `dbutils.widgets` replacement | Warning |
| Photon → NEE differences | Warning |
| DBFS paths | Blocker (persistent) / Info (temp) |
| `spark.databricks.*` configs | Info |
| Init scripts (system packages) | Blocker (system) / Warning (Python) |
| `restartPython()` behavior | Warning |
| Repos vs Git Integration | Info |
| Streaming trigger rewrite | Warning |
