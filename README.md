# AnalyticsPlatformAgents

A multi-agent system for designing and implementing analytics platforms on Microsoft Fabric.

## Agent Team

| Agent | File | Role |
|-------|------|------|
| **Orchestrator** | `agents/orchestrator.md` | Coordinates the end-to-end workflow across all agents |
| **Architect** | `agents/architect.md` | Designs technology-agnostic analytics architectures (layers, SCD patterns, metadata framework) |
| **Modeler** | `agents/modeler.md` | Translates architecture specs into Fabric-specific blueprints (Lakehouse, Warehouse, Pipelines, Notebooks) |
| **Creator** | *(add externally)* | Generates deployable Fabric artifacts from blueprints |

## Workflow

```
Discovery → Architecture Spec → Fabric Blueprint → Deployable Artifacts
   (Architect)      (Architect)       (Modeler)         (Creator)
```

1. **Discovery** — Architect interviews stakeholders to understand source systems, business entities, SLAs, grain, and reporting needs.
2. **Architecture** — Architect produces `output/architecture-spec.md` with layer definitions, entity catalogue, data flow diagrams, and governance rules.
3. **Modelling** — Modeler consumes the architecture spec and produces `output/fabric-blueprint.md` with Fabric artifact mappings, DDL, notebook specs, and pipeline definitions.
4. **Creation** — Creator (added separately) generates deployable artifacts into `output/artifacts/`.

## Folder Structure

```
AnalyticsPlatformAgents/
├── agents/                    # Agent definitions (VS Code Copilot discovers these)
│   ├── orchestrator.md
│   ├── architect.md
│   └── modeler.md
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
3. Add Creator agents by placing their definition in `agents/` and their knowledge base in `.resources/`.

## Adding Creator Agents

Drop the agent `.md` file into `agents/` and any supporting knowledge base files into `.resources/`. The orchestrator will automatically recognise new team members listed in its configuration. Update the orchestrator's team table if needed.

## Sample Outputs

The `output/` folder contains example deliverables from a Swiss Railway Visitors analytics platform design:
- `architecture-spec.md` — Three-layer architecture (Landing/Persistence/Presentation) with SCD2, metadata-driven ETL, 6 Mermaid diagrams
- `fabric-blueprint.md` — Fabric implementation with Lakehouse (L0/L1), Warehouse (L2), Notebook specs, Pipeline definitions
