# Post-Migration Validation & Testing

Systematic verification that migrated Databricks items work correctly in Fabric before cutover.

> **Script pattern**: Sections show function signatures and key logic outlines. Generate the full runnable script on demand — this keeps the resource compact and reduces token load.

> **When to run**: Validation runs **incrementally after each phase**, not only at the end.
>
> | After Phase | Run These Sections | Gate |
> |---|---|---|
> | Phase 1 (Environments + Lakehouses) | V1, V2 | Do not proceed to Phase 2 until Environments publish and Shortcuts are healthy |
> | Phase 2 (Notebooks) | V3 | Do not proceed to Phase 3 until critical notebooks execute successfully |
> | Phase 3 (Jobs + Pipelines) | V4 | Do not cut over until SJDs/Pipelines pass |
> | Phase 4 (Full validation) | V5, V6 | Migration complete only when report is green |
>
> **Auth token**: Use the token-acquisition recipe in [COMMON-CLI § Authentication Recipes](../../../common/COMMON-CLI.md#authentication-recipes) with audience `https://api.fabric.microsoft.com`.

---

## Validation Workflow

```
Validation:
├── V1: Environment validation (Phase 1 outputs)
├── V2: Data validation (Lakehouses, Shortcuts, Tables)
├── V3: Notebook execution testing (Phase 2 outputs)
├── V4: Job/Pipeline execution testing (Phase 3 outputs)
├── V5: Output comparison (Databricks vs Fabric)
└── V6: Generate validation report
```

---

## Default Validation Tolerances

Apply these tolerances consistently across all comparisons. Exact equality is required only where noted; numeric aggregates use a **relative** tolerance so large magnitudes do not false-fail.

| Check | Tolerance / Rule |
|---|---|
| **Row count** | Exact match — any difference is a failure |
| **Schema** | Column name must match exactly; type must be compatible (e.g., nullable widening is acceptable, a type change is not) |
| **Numeric aggregate** (`sum`, `avg`, `min`, `max`) | Pass if `abs(expected - actual) <= max(abs_tol, rel_tol * max(abs(expected), abs(actual)))` with `abs_tol = 1e-3`, `rel_tol = 1e-9`. A raw absolute threshold alone false-fails large sums |
| **Sampling** | Use a **fixed seed** for reproducible sample comparisons |
| **Overall result** | `PASS` = all checks green; `PARTIAL` = only warning-level diffs; `FAIL` = any exact-match check (row count / schema / blocker) fails |

```python
def within_tolerance(expected, actual, abs_tol=1e-3, rel_tol=1e-9):
    """True if expected and actual agree within absolute OR relative tolerance.
    The relative term prevents false failures on large-magnitude aggregates."""
    delta = abs(expected - actual)
    scale = max(abs(expected), abs(actual))
    return delta <= abs_tol or delta <= rel_tol * scale
```

---

## V1: Environment Validation

Verify that Fabric Environments created in Phase 1 are published and usable.

### Check Environment Publish Status

```
GET https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/environments/{environmentId}
```

Check `properties.publishDetails.state` — must be `"Success"`.

### Validate Libraries

Run a test notebook attached to each Environment to confirm libraries are importable:

```python
# Verify critical libraries are importable
import_errors = []
required_libs = {
    "pandas": "pandas",
    "scikit-learn": "sklearn",
    "mlflow": "mlflow",
    # ... from the Databricks cluster library list
}

for pkg, module in required_libs.items():
    try:
        __import__(module)
    except ImportError:
        import_errors.append(pkg)

assert len(import_errors) == 0, f"Missing libraries: {import_errors}"
```

### Validate Spark Runtime Version

```python
# Check Fabric Runtime version meets the minimum expectation.
# Fabric Runtime 1.1 = Spark 3.3, 1.2 = Spark 3.4, 1.3 = Spark 3.5.
# Assert a *minimum* (not an exact version) so the check passes on any supported runtime.
print(f"Spark version: {spark.version}")
major_minor = tuple(int(x) for x in spark.version.split(".")[:2])
assert major_minor >= (3, 3), f"Expected Spark >= 3.3, got {spark.version}"
```

---

## V2: Data Validation

Verify Lakehouses and OneLake Shortcuts are healthy and accessible.

### Check Shortcut Health

```
GET https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/items/{lakehouseId}/shortcuts
```

For each shortcut, verify:
- Status is not "Failed" or "Disconnected"
- Target path is accessible (attempt a `notebookutils.fs.ls()` on the shortcut path)

### Row Count Comparison

Compare row counts between Databricks source tables and Fabric Lakehouse tables:

```python
def compare_row_counts(source_counts: dict, fabric_spark) -> list:
    """
    source_counts: dict mapping "schema.table" → row_count from Databricks
    fabric_spark: active SparkSession in Fabric
    Returns list of mismatches
    """
    mismatches = []
    for table_name, expected_count in source_counts.items():
        actual_count = fabric_spark.table(table_name).count()
        if actual_count != expected_count:
            mismatches.append({
                "table": table_name,
                "expected": expected_count,
                "actual": actual_count,
                "delta": actual_count - expected_count
            })
    return mismatches
```

### Schema Comparison

```python
def compare_schemas(source_schema: dict, fabric_spark) -> list:
    """
    source_schema: dict mapping "schema.table" → list of (col_name, col_type) from Databricks
    Returns list of schema differences
    """
    differences = []
    for table_name, expected_cols in source_schema.items():
        actual_cols = [(f.name, str(f.dataType)) for f in fabric_spark.table(table_name).schema.fields]
        if set(actual_cols) != set(expected_cols):
            differences.append({
                "table": table_name,
                "missing_in_fabric": set(expected_cols) - set(actual_cols),
                "extra_in_fabric": set(actual_cols) - set(expected_cols)
            })
    return differences
```

---

## V3: Notebook Execution Testing

Execute migrated notebooks and verify they complete without errors.

### Execution via REST API

```
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/items/{notebookId}/jobs/RunNotebook/instances
```

> The job type is part of the **path** (`.../jobs/{jobType}/instances`). The older query-string form (`.../jobs/instances?jobType=RunNotebook`) still works for backward compatibility.

Poll for completion:
```
GET https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/items/{notebookId}/jobs/instances/{instanceId}
```

### Execution Result Classification

| Status | Meaning | Action |
|---|---|---|
| `Completed` | Notebook ran successfully | ✅ Pass |
| `Failed` | Runtime error, or the run exceeded its configured timeout | Investigate cell outputs and duration; raise the job timeout only if the run is legitimately long |
| `Cancelled` | Explicitly cancelled by a user or the system — **not** a timeout | Do not auto-retry; determine why it was cancelled first |
| `Dequeued` | Capacity unavailable | Wait for capacity; retry |

### Common Post-Migration Failures

| Error | Root Cause | Fix |
|---|---|---|
| `NameError: name 'dbutils' is not defined` | Missed `dbutils` → `notebookutils` transform | Re-scan notebook for remaining `dbutils` references |
| `AnalysisException: Table or view not found` | Incorrect catalog-to-Lakehouse mapping or missing Lakehouse attachment | Verify the source catalog maps to the attached Lakehouse and the table uses its preserved `schema.table` name |
| `Py4JJavaError: Path does not exist: dbfs:/...` | DBFS path not converted to OneLake | Replace with `Files/...` or `abfss://` path |
| `ModuleNotFoundError: No module named '...'` | Library not in Fabric Environment | Add to Environment and republish |
| `PermissionError` on Key Vault access | Secret scope mapping incorrect | Verify `notebookutils.credentials.getSecret(kvUrl, secretName)` references correct vault |

---

## V4: Job/Pipeline Execution Testing

### Spark Job Definition Validation

Trigger a test run of each migrated SJD:

```
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/items/{sjdId}/jobs/SparkJob/instances
```

### Pipeline Validation

For migrated Data Pipelines (from multi-task Databricks Jobs):

```
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/items/{pipelineId}/jobs/Pipeline/instances
```

Verify:
- All activities complete successfully
- Activity dependencies execute in correct order
- Schedule triggers fire at expected times (if enabled)

---

## V5: Output Comparison (Databricks vs Fabric)

For critical tables/outputs, compare data between the Databricks source and Fabric target:

### Comparison Strategy

| Data Volume | Approach |
|---|---|
| < 10K rows | Full row-level comparison (`exceptAll`) |
| 10K–1M rows | Sample comparison (random 1% + statistical checks) |
| > 1M rows | Aggregate comparison (counts, sums, min/max, null counts per column) |

### Row-Level Comparison (Small Tables)

```python
def compare_outputs(databricks_df, fabric_df) -> dict:
    """Compare two DataFrames for exact equality (symmetric diff)."""
    results = {
        "row_count_match": databricks_df.count() == fabric_df.count(),
        "schema_match": databricks_df.schema == fabric_df.schema,
    }
    if results["schema_match"]:
        missing_in_fabric = databricks_df.exceptAll(fabric_df).count()
        extra_in_fabric = fabric_df.exceptAll(databricks_df).count()
        results["missing_in_fabric"] = missing_in_fabric
        results["extra_in_fabric"] = extra_in_fabric
        results["pass"] = results["row_count_match"] and missing_in_fabric == 0 and extra_in_fabric == 0
    else:
        results["pass"] = False
    return results
```

### Aggregate Comparison (Large Tables)

```python
def aggregate_comparison(databricks_df, fabric_df, numeric_cols: list) -> dict:
    """Statistical comparison for large tables."""
    from pyspark.sql import functions as F
    
    stats = {}
    for col_name in numeric_cols:
        db_stats = databricks_df.agg(
            F.count(col_name).alias("count"),
            F.sum(col_name).alias("sum"),
            F.avg(col_name).alias("avg"),
            F.min(col_name).alias("min"),
            F.max(col_name).alias("max")
        ).collect()[0]
        
        fb_stats = fabric_df.agg(
            F.count(col_name).alias("count"),
            F.sum(col_name).alias("sum"),
            F.avg(col_name).alias("avg"),
            F.min(col_name).alias("min"),
            F.max(col_name).alias("max")
        ).collect()[0]
        
        stats[col_name] = {
            "count_match": db_stats["count"] == fb_stats["count"],
            "sum_match": within_tolerance(db_stats["sum"], fb_stats["sum"]),
            "avg_match": within_tolerance(db_stats["avg"], fb_stats["avg"]),
        }
    return stats
```

> Uses `within_tolerance()` from **Default Validation Tolerances** above — a raw `abs(...) < 0.001` check false-fails large SUMs, so the relative term is required.

---

## V6: Generate Validation Report

Produce a structured report summarizing all validation results:

```
validation_report:
  workspace: <fabric_workspace>
  source: <databricks_workspace>
  timestamp: <ISO 8601>
  
  environment_validation:
    status: PASS | FAIL
    environments_checked: 3
    libraries_verified: 12
    failures: []
    
  data_validation:
    status: PASS | FAIL
    tables_checked: 24
    row_count_mismatches: []
    schema_mismatches: []
    shortcuts_healthy: true
    
  notebook_validation:
    status: PASS | PARTIAL | FAIL
    notebooks_tested: 38
    passed: 36
    failed: 2
    failures:
      - notebook: silver_transform
        error: "NameError: name 'dbutils' is not defined"
        cell: 5
        
  job_validation:
    status: PASS | FAIL
    sjds_tested: 4
    pipelines_tested: 2
    failures: []
    
  output_comparison:
    status: PASS | PARTIAL | FAIL
    tables_compared: 8
    exact_matches: 7
    aggregate_matches: 1
    mismatches: []
    
  overall_status: PASS | PARTIAL | FAIL
  blockers_remaining: 0
  ready_for_cutover: true | false
  
  recommendations:
    - "Fix remaining dbutils reference in silver_transform notebook (cell 5)"
    - "Verify schedule triggers after cutover"
```

### Report Status Definitions

| Status | Meaning | Action |
|---|---|---|
| **PASS** | All checks green | Safe to cutover |
| **PARTIAL** | Some items pass, some have warnings | Review warnings; decide if acceptable |
| **FAIL** | Critical failures prevent cutover | Fix failures before proceeding |
