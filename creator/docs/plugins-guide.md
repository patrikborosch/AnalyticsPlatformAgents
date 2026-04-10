# Plugins Guide

Plugins bundle multiple skills together for easy installation. This guide explains how plugins work and how to add skills to them.

> Plugins currently package **skills** for Copilot CLI routing. Cross-endpoint orchestration agents are maintained separately under `agents/` and reflected through compatibility files.

## Overview

skills-for-fabric offers two plugin bundles targeting different user personas:

| Plugin | Target User | Skills Included |
|--------|-------------|-----------------|
| `authoring` | Developers writing code | eventhouse-authoring-cli, sqldw-authoring-cli, spark-authoring-cli |
| `consumption` | Users exploring data | eventhouse-consumption-cli, powerbi-consumption-cli, sqldw-consumption-cli, spark-consumption-cli |

Both plugins include `check-updates` for version management.

## Folder Structure

```
plugins/
├── authoring/
│   └── plugin.json
└── consumption/
    └── plugin.json
```

## plugin.json Format

```json
{
  "name": "fabric-authoring",
  "displayName": "Microsoft Fabric Authoring Skills",
  "description": "Developer skills for authoring Microsoft Fabric solutions",
  "publisher": "microsoft",
  "version": "0.1.5",
  "skills": [
    "../../skills/check-updates",
    "../../skills/eventhouse-authoring-cli",
    "../../skills/sqldw-authoring-cli",
    "../../skills/spark-authoring-cli"
  ],
  "mcpServers": {},
  "repository": "https://github.com/gim-home/skills-for-fabric",
  "keywords": ["fabric", "microsoft-fabric", "authoring"],
  "license": "MIT"
}
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier (no spaces) |
| `displayName` | Yes | Human-readable name |
| `description` | Yes | Brief description |
| `publisher` | Yes | Publisher name |
| `version` | Yes | Semantic version (synced with root package.json) |
| `skills` | Yes | Array of relative paths to skill folders |
| `mcpServers` | No | MCP server configurations (usually empty) |
| `repository` | Yes | GitHub repository URL |
| `keywords` | No | Search keywords |
| `license` | Yes | License identifier |

## How Skills Are Bundled

### Skill Path Resolution

Skills are referenced by relative path from the plugin.json location:

```
plugins/authoring/plugin.json
    └── "../../skills/sqldw-authoring-cli"
                        │
                        ▼
        skills/sqldw-authoring-cli/SKILL.md
```

### Installation Commands

Users can install the full bundle or individual plugins:

```bash
# Full bundle (all skills)
/plugin install gim-home/skills-for-fabric

# Authoring plugin only
/plugin install gim-home/skills-for-fabric/authoring

# Consumption plugin only
/plugin install gim-home/skills-for-fabric/consumption

# Filter by endpoint
/plugin install gim-home/skills-for-fabric --filter "sqldw-*"
```

## Adding a Skill to a Plugin

### Determine the Correct Plugin

| If your skill is for... | Add to... |
|------------------------|-----------|
| Developers (DDL, DML, CI/CD, automation) | `plugins/authoring/plugin.json` |
| Users (queries, exploration, monitoring) | `plugins/consumption/plugin.json` |
| Both personas | Both plugin.json files |
| Utility (like check-updates) | Both plugin.json files |

### Add the Skill Path

Edit the appropriate `plugin.json`:

```json
{
  "skills": [
    "../../skills/check-updates",
    "../../skills/sqldw-authoring-cli",
    "../../skills/spark-authoring-cli",
    "../../skills/my-new-skill"          // Add here
  ]
}
```

### Verify the Path

Ensure the path resolves correctly:

```bash
# From plugins/authoring/
ls ../../skills/my-new-skill/SKILL.md
```

## Version Management

### Syncing Versions

All version numbers should stay in sync:

- `package.json` (root) — source of truth
- `plugins/authoring/plugin.json`
- `plugins/consumption/plugin.json`

The `sync-version.yml` workflow can automate this.

### Updating Versions

When releasing a new version:

1. Update `package.json` version
2. Update both `plugin.json` versions
3. Update `CHANGELOG.md`
4. Create a GitHub release

## MCP Servers in Plugins

The `mcpServers` field is reserved for MCP server configurations:

```json
{
  "mcpServers": {
    "fabric-sql": {
      "command": "fabric-sql-mcp",
      "args": ["--config", "~/.fabric/config.json"]
    }
  }
}
```

**Current state:** MCP servers are registered separately via `mcp-setup/` scripts. The `mcpServers` field is typically empty in skills-for-fabric plugins.

See: [MCP Servers Guide](mcp-servers-guide.md)

## Cross-Tool Compatibility

Plugins are designed for GitHub Copilot CLI. For other tools, use the compatibility files:

| Tool | Configuration |
|------|---------------|
| Claude Code | Copy `compatibility/CLAUDE.md` to project root |
| Cursor | Copy `compatibility/.cursorrules` to project root |
| Codex/Jules | Copy `compatibility/AGENTS.md` to project root |
| Windsurf | Copy `compatibility/.windsurfrules` to project root |

The install scripts (`install.ps1`, `install.sh`) automate this setup.

## Best Practices

1. **Keep plugins focused** — authoring vs. consumption distinction
2. **Include check-updates** in all plugins
3. **Use relative paths** from plugin.json location
4. **Sync versions** across all package files
5. **Test installation** after adding skills

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Skill not found after install | Verify relative path in plugin.json |
| Version mismatch warnings | Sync versions across package.json and plugin.json files |
| Skill appears in wrong plugin | Move skill reference to correct plugin.json |
