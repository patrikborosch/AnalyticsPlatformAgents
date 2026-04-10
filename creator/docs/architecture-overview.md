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
skills-for-fabric/
├── agents/                    # Cross-workload orchestration definitions
│   ├── FabricDataEngineer.agent.md
│   └── FabricAdmin.agent.md
├── skills/                    # Individual skill definitions
│   ├── check-updates/
│   ├── eventhouse-authoring-cli/
│   ├── eventhouse-consumption-cli/
│   ├── powerbi-authoring-cli/
│   ├── powerbi-consumption-cli/
│   ├── spark-authoring-cli/
│   ├── spark-consumption-cli/
│   ├── sqldw-authoring-cli/
│   └── sqldw-consumption-cli/
├── common/                    # Shared reference documents
│   ├── COMMON-CORE.md
│   ├── COMMON-CLI.md
│   └── {ENDPOINT}-{AUTHORING|CONSUMPTION}-CORE.md
├── plugins/                   # Skill bundles for distribution
│   ├── authoring/
│   └── consumption/
├── mcp-setup/                 # MCP server registration scripts
├── compatibility/             # Cross-tool configuration files
├── tests/                     # Quality and routing tests
├── docs/                      # Contributor documentation
└── .github/                   # CI/CD, hooks, meta-skills
```

## Folder Purposes

### `agents/` — Agent Definitions

Each file defines one agent persona for cross-endpoint orchestration.

```text
agents/
├── FabricDataEngineer.agent.md   # Data engineering orchestration agent
└── FabricAdmin.agent.md        # Fabric administration agent
```

**Key points:**
- One file = one agent persona (flat structure, no subfolders)
- Agents coordinate cross-endpoint workflows and delegate endpoint depth to skills
- Agents should avoid duplicating deep endpoint references already covered by skills/common

### `skills/` — Skill Definitions

Each subfolder contains one skill with a `SKILL.md` file that defines what the AI assistant should know when that skill is invoked.

```text
skills/
└── sqldw-authoring-cli/
    ├── SKILL.md              # Main skill definition (required)
    └── references/           # Optional supporting files
        └── script-templates.md
```

**Key points:**
- One folder = one skill
- Folder name must match the `name` field in SKILL.md frontmatter
- Skills should be focused on a specific endpoint use case, not comprehensive reference manuals

See: [Skill Authoring Guide](skill-authoring-guide.md)

### `common/` — Shared Reference Documents

Contains language-agnostic and implementation-specific reference material that multiple skills can include.

| File Pattern | Purpose | Example |
|--------------|---------|---------|
| `COMMON-CORE.md` | Fabric-wide concepts (topology, auth, APIs) | Token audiences, REST patterns |
| `COMMON-CLI.md` | CLI implementation patterns | `az rest`, `curl`, `jq` recipes |
| `{ENDPOINT}-AUTHORING-CORE.md` | Authoring reference for an endpoint | T-SQL DDL/DML, KQL `.create-merge table` |
| `{ENDPOINT}-CONSUMPTION-CORE.md` | Consumption reference for an endpoint | SELECT patterns, KQL `summarize` |

**Why common/?**
- Avoids duplication across skills
- Keeps skills focused on "how to invoke" rather than comprehensive API docs
- Single source of truth for core patterns

See: [Common Folder Guide](common-folder-guide.md)

### `plugins/` — Skill Bundles

Groups skills into installable bundles for different user personas.

```text
plugins/
├── authoring/
│   └── plugin.json           # References developer-focused skills
└── consumption/
    └── plugin.json           # References consumer-focused skills
```

**plugin.json** defines which skills are included in each bundle:
```json
{
  "name": "fabric-authoring",
  "skills": [
    "../../skills/check-updates",
    "../../skills/eventhouse-authoring-cli",
    "../../skills/sqldw-authoring-cli",
    "../../skills/spark-authoring-cli"
  ]
}
```

> Plugins currently package **skills** for Copilot CLI routing. Agents are maintained separately in `agents/` for cross-tool orchestration.

See: [Plugins Guide](plugins-guide.md)

### `mcp-setup/` — MCP Server Registration

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

### `compatibility/` — Cross-Tool Configuration

Configuration files for AI coding tools other than GitHub Copilot CLI.

| File | Tool |
|------|------|
| `CLAUDE.md` | Claude Code |
| `.cursorrules` | Cursor |
| `AGENTS.md` | Codex, Jules, OpenCode |
| `.windsurfrules` | Windsurf |

These files are copied to project roots to provide agent/skill-compatible behavior in other tools.

### `tests/` — Quality and Routing Tests

Automated tests to validate skill quality and correct routing.

| File | Purpose |
|------|---------|
| `test_semantic.py` | Validates naming conventions, description similarity, triggers |
| `test_skill_routing.py` | Verifies prompts route to correct skills |
| `conftest.py` | Shared pytest fixtures |

See: [Testing Guide](testing-guide.md)

### `docs/` — Contributor Documentation

You are here. Documentation for skill and agent contributors.

### `.github/` — CI/CD and Automation

| Folder/File | Purpose |
|-------------|---------|
| `workflows/quality-check.yml` | PR quality checks |
| `workflows/quality_checker.py` | Quality validation script |
| `workflows/security-audit.yml` | Security scanning |
| `hooks/pre-commit` | Local pre-commit hook |
| `skills/` | Meta-skills for repo contributors |
| `copilot-instructions.md` | Repository-wide Copilot instructions |

## Cross-References

Skills reference common documents using relative paths:

```markdown
## Prerequisite Knowledge

Read these companion documents:
- [COMMON-CORE.md](../../common/COMMON-CORE.md) — Fabric REST API patterns
- [COMMON-CLI.md](../../common/COMMON-CLI.md) — CLI implementation
```

**Rules:**
- All relative links are validated by the quality checker
- Broken references block PR merges
- Use `../../common/` to reference common docs from skills
- Agents can reference both skills and common docs, while keeping orchestration logic in agent files

## Tooling Insight

GitHub Copilot CLI provides native skill routing. Other tools (Claude, Cursor, Codex, Windsurf) are best served by agent-style instruction layering. The hybrid architecture supports both pathways without duplicating all endpoint detail at the top layer.

## File Organization Principles

1. **One concept, one file** — Don't mix unrelated topics
2. **Agents orchestrate** — Cross-workload concerns belong in agents
3. **Skills are focused** — Endpoint-specific use case, not encyclopedic
4. **Common is shared** — If 2+ skills need it, put it in common/
5. **Plugins are bundles** — Group skills by persona
6. **MCP is separate** — Data connections go in mcp-setup/, not skills
7. **Tests validate quality** — Every PR runs quality checks

## Next Steps

- [Skill Authoring Guide](skill-authoring-guide.md) — How to create a skill
- [Common Folder Guide](common-folder-guide.md) — When to add to common/
- [Quality Requirements](quality-requirements.md) — What makes a good skill
