# AnalyticsPlatformAgents

> **Note:** This project is experimental. Agent-generated outputs should be reviewed before use in production environments. Always be the human in the loop.

A multi-agent system for designing and implementing analytics platforms on Microsoft Fabric.

## Agent Team

| Agent | File | Role |
|-------|------|------|
| **Orchestrator** | `agents/orchestrator.md` | Coordinates the end-to-end workflow across all agents |
| **Architect** | `agents/architect.md` | Designs technology-agnostic analytics architectures (layers, SCD patterns, metadata framework) |
| **Modeler** | `agents/modeler.md` | Translates architecture specs into Fabric-specific blueprints (Lakehouse, Warehouse, Pipelines, Notebooks) |
| **Creator** | `agents/creator.agent.md` | Dispatcher for Phase 3 — reads blueprint, decomposes tasks, dispatches to Fabric agents in order |
| **FabricDataEngineer** | `agents/FabricDataEngineer.agent.md` | Cross-workload Fabric implementation — Spark, SQL, Pipelines, Medallion architecture |
| **FabricAdmin** | `agents/FabricAdmin.agent.md` | Workspace administration, governance, capacity, security |
| **FabricAppDev** | `agents/FabricAppDev.agent.md` | Full-stack applications consuming Fabric data (ODBC, XMLA, REST) |

## Workflow

```
Discovery → Architecture Spec → Fabric Blueprint → Deployable Artifacts
   (Architect)      (Architect)       (Modeler)    (Creator → FabricAdmin → FabricDataEngineer → FabricAppDev)
```

1. **Discovery** — Architect interviews stakeholders to understand source systems, business entities, SLAs, grain, and reporting needs.
2. **Architecture** — Architect produces `output/architecture-spec.md` with layer definitions, entity catalogue, data flow diagrams, and governance rules.
3. **Modelling** — Modeler consumes the architecture spec and produces `output/fabric-blueprint.md` with Fabric artifact mappings, DDL, notebook specs, and pipeline definitions.
4. **Creation** — `@creator` reads the blueprint, decomposes tasks, and dispatches to Fabric agents in order: `@FabricAdmin` (workspaces, governance) → `@FabricDataEngineer` (artifacts, pipelines) → `@FabricAppDev` (consuming applications).

## Folder Structure

```
AnalyticsPlatformAgents/
├── agents/                    # Agent definitions (VS Code Copilot discovers these)
│   ├── orchestrator.md
│   ├── architect.md
│   ├── modeler.md
│   ├── FabricDataEngineer.agent.md
│   ├── FabricAdmin.agent.md
│   ├── FabricAppDev.agent.md
│   └── creator.agent.md
├── .prompts/                  # Reusable prompt files
│   ├── 01-discovery.prompt.md
│   ├── 02-architecture.prompt.md
│   ├── 03-receive-handoff.prompt.md
│   └── 04-fabric-blueprint.prompt.md
├── .resources/                # Shared knowledge base
│   ├── kb-scd-fact-patterns.md
│   ├── kb-metadata-pipeline-framework.md
│   ├── kb-layered-architecture.md
│   ├── kb-fabric-artifacts.md
│   ├── kb-fabric-patterns.md
│   └── kb-fabric-datatypes.md
├── creator/                       # Fabric Creator skills & knowledge (from skills-for-fabric)
│   ├── common/                    # 9 shared knowledge files (COMMON-CORE, SPARK-*, SQLDW-*, etc.)
│   ├── skills/                    # 12 specialised skills (spark-authoring, sqldw-authoring, etc.)
│   ├── docs/                      # Skill authoring guides, architecture docs
│   ├── prompt_examples/           # Example prompts for Fabric workflows
│   └── mcp-setup/                 # MCP server configuration
├── output/                    # Generated deliverables
│   ├── architecture-spec.md
│   ├── fabric-blueprint.md
│   └── artifacts/             # Creator output (notebooks, warehouse DDL, pipelines)
│       ├── notebooks/
│       ├── warehouse/
│       └── pipelines/
└── .github/
    └── copilot-instructions.md
```

## Getting Started

1. Open this folder as a VS Code workspace.
2. Start with `@orchestrator` in Copilot Chat for a guided session, or invoke agents directly:
   - `@architect` — Run discovery and generate architecture spec
   - `@modeler` — Consume architecture spec and generate Fabric blueprint
   - `@creator` — Dispatch blueprint tasks to Fabric agents in order
   - `@FabricDataEngineer` — Implement cross-workload Fabric solutions
   - `@FabricAdmin` — Workspace governance and administration
   - `@FabricAppDev` — Build applications consuming Fabric data
3. The Fabric agents delegate to specialised skills in `creator/skills/` for endpoint-specific implementation.

## Repository Hygiene

**Temporary Folder Policy:** All agents use temporary folders outside the repository for scratch work. Agents create timestamped folders in `$env:TEMP` (Windows) or `/tmp` (Linux/Mac) for analysis, intermediate outputs, and temporary artifacts. Only final, publishable deliverables are written to `output/`.

This prevents accidental commits of sensitive data (workspace IDs, subscription IDs, tenant-specific configurations) and keeps the repository clean for public sharing.

## Creator Skills (from skills-for-fabric)

The `creator/` folder contains the official Microsoft Fabric skills from [aka.ms/skills-for-fabric):

| Skill | Purpose |
|-------|---------|
| `spark-authoring-cli` | Notebook development, Lakehouse management, PySpark engineering |
| `spark-consumption-cli` | Interactive Spark analysis and exploration |
| `sqldw-authoring-cli` | T-SQL DDL/DML, Warehouse schema, ETL scripting |
| `sqldw-consumption-cli` | Read-only T-SQL analytics and exploration |
| `eventhouse-authoring-cli` | KQL management, Eventhouse operations, ingestion |
| `eventhouse-consumption-cli` | Read-only KQL queries against Eventhouse |
| `powerbi-authoring-cli` | Semantic model creation, TMDL, refresh, permissions |
| `powerbi-consumption-cli` | DAX queries and semantic model discovery |
| `e2e-medallion-architecture` | End-to-end Bronze/Silver/Gold lakehouse patterns |
| `check-updates` | Version check for skill updates |
| `paginated-report-ops` | Paginated report operations |
| `powerbi-ibcs` | IBCS-compliant PowerBI report patterns |

## Adding More Skills

Drop additional skill folders into `creator/skills/` following the same pattern (`SKILL.md` + optional `references/` or `resources/`). Shared knowledge goes in `creator/common/`.

## Sample Outputs

The `output/` folder contains example deliverables from a Contoso Rail Visitors analytics platform design:
- `architecture-spec.md` — Three-layer architecture (Landing/Persistence/Presentation) with SCD2, metadata-driven ETL, 6 Mermaid diagrams
- `fabric-blueprint.md` — Fabric implementation with Lakehouse (L0/L1), Warehouse (L2), Notebook specs, Pipeline definitions
