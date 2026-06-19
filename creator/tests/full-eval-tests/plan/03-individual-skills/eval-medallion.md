# Eval Plan: e2e-medallion-architecture

## Skill Overview
- **Skill:** `e2e-medallion-architecture`
- **Category:** Pipeline (Write + Read)
- **Purpose:** Implement end-to-end Bronze/Silver/Gold lakehouse pattern with PySpark, Delta Lake, and Fabric Pipelines

## Pre-requisites
- Active Fabric tenant/capacity with permissions to create multiple workspaces
- Eval datasets generated (CSV files for Bronze ingestion)
- Sufficient capacity for 3 workspaces and 3 lakehouses (Bronze, Silver, Gold)

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Case Types

## Test Cases

### MED-01: Design Medallion Architecture *(description)*
- **Prompt:** "Design a medallion architecture with Bronze, Silver, and Gold layers for sales data. Do not deploy, just describe"
- **Expected:** Skill proposes default 3-layer architecture with separate lakehouses for Bronze/Silver/Gold, plus lakehouses, schemas, and data flow
- **Pass criteria:** Output describes Bronze (raw), Silver (cleansed), Gold (aggregated) layers and defaults to separate workspaces with a single-workspace override option
- **Verification:** Text response only — no API calls needed


### MED-02:Spark Configuration per Layer *(description)*
- **Prompt:** "Describe how you would optimize Spark configurations for each medallion layer: Bronze (high throughput), Silver (balanced), Gold (low latency)"
- **Expected:** Different Spark configs per layer
- **Pass criteria:** Response includes distinct config values for each layer appropriate for its workload
- **Verification:** Text response only — no API calls needed

## Consistency Test Matrix

## Expected Token Range
- 2500–6000 tokens per invocation (most complex skill)
