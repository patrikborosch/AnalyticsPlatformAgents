# Eval Plan: eventstream-authoring-cli

## Skill Overview
- **Skill:** `eventstream-authoring-cli`
- **Category:** Eventstream / Real-Time Intelligence (Write)
- **Purpose:** Create, wire, and deploy Microsoft Fabric Eventstream real-time event streaming topologies via the Fabric Items REST API and Topology API — sources, operators, destinations, and stream routing

## Pre-requisites
- Fabric workspace with capacity that supports Eventstream
- At least one Lakehouse and one Eventhouse (with KQL Database) provisioned for destination testing
- Fabric API authentication configured

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### ESA-01: Create Empty Eventstream
- **Prompt:** "Create an Eventstream called eval-sensor-pipeline in my workspace"
- **Expected:** Empty Eventstream item created
- **Pass criteria:** `GET .../eventstreams` lists `eval-sensor-pipeline` with correct `id` and `type`
- **Metrics:** Success rate, token usage

### ESA-02: Deploy Topology with SampleData Source
- **Prompt:** "Update eval-sensor-pipeline with a SampleData source using the Bicycles dataset, a DefaultStream, and a Lakehouse destination writing to a Delta table called EvalBicycles in my Lakehouse"
- **Expected:** Topology deployed with source → stream → destination
- **Pass criteria:** `GET .../topology` shows source (type=SampleData, status=Running), destination (type=Lakehouse, status=Running), and stream (type=DefaultStream)
- **Golden data:** SampleData Bicycles schema: BikepointID, Street, Neighborhood, Latitude, Longitude, No_Bikes, No_Empty_Docks

### ESA-03: Add Filter Operator
- **Prompt:** "Add a Filter operator to eval-sensor-pipeline that keeps only events where No_Bikes is greater than 5, and route the filtered output to a second Lakehouse Delta table called EvalBicyclesFiltered"
- **Expected:** Topology updated with Filter operator between stream and new destination
- **Pass criteria:** `GET .../topology` shows Filter operator with correct condition, second destination wired via `inputNodes`

### ESA-04: Add Aggregate Operator
- **Prompt:** "Create a new Eventstream called eval-stock-agg with a SampleData source using StockMarket, an Aggregate operator that computes Minimum and Maximum of price over a 1-minute tumbling window, and an Eventhouse destination writing to table EvalStockAgg in my KQL Database"
- **Expected:** Topology with SampleData → DefaultStream → Aggregate → Eventhouse
- **Pass criteria:** `GET .../topology` shows Aggregate operator with `Minimum`/`Maximum` functions and `duration` of 1 minute; Eventhouse destination with correct `itemId` (KQL Database ID, not Eventhouse ID)

### ESA-05: Deploy SQL Operator with Multi-Table Routing
- **Prompt:** "Create an Eventstream called eval-sql-router with a SampleData YellowTaxi source, a SQL operator that routes high-fare trips (fare_amount > 50) INTO HighFareDest and all trips INTO AllTripsDest, with both destinations going to Lakehouse Delta tables"
- **Expected:** SQL operator with two INTO clauses, each wired to a separate Lakehouse destination
- **Pass criteria:** `GET .../topology` shows SQL operator, two Lakehouse destinations named `HighFareDest` and `AllTripsDest`; SQL query references correct stream alias and column names

### ESA-06: Deploy Custom Endpoint Source
- **Prompt:** "Create an Eventstream called eval-custom-endpoint with a Custom Endpoint source and an Eventhouse destination writing to table EvalCustomData in my KQL Database"
- **Expected:** Topology with CustomEndpoint source → DefaultStream → Eventhouse destination
- **Pass criteria:** `GET .../topology` shows source (type=CustomEndpoint, status=Running); `GET .../sources/{sourceId}/connection` returns `fullyQualifiedNamespace`, `eventHubName`, and `accessKeys`

### ESA-07: Pause and Resume Eventstream
- **Prompt:** "Pause the eval-sensor-pipeline Eventstream, verify it is paused, then resume it"
- **Expected:** Eventstream paused (sources/destinations show Paused status), then resumed (status returns to Running)
- **Pass criteria:** After pause: `GET .../topology` shows node statuses as `Paused`. After resume: statuses return to `Running`

### ESA-08: Update Existing Topology — Add Destination
- **Prompt:** "Add an Eventhouse destination to eval-sensor-pipeline that writes the DefaultStream to a KQL table called EvalBicyclesKQL in my KQL Database"
- **Expected:** Topology updated with additional Eventhouse destination alongside existing Lakehouse destination
- **Pass criteria:** `GET .../topology` shows both Lakehouse and Eventhouse destinations, both referencing the DefaultStream

### ESA-09: Delete Eventstream (throwaway target)
- **Prompt:** "Create a new Eventstream named 'eval-delete-target-eventstream' with a SampleData Bicycles source and no destination, then delete it"
- **Expected:** Throwaway eventstream created, then deleted in the same test
- **Pass criteria:** `GET .../eventstreams` includes `eval-delete-target-eventstream` after create, then no longer includes it after delete (DELETE returns 200); the persistent `eval-stock-agg` from ESA-04 is left untouched so downstream consumption tests can read it
- **Why throwaway:** This test validates the DELETE operation. Earlier versions deleted the persistent `eval-stock-agg` here, which broke ESC-05 (eventstream-consumption) because the consumption plan runs against the same workspace and reads `eval-stock-agg`. The throwaway pattern keeps the test's actual intent (verify delete works) while preserving cross-plan state.

### ESA-10: Node Naming Validation
- **Prompt:** "Create an Eventstream called eval-naming-test with a SampleData Bicycles source named BikeSource, a Filter operator named TempFilter, and a Lakehouse destination named LHOutput"
- **Expected:** All node names accepted (alphanumeric PascalCase, 3–63 chars)
- **Pass criteria:** `GET .../topology` shows all three nodes with exact names as specified

### ESA-11: Negative — Ambiguous prompt
- **Prompt:** "Set up my Eventstream"
- **Expected:** Skill should ask for clarification (which source type, which destination, what transformations)
- **Pass criteria:** Agent asks clarifying questions, does not fail silently or create incomplete topology

## Write Operations (for consistency pairing)

| Write Case | Eventstream | Topology Elements | Paired Read Skill |
|-----------|-------------|-------------------|-------------------|
| ESA-02 | eval-sensor-pipeline | SampleData → Lakehouse | eventstream-consumption-cli |
| ESA-04 | eval-stock-agg | SampleData → Aggregate → Eventhouse | eventstream-consumption-cli |
| ESA-06 | eval-custom-endpoint | CustomEndpoint → Eventhouse | eventstream-consumption-cli |

## Expected Token Range
- 1500–4000 tokens per invocation
