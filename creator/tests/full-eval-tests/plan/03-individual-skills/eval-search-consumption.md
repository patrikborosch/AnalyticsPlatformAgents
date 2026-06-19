# Eval Plan: search-consumption-cli

## Skill Overview
- **Skill:** `search-consumption-cli`
- **Category:** Catalog Search (Read)
- **Purpose:** Search the OneLake catalog to find Fabric items by name, description, workspace name, or type via `az rest`

## Pre-requisites
- Dynamic test workspace provisioned by `tests/testdata/setup_test_env.py`
- Items provisioned by setup: lakehouse (`LSEGDemo`), eventhouse (`SkillsTestEventhouse`), semantic model (`nyctaxi_yellow_directlake`), notebook (`sparkauthoring_notebook_check`), dataflow (`SkillsTestDataflow`)
- `az login` completed against the shared test tenant (`E2EAPIMSIT2.onmicrosoft.com`)

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Setup
This plan uses the dynamically provisioned workspace and items from `tests/testdata/last_setup.json`. No additional setup is required beyond the standard `setup_test_env.py` run. All item names below are constants defined in the setup script.

## Test Cases

### SC-01: Find Lakehouse by Name
- **Prompt:** "Find a lakehouse called LSEGDemo using the Catalog Search API. Show me its ID and which workspace it belongs to."
- **Expected result:** Catalog Search returns the lakehouse with id, type, displayName, workspace info
- **Pass criteria:** Skill uses `POST /v1/catalog/search` with search text and type filter; result includes `LSEGDemo` in the dynamic workspace

### SC-02: Find Eventhouse by Name
- **Prompt:** "Find an eventhouse called SkillsTestEventhouse using the Catalog Search API."
- **Expected result:** Returns the eventhouse with id and workspace info
- **Pass criteria:** Skill uses `POST /v1/catalog/search` with `Type eq 'Eventhouse'` filter; result includes `SkillsTestEventhouse` in the dynamic workspace

### SC-03: Find Semantic Model by Name
- **Prompt:** "Search for a semantic model called nyctaxi_yellow_directlake. Give me its ID and workspace."
- **Expected result:** Returns the semantic model with id and workspace info
- **Pass criteria:** Skill uses `POST /v1/catalog/search` with `Type eq 'SemanticModel'` filter; result includes `nyctaxi_yellow_directlake` in the dynamic workspace

### SC-04: List All Items of a Type
- **Prompt:** "List all lakehouses I have access to across all workspaces."
- **Expected result:** Returns lakehouses across workspaces, including `LSEGDemo`
- **Pass criteria:** Skill uses empty search string with `Type eq 'Lakehouse'` filter; results include `LSEGDemo`

### SC-05: Combined Search and Type Filter
- **Prompt:** "Search for items named LSEGDemo that are either Lakehouses or SemanticModels."
- **Expected result:** Skill uses search text with combined type filter
- **Pass criteria:** Filter uses `Type eq 'Lakehouse' or Type eq 'SemanticModel'` syntax; results include `LSEGDemo`

### SC-06: Extract Item and Workspace IDs
- **Prompt:** "Find the notebook called sparkauthoring_notebook_check and give me its item ID and workspace ID."
- **Expected result:** Skill extracts `id` and `hierarchy.workspace.id` from the search response
- **Pass criteria:** Both IDs are returned; workspace matches the dynamic workspace

## Teardown
No teardown required — the standard workspace teardown handles cleanup.
