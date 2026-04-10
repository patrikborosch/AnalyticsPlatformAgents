---
name: powerbi-authoring-cli
description: >
  Create, manage, and deploy Power BI semantic models inside Microsoft Fabric workspaces via `az rest` CLI against Fabric and Power BI REST APIs. Use when the user wants to:
  (1) create a semantic model from TMDL definition files,
  (2) retrieve or download semantic model definitions,
  (3) update a semantic model definition with modified TMDL,
  (4) trigger or manage dataset refresh operations,
  (5) configure data sources, parameters, or permissions,
  (6) deploy semantic models between pipeline stages.
  Covers Fabric Items API (CRUD) and Power BI Datasets API (refresh, data sources, permissions).
  For read-only DAX queries, use `powerbi-consumption-cli`.
  For fine-grained modeling changes, route to `powerbi-modeling-mcp`.
  Triggers: "create semantic model", "upload TMDL", "download semantic model TMDL",
  "refresh dataset", "semantic model deployment pipeline", "dataset permissions",
  "list dataset users", "semantic model authoring".
---

> **Update Check — ONCE PER SESSION (mandatory)**
> The first time this skill is used in a session, run the **check-updates** skill before proceeding.
> - **GitHub Copilot CLI / VS Code**: invoke the `check-updates` skill.
> - **Claude Code / Cowork / Cursor / Windsurf / Codex**: compare local vs remote package.json version.
> - Skip if the check was already performed earlier in this session.

> **CRITICAL NOTES**
> 1. To find the workspace details (including its ID) from workspace name: list all workspaces and, then, use JMESPath filtering
> 2. To find the item details (including its ID) from workspace ID, item type, and item name: list all items of that type in that workspace and, then, use JMESPath filtering

# Power BI Semantic Model Authoring — CLI Skill

## Table of Contents

| Task | Reference | Notes |
|---|---|---|
| Finding Workspaces and Items in Fabric | [COMMON-CLI.md § Finding Workspaces and Items in Fabric](../../common/COMMON-CLI.md#finding-workspaces-and-items-in-fabric) | **Mandatory** — *READ link first* [needed for finding workspace id by its name or item id by its name, item type, and workspace id] |
| Fabric Topology & Key Concepts | [COMMON-CORE.md § Fabric Topology & Key Concepts](../../common/COMMON-CORE.md#fabric-topology--key-concepts) | Hierarchy; Finding Things in Fabric |
| Environment URLs | [COMMON-CORE.md § Environment URLs](../../common/COMMON-CORE.md#environment-urls) | Production (Public Cloud) |
| Tool Selection Rationale | [COMMON-CLI.md § Tool Selection Rationale](../../common/COMMON-CLI.md#tool-selection-rationale) ||
| Authentication Recipes | [COMMON-CLI.md § Authentication Recipes](../../common/COMMON-CLI.md#authentication-recipes) | `az login` flows, environment detection, token acquisition, and debugging |
| Fabric Control-Plane API via `az rest` | [COMMON-CLI.md § Fabric Control-Plane API via `az rest`](../../common/COMMON-CLI.md#fabric-control-plane-api-via-az-rest) | **Always pass `--resource`**; includes workspace/item operations, pagination, and LRO patterns |
| OneLake Data Access via `curl` | [COMMON-CLI.md § OneLake Data Access via `curl`](../../common/COMMON-CLI.md#onelake-data-access-via-curl) | Use `curl` not `az rest` (different token audience) |
| Job Execution (CLI) | [COMMON-CLI.md § Job Execution](../../common/COMMON-CLI.md#job-execution) | Run notebooks/pipelines, refresh semantic models, check/cancel jobs |
| OneLake Shortcuts | [COMMON-CLI.md § OneLake Shortcuts](../../common/COMMON-CLI.md#onelake-shortcuts) | Create a Shortcut; List Shortcuts; Delete a Shortcut |
| Capacity Management (CLI) | [COMMON-CLI.md § Capacity Management](../../common/COMMON-CLI.md#capacity-management) | List Capacities; Assign Workspace to Capacity |
| Composite Recipes | [COMMON-CLI.md § Composite Recipes](../../common/COMMON-CLI.md#composite-recipes) | End-to-end workspace→lakehouse→file, SQL endpoint→query, and notebook execution recipes |
| Gotchas & Troubleshooting (CLI-Specific) | [COMMON-CLI.md § Gotchas & Troubleshooting (CLI-Specific)](../../common/COMMON-CLI.md#gotchas--troubleshooting-cli-specific) | `az rest` audience, shell escaping, token expiry |
| Quick Reference | [COMMON-CLI.md § Quick Reference](../../common/COMMON-CLI.md#quick-reference) | `az rest` Template; Token Audience ↔ CLI Tool Matrix |
| DAX Queries & Metadata Discovery | [powerbi-consumption-cli](../powerbi-consumption-cli/SKILL.md) | Read-only DAX queries; use for post-creation validation |
| Tool Stack | [SKILL.md § Tool Stack](#tool-stack) | `az rest` (primary), `jq` (JSON parsing), `base64` encoding |
| Authentication & API Audiences | [SKILL.md § Authentication & API Audiences](#authentication--api-audiences) | Two audiences: Fabric API vs Power BI Datasets API |
| Must/Prefer/Avoid | [SKILL.md § Must/Prefer/Avoid](#mustpreferavoid) | Guardrails for semantic model authoring |
| SemanticModel Definition & Envelope | [ITEM-DEFINITIONS-CORE.md § SemanticModel](../../common/ITEM-DEFINITIONS-CORE.md#semanticmodel) | TMDL format; required parts, [envelope structure](../../common/ITEM-DEFINITIONS-CORE.md#definition-envelope), [support matrix](../../common/ITEM-DEFINITIONS-CORE.md#per-item-type-definitions) |
| TMDL File Structure & Examples | [SKILL.md § TMDL File Structure](#tmdl-file-structure) | Required parts, [minimal content examples](#minimal-tmdl-content-examples) |
| TMDL CRUD (Create / Get / Update) | [SKILL.md § Create Semantic Model](#create-semantic-model) | [Create](#create-semantic-model) → [Get/Download](#getdownload-definition) → [Update](#update-definition); full lifecycle with LRO |
| Authoring Scope Matrix | [SKILL.md § Authoring Scope Matrix](#authoring-scope-matrix) | What Fabric API supports vs what to avoid |
| Refresh Operations | [SKILL.md § Refresh Operations](#refresh-operations) | Trigger, cancel, history, schedule (Power BI API) |
| Data Sources & Parameters | [SKILL.md § Data Sources & Parameters](#data-sources--parameters) | Get/update data sources and parameters |
| Permissions | [SKILL.md § Permissions](#permissions) | Grant/update dataset user permissions |
| Deployment Pipelines | [SKILL.md § Deployment Pipelines](#deployment-pipelines) | List, get stages, deploy between stages |
| Agentic Workflow | [SKILL.md § Agentic Workflow](#agentic-workflow) | Step-by-step: discover → create → verify → refresh → validate |
| Troubleshooting | [SKILL.md § Troubleshooting](#troubleshooting) | Common errors table: LRO, auth, TMDL encoding, refresh |
| Examples | [SKILL.md § Examples](#examples) | Create model, download definition, refresh, deploy |
| Property-to-API Mapping | [semantic-model-properties-guide.md § Property-to-API Mapping](./references/semantic-model-properties-guide.md#property-to-api-mapping) | Maps each property category to the correct API surface |
| Owner, Storage Mode & Operational Metadata | [semantic-model-properties-guide.md § Owner, Storage Mode](./references/semantic-model-properties-guide.md#owner-storage-mode--operational-metadata) | Power BI Datasets API properties |
| Refresh History Response Properties | [semantic-model-properties-guide.md § Refresh History](./references/semantic-model-properties-guide.md#refresh-history-response-properties) | Refresh detail response fields |
| Data Source Response Properties | [semantic-model-properties-guide.md § Data Sources](./references/semantic-model-properties-guide.md#data-source-response-properties) | Connection and gateway properties |
| DirectQuery / LiveConnection Refresh Schedule | [semantic-model-properties-guide.md § DQ Refresh Schedule](./references/semantic-model-properties-guide.md#directquery--liveconnection-refresh-schedule) | DirectQuery/LiveConnection schedule settings |
| Upstream Dataflow Links | [semantic-model-properties-guide.md § Upstream Dataflows](./references/semantic-model-properties-guide.md#upstream-dataflow-links) | Dataflow dependency properties |
| Per-Table Storage Mode | [semantic-model-properties-guide.md § Per-Table Storage](./references/semantic-model-properties-guide.md#per-table-storage-mode) | Table-level storage mode via TMDL |
| TMDL Syntax Rules | [tmdl-authoring-guide.md § TMDL Syntax Rules](./references/tmdl-authoring-guide.md#tmdl-syntax-rules) | Tab indentation, object declaration, quoting rules |
| Modeling Best Practices | [tmdl-authoring-guide.md § Modeling Best Practices](./references/tmdl-authoring-guide.md#modeling-best-practices) | Naming conventions, column rules, measure & DAX rules, format strings |
| Relationships | [tmdl-authoring-guide.md § Relationships](./references/tmdl-authoring-guide.md#relationships) | Relationship declarations, key rules |
| Hierarchies | [tmdl-authoring-guide.md § Hierarchies](./references/tmdl-authoring-guide.md#hierarchies) | Hierarchy declarations and key rules |
| Direct Lake Guidelines | [tmdl-authoring-guide.md § Direct Lake Guidelines](./references/tmdl-authoring-guide.md#direct-lake-guidelines) | Direct Lake mode configuration and constraints |
| Calculated Tables | [tmdl-authoring-guide.md § Calculated Tables](./references/tmdl-authoring-guide.md#calculated-tables) | DAX-based calculated table definitions |
| Date/Calendar Table | [tmdl-authoring-guide.md § Date/Calendar Table](./references/tmdl-authoring-guide.md#datecalendar-table) | Calendar table setup and marking |
| Parameters | [tmdl-authoring-guide.md § Parameters](./references/tmdl-authoring-guide.md#parameters) | Expression-based parameter declarations |
| Annotations | [tmdl-authoring-guide.md § Annotations](./references/tmdl-authoring-guide.md#annotations) | Model and object-level annotations |
| TMDL File Layout & Core Files | [tmdl-advanced-features-guide.md § File Layout](./references/tmdl-advanced-features-guide.md#file-layout-for-advanced-features) | Directory structure, [database.tmdl](./references/tmdl-advanced-features-guide.md#databasetmdl--full-declaration), [model.tmdl](./references/tmdl-advanced-features-guide.md#modeltmdl--references) |
| Calculation Groups | [tmdl-advanced-features-guide.md § Calculation Groups](./references/tmdl-advanced-features-guide.md#calculation-groups) | Calculation group tables and items |
| Security Roles | [tmdl-advanced-features-guide.md § Security Roles](./references/tmdl-advanced-features-guide.md#security-roles) | RLS/OLS role definitions |
| Security Role Memberships | [SKILL.md § Security Role Memberships](#security-role-memberships) | Add/list/delete users & groups in RLS roles (Power BI API) |
| Translations / Cultures | [tmdl-advanced-features-guide.md § Translations / Cultures](./references/tmdl-advanced-features-guide.md#translations--cultures) | Localization via culture files |
| Perspectives | [tmdl-advanced-features-guide.md § Perspectives](./references/tmdl-advanced-features-guide.md#perspectives) | Perspective definitions for subset views |
| Functions | [tmdl-advanced-features-guide.md § Functions](./references/tmdl-advanced-features-guide.md#functions) | User-defined DAX functions in the model |
| Calendar Objects | [tmdl-advanced-features-guide.md § Calendar Objects](./references/tmdl-advanced-features-guide.md#calendar-objects) | Auto date/time calendar table objects |

---

## Tool Stack

| Tool | Role | Install |
|---|---|---|
| `az` CLI | **Primary**: `az rest` for Fabric and Power BI REST API calls, `az login` for auth. | Pre-installed in most dev environments |
| `jq` | Parse JSON from `az rest` responses | Pre-installed or trivial |
| `base64` (Linux/macOS) / `[Convert]::ToBase64String` (PowerShell) | Encode TMDL file content for definition payloads | Built-in |

> **Agent check** — verify before first operation:
> ```bash
> az version 2>/dev/null || echo "INSTALL: https://learn.microsoft.com/cli/azure/install-azure-cli"
> ```

---

## Authentication & API Audiences

This skill uses **two distinct API audiences**. Using the wrong audience returns a 401.

| API | Audience (`--resource`) | Use For |
|---|---|---|
| Fabric Items API | `https://api.fabric.microsoft.com` | Create/get/update/delete semantic model definitions, list items, LRO polling |
| Power BI Datasets API | `https://analysis.windows.net/powerbi/api` | Refresh, data sources, parameters, permissions, deployment pipelines |

```bash
# Fabric Items API — semantic model definition operations
az rest --method post \
  --resource "https://api.fabric.microsoft.com" \
  --url "https://api.fabric.microsoft.com/v1/workspaces/$WS_ID/semanticModels" \
  ...

# Power BI Datasets API — refresh, data sources, permissions
az rest --method post \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "https://api.powerbi.com/v1.0/myorg/groups/$WS_ID/datasets/$DATASET_ID/refreshes" \
  ...
```

---

## Must/Prefer/Avoid

### MUST DO

- **Read the relevant TMDL reference sections BEFORE generating any TMDL** — at minimum read [TMDL Syntax Rules](./references/tmdl-authoring-guide.md#tmdl-syntax-rules) and [Modeling Best Practices](./references/tmdl-authoring-guide.md#modeling-best-practices). If the task involves relationships, hierarchies, calculation groups, security roles, or translations, also read the corresponding sections in [tmdl-authoring-guide.md](./references/tmdl-authoring-guide.md) and [tmdl-advanced-features-guide.md](./references/tmdl-advanced-features-guide.md). Do not generate TMDL from memory.
- **Always pass `--resource`** to `az rest` — omitting it causes silent auth failures. Use the correct audience per the table above.
- **Always pass `--headers "Content-Type=application/json"`** on POST/PATCH/PUT calls with a `--body` to the Power BI Datasets API — omitting it causes `Unsupported Media Type` errors.
- **Include ALL definition parts** in `updateDefinition` — modified + unmodified. The API replaces the entire definition; omitting parts deletes them.
- **Never include `.platform`** in `updateDefinition` payloads — it is Git integration metadata and causes errors.
- **Poll LRO to completion** — `createItemWithDefinition`, `getDefinition`, and `updateDefinition` return `202 Accepted` with an `Operation-Id` header. Poll until terminal state.
- **Base64-encode TMDL content** — all `payload` values in definition parts must be base64-encoded.
- **Single-quote names with special chars** — names containing spaces, `.`, `=`, `:`, or `'` must be wrapped in single quotes in TMDL.
- **Verify workspace has capacity** before creating a semantic model — call `GET /v1/workspaces/{id}` and check `capacityId`.

### PREFER

- **`createItemWithDefinition`** (single POST) over create-then-update for new semantic models.
- **TMDL format** over TMSL — TMDL is text-based, diff-friendly, and the preferred format for Fabric.
- **Measures before columns** in TMDL table files — follows TMDL convention.
- **Multi-line DAX in triple backticks** — improves readability for complex expressions.
- **Route fine-grained changes to `powerbi-modeling-mcp`** — for adding/modifying individual measures, columns, or relationships, the MCP server is more efficient than full definition round-trips.
- **Get definition before updating** — always retrieve the current definition, modify, then POST back to avoid overwriting concurrent changes.
- **Cross-reference `powerbi-consumption-cli`** for post-creation validation — run DAX queries to verify measures, relationships, and data.

### AVOID

- **`updateDefinition` for small changes** — a full definition round-trip is heavy; route to `powerbi-modeling-mcp` for individual object edits.
- **Report creation** — not supported by this skill. Reports require a separate definition format (PBIR/PBIR-Legacy).
- **`lineageTag` on new objects** — TMDL auto-generates lineage tags; adding them manually causes conflicts.
- **`//` comments in TMDL** — not supported. Use `///` descriptions instead.
- **`description` property in TMDL** — use `///` syntax above the object instead.
- **Hardcoded workspace/item IDs** — resolve dynamically via REST API (see [COMMON-CLI.md § Finding Workspaces and Items in Fabric](../../common/COMMON-CLI.md#finding-workspaces-and-items-in-fabric)).
- **Sending only modified parts in `updateDefinition`** — the API replaces the full definition; missing parts are deleted.

---

## TMDL File Structure

For the full definition envelope and part paths, see [ITEM-DEFINITIONS-CORE.md § SemanticModel](../../common/ITEM-DEFINITIONS-CORE.md#semanticmodel).

Required TMDL parts for `createItemWithDefinition` and `updateDefinition`:

| Part Path | Content | Required |
|---|---|---|
| `definition.pbism` | Semantic model connection settings | Yes |
| `definition/database.tmdl` | Database properties (compatibility level) | Yes |
| `definition/model.tmdl` | Model properties (culture, default summarization) | Yes |
| `definition/tables/<TableName>.tmdl` | Per-table: columns, measures, partitions | Yes (≥1) |

> **Critical**: `updateDefinition` must include ALL parts — modified and unmodified. The API replaces the entire definition. Never include `.platform` in update payloads.

For TMDL syntax rules, naming conventions, and modeling best practices, see [tmdl-authoring-guide.md](./references/tmdl-authoring-guide.md).

---

## Minimal TMDL Content Examples

### definition.pbism

```json
{
    "version": "4.2",
    "settings": {
        "qnaEnabled": true
    }
}
```

### database.tmdl

```tmdl
database
	compatibilityLevel: 1702
	compatibilityMode: powerBI
```

### model.tmdl

```tmdl
model Model
	culture: en-US
	defaultPowerBIDataSourceVersion: powerBI_V3
	discourageImplicitMeasures
```

> **Note**: `defaultPowerBIDataSourceVersion: powerBI_V3` is required for Import-mode models. Without it, the API returns `Import from JSON supported for V3 models only`.

### Import-Mode Table

```tmdl
table Customer

	/// Total number of customers
	measure '# Customers' = COUNTROWS(Customer)
		formatString: #,##0

	column CustomerId
		dataType: int64
		isHidden
		isKey
		summarizeBy: none
		sourceColumn: CustomerId

	column 'Customer Name'
		dataType: string
		sourceColumn: CustomerName

	partition Customer = m
		mode: import
		source =
			let
				Source = Sql.Database(#"Server", #"Database"),
				Customer = Source{[Schema="dbo", Item="Customer"]}[Data]
			in
				Customer
```

### Direct Lake Table

````tmdl
expression DL_Lakehouse =
	let
		Source = AzureStorage.DataLake("https://onelake.dfs.fabric.microsoft.com/<WorkspaceId>/<LakehouseId>", [HierarchicalNavigation=true])
	in
		Source

table Sales

	/// Total revenue
	measure 'Total Sales' = ```
			SUMX(
				Sales,
				Sales[Quantity] * Sales[UnitPrice]
			)
			```
		formatString: \$#,##0.00

	column SalesKey
		dataType: int64
		isHidden
		isKey
		summarizeBy: none
		sourceColumn: sales_key

	column Quantity
		dataType: int64
		sourceColumn: quantity

	column UnitPrice
		dataType: decimal
		summarizeBy: none
		sourceColumn: unit_price

	partition Sales = entity
		mode: directLake
		source
			entityName: Sales
			schemaName: dbo
			expressionSource: DL_Lakehouse
````

---

## Create Semantic Model

Full lifecycle: author TMDL → base64-encode → construct payload → POST → poll LRO.

Per [COMMON-CLI.md § Item CRUD Operations](../../common/COMMON-CLI.md#item-crud-operations) and [ITEM-DEFINITIONS-CORE.md § Definition Envelope](../../common/ITEM-DEFINITIONS-CORE.md#definition-envelope):

```bash
WS_ID="<workspaceId>"

# 1. Base64-encode each TMDL file
PBISM=$(base64 -w 0 < definition.pbism)
DB=$(base64 -w 0 < definition/database.tmdl)
MODEL=$(base64 -w 0 < definition/model.tmdl)
TABLE=$(base64 -w 0 < definition/tables/Customer.tmdl)

# 2. Construct payload and create — use --verbose to capture HTTP status and LRO headers
cat > /tmp/body.json << EOF
{
  "displayName": "MySalesModel",
  "definition": {
    "format": "TMDL",
    "parts": [
      {"path": "definition.pbism", "payload": "$PBISM", "payloadType": "InlineBase64"},
      {"path": "definition/database.tmdl", "payload": "$DB", "payloadType": "InlineBase64"},
      {"path": "definition/model.tmdl", "payload": "$MODEL", "payloadType": "InlineBase64"},
      {"path": "definition/tables/Customer.tmdl", "payload": "$TABLE", "payloadType": "InlineBase64"}
    ]
  }
}
EOF
az rest --method post --verbose \
  --resource "https://api.fabric.microsoft.com" \
  --url "https://api.fabric.microsoft.com/v1/workspaces/$WS_ID/semanticModels" \
  --headers "Content-Type=application/json" \
  --body @/tmp/body.json
```

> **PowerShell** — use `[Convert]::ToBase64String([System.IO.File]::ReadAllBytes("file"))` instead of `base64 -w 0`.

If the response is `202 Accepted`, poll using the LRO pattern from [COMMON-CLI.md § Long-Running Operations](../../common/COMMON-CLI.md#long-running-operations-lro-pattern).

---

## Get/Download Definition

Retrieve TMDL definition for backup, migration, or inspection. `getDefinition` is a **POST** (not GET).

```bash
WS_ID="<workspaceId>"
MODEL_ID="<semanticModelId>"

# 1. Request definition — may return 200 (inline) or 202 (LRO)
RESPONSE=$(az rest --method post --verbose \
  --resource "https://api.fabric.microsoft.com" \
  --url "https://api.fabric.microsoft.com/v1/workspaces/$WS_ID/semanticModels/$MODEL_ID/getDefinition?format=TMDL" \
  --body '{}' \
  --output json 2>/dev/null)

# 2. If 202, poll the Location header URL until Succeeded, then GET /result

# 3. Decode each part
echo "$RESPONSE" | jq -r '.definition.parts[] | .path + " " + .payload' | \
while read -r path payload; do
  mkdir -p "$(dirname "$path")"
  echo "$payload" | base64 -d > "$path"
done
```

---

## Update Definition

> **Critical rules**: Must include ALL parts (modified + unmodified). Never include `.platform`. The API replaces the entire definition — omitted parts are deleted.

```bash
WS_ID="<workspaceId>"
MODEL_ID="<semanticModelId>"

# 1. Get current definition (see Get/Download Definition above)
# 2. Modify the relevant TMDL files
# 3. Re-encode ALL parts and POST

cat > /tmp/body.json << EOF
{
  "definition": {
    "format": "TMDL",
    "parts": [
      {"path": "definition.pbism", "payload": "$PBISM", "payloadType": "InlineBase64"},
      {"path": "definition/database.tmdl", "payload": "$DB", "payloadType": "InlineBase64"},
      {"path": "definition/model.tmdl", "payload": "$MODEL", "payloadType": "InlineBase64"},
      {"path": "definition/tables/Customer.tmdl", "payload": "$TABLE", "payloadType": "InlineBase64"}
    ]
  }
}
EOF
az rest --method post \
  --resource "https://api.fabric.microsoft.com" \
  --url "https://api.fabric.microsoft.com/v1/workspaces/$WS_ID/semanticModels/$MODEL_ID/updateDefinition" \
  --body @/tmp/body.json
```

Use `?updateMetadata=true` query parameter only when the `.platform` file must be included to update display name or description via definition.

---

## Authoring Scope Matrix

| Operation | Supported | Method |
|---|---|---|
| Create semantic model with TMDL | ✅ | `POST /v1/workspaces/{id}/semanticModels` with definition |
| Get/download TMDL definition | ✅ | `POST .../semanticModels/{id}/getDefinition?format=TMDL` |
| Update full TMDL definition | ✅ | `POST .../semanticModels/{id}/updateDefinition` |
| Delete semantic model | ✅ | `DELETE /v1/workspaces/{id}/semanticModels/{id}` |
| Refresh dataset | ✅ | Power BI Datasets API (Phase 4) |
| Add/modify single measure or column | ⚠️ Route to `powerbi-modeling-mcp` | Full definition round-trip is inefficient |
| Create reports | ❌ | Not in scope — separate definition format (PBIR) |

---

## Refresh Operations

All refresh operations use the **Power BI Datasets API** audience (`https://analysis.windows.net/powerbi/api`).

```bash
WS_ID="<workspaceId>"
DATASET_ID="<semanticModelId>"
PBI="https://api.powerbi.com/v1.0/myorg"

# Trigger full refresh
cat > /tmp/body.json << 'EOF'
{"notifyOption": "NoNotification"}
EOF
az rest --method post --verbose \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/refreshes" \
  --headers "Content-Type=application/json" \
  --body @/tmp/body.json

# Get refresh history (latest first)
az rest --method get \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/refreshes?\$top=5"

# Cancel an in-progress refresh
az rest --method delete \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/refreshes/<refreshId>"

# Get refresh schedule
az rest --method get \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/refreshSchedule"

# Update refresh schedule
cat > /tmp/body.json << 'EOF'
{
  "value": {
    "enabled": true,
    "days": ["Monday", "Wednesday", "Friday"],
    "times": ["02:00", "14:00"],
    "localTimeZoneId": "UTC"
  }
}
EOF
az rest --method patch \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/refreshSchedule" \
  --headers "Content-Type=application/json" \
  --body @/tmp/body.json
```

---

## Data Sources & Parameters

```bash
# Get data sources for a dataset
az rest --method get \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/datasources"

# Get parameters
az rest --method get \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/parameters"

# Update parameters
cat > /tmp/body.json << 'EOF'
{
  "updateDetails": [
    {"name": "Server", "newValue": "newserver.database.windows.net"},
    {"name": "Database", "newValue": "ProductionDB"}
  ]
}
EOF
az rest --method post \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/Default.UpdateParameters" \
  --headers "Content-Type=application/json" \
  --body @/tmp/body.json
```

> After updating parameters or data source credentials, trigger a refresh for changes to take effect.

---

## Permissions

```bash
# List dataset users
az rest --method get \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/users"

# Grant dataset permissions to a user
cat > /tmp/body.json << 'EOF'
{
  "identifier": "user@contoso.com",
  "principalType": "User",
  "datasetUserAccessRight": "Read"
}
EOF
az rest --method post \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/users" \
  --headers "Content-Type=application/json" \
  --body @/tmp/body.json

# Update existing user permissions
cat > /tmp/body.json << 'EOF'
{
  "identifier": "user@contoso.com",
  "principalType": "User",
  "datasetUserAccessRight": "ReadReshare"
}
EOF
az rest --method put \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/users" \
  --headers "Content-Type=application/json" \
  --body @/tmp/body.json
```

Permission levels: `Read`, `ReadReshare`, `ReadExplore`, `ReadReshareExplore`.

---

## Security Role Memberships

After defining RLS/OLS roles in TMDL (see [Security Roles](./references/tmdl-advanced-features-guide.md#security-roles)), use the **Power BI Datasets API** to assign users and groups to those roles.

```bash
PBI="https://api.powerbi.com/v1.0/myorg"

# List members of a security role
az rest --method get \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/users" \
  | jq '[.value[] | select(.datasetUserAccessRight == "Read" and .roles != null)]'

# Add a user to a security role
cat > /tmp/body.json << 'EOF'
{
  "identifier": "user@contoso.com",
  "principalType": "User",
  "datasetUserAccessRight": "Read",
  "roles": ["SalesRegion"]
}
EOF
az rest --method post \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/users" \
  --headers "Content-Type=application/json" \
  --body @/tmp/body.json

# Add a security group to a role
cat > /tmp/body.json << 'EOF'
{
  "identifier": "<group-object-id>",
  "principalType": "Group",
  "datasetUserAccessRight": "Read",
  "roles": ["SalesRegion"]
}
EOF
az rest --method post \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/users" \
  --headers "Content-Type=application/json" \
  --body @/tmp/body.json

# Update role membership (e.g., move user to a different role)
cat > /tmp/body.json << 'EOF'
{
  "identifier": "user@contoso.com",
  "principalType": "User",
  "datasetUserAccessRight": "Read",
  "roles": ["EuropeOnly"]
}
EOF
az rest --method put \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/users" \
  --headers "Content-Type=application/json" \
  --body @/tmp/body.json
```

> The `roles` array accepts one or more role names that must match roles defined in the semantic model's TMDL. The user/group must also have at least `Read` permission on the dataset. `principalType` can be `User`, `Group`, or `App`.

---

## Deployment Pipelines

Deployment pipelines use the **Fabric API** audience (`https://api.fabric.microsoft.com`).

```bash
FABRIC="https://api.fabric.microsoft.com/v1"

# List deployment pipelines
az rest --method get \
  --resource "https://api.fabric.microsoft.com" \
  --url "$FABRIC/deploymentPipelines"

# Get pipeline stages
az rest --method get \
  --resource "https://api.fabric.microsoft.com" \
  --url "$FABRIC/deploymentPipelines/<pipelineId>/stages"

# Deploy from one stage to the next (e.g., Dev → Test)
cat > /tmp/body.json << 'EOF'
{
  "sourceStageOrder": 0,
  "targetStageOrder": 1,
  "items": [
    {
      "sourceItemId": "<semanticModelId>",
      "itemType": "SemanticModel"
    }
  ],
  "options": {
    "allowCreateArtifact": true,
    "allowOverwriteArtifact": true
  }
}
EOF
az rest --method post \
  --resource "https://api.fabric.microsoft.com" \
  --url "$FABRIC/deploymentPipelines/<pipelineId>/deploy" \
  --headers "Content-Type=application/json" \
  --body @/tmp/body.json
```

> Omit the `items` array to deploy all items in the stage. The deploy call returns `202 Accepted` — poll using the [LRO pattern](../../common/COMMON-CLI.md#long-running-operations-lro-pattern).

---

## Agentic Workflow

### Tool Selection Priority

1. **`powerbi-modeling-mcp` available** → use MCP tools for fine-grained object changes (measures, columns, relationships)
2. **MCP unavailable, TMDL files available** → edit TMDL files directly, deploy via `az rest` updateDefinition
3. **MCP unavailable, workspace only** → use this skill: getDefinition → edit TMDL → updateDefinition

### Workflow Steps

1. **Discover workspace** → list workspaces, find target by name (see [COMMON-CLI.md § Finding Workspaces and Items](../../common/COMMON-CLI.md#finding-workspaces-and-items-in-fabric))
2. **List semantic models** → `GET /v1/workspaces/{id}/semanticModels` to find existing models or confirm name availability
3. **Analyze source schema** → inspect source tables/columns via SQL, DAX, or Lakehouse metadata to inform star schema design
4. **Design star schema** → identify fact and dimension tables, define relationship keys, plan measures
5. **Author TMDL files** → create `definition.pbism`, `database.tmdl`, `model.tmdl`, and table files per [Minimal TMDL Content Examples](#minimal-tmdl-content-examples) and [tmdl-authoring-guide.md](./references/tmdl-authoring-guide.md)
6. **Create relationships** → define in table TMDL files **before** creating measures that depend on them
7. **Create measures** → add explicit measures with `formatString` for all aggregatable values
8. **Deploy** → base64-encode all parts → POST createItemWithDefinition (see [Create Semantic Model](#create-semantic-model))
9. **Verify** → run validation checks (see below)
10. **Refresh** → trigger dataset refresh via [Refresh Operations](#refresh-operations)
11. **Validate with DAX** → use [powerbi-consumption-cli](../powerbi-consumption-cli/SKILL.md) to run DAX queries against the deployed model

### Post-Creation Validation

- **TMDL structure** — verify all required parts are present (definition.pbism, database.tmdl, model.tmdl, ≥1 table)
- **Test measures** — run `EVALUATE { [Measure Name] }` for each measure via DAX
- **Verify relationships** — confirm cardinality, cross-filter direction, matching `dataType` on both sides
- **Verify columns** — confirm `sourceColumn` mappings and `dataType` match source schema
- **Check for duplicates** — no duplicate measure names or orphan objects

---

## Troubleshooting

> **Early-abort rule**: If **both** `getDefinition` returns `404 EntityNotFound` (on an item you can list/GET) **and** the Power BI refresh API returns `403 Forbidden` with `"identity None"`, **stop retrying immediately** — the user almost certainly has only Viewer role on the workspace. Verify by calling `GET /v1/workspaces/{id}/roleAssignments`; if that also returns `403 InsufficientWorkspaceRole`, confirm to the user they need Contributor or higher role. Do **not** retry with different URL formats, endpoints, or parameters — the issue is permissions, not API usage.

| Symptom | Cause | Fix |
|---|---|---|
| `403 Forbidden` with `"identity None"` on Power BI API | User has Viewer role — refresh, data sources, and permissions APIs require Contributor+ | **Stop immediately.** Ask user to request Contributor/Member/Admin role on the workspace |
| `404 EntityNotFound` on getDefinition but item exists in list | Insufficient permissions masquerading as 404 — getDefinition requires Contributor+ | Check workspace role first; do not retry with different URL formats |
| `403 InsufficientWorkspaceRole` on roleAssignments | User is Viewer on the workspace | Confirms Viewer role — all authoring and most read operations are blocked |
| `401 Unauthorized` on Fabric API | Wrong or missing `--resource` | Use `--resource "https://api.fabric.microsoft.com"` |
| `401 Unauthorized` on Power BI API | Wrong audience | Use `--resource "https://analysis.windows.net/powerbi/api"` |
| `411 Length Required` on getDefinition | Missing request body | Pass `--body '{}'` — getDefinition is a POST |
| LRO poll never completes | Token expired during long operation | Re-acquire token in poll loop; increase Retry-After interval |
| `202 Accepted` but no result | Didn't follow LRO to completion | Poll `Location` header URL until `Succeeded`, then GET `/result` |
| TMDL validation error on create/update | Syntax error in TMDL content | Check TMDL rules in [tmdl-authoring-guide.md](./references/tmdl-authoring-guide.md); validate before encoding |
| Parts missing after updateDefinition | Only modified parts were sent | Must include ALL parts (modified + unmodified) in every update |
| Error including `.platform` in update | `.platform` not accepted by default | Remove `.platform` from parts, or use `?updateMetadata=true` |
| Base64 decode produces garbled content | Wrong encoding or line wrapping | Use `base64 -w 0` (no line wrap) or `[Convert]::ToBase64String()` |
| Refresh fails with data source error | Credentials expired or parameters wrong | Check data sources and parameters; update credentials if needed |
| Deployment pipeline fails | Workspace not assigned to stage | Assign workspace to pipeline stage before deploying |
| `lineageTag` conflict on new objects | Manually added `lineageTag` | Remove `lineageTag` from new objects — it is auto-generated |
| DAX error testing measures | Measure name case mismatch | DAX measure names are case-sensitive; match exactly |
| Attempting `INFO.ROLES()` / `INFO.ROLEMEMBERSHIPS()` via DAX to retrieve role members | DAX `INFO` functions do not reliably return role membership data and may return empty or incomplete results | Use the **Power BI REST API** instead: `GET /v1.0/myorg/groups/{workspaceId}/datasets/{datasetId}/users` and filter by `roles` field (see [Security Role Memberships](#security-role-memberships)) |

---

## Examples

### Create a Semantic Model from TMDL

```bash
WS_ID="<workspaceId>"

# Encode all TMDL files
PBISM=$(base64 -w 0 < definition.pbism)
DB=$(base64 -w 0 < definition/database.tmdl)
MODEL=$(base64 -w 0 < definition/model.tmdl)
CUSTOMER=$(base64 -w 0 < definition/tables/Customer.tmdl)
SALES=$(base64 -w 0 < definition/tables/Sales.tmdl)

cat > /tmp/body.json << EOF
{
  "displayName": "SalesModel",
  "definition": {
    "parts": [
      {"path": "definition.pbism", "payload": "$PBISM", "payloadType": "InlineBase64"},
      {"path": "definition/database.tmdl", "payload": "$DB", "payloadType": "InlineBase64"},
      {"path": "definition/model.tmdl", "payload": "$MODEL", "payloadType": "InlineBase64"},
      {"path": "definition/tables/Customer.tmdl", "payload": "$CUSTOMER", "payloadType": "InlineBase64"},
      {"path": "definition/tables/Sales.tmdl", "payload": "$SALES", "payloadType": "InlineBase64"}
    ]
  }
}
EOF
az rest --method post --verbose \
  --resource "https://api.fabric.microsoft.com" \
  --url "https://api.fabric.microsoft.com/v1/workspaces/$WS_ID/semanticModels" \
  --headers "Content-Type=application/json" \
  --body @/tmp/body.json
```

### Download a Semantic Model Definition

```bash
WS_ID="<workspaceId>"
MODEL_ID="<semanticModelId>"

# Get definition (may return 202 — follow LRO)
RESULT=$(az rest --method post \
  --resource "https://api.fabric.microsoft.com" \
  --url "https://api.fabric.microsoft.com/v1/workspaces/$WS_ID/semanticModels/$MODEL_ID/getDefinition?format=TMDL" \
  --body '{}' --output json)

# Decode and save all parts
echo "$RESULT" | jq -r '.definition.parts[] | .path + "\t" + .payload' | \
while IFS=$'\t' read -r path payload; do
  mkdir -p "$(dirname "$path")"
  echo "$payload" | base64 -d > "$path"
  echo "Saved: $path"
done
```

### Trigger a Refresh and Check Status

```bash
WS_ID="<workspaceId>"
DATASET_ID="<semanticModelId>"
PBI="https://api.powerbi.com/v1.0/myorg"

# Trigger refresh
cat > /tmp/body.json << 'EOF'
{"type": "Full"}
EOF
az rest --method post \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/refreshes" \
  --body @/tmp/body.json

# Check latest refresh status
az rest --method get \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$DATASET_ID/refreshes?\$top=1"
```

### Deploy to Production via Pipeline

```bash
FABRIC="https://api.fabric.microsoft.com/v1"
PIPELINE_ID="<pipelineId>"

# Deploy from Test (stage 1) to Production (stage 2)
cat > /tmp/body.json << 'EOF'
{
  "sourceStageOrder": 1,
  "targetStageOrder": 2,
  "items": [
    {"sourceItemId": "<semanticModelId>", "itemType": "SemanticModel"}
  ],
  "options": {
    "allowCreateArtifact": true,
    "allowOverwriteArtifact": true
  }
}
EOF
az rest --method post \
  --resource "https://api.fabric.microsoft.com" \
  --url "$FABRIC/deploymentPipelines/$PIPELINE_ID/deploy" \
  --body @/tmp/body.json
```
