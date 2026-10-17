<!-- Mode reference for the `eventhouse-cli` skill. Loaded on demand from `skills/eventhouse-cli/SKILL.md` when the request matches the `authoring` mode. -->

> **PRE-MUTATION REQUIREMENTS GATE (mandatory)**
> Before any mutation, confirm the request identifies the target KQL database
> and the intended table, schema, ingestion, policy, function, or materialized
> view change. If the request is generic, such as "set up my Eventhouse", ask a
> clarifying question and stop before mutation. Do not infer a schema or apply
> management commands from unrelated workspace items.

# eventhouse-cli authoring mode — Eventhouse Authoring and Management via CLI

## Contents

- [Tool Stack](#tool-stack)
- [Connection](#connection)
- [Authoring Scope](#authoring-scope)
- [Execute KQL Command](#execute-kql-command)
- [Table Management via CLI](#table-management-via-cli)
- [Data Ingestion via CLI](#data-ingestion-via-cli)
- [Policies via CLI](#policies-via-cli)
- [Advanced Operations](#advanced-operations)
- [Must / Prefer / Avoid / Troubleshooting](#must--prefer--avoid--troubleshooting)
- [Agentic Workflows](#agentic-workflows)
- [Examples](#examples)
- [Agent Integration Notes](#agent-integration-notes)

> Shared Fabric guidance (auth, pagination, LRO, gotchas) and the other references
> for this skill are indexed in `SKILL.md`. Read them from there, not from here.

---

---

## Tool Stack

| Tool | Purpose | Install |
|---|---|---|
| **az cli** | KQL management commands via Kusto REST API; Fabric control-plane discovery | `winget install Microsoft.AzureCLI` |
| **jq** | JSON processing and output formatting | `winget install jqlang.jq` |

---

## Connection

Discovery is identical to consumption mode. Authoring requires elevated roles:

```bash
# Discover KQL Database query URI
WS_ID="<workspace-id>"
az rest --method GET \
  --url "https://api.fabric.microsoft.com/v1/workspaces/${WS_ID}/kqlDatabases" \
  --resource "https://api.fabric.microsoft.com" \
  | jq '.value[] | {name: .displayName, queryUri: .properties.queryServiceUri}'

# Set connection variables
CLUSTER_URI="https://<cluster>.kusto.fabric.microsoft.com"
DB_NAME="MyDatabase"

# Verify admin access
# Unquoted heredoc: the database name is interpolated into the command text itself.
read -r -d '' CSL <<KQL || true
.show database ${DB_NAME} principals | where Role == 'Admin'
KQL
jq -n --arg db "${DB_NAME}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
az rest --method POST \
  --url "${CLUSTER_URI}/v1/rest/mgmt" \
  --resource "https://kusto.kusto.windows.net" \
  --headers "Content-Type=application/json" \
  --body @/tmp/kql_body.json \
  | jq '.Tables[0].Rows'
```

---

## Authoring Scope

| Operation | Command Pattern |
|---|---|
| Create table | `.create-merge table T (cols)` |
| Add column | `.alter-merge table T (NewCol: type)` |
| Drop table | `.drop table T ifexists` |
| Ingest data | `.ingest into table T (...)` |
| Set retention | `.alter table T policy retention ...` |
| Set caching | `.alter table T policy caching hot = Nd` |
| Create function | `.create-or-alter function F() { ... }` |
| Create materialized view | `.create materialized-view MV on table T { ... }` |
| Create update policy | `.alter table T policy update ...` |
| Create data mapping | `.create table T ingestion csv mapping ...` |

---

## Execute KQL Command

All KQL management commands in this skill follow the same `az rest` pattern. After setting `CLUSTER_URI` and `DB`:

```bash
# A quoted heredoc keeps the command literal -- no shell expansion, and no
# backslash-escaping even for policies and mappings that contain their own JSON.
read -r -d '' CSL <<'KQL' || true
<KQL management command>
KQL

# jq JSON-escapes the command; ${DB} still expands because it is passed as an argument.
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json

az rest --method POST \
  --url "${CLUSTER_URI}/v1/rest/mgmt" \
  --resource "https://kusto.kusto.windows.net" \
  --headers "Content-Type=application/json" \
  --body @/tmp/kql_body.json \
  | jq '.Tables[0].Rows'
```

> **Never build the body by interpolating the command into a JSON string.** A KQL command that contains double quotes -- any ingestion mapping or policy document -- produces invalid JSON that `az rest` rejects. `jq -n --arg` handles the escaping, so no command needs special treatment and no database name needs hardcoding.

> **Endpoint** — management commands go to `/v1/rest/mgmt`. That includes anything starting with `.`, such as `.show tables details | project ...`, even with a trailing pipe. Use `/v1/rest/query` only for expressions like `Events | count`.

> **PowerShell equivalent** — `@{db=$Database;csl=$Command} | ConvertTo-Json -Compress` gives the same escaping guarantee. Check `$LASTEXITCODE` after every `az rest` call; a native-command failure does not stop PowerShell on its own. Ready-to-run scripts live in `scripts/`.

---

## Table Management via CLI

### Create Table (Idempotent)

```bash
read -r -d '' CSL <<'KQL' || true
.create-merge table Events (Timestamp: datetime, EventType: string, UserId: string, Properties: dynamic, Duration: real)
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute `/tmp/kql_body.json` — see [Execute KQL Command](#execute-kql-command)

### Add Column

```bash
read -r -d '' CSL <<'KQL' || true
.alter-merge table Events (Region: string)
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute `/tmp/kql_body.json` — see [Execute KQL Command](#execute-kql-command)

### Drop Table

```bash
read -r -d '' CSL <<'KQL' || true
.drop table Events ifexists
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute `/tmp/kql_body.json` — see [Execute KQL Command](#execute-kql-command)

---

## Data Ingestion via CLI

### Inline Ingestion (Testing)

```bash
# Real newlines after `<|`, not a literal \n: the heredoc keeps the text verbatim, so a
# backslash-n would reach the server as two characters rather than a row separator.
read -r -d '' CSL <<'KQL' || true
.ingest inline into table Events <|
2025-01-15T10:00:00Z,Login,user1,{},0.5
2025-01-15T10:01:00Z,Click,user2,{},0.2
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute `/tmp/kql_body.json` — see [Execute KQL Command](#execute-kql-command)

### Ingest from Storage

```bash
read -r -d '' CSL <<'KQL' || true
.ingest into table Events (h'https://mystorage.blob.core.windows.net/data/events.csv.gz;impersonate') with (format='csv', ingestionMappingReference='EventsCsvMapping', ignoreFirstRecord=true)
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute `/tmp/kql_body.json` — see [Execute KQL Command](#execute-kql-command)

### Ingest from OneLake

```bash
read -r -d '' CSL <<'KQL' || true
.ingest into table Events (h'abfss://workspace@onelake.dfs.fabric.microsoft.com/lakehouse.Lakehouse/Files/events.parquet;impersonate') with (format='parquet')
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute `/tmp/kql_body.json` — see [Execute KQL Command](#execute-kql-command)

### Set-or-Append from Query

```bash
read -r -d '' CSL <<'KQL' || true
.set-or-append CleanEvents <| RawEvents | where IsValid == true | project Timestamp, EventType, UserId
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute `/tmp/kql_body.json` — see [Execute KQL Command](#execute-kql-command)

---

## Policies via CLI

### Retention

```bash
# Set 365-day retention
read -r -d '' CSL <<'KQL' || true
.alter table Events policy retention '{"SoftDeletePeriod":"365.00:00:00","Recoverability":"Enabled"}'
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute `/tmp/kql_body.json` — see [Execute KQL Command](#execute-kql-command)

### Caching (Hot Cache)

```bash
# Keep last 30 days in hot cache
read -r -d '' CSL <<'KQL' || true
.alter table Events policy caching hot = 30d
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute `/tmp/kql_body.json` — see [Execute KQL Command](#execute-kql-command)

### Streaming Ingestion

```bash
read -r -d '' CSL <<'KQL' || true
.alter table Events policy streamingingestion enable
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute `/tmp/kql_body.json` — see [Execute KQL Command](#execute-kql-command)

---

## Advanced Operations

Materialized views, stored functions, update policies, schema evolution and
authoring-operation monitoring are out of scope for this file. `SKILL.md` routes to the
reference that covers them.

---

## Must / Prefer / Avoid / Troubleshooting

### Must

- **Clarify before acting on ambiguous prompts** — if the request does not specify a target table, operation type, or schema (e.g. "set up my Eventhouse", "configure my database"), ask the user what they want to do. Never infer intent and apply management commands autonomously. Irreversible side-effects (policy changes, schema mutations, data ingestion) require explicit user intent.
- **Use idempotent commands** — `.create-merge table`, `.create-or-alter function`, `.create table ifnotexists`.
- **Verify permissions** before authoring — must have `Admin` or `Ingestor` role.
- **Test update policies** by running the function independently before attaching.
- **Include `impersonate`** in storage URIs when ingesting from OneLake or Blob Storage.

### Prefer

- **`az rest` with loop** for deploying multi-command schema files.
- **Fabric KQL MCP server** for agent-integrated ingestion and management workflows.
- **`.create-merge table`** over `.create table` for safe schema evolution.
- **Materialized views** over repeated expensive aggregation queries.
- **Script-based CI/CD** — export schema with `.show database DB schema as csl script`, store in git.

### Avoid

- **`.drop table`** without `ifexists` — fails on missing tables.
- **`.alter table`** to add columns — use `.alter-merge table` instead (additive only).
- **Ingestion without mappings** for CSV/JSON — column order or field names may not match.
- **Hardcoded storage URIs** — parameterise in scripts.
- **Disabling materialized views** without understanding the re-backfill cost.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `.create table` fails "already exists" | Use `.create-merge table` or `.create table ifnotexists` |
| Ingestion succeeds but table empty | Check data mappings: `.show table T ingestion csv mappings` |
| Update policy not firing | Verify function runs standalone; check `.show table T policy update` |
| `Forbidden (403)` on management commands | Request `admin` or `ingestor` database role |
| Materialized view stuck | Check `.show materialized-view MV statistics`; may need `.disable`/`.enable` |
| OneLake ingest auth error | Add `;impersonate` to `abfss://` URI |

---

## Agentic Workflows

### Exploration Before Authoring

Always check for explicit intent before doing anything:

```text
Step 0 → Is the request specific? Does it name a table, operation, and/or schema?
         → NO  → Ask: "What would you like to set up? Options: create tables,
                  configure policies, set up ingestion mappings, create materialized views."
                  STOP — do not proceed until user specifies.
         → YES → Continue to Step 1.
Step 1 → .show tables details                        // what exists?
Step 2 → .show table <TABLE> schema as json          // current columns
Step 3 → .show table <TABLE> policy retention        // current policies
Step 4 → Plan changes (create-merge, alter, etc.)
Step 5 → Execute changes
Step 6 → Verify: .show table <TABLE> schema as json  // confirm changes
```

### Script Generation Workflow

```text
Step 1 → Understand requirements from user
Step 2 → Generate KQL management commands
Step 3 → Save to .kql file
Step 4 → Deploy via az rest (one command at a time)
Step 5 → Verify deployed state matches intent
```

---

## Examples

### Example 1: Create Table with Policies and Mapping

```bash
# Create table
read -r -d '' CSL <<'KQL' || true
.create-merge table SensorData (Timestamp: datetime, DeviceId: string, Temperature: real, Humidity: real, Location: dynamic)
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute `/tmp/kql_body.json` — see [Execute KQL Command](#execute-kql-command)

```bash
# Set retention
read -r -d '' CSL <<'KQL' || true
.alter table SensorData policy retention '{"SoftDeletePeriod":"90.00:00:00","Recoverability":"Enabled"}'
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute `/tmp/kql_body.json` — see [Execute KQL Command](#execute-kql-command)

```bash
# Set caching
read -r -d '' CSL <<'KQL' || true
.alter table SensorData policy caching hot = 7d
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute `/tmp/kql_body.json` — see [Execute KQL Command](#execute-kql-command)

```bash
# Create JSON mapping
read -r -d '' CSL <<'KQL' || true
.create table SensorData ingestion json mapping 'SensorJsonMapping' '[{"column":"Timestamp","path":"$.ts","datatype":"datetime"},{"column":"DeviceId","path":"$.deviceId","datatype":"string"},{"column":"Temperature","path":"$.temp","datatype":"real"},{"column":"Humidity","path":"$.humidity","datatype":"real"},{"column":"Location","path":"$.location","datatype":"dynamic"}]'
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute `/tmp/kql_body.json` — see [Execute KQL Command](#execute-kql-command)

### Example 2: ETL with Update Policy

```kql
// 1. Target table
.create-merge table ParsedLogs (Timestamp: datetime, Level: string, Message: string, Source: string)

// 2. Transform function
.create-or-alter function ParseRawLogs() {
    RawLogs
    | extend J = parse_json(RawMessage)
    | project
        Timestamp = todatetime(J.timestamp),
        Level = tostring(J.level),
        Message = tostring(J.message),
        Source = tostring(J.source)
}

// 3. Attach update policy
.alter table ParsedLogs policy update
@'[{"IsEnabled":true,"Source":"RawLogs","Query":"ParseRawLogs()","IsTransactional":true}]'
```

---

## Agent Integration Notes

- This skill covers **authoring operations** — creating/altering database objects and ingesting data.
- For **read-only queries** and data exploration, switch to the `eventhouse-cli` consumption mode.
- For **cross-workload orchestration**, delegate to the **FabricDataEngineer** agent.
- All management commands require elevated database roles (`Admin` or `Ingestor`).
