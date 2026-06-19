# Eval Plan: eventhouse-authoring-cli

## Skill Overview
- **Skill:** `eventhouse-authoring-cli`
- **Category:** KQL / Eventhouse (Write)
- **Purpose:** Execute KQL management commands — table management, ingestion, policies, functions, materialized views, and data mappings against Fabric Eventhouse and KQL Databases

## Pre-requisites
- Shared `{{EVENTHOUSE}}` with KQL Database `{{KQLDB}}` provisioned by runner (Phase 0b)
- Eval datasets generated per `01-data-generation.md` (sensor_readings.json, sales CSVs)
- Fabric API authentication configured

## Data Setup (run FIRST — before any test cases)

Clean up any leftover KQL objects from a prior run:
1. `.drop table eval_sensor_readings ifexists` in `{{KQLDB}}`
2. `.drop table eval_sensor_alerts ifexists` in `{{KQLDB}}`
3. `.drop table eval_sales ifexists` in `{{KQLDB}}`
4. `.drop materialized-view eval_hourly_avg ifexists` in `{{KQLDB}}`
5. `.drop function eval_avg_temperature ifexists` in `{{KQLDB}}`

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### KA-01: Create KQL Table
- **Prompt:** "Create a KQL table called eval_sensor_readings in my Eventhouse with columns: device_id (string), timestamp (datetime), temperature (real), humidity (real), pressure (real), tags (dynamic)"
- **Expected:** Table created with exact schema
- **Pass criteria:** `.show table eval_sensor_readings` returns correct schema
- **Metrics:** Success rate, token usage

### KA-02: Ingest Data Inline
- **Prompt:** "Ingest these 5 rows inline into eval_sensor_readings in my Eventhouse: ('sensor_001','2025-01-01T00:00:00Z',20.6,41.05,1013.09,dynamic(['indoor','floor1'])), ('sensor_002','2025-01-01T01:00:00Z',21.1,42.10,1013.18,dynamic(['indoor','floor2'])), ('sensor_003','2025-01-01T02:00:00Z',21.6,43.15,1013.27,dynamic(['outdoor','yard'])), ('sensor_004','2025-01-01T03:00:00Z',22.1,44.20,1013.36,dynamic(['indoor','floor1'])), ('sensor_005','2025-01-01T04:00:00Z',22.6,45.25,1013.45,dynamic(['outdoor','roof']))"
- **Expected:** 5 rows ingested
- **Pass criteria:** `eval_sensor_readings | count` returns 5
- **Golden data:** See `evalsets/expected-results/sensor_5rows.json`

### KA-03: Create Ingestion Mapping
- **Prompt:** "Create a JSON ingestion mapping called eval_sensor_json_mapping for eval_sensor_readings in my Eventhouse that maps device_id, timestamp, readings.temperature, readings.humidity, readings.pressure, and tags from nested JSON"
- **Expected:** Mapping created
- **Pass criteria:** `.show table eval_sensor_readings ingestion json mappings` includes `eval_sensor_json_mapping`

### KA-04: Ingest from Storage (Blob/OneLake)
- **Prompt:** "Ingest data from the sensor_readings.json file into eval_sensor_readings in my Eventhouse using the eval_sensor_json_mapping"
- **Expected:** 500 rows ingested (10 devices × 50 readings)
- **Pass criteria:** Row count = 500 (after clearing inline data or in addition)
- **Missing infra note:** If no blob/OneLake storage URI is available in the eval environment, record status as `ERROR` (not `SKIP`) with detail "infrastructure not configured: no storage path available". Do NOT use SKIP — SKIP triggers a suite-level abort.

### KA-05: Create KQL Function
- **Prompt:** "Create a stored function called eval_avg_temperature in my Eventhouse that returns the average temperature per device_id from eval_sensor_readings"
- **Expected:** Function created
- **Pass criteria:** `.show functions` includes `eval_avg_temperature`, function is callable

### KA-06: Set Retention Policy
- **Prompt:** "Set the retention policy for eval_sensor_readings in my Eventhouse to 90 days soft-delete and 365 days recoverability"
- **Expected:** Retention policy applied
- **Pass criteria:** `.show table eval_sensor_readings policy retention` shows correct values

### KA-07: Set Caching Policy
- **Prompt:** "Set the caching policy for eval_sensor_readings in my Eventhouse to 30 days hot cache"
- **Expected:** Caching policy applied
- **Pass criteria:** `.show table eval_sensor_readings policy caching` shows 30d

### KA-08: Create Materialized View
- **Prompt:** "Create a materialized view called eval_hourly_avg in my Eventhouse that computes average temperature, humidity, and pressure per device_id per hour from eval_sensor_readings"
- **Expected:** Materialized view created
- **Pass criteria:** `.show materialized-views` includes `eval_hourly_avg`

### KA-09: Alter Table — Add Column
- **Prompt:** "Add a column battery_level of type real to eval_sensor_readings in my Eventhouse"
- **Expected:** Column added
- **Pass criteria:** `.show table eval_sensor_readings` includes battery_level column

### KA-10: Create Update Policy
- **Prompt:** "Create an update policy on a target table eval_sensor_alerts that triggers when eval_sensor_readings receives new data with temperature > 30.0"
- **Expected:** Update policy created with transformation query
- **Pass criteria:** `.show table eval_sensor_alerts policy update` shows the policy

### KA-11: Create Sales Table for Cross-Skill Testing
- **Prompt:** "Create a KQL table called eval_sales in my Eventhouse with columns: transaction_id (long), customer_id (long), product_name (string), category (string), quantity (long), unit_price (real), total_amount (real), transaction_date (datetime), region (string)"
- **Expected:** Table created
- **Pass criteria:** Schema matches specification

### KA-12: Negative — Ambiguous prompt
- **Prompt:** "Set up my Eventhouse"
- **Expected:** Skill should ask for clarification or provide structured options
- **Pass criteria:** Agent asks clarifying questions, does not fail silently

## Write Operations (for consistency pairing)

| Write Case | Table | Rows | Paired Read Skill |
|-----------|-------|------|-------------------|
| KA-02 | eval_sensor_readings | 5 | eventhouse-consumption-cli |
| KA-04 | eval_sensor_readings | 500 | eventhouse-consumption-cli |

## Data Teardown (run LAST — after all test cases)

Clean up KQL objects created by this plan. Do NOT drop the shared `{{EVENTHOUSE}}` or `{{KQLDB}}`.
1. `.drop materialized-view eval_hourly_avg ifexists`
2. `.drop function eval_avg_temperature ifexists`
3. `.drop table eval_sensor_alerts ifexists`
4. `.drop table eval_sales ifexists`
5. `.drop table eval_sensor_readings ifexists`

## Expected Token Range
- 1200–3500 tokens per invocation
