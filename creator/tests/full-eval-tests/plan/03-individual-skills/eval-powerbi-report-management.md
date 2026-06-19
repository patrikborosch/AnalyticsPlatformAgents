---
plugin: powerbi-authoring
---

# Eval Plan: powerbi-report-management

## Skill Overview
- **Skill:** `powerbi-report-management`
- **Category:** Power BI Report Management
- **Purpose:** Manage Power BI report items in Fabric workspaces via Fabric REST APIs, including listing reports, downloading PBIR definitions, creating/updating report definitions, deleting reports, and publishing local PBIP reports.

## Pre-requisites
- Fabric workspace available as `{{WORKSPACE}}`
- Authentication configured (`az login`)
- Local PBIP fixture at `./evalsets/fixtures/sales-pbip/` (provisioned by this plan's Data Setup below)

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Data Setup (run before test cases)

Before executing PBRM-01..PBRM-05, publish the local PBIP fixture so subsequent read/update/delete cases have a real report to operate on. All names use the `eval_pbrm_` prefix for parallel-safety:

1. Publish `./evalsets/fixtures/sales-pbip/sales.SemanticModel/` to workspace `{{WORKSPACE}}` as semantic model `eval_pbrm_sales_model`.
2. Publish `./evalsets/fixtures/sales-pbip/sales.Report/` to workspace `{{WORKSPACE}}` as report `eval_pbrm_sales_report` bound to `eval_pbrm_sales_model`.
3. Capture the resulting report and semantic model IDs for reuse across cases.

## Test Cases

### PBRM-01: List and Resolve Report Item
- **Prompt:** "In workspace `{{WORKSPACE}}`, list Power BI reports and find the report named `eval_pbrm_sales_report`. Show its report ID."
- **Expected:** Skill resolves workspace and report IDs using Fabric workspace/report APIs.
- **Pass criteria:** Output uses the specified workspace only, lists report items, identifies the matching report, and does not confuse reports with notebooks, semantic models, or other Fabric item types.

### PBRM-02: Download PBIR Definition
- **Prompt:** "Download the PBIR definition for report `eval_pbrm_sales_report` in workspace `{{WORKSPACE}}` and explain the decoded definition parts."
- **Expected:** Skill calls the report getDefinition flow, handles LRO polling if needed, and decodes PBIR parts.
- **Pass criteria:** Output references `getDefinition?format=PBIR`, operation polling, decoded definition parts, and safe local output handling.

### PBRM-03: Publish Local PBIP Decision Flow
- **Prompt:** "Publish the local PBIP at `./evalsets/fixtures/sales-pbip/` to workspace `{{WORKSPACE}}` as `eval_pbrm_sales_report_v2`."
- **Expected:** Skill confirms report publish decisions before creating/updating Fabric report items.
- **Pass criteria:** Output confirms target workspace, asks whether to publish the local semantic model or bind to an existing model, describes report create/update decision points, and avoids silently guessing model bindings.

### PBRM-04: Delete Report Safety
- **Prompt:** "Delete the report named `eval_pbrm_temp_report` from workspace `{{WORKSPACE}}`."
- **Expected:** Skill resolves the exact report item and confirms safe deletion behavior.
- **Pass criteria:** Output scopes deletion to Power BI report items, verifies the target name/ID, avoids deleting semantic models or unrelated items, and describes post-delete verification. If the report does not exist, the skill reports that clearly rather than deleting an unintended item.

### PBRM-05: Update Report Definition
- **Prompt:** "Update the report `eval_pbrm_sales_report` in workspace `{{WORKSPACE}}` to add a new card visual bound to the `Total Quantity` measure. Re-download the definition afterwards and verify both visuals are present."
- **Expected:** Skill performs a full updateDefinition round-trip including LRO polling and post-update verification.
- **Pass criteria:** Output calls `updateDefinition` with **all** definition parts (modified + unmodified per the skill's CRITICAL NOTES on update payloads), polls the LRO to completion, re-downloads via `getDefinition?format=PBIR`, and confirms both the original and new visual are present in the returned definition.

## Data Teardown (run after test cases)

After all PBRM cases complete (pass or fail), clean up Fabric items from `{{WORKSPACE}}` in this order to avoid orphaned reports:

1. Delete report `eval_pbrm_sales_report` (if present)
2. Delete report `eval_pbrm_sales_report_v2` (if present)
3. Delete report `eval_pbrm_temp_report` (if present)
4. Delete semantic model `eval_pbrm_sales_model` (last — reports must be removed first)

## Write Operations (for consistency pairing)

| Write Case | Object | Type | Paired Read Skill |
|-----------|--------|------|-------------------|
| PBRM-03 | eval_pbrm_sales_report_v2 report item | Power BI Report | powerbi-report-management |
| PBRM-04 | eval_pbrm_temp_report deletion | Power BI Report | powerbi-report-management |
| PBRM-05 | eval_pbrm_sales_report updateDefinition | Power BI Report | powerbi-report-management |

## Expected Token Range
- 1500–4000 tokens per invocation
