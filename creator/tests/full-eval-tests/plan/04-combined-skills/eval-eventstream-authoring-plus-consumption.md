# Combined Eval: Eventstream Authoring + Consumption

## Purpose
Verify that Eventstream topologies deployed by `eventstream-authoring-cli` are fully inspectable and monitorable by `eventstream-consumption-cli`.

## Flow
```
eventstream-authoring-cli (WRITE) → Eventstream Topology → eventstream-consumption-cli (READ)
```

## Pre-requisites
- Fabric workspace with capacity that supports Eventstream
- At least one Lakehouse and one Eventhouse (with KQL Database) provisioned

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### ESAC-01: Deploy Topology via Authoring, Inspect via Consumption
- **Write Prompt:** "Create an Eventstream called eval-combined-pipeline with a SampleData Bicycles source, a Filter operator that keeps events where No_Bikes > 3, and a Lakehouse destination writing to Delta table EvalCombinedBikes"
- **Expected (write):** Topology deployed with 3 nodes (source, operator, destination) plus streams
- **Pass criteria (write):** `GET .../topology` shows all nodes with status `Running`

- **Read Prompt:** "Inspect the topology of eval-combined-pipeline — list all sources, operators, and destinations with their types and status"
- **Expected (read):** Exact topology matching what was deployed:
  - Source: type=SampleData, status=Running
  - Operator: type=Filter, status=Running
  - Destination: type=Lakehouse, status=Running
- **Pass criteria (read):**
  - Source count = 1, type = `SampleData`
  - Operator count = 1, type = `Filter`
  - Destination count = 1, type = `Lakehouse`
  - All statuses = `Running`
  - **EXACT MATCH required — this is a consistency test**

### ESAC-02: Deploy Custom Endpoint, Retrieve Connection via Consumption
- **Write Prompt:** "Create an Eventstream called eval-combined-custom with a Custom Endpoint source and an Eventhouse destination writing to table EvalCombinedCustom in my KQL Database"
- **Expected (write):** Topology deployed with CustomEndpoint source
- **Pass criteria (write):** `GET .../topology` shows CustomEndpoint source with status `Running`

- **Read Prompt:** "Get the Kafka connection details for the Custom Endpoint source in eval-combined-custom — I need the bootstrap server, topic name, and connection string"
- **Expected (read):** Connection details returned:
  - `fullyQualifiedNamespace`: ends with `.servicebus.windows.net`
  - `eventHubName`: starts with `es_`
  - `accessKeys.primaryConnectionString`: starts with `Endpoint=sb://`
- **Pass criteria (read):**
  - All three fields present and non-empty
  - Namespace format valid
  - Connection string is a valid Event Hub connection string
  - **EXACT FORMAT MATCH required**

### ESAC-03: Pause via Authoring, Verify Status via Consumption
- **Write Prompt:** "Pause the eval-combined-pipeline Eventstream"
- **Expected (write):** Eventstream paused
- **Pass criteria (write):** `POST .../pause` returns 200

- **Read Prompt:** "Check the status of all nodes in eval-combined-pipeline"
- **Expected (read):** All nodes show `Paused` status
- **Pass criteria (read):**
  - Source status = `Paused`
  - Destination status = `Paused`
  - **STATUS MATCH required**

- **Cleanup Prompt:** "Resume eval-combined-pipeline"
- **Expected (cleanup):** Eventstream resumed, statuses return to `Running`

## Consistency Scoring

For each read test case, compute:
```
topology_match  = (all node names, types match deployed topology) ? 1 : 0
node_count_ok   = (actual source/operator/dest count == expected) ? 1 : 0
status_accuracy = (nodes with correct status / total nodes)
consistency     = (topology_match + node_count_ok + status_accuracy) / 3
```

**Pass threshold:** consistency = 1.0 for all test cases

## Expected Token Range
- 2500–5500 tokens per combined test (write + read + verify)
