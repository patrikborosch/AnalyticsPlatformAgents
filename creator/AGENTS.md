# skills-for-fabric Development Agent

> **For Skill Developers** — This file guides AI agents helping contributors create and maintain skills in this repository. If you're a **skill user** (consuming skills for Fabric development), see `compatibility/AGENTS.md` instead.

## Restrictions
Copilot can read the common folder, but *can never write* inside the common folder.
The files under /common should only be modified manually

You are an AI assistant helping developers contribute skills to the skills-for-fabric repository.

## Architecture Mode

- Repository layering: **Agents → Skills → Common**
- For cross-workload orchestration, use `agents/FabricDataEngineer.agent.md`
- Keep endpoint-specific implementation detail in `skills/`

## Quick Reference

| Topic | Document |
|-------|----------|
| **Getting started** | [CONTRIBUTING.md](CONTRIBUTING.md) |
| **Skill structure & authoring** | [docs/skill-authoring-guide.md](docs/skill-authoring-guide.md) |
| **Quality requirements** | [docs/quality-requirements.md](docs/quality-requirements.md) |
| **Existing skills** | [docs/skill-catalog.md](docs/skill-catalog.md) |
| **Repository architecture** | [docs/architecture-overview.md](docs/architecture-overview.md) |
| **Shared references** | [docs/common-folder-guide.md](docs/common-folder-guide.md) |
| **Plugin bundles** | [docs/plugins-guide.md](docs/plugins-guide.md) |
| **Security guidelines** | [SECURITY-GUIDELINES.md](SECURITY-GUIDELINES.md) |

## Key Conventions

- **Naming**: `{endpoint}-authoring-cli` (developers), `{endpoint}-consumption-cli` (consumers), or `{endpoint}-operations-cli` (diagnostics)
- **Structure**: Each skill in `skills/{name}/SKILL.md`
- **Agents**: Cross-endpoint orchestration in `agents/{persona}.agent.md` (e.g., `FabricDataEngineer`, `FabricAdmin`)
- **Quality check**: `python .github/workflows/quality_checker.py`

## Must/Avoid (Summary)

| Must | Avoid |
|------|-------|
| YAML frontmatter with `name` and `description` | Skills over 15,000 tokens |
| Update check notice (blockquote) | Overlapping trigger phrases |
| Language-tagged code blocks | Hardcoded secrets |
| Action verb in description | Copy-paste code templates |

For full details, see [docs/quality-requirements.md](docs/quality-requirements.md).
