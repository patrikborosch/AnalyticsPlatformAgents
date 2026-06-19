# Eval Plan: dataflows-authoring-cli

## Skill Overview
- **Skill:** `dataflows-authoring-cli`
- **Category:** Dataflows Gen2 (Write)
- **Purpose:** Create, update, delete, and manage Fabric Dataflows Gen2 with Power Query M definitions via CLI (az rest / curl)

## Pre-requisites
- Fabric workspace provisioned with Dataflows Gen2 capacity
- Fabric API authentication configured (`az login`)
- Test dataflow definitions prepared (mashup.pq, queryMetadata.json)

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### DFA-01: Create Dataflow with Inline Definition
- **Prompt:** "Create a Dataflow Gen2 named 'eval_authoring_basic' in my workspace with a simple Power Query M definition that returns a table with columns Id (number), Name (text), Value (number) and 3 hardcoded rows"
- **Expected:** Dataflow created with valid definition
- **Pass criteria:** Dataflow appears in workspace item list with type `Dataflow`

### DFA-02: Get Dataflow Definition
- **Prompt:** "Get the definition of the 'eval_authoring_basic' dataflow and decode the mashup.pq content"
- **Expected:** Base64-decoded mashup.pq returned with the M code from DFA-01
- **Pass criteria:** Decoded content contains `section Section1` and the table definition

### DFA-03: Update Dataflow Definition
- **Prompt:** "Update the 'eval_authoring_basic' dataflow to add a fourth row (4, 'Delta', 400) to the hardcoded table"
- **Expected:** Definition updated with new row
- **Pass criteria:** Re-fetching definition shows 4 rows in the M code

### DFA-04: Trigger Refresh Job
- **Prompt:** "Trigger a refresh of the 'eval_authoring_basic' dataflow and poll until it completes"
- **Expected:** Refresh job triggered and completes (success or failure depending on data source)
- **Pass criteria:** Job status returned with `startTimeUtc`, `endTimeUtc`, and `status`

### DFA-05: Trigger Refresh with Parameter Override
- **Prompt:** "Trigger a refresh of a parameterized dataflow with parameter overrides: BaseURL = 'https://example.com/api'"
- **Expected:** Refresh triggered with executionData containing parameter overrides
- **Pass criteria:** Job request includes `executionData` with parameter values

### DFA-06: Delete Dataflow (throwaway target)
- **Prompt:** "Create a new Dataflow Gen2 named 'eval_delete_target_dataflow' in my workspace with a minimal Power Query M definition (an empty table with one column 'Id' of type number), then delete it"
- **Expected:** Throwaway dataflow created, then deleted in the same test
- **Pass criteria:** 'eval_delete_target_dataflow' appears in workspace item list after create, then no longer appears after delete; the persistent 'eval_authoring_basic' is left untouched so downstream consumption tests can read it
- **Why throwaway:** This test validates the DELETE operation on a freshly-created item. Earlier versions deleted the persistent 'eval_authoring_basic' here, which then broke 7 of 8 dataflows-consumption tests because the consumption plan runs against the same workspace later. The throwaway pattern keeps the test's actual intent (verify delete works) while preserving cross-plan state.

### DFA-07: Create Dataflow with Connection Binding
- **Prompt:** "Create a Dataflow Gen2 that connects to a Lakehouse SQL endpoint and queries a table. Show the connection binding in the definition."
- **Expected:** Definition includes connection references in queryMetadata.json
- **Pass criteria:** queryMetadata.json contains a `connections` array entry with a valid `connectionId` and `path`

### DFA-08: Export Definition for CI/CD
- **Prompt:** "Export the full definition of a dataflow (mashup.pq, queryMetadata.json, .platform) as separate decoded files suitable for Git version control"
- **Expected:** Three files decoded and presented
- **Pass criteria:** All three parts present with readable content (not base64)

### DFA-09: Discover Supported Connection Types and Required Parameters
- **Prompt:** "I want to create a SQL connection programmatically for my dataflow. List the supported connection types from Fabric, find the SQL entry, and tell me which `connectionDetails.parameters` and `credentialDetails.credentials.credentialType` values are valid."
- **Expected:** Agent calls `GET /v1/connections/supportedConnectionTypes` (filtered to `type=='SQL'`) and reports the parameter list and supported credential types from the live response.
- **Pass criteria** (static correctness, no live `201 Created` required):
  - Output references `GET /v1/connections/supportedConnectionTypes`
  - Output names at least the `server` parameter and at least one valid `credentialType` (e.g., `Basic`, `ServicePrincipal`, or `WorkspaceIdentity`)
  - Output does **not** invent parameter names that don't appear in the API response

### DFA-10: Generate a Schema-Accurate Cloud Connection Body
- **Prompt:** "Generate a `POST /v1/connections` request body to create a cloud SQL connection named 'eval_authoring_conn' with Basic auth, using a Fabric Key Vault connection for the password (do not put a plaintext password in the body)."
- **Expected:** A valid JSON body with the schema-accurate structure described in `connection-management.md`.
- **Pass criteria** (static correctness):
  - Body has `connectivityType: "ShareableCloud"`, `displayName`, and `privacyLevel: "Organizational"` (default explicit)
  - `connectionDetails`: `type: "SQL"`, `creationMethod: "SQL"`, with `parameters[]` for `server` (and optionally `database`)
  - `credentialDetails.credentials`: `credentialType: "Basic"`, `username`, and `passwordReference` (with `connectionId` + `secretName`)
  - **No** plaintext `password` field
  - **No** OAuth2 credentials (this credential type is not creatable via the API)

### DFA-11: End-to-End — Create Connection, Bind to Dataflow, Verify Bindings, Refresh
- **Prompt:** "I have a Dataflow Gen2 'eval_authoring_basic' that needs a new SQL connection. Walk through the full flow: list supported types, create a cloud SQL connection, capture its plain-GUID id, fetch ClusterId, bind it into queryMetadata.json, updateDefinition, **verify the bindings survived the save**, and trigger refresh."
- **Expected:** Step-by-step recipe covering all six phases with the right ID format at each step.
- **Pass criteria** (static correctness):
  - Mentions `GET /v1/connections/supportedConnectionTypes` before `POST /v1/connections`
  - Captures `id` from the `POST` response (plain GUID)
  - Fetches `ClusterId` via `GET https://api.powerbi.com/v2.0/myorg/me/gatewayClusterDatasources/<id>` with the Power BI audience (`--resource https://analysis.windows.net/powerbi/api`) and embeds the **stringified composite** `{"ClusterId":"…","DatasourceId":"…"}` into `queryMetadata.json connections[].connectionId`. The Fabric-audience `/v2/power-gateway/datasources/<id>` endpoint returns 404 and must not be used.
  - Includes a re-fetch / verify step **after** `updateDefinition` to confirm `connections[]` survived
  - Triggers refresh **only after** the verification step

### DFA-12: Preview Power Query M Before Saving via updateDefinition
- **Prompt:** "Before I save my new Power Query M to the 'eval_authoring_basic' dataflow, I want to preview that the M evaluates correctly against the bound connection. The query is named `Customers` and reads from a SQL connection. Walk me through the preview-then-save flow."
- **Expected:** Step-by-step recipe with `executeQuery` preview ordered **before** `updateDefinition`.
- **Pass criteria** (static correctness):
  - Mentions `POST /v1/workspaces/{ws}/dataflows/{df}/executeQuery` with body `{"QueryName":"...","customMashupDocument":"..."}`
  - Wraps the M as a complete `section Section1; ... shared Customers = ...;` document (does NOT send a raw `let ... in ...` expression and rely on server-side wrapping)
  - States that `QueryName` must match a `shared` member declared in the document
  - Captures the response with `--output-file results.arrow` (raw Apache Arrow bytes — `az rest` does NOT return a JSON `{success,error}` envelope) **before** calling `updateDefinition`
  - Checks for embedded source errors via `grep -q '"Error":"' results.arrow` (HTTP 200 does NOT mean success); only proceeds when the marker is absent
  - `updateDefinition` is ordered **after** a successful preview, not before
  - Does NOT recommend `EvaluateQuery` for this flow (that endpoint requires a prior successful refresh)
  - Does NOT claim a Fabric REST `validateOnly` mode exists (that is MCP-only client-side parsing)
  - When the candidate source is production-volume, recommends a preview-only cap (e.g. `Table.FirstN`, `TOP N` via `Value.NativeQuery`, or a date predicate) and explicitly notes the cap is stripped before the production save

### DFA-13: Iterative Preview — Fix Error and Re-Preview Before Save
- **Prompt:** "My executeQuery preview just returned `{ \"success\": false, \"error\": \"Query not found: SalesData\" }` — what does this mean and what do I do next? My customMashupDocument starts with `let Source = ... in Filtered`."
- **Expected:** Diagnoses the auto-wrap / QueryName-mismatch issue and prescribes a re-preview-then-save loop.
- **Pass criteria** (static correctness):
  - Identifies that `customMashupDocument` is missing the `section Section1; shared <name> = ...;` wrapper, so no `shared` member matches `QueryName`
  - Provides a corrected `section Section1; shared SalesData = let ... in ...;` document
  - Re-runs `executeQuery` with the corrected document **before** any `updateDefinition` call
  - Does not jump straight to `updateDefinition` and refresh-then-debug

### DFA-14: Generate a Schema-Accurate Create-Dataflow Body
- **Prompt:** "Generate the JSON request body for `POST /v1/workspaces/{ws}/dataflows` to create a Dataflow Gen2 named 'eval_authoring_basic' with an inline mashup.pq, queryMetadata.json, and .platform. Show me the exact body you'd send."
- **Expected:** A valid create-dataflow body that uses `definition.parts[]` only and omits `definition.format` (the Fabric API rejects `format: "json"` on Dataflow Gen2 with `400 InvalidDefinitionFormat`).
- **Pass criteria** (static correctness):
  - Body has `displayName` and `definition.parts[]` with at least `mashup.pq`, `queryMetadata.json`, and `.platform` entries
  - Each part has `path`, base64 `payload`, and `payloadType: "InlineBase64"`
  - Body does **NOT** include `definition.format` (no `"format": "json"` or any other value at the `definition` level)
  - Body does **NOT** include a top-level `"type": "Dataflow"` discriminator (the per-workload `/dataflows` collection implies type by path; `"type"` is only required on the generic Items API path `/v1/workspaces/{ws}/items`)
  - If the agent volunteers a rationale, it correctly notes that `format` is rejected by the Fabric API for Dataflow Gen2

### DFA-15: Refresh-Pattern Correctness — URL, jobType, and Location Capture
- **Prompt:** "Show me the exact CLI commands to trigger a refresh of dataflow `<dfId>` in workspace `<wsId>`, capture the operation Location header from the 202 response, and poll until completion. Provide both bash and PowerShell."
- **Expected:** Recipes that use the current-API endpoint, the correct jobType, and a working Location-header capture — not legacy or fake patterns.
- **Pass criteria** (static correctness):
  - URL is `POST /v1/workspaces/{wsId}/dataflows/{dfId}/jobs/instances?jobType=Refresh` (the documented workload-specific path; NOT the legacy `/jobs/Execute/instances`; NOT `jobType=Pipeline` which returns `400 InvalidJobType`). The cross-type Items path `/v1/workspaces/{wsId}/items/{dfId}/jobs/instances?jobType=Refresh` is functionally equivalent but the per-workload `/dataflows` path is preferred to match the public REST docs.
  - Bash recipe captures the Location header via `curl -D -` (or `curl -i`) plus `az account get-access-token` — does **NOT** use `az rest --include-response-headers` (that flag does not exist)
  - PowerShell recipe captures Location via `Invoke-WebRequest -UseBasicParsing` and `$resp.Headers["Location"]` — does **NOT** use `az rest --include-response-headers`
  - Recipe does **NOT** rely on parsing `/operations/<id>` out of the response **body** (the 202 body is empty; the operation id is only in the Location header)
  - Polling step uses the captured Location URL with `GET` and inspects `status` for the **job-instance** enum (`NotStarted` / `InProgress` / **`Completed`** / `Failed` / `Cancelled`) — terminal-success is `Completed`, NOT `Succeeded` (the latter is the LRO-operation enum returned by `getDefinition` / `updateDefinition`; conflating the two causes infinite polling loops). See `references/authoring-cli-quickref.md § Status Enum Reference`.

### DFA-16: Per-Cell Error Semantics on Type Conversion
- **Prompt:** "I have a text column with values `\"1\"`, `\"abc\"`, `\"3\"`. Write Power Query M that casts it to `Int64.Type` and tells me exactly what is in row index 1 (zero-based) after the cast. Then show me how to replace the bad cells with `null` so downstream readers do not raise."
- **Expected:** Agent loads `references/m-language.md` and correctly distinguishes errored cells from `null`, uses `try <step>{1}[<col>]` to probe (not `is null` checks), and proposes `Table.ReplaceErrorValues(<step>, {{"<col>", null}})`.
- **Pass criteria:**
  - Generated M includes a `try` expression around a cell-level access of row index 1 (e.g., `try <step>{1}[A]`) — step name is the agent's choice.
  - Answer communicates the cell is an **error**, not null — via the `[HasError]` field, a `try` cell-probe, explicit prose, or a recovery whose contract presupposes errored cells (e.g. `Table.ReplaceErrorValues`). The literal `[HasError]` token is sufficient but **not** required — a valid answer built on `Table.ReplaceErrorValues` (which `m-language.md` itself prefers) need never emit it.
  - Recovery snippet uses `Table.ReplaceErrorValues` — NOT `Table.SelectRows(... each [A] <> null)` (would silently keep the errored cell because errored cells serialize as null but are not null).
  - Answer does not claim the value is `null` (which would be the silent-data-loss failure mode).

### DFA-17: `each` Scoping Inside `Table.Group`
- **Prompt:** "Given a table with columns `G` (text) and `V` (Int64), group by `G` and produce two aggregate columns: `SumV` = sum of all V values in the group, and `FirstV` = the V from the first row of the group. Write the M."
- **Expected:** Agent loads `references/m-language.md` and treats the `Table.Group` `each` scope as the sub-table: `SumV` reads the V column as a list, `FirstV` indexes the first row's V cell. `[V]` is shorthand for `_[V]`, so either form is valid (Microsoft's own `Table.Group` docs use the shorthand `each List.Sum([price])`).
- **Pass criteria:**
  - `SumV` aggregator sums the V column — `each List.Sum(_[V])` or the equivalent shorthand `each List.Sum([V])`.
  - `FirstV` aggregator reads the first row's V cell — `each _{0}[V]` (item access needs the explicit `_`; `{0}[V]` is wrong).
  - The M operates on the sub-table's V column (list) and its first row, not on a non-existent scalar field of the grouped table.

### DFA-18: Web Scraping — Prefer `Html.Table`, Reject `Web.Page`
- **Prompt:** "Build a Power Query M expression that scrapes the company name and year-founded values from `https://example.com/companies`. The company entries are repeating `<div class=\"company-info\">` blocks with `.company-name` and `.start-year` child selectors."
- **Expected:** Agent loads `references/connectors.md`, picks `Web.Contents` + `Html.Table` with a `RowSelector` option, and explicitly avoids both `Web.Page` and `Web.BrowserContents` (both runtime-disabled in Dataflow Gen2 cloud refresh).
- **Pass criteria:**
  - Generated M calls `Html.Table(...)` with a `[RowSelector = ".company-info"]` (or equivalent) third argument.
  - Generated M does NOT call `Web.Page` anywhere.
  - Generated M does NOT call `Web.BrowserContents` anywhere.
  - Generated M does NOT use `Text.Split` / `Text.BetweenDelimiters` / regex against the raw HTML to do the initial table extraction (post-extraction text ops on column values are allowed; initial conversion must use `Html.Table`).

### DFA-19: `PowerPlatform.Dataflows` Workspace Navigation
- **Prompt:** "Write a Power Query M expression that uses the `PowerPlatform.Dataflows` connector to read the output of a Dataflow Gen2 named `eval_authoring_basic` in the current workspace. The workspace ID should be passed via a workspace variable rather than hardcoded."
- **Expected:** Agent loads `references/connectors.md` and produces the canonical nav-table drill pattern: `PowerPlatform.Dataflows(null)` → `{[Id="Workspaces"]}[Data]` → filter by workspace ID → filter by dataflow name → `[Data]`.
- **Pass criteria:**
  - Generated M calls `PowerPlatform.Dataflows(null)` (the `null` argument is required — `PowerPlatform.Dataflows()` would be a compile error).
  - First drill step is `{[Id="Workspaces"]}[Data]`.
  - Workspace selection uses a variable reference (e.g., `Variable.Value("currentWorkspaceId")`) — NOT a hardcoded GUID literal.
  - Final step uses `{[dataflowName = "eval_authoring_basic"]}[Data]` (or equivalent index access on the dataflow name field).

## Write Operations (for consistency pairing)

| Write Case | Artifact | Paired Read Skill |
|-----------|----------|-------------------|
| DFA-01 | Dataflow definition | dataflows-consumption-cli |
| DFA-03 | Updated definition | dataflows-consumption-cli |
| DFA-04 | Refresh job | dataflows-consumption-cli |
| DFA-10 | Connection request body | dataflows-consumption-cli |
| DFA-11 | Connection + bound dataflow | dataflows-consumption-cli |
| DFA-12 | Previewed-then-saved mashup | dataflows-consumption-cli |
| DFA-13 | Re-previewed corrected mashup | dataflows-consumption-cli |
| DFA-14 | Create-dataflow request body (static) | n/a — static correctness |
| DFA-15 | Refresh recipe (static) | n/a — static correctness |
| DFA-16 | Per-cell error M (static) | n/a — static correctness |
| DFA-17 | `Table.Group` M (static) | n/a — static correctness |
| DFA-18 | Web/HTML scraping M (static) | n/a — static correctness |
| DFA-19 | `PowerPlatform.Dataflows` nav M (static) | n/a — static correctness |

## Expected Token Range
- 1500–3500 tokens per invocation
