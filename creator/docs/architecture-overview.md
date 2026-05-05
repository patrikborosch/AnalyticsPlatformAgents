# Architecture Overview

This document explains the skills-for-fabric repository structure and how all the pieces fit together.

## Why Hybrid: Agents + Skills

skills-for-fabric uses a hybrid architecture:

- **Skills** = deep, focused, single-endpoint units (one endpoint, one persona, one access method)
- **Agents** = orchestration layers for cross-endpoint and cross-cutting workflows

This design keeps single-endpoint guidance compact while still supporting end-to-end scenarios that naturally span Spark, Warehouse, Pipelines, and related workloads.

### Skill vs Agent Differentiators

| | Skill | Agent |
|---|---|---|
| Scope | Single endpoint × persona | Cross-endpoint or cross-persona |
| Composability | Self-contained | Orchestrates multiple skills |
| Depth | Deep implementation detail | Broad workflow coordination |
| Primary tool | GitHub Copilot CLI | Claude/Codex/Cursor/Windsurf |
| Growth model | Add endpoint skills | Add cross-cutting agent sections |
| Activation | Trigger-matched | Session guidance |

### Why not one omnibus agent

- It exceeds practical token budgets as workload coverage grows
- It mixes developer/analyst concerns in one context
- It introduces routing ambiguity for broad prompts
- A single failure affects all use cases

### Top-down Flow Principle

Content flows one way:

**Agents → Skills → Common**

- Agents orchestrate and delegate
- Skills provide endpoint-specific depth
- Common provides shared reference foundations

Content should not flow upward (for example, common docs should not encode orchestration policy).

## Skill vs Agent Decision Framework

Use this decision tree when adding new content:

1. **Single endpoint + single persona?** → Build/extend a **Skill**
2. **Crosses multiple workload endpoints or is cross-cutting?** → Build/extend an **Agent**
3. **Utility behavior (updates/tooling)?** → Create a **Utility Skill**
4. **None of the above?** → Add a `common/` reference document

### Two-Endpoint Test

If useful output requires knowledge of **2+ Fabric workload endpoints**, it belongs in an agent.

Do **not** count authentication and catalog/workspace discovery toward this threshold because those are universal prerequisites.

## Repository Structure

```text
AnalyticsPlatformAgents/
├── agents/                    # Agent definitions (7 agents)
│   ├── orchestrator.md
│   ├── architect.md
│   ├── modeler.md
│   ├── creator.agent.md
│   ├── FabricDataEngineer.agent.md
│   ├── FabricAdmin.agent.md
│   └── FabricAppDev.agent.md
├── .prompts/                  # Reusable prompt files (workflow phases)
├── .resources/                # Shared knowledge base (SCD, layered arch, etc.)
├── creator/                   # Fabric skills & knowledge (from skills-for-fabric)
│   ├── skills/                # 13 specialised skills
│   ├── common/                # 9 shared reference documents
│   ├── docs/                  # Contributor documentation (you are here)
│   ├── mcp-setup/             # MCP server registration scripts
│   └── prompt_examples/       # Example prompts for Fabric workflows
├── output/                    # Generated deliverables (specs, blueprints, artifacts)
└── .github/                   # Repository configuration
    └── copilot-instructions.md
```

> **Provenance note:** The `creator/` subtree was imported from the upstream [skills-for-fabric](https://github.com/TheTrustedAdvisor/skills-for-fabric) project by Bogdan Crivat. Some upstream folders (`plugins/`, `compatibility/`, `tests/`) are not present in this repository because they are not needed for the agent-based workflow here.

## Folder Purposes

### `agents/` — Agent Definitions

Each file defines one agent persona. The repo contains 7 agents in a flat structure:

```text
agents/
├── orchestrator.md              # End-to-end workflow coordinator
├── architect.md                 # Technology-agnostic analytics architecture design
├── modeler.md                   # Fabric-specific blueprint generation
├── creator.agent.md             # Phase 3 dispatcher (decomposes blueprint → agent tasks)
├── FabricDataEngineer.agent.md  # Data engineering + semantic model orchestration
├── FabricAdmin.agent.md         # Workspace administration, governance, security
└── FabricAppDev.agent.md        # Application development consuming Fabric data
```

**Key points:**
- One file = one agent persona (flat structure, no subfolders)
- Agents coordinate cross-endpoint workflows and delegate endpoint depth to skills
- Agents should avoid duplicating deep endpoint references already covered by skills/common

### `creator/skills/` — Skill Definitions

Each subfolder contains one skill with a `SKILL.md` file that defines what the AI assistant should know when that skill is invoked.

```text
skills/
└── sqldw-authoring-cli/
    ├── SKILL.md              # Main skill definition (required)
    └── references/           # Optional supporting files
        └── script-templates.md
```

**13 skills total:** spark-authoring-cli, spark-consumption-cli, sqldw-authoring-cli, sqldw-consumption-cli, eventhouse-authoring-cli, eventhouse-consumption-cli, powerbi-authoring-cli, powerbi-consumption-cli, powerbi-ibcs, paginated-report-authoring, paginated-report-ops, e2e-medallion-architecture, check-updates.

**Key points:**
- One folder = one skill
- Folder name must match the `name` field in SKILL.md frontmatter
- Skills should be focused on a specific endpoint use case, not comprehensive reference manuals

See: [Skill Authoring Guide](skill-authoring-guide.md)

### `creator/common/` — Shared Reference Documents

Contains language-agnostic and implementation-specific reference material that multiple skills can include.

| File Pattern | Purpose | Example |
|--------------|---------|---------|
| `COMMON-CORE.md` | Fabric-wide concepts (topology, auth, APIs) | Token audiences, REST patterns |
| `COMMON-CLI.md` | CLI implementation patterns | `az rest`, `curl`, `jq` recipes |
| `{ENDPOINT}-AUTHORING-CORE.md` | Authoring reference for an endpoint | T-SQL DDL/DML, KQL `.create-merge table` |
| `{ENDPOINT}-CONSUMPTION-CORE.md` | Consumption reference for an endpoint | SELECT patterns, KQL `summarize` |
| `ITEM-DEFINITIONS-CORE.md` | Fabric item definition envelope structures | Base64 payloads, platform files |

**Why common/?**
- Avoids duplication across skills
- Keeps skills focused on "how to invoke" rather than comprehensive API docs
- Single source of truth for core patterns

See: [Common Folder Guide](common-folder-guide.md)

### `creator/mcp-setup/` — MCP Server Registration

Contains scripts and templates for registering Model Context Protocol (MCP) servers.

```text
mcp-setup/
├── README.md
├── mcp-config-template.json
├── register-fabric-mcp.ps1
└── register-fabric-mcp.sh
```

**Key points:**
- MCP servers provide live data connections (databases, APIs)
- Skills provide knowledge and patterns; MCP servers provide data access
- MCP configuration goes here, NOT in skills

See: [MCP Servers Guide](mcp-servers-guide.md)

### `creator/docs/` — Contributor Documentation

You are here. Documentation for skill and agent contributors.

### `.resources/` — Knowledge Base

Shared knowledge files referenced by the Architect and Modeler agents:

| File | Topic |
|------|-------|
| `kb-scd-fact-patterns.md` | SCD Type 1/2/6 and fact table patterns |
| `kb-metadata-pipeline-framework.md` | Metadata-driven ETL/ELT framework |
| `kb-layered-architecture.md` | L0 Landing / L1 Persistence / L2 Presentation |
| `kb-fabric-artifacts.md` | Fabric artifact catalogue and capabilities |
| `kb-fabric-patterns.md` | Fabric implementation patterns |
| `kb-fabric-datatypes.md` | Fabric-supported data types and mappings |

### `.github/` — Repository Configuration

Currently contains:
- `copilot-instructions.md` — Repository-wide GitHub Copilot Chat instructions

## Cross-References

Skills reference common documents using relative paths:

```markdown
## Prerequisite Knowledge

Read these companion documents:
- [COMMON-CORE.md](../../common/COMMON-CORE.md) — Fabric REST API patterns
- [COMMON-CLI.md](../../common/COMMON-CLI.md) — CLI implementation
```

**Rules:**
- Use `../../common/` to reference common docs from skills
- Agents can reference both skills and common docs, while keeping orchestration logic in agent files

## File Organization Principles

1. **One concept, one file** — Don't mix unrelated topics
2. **Agents orchestrate** — Cross-workload concerns belong in agents
3. **Skills are focused** — Endpoint-specific use case, not encyclopedic
4. **Common is shared** — If 2+ skills need it, put it in common/
5. **MCP is separate** — Data connections go in mcp-setup/, not skills

## Next Steps

- [Skill Authoring Guide](skill-authoring-guide.md) — How to create a skill
- [Common Folder Guide](common-folder-guide.md) — When to add to common/
- [Quality Requirements](quality-requirements.md) — What makes a good skill
