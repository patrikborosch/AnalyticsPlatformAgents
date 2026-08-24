# Analytics Platform Agents — One-Pager

> **Your AI-powered team for designing and building analytics platforms on Microsoft Fabric.**

---

## What Is This Repo?

A ready-to-use **multi-agent system** that runs inside VS Code via GitHub Copilot Chat. Open the workspace, type `@orchestrator`, and a team of specialized AI agents will walk you through designing, modelling, deploying, and operating a complete analytics platform on Microsoft Fabric — from whiteboard to production.

No boilerplate. No manual SDK wiring. Just describe what you need.

---

## The Agent Team

| Agent | What It Does | Example Prompt |
|-------|-------------|----------------|
| **@orchestrator** | Coordinates the full workflow end-to-end | *"Build an analytics platform for our sales data"* |
| **@architect** | Designs layered architectures, SCD patterns, metadata frameworks | *"Design a data platform with SCD Type 2 for customers"* |
| **@modeler** | Translates architecture into Fabric-specific blueprints | *"Generate a Fabric blueprint from the architecture spec"* |
| **@creator** | Dispatcher for Phase 3 — decomposes blueprint into agent tasks | *"Execute the fabric blueprint"* |
| **@FabricDataEngineer** | Builds the solution — Spark notebooks, SQL warehouses, pipelines, semantic models | *"Deploy the medallion architecture to my workspace"* |
| **@FabricAdmin** | Manages workspaces, governance, capacity, security, migrations | *"Document my workspace"* / *"Migrate paginated reports"* |
| **@FabricAppDev** | Builds applications consuming Fabric data (Python, ODBC, REST) | *"Build a dashboard app connected to my warehouse"* |

---

## What Can It Build?

```
Discovery → Architecture Spec → Fabric Blueprint → Deployed Artifacts
```

**From requirements to running infrastructure in one conversation:**

- **Lakehouse & Warehouse** setup with proper layer separation (Landing / Persistence / Presentation)
- **PySpark notebooks** for ingestion, SCD2 merges, incremental loads, quality checks
- **Warehouse DDL** with schemas, tables, stored procedures, and seed data
- **Pipelines** for orchestration with metadata-driven execution
- **Power BI** semantic models (TMDL) and reports (PBIR) — authored and deployed
- **Eventhouse** (KQL) real-time analytics pipelines
- **Medallion architecture** end-to-end with a single prompt
- **Paginated report migration** from on-prem PBIRS to Fabric (data source repointing + import)
- **Tenant scanning** — discover, analyze, and map dependencies across your entire Fabric tenant

---

## 13 Specialized Skills

The agents delegate to battle-tested skills for endpoint-specific work, most of them derived from the [AI Skills in Microsoft Fabric](https://blog.fabric.microsoft.com/en-us/blog/introducing-ai-skills-in-microsoft-fabric-now-in-public-preview?ft=Bogdan%20Crivat:author) project by Bogdan Crivat and some built during some vibe coding sessions:

| Skill | What It Does |
|-------|-------------|
| `spark-authoring-cli` | Workspace, lakehouse, and notebook management via REST API |
| `spark-consumption-cli` | Interactive lakehouse data analysis via Livy sessions |
| `sqldw-authoring-cli` | Warehouse DDL, DML, ingestion, and stored procedures |
| `sqldw-consumption-cli` | Read-only T-SQL queries against Fabric warehouses |
| `eventhouse-authoring-cli` | KQL table management, ingestion, and streaming |
| `eventhouse-consumption-cli` | Real-time KQL queries against Eventhouse |
| `powerbi-authoring-cli` | Create and deploy semantic models and reports |
| `powerbi-consumption-cli` | Query semantic models, manage refreshes |
| `powerbi-ibcs` | IBCS-compliant chart design patterns |
| `e2e-medallion-architecture` | Full Bronze/Silver/Gold implementation |
| `paginated-report-authoring` | Author paginated reports (.rdl) from scratch |
| `paginated-report-ops` | PBIRS → Fabric migration (export, repoint, import .rdl) |
| `check-updates` | Auto-check for skill updates from marketplace |

---

## Built-In Knowledge Base

Agents don't just generate code — they reference curated knowledge files:

- **SCD & fact patterns** — Type 1/2/6, incremental loads, snapshots
- **Metadata-driven pipeline framework** — config tables, audit trails, retry logic
- **Layered architecture** — L0 Landing / L1 Persistence / L2 Presentation
- **Fabric artifact catalogue** — what each item type can and cannot do
- **Fabric data types** — mapping rules from source systems to Fabric

---

## Getting Started (2 Minutes)

1. **Clone** the repo → [`github.com/patrikborosch/AnalyticsPlatformAgents`](https://github.com/patrikborosch/AnalyticsPlatformAgents)
2. **Open** the folder in VS Code
3. **Ensure** [GitHub Copilot Chat](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot-chat) is installed
4. **Type** `@orchestrator` in Copilot Chat and describe your analytics scenario
5. **Watch** the agents collaborate — architecture spec → blueprint → deployed artifacts

That's it. The agents handle the rest.

---

## Example Prompts to Try

| Prompt | What Happens |
|--------|-------------|
| *"@orchestrator Build a sales analytics platform with daily incremental loads"* | Full 4-phase workflow: discovery → architecture → blueprint → deployment |
| *"@FabricDataEngineer Deploy a medallion architecture in my workspace"* | Creates lakehouses, notebooks, warehouse, and pipeline in one go |
| *"@FabricAdmin Document my workspace"* | Scans workspace items, lineage, business logic — produces a summary |
| *"@FabricAdmin Migrate paginated reports from C:\PBIRS to Fabric"* | Repoints .rdl data sources and imports into a workspace folder |
| *"@FabricAppDev Build a Python app that queries my warehouse"* | Generates connection code, parameterized queries, and data access layer |
| *"@architect Design a data platform with SCD Type 2 for 5 source systems"* | Produces a full architecture spec with layer design and entity catalogue |

---

## Repo Structure at a Glance

```
agents/          7 agent definitions (orchestrator, architect, modeler, creator, engineer, admin, appdev)
creator/
  ├── skills/    13 specialized skills with tested workflows
  ├── common/    9 shared knowledge files (Spark, SQL, KQL, CLI patterns)
  └── docs/      Guides for authoring new skills and extending the system
.resources/      6 knowledge base files (SCD patterns, layered arch, Fabric artifacts)
output/          Runtime target for agent deliverables (gitignored)
```

---

*Open the workspace. Talk to the agents. Ship your analytics platform.*
