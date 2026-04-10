## Analytics Platform Agents — Global Instructions

This workspace contains a multi-agent system for analytics platform design and implementation on Microsoft Fabric.

### Agent Team

- **@orchestrator** (`agents/orchestrator.md`) — Start here for full workflows. Coordinates: Discovery → Architecture → Modelling → Creation.
- **@architect** (`agents/architect.md`) — Designs technology-agnostic analytics architectures with layered patterns, SCD strategies, and metadata-driven pipelines.
- **@modeler** (`agents/modeler.md`) — Translates architecture specifications into Fabric-specific blueprints (Lakehouse, Warehouse, Notebooks, Pipelines). Produces agent-tagged handoff.
- **@creator** (`agents/creator.agent.md`) — Dispatcher for Phase 3. Reads blueprint, decomposes tasks, and dispatches to Fabric agents in order.
- **@FabricDataEngineer** (`agents/FabricDataEngineer.agent.md`) — Cross-workload Fabric data engineering orchestration. Works orchestrated (from @creator) or standalone (direct tasks).
- **@FabricAdmin** (`agents/FabricAdmin.agent.md`) — Workspace administration, governance, capacity, security. Works orchestrated (from @creator) or standalone.
- **@FabricAppDev** (`agents/FabricAppDev.agent.md`) — Full-stack application development consuming Fabric data. Works orchestrated (from @creator) or standalone.

### Agent Invocation Modes

**Full workflow:** `@orchestrator` → `@architect` → `@modeler` → `@creator` → `@FabricAdmin` → `@FabricDataEngineer` → `@FabricAppDev`

**Direct access:** Invoke any Fabric agent directly for ad-hoc tasks — no architecture spec or blueprint required. The agent gathers requirements conversationally.

### Shared Knowledge Base

Architect & Modeler reference files in `.resources/`:
- `kb-scd-fact-patterns.md` — SCD Type 1/2/6 and fact table patterns
- `kb-metadata-pipeline-framework.md` — Metadata-driven ETL/ELT framework
- `kb-layered-architecture.md` — L0 Landing / L1 Persistence / L2 Presentation patterns
- `kb-fabric-artifacts.md` — Fabric artifact catalogue and capabilities
- `kb-fabric-patterns.md` — Fabric implementation patterns
- `kb-fabric-datatypes.md` — Fabric-supported data types and mappings

Fabric agents (`@FabricDataEngineer`, `@FabricAdmin`, `@FabricAppDev`) reference files in `creator/`:
- `creator/common/` — 9 shared knowledge files (COMMON-CORE, COMMON-CLI, SPARK-*, SQLDW-*, EVENTHOUSE-*, ITEM-DEFINITIONS-CORE)
- `creator/skills/` — 10 specialised skills (spark-authoring-cli, sqldw-authoring-cli, eventhouse-authoring-cli, powerbi-authoring-cli, medallion-architecture, etc.)
- `creator/docs/` — Skill authoring guides, architecture overview, MCP servers guide

### Workflow Rules

1. Agents produce output into `output/` — never overwrite without user confirmation.
2. Architecture spec must exist before Modeler runs.
3. Fabric blueprint must exist before orchestrated Creation (Phase 3) runs.
4. Fabric agents can be invoked directly for standalone tasks without prerequisites.
5. Each agent validates its input before starting work.
6. Use Mermaid diagrams for all architectural visualisations.
7. In Phase 3, `@creator` dispatches: `@FabricAdmin` first (workspaces), then `@FabricDataEngineer` (artifacts), then `@FabricAppDev` (apps).

### Naming Conventions

- Output files: `output/<deliverable-name>.md`
- Generated artifacts: `output/artifacts/{notebooks,warehouse,pipelines}/`
- Knowledge base: `.resources/kb-<topic>.md`
- Prompts: `.prompts/<nn>-<name>.prompt.md` (numbered for workflow order)
