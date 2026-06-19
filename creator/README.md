# Microsoft Fabric Skills

AI coding assistant skills for Microsoft Fabric developers and consumers. Optimized for GitHub Copilot CLI, with cross-compatibility for Claude Code, VS Code Copilot, Cursor, and other AI coding tools.


## How you can use Fabric Skills (CLI/Claude Code/VSCode prompts)


- **[Analytics PDF report](prompt_examples/NYC_AnalyzeExistingDataCreatePDF.txt)** -- Analyzes Fabric data and produces a PDF report
- **[Document My Workspace](prompt_examples/DocumentMyWorkspace.txt)** -- Inventories the artifacts in a named Fabric workspace and produces a written summary
- **[NYC Taxi - Fabric Medallion Project](prompt_examples/NYCTaxi_MedallionArchitecture.txt)** -- Downloads a public dataset, prepares it in Spark and creates T-SQL 
views for consumption
- **[Dashboard App](prompt_examples/DashboardApp.txt)** -- Generates an interactive dashboard which connects to Fabric data



## Installation

### GitHub Copilot CLI (Recommended)

**ALWAYS START WITH THIS: connect to the Fabric Skills Marketplace:**
```bash
/plugin marketplace add gim-home/skills-for-fabric
```

**Full bundle (all skills except the `powerbi-report-*` set):**
```bash
/plugin install fabric-skills@fabric-collection 
```

**Install by persona:**
```bash
# Developers only - SDKs, APIs, automation, CI/CD
/plugin install fabric-authoring@fabric-collection 

# Consumers only - interactive queries, exploration, monitoring
/plugin install fabric-consumption@fabric-collection 

# Power BI Developers only - semantic models, reports, pbip
/plugin install powerbi-authoring@fabric-collection 
```

**Filter by endpoint/engine (within any plugin):**
```bash
/plugin install fabric-skills@fabric-collection  --filter "sqldw-*"
/plugin install fabric-skills@fabric-collection  --filter "spark-*"
/plugin install fabric-skills@fabric-collection  --filter "eventhouse-*"
```

### Manual Installation

1. Clone this repository
2. Add the marketplace from your local clone:
   ```bash
   copilot plugin marketplace add /path/to/skills-for-fabric
   copilot plugin install fabric-skills@fabric-collection
   ```




## Skills Overview

### Authentication

All Fabric operations require Azure AD authentication:

```bash
az login
az account get-access-token --resource https://api.fabric.microsoft.com
```


### Developer Skills (`-authoring-`)

For developers writing code - uses REST APIs for management, protocol-specific connections for data access.

| Skill | Pattern |
|-------|---------|
| `activator-authoring-cli` | Create and manage Fabric Activator / Reflex alerts, rules, and actions via Fabric REST APIs and `az rest` |
| `sqldw-authoring-cli` | Author Warehouses, Lakehouse SQL Endpoints, and Mirrored Databases from CLI environments |
| `spark-authoring-cli` | Develop Microsoft Fabric Spark/data engineering workflows with intelligent routing to specialized resources, including Materialized Lake View authoring and refresh patterns |
| `eventhouse-authoring-cli` | Execute KQL management commands (table management, ingestion, policies, materialized views, functions) against Fabric Eventhouse and KQL Databases via `az rest` |
| `semantic-model-authoring` | Create, manage, deploy, and tune Power BI semantic models |

#### Power BI Report Developer Skills (ships separately in `powerbi-authoring@fabric-collection`)

The Power BI report developer skills not included in the `fabric-authoring` bundle. Install the `powerbi-authoring` plugin to get them:

```bash
/plugin install powerbi-authoring@fabric-collection 
```

| Skill | Pattern |
|-------|---------|
| `powerbi-report-planning` | Plan Power BI reports from requirements through approved report specs before PBIR authoring |
| `powerbi-report-design` | Produce Power BI report design briefs, visual layout guidance, chart choices, themes, and accessibility direction |
| `powerbi-report-authoring` | Create and modify local Power BI PBIR/PBIP report pages, visuals, filters, themes, and validation workflows |
| `powerbi-report-management` | Manage Fabric Power BI report items and PBIR definitions with create, download, update, publish, and delete workflows |
| `semantic-model-authoring` | Create, manage, deploy, and tune Power BI semantic models |

### Consumer Skills (`-consumption-`)

For interactive operations via MCP servers - no SDK/driver setup needed.

| Skill | Description |
|-------|-------------|
| `activator-consumption-cli` | Inspect existing Fabric Activator / Reflex alerts, definitions, rules, sources, and actions via read-only REST API workflows |
| `semantic-model-consumption` | Execute DAX queries against Power BI semantic models via MCP server for metadata discovery and data retrieval |
| `fabriciq` | Query Power BI data through the Fabric MCP endpoint -- discover artifacts, inspect schemas, resolve values, generate and execute DAX queries |
| `sqldw-consumption-cli` | Query Warehouses, Lakehouse SQL Endpoints, and Mirrored Databases from CLI environments |
| `sqldw-operations-cli` | Analyze Fabric Data Warehouse performance and diagnose slow queries via CLI using sqlcmd and queryinsights views |
| `spark-consumption-cli` | Query and analyze Microsoft Fabric Lakehouse tables |
| `eventhouse-consumption-cli` | Run read-only KQL queries against Fabric Eventhouse and KQL Databases via `az rest` |

### Operations Skills

| Skill | Description |
|-------|-------------|
| `sqldw-operations-cli` | Analyze Fabric Data Warehouse performance and diagnose slow queries via CLI using sqlcmd and queryinsights views |
| `spark-operations-cli` | Diagnose Spark job failures, monitor Livy session health, analyze performance bottlenecks, and triage pipeline run failures using Spark Monitoring APIs |

### Utility Skills

| Skill | Description |
|-------|-------------|
| `check-updates` | Automatically checks for marketplace updates at session start |

### Agents

For cross-workload orchestration, skills-for-fabric now includes agent definitions:

| Agent | Purpose |
|-------|---------|
| `FabricDataEngineer` | Orchestrate medallion architecture, ETL/ELT, migration, and data quality workflows across Spark, SQL, and KQL skills |
| `FabricAdmin` | Manage capacity planning, governance, security, cost optimization, and observability across the Fabric tenant |
| `FabricIQ` | Answer business questions backed by Power BI data -- discover reports, inspect schemas, resolve values, generate DAX, and present insights |

Agents and their resources live in `agents/`. See [Architecture Overview](docs/architecture-overview.md) for the skill-vs-agent decision framework.

## Automatic Update Checking

skills-for-fabric includes automatic update checking. At the start of each session, the first skill invoked will:

1. Check the [GitHub releases](https://github.com/gim-home/skills-for-fabric/releases) for the latest version
2. Compare against your installed version (from `package.json`)
3. If an update is available, display the changelog and provide update commands

This check runs **once per session** and is non-blocking -- you can continue using skills even if you choose not to update.

To manually check for updates:
```bash
# GitHub Copilot CLI
/fabric-skills:check-updates
```

## Cross-Tool Compatibility

These skills work with multiple AI coding tools. The canonical sources for the
non-Copilot tools live under `compatibility/` in this internal repo and are
**flattened to the project root** of the public repo (`microsoft/skills-for-fabric`)
by the release flow -- so end users get them automatically when they clone the
public repo. (User-facing copy lives in [`public/README.md`](public/README.md).)

| Tool | Internal source | Public-repo location (after clone) |
|------|-----------------|------------------------------------|
| GitHub Copilot CLI | n/a | Automatic via plugin system |
| VS Code Copilot | n/a | Automatic via `.github/skills/` |
| Claude Code | `compatibility/CLAUDE.md` | `CLAUDE.md` |
| Cursor | `compatibility/.cursorrules` | `.cursorrules` |
| Codex / Jules | `compatibility/AGENTS.md` | `AGENTS.md` |
| Windsurf | `compatibility/.windsurfrules` | `.windsurfrules` |
| Gemini CLI | `compatibility/GEMINI.md` | `GEMINI.md` |

Contributors editing these files: update `compatibility/<file>` only -- never
add a duplicate at the internal repo root. The internal repo's root `AGENTS.md`
is a separate, contributor-only file (matching `.github/copilot-instructions.md`
for Copilot) and is replaced by the user-facing version on publish.

## MCP Server Registration

If you have Fabric MCP servers (built separately), use the scripts in `mcp-setup/` to register them:

```bash
# Windows
.\mcp-setup\register-fabric-mcp.ps1

# macOS/Linux
./mcp-setup/register-fabric-mcp.sh
```

See [mcp-setup/README.md](mcp-setup/README.md) for details.

## Security & Responsible AI

### Security

skills-for-fabric implements focused security controls:

- ✅ **Secret Scanning**: TruffleHog + Gitleaks detect credentials
- ✅ **Prompt Injection Protection**: Automated scanning for dangerous patterns

**Report security vulnerabilities**: See [SECURITY.md](SECURITY.md)

**Optional Advanced Checks** (disabled by default, available as `.disabled` files):
- CodeQL SAST scanning
- Dependency review and Dependabot
- Python/Markdown/YAML linting
- CI test automation
- OpenSSF Scorecard

### Responsible AI

Skills are designed to resist prompt injection and other AI-specific attacks:

- Clear separation of instructions vs user content
- Input validation and sanitization
- No arbitrary code execution
- Secret redaction in outputs
- Red-team tested against OWASP LLM Top 10

**Learn more**: [docs/compliance/RAI_THREAT_MODEL.md](docs/compliance/RAI_THREAT_MODEL.md)

### Data Handling

- Skills process data locally or through authenticated Fabric APIs
- No data sent to third parties
- Credentials managed through Azure AD / GitHub Secrets
- Audit logging for tool executions

## Reporting Issues & Bugs

If you encounter errors, unexpected behavior, or failures while using Fabric Skills, please file a structured issue:

**[Submit a Bug Report](https://github.com/gim-home/skills-for-fabric/issues/new?template=fabric_skills_bug.yml)**

When submitting, you will be required to provide:
- Detailed problem description and reproduction steps
- Full error output (untruncated)
- Complete Copilot CLI execution trace
- Environment details (OS, PowerShell version, CLI versions)

> **Note**: Use your Microsoft EMU GitHub account and do not include secrets or tokens in issue reports. For security vulnerabilities, report privately via [SECURITY.md](SECURITY.md).

## Contributing

**Start here:** [CONTRIBUTING.md](CONTRIBUTING.md) -- the full guide for adding or modifying skills.

### 6-step critical path for your first PR

1. Read [CONTRIBUTING.md](CONTRIBUTING.md) (full TL;DR at the top) and [Skill Authoring Guide](docs/skill-authoring-guide.md).
2. Fork the repo and write your skill under `skills/<your-skill-name>/SKILL.md`.
3. From the repo root in Copilot CLI, invoke **[`/pre-pr-check`](.github/skills/pre-pr-check/SKILL.md)** -- walks you through quality lint + ephemeral smoke + filtered full-eval for the skills you changed.
4. Then invoke **[`/pre-pr-review`](.github/skills/pre-pr-review/SKILL.md)** -- runs a cross-verified self-review against the same checklist maintainers / bots use.
5. Push and open your PR. CI auto-runs Skill PR Validation + PR-touched smoke + PR-touched full-eval; results land as sticky comments.
6. Briefly note any manual checks CI doesn't run in the PR description -- trigger-overlap pair scores for multi-skill PRs, baseline-no-skills delta for new skills, tenant-specific repro.

Running steps 3 + 4 before pushing typically eliminates 80%+ of bot / reviewer round-trips.

### What CI enforces

- All tests pass
- Security scans pass
- Code owner approval
- No hardcoded secrets
- Prompt injection resistance
- Skill ownership manifest + coverage policy (per-skill smoke / eval thresholds)

## Documentation

### For Users
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
- [SECURITY.md](SECURITY.md) - Security policy and reporting
- [SUPPORT.md](SUPPORT.md) - Getting help

### For Maintainers
- [docs/compliance/RAI_THREAT_MODEL.md](docs/compliance/RAI_THREAT_MODEL.md) - AI security threats and mitigations
- [docs/compliance/SECURITY_BASELINE.md](docs/compliance/SECURITY_BASELINE.md) - Supply chain security
- [docs/compliance/REPO_GUARDRAILS.md](docs/compliance/REPO_GUARDRAILS.md) - Repository configuration guide

### Reference
- [Fabric REST APIs](https://learn.microsoft.com/en-us/rest/api/fabric/articles/)
- [Microsoft Fabric Documentation](https://learn.microsoft.com/en-us/fabric/)

## License

MIT
