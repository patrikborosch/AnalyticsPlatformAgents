## Analytics Platform Agents — Global Instructions

This workspace contains a multi-agent system for analytics platform design and implementation on Microsoft Fabric.

### Agent Team

- **@orchestrator** (`agents/orchestrator.md`) — Start here. Coordinates the full workflow: Discovery → Architecture → Modelling → Creation.
- **@architect** (`agents/architect.md`) — Designs technology-agnostic analytics architectures with layered patterns, SCD strategies, and metadata-driven pipelines.
- **@modeler** (`agents/modeler.md`) — Translates architecture specifications into Fabric-specific blueprints (Lakehouse, Warehouse, Notebooks, Pipelines).

### Shared Knowledge Base

All agents reference files in `.resources/`:
- `kb-scd-fact-patterns.md` — SCD Type 1/2/6 and fact table patterns
- `kb-metadata-pipeline-framework.md` — Metadata-driven ETL/ELT framework
- `kb-layered-architecture.md` — L0 Landing / L1 Persistence / L2 Presentation patterns
- `kb-fabric-artifacts.md` — Fabric artifact catalogue and capabilities
- `kb-fabric-patterns.md` — Fabric implementation patterns
- `kb-fabric-datatypes.md` — Fabric-supported data types and mappings

### Workflow Rules

1. Agents produce output into `output/` — never overwrite without user confirmation.
2. Architecture spec must exist before Modeler runs.
3. Fabric blueprint must exist before Creator runs.
4. Each agent validates its input before starting work.
5. Use Mermaid diagrams for all architectural visualisations.

### Naming Conventions

- Output files: `output/<deliverable-name>.md`
- Generated artifacts: `output/artifacts/{notebooks,warehouse,pipelines}/`
- Knowledge base: `.resources/kb-<topic>.md`
- Prompts: `.prompts/<nn>-<name>.prompt.md` (numbered for workflow order)
