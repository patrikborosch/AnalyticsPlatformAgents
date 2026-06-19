# Eval Plan: hdinsight-migration

## Skill Overview
- **Skill:** `hdinsight-migration`
- **Category:** Migration Guidance (Description)
- **Purpose:** Guide engineers migrating Azure HDInsight workloads to Microsoft Fabric — WASB/ABFS path conversion, Hive DDL to Delta Lake, SparkSession migration, Oozie workflow porting, and introducing notebookutils

## Pre-requisites
- No Fabric workspace resources required — all tests are description/guidance tests
- No eval datasets required

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Case Types

All tests are **description tests** — invoke the skill and verify the text output only. No Fabric API calls are made.

> **Important:** Do NOT create workspaces, lakehouses, or any Fabric resources for any test in this plan. Just invoke the skill prompt and evaluate the response text.

## Test Cases

### HDI-01: WASB path → OneLake path conversion *(description)*
- **Prompt:** "My HDInsight Spark job reads data from `wasb://raw-data@mystorageaccount.blob.core.windows.net/logs/2024/`. What is the equivalent path pattern in Microsoft Fabric after migration?"
- **Expected:** Skill explains that `wasb://` is not supported in Fabric, describes creating a OneLake Shortcut to the Blob container, and shows the resulting `abfss://workspace@onelake.dfs.fabric.microsoft.com/...` path pattern or equivalent `Files/` relative path
- **Pass criteria:** Response includes `onelake.dfs.fabric.microsoft.com` in the path example and explains the shortcut creation step; does not suggest using `wasb://` directly
- **Verification:** Text response only

### HDI-02: `HiveContext` + `SparkContext` → Fabric SparkSession *(description)*
- **Prompt:** "My HDInsight notebook starts with: `from pyspark.sql import HiveContext; sc = SparkContext(); hc = HiveContext(sc)`. How do I port this to Fabric?"
- **Expected:** Skill explains `HiveContext` and standalone `SparkContext()` are legacy Spark 1.x/2.x APIs not needed in Fabric; the pre-instantiated `spark` session replaces them; provides the Fabric equivalent (just use `spark` directly)
- **Pass criteria:** Response explicitly states both `HiveContext` and `SparkContext()` constructors should be removed; explains `spark` and `sc` are pre-instantiated in Fabric notebooks
- **Verification:** Text response only

### HDI-03: Hive `STORED AS ORC` DDL → Delta Lake DDL *(description)*
- **Prompt:** "I have a Hive table: `CREATE TABLE sales_db.fact_orders (order_id BIGINT, amount DECIMAL(18,2)) STORED AS ORC LOCATION 'wasb://...' TBLPROPERTIES ('orc.compress'='SNAPPY')`. How do I create the equivalent in Fabric?"
- **Expected:** Skill converts to Delta DDL: removes `STORED AS ORC`, replaces with `USING DELTA`; removes or updates `LOCATION` to OneLake path or managed table; removes ORC-specific `TBLPROPERTIES`; adds `CREATE SCHEMA IF NOT EXISTS sales_db` step first
- **Pass criteria:** Response includes `USING DELTA`, creates the schema, removes `STORED AS ORC` and ORC-specific properties, and notes that Fabric Lakehouse manages the storage location
- **Verification:** Text response only

### HDI-04: Oozie Spark action → Fabric Pipeline Notebook activity *(description)*
- **Prompt:** "I have an Oozie `<spark>` action that runs a Spark job with parameters `--date 2024-01-01 --env prod`. How do I replace this with a Fabric Pipeline?"
- **Expected:** Skill maps the Oozie `<spark>` action to a Fabric Pipeline **Notebook activity** (or Spark Job Definition activity), shows how to pass `--date` and `--env` as notebook parameters, and mentions using a schedule trigger to replace the Oozie coordinator
- **Pass criteria:** Response identifies Notebook activity or SJD activity as the replacement; explains parameter passing (pipeline parameters → notebook cell parameters); mentions schedule trigger for time-based Oozie coordinators
- **Verification:** Text response only

### HDI-05: Introducing `notebookutils` for file operations *(description)*
- **Prompt:** "In my HDInsight jobs I use subprocess calls and the HDFS client to list and copy files. What is the Fabric equivalent? Show me how to list files in a folder and copy a file."
- **Expected:** Skill introduces `notebookutils.fs.ls()` and `notebookutils.fs.cp()` as the Fabric equivalents; explains no import is needed; shows code examples using `Files/` paths
- **Pass criteria:** Response includes `notebookutils.fs.ls(path)` and `notebookutils.fs.cp(src, dest)` with correct syntax; notes that `notebookutils` is pre-instantiated (no import required)
- **Verification:** Text response only

### HDI-06: Negative — HDFS path in Fabric *(description)*
- **Prompt:** "How do I access `hdfs:///user/data/input/` from my Fabric notebook?"
- **Expected:** Skill explains HDFS paths are not available in Fabric (no Hadoop cluster); guides the user to use OneLake `abfss://` paths or `Files/` relative paths instead; suggests an OneLake Shortcut if the data is still on an on-premises HDFS cluster
- **Pass criteria:** Response does not suggest using `hdfs://` paths; clearly states HDFS is not available; provides a OneLake-based alternative
- **Verification:** Text response only

## Write Operations (for consistency pairing)

*None — this skill produces guidance output only; no Fabric resources are written.*

## Expected Token Range
- 600–1800 tokens per invocation
