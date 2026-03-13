---
description: Compile the full Fabric implementation blueprint from modeled artifacts
---

# Generate Fabric Implementation Blueprint

Compile all modeled Fabric artifacts into a structured implementation blueprint document.

## Output Structure

Produce a single Markdown document with these sections in order:

### 1. Executive Summary
- Source architecture version/date
- Layer count, table count, pipeline count
- Fabric workspace count, estimated capacity tier

### 2. Workspace Layout
- Table: Workspace → Type → Contents → Purpose
- Naming convention applied
- Capacity assignment recommendations

### 3. Fabric Architecture Diagram
- Mermaid diagram showing all workspaces, artifacts, and data-flow arrows
- Use `graph LR` layout with subgraphs per workspace

### 4. Layer Definitions (repeat per layer)
For each layer (L0, L1, L2, L4-RT if applicable):

#### 4.a Storage Artifacts
- Table DDL (Spark SQL or T-SQL as appropriate)
- Delta properties (optimizeWrite, autoCompaction, etc.)
- Partition strategy
- Z-ORDER / V-ORDER specification

#### 4.b Process Specifications
For each process (Notebook, Stored Procedure, or Eventstream):
- Name, type, language
- Input tables → Output tables
- Parameterisation from metadata
- Core logic (pseudocode or actual code blocks)
- Error handling and logging

#### 4.c Layer Transition Spec
- Source layer → Target layer
- Transformation type (full-load, SCD2, incremental, CDC)
- Artifact responsible
- Cross-layer access method (Shortcut or direct)

### 5. Metadata Repository
- Full T-SQL DDL for all metadata tables
- Seed data for initial configuration
- Stored procedures for metadata operations

### 6. Pipeline Specifications
For each pipeline:
- Activity list with dependencies
- ForEach / If Condition / Switch logic
- Parameterisation
- Failure handling and retry policy
- Schedule/trigger configuration

### 7. Quality Framework
- Quality check specifications
- Threshold definitions
- Alert/notification strategy

### 8. Rollback & Recovery
- Delta time travel procedures
- RESTORE commands
- Recovery runbook

### 9. Naming Convention Reference
- All naming rules applied in this blueprint
- Pattern table: artifact type → prefix → example

### 10. Modeler-to-Creator Handoff Checklist
- [ ] All table DDL complete
- [ ] All process specs complete
- [ ] All pipeline specs complete
- [ ] Metadata repository defined
- [ ] Semantic model — out of scope (Semantic Model Agent)
- [ ] Quality framework defined
- [ ] Mermaid diagrams embedded
- [ ] Naming conventions documented
