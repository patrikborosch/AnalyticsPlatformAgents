# Eval Plan: synapse-migration

## Skill Overview
- **Skill:** `synapse-migration`
- **Category:** Migration Guidance (Description)
- **Purpose:** Guide engineers migrating Azure Synapse Analytics workloads to Microsoft Fabric — utility API porting, connectivity migration, SQL surface area gaps, and pipeline mapping

## Pre-requisites
- No Fabric workspace resources required — all tests are description/guidance tests
- No eval datasets required

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Case Types

All tests are **description tests** — invoke the skill and verify the text output only. No Fabric API calls are made.

> **Important:** Do NOT create workspaces, lakehouses, pipelines, or any Fabric resources for any test in this plan. Just invoke the skill prompt and evaluate the response text.

## Test Cases

### SYN-01: `mssparkutils.env` → `notebookutils.runtime` namespace *(description)*
- **Prompt:** "I have Synapse code that calls `mssparkutils.env.getWorkspaceName()` and `mssparkutils.env.getJobId()`. What are the exact notebookutils equivalents in Fabric?"
- **Expected:** Skill maps both calls to `notebookutils.runtime.context["workspaceName"]` and `notebookutils.runtime.context["jobId"]` and explains the namespace change from `env` to `runtime`
- **Pass criteria:** Response includes `notebookutils.runtime.context`, the correct key names `workspaceName` and `jobId`, and notes this is the key difference versus `mssparkutils.env`
- **Verification:** Text response only

### SYN-02: Linked Service → Fabric Data Connection / OneLake Shortcut *(description)*
- **Prompt:** "In Synapse I use a Linked Service called 'MyADLS' to connect to an ADLS Gen2 container. What replaces Linked Services in Fabric, and how do I access the same ADLS data?"
- **Expected:** Skill explains that Linked Services do not exist in Fabric and recommends an OneLake Shortcut as the replacement for ADLS Gen2 storage access, with a note that external databases use Fabric Data Connections instead
- **Pass criteria:** Response distinguishes between OneLake Shortcuts (for storage) and Data Connections (for databases); mentions `notebookutils.credentials.getSecret()` for credential handling
- **Verification:** Text response only

### SYN-03: `mssparkutils.credentials.getConnectionStringOrCreds()` migration *(description)*
- **Prompt:** "My Synapse notebook uses `mssparkutils.credentials.getConnectionStringOrCreds('AzureSQL_LinkedService')` to get a connection string. How do I port this to Fabric?"
- **Expected:** Skill explains this API is not available in Fabric (Linked Services don't exist), and shows the replacement using `notebookutils.credentials.getSecret(keyVaultUrl, secretName)` with the Key Vault URL
- **Pass criteria:** Response explicitly states the method is unavailable in Fabric and provides the `notebookutils.credentials.getSecret()` alternative with correct signature
- **Verification:** Text response only

### SYN-04: Dedicated SQL Pool DDL with distribution hints → Fabric Warehouse *(description)*
- **Prompt:** "I have a Dedicated SQL Pool table: `CREATE TABLE dbo.FactSales (...) WITH (DISTRIBUTION = HASH(CustomerID), CLUSTERED COLUMNSTORE INDEX)`. How do I create the equivalent in Fabric Warehouse?"
- **Expected:** Skill explains that `DISTRIBUTION` and `CLUSTERED COLUMNSTORE INDEX` hints are not needed in Fabric Warehouse (auto-managed), and provides the simplified DDL without those clauses
- **Pass criteria:** Response removes distribution hints, explains Fabric Warehouse auto-distributes, and provides a clean DDL
- **Verification:** Text response only

### SYN-05: PolyBase `CREATE EXTERNAL TABLE` → Fabric `COPY INTO` *(description)*
- **Prompt:** "My Synapse workspace uses PolyBase with `CREATE EXTERNAL DATA SOURCE` and `CREATE EXTERNAL TABLE` for bulk loading from ADLS. How do I load data in bulk in Fabric Warehouse?"
- **Expected:** Skill explains PolyBase is not available in Fabric Warehouse and provides `COPY INTO` as the replacement, with a working example using a OneLake path
- **Pass criteria:** Response includes a `COPY INTO` example with an `abfss://...onelake.dfs.fabric.microsoft.com/...` path or equivalent, and does not suggest PolyBase
- **Verification:** Text response only

### SYN-06: Negative — Ambiguous migration prompt *(description)*
- **Prompt:** "Migrate my Synapse to Fabric"
- **Expected:** Skill asks for clarification on which workload type to migrate (Spark notebooks, Dedicated SQL Pool, Synapse Pipelines, Linked Services) rather than making assumptions
- **Pass criteria:** Agent requests at minimum one clarifying detail (workload type, workspace name, or current code snippet) rather than producing generic output that cannot be acted upon
- **Verification:** Text response only

## Write Operations (for consistency pairing)

*None — this skill produces guidance output only; no Fabric resources are written.*

## Expected Token Range
- 600–1800 tokens per invocation
