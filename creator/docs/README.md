# Documentation

This folder contains contributor guides, specifications, and planning documents for skills-for-fabric.

## Getting Started

New to skills-for-fabric? Start here:

1. **[Architecture Overview](architecture-overview.md)** — Understand the repository structure
2. **[Skill Authoring Guide](skill-authoring-guide.md)** — How to create a skill
3. **[Quality Requirements](quality-requirements.md)** — What makes a good skill
4. **[Testing Guide](testing-guide.md)** — How to validate your changes

## Contributor Guides

### MICROSOFT Internal 
* ### Presentation on [Fabric Skills Creator Guidelines](https://microsoft-my.sharepoint.com/:p:/p/cristp/IQAMk2UjpXoHRqh6YXPYdh0lASTthBCKK90RiExuHcsfBkQ?e=LlH489)
* ### Document with details [AISkillsGuide](https://microsoft-my.sharepoint.com/:w:/p/cristp/IQAWcfOxwVSYSKsUel3j7V5ZAbUSkh-idunkJ-buXMhDKck?e=VrwpnB)

| Guide | Purpose |
|-------|---------|
| [Architecture Overview](architecture-overview.md) | Repository structure, folder purposes, cross-references |
| [Skill Authoring Guide](skill-authoring-guide.md) | Create skills: naming, structure, descriptions, what to avoid |
| [Common Folder Guide](common-folder-guide.md) | What belongs in `common/`, CORE vs CLI pattern |
| [Plugins Guide](plugins-guide.md) | How skills are bundled into plugins |
| [Quality Requirements](quality-requirements.md) | Token limits, similarity rules, trigger disambiguation |
| [Testing Guide](testing-guide.md) | Tests to run, pre-commit hooks, CI/CD |
| [MCP Servers Guide](mcp-servers-guide.md) | MCP registration in `mcp-setup/` |
| [Skill Catalog](skill-catalog.md) | Existing skills with purpose and triggers |

## Planning Documents

| Folder | Purpose | When to Use |
|--------|---------|-------------|
| `architecture/` | Architecture Decision Records (ADRs) | Record significant technical decisions and their rationale |
| `specs/` | Feature specifications | Detail requirements before implementation |
| `rfcs/` | Request for Comments | Propose and discuss significant changes |

### Templates

- [ADR Template](architecture/_template.md)
- [Spec Template](specs/_template.md)
- [RFC Template](rfcs/_template.md)

## Project Planning

- [Roadmap](roadmap.md) — Project roadmap and skill coverage matrix

## Guidelines

### When to Write Planning Docs

- **ADR**: You made (or need to make) a technical decision that affects multiple skills or the overall architecture
- **Spec**: You're adding a new feature or skill and want to document requirements first
- **RFC**: You're proposing a significant change that needs community/team input before proceeding

### Keeping Docs Current

1. **Link to implementations** — Reference the actual code files in your docs
2. **Update on PR** — If your PR changes behavior documented here, update the docs in the same PR
3. **Mark obsolete docs** — Use `Status: Deprecated` or `Superseded by` rather than deleting

### Naming Conventions

- ADRs: `ADR-NNN-short-title.md` (e.g., `ADR-001-skill-routing-algorithm.md`)
- Specs: `feature-name.md` (e.g., `quality-checker.md`)
- RFCs: `RFC-NNN-short-title.md` (e.g., `RFC-001-multi-engine-support.md`)

## Index

### Architecture Decisions

| ID | Title | Status | Date |
|----|-------|--------|------|
| - | *No ADRs yet* | - | - |

### Specifications

| Name | Status | Related Skills |
|------|--------|----------------|
| - | *No specs yet* | - |

### RFCs

| ID | Title | Status | Author |
|----|-------|--------|--------|
| - | *No RFCs yet* | - | - |
