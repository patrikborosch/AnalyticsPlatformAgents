---
plugin: powerbi-authoring
---

# Eval Plan: semantic-model-authoring

## Skill Overview
- **Skill:** `semantic-model-authoring`
- **Category:** Power BI Semantic Model Authoring (Write)
- **Purpose:** Develop and manage Power BI semantic models across Desktop, PBIP projects, and Fabric Service, including model creation, modeling standards, DAX optimization/refactoring, and Copilot/data-agent readiness

## Pre-requisites
- Fabric API authentication configured (`az login`)
- Fabric workspace `{{WORKSPACE}}` provisioned by runner (Phase 0)
- Shared `{{LAKEHOUSE}}` lakehouse provisioned by runner (Phase 0)
- Shared `{{WAREHOUSE}}` warehouse provisioned by runner (Phase 0)
- MCP server `powerbi-modeling-mcp` is available
- Delete all semantic models `eval_sm*` in `{{WORKSPACE}}` (if exist)

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### PSMA-01: Create a Direct Lake semantic model
- **Prompt:**
  "Create or replace semantic model in `{{WORKSPACE}}` connected to lakehouse `{{LAKEHOUSE}}` using DirectLake.
  Name of the semantic model: `eval_sm_sales_directlake`
  Business requirements:
    - I want to see the total sales amount so that I can understand revenue performance.
    - I want to see year-over-year and month-over-month sales growth percentages
    - I want to track profit %"
- **Expected:** Semantic model is created with correct definition.
- **Pass criteria:** 
  - Semantic model created in workspace; 
  - Modeling and direct lake guidelines were followed; 
  - Agent uses Fabric `{{LAKEHOUSE}}` as data source;
  - Business requirements in the prompt were respected as business measures;
  - Semantic model uses Direct Lake mode and partitions are entity based;  
  
### PSMA-02: Create a Import semantic model
- **Prompt:**
  "Create or replace semantic model in `{{WORKSPACE}}` connected to warehouse `{{WAREHOUSE}}` using Import.
    Name of the semantic model: `eval_sm_sales_import`
    Business requirements:
      - I want to see the total sales amount so that I can understand revenue performance.
      - I want to see total sales by product and product category    "
- **Expected:** Semantic model is created with correct definition.
- **Pass criteria:** 
  - Semantic model created in workspace; 
  - Modeling guidelines were followed; 
  - Agent uses Fabric `{{WAREHOUSE}}` as data source
  - Business requirements in the prompt were respected as business measures
  - Model definition includes a semantic model parameter to the Fabric SQL database connection string
  - Model uses Import mode with a Power Query expression for each table that queries the Fabric SQL database

### PSMA-03: Refresh the import semantic model
- **Prompt:** "Configure a shared cloud connection to `{{WAREHOUSE}}` in semantic model `eval_sm_sales_import` and refresh it."
- **Expected:** Semantic model is refreshed successfully
- **Pass criteria:** 
  - A connection to `{{WAREHOUSE}}` is configured in the semantic model
  - Semantic model refreshes successfully  
  
### PSMA-04: Get/Download Semantic Model Definition
- **Prompt:** "Download the TMDL definition of `eval_sm_sales_import` in workspace `{{WAREHOUSE}}`"
- **Expected:** Output contains semantic model definition as non-encoded *.tmdl files
- **Pass criteria:**   
  - Skill calls the `getDefinition` REST API  
  - Polls LRO if 202, and decodes all definition parts    

### PSMA-05: Set semantic model parameter
- **Prompt:** "Change the semantic model parameter of model `eval_sm_sales_import` that targets the `{{WAREHOUSE}}` with the same value appended by '-CHANGED'.
- **Expected:** Semantic model parameter is updated   
- **Pass criteria:**   
  - The API `/datasets/<model id>/parameters` is called    
  
### PSMA-06: Prepare Semantic Model for Copilot / Data Agents
- **Prompt:**
  "Prepare the semantic model `eval_sm_sales_import` to be consumed by Microsoft Fabric Copilot and Power BI Data Agents.
  Assume conversational BI is the target consumption mode and the model structure is stable."
- **Expected:** Semantic model is edited following the skill guidance
- **Pass criteria:**
  - Skill reference file `semantic-model-ai-readiness.md` is loaded
  - Agent inventoried the model and walked the Readiness Checklist (architecture, naming/synonyms, descriptions, AI instructions, AI Data Schema, Verified Answers, Data Agent alignment) in order
  - Output shows readiness workflow execution with model inventory and checklist progression  

## Data Teardown (run LAST — after all test cases)

Clean up objects created by this plan. Do NOT drop the shared `{{LAKEHOUSE}}` lakehouse or `{{WAREHOUSE}}` warehouse
1. Delete semantic models `eval_sm_*` created in `{{WORKSPACE}}`

## Expected Token Range
- 1500-4500 tokens per invocation
