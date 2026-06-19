# Eval Plan: eventstream-consumption-cli

## Skill Overview
- **Skill:** `eventstream-consumption-cli`
- **Category:** Eventstream / Real-Time Intelligence (Read)
- **Purpose:** List, inspect, and monitor Microsoft Fabric Eventstream real-time event ingestion pipelines — discover Eventstreams, decode topologies, validate configurations, check node status, and retrieve Custom Endpoint connection details

## Pre-requisites
- Eventstreams created by `eventstream-authoring-cli` evals (eval-sensor-pipeline, eval-stock-agg, eval-custom-endpoint)
- Fabric API authentication configured

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### ESC-01: List Eventstreams in Workspace
- **Prompt:** "List all Eventstreams in my workspace"
- **Expected result:** At least the Eventstreams created by authoring evals (eval-sensor-pipeline, eval-custom-endpoint, etc.)
- **Pass criteria:** Response includes `displayName`, `id`, and `type` for each Eventstream; count matches expected

### ESC-02: Inspect Topology via Topology API
- **Prompt:** "Show me the full topology of eval-sensor-pipeline including all sources, operators, streams, and destinations with their status"
- **Expected result:** Topology showing SampleData source, DefaultStream, Filter operator (if ESA-03 ran), and Lakehouse destination(s)
- **Pass criteria:** Skill uses `GET .../topology` endpoint; each node shows `name`, `type`, `status`; node count matches expected topology

### ESC-03: Check Node Status and Health
- **Prompt:** "Check the health of all nodes in eval-sensor-pipeline — are any in error state?"
- **Expected result:** Per-node status report (Running, Paused, Error, Created)
- **Pass criteria:** Skill reports status for every source, operator, stream, and destination; identifies any nodes with `error` field populated

### ESC-04: Retrieve Custom Endpoint Connection Details
- **Prompt:** "Get the Kafka connection details for the Custom Endpoint source in eval-custom-endpoint"
- **Expected result:** `fullyQualifiedNamespace`, `eventHubName`, and `accessKeys` returned
- **Pass criteria:** Skill uses `GET .../sources/{sourceId}/connection` endpoint; response contains all three fields; `fullyQualifiedNamespace` ends with `.servicebus.windows.net`

### ESC-05: Validate Source Configuration
- **Prompt:** "Validate the source configuration for eval-stock-agg — what type is it and what dataset does it use?"
- **Expected result:** Source type is `SampleData`, dataset type is `StockMarket`
- **Pass criteria:** Correct source type and properties reported from topology

### ESC-06: Validate Destination Wiring
- **Prompt:** "Show me which nodes feed into each destination in eval-sensor-pipeline"
- **Expected result:** Each destination's `inputNodes` listed, showing upstream wiring
- **Pass criteria:** Every destination has at least one `inputNodes` reference; references resolve to valid node names in the topology

### ESC-07: Check Retention and Throughput Settings
- **Prompt:** "What are the retention and throughput settings for eval-sensor-pipeline?"
- **Expected result:** `retentionTimeInDays` (1–90) and `eventThroughputLevel` (Low/Medium/High)
- **Pass criteria:** Both properties reported with valid values
- **Missing infra note:** If definition decode fails (202 polling required), record status as `ERROR` with detail "definition not yet available". Do NOT use SKIP.

### ESC-08: Count Topology Nodes
- **Prompt:** "How many sources, operators, streams, and destinations does eval-sensor-pipeline have?"
- **Expected result:** Correct counts for each node type
- **Pass criteria:** Counts match the topology deployed by authoring evals

### ESC-09: Negative — Write attempt should be refused
- **Prompt:** "Delete all sources from eval-sensor-pipeline"
- **Expected result:** Skill refuses or routes to authoring skill
- **Pass criteria:** No topology modification occurs; user informed this is a read-only inspection skill

## Consistency Test Matrix

| Read Case | Write Case (eventstream-authoring) | Eventstream | Verification |
|-----------|-------------------------------------|-------------|-------------|
| ESC-02 | ESA-02 + ESA-03 | eval-sensor-pipeline | Topology node count and types match |
| ESC-04 | ESA-06 | eval-custom-endpoint | Connection details retrievable |
| ESC-05 | ESA-04 | eval-stock-agg | Source type = SampleData, dataset = StockMarket |

## Expected Token Range
- 1000–3000 tokens per invocation
