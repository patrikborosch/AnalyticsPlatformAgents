# Eval Plan: activator-authoring-cli

## Skill Overview
- **Skill:** `activator-authoring-cli`
- **Category:** Activator / Reflex (Write)
- **Purpose:** Create, update, and delete Fabric Activator / Reflex items, sources, rules, and actions via Fabric REST APIs and definition updates

## Pre-requisites
- Shared `{{EVENTHOUSE}}` with KQL Database `{{KQLDB}}` provisioned by runner (Phase 0b)
- Shared `{{LAKEHOUSE}}` provisioned by runner (Phase 0b) for notebook-target and spark-job-target setup
- Fabric workspace supports Activator / Reflex items
- DTB-specific coverage still requires one reachable `DigitalTwinBuilder` or a **bound** `Ontology` item. Manual verification confirmed that bare Ontology item creation works through the public API, but end-to-end binding import through public `updateDefinition` is not yet reliable enough to make the ontology-backed case mandatory

## Data Setup (run FIRST — before any test cases)

This plan provisions its own source data and cleans up its own Activator items.

For time-axis KQL data, do **not** use fixed historical timestamps. At the start of each eval run, compute a recent UTC window ending a few hours before the run, for example:
- `{{TIMEAXIS_START_UTC}} = current UTC time - 4 hours`
- `{{TIMEAXIS_END_UTC}} = current UTC time - 2 hours`

Ingest all `activator_timeaxis_source.Timestamp` values inside that window, and use the same values as the default `value` fields for the Activator source `DURATION_START` and `DURATION_END` query parameters. The exact clock values should be generated per run; avoid stale defaults such as `2025-01-01`.

1. In `{{KQLDB}}`, drop leftover tables if they exist:
   - `.drop table activator_timeaxis_source ifexists`
   - `.drop table activator_snapshot_source ifexists`
2. Create `activator_timeaxis_source` with columns:
   - `Timestamp: datetime`
   - `DeviceId: string`
   - `Temperature: real`
   - `Pressure: real`
   - `Humidity: real`
   - `Status: string`
   - `Message: string`
   - `IsOnline: bool`
   - `Building: string`
3. Ingest sample rows into `activator_timeaxis_source` with:
   - `Timestamp` values inside the recent `{{TIMEAXIS_START_UTC}}`–`{{TIMEAXIS_END_UTC}}` window, such as `{{TIMEAXIS_START_UTC}} + 1m` through `{{TIMEAXIS_START_UTC}} + 10m`
   - at least one `Building-B` row
   - at least one `ERROR` status
   - at least one temperature outside the 10–25 range
4. Create `activator_snapshot_source` with columns:
   - `DeviceId: string`
   - `DeviceName: string`
   - `Status: string`
   - `Location: string`
   - `BatteryLevel: real`
5. Ingest sample rows into `activator_snapshot_source` with:
   - at least one battery level below 20
   - no timestamp column at all
6. Delete any leftover Activators from prior runs if they exist:
    - `eval-temp-monitor`
    - `eval-snapshot-monitor`
    - `eval-dtb-monitor`
    - `eval-eventstream-monitor`
    - `eval-workspace-monitor`
    - `eval-threshold-update`
7. Delete any leftover Eventstreams from prior runs if they exist:
   - `eval_activator_source_eventstream`
8. Delete any leftover target items from prior runs if they exist:
   - notebook `eval_activator_target_notebook`
   - dataflow `eval_activator_target_dataflow`
   - spark job definition `eval_activator_target_sparkjob`
   - user data function `eval_activator_target_udf`
9. Create a notebook item named `eval_activator_target_notebook` in the workspace with a minimal definition (for example, one code cell that prints `activator eval target`) and bind it to `{{LAKEHOUSE}}` if notebook metadata requires a default lakehouse.
10. Create a Dataflow Gen2 item named `eval_activator_target_dataflow` with a minimal inline Power Query M definition (for example, a hardcoded table with two rows) using the standard `Dataflow` create + `updateDefinition` flow.
11. Create a Spark job definition item named `eval_activator_target_sparkjob` using `SparkJobDefinitionV2`, a minimal `Main/main.py`, and `SparkJobDefinitionV1.json` bound to `{{LAKEHOUSE}}`.
12. Create a user data function item named `eval_activator_target_udf` using `POST /v1/workspaces/{workspaceId}/userDataFunctions` with the documented UDF definition shape. Use `POST .../userDataFunctions/{id}/updateDefinition` with these definition parts:
    - `definition.json`: include `$schema = "https://developer.microsoft.com/json-schemas/fabric/item/userDataFunction/definition/1.1.0/schema.json"`, `runtime = "PYTHON"`, `connectedDataSources = []`, `functions = [{ "name": "hello_fabric", "description": "Activator eval target", "isPublicEndpointEnabled": true }]`, and `libraries.public` containing `{ "name": "fabric-user-data-functions", "type": "PYPI", "version": "1.0" }`
    - `resources/functions.json`: include `runtime = "PYTHON"` and a matching `functionsMetadata` entry for `hello_fabric` with `scriptFile = "function_app.py"`, an HTTP trigger binding that explicitly sets `authLevel = "Anonymous"`, and `fabricProperties.fabricFunctionParameters` for `{ "name": "name", "dataType": "str" }` and `{ "name": "temperature", "dataType": "float" }`, plus `fabricFunctionReturnType = "str"` and `fabricMetadataSchemaVersion = "1.1.0"`
    - `function_app.py`: include `import fabric.functions as fn`, `udf = fn.UserDataFunctions()`, and a decorated `@udf.function()` implementation for `hello_fabric(name: str, temperature: float) -> str`
13. Poll the UDF `updateDefinition` long-running operation until the operation body has `status = "Succeeded"` or `status = "Failed"` before verifying the fixture. Do **not** treat HTTP 200 from the operation endpoint as completion while the body still says `status = "Running"`. If the documented `resources/functions.json` path reaches `Succeeded` but still exposes no functions, retry once with the same `functionsMetadata` content at `.resources/functions.json`, including the same HTTP trigger `authLevel = "Anonymous"` value; never change the retry to `authLevel = "Function"` because Fabric rejects that value. Poll that retry LRO to `Succeeded` or `Failed`, and record both attempts.
14. After a completed definition update, verify that `eval_activator_target_udf` exposes a non-empty function list and record the discovered function name as `{{UDF_FUNCTION_NAME}}` (expected: `hello_fabric`). Prefer the documented functions discovery endpoint if available; otherwise inspect decoded `definition.json.functions[]` and `resources/functions.json.functionsMetadata[]` or `.resources/functions.json.functionsMetadata[]` from `getDefinition`. If the function list is empty after a completed update, the UDF fixture is invalid and AAC-14 must not be treated as passing.
15. Capture the created notebook, dataflow, spark job definition, and user data function IDs for Fabric item action assertions.
16. If you need to seed ontology coverage in the workspace, create a bare Ontology item (for example, `eval_activator_ontology`) with `POST /v1/workspaces/{workspaceId}/ontologies`, wait for the LRO to succeed, and record the created item ID. Manual verification confirmed that this public create flow works and auto-provisions companion Lakehouse, SQL endpoint, and GraphModel items.
17. If you continue manual ontology preparation, follow the public ontology prerequisites:
    - create a managed static OneLake table first (manual verification succeeded with a separate non-schema lakehouse and a managed `dbo.ontology_devices` table loaded from CSV)
    - plan to bind time-series data from the existing Eventhouse / KQL table after static binding is in place
    - do **not** assume the ontology companion lakehouse is a drop-in source for automated setup
18. Try to discover one reachable DTB / Ontology item that is already usable for `digitalTwinBuilderSource-v1` queries and record:
    - `{{DTB_ITEM_NAME}}`
    - `{{DTB_ITEM_TYPE}}` (either `DigitalTwinBuilder` or `Ontology`)
    - `{{DTB_ITEM_WORKSPACE_NAME}}`
    - `{{DTB_ITEM_ID}}`
    - `{{DTB_ITEM_WORKSPACE_ID}}`
    A bare created Ontology item does **not** count here until it is actually bound to data. During manual verification, entity-only ontology imports succeeded but minimal public `EntityTypes/.../DataBindings/*.json` imports failed with `ALMOperationImportFailed`, so if no pre-bound DTB / Ontology item can be found, record `AAC-06` as `ERROR` with detail `EVAL-BAIL-001: no pre-bound DTB or Ontology item available in eval workspace`. Do NOT use SKIP — SKIP triggers a suite-level abort per `00-overview.md`. This deterministic failure mode prevents the silent error class observed in run #25988928060.

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

### Activator assertion rules

The Activator definition can become large when this plan runs AAC-01 through AAC-26 in one session. To avoid false failures, implement pass/fail checks against the **full decoded JSON entity list**, not against display excerpts or shortened log strings.

- Do not use truncated strings, compacted previews, grep output, or markdown excerpts as pass/fail inputs. Those are acceptable only for human-readable notes.
- For rule checks, find the `timeSeriesView-v1` entity by `payload.name`, parse `payload.definition.instance` as JSON, and inspect `templateId`, `steps[]`, `rows[]`, and `arguments[]` structurally.
- For source checks, find the source entity by `type`, `payload.name`, `parentContainer.targetUniqueIdentifier`, and expected target IDs rather than by substring search over the whole Reflex definition.
- For Fabric item action checks, find the named rule, then inspect its `ActStep` row named `FabricItemBinding`; use `fabricJobConnectionDocumentId` to resolve the referenced standalone `fabricItemAction-v1` entity and compare `workspaceId`, `itemId`, `itemType`, and `jobType` structurally.
- For event-trigger minimal graph checks, scope the assertion to the relevant source container. A pure event-trigger container must not contain Object / Attribute / SplitEvent entities, but unrelated containers in the same workspace or another Activator definition are not evidence of failure.
- Eventstream sink-created readback entities can legitimately preserve service-managed template versions such as `1.1`; record that readback discrepancy as a warning, not a failure by itself.

## Test Cases

### AAC-01: Create Empty Activator Item
- **Prompt:** "Create a new Activator item called `eval-threshold-update` in my workspace."
- **Expected:** Empty Activator / Reflex item created successfully.
- **Pass criteria:**
  - `POST /v1/workspaces/{workspaceId}/reflexes` returns `201 Created` or `202 Accepted` followed by LRO success
  - Item appears in `GET /v1/workspaces/{workspaceId}/reflexes`
  - Response includes a valid `id`, `displayName`, and `type`

### AAC-02: Create Activator With Description
- **Prompt:** "Create an Activator item named `eval-temp-monitor` with description `Monitors time-axis sensor data for temperature alerts` in my workspace."
- **Expected:** Activator created with both display name and description.
- **Pass criteria:**
  - Request resolves workspace dynamically
  - `POST /v1/workspaces/{workspaceId}/reflexes` returns `201 Created` or `202 Accepted` followed by LRO success
  - Item exists with exact `displayName`
  - Description is present and readable through item metadata

### AAC-03: Add Time-Axis KQL Source + Range Rule + Teams Action
- **Prompt:** "Configure `eval-temp-monitor` to monitor the `activator_timeaxis_source` table in my KQL database `{{KQLDB}}`. Send a Teams message when the temperature moves outside the safe 10 to 25 degree band, but only for devices in Building-B."
- **Expected:** Activator definition uses a `kqlSource-v1` over the shared KQL database plus an attribute-trigger rule with a building filter and Teams action.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Decoded definition contains `kqlSource-v1`
  - Source uses `eventTimeSettings` with `timeFieldName` mapped to `Timestamp`
  - Source includes `queryParameters` for duration start/end rather than hardcoded `ago(...)`
  - `DURATION_START` and `DURATION_END` default `value` fields match the recent fixture window used for ingestion, not fixed stale dates
  - KQL query declares `startTime` and `endTime` via `declare query_parameters(startTime:datetime, endTime:datetime);`
  - Rule uses a transition-style range detector equivalent to `NumberEntersOrLeavesRange` with `LeavesRange` and bounds 10–25, rather than a steady-state `IsOutsideRange` condition
  - Rule contains a `DimensionalFilterStep` for `Building-B`
  - New rule is created with `shouldRun: true` by default
  - Payload/readback checks use the full decoded JSON entity list

### AAC-04: Add Snapshot-Mode KQL Source + Email Action
- **Prompt:** "Create an Activator called `eval-snapshot-monitor` that monitors the `activator_snapshot_source` table in my KQL database `{{KQLDB}}` and emails me when any device battery level falls under 20 percent."
- **Expected:** Activator definition uses snapshot-mode KQL source because the table has no timestamp column.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Source definition uses `kqlSource-v1`
  - Source has **no** `eventTimeSettings`
  - Source `queryParameters` is empty
  - Rule uses a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesLessThan` and value 20, rather than a steady-state `IsLessThan` condition
  - Rule action is `EmailMessage`
  - New rule is created with `shouldRun: true` by default
  - Payload passes the validator

### AAC-05: Create Workspace-Events Rule With Minimal Event Graph
- **Prompt:** "Create an Activator called `eval-workspace-monitor` that watches my workspace for item creation or deletion events and sends me a Teams message every time something happens."
- **Expected:** Activator uses a `realTimeHubSource-v1` / workspace-events style source with an event-trigger rule.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Definition contains a real-time hub source and an `EventTrigger` rule
  - The `realTimeHubSource-v1` connection includes `scope = Workspace` and `eventGroupType = Microsoft.Fabric.WorkspaceEvents`
  - The referenced `container-v1` payload uses `type = rthSubscriptions`
  - Rule uses `EventDetectStep` with an every-event pattern
  - New rule is created with `shouldRun: true` by default
  - Definition uses the minimal event-trigger graph (container, source, source event, rule, optional standalone action)
  - Definition does **not** create Object / SplitEvent / IdentityPartAttribute / BasicEventAttribute entities for this pure event-trigger scenario
- **Missing infra note:** If no workspace-events RealTimeHub subscription source is available in the eval environment (Phase 0b does not provision one today), record status as `ERROR` with detail `EVAL-BAIL-001: workspace-events subscription not configured in eval workspace`. Do NOT use SKIP — SKIP triggers a suite-level abort per `00-overview.md`. This deterministic failure mode prevents the silent error class observed in run #25988928060.

### AAC-06: Add DTB / Ontology Time-Axis Source
- **Prompt:** "Create an Activator called `eval-dtb-monitor` that uses the existing `{{DTB_ITEM_TYPE}}` item `{{DTB_ITEM_NAME}}` from workspace `{{DTB_ITEM_WORKSPACE_NAME}}` as a Digital Twin Builder source. Query truck telemetry every 5 minutes, use a JSON query body with an entity selector plus a time-series selector, include a composite key, treat `Timestamp` as the event-time column, and send a Teams message when a truck starts going faster than 80."
- **Expected:** Activator definition uses `digitalTwinBuilderSource-v1` with a DTB / Ontology item ref, JSON-string query payload, and time-axis settings.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Decoded definition contains `digitalTwinBuilderSource-v1`
  - Source `connection` points at the dynamically resolved `{{DTB_ITEM_ID}}` / `{{DTB_ITEM_WORKSPACE_ID}}`
  - Source `connection.itemType` matches `{{DTB_ITEM_TYPE}}`
  - `query.queryString` is stored as a JSON string, not a nested object
  - `query.compositeKey` is present with both `name` and `keys`
  - `eventTimeSettings.timeFieldName` is `Timestamp`
    - `queryParameters` contains one `DURATION_START` entry and one `DURATION_END` entry
    - Response makes it clear that DTB time parameters are applied as endpoint query params rather than referenced inside the JSON query body
  - Rule uses a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesGreaterThan` and value 80
  - New rule is created with `shouldRun: true` by default

### AAC-07: Create Eventstream-Backed Activator Via Eventstream Sink
- **Prompt:** "Create an Activator called `eval-eventstream-monitor` in my workspace. Then create or update an Eventstream called `eval_activator_source_eventstream` with a `SampleData` `Bicycles` source, a default stream, and an `Activator` destination pointing at that Activator. After the sink is in place, read the Activator definition, find the auto-created source event, and add a disabled Teams rule that would notify for each incoming bicycle event without building an object or attribute model."
- **Expected:** Eventstream sink creation auto-provisions the Activator source entities, and authoring successfully appends a disabled minimal `EventTrigger` rule against the discovered SourceEvent.
- **Pass criteria:**
  - Eventstream create or update succeeds and the topology contains an `Activator` destination pointing at the newly created Activator item
  - Decoded Activator definition contains exactly one `eventstreamSource-v1` for the scratch Eventstream
  - The Eventstream source contains `payload.metadata.eventstreamArtifactId` equal to the Eventstream item ID
  - Decoded Activator definition contains one auto-created `timeSeriesView-v1` event view for the Eventstream source
  - The SourceEvent `SourceSelector.entityId` points at the discovered `eventstreamSource-v1`
  - A rule is added with `definition.type = "Rule"` and `templateId = "EventTrigger"`
  - The rule `FieldsDefaultsStep` references the discovered SourceEvent entity ID, not the raw source entity ID
  - The rule is created with `shouldRun: false` to avoid notification side effects during eval
  - The definition does **not** add Object / SplitEvent / IdentityPartAttribute / BasicEventAttribute entities for this pure event-trigger scenario

### AAC-08: Add Occurrence-Based Rule
- **Prompt:** "Add a rule named `RepeatedHotSpike` to `eval-temp-monitor` that alerts on Teams only after we see three separate hot spikes over 30 degrees within 10 minutes."
- **Expected:** Rule uses an occurrence option instead of firing on the first breach.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Rule uses a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesGreaterThan` and value 30
  - Rule includes occurrence semantics equivalent to `ForNthTime` with `n=3` and a 10-minute window
  - Teams action is wired to the rule
  - New rule is created with `shouldRun: true` by default

### AAC-09: Add Aggregation-Based Rule
- **Prompt:** "Add a rule named `AvgTooHigh` to `eval-temp-monitor` that alerts on Teams when the 5-minute average temperature gets too high, above 25 degrees."
- **Expected:** Rule uses aggregation before detection.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Rule includes a `ScalarSelectStep` / equivalent summary step computing average
  - Window duration is 5 minutes (300000 ms)
  - Detection step uses a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesGreaterThan` and value 25
  - New rule is created with `shouldRun: true` by default

### AAC-10: Add Alert With Temperature And Pressure Included
- **Prompt:** "Add a rule named `TempAndPressureAlert` to `eval-temp-monitor` that sends a Teams alert when the current temperature is greater than 32 degrees for Building-B devices. I want both the current temperature and pressure included in the alert."
- **Expected:** Definition adds a Teams rule whose alert content includes dynamic references for both temperature and pressure rather than only static text.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Rule uses a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesGreaterThan` and value 32, even though the user phrased the condition as "is greater than"
  - Rule contains a `DimensionalFilterStep` for `Building-B`
  - Teams action remains wired to the rule
  - The action binding includes dynamic alert content that references both the temperature field and the pressure field
  - At least one alert text field (`headline` and/or `optionalMessage`) contains mixed static text plus dynamic references rather than plain strings only
  - If `additionalInformation` is used, it includes structured entries for temperature and pressure rather than an empty array
  - New rule is created with `shouldRun: true` by default

### AAC-11: Add Notebook Fabric Item Action
- **Prompt:** "Add a rule named `RunNotebookOnCriticalTemp` to `eval-temp-monitor` that runs the notebook `eval_activator_target_notebook` in my workspace when Building-B devices start running hotter than 35 degrees."
- **Expected:** Definition adds a notebook-target `FabricItemInvocation` action using a standalone `fabricItemAction-v1` entity plus a `FabricItemBinding` row in the rule ActStep.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Definition contains a `fabricItemAction-v1` entity
  - The action points at the dynamically resolved notebook item ID in the current workspace
  - The action uses `itemType: "SynapseNotebook"` and `jobType: "RunNotebook"`
  - The rule ActStep contains row name `FabricItemBinding` with kind `FabricItemInvocation`
  - The binding includes a non-empty `fabricJobConnectionDocumentId`
  - The binding retains `additionalInformation` and `parameters` arrays
  - Rule uses a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesGreaterThan` and value 35
  - New rule is created with `shouldRun: true` by default

### AAC-12: Add Dataflow Fabric Item Action
- **Prompt:** "Add a rule named `RunDataflowOnCriticalTemp` to `eval-temp-monitor` that runs the dataflow `eval_activator_target_dataflow` in my workspace when Building-B devices start running hotter than 36 degrees."
- **Expected:** Definition adds a dataflow-target `FabricItemInvocation` action using a standalone `fabricItemAction-v1` entity plus a `FabricItemBinding` row in the rule ActStep.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Definition contains a `fabricItemAction-v1` entity
  - The action points at the dynamically resolved dataflow item ID in the current workspace
  - The action uses `itemType: "DataflowFabric"` and `jobType: "Execute"`
  - The rule ActStep contains row name `FabricItemBinding` with kind `FabricItemInvocation`
  - The binding includes a non-empty `fabricJobConnectionDocumentId`
  - The binding retains `additionalInformation` and `parameters` arrays
  - Rule uses a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesGreaterThan` and value 36
  - New rule is created with `shouldRun: true` by default

### AAC-13: Add Spark Job Definition Fabric Item Action
- **Prompt:** "Add a rule named `RunSparkJobOnCriticalTemp` to `eval-temp-monitor` that runs the spark job definition `eval_activator_target_sparkjob` in my workspace when Building-B devices start running hotter than 37 degrees."
- **Expected:** Definition adds a spark-job-target `FabricItemInvocation` action using a standalone `fabricItemAction-v1` entity plus a `FabricItemBinding` row in the rule ActStep.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Definition contains a `fabricItemAction-v1` entity
  - The action points at the dynamically resolved spark job definition item ID in the current workspace
  - The action uses `itemType: "SparkJobDefinition"` and `jobType: "sparkjob"`
  - The rule ActStep contains row name `FabricItemBinding` with kind `FabricItemInvocation`
  - The binding includes a non-empty `fabricJobConnectionDocumentId`
  - The binding retains `additionalInformation` and `parameters` arrays, even if the parameters array is empty because current public parameter discovery does not expose spark-job parameters
  - Rule uses a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesGreaterThan` and value 37
  - New rule is created with `shouldRun: true` by default

### AAC-14: Add User Data Function Fabric Item Action
- **Prompt:** "Add a rule named `RunUdfOnCriticalTemp` to `eval-temp-monitor` that runs the user data function `{{UDF_FUNCTION_NAME}}` from the item `eval_activator_target_udf` in my workspace when Building-B devices start running hotter than 38 degrees. Pass a static string parameter named `name` and also pass the triggering temperature as a numeric parameter named `temperature`."
- **Expected:** Definition adds a UDF-target `FabricItemInvocation` action using a standalone `fabricItemAction-v1` entity plus a `FabricItemBinding` row in the rule ActStep.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Definition contains a `fabricItemAction-v1` entity
  - The target UDF item was verified during setup to expose a non-empty function list
  - The target resolves the underlying Fabric item created through the public `UserDataFunction` API, but the action payload uses `itemType: "UserDataFunctions"`
  - The action uses `jobType: "Execute"`
  - The rule ActStep contains row name `FabricItemBinding` with kind `FabricItemInvocation`
  - The rule `payload.definition.instance` is a JSON-encoded string and every rule template step has an `id`
  - The binding includes a non-empty `fabricJobConnectionDocumentId` that references the standalone `fabricItemAction-v1.uniqueIdentifier`
  - The binding includes `subitemId` equal to `{{UDF_FUNCTION_NAME}}`
  - The binding includes only parameters exposed by the target UDF metadata, with `parameterName` matching that metadata exactly and `parameterType` set to the canonical Activator value (`String`, `Number`, or `Boolean`) corresponding to the metadata's Python type — **not** the raw Python type name (e.g. `float` is rejected; use `Number`)
  - The binding includes a `FabricItemParameter` named `name` with `parameterType: "String"` and a static string literal value (a single string part inside `parameterValue.values`) when the UDF exposes that parameter
  - The binding includes a `FabricItemParameter` named `temperature` with `parameterType: "Number"` whose value is dynamically sourced from the triggering temperature field / attribute rather than hardcoded when the UDF exposes that parameter. Specifically:
    - `parameterValue.values` contains an `AttributeReference` / `EventFieldReference` part with `type: "complexReference"` rather than only a literal string part
    - for `AttributeReference`, `entityId` resolves to a `BasicEventAttribute` entity in the same definition (not an `IdentityPartAttribute`)
  - Rule uses a transition-style numeric detector equivalent to `NumberBecomes` with `BecomesGreaterThan` and value 38
  - New rule is created with `shouldRun: true` by default

### AAC-15: Add Explicit Steady-State Number Rule
- **Prompt:** "Add a rule named `SteadyHotEveryTime` to `eval-temp-monitor` that sends a Teams alert every time the current temperature is greater than 30 degrees for Building-B devices while it remains above 30."
- **Expected:** Definition adds an explicitly steady-state rule because the prompt asks for every-time firing while the condition remains true.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Rule uses a state detector equivalent to `NumberValueCondition` with `IsGreaterThan` and threshold 30
  - Rule does **not** use `NumberBecomes` / `BecomesGreaterThan`
  - Rule includes occurrence semantics equivalent to `EachTime`
  - Rule contains a `DimensionalFilterStep` for `Building-B`
  - Teams action is wired to the rule
  - New rule is created with `shouldRun: true` by default

### AAC-16: Add Sustained Period Number Rule
- **Prompt:** "Add a rule named `SustainedHotFiveMinutes` to `eval-temp-monitor` that sends a Teams alert if the temperature stays above 30 degrees for 5 minutes."
- **Expected:** Definition adds a state condition with a sustained-period detector option.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Rule uses a state detector equivalent to `NumberValueCondition` with `IsGreaterThan` and threshold 30
  - Rule includes `SustainedPeriodOption` with a 5-minute period (300000 ms)
  - Rule does **not** use `NumberBecomes` / `BecomesGreaterThan`
  - Teams action is wired to the rule
  - New rule is created with `shouldRun: true` by default

### AAC-17: Add Number Change Rule
- **Prompt:** "Add a rule named `TemperatureResetToZero` to `eval-temp-monitor` that sends a Teams alert when the temperature changes to 0 degrees."
- **Expected:** Definition adds a numeric change detector rather than a threshold detector.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Rule uses `NumberChanges` with `op = "ChangesTo"` and value 0
  - Rule does **not** use `NumberBecomes` or `NumberValueCondition`
  - Teams action is wired to the rule
  - New rule is created with `shouldRun: true` by default

### AAC-18: Add Percent Trend Rule
- **Prompt:** "Add a rule named `PressureTrendUp10Percent` to `eval-temp-monitor` that sends a Teams alert when pressure increases by at least 10 percent from its previous value."
- **Expected:** Definition adds a trend detector using the documented row-name/kind pairing.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Rule uses row name `NumberTrends` with kind `NumberTrendsBy`
  - Trend operation is `IncreasesByAtLeast`
  - `offset` is 10 and `inPercent` is `true`
  - Teams action is wired to the rule
  - New rule is created with `shouldRun: true` by default

### AAC-19: Add Missing-Heartbeat Rule
- **Prompt:** "Add a rule named `NoReadingsForFiveMinutes` to `eval-temp-monitor` that sends a Teams alert if no sensor readings arrive for 5 minutes."
- **Expected:** Definition adds a heartbeat detector for missing readings.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Rule uses `NoHeartbeat` with duration 5 minutes (300000 ms)
  - Rule does **not** use `OnEveryValue` or `EachTime` as the primary heartbeat detector
  - Teams action is wired to the rule
  - New rule is created with `shouldRun: true` by default

### AAC-20: Add Text Change Rule
- **Prompt:** "Add a rule named `StatusChangedToError` to `eval-temp-monitor` that sends a Teams alert when the device status changes to `ERROR`."
- **Expected:** Definition adds a text change detector rather than a text state equality condition.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Rule uses `TextChanges` with `op = "ChangesTo"` and value `ERROR`
  - Rule does **not** use `TextValueCondition` / `IsEqualTo` as the primary detector
  - Teams action is wired to the rule
  - New rule is created with `shouldRun: true` by default

### AAC-21: Add Logical Transition Rule
- **Prompt:** "Add a rule named `DeviceWentOffline` to `eval-temp-monitor` that sends a Teams alert when `IsOnline` becomes false."
- **Expected:** Definition adds a boolean transition detector.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - Rule uses `LogicalBecomes` with `BecomesFalse`
  - The selected attribute is the boolean `IsOnline` field / attribute
  - Rule does **not** use `LogicalValueCondition` / `IsEqual` as the primary detector
  - Teams action is wired to the rule
  - New rule is created with `shouldRun: true` by default

### AAC-22: Add Text Occurrence Rule
- **Prompt:** "Add a rule named `ErrorBurstCount` to `eval-temp-monitor` that sends a Teams alert when more than 10 `ERROR` status readings occur within 5 minutes."
- **Expected:** Definition adds a text condition with occurrence semantics for `ERROR` status readings. Do not model this as a numeric count aggregation over the text `Status` attribute.
- **Pass criteria:**
  - `updateDefinition` returns HTTP 200
  - `ScalarSelectStep` selects the text `Status` field / attribute
  - `ScalarDetectStep` uses `TextValueCondition` with `op = "IsEqualTo"` and `value = "ERROR"`
  - The same `ScalarDetectStep` includes an occurrence option equivalent to `ForNthTime` with `n = 11` and duration 5 minutes (300000 ms), representing "more than 10" readings
  - Rule does **not** use `NumberSummary` / `Count` over the text status field
  - Rule does **not** use `NumberBecomes` / `BecomesGreaterThan` for this text occurrence condition
  - Teams action is wired to the rule
  - New rule is created with `shouldRun: true` by default

### AAC-23: Update Existing Rule Threshold
- **Prompt:** "Change the threshold in the `AvgTooHigh` rule in `eval-temp-monitor` from 25 to 28 degrees."
- **Expected:** Existing rule is modified in place.
- **Pass criteria:**
  - Agent reads the current definition first
  - Correct rule is located by name
  - Detection threshold is updated from 25 to 28
  - Updated definition round-trips successfully through `getDefinition`
  - The updated rule remains `shouldRun: true` unless the prompt explicitly requested a stopped state

### AAC-24: Toggle Rule Off Then On
- **Prompt:** "Stop the `AvgTooHigh` rule in `eval-temp-monitor`, verify it is off, then start it again."
- **Expected:** `shouldRun` toggles to false and then back to true.
- **Pass criteria:**
  - Definition update succeeds for both transitions
  - Follow-up `getDefinition` confirms `shouldRun: false` and then `shouldRun: true`

### AAC-25: Delete Activator By Name
- **Prompt:** "Delete the Activator called `eval-threshold-update` from my workspace."
- **Expected:** Activator is removed by name using item resolution rather than hardcoded IDs.
- **Pass criteria:**
  - Agent resolves the Activator ID dynamically
  - `DELETE /v1/workspaces/{workspaceId}/reflexes/{reflexId}` returns a successful response
  - Deleted item no longer appears in the workspace item listing

### AAC-26: Negative — Read-Only Prompt Should Not Route Here
- **Prompt:** "Show me all the Activators in my workspace."
- **Expected:** This should route to `activator-consumption-cli`, not this authoring skill.
- **Pass criteria:** FAIL_INVOCATION if `activator-authoring-cli` is used instead of `activator-consumption-cli`

## Data Teardown (run LAST — after all test cases)

Clean up all objects created by this plan. Do NOT drop the shared `{{EVENTHOUSE}}` or `{{KQLDB}}`.

1. Delete Activators if they still exist:
    - `eval-temp-monitor`
    - `eval-snapshot-monitor`
    - `eval-dtb-monitor`
    - `eval-eventstream-monitor`
    - `eval-workspace-monitor`
    - `eval-threshold-update`
2. Delete Eventstreams if they still exist:
   - `eval_activator_source_eventstream`
3. Delete target items if they still exist:
   - notebook `eval_activator_target_notebook`
   - dataflow `eval_activator_target_dataflow`
   - spark job definition `eval_activator_target_sparkjob`
   - user data function `eval_activator_target_udf`
4. Drop KQL tables:
    - `.drop table activator_timeaxis_source ifexists`
    - `.drop table activator_snapshot_source ifexists`

## Write Operations

| Write Case | Operation | Reversible |
|-----------|-----------|------------|
| AAC-01 | Create Activator item | Delete to reverse |
| AAC-02 | Create Activator item with description | Delete to reverse |
| AAC-03 | Upload Activator definition with KQL source and Teams rule | Update/delete to reverse |
| AAC-04 | Upload Activator definition with snapshot-mode source and email rule | Update/delete to reverse |
| AAC-05 | Upload Activator definition with workspace-events rule | Update/delete to reverse |
| AAC-06 | Add DTB / Ontology source definition | Update/delete to reverse |
| AAC-07 | Create Eventstream-backed Activator flow and append disabled event-trigger rule | Delete Eventstream + Activator to reverse |
| AAC-08 | Add occurrence-based rule | Update definition to remove |
| AAC-09 | Add aggregation-based rule | Update definition to remove |
| AAC-10 | Add Teams alert with dynamic temperature and pressure content | Update definition to remove |
| AAC-11 | Add notebook Fabric item action rule | Update definition to remove |
| AAC-12 | Add dataflow Fabric item action rule | Update definition to remove |
| AAC-13 | Add spark job definition Fabric item action rule | Update definition to remove |
| AAC-14 | Add user data function Fabric item action rule | Update definition to remove |
| AAC-15 | Add explicit steady-state numeric rule | Update definition to remove |
| AAC-16 | Add sustained-period numeric rule | Update definition to remove |
| AAC-17 | Add numeric change rule | Update definition to remove |
| AAC-18 | Add percent trend rule | Update definition to remove |
| AAC-19 | Add missing-heartbeat rule | Update definition to remove |
| AAC-20 | Add text change rule | Update definition to remove |
| AAC-21 | Add logical transition rule | Update definition to remove |
| AAC-22 | Add text occurrence rule | Update definition to remove |
| AAC-23 | Modify threshold inside existing rule | Update definition to revert |
| AAC-24 | Toggle shouldRun | Update definition to revert |
| AAC-25 | Delete Activator item | Recreate to reverse |

## Expected Token Range
- 2500–7000 tokens per invocation
