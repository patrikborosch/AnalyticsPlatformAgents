<!-- Mode reference for the `eventhouse-cli` skill. Loaded on demand from `skills/eventhouse-cli/SKILL.md` when the request matches the `consumption` mode. -->

> **SCOPE BOUNDARY — READ-ONLY (mandatory)**
> This mode may run read-only KQL queries and `.show` commands only. Do not
> create, alter, ingest, drop, or otherwise mutate KQL objects. If the request
> requires a write, announce the mode switch and load the authoring reference from
> the `SKILL.md` index before issuing the first management command.

# eventhouse-cli consumption mode — Read-Only KQL Queries via CLI

## Contents

- [Tool Stack](#tool-stack)
- [Connection](#connection)
- [Agentic Exploration](#agentic-exploration)
- [Running Queries](#running-queries)
- [Monitoring](#monitoring)
- [Must / Prefer / Avoid / Troubleshooting](#must--prefer--avoid--troubleshooting)
- [Examples](#examples)
- [Agent Integration Notes](#agent-integration-notes)

> Shared Fabric guidance (auth, pagination, LRO, gotchas) and the other references
> for this skill are indexed in `SKILL.md`. Read them from there, not from here.

---

---

## Tool Stack

| Tool | Purpose | Install |
|---|---|---|
| **az cli** | KQL queries and management commands via Kusto REST API; Fabric control-plane discovery | `winget install Microsoft.AzureCLI` |
| **jq** | JSON processing and output formatting | `winget install jqlang.jq` |

## Connection

### Step 1 — Discover KQL Database Query URI

```bash
# Get workspace ID (if not known)
WS_ID=$(az rest --method GET \
  --url "https://api.fabric.microsoft.com/v1/workspaces" \
  --resource "https://api.fabric.microsoft.com" \
  | jq -r '.value[] | select(.displayName=="MyWorkspace") | .id')

# List KQL Databases and get connection properties
az rest --method GET \
  --url "https://api.fabric.microsoft.com/v1/workspaces/${WS_ID}/kqlDatabases" \
  --resource "https://api.fabric.microsoft.com" \
  | jq '.value[] | {name: .displayName, id: .id, queryUri: .properties.queryServiceUri, dbName: .properties.databaseName}'
```

### Step 2 — Set Connection Variables

```bash
CLUSTER_URI="https://<cluster>.kusto.fabric.microsoft.com"
DB_NAME="MyKqlDatabase"
```

### Step 3 — Verify Connection

> **Important — body file pattern**: KQL queries contain `|` (pipe) characters which break shell
> escaping in both bash and PowerShell. **Always write the JSON body to a temp file** and reference
> it with `--body @<file>`. This is the recommended approach for all `az rest` KQL calls.
> On PowerShell, use `@{db="X";csl="..."} | ConvertTo-Json -Compress | Out-File $env:TEMP\kql_body.json -Encoding utf8NoBOM` then `--body "@$env:TEMP\kql_body.json"`.

```bash
# Write body to temp file (avoids pipe escaping issues)
read -r -d '' CSL <<'KQL' || true
print Message = 'Connected successfully', Cluster = current_cluster_endpoint(), Timestamp = now()
KQL
jq -n --arg db "MyKqlDatabase" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json

az rest --method POST \
  --url "${CLUSTER_URI}/v1/rest/query" \
  --resource "https://kusto.kusto.windows.net" \
  --headers "Content-Type=application/json" \
  --body @/tmp/kql_body.json \
  | jq '.Tables[0].Rows'
```

---

## Agentic Exploration

### "Chat With My Data" — Discovery Sequence

When the user asks to explore or query an Eventhouse without specifying tables:

```kql
Step 1 → .show tables                                    // discover tables
Step 2 → .show table <TABLE> schema as json              // understand columns + types
Step 3 → <TABLE> | take 10                               // see sample data
Step 4 → <TABLE> | summarize count() by bin(Timestamp, 1h) | render timechart  // shape of data
Step 5 → Formulate targeted query based on user's question
```

### Schema-Aware Query Generation

After schema discovery, generate queries using actual column names and types:

```kql
// Example: user asks "show me errors in the last hour"
// After discovering table "AppEvents" with columns: Timestamp, Level, Message, Source
AppEvents
| where Timestamp > ago(1h)
| where Level == "Error"
| summarize ErrorCount = count() by Source, bin(Timestamp, 5m)
| order by ErrorCount desc
```

---

## Running Queries

### Via `az rest`

> **Always use the temp-file pattern** for `--body` — KQL pipes (`|`) break inline shell escaping.

```bash
# Run a KQL query
read -r -d '' CSL <<'KQL' || true
Events | where Timestamp > ago(1h) | count
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json

az rest --method POST \
  --url "${CLUSTER_URI}/v1/rest/query" \
  --resource "https://kusto.kusto.windows.net" \
  --headers "Content-Type=application/json" \
  --body @/tmp/kql_body.json \
  | jq '.Tables[0].Rows'
```

### Output Formatting

```bash
# Pretty-print results as a table with jq
read -r -d '' CSL <<'KQL' || true
.show tables
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json

az rest --method POST \
  --url "${CLUSTER_URI}/v1/rest/query" \
  --resource "https://kusto.kusto.windows.net" \
  --headers "Content-Type=application/json" \
  --body @/tmp/kql_body.json \
  | jq '.Tables[0] | [.Columns[].ColumnName] as $cols | .Rows[] | [$cols, .] | transpose | map({(.[0]): .[1]}) | add'

# Save results to file
read -r -d '' CSL <<'KQL' || true
Events | where Timestamp > ago(1h) | summarize count() by EventType
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json

az rest --method POST \
  --url "${CLUSTER_URI}/v1/rest/query" \
  --resource "https://kusto.kusto.windows.net" \
  --headers "Content-Type=application/json" \
  --body @/tmp/kql_body.json \
  --output-file results.json
```

---

## Monitoring

```kql
// Active queries
.show queries

// Recent commands (last hour)
.show commands
| where StartedOn > ago(1h)
| project StartedOn, CommandType, Text = substring(Text, 0, 80), Duration, State
| order by StartedOn desc

// Ingestion failures (for context when data seems stale)
.show ingestion failures
| where FailedOn > ago(24h)
| summarize count() by ErrorCode
| top 5 by count_
```

---

## Must / Prefer / Avoid / Troubleshooting

### Must

- **Always include time filters** — `where Timestamp > ago(...)` must be present on time-series tables.
- **Discover schema before querying** — run `.show tables` and `.show table T schema as json` first.
- **Use `has` for term search** — indexed and fast; only fall back to `contains` for substring needs.
- **Verify cluster URI** — KQL Database URIs are per-item; always resolve via Fabric REST API.

### Prefer

- **`az rest`** for CLI query sessions; **Fabric KQL MCP server** for agent-integrated workflows.
- **`project` early** to drop unneeded columns before aggregation.
- **`materialize()`** when a sub-expression is used multiple times.
- **`take 100`** for initial exploration; avoid full table scans.
- **`render timechart`** for time-series; `render piechart` for distribution.

### Avoid

- **`contains`** on large tables — full scan, not indexed. Use `has` or `has_cs`.
- **`join`** without filtering both sides first — causes memory explosion.
- **`SELECT *`** equivalent (`project` all columns) on wide tables.
- **Missing `bin()`** in time-series `summarize` — produces one row per unique timestamp.
- **Hardcoded cluster URIs** — always resolve from Fabric REST API or environment variables.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `az rest` auth fails | Run `az login` first; ensure `--resource "https://kusto.kusto.windows.net"` is set |
| Empty results on valid table | Check database context; may need `database("name").table` |
| Query timeout | Add tighter time filter; check `.show queries` for competing queries |
| `Forbidden (403)` | Request `viewer` role on the KQL Database |
| Results truncated | Default limit is 500K rows; add `set truncationmaxrecords = N;` before query |
| KQL pipe `\|` breaks PowerShell or bash | **Never inline KQL in `--body`**. Write JSON to a temp file and use `--body @file.json` (see [Running Queries](#running-queries)) |

---

## Examples

### Example 1: Discover and Query

```bash
# 1. Set connection variables (after discovering URI via Step 1)
CLUSTER_URI="https://<your-cluster>.kusto.fabric.microsoft.com"
DB_NAME="SalesDB"

# 2. Discover tables
read -r -d '' CSL <<'KQL' || true
.show tables
KQL
jq -n --arg db "${DB_NAME}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
az rest --method POST \
  --url "${CLUSTER_URI}/v1/rest/query" \
  --resource "https://kusto.kusto.windows.net" \
  --headers "Content-Type=application/json" \
  --body @/tmp/kql_body.json \
  | jq '.Tables[0].Rows'

# 3. Explore schema
read -r -d '' CSL <<'KQL' || true
.show table Orders schema as json
KQL
jq -n --arg db "${DB_NAME}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
az rest --method POST \
  --url "${CLUSTER_URI}/v1/rest/query" \
  --resource "https://kusto.kusto.windows.net" \
  --headers "Content-Type=application/json" \
  --body @/tmp/kql_body.json \
  | jq '.Tables[0].Rows'

# 4. Sample data
read -r -d '' CSL <<'KQL' || true
Orders | take 10
KQL
jq -n --arg db "${DB_NAME}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
az rest --method POST \
  --url "${CLUSTER_URI}/v1/rest/query" \
  --resource "https://kusto.kusto.windows.net" \
  --headers "Content-Type=application/json" \
  --body @/tmp/kql_body.json \
  | jq '.Tables[0].Rows'
```

```kql
// 5. Analytical query (via az rest --body @file)
Orders
| where OrderDate > ago(30d)
| summarize
    TotalOrders = count(),
    TotalRevenue = sum(Amount)
    by bin(OrderDate, 1d)
| render timechart
```

### Example 2: Cross-Database Query

```kql
// Query across KQL databases in the same Eventhouse
let orders = database("SalesDB").Orders | where OrderDate > ago(7d);
let products = database("CatalogDB").Products;
orders
| join kind=inner (products) on ProductId
| summarize Revenue = sum(Amount) by ProductName
| top 10 by Revenue desc
```

### Example 3: Export Results to File

```bash
# Run query and save results to JSON
read -r -d '' CSL <<'KQL' || true
Events | where Timestamp > ago(1d) | summarize count() by EventType
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json

az rest --method POST \
  --url "${CLUSTER_URI}/v1/rest/query" \
  --resource "https://kusto.kusto.windows.net" \
  --headers "Content-Type=application/json" \
  --body @/tmp/kql_body.json \
  --output-file results.json

# Convert to CSV with jq
cat results.json \
  | jq -r '.Tables[0] | (.Columns | map(.ColumnName)), (.Rows[]) | @csv' > results.csv
```

---

## Agent Integration Notes

- This skill is **read-only** — it does not create, alter, or drop database objects.
- For authoring operations (table management, ingestion, policies), switch to the `eventhouse-cli` authoring mode.
- For cross-workload orchestration (Spark + SQL + KQL), delegate to the **FabricDataEngineer** agent.
- The **Fabric KQL MCP server** (`fabric-kql` in `mcp-setup/mcp-config-template.json`) can be used as an alternative to `az rest` for agent-integrated query execution.
