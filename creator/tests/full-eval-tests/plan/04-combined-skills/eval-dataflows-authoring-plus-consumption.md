# Combined Eval: Dataflows Authoring + Consumption

## Purpose
Verify that dataflows created/modified by `dataflows-authoring-cli` are accurately inspectable by `dataflows-consumption-cli`.

## Flow
```
dataflows-authoring-cli (WRITE) → Dataflow Gen2 → dataflows-consumption-cli (READ definition, status, history)
```

## Pre-requisites
- Fabric workspace with Dataflows Gen2 capacity
- Fabric API authentication configured

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### DFCOMB-01: Create Dataflow via Authoring
- **Prompt:** "Create a Dataflow Gen2 named 'eval_combined_dataflow' with a Power Query M definition that returns a table with columns: Id (number), City (text), Population (number) with rows: (1,'Seattle',749256), (2,'Portland',652573), (3,'Vancouver',702000)"
- **Expected:** Dataflow created with valid definition
- **Pass criteria:** Dataflow exists in workspace item list

### DFCOMB-02: Read Back Definition via Consumption
- **Prompt:** "Decode the full definition of the 'eval_combined_dataflow' dataflow and show me the Power Query M code"
- **Expected:** Decoded mashup.pq with exact M code matching DFCOMB-01
- **Pass criteria:**
  - Contains `section Section1`
  - Contains rows: Seattle/749256, Portland/652573, Vancouver/702000
  - **EXACT MATCH required — this is a consistency test**

### DFCOMB-03: Trigger Refresh via Authoring, Monitor via Consumption
- **Prompt (authoring):** "Trigger a refresh of 'eval_combined_dataflow'"
- **Prompt (consumption):** "Show me the refresh status and job history for 'eval_combined_dataflow'"
- **Expected:** Job triggered by authoring appears in consumption job history
- **Pass criteria:**
  - Job instance visible in history
  - `startTimeUtc` and `status` present
  - Latest job timestamp matches the triggered refresh

### DFCOMB-04: Update Definition via Authoring, Verify via Consumption
- **Prompt (authoring):** "Update 'eval_combined_dataflow' to add a fourth row: (4,'SanFrancisco',883305)"
- **Prompt (consumption):** "Decode the definition of 'eval_combined_dataflow' again"
- **Expected:** Updated definition now shows 4 rows
- **Pass criteria:**
  - Row count in M code = 4
  - New row (SanFrancisco/883305) present
  - **EXACT MATCH required**

### DFCOMB-05: Cleanup via Authoring
- **Prompt:** "Delete the dataflow named 'eval_combined_dataflow'"
- **Expected:** Dataflow deleted
- **Pass criteria:** Dataflow no longer appears in workspace item list

## Consistency Scoring

For each read test case, compute:
```
definition_match = (decoded M code matches expected) ? 1 : 0
job_visible      = (triggered job appears in history) ? 1 : 0
row_accuracy     = (matching rows / total expected rows)
consistency      = (definition_match + job_visible + row_accuracy) / 3
```

**Pass threshold:** consistency = 1.0 for all test cases

## Expected Token Range
- 2500–5000 tokens per combined test (write + read + verify)
