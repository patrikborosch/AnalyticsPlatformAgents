# Combined Eval: Activator Authoring + Consumption

## Purpose
Verify that `activator-authoring-cli` and `activator-consumption-cli` work together for round-trip Activator workflows: create, inspect, modify, toggle, and delete.

## Flow
```text
activator-authoring-cli (WRITE) → Activator / Reflex item + definition → activator-consumption-cli (READ)
```

## Pre-requisites
- Shared `{{EVENTHOUSE}}` with KQL Database `{{KQLDB}}` provisioned by runner (Phase 0b)
- Shared `{{LAKEHOUSE}}` provisioned by runner (Phase 0b) for notebook-target and spark-job-target setup
- Fabric workspace supports Activator / Reflex items
- DTB-specific coverage still requires one reachable `DigitalTwinBuilder` or a **bound** `Ontology` item. Manual verification confirmed that bare Ontology item creation works through the public API, but public binding import is not yet reliable enough to make the ontology-backed case mandatory

## Data Setup (run FIRST)

For time-axis KQL data, do **not** use fixed historical timestamps. At the start of each eval run, compute a recent UTC window ending a few hours before the run, for example:
- `{{TIMEAXIS_START_UTC}} = current UTC time - 4 hours`
- `{{TIMEAXIS_END_UTC}} = current UTC time - 2 hours`

Ingest all `activator_combo_timeaxis.Timestamp` values inside that window, and use the same generated timestamps as the default `value` fields for the Activator source `DURATION_START` and `DURATION_END` query parameters. The exact clock values should be generated per run; avoid stale defaults such as `2025-01-01`.

1. In `{{KQLDB}}`, drop and recreate:
   - `activator_combo_timeaxis`
   - `activator_combo_snapshot`
2. Load sample rows into:
   - `activator_combo_timeaxis` with `Timestamp`, `Temperature`, `Building`, `Status`; timestamped rows must fall inside the recent `{{TIMEAXIS_START_UTC}}`–`{{TIMEAXIS_END_UTC}}` window
   - `activator_combo_snapshot` with `DeviceId`, `BatteryLevel`, `Status` and **no** timestamp column
3. Delete any leftover target items if they exist, then recreate:
   - notebook `eval_activator_target_notebook`
   - dataflow `eval_activator_target_dataflow`
   - spark job definition `eval_activator_target_sparkjob`
   - user data function `eval_activator_target_udf`
4. Create the notebook `eval_activator_target_notebook` with a minimal definition and bind it to `{{LAKEHOUSE}}` if notebook metadata requires a default lakehouse.
5. Create the Dataflow Gen2 item `eval_activator_target_dataflow` with a minimal inline Power Query M definition.
6. Create the Spark job definition item `eval_activator_target_sparkjob` using `SparkJobDefinitionV2`, a minimal `Main/main.py`, and `SparkJobDefinitionV1.json` bound to `{{LAKEHOUSE}}`.
7. Create the user data function item `eval_activator_target_udf` with the documented UDF definition shape: `definition.json` containing `$schema`, `runtime = "PYTHON"`, `connectedDataSources = []`, a non-empty `functions` list for `hello_fabric`, and `libraries.public` including `fabric-user-data-functions`; `resources/functions.json` containing matching `functionsMetadata` with HTTP trigger binding that explicitly sets `authLevel = "Anonymous"` plus `fabricProperties.fabricFunctionParameters` for `name: str` and `temperature: float`; and `function_app.py` with `import fabric.functions as fn`, `udf = fn.UserDataFunctions()`, and a decorated `@udf.function()` implementation for `hello_fabric(name: str, temperature: float) -> str`. Poll the UDF `updateDefinition` LRO until the body status is `Succeeded` or `Failed` before verifying; HTTP 200 with body status `Running` is not complete. If `resources/functions.json` succeeds but exposes no functions, retry once with the same `functionsMetadata` content at `.resources/functions.json`, keeping `authLevel = "Anonymous"`; never retry with `authLevel = "Function"` because Fabric rejects that value. Poll to terminal status, record both attempts, and verify that the item exposes a non-empty function list and record the discovered function name as `{{UDF_FUNCTION_NAME}}` (expected: `hello_fabric`).
8. Delete leftover Activators if they exist:
     - `eval-combo-monitor`
     - `eval-combo-snapshot`
     - `eval-combo-workspace`
     - `eval-combo-dtb`
     - `eval-combo-eventstream`
9. Delete leftover Eventstreams if they exist:
    - `eval_combo_source_eventstream`
10. If you need to seed ontology coverage in the workspace, create a bare Ontology item with `POST /v1/workspaces/{workspaceId}/ontologies` and wait for the LRO to succeed. Manual verification confirmed that this create flow works and auto-provisions companion Lakehouse, SQL endpoint, and GraphModel items.
11. For any follow-on ontology preparation, assume the public prerequisites from the ontology docs:
    - static OneLake data must be prepared first
    - time-series data can then come from Eventhouse / KQL
    - a separate non-schema lakehouse with a managed static table is a safer prep target than the ontology companion lakehouse
12. Try to discover one reachable DTB / Ontology item that is already usable for `digitalTwinBuilderSource-v1` queries and record:
    - `{{DTB_ITEM_NAME}}`
    - `{{DTB_ITEM_TYPE}}`
    - `{{DTB_ITEM_WORKSPACE_NAME}}`
    - `{{DTB_ITEM_ID}}`
    - `{{DTB_ITEM_WORKSPACE_ID}}`
    A bare created Ontology item does **not** count here until it is actually bound to data. During manual verification, entity-only ontology imports succeeded but minimal public `EntityTypes/.../DataBindings/*.json` imports failed with `ALMOperationImportFailed`, so if no pre-bound DTB / Ontology item can be found, skip `ACA-06` only.

## Data Teardown (run LAST)

1. Delete:
    - `eval-combo-monitor`
    - `eval-combo-snapshot`
    - `eval-combo-workspace`
    - `eval-combo-dtb`
    - `eval-combo-eventstream`
2. Delete Eventstreams if they still exist:
   - `eval_combo_source_eventstream`
3. Delete target items if they still exist:
   - notebook `eval_activator_target_notebook`
   - dataflow `eval_activator_target_dataflow`
   - spark job definition `eval_activator_target_sparkjob`
   - user data function `eval_activator_target_udf`
4. Drop:
    - `.drop table activator_combo_timeaxis ifexists`
    - `.drop table activator_combo_snapshot ifexists`

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### ACA-01: Create Then List
- **Prompt sequence:**
  1. "Create an Activator called `eval-combo-monitor` in my workspace."
  2. "List all Activators in my workspace and show me `eval-combo-monitor`."
- **Expected:** Step 1 routes to authoring and creates the item; Step 2 routes to consumption and finds it.
- **Pass criteria:**
  - Correct skill routing in both steps
  - Step 1 records `POST /v1/workspaces/{workspaceId}/reflexes` returning `201 Created` or `202 Accepted` followed by LRO success
  - Created item appears in the list with the exact name

### ACA-02: Create Time-Axis KQL Rule Then Inspect
- **Prompt sequence:**
  1. "Configure `eval-combo-monitor` to monitor the `activator_combo_timeaxis` table in my KQL database `{{KQLDB}}` and send a Teams message when the current temperature is greater than 30 degrees for Building-B devices."
  2. "Decode the definition of `eval-combo-monitor` and show me the source and rule details."
- **Expected:** Time-axis KQL source and rule are readable after authoring.
- **Pass criteria:**
  - Step 1 uses `activator-authoring-cli`
  - Step 2 uses `activator-consumption-cli`
  - Readback confirms `kqlSource-v1`, time-axis support, `declare query_parameters(startTime:datetime, endTime:datetime);`, filter on Building-B, and Teams action
  - Readback shows `DURATION_START` and `DURATION_END` default values matching the recent fixture window used for ingestion, not fixed stale dates
  - Readback shows a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesGreaterThan` rather than a steady-state `IsGreaterThan` condition, even though the user phrased the condition as "is greater than"
  - Readback shows the new rule started with `shouldRun: true`

### ACA-03: Add Aggregation Rule Then Verify Readback
- **Prompt sequence:**
  1. "Add a rule named `AvgTooHigh` to `eval-combo-monitor` that alerts when the 5-minute average temperature gets too high, above 25 degrees."
  2. "Explain the `AvgTooHigh` rule in `eval-combo-monitor`."
- **Expected:** Aggregation rule written by authoring is readable by consumption.
- **Pass criteria:**
  - Readback shows a 5-minute average aggregation
  - Readback shows threshold 25
  - Readback shows a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesGreaterThan`
  - Readback keeps the rule name `AvgTooHigh`
  - Readback shows the new rule started with `shouldRun: true`

### ACA-04: Modify Threshold Then Verify Updated Value
- **Prompt sequence:**
  1. "Change the threshold in the `AvgTooHigh` rule in `eval-combo-monitor` from 25 to 28."
  2. "What threshold is currently configured for `AvgTooHigh` in `eval-combo-monitor`?"
- **Expected:** Updated rule value round-trips exactly.
- **Pass criteria:**
  - Threshold changes from 25 to 28 in the write step
  - Consumption readback reports the updated value 28

### ACA-05: Create Snapshot-Mode Email Monitor Then Inspect
- **Prompt sequence:**
  1. "Create an Activator called `eval-combo-snapshot` that monitors the `activator_combo_snapshot` table in my KQL database `{{KQLDB}}` and emails me when battery level falls under 20 percent."
  2. "Inspect the source and action configuration for `eval-combo-snapshot`."
- **Expected:** Snapshot-mode source and email action are readable after authoring.
- **Pass criteria:**
  - Readback confirms no `eventTimeSettings`
  - Readback confirms empty `queryParameters`
  - Readback shows an `EmailMessage` action with the low-battery condition
  - Readback shows a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesLessThan`
  - Readback shows the new rule started with `shouldRun: true`

### ACA-06: Create DTB / Ontology Source Then Inspect
- **Prompt sequence:**
  1. "Create an Activator called `eval-combo-dtb` that uses the existing `{{DTB_ITEM_TYPE}}` item `{{DTB_ITEM_NAME}}` from workspace `{{DTB_ITEM_WORKSPACE_NAME}}` as a Digital Twin Builder source. Query truck telemetry every 5 minutes with a JSON query body that includes an entity selector plus a time-series selector, include a composite key, treat `Timestamp` as the event-time column, and send a Teams message when a truck starts going faster than 80."
  2. "Decode the definition of `eval-combo-dtb` and explain the DTB / Ontology source configuration."
- **Expected:** DTB / Ontology source written by authoring is readable by consumption.
- **Pass criteria:**
  - Step 1 uses `activator-authoring-cli`
  - Step 2 uses `activator-consumption-cli`
  - Readback shows `digitalTwinBuilderSource-v1`
  - Readback shows `connection.itemType` equal to `DigitalTwinBuilder` or `Ontology`
  - Readback shows `query.queryString` as a JSON-string payload, not KQL
  - Readback shows `query.compositeKey`
  - Readback shows `eventTimeSettings.timeFieldName = "Timestamp"`
  - Readback shows one `DURATION_START` and one `DURATION_END` query parameter
  - Readback explains that DTB time parameters are applied as endpoint query params rather than referenced inside the JSON query body
  - Readback shows a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesGreaterThan` and value 80
  - Readback shows the new rule started with `shouldRun: true`

### ACA-07: Add Notebook Fabric Item Action Then Inspect
- **Prompt sequence:**
  1. "Add a rule named `RunNotebookOnCriticalTemp` to `eval-combo-monitor` that runs the notebook `eval_activator_target_notebook` in my workspace when Building-B devices start running hotter than 35 degrees."
  2. "Show me the Fabric item action configuration for `RunNotebookOnCriticalTemp` in `eval-combo-monitor`."
- **Expected:** Notebook-target Fabric item action written by authoring is readable by consumption.
- **Pass criteria:**
  - Step 1 uses `activator-authoring-cli`
  - Step 2 uses `activator-consumption-cli`
  - Readback shows `fabricItemAction-v1` / `FabricItemInvocation`
  - Readback shows notebook name `eval_activator_target_notebook`
  - Readback shows `itemType: "SynapseNotebook"` and `jobType: "RunNotebook"`
  - Readback shows a non-empty `fabricJobConnectionDocumentId`
  - Readback shows a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesGreaterThan` and value 35
  - Readback shows the new rule started with `shouldRun: true`

### ACA-08: Add Dataflow Fabric Item Action Then Inspect
- **Prompt sequence:**
  1. "Add a rule named `RunDataflowOnCriticalTemp` to `eval-combo-monitor` that runs the dataflow `eval_activator_target_dataflow` in my workspace when Building-B devices start running hotter than 36 degrees."
  2. "Show me the Fabric item action configuration for `RunDataflowOnCriticalTemp` in `eval-combo-monitor`."
- **Expected:** Dataflow-target Fabric item action written by authoring is readable by consumption.
- **Pass criteria:**
  - Step 1 uses `activator-authoring-cli`
  - Step 2 uses `activator-consumption-cli`
  - Readback shows `fabricItemAction-v1` / `FabricItemInvocation`
  - Readback shows dataflow name `eval_activator_target_dataflow`
  - Readback shows `itemType: "DataflowFabric"` and `jobType: "Execute"`
  - Readback shows a non-empty `fabricJobConnectionDocumentId`
  - Readback shows a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesGreaterThan` and value 36
  - Readback shows the new rule started with `shouldRun: true`

### ACA-09: Add Spark Job Definition Fabric Item Action Then Inspect
- **Prompt sequence:**
  1. "Add a rule named `RunSparkJobOnCriticalTemp` to `eval-combo-monitor` that runs the spark job definition `eval_activator_target_sparkjob` in my workspace when Building-B devices start running hotter than 37 degrees."
  2. "Show me the Fabric item action configuration for `RunSparkJobOnCriticalTemp` in `eval-combo-monitor`."
- **Expected:** Spark-job-target Fabric item action written by authoring is readable by consumption.
- **Pass criteria:**
  - Step 1 uses `activator-authoring-cli`
  - Step 2 uses `activator-consumption-cli`
  - Readback shows `fabricItemAction-v1` / `FabricItemInvocation`
  - Readback shows spark job definition name `eval_activator_target_sparkjob`
  - Readback shows `itemType: "SparkJobDefinition"` and `jobType: "sparkjob"`
  - Readback shows a non-empty `fabricJobConnectionDocumentId`
  - Readback shows a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesGreaterThan` and value 37
  - Readback shows the new rule started with `shouldRun: true`

### ACA-10: Add User Data Function Fabric Item Action Then Inspect
- **Prompt sequence:**
  1. "Add a rule named `RunUdfOnCriticalTemp` to `eval-combo-monitor` that runs the user data function `{{UDF_FUNCTION_NAME}}` from the item `eval_activator_target_udf` in my workspace when Building-B devices start running hotter than 38 degrees. Pass a static string parameter named `name` and also pass the triggering temperature as a numeric parameter named `temperature`."
  2. "Show me the Fabric item action configuration for `RunUdfOnCriticalTemp` in `eval-combo-monitor`."
- **Expected:** UDF-target Fabric item action written by authoring is readable by consumption.
- **Pass criteria:**
  - Step 1 uses `activator-authoring-cli`
  - Step 2 uses `activator-consumption-cli`
  - Readback shows `fabricItemAction-v1` / `FabricItemInvocation`
  - Readback shows user data function item name `eval_activator_target_udf`
  - Readback shows Activator payload `itemType: "UserDataFunctions"` and `jobType: "Execute"`
  - Readback shows `subitemId` equal to `{{UDF_FUNCTION_NAME}}`
  - Readback makes it clear that the target UDF item exposes a non-empty function list including `{{UDF_FUNCTION_NAME}}`
  - Readback shows a non-empty `fabricJobConnectionDocumentId` that references the standalone `fabricItemAction-v1`
  - Readback shows only UDF parameters exposed by the target function metadata, with parameter names and types preserved
  - Readback shows a static parameter named `name` when the UDF exposes that parameter
  - Readback shows a dynamic parameter named `temperature` sourced from the triggering temperature field / attribute rather than a hardcoded literal when the UDF exposes that parameter
  - Readback shows a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesGreaterThan` and value 38
  - Readback shows the new rule started with `shouldRun: true`

### ACA-11: Create Workspace-Events Monitor Then Inspect Minimal Graph
- **Prompt sequence:**
  1. "Create an Activator called `eval-combo-workspace` that watches my workspace for item creation or deletion events and sends a Teams message every time something happens."
  2. "Show me the internal graph for `eval-combo-workspace`."
- **Expected:** Event-trigger workspace-events scenario round-trips cleanly.
- **Pass criteria:**
  - Readback confirms a real-time hub / workspace-events source
   - Readback confirms an event-trigger rule
   - Readback confirms minimal event graph and no object/attribute modeling

### ACA-12: Create Eventstream-Backed Activator Then Inspect
- **Prompt sequence:**
  1. "Create an Activator called `eval-combo-eventstream` in my workspace. Then create or update an Eventstream called `eval_combo_source_eventstream` with a `SampleData` `Bicycles` source, a default stream, and an `Activator` destination pointing at that Activator. After the sink is in place, read the Activator definition, find the auto-created source event, and add a disabled Teams rule that would notify for each incoming bicycle event."
  2. "Decode the definition of `eval-combo-eventstream` and explain the Eventstream source, the auto-created source event, and the disabled rule."
- **Expected:** Eventstream sink provisioning plus Activator readback round-trip cleanly.
- **Pass criteria:**
  - Step 1 uses `activator-authoring-cli`
  - Step 2 uses `activator-consumption-cli`
  - Readback shows `eventstreamSource-v1`
  - Readback shows `payload.metadata.eventstreamArtifactId` equal to the Eventstream item ID
  - Readback shows an auto-created SourceEvent that references the Eventstream source entity
  - Readback shows a disabled `EventTrigger` rule that references the discovered SourceEvent entity
  - Readback confirms the minimal event graph and no object/attribute modeling
  - Readback makes it clear that this disabled Eventstream rule is a specific exception; the default authoring behavior for new rules is `shouldRun: true`

### ACA-13: Toggle Rule Then Verify Running State
- **Prompt sequence:**
  1. "Stop the `AvgTooHigh` rule in `eval-combo-monitor`, verify it is off, then start it again."
  2. "Show me whether the `AvgTooHigh` rule in `eval-combo-monitor` is currently running."
- **Expected:** Toggle operation is visible on readback.
- **Pass criteria:**
  - Authoring step completes both toggle operations
  - Consumption step reports the final `shouldRun` state accurately

### ACA-14: Delete Then Verify Removal
- **Prompt sequence:**
  1. "Delete the Activator `eval-combo-monitor` from my workspace."
  2. "List all Activators in my workspace."
- **Expected:** Deleted item no longer appears in the list.
- **Pass criteria:**
  - Correct skill routing for write then read
  - Step 1 records `DELETE /v1/workspaces/{workspaceId}/reflexes/{reflexId}` returning a successful response
  - `eval-combo-monitor` is absent after deletion

## Consistency Metrics

| Metric | Target |
|--------|--------|
| Read/write round-trip consistency | 100% — items, rules, and source/action details written by authoring must be retrievable by consumption |
| Skill routing accuracy | 100% — write steps to authoring, read steps to consumption |
| Definition encoding round-trip | 100% — updated definitions remain readable via `getDefinition` |

## Expected Token Range
- 3000–8000 tokens per combined test (write + read + verify)
