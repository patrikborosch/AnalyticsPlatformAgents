# Eval Plan: dataflows-consumption-cli

## Skill Overview
- **Skill:** `dataflows-consumption-cli`
- **Category:** Dataflows Gen2 (Read)
- **Purpose:** Monitor, inspect, and discover Fabric Dataflows Gen2 via read-only CLI operations (az rest / curl)

## Pre-requisites
- Fabric workspace with at least one Dataflow Gen2 (created by `dataflows-authoring-cli` evals or pre-existing)
- Fabric API authentication configured (`az login`)
- At least one dataflow with refresh history

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### DFC-01: List Dataflows in Workspace
- **Prompt:** "List all Dataflows Gen2 in my workspace"
- **Expected:** List of dataflows with displayName, id, and type
- **Pass criteria:** Output includes at least one dataflow with type `Dataflow`

### DFC-02: Decode Dataflow Definition (Consistency with DFA-01)
- **Prompt:** "Get and decode the full definition of the 'eval_authoring_basic' dataflow — show me the Power Query M code"
- **Expected:** Decoded mashup.pq content matching what was created in DFA-01
- **Pass criteria:**
  - Contains `section Section1`
  - Contains the hardcoded table rows from DFA-01
  - **EXACT MATCH required — this is a consistency test**

### DFC-03: Discover Parameters
- **Prompt:** "What parameters does my dataflow have? Show me their names, types, and default values"
- **Expected:** Parameter list extracted from M code or queryMetadata.json
- **Pass criteria:** Parameters listed with name, type, and currentValue/defaultValue

### DFC-04: Check Refresh Status
- **Prompt:** "What is the current refresh status of my dataflow? Is it running or completed?"
- **Expected:** Current job status (Completed, InProgress, Failed, or no active job)
- **Pass criteria:** Status includes `status` field and timestamps

### DFC-05: Retrieve Job History
- **Prompt:** "Show me the last 5 refresh runs for my dataflow with their start times, end times, and status"
- **Expected:** Job instance history with timing details
- **Pass criteria:** Output includes `startTimeUtc`, `endTimeUtc`, `status` for each run

### DFC-06: Analyze Staging Settings
- **Prompt:** "Which queries in my dataflow use staging (data movement service) and which run via the mashup engine directly?"
- **Expected:** Classification of queries by staging mode from queryMetadata.json
- **Pass criteria:** Queries classified with `AllowNativeQuery` or staging settings identified

### DFC-07: Inspect Connection Bindings
- **Prompt:** "What data source connections does my dataflow use? Show the connection details"
- **Expected:** Connection overrides from queryMetadata.json decoded and displayed
- **Pass criteria:** Output includes connection kind, path, and connectionId references

### DFC-08: Negative — Write Attempt Should Be Refused
- **Prompt:** "Delete the dataflow named 'eval_authoring_basic'"
- **Expected:** Skill refuses or routes to authoring skill
- **Pass criteria:** No dataflow deleted, user informed this is a read-only skill

## Consistency Test Matrix

| Read Case | Write Case (dataflows-authoring) | Artifact | Verification |
|-----------|----------------------------------|----------|-------------|
| DFC-02 | DFA-01 | Dataflow definition | M code exact match |
| DFC-05 | DFA-04 | Job history | Latest job matches triggered refresh |

## Expected Token Range
- 800–2500 tokens per invocation
