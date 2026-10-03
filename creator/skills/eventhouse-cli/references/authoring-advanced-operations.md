<!-- Reference for the `eventhouse-cli` skill, authoring mode. Linked from SKILL.md for
     materialized views, stored functions, update policies, schema evolution and
     authoring-operation monitoring. -->

# eventhouse-cli authoring mode — Advanced Operations

## Contents

- [Executing a Command](#executing-a-command)
- [Materialized Views via CLI](#materialized-views-via-cli)
- [Functions and Update Policies via CLI](#functions-and-update-policies-via-cli)
- [Schema Evolution via CLI](#schema-evolution-via-cli)
- [Monitoring Authoring Operations](#monitoring-authoring-operations)

> Every command below is a MUTATION unless stated otherwise. Before executing, confirm the
> target KQL database and the intended change. If the request is generic, such as "set up
> my Eventhouse", ask a clarifying question and stop rather than inferring a schema.

---

## Executing a Command

Each snippet below builds a request body at `/tmp/kql_body.json`. Send it with:

```bash
az rest --method POST \
  --url "${CLUSTER_URI}/v1/rest/mgmt" \
  --resource "https://kusto.kusto.windows.net" \
  --headers "Content-Type=application/json" \
  --body @/tmp/kql_body.json \
  | jq '.Tables[0].Rows'
```

`.show` stays a management command even with a trailing `| project`, so everything here
goes to `/v1/rest/mgmt`. `/v1/rest/query` is only for expressions such as `Events | count`.

---

## Materialized Views via CLI

```bash
# Create materialized view with backfill
read -r -d '' CSL <<'KQL' || true
.create materialized-view with (backfill=true) HourlyEventCounts on table Events { Events | summarize Count = count(), LastSeen = max(Timestamp) by EventType, bin(Timestamp, 1h) }
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute it with the `az rest` call in [Executing a Command](#executing-a-command).

```bash
# Check health
read -r -d '' CSL <<'KQL' || true
.show materialized-view HourlyEventCounts statistics
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute it with the `az rest` call in [Executing a Command](#executing-a-command).

---

## Functions and Update Policies via CLI

### Create Function

```bash
read -r -d '' CSL <<'KQL' || true
.create-or-alter function with (docstring='Parse raw events', folder='ETL') ParseRawEvents() { RawEvents | extend Parsed = parse_json(RawData) | project Timestamp = todatetime(Parsed.timestamp), EventType = tostring(Parsed.eventType), UserId = tostring(Parsed.userId) }
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute it with the `az rest` call in [Executing a Command](#executing-a-command).

### Create Update Policy

The policy is itself a JSON document. Written this way it needs no backslash-escaping and
no hardcoded database name -- the heredoc keeps it literal and `jq` does the escaping.

```bash
read -r -d '' CSL <<'KQL' || true
.alter table ParsedEvents policy update @'[{"IsEnabled":true,"Source":"RawEvents","Query":"ParseRawEvents()","IsTransactional":true}]'
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
```

> Execute it with the `az rest` call in [Executing a Command](#executing-a-command).

---

## Schema Evolution via CLI

### Safe Schema Deployment Script

Save management commands in a `.kql` file and submit the **whole file** in one
`.execute database script`. Do not loop over it line by line: a script exported by
`.show database schema as csl script` contains multiline function bodies and policies, and
splitting on newlines cuts valid commands in half. `ThrowOnErrors=true` stops at the first
bad command instead of reporting partial success.

```bash
# deploy_schema.kql holds ordinary KQL -- no JSON escaping, quotes written as-is:
# .create-merge table Events (Timestamp: datetime, EventType: string, Properties: dynamic)
# .alter table Events policy retention '{"SoftDeletePeriod":"365.00:00:00","Recoverability":"Enabled"}'
# .alter table Events policy caching hot = 30d

jq -n --arg db "${DB}" --rawfile script deploy_schema.kql \
  '{db: $db, csl: (".execute database script with (ThrowOnErrors=true) <|\n" + $script)}' \
  > /tmp/kql_body.json
az rest --method POST \
  --url "${CLUSTER_URI}/v1/rest/mgmt" \
  --resource "https://kusto.kusto.windows.net" \
  --headers "Content-Type=application/json" \
  --body @/tmp/kql_body.json \
  | jq '.Tables[0].Rows'
```

`scripts/deploy-schema.sh` does exactly this; run it rather than retyping the above.

### Export Current Schema

```bash
# Unquoted heredoc here: the database name has to be interpolated into the command text
# itself. There is nothing to escape in this one, so expansion is safe.
read -r -d '' CSL <<KQL || true
.show database ${DB} schema as csl script
KQL
jq -n --arg db "${DB}" --arg csl "${CSL}" '{db: $db, csl: $csl}' > /tmp/kql_body.json
az rest --method POST \
  --url "${CLUSTER_URI}/v1/rest/mgmt" \
  --resource "https://kusto.kusto.windows.net" \
  --headers "Content-Type=application/json" \
  --body @/tmp/kql_body.json \
  | jq -r '.Tables[0].Rows[][0]' > current_schema.kql
```

---

## Monitoring Authoring Operations

```kql
// Recent management commands
.show commands
| where StartedOn > ago(1h)
| project StartedOn, CommandType, Text = substring(Text, 0, 100), State, Duration
| order by StartedOn desc

// Ingestion failures
.show ingestion failures
| where FailedOn > ago(24h)
| summarize FailureCount = count() by ErrorCode, Table
| order by FailureCount desc

// Materialized view health
.show materialized-views
| project Name, IsEnabled, IsHealthy, MaterializedTo
```
