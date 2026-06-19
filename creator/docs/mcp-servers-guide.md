# MCP Servers Guide

Model Context Protocol (MCP) servers provide live data connections to AI assistants. This guide explains how MCP servers fit into skills-for-fabric and how to register them.

> **Before you reach for MCP**, check the policy on **when** to use it. `-cli` is the default access method for new skills, and `-cli` → `-mcp` migrations of shipped skills require an issue + core-team sign-off before the PR. See [CONTRIBUTING.md § CLI vs. MCP: Choosing an Access Method](../CONTRIBUTING.md#cli-vs-mcp-choosing-an-access-method). This guide covers the **operational** details once that decision has been made.
>
> **Remote MCP only.** When this repo says `-mcp`, we mean a **remote MCP server** -- a Fabric-hosted, workload-team-hosted, or org-hosted HTTP endpoint with its own auth/scope model. **Local stdio MCP that wraps the same `sqlcmd` / `az rest` calls a `-cli` skill already makes is rejected by default** (it loses the LLM-efficiency tradeoff without delivering any of the server-side wins that justify MCP -- see the [`-mcp` means *remote* MCP](../CONTRIBUTING.md#-mcp-means-remote-mcp) policy note for the full rationale). Some examples on this page predate that policy and show locally-spawned stdio servers (`"command": "npx"`, `--connection-string`); read them as *illustrative of MCP config shape*, not as endorsed deployment patterns for new contributions.

## What is MCP?

MCP (Model Context Protocol) is a standard for connecting AI assistants to external data sources and tools. MCP servers:

- Provide real-time access to databases, APIs, and services
- Enable AI assistants to execute queries and retrieve live data
- Run as separate processes that communicate with the AI tool

## Skills vs. MCP Servers

| Aspect | Skills | MCP Servers |
|--------|--------|-------------|
| **Purpose** | Provide knowledge and patterns | Provide data access |
| **Content** | Markdown documentation | Executable servers |
| **Runtime** | Loaded into AI context | Run as separate processes |
| **Example** | "How to query a warehouse" | "Execute this SQL query" |

**Key insight:** Skills teach the AI assistant *what to do*. MCP servers *do it*.

## The mcp-setup Folder

MCP server registration scripts and templates live in `mcp-setup/`:

```
mcp-setup/
├── README.md                    # Setup instructions
├── mcp-config-template.json     # Template for MCP configuration
├── register-fabric-mcp.ps1      # Windows registration script
└── register-fabric-mcp.sh       # macOS/Linux registration script
```

## Why MCP Config Goes Here

MCP servers should NOT be defined inside skills because:

1. **Separation of concerns** — Skills are knowledge; MCP is infrastructure
2. **Security** — MCP configs may contain connection strings or credentials
3. **Reusability** — One MCP server can serve multiple skills
4. **Maintenance** — MCP server setup is a one-time operation, not per-skill

## MCP Configuration Template

```json
{
  "mcpServers": {
    "fabric-sql": {
      "command": "npx",
      "args": [
        "-y",
        "@anthropic/mcp-server-fabric-sql",
        "--connection-string",
        "Server=<endpoint>.datawarehouse.fabric.microsoft.com;Database=<db>;Authentication=ActiveDirectoryDefault"
      ]
    },
    "fabric-spark": {
      "command": "fabric-spark-mcp",
      "args": ["--workspace-id", "<wsId>", "--lakehouse-id", "<lhId>"]
    }
  }
}
```

## Registering an MCP Server

### Prerequisites

1. The MCP server package must be installed (npm, pip, or standalone binary)
2. You need connection details for your Fabric resources
3. You need authentication configured (typically `az login`)

### Windows

```powershell
.\mcp-setup\register-fabric-mcp.ps1
```

### macOS/Linux

```bash
./mcp-setup/register-fabric-mcp.sh
```

### Manual Registration

For tools that support MCP configuration files:

1. Copy `mcp-config-template.json` to your tool's config location
2. Replace placeholders with your actual values
3. Restart the AI tool

## Adding a New MCP Server

### Create or Obtain the Server

> **Local-stdio packages (`npx -y @vendor/mcp-server-*`, `pip install mcp-server-*`, standalone binaries) are not the right shape for new contributions to this repo** -- see the remote-MCP-only note at the top. They are listed below because the historical MCP ecosystem standardized on them, but a new `-mcp` skill in skills-for-fabric should target a remote HTTP MCP endpoint.

Possible MCP server shapes (for reference):

- **Remote HTTP MCP endpoints** (preferred for this repo) -- a service the workload team or platform team hosts; the user only needs the URL and the right Entra scopes.
- Local stdio servers -- published npm packages (`@anthropic/mcp-server-*`), Python packages (`pip install mcp-server-*`), standalone binaries, custom implementations. **Discouraged for new skills-for-fabric contributions.**

### Add Registration Logic

Update the registration scripts:

**register-fabric-mcp.sh:**
```bash
# Add Fabric SQL MCP
add_mcp_server "fabric-sql" \
  "npx" \
  "-y @anthropic/mcp-server-fabric-sql --connection-string $CONN_STRING"
```

**register-fabric-mcp.ps1:**
```powershell
# Add Fabric SQL MCP
Add-McpServer -Name "fabric-sql" `
  -Command "npx" `
  -Args @("-y", "@anthropic/mcp-server-fabric-sql", "--connection-string", $connString)
```

### Update the Template

Add the new server to `mcp-config-template.json`:

```json
{
  "mcpServers": {
    "existing-server": { ... },
    "new-server": {
      "command": "...",
      "args": [...]
    }
  }
}
```

### Document in README

Update `mcp-setup/README.md` with:
- Server purpose
- Prerequisites
- Configuration options

## MCP Server Security

### Do NOT Commit Secrets

MCP configurations often contain connection strings. The template uses placeholders:

```json
{
  "args": ["--connection-string", "<YOUR_CONNECTION_STRING>"]
}
```

### Use Environment Variables

Prefer environment variables over hardcoded values:

```json
{
  "args": ["--connection-string", "${FABRIC_CONN_STRING}"]
}
```

### Rely on Azure CLI Auth

When possible, use `ActiveDirectoryDefault` which leverages `az login`:

```json
{
  "args": ["--auth-method", "ActiveDirectoryDefault"]
}
```

## Skills That Complement MCP

When an MCP server is available, skills can reference it. (Sample below uses a local stdio shape for historical reasons -- for new skills, the prerequisite would be access to a hosted MCP endpoint plus the right Entra scopes, not "install this package locally".)

```markdown
## Prerequisites

This skill works best with the Fabric SQL MCP server installed.
See [mcp-setup/README.md](../mcp-setup/README.md) for installation.

## With MCP Server

If you have `fabric-sql` MCP configured, I can execute queries directly:

> Execute: SELECT TOP 10 * FROM dbo.FactSales

## Without MCP Server

Without MCP, I'll generate sqlcmd commands for you to run:

```bash
sqlcmd -S $FABRIC_SERVER -d $FABRIC_DB -G -Q "SELECT TOP 10 * FROM dbo.FactSales"
```
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| MCP server not found | Verify the server package is installed |
| Authentication fails | Run `az login` and ensure correct tenant |
| Connection timeout | Check firewall rules, port 1433 access |
| Server crashes on startup | Check logs, verify connection string format |
| Tool doesn't recognize MCP | Verify config file location for your AI tool |

## Further Reading

- [MCP Specification](https://modelcontextprotocol.io/)
- [mcp-setup/README.md](../mcp-setup/README.md) — Detailed setup instructions
