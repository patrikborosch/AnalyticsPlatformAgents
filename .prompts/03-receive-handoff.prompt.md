---
description: Receive an architecture handoff and translate it into a Fabric implementation model
---

# Receive Architecture Handoff

Parse the Analytics Architect Agent's handoff document and translate it into a Fabric-specific implementation model.

## Instructions

### Step 1 — Parse & Validate
1. Identify all **objects** (tables/entities) from the Object Catalogue
2. Identify all **pipelines** and their steps
3. Identify all **transformation rules** referenced by mappings
4. Identify all **quality rules**
5. Flag any **missing or ambiguous** specifications — ask before proceeding

### Step 2 — Map to Fabric Artifacts
For each architectural element, determine the Fabric artifact:

| Architect Element | Fabric Artifact |
|---|---|
| L0 Landing tables | Lakehouse tables in `lh_landing` |
| L1 Persistence tables | Lakehouse Delta tables in `lh_persist` |
| L2 Presentation tables | Warehouse tables in `wh_present` |
| Metadata repository | Warehouse tables in `wh_meta` |
| Audit log | Warehouse or Lakehouse table |
| Ingestion jobs | Notebooks + Copy Activities in Pipeline |
| SCD2 merge jobs | Parameterised Notebook `nb_scd2_merge` |
| Current-state refresh | Stored Procedure in Warehouse |
| Quality checks | Notebook `nb_quality_check` |
| Orchestration | Data Pipeline `pl_main_orchestrator` |
| Semantic layer | *(out of scope — Semantic Model Agent)* |

### Step 3 — Produce Layer by Layer
Work through each layer producing:
1. **L0:** Table DDL (Spark), ingestion Notebook/Pipeline specs
2. **L1:** Table DDL (Spark) with SCD2 columns, Delta properties, merge Notebook specs
3. **L2:** Table DDL (T-SQL), Stored Procedure specs, Shortcuts to L1
4. **Metadata:** T-SQL DDL for all metadata tables, seed data
5. **Pipelines:** Full activity specifications

> **Note:** Semantic Model and Report specifications are out of scope (handled by the Semantic Model Agent).

### Step 4 — Produce Mermaid Diagrams
- Fabric Architecture Diagram (workspaces, artifacts, data flow)
- Pipeline Activity Flowchart
- Table Relationship ERDs per layer
- Cross-Workspace Access Diagram

### Step 5 — Creator Handoff
Compile into structured document ready for the Creator Agent.
