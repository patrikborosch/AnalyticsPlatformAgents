# Eval Plan: databricks-migration

## Skill Overview
- **Skill:** `databricks-migration`
- **Category:** Migration Guidance (Description)
- **Purpose:** Guide engineers migrating Databricks workloads to Microsoft Fabric — complete dbutils → notebookutils mapping, Unity Catalog to Lakehouse schema migration, cluster/job/MLflow/Delta Sharing porting

## Pre-requisites
- No Fabric workspace resources required — all tests are description/guidance tests
- No eval datasets required

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Case Types

All tests are **description tests** — invoke the skill and verify the text output only. No Fabric API calls are made.

> **Important:** Do NOT create workspaces, lakehouses, or any Fabric resources for any test in this plan. Just invoke the skill prompt and evaluate the response text.

## Test Cases

### DB-01: `dbutils.fs.mount()` → Fabric mount options *(description)*
- **Prompt:** "My Databricks notebooks mount ADLS Gen2 with `dbutils.fs.mount(source='abfss://container@account.dfs.core.windows.net/', mount_point='/mnt/mydata', extra_configs={...})`. How do I replace this in Fabric?"
- **Expected:** Skill explains Fabric replacement options: `notebookutils.fs.mount()` for runtime mounts and **OneLake Shortcut** for durable/shared access; explains at a high level that Fabric uses Fabric-supported authentication or secret-management patterns rather than directly reusing Databricks OAuth `extra_configs`; shows that after shortcut creation, data is accessible at `Files/mydata/` or the equivalent OneLake path with no runtime mount code required
- **Pass criteria:** Response recommends an appropriate Fabric replacement option (`notebookutils.fs.mount()` for runtime mounts or OneLake Shortcut for persistent/shared access); does not imply Databricks `extra_configs` can be reused directly; distinguishes runtime-mount durability from OneLake Shortcuts when both options are discussed; does not suggest mounting via Spark config
- **Verification:** Text response only

### DB-02: `dbutils.secrets.get()` → `notebookutils.credentials.getSecret()` *(description)*
- **Prompt:** "I use `dbutils.secrets.get(scope='prod-secrets', key='db-password')` in Databricks. What is the exact Fabric equivalent?"
- **Expected:** Skill maps `dbutils.secrets.get(scope, key)` to `notebookutils.credentials.getSecret(keyVaultUrl, secretName)`; explains that Databricks secret scopes map to Azure Key Vault URLs; provides a working code example with the correct signature
- **Pass criteria:** Response includes `notebookutils.credentials.getSecret("https://<vault>.vault.azure.net/", "db-password")` pattern; correctly explains scope → Key Vault URL mapping; notes the Key Vault Secrets User role requirement
- **Verification:** Text response only

### DB-03: `dbutils.widgets` → Fabric notebook parameters *(description)*
- **Prompt:** "My Databricks notebook uses `dbutils.widgets.text('batch_date', '2024-01-01')` and then `batch_date = dbutils.widgets.get('batch_date')`. How do I replicate this in Fabric?"
- **Expected:** Skill explains `dbutils.widgets` has no direct equivalent; describes the Fabric pattern: tag a cell as `parameters`, declare the variable with a default value, and the pipeline or parent notebook injects the override at runtime; optionally shows `notebookutils.runtime.context.get("parameters", {})` for programmatic access
- **Pass criteria:** Response mentions the `parameters` cell tag; explains pipeline-based parameter injection; does NOT suggest a `dbutils.widgets` equivalent that doesn't exist
- **Verification:** Text response only

### DB-04: `dbutils.library.installPyPI()` → Fabric Environment *(description)*
- **Prompt:** "My Databricks notebook installs libraries at runtime: `dbutils.library.installPyPI('scikit-learn', version='1.3.0')` followed by `dbutils.library.restartPython()`. How do I handle this in Fabric?"
- **Expected:** Skill explains `dbutils.library` is not available in Fabric; directs the user to create a **Fabric Environment** item, add `scikit-learn==1.3.0` as a pip package, and attach it to the notebook or workspace — no runtime install code needed
- **Pass criteria:** Response explicitly states `dbutils.library` is unavailable; recommends Fabric Environment; explains the attach-to-notebook/workspace pattern; does not suggest `%pip install` for production workloads
- **Verification:** Text response only

### DB-05: Unity Catalog 3-level namespace → Fabric Lakehouse 2-level *(description)*
- **Prompt:** "My Databricks code reads from `spark.read.table('prod.silver.customers')` using Unity Catalog. How does this translate to Fabric?"
- **Expected:** Skill explains Fabric uses a 2-level namespace (schema.table) within a Lakehouse context; the `prod` catalog maps to a Fabric Lakehouse (e.g., `ProdLakehouse`); the equivalent Fabric call is `spark.read.table('silver.customers')` when `ProdLakehouse` is the attached Lakehouse
- **Pass criteria:** Response removes the catalog prefix; explains Lakehouse = catalog concept; shows `silver.customers` as the Fabric equivalent; mentions attaching the correct Lakehouse for context
- **Verification:** Text response only

### DB-06: MLflow tracking URI migration *(description)*
- **Prompt:** "My Databricks ML notebook starts with `mlflow.set_tracking_uri('databricks')` and `mlflow.set_experiment('/Users/me/MyExp')`. What changes when moving to Fabric?"
- **Expected:** Skill explains: (1) remove `mlflow.set_tracking_uri('databricks')` — Fabric auto-tracks MLflow; (2) change `set_experiment` to use a simple name without the path prefix: `mlflow.set_experiment('MyExp')`; all other MLflow calls (`log_metric`, `log_param`, `autolog`) are unchanged
- **Pass criteria:** Response removes `set_tracking_uri`; changes experiment to name-only; confirms all other MLflow APIs are identical; does not suggest any Fabric-specific MLflow import
- **Verification:** Text response only

### DB-07: Negative — `dbutils` in Fabric notebook *(description)*
- **Prompt:** "Can I use dbutils in a Fabric notebook? I want to run `dbutils.fs.ls('/mnt/data')`."
- **Expected:** Skill clearly states `dbutils` is not available in Fabric notebooks; explains `notebookutils.fs.ls()` is the equivalent; corrects the DBFS path (`/mnt/data`) to a OneLake path or `Files/` relative path; does not suggest importing dbutils or a compatibility shim
- **Pass criteria:** Response states `dbutils` is unavailable; provides `notebookutils.fs.ls("Files/data/")` or equivalent; corrects the DBFS path format
- **Verification:** Text response only

## Write Operations (for consistency pairing)

*None — this skill produces guidance output only; no Fabric resources are written.*

## Expected Token Range
- 600–2000 tokens per invocation
