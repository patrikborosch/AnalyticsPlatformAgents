# Eval Plan: activator-consumption-cli

## Skill Overview
- **Skill:** `activator-consumption-cli`
- **Category:** Activator / Reflex (Read)
- **Purpose:** List, inspect, and decode Fabric Activator / Reflex items and their rule/source/action definitions

## Pre-requisites
- Shared `{{EVENTHOUSE}}` with KQL Database `{{KQLDB}}` provisioned by runner (Phase 0b)
- Shared `{{LAKEHOUSE}}` provisioned by runner (Phase 0b) for notebook-target and spark-job-target setup
- Fabric workspace supports Activator / Reflex items
- DTB-specific coverage still requires one reachable `DigitalTwinBuilder` or a **bound** `Ontology` item. Manual verification confirmed that bare Ontology item creation works through the public API, but public binding import is not yet reliable enough to make the ontology-backed case mandatory

## Data Setup (run FIRST — before any test cases)

This plan must be self-contained and may not depend on the authoring eval having run first.
Like other self-contained consumption plans in this repo, it provisions its own
baseline fixtures during setup and removes them during teardown; the consumption
test cases themselves remain read-only.

For time-axis KQL fixtures, do **not** use fixed historical timestamps. At setup time, compute a recent UTC window ending a few hours before the run, for example:
- `{{TIMEAXIS_START_UTC}} = current UTC time - 4 hours`
- `{{TIMEAXIS_END_UTC}} = current UTC time - 2 hours`

Ingest all `activator_timeaxis_source.Timestamp` values inside that window, and set the baseline Activator source `DURATION_START` and `DURATION_END` default `value` fields to the same generated timestamps. Avoid stale defaults such as `2025-01-01`.

1. In `{{KQLDB}}`, recreate the same source tables used for Activator inspection:
   - `activator_timeaxis_source`
   - `activator_snapshot_source`
2. Load sample rows into both tables:
   - `activator_timeaxis_source` must include `Timestamp`, `Temperature`, `Pressure`, `Status`, `Message`, `IsOnline`, `Building`; timestamped rows must fall inside the recent `{{TIMEAXIS_START_UTC}}`–`{{TIMEAXIS_END_UTC}}` window
   - `activator_snapshot_source` must omit timestamps entirely and include `BatteryLevel`
3. Create a notebook item named `eval_activator_target_notebook` in the workspace with a minimal definition and bind it to `{{LAKEHOUSE}}` if notebook metadata requires a default lakehouse.
4. Create a Dataflow Gen2 item named `eval_activator_target_dataflow` with a minimal inline Power Query M definition.
5. Create a Spark job definition item named `eval_activator_target_sparkjob` using `SparkJobDefinitionV2`, a minimal `Main/main.py`, and `SparkJobDefinitionV1.json` bound to `{{LAKEHOUSE}}`.
6. Create a user data function item named `eval_activator_target_udf` with the documented UDF definition shape: `definition.json` containing `$schema`, `runtime = "PYTHON"`, `connectedDataSources = []`, a non-empty `functions` list for `hello_fabric`, and `libraries.public` including `fabric-user-data-functions`; `resources/functions.json` containing matching `functionsMetadata` with HTTP trigger binding that explicitly sets `authLevel = "Anonymous"` plus `fabricProperties.fabricFunctionParameters` for `name: str` and `temperature: float`; and `function_app.py` with `import fabric.functions as fn`, `udf = fn.UserDataFunctions()`, and a decorated `@udf.function()` implementation for `hello_fabric(name: str, temperature: float) -> str`. Poll the UDF `updateDefinition` LRO until the body status is `Succeeded` or `Failed` before verifying; HTTP 200 with body status `Running` is not complete. If `resources/functions.json` succeeds but exposes no functions, retry once with the same `functionsMetadata` content at `.resources/functions.json`, keeping `authLevel = "Anonymous"`; never retry with `authLevel = "Function"` because Fabric rejects that value. Poll to terminal status, record both attempts, and verify that the item exposes a non-empty function list and record the discovered function name as `{{UDF_FUNCTION_NAME}}` (expected: `hello_fabric`).
7. Create three baseline Activators for read-only inspection using authoring flows or direct REST calls during setup:
    - `eval-temp-monitor` — time-axis KQL source, Building-B filter, Teams rule, rules named `RepeatedHotSpike`, `AvgTooHigh`, `SteadyHotEveryTime`, `SustainedHotFiveMinutes`, `TemperatureResetToZero`, `PressureTrendUp10Percent`, `NoReadingsForFiveMinutes`, `StatusChangedToError`, `DeviceWentOffline`, and `ErrorBurstCount`, plus Fabric item action rules named `RunNotebookOnCriticalTemp`, `RunDataflowOnCriticalTemp`, `RunSparkJobOnCriticalTemp`, and `RunUdfOnCriticalTemp`; for ordinary threshold alerts, prefer transition-style conditions rather than steady-state conditions, but include explicit steady-state and sustained-period rules when the prompt asks for those semantics
    - `eval-snapshot-monitor` — snapshot-mode KQL source with Email rule for battery becoming less than 20
    - `eval-workspace-monitor` — workspace-events / real-time hub source with Teams action and minimal event graph
8. Create `eval-eventstream-monitor` plus Eventstream `eval_activator_source_eventstream` using:
   - `SampleData` source with `type: "Bicycles"`
   - one `Activator` destination pointing at `eval-eventstream-monitor`
   - resulting Activator readback with one `eventstreamSource-v1`, one auto-created SourceEvent, and one disabled event-trigger rule that references the discovered SourceEvent
9. If you need to seed ontology coverage in the workspace before discovery, create a bare Ontology item with `POST /v1/workspaces/{workspaceId}/ontologies` and wait for the LRO to succeed. Manual verification confirmed that this create flow works and auto-provisions companion Lakehouse, SQL endpoint, and GraphModel items, but a bare Ontology item is not yet sufficient for Activator source coverage by itself.
10. If a DTB / Ontology item is reachable **and already bound to usable data**, also create `eval-dtb-monitor` using `digitalTwinBuilderSource-v1` with:
    - `connection` pointing at the discovered item
    - a JSON-string query body with `entitySelector` and `timeSeriesSelector`
    - `query.compositeKey`
    - `eventTimeSettings.timeFieldName = "Timestamp"`
    - `queryParameters` containing one `DURATION_START` and one `DURATION_END` entry
    Manual verification showed that entity-only ontology imports succeed, but minimal public `EntityTypes/.../DataBindings/*.json` imports currently fail with `ALMOperationImportFailed`, so keep this ontology-backed baseline conditional on finding a pre-bound item.
11. Ensure all baseline Activators are readable through `getDefinition`

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### ACC-01: List Activators In Workspace
- **Prompt:** "List all Activator items in my workspace."
- **Expected result:** At least the three baseline Activators created during setup.
- **Pass criteria:**
  - Response includes `eval-temp-monitor`, `eval-snapshot-monitor`, and `eval-workspace-monitor`
  - Each item includes `id`, `displayName`, and `description` when available

### ACC-02: Get Details For A Specific Activator
- **Prompt:** "Show me the details of the Activator called `eval-temp-monitor` in my workspace."
- **Expected result:** Item metadata including id, name, description, type, and workspace.
- **Pass criteria:**
  - Agent resolves item ID dynamically by name
  - Item detail response includes the exact Activator name and its `id`

### ACC-03: Decode Full Definition
- **Prompt:** "Show me the full decoded definition of `eval-temp-monitor`."
- **Expected result:** Base64-decoded `ReflexEntities.json` shown as readable JSON.
- **Pass criteria:**
  - Uses `POST .../getDefinition` with an explicit body
  - Decodes Base64 payload correctly
  - Displays structured JSON rather than raw encoded payload only

### ACC-04: List Rules And Active State
- **Prompt:** "What rules are defined in `eval-temp-monitor`, and are they currently running?"
- **Expected result:** Rule names and `shouldRun` status values.
- **Pass criteria:**
  - Response includes at least `RepeatedHotSpike` and `AvgTooHigh`
  - Running state is shown for each rule
  - Response makes it clear that author-created rules are expected to default to `shouldRun: true`

### ACC-05: Inspect Time-Axis KQL Source
- **Prompt:** "Show me the KQL source configuration for `eval-temp-monitor` and explain whether it is using time-axis support."
- **Expected result:** Source configuration explains that time-axis support is enabled.
- **Pass criteria:**
  - Source is identified as `kqlSource-v1`
  - `eventTimeSettings` is present and mapped to `Timestamp`
  - Duration query parameters are present with default values matching the recent fixture window used for ingestion
  - Query text includes `declare query_parameters(startTime:datetime, endTime:datetime);`
  - Query uses a parameterized time range rather than hardcoded `ago(...)`

### ACC-06: Inspect Snapshot-Mode KQL Source
- **Prompt:** "Inspect the source for `eval-snapshot-monitor` and tell me whether it is using snapshot mode."
- **Expected result:** Source is described as snapshot mode because the table has no timestamp column.
- **Pass criteria:**
  - Source is identified as `kqlSource-v1`
  - No `eventTimeSettings` are present
  - `queryParameters` is empty
  - Response explains that the source reads current-state rows rather than a time-windowed stream

### ACC-07: Inspect Workspace-Events Rule Graph
- **Prompt:** "Show me how `eval-workspace-monitor` is wired internally — source, event graph, and rule structure."
- **Expected result:** Minimal event graph for workspace events is described.
- **Pass criteria:**
  - Real-time hub / workspace-events source is identified
  - Rule is identified as an event-trigger style rule
  - Response confirms the minimal event graph and absence of object/attribute modeling for this pure event-trigger case

### ACC-08: Inspect DTB / Ontology Source
- **Prompt:** "Show me the Digital Twin Builder / Ontology source configuration for `eval-dtb-monitor` and explain whether it is using time-axis support."
- **Expected result:** DTB / Ontology source configuration is decoded and described as a time-axis source.
- **Pass criteria:**
  - Source is identified as `digitalTwinBuilderSource-v1`
  - Source `connection.itemType` is `DigitalTwinBuilder` or `Ontology`
  - `query.queryString` is shown as a JSON-string payload rather than described as KQL
  - `query.compositeKey` is present
  - `eventTimeSettings.timeFieldName` is `Timestamp`
   - `queryParameters` includes one `DURATION_START` entry and one `DURATION_END` entry
   - Response explains that DTB time parameters are applied as endpoint query params rather than referenced inside the JSON query body
- **Missing infra note:** ACC-08 depends on the `eval-dtb-monitor` Activator from authoring plan AAC-06. If AAC-06 failed with `EVAL-BAIL-001` because no DTB / Ontology item was available, record `ACC-08` as `ERROR` with detail `EVAL-BAIL-001: prerequisite AAC-06 unavailable (no DTB / Ontology item)`. Do NOT use SKIP — SKIP triggers a suite-level abort per `00-overview.md`. This deterministic failure mode prevents the silent error class observed in run #25988928060.

### ACC-09: Inspect Eventstream Push-Source Wiring
- **Prompt:** "Inspect `eval-eventstream-monitor` and explain the Eventstream-backed source flow — show me the Eventstream source entity, the auto-created source event, and how the rule is wired to it."
- **Expected result:** Eventstream-backed Activator is described as a sink-driven push-source flow.
- **Pass criteria:**
  - Response identifies `eventstreamSource-v1`
  - Response shows `payload.metadata.eventstreamArtifactId`
  - Response identifies the auto-created `timeSeriesView-v1` event view / SourceEvent
  - Response explains that the SourceEvent references the Eventstream source entity rather than a hand-authored pull-source query
  - Response identifies the disabled `EventTrigger` rule and explains that it references the discovered SourceEvent entity
  - Response makes it clear that this flow is Eventstream sink first, Activator readback second
  - Response makes it clear that the disabled Eventstream rule is the explicit exception; normal new rules default to started

### ACC-10: Inspect Teams And Email Actions
- **Prompt:** "Show me the configured action types and targets for `eval-temp-monitor` and `eval-snapshot-monitor`."
- **Expected result:** Teams action for the temperature monitor and email action for the snapshot monitor.
- **Pass criteria:**
  - Response identifies the Teams action in `eval-temp-monitor`
  - Response identifies the Email action in `eval-snapshot-monitor`
  - Action targets or recipients are shown when present in the definition

### ACC-11: Inspect Notebook Fabric Item Action
- **Prompt:** "Show me the Fabric item action configuration in `eval-temp-monitor` and identify which notebook it runs."
- **Expected result:** Notebook-target Fabric item action details are decoded from the definition.
- **Pass criteria:**
  - Response identifies a `fabricItemAction-v1` / `FabricItemInvocation`
  - Response identifies notebook name `eval_activator_target_notebook`
  - Response shows `itemType: "SynapseNotebook"` and `jobType: "RunNotebook"`
  - Response shows a non-empty `fabricJobConnectionDocumentId`

### ACC-12: Inspect Dataflow Fabric Item Action
- **Prompt:** "Show me the Fabric item action configuration for the `RunDataflowOnCriticalTemp` rule in `eval-temp-monitor`."
- **Expected result:** Dataflow-target Fabric item action details are decoded from the definition.
- **Pass criteria:**
  - Response identifies a `fabricItemAction-v1` / `FabricItemInvocation`
  - Response identifies dataflow name `eval_activator_target_dataflow`
  - Response shows `itemType: "DataflowFabric"` and `jobType: "Execute"`
  - Response shows a non-empty `fabricJobConnectionDocumentId`

### ACC-13: Inspect Spark Job Definition Fabric Item Action
- **Prompt:** "Show me the Fabric item action configuration for the `RunSparkJobOnCriticalTemp` rule in `eval-temp-monitor`."
- **Expected result:** Spark-job-target Fabric item action details are decoded from the definition.
- **Pass criteria:**
  - Response identifies a `fabricItemAction-v1` / `FabricItemInvocation`
  - Response identifies spark job definition name `eval_activator_target_sparkjob`
  - Response shows `itemType: "SparkJobDefinition"` and `jobType: "sparkjob"`
  - Response shows a non-empty `fabricJobConnectionDocumentId`
  - Response makes it clear that the binding can legitimately have an empty parameters array because current public parameter discovery does not expose spark-job parameters

### ACC-14: Inspect User Data Function Fabric Item Action
- **Prompt:** "Show me the Fabric item action configuration for the `RunUdfOnCriticalTemp` rule in `eval-temp-monitor`."
- **Expected result:** UDF-target Fabric item action details are decoded from the definition.
- **Pass criteria:**
  - Response identifies a `fabricItemAction-v1` / `FabricItemInvocation`
  - Response identifies user data function item name `eval_activator_target_udf`
  - Response shows Activator payload `itemType: "UserDataFunctions"` and `jobType: "Execute"`
  - Response shows `subitemId` equal to `{{UDF_FUNCTION_NAME}}`
  - Response makes it clear that the target UDF item actually exposes that function rather than only referencing an item with an empty function list
  - Response shows a non-empty `fabricJobConnectionDocumentId` that references the standalone `fabricItemAction-v1`
  - Response shows only UDF parameters exposed by the target function metadata, with parameter names and types preserved
  - Response shows a static parameter named `name` when the UDF exposes that parameter
  - Response shows a dynamic parameter named `temperature` whose value comes from the triggering temperature field / attribute rather than a hardcoded literal when the UDF exposes that parameter

### ACC-15: Inspect Aggregation And Occurrence Logic
- **Prompt:** "Explain the conditions behind the `RepeatedHotSpike` and `AvgTooHigh` rules in `eval-temp-monitor`."
- **Expected result:** One rule is described as occurrence-based; the other as aggregation-based.
- **Pass criteria:**
  - `RepeatedHotSpike` is described as requiring repeated transition-based threshold crossings over a window rather than repeated steady-state matches
  - `AvgTooHigh` is described as using a 5-minute average and a threshold of 28
  - Response makes it clear that transition-style conditions are preferred for these alerting rules to avoid repeated notifications while the value stays high, and that ordinary wording like "is greater than" should still be interpreted as transition-based unless the user explicitly asks to notify every time / while the condition remains true

### ACC-16: Inspect Additional Rule Condition Expressivity
- **Prompt:** "Explain the condition types behind the `SteadyHotEveryTime`, `SustainedHotFiveMinutes`, `TemperatureResetToZero`, `PressureTrendUp10Percent`, `NoReadingsForFiveMinutes`, `StatusChangedToError`, `DeviceWentOffline`, and `ErrorBurstCount` rules in `eval-temp-monitor`."
- **Expected result:** The response identifies the distinct detector, occurrence, state-option, heartbeat, text, logical, trend, and aggregation semantics for each rule.
- **Pass criteria:**
  - `SteadyHotEveryTime` is described as an explicit steady-state `NumberValueCondition` / `IsGreaterThan` rule with `EachTime`, not a transition detector
  - `SustainedHotFiveMinutes` is described as a state numeric rule with `SustainedPeriodOption` for 5 minutes
  - `TemperatureResetToZero` is described as `NumberChanges` / `ChangesTo` 0
  - `PressureTrendUp10Percent` is described as `NumberTrendsBy` with `IncreasesByAtLeast`, offset 10, and percent mode enabled
  - `NoReadingsForFiveMinutes` is described as `NoHeartbeat` with a 5-minute duration
  - `StatusChangedToError` is described as `TextChanges` / `ChangesTo` `ERROR`
  - `DeviceWentOffline` is described as `LogicalBecomes` / `BecomesFalse`
  - `ErrorBurstCount` is described as a text equality condition for `Status = ERROR` with occurrence semantics (`ForNthTime` n=11 within 5 minutes), not as a numeric `Count` aggregation over the text status field

### ACC-17: Summary View
- **Prompt:** "Give me a concise summary of `eval-temp-monitor` — sources, objects, rules, and actions."
- **Expected result:** Grouped summary of the Activator configuration.
- **Pass criteria:**
  - Response groups content by source / rules / actions
  - Summary references the actual baseline entities rather than generic placeholders

### ACC-18: Negative — Write Operation Should Not Route Here
- **Prompt:** "Create a new Activator rule that sends a Teams message when temperature exceeds 30°C."
- **Expected result:** This should route to `activator-authoring-cli`, not this read-only skill.
- **Pass criteria:** FAIL_INVOCATION if `activator-consumption-cli` is used instead of `activator-authoring-cli`

## Data Teardown (run LAST — after all test cases)

1. Delete baseline Activators:
    - `eval-temp-monitor`
    - `eval-snapshot-monitor`
    - `eval-dtb-monitor`
    - `eval-eventstream-monitor`
    - `eval-workspace-monitor`
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

None during the consumption test cases themselves. Setup and teardown do create
and remove baseline fixtures so the plan can run independently, but the
evaluation prompts for `activator-consumption-cli` stay read-only.

## Expected Token Range
- 2000–6000 tokens per invocation
