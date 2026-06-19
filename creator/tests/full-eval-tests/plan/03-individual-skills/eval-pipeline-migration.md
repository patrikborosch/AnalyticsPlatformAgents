# Eval Plan: pipeline-migration

## Skill Overview
- **Skill:** `pipeline-migration`
- **Category:** Migration (Guidance-only eval — skill is capable of live Fabric API calls)
- **Purpose:** Migrate Synapse Data Factory pipeline artifacts to Microsoft Fabric Data Factory — reads source from Synapse data-plane APIs, creates Fabric pipelines/connections/Variable Libraries via Fabric REST API; also performs SynapseNotebook → TridentNotebook activity conversion and flags parked activities (SSIS, SHIR-only, Databricks)

## Prerequisites
- The skill is capable of live Fabric API calls (creates DataPipeline items, Connections, VariableLibrary items) but this eval plan does **not** exercise them
- These test cases use guidance-mode prompts ("how do I…") to evaluate correctness of migration instructions without requiring a live environment
- No eval datasets required

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Case Types

Tests in **this plan** all use **guidance-mode prompts** — invoke the skill with a "how do I…" question and verify the text output only. This tests correctness of migration instructions without requiring a live Synapse or Fabric environment.

> The skill's smoke test in `tests/tests.json` separately covers an **offline JSON translation** prompt (`"Translate the following Synapse pipeline … output the migrated JSON only"`) to exercise the transformation logic itself. That smoke test does not belong in this plan because it expects structured JSON output rather than guidance text — see `tests/tests.json` for the routing rules and expected substrings.

> **Important:** Do NOT create workspaces, pipelines, or any Fabric resources for any test in this plan. Just invoke the skill prompt and evaluate the response text.

## Test Cases

### PM-01: SynapseNotebook → TridentNotebook conversion
- **Prompt:** "I have a Synapse pipeline with a SynapseNotebook activity that runs a notebook called 'DataTransform'. The activity sets sparkPool to 'MediumPool'. How do I convert this to a Fabric TridentNotebook activity?"
- **Expected:** Skill explains the type rename from `SynapseNotebook` to `TridentNotebook`; states that `sparkPool`/`sessionConfiguration` must be removed; explains that the notebook is referenced by GUID (not name) obtained from `GET /v1/workspaces/{wsId}/notebooks`; provides a before/after JSON example or clear steps
- **Pass criteria:** Response mentions GUID-based reference (not name-based); states that `sparkPool` must be removed; shows or describes the `TridentNotebook` `typeProperties` structure with `notebookId` and `workspaceId`; does not suggest referencing notebooks by display name
- **Verification:** Text response only

### PM-02: Dataset inlining into Copy activity
- **Prompt:** "My Synapse Copy activity references a dataset named 'AzureBlobDataset' as its source. In Fabric, how do I handle this since datasets don't exist?"
- **Expected:** Skill explains Fabric has no Dataset item type; all dataset properties must be inlined into the activity's `source` (and `sink`) `typeProperties`; walks through the inlining pattern — take the dataset's `typeProperties` and merge them into the activity source block
- **Pass criteria:** Response states datasets don't exist in Fabric as separate items; describes moving dataset `typeProperties` into the activity's source/sink blocks; does not suggest creating a Dataset item in Fabric
- **Verification:** Text response only

### PM-03: Global parameter expression rewrite
- **Prompt:** "My Synapse pipeline uses @pipeline().globalParameters.environment throughout its activities. How do I handle this after migrating to Fabric?"
- **Expected:** Skill explains `@pipeline().globalParameters` does not exist in Fabric; the replacement is a Variable Library item; the expression becomes `@pipeline().libraryVariables.environment`; explains the Variable Library must be created first (Phase 1 in the migration sequence)
- **Pass criteria:** Response explicitly states `@pipeline().globalParameters` is invalid in Fabric; provides `@pipeline().libraryVariables.<name>` as the replacement; mentions creating a Variable Library item; does not suggest the globalParameters expression still works
- **Verification:** Text response only

### PM-04: Linked service → Fabric Connection mapping
- **Prompt:** "I have a Synapse linked service called 'AzureSQLLinkedService' pointing to an Azure SQL Database. What is the Fabric equivalent and how do I reference it in migrated pipeline activities?"
- **Expected:** Skill maps linked services to Fabric Connections; explains connections are created via `POST /v1/connections`; after dataset inlining, the connection is referenced via the activity's root-level `linkedService` property (a sibling of `typeProperties`, not nested inside `source`/`sink`); notes connections must exist before building pipeline JSON
- **Pass criteria:** Response identifies Fabric Connections as the linked service equivalent; describes obtaining the connection name; explains the connection reference lives at the activity root as `linkedService` (sibling of `typeProperties`); explains that connections must be created before assembling pipeline JSON; does not suggest reusing Synapse linked service names directly
- **Verification:** Text response only

### PM-05: Parked activities — SSIS and Databricks
- **Prompt:** "My Synapse pipeline has two activity types: ExecuteSSISPackage and DatabricksNotebook. Can I migrate these to Fabric?"
- **Expected:** Skill clearly flags both as parked/unsupported in direct migration; `ExecuteSSISPackage` has no Fabric equivalent; `DatabricksNotebook` can be approximated via `WebActivity` calling the Databricks REST API; directs user to pipeline-gotchas.md guidance
- **Pass criteria:** Response marks `ExecuteSSISPackage` as not supported (parked); offers WebActivity workaround for Databricks activities; does not imply these can be migrated transparently; recommends reviewing the gotchas documentation
- **Verification:** Text response only

### PM-06: Full pipeline migration scope assessment
- **Prompt:** "I have a Synapse workspace with 25 pipelines. Before I start migrating them to Fabric, I want to understand the scope and complexity. What should I assess?"
- **Expected:** Skill describes the pipeline assessment workflow — counting activities by type, identifying SynapseNotebook vs. compatible vs. parked activities, listing linked services for connection mapping, identifying global parameters for Variable Library creation; describes the read-only assessment as a prerequisite before migration
- **Pass criteria:** Response outlines assessment steps covering: activity type inventory, parked activity identification, linked service enumeration, dataset reference counting, global parameter inventory; recommends running assessment before migration; references the assessment capability of the skill
- **Verification:** Text response only

### PM-07: Negative — Validation activity type
- **Prompt:** "My Synapse pipeline uses a Validation activity to check if a file exists before copying it. Can I keep this in Fabric?"
- **Expected:** Skill explains the `Validation` activity type does not exist in Fabric Data Factory; it must be rewritten as a `GetMetadata` activity to fetch file metadata followed by an `IfCondition` activity to check the result
- **Pass criteria:** Response states `Validation` is not supported in Fabric; provides `GetMetadata` + `IfCondition` as the replacement pattern; does not suggest the Validation activity is available in Fabric
- **Verification:** Text response only

## Write Operations (for consistency pairing)

*Test cases in this plan use guidance-mode prompts and produce no Fabric resource writes. In production use, the skill creates DataPipeline items, Connections, and VariableLibrary items via the Fabric REST API.*

## Expected Token Range
- 400–2000 tokens per invocation
