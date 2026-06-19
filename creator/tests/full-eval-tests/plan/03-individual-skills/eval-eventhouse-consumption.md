# Eval Plan: eventhouse-consumption-cli

## Skill Overview
- **Skill:** `eventhouse-consumption-cli`
- **Category:** KQL / Eventhouse (Read)
- **Purpose:** Run KQL queries against Fabric Eventhouse for real-time intelligence and time-series analytics, schema discovery, and ingestion monitoring

## Pre-requisites
- Shared `{{EVENTHOUSE}}` with KQL Database `{{KQLDB}}` provisioned by runner (Phase 0b)

## Data Setup (run FIRST — before any test cases)

This plan provisions its own data. Do NOT depend on eventhouse-authoring having run first.

1. `.drop table eval_sensor_readings ifexists` in `{{KQLDB}}`
2. `.drop table eval_sales ifexists` in `{{KQLDB}}`
3. `.drop materialized-view eval_hourly_avg ifexists` in `{{KQLDB}}`
4. Create table `eval_sensor_readings` with schema: device_id (string), timestamp (datetime), temperature (real), humidity (real), pressure (real), tags (dynamic)
5. Ingest 5 inline rows:
   ```kql
   .ingest inline into table eval_sensor_readings <|
   sensor_001,2025-01-01T00:00:00Z,20.6,41.05,1013.09,["indoor","floor1"]
   sensor_002,2025-01-01T01:00:00Z,21.1,42.10,1013.18,["indoor","floor2"]
   sensor_003,2025-01-01T02:00:00Z,21.6,43.15,1013.27,["outdoor","yard"]
   sensor_004,2025-01-01T03:00:00Z,22.1,44.20,1013.36,["indoor","floor1"]
   sensor_005,2025-01-01T04:00:00Z,22.6,45.25,1013.45,["outdoor","roof"]
   ```
6. Create table `eval_sales` with schema: transaction_id (long), customer_id (long), product_name (string), category (string), quantity (long), unit_price (real), total_amount (real), transaction_date (datetime), region (string) — for KC-05 join test
7. Create materialized view `eval_hourly_avg` computing average temperature, humidity, pressure per device_id per hour from `eval_sensor_readings` — for KC-04 time-series test

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### KC-01: Simple Row Count
- **Prompt:** "Run a KQL query to count the rows in eval_sensor_readings in my Eventhouse"
- **Expected result:** 5
- **Pass criteria:** Exact count match

### KC-02: Schema Discovery
- **Prompt:** "Show the schema of eval_sensor_readings in my Eventhouse"
- **Expected result:** All columns listed with types (device_id:string, timestamp:datetime, temperature:real, humidity:real, pressure:real, tags:dynamic)
- **Pass criteria:** All columns present with correct KQL types

### KC-03: Filtered Query (where)
- **Prompt:** "Query eval_sensor_readings in my Eventhouse for all readings where temperature > 22.0"
- **Expected result:** Subset of rows meeting filter criteria
- **Pass criteria:** All returned rows have temperature > 22.0, no rows with temperature ≤ 22.0

### KC-04: Time-Series Aggregation (summarize + bin)
- **Prompt:** "Query eval_sensor_readings in my Eventhouse: compute average temperature per device per day using bin(timestamp, 1d)"
- **Expected result:** One row per device per day
- **Pass criteria:** Results use `summarize ... by ... bin()` pattern, values match golden results

### KC-05: Join Query
- **Prompt:** "Join eval_sensor_readings with eval_sales in my Eventhouse on some common dimension and show combined results"
- **Expected result:** Join executes (even if limited overlap)
- **Pass criteria:** Skill generates valid KQL join syntax, query executes without error

### KC-06: Render / Visualization Hint
- **Prompt:** "Query average temperature by day from eval_sensor_readings in my Eventhouse and render as a timechart"
- **Expected result:** Query includes `| render timechart`
- **Pass criteria:** Skill appends render operator, query is valid

### KC-07: Ingestion Monitoring
- **Prompt:** "Show recent ingestion operations for eval_sensor_readings in my Eventhouse"
- **Expected result:** Ingestion log entries
- **Pass criteria:** Skill uses `.show ingestion failures` or journal commands

### KC-08: Negative — Write attempt should fail/be refused
- **Prompt:** "Drop the eval_sensor_readings table from my Eventhouse"
- **Expected result:** Skill refuses or routes to authoring skill
- **Pass criteria:** No table dropped, user informed this is a read-only query skill

## Data Teardown (run LAST — after all test cases)

Clean up KQL objects created by this plan. Do NOT drop the shared `{{EVENTHOUSE}}` or `{{KQLDB}}`.
1. `.drop materialized-view eval_hourly_avg ifexists`
2. `.drop table eval_sales ifexists`
3. `.drop table eval_sensor_readings ifexists`

## Consistency Test Matrix

| Read Case | Data Source | Table | Verification |
|-----------|------------|-------|-------------|
| KC-01 | Data Setup (step 5) | eval_sensor_readings | Row count = 5 |

## Expected Token Range
- 1000–3000 tokens per invocation
