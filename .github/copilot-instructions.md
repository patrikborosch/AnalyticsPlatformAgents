## Analytics Platform Agents — Global Instructions

This workspace contains a multi-agent system for analytics platform design and implementation on Microsoft Fabric.

### Agent Team

- **@orchestrator** (`agents/orchestrator.md`) — Start here for full workflows. Coordinates: Requirements → Architecture → Modelling → Creation.
- **@requirements** (`agents/requirements.md`) — Elicits and documents business requirements in plain language before any technical design begins. Produces `output/requirements.md` with use case backlog, source inventory, NFRs, acceptance criteria (`AC-nnn`), and architect handoff. Owns the Definition of Done (DoD-R) for Phase 0.
- **@architect** (`agents/architect.md`) — Designs technology-agnostic analytics architectures with layered patterns, SCD strategies, and metadata-driven pipelines. Reads `output/requirements.md` as primary input.
- **@modeler** (`agents/modeler.md`) — Translates architecture specifications into Fabric-specific blueprints (Lakehouse, Warehouse, Notebooks, Pipelines). Produces agent-tagged handoff.
- **@creator** (`agents/creator.agent.md`) — Dispatcher for Phase 3. Reads blueprint, decomposes tasks, and dispatches to Fabric agents in order.
- **@validator** (`agents/validator.md`) — Phase 4 independent judge. Executes validation gates G0–G5 against the acceptance criteria, issues binary verdicts with evidence, and routes failures back to the agent that owns the root cause. Never fixes anything itself.
- **@FabricDataEngineer** (`agents/FabricDataEngineer.agent.md`) — Cross-workload Fabric data engineering orchestration. Works orchestrated (from @creator) or standalone (direct tasks).
- **@FabricAdmin** (`agents/FabricAdmin.agent.md`) — Workspace administration, governance, capacity, security. Works orchestrated (from @creator) or standalone.
- **@FabricAppDev** (`agents/FabricAppDev.agent.md`) — Full-stack application development consuming Fabric data. Works orchestrated (from @creator) or standalone.
- **@FabricIQ** (`agents/FabricIQ.agent.md`) — Answers data questions about Power BI reports and semantic models: discovers artifacts, inspects schemas, generates and executes DAX. Standalone.
- **@FabricMigrationEngineer** (`agents/FabricMigrationEngineer.agent.md`) — Orchestrates end-to-end workload migration to Fabric from Synapse, HDInsight, or Databricks. Standalone.

### Agent Invocation Modes

**Full workflow:** `@orchestrator` → `@requirements` → `@architect` → `@modeler` → `@creator` → `@FabricAdmin` → `@FabricDataEngineer` → `@FabricAppDev` → `@validator`

The workflow is a **loop, not a waterfall**. `@validator` is the only agent authorised to send work backwards, and it routes each failure to the phase that owns the root cause: requirements, architecture, blueprint, or implementation.

**Direct access:** Invoke any Fabric agent directly for ad-hoc tasks — no architecture spec or blueprint required. The agent gathers requirements conversationally.

### Shared Knowledge Base

Architect & Modeler reference files in `.resources/`:
- `kb-scd-fact-patterns.md` — SCD Type 1/2/6 and fact table patterns
- `kb-metadata-pipeline-framework.md` — Metadata-driven ETL/ELT framework
- `kb-layered-architecture.md` — L0 Landing / L1 Persistence / L2 Presentation patterns
- `kb-fabric-artifacts.md` — Fabric artifact catalogue and capabilities
- `kb-fabric-patterns.md` — Fabric implementation patterns
- `kb-fabric-datatypes.md` — Fabric-supported data types and mappings
- `kb-validation-assertions.md` — Technology-agnostic assertion library used by `@modeler` (binding) and `@validator` (execution)

Fabric agents (`@FabricDataEngineer`, `@FabricAdmin`, `@FabricAppDev`) reference files in `creator/`:
- `creator/common/` — 9 shared knowledge files (COMMON-CORE, COMMON-CLI, SPARK-*, SQLDW-*, EVENTHOUSE-*, ITEM-DEFINITIONS-CORE)
- `creator/skills/` — 13 specialised skills (spark-authoring-cli, sqldw-authoring-cli, eventhouse-authoring-cli, powerbi-authoring-cli, powerbi-ibcs, paginated-report-authoring, paginated-report-ops, e2e-medallion-architecture, etc.)
- `creator/docs/` — Skill authoring guides, architecture overview, MCP servers guide

### Workflow Rules

1. Agents produce output into `output/` — never overwrite without user confirmation.
2. Requirements document should exist before Architect runs (recommended but not mandatory for ad-hoc tasks). Phase 0 completeness is governed by the Definition of Done (DoD-R) in `agents/requirements.md` — the single source of truth, not duplicated elsewhere.
3. Requirement IDs (`UC-nnn`, `FR-nnn`, `NFR-nnn`, `S-nnn`, `E-nnn`, `AC-nnn`, `A-nnn`, `R-nnn`, `Q-nnn`) are assigned in Phase 0 and must be carried forward by every downstream agent. Never renumber an existing ID.
4. Architecture spec must exist before Modeler runs.
5. Fabric blueprint must exist before orchestrated Creation (Phase 3) runs, and must include Validation Specifications binding every `AC-nnn` to an executable assertion.
6. Run the G0 pre-flight (`@validator` in `static` mode) before deploying anything — it needs no tenant access and catches platform-illegal specifications while they are still free to fix.
7. Fabric agents can be invoked directly for standalone tasks without prerequisites.
8. Each agent validates its input before starting work.
9. Use Mermaid diagrams for all architectural visualisations.
10. In Phase 3, `@creator` dispatches: `@FabricAdmin` first (workspaces), then `@FabricDataEngineer` (artifacts), then `@FabricAppDev` (apps).
11. Phase 3 is complete when `@validator` returns `VALIDATED` — not when the build agents report completion. "Deployed" and "working" are different claims.
12. No agent validates its own work. `@validator` writes no artifacts; builders issue no verdicts.
13. `NOT VALIDATED` (criteria unproven) is reported as its own outcome. Never round it up to success because nothing visibly failed.
14. A failing assertion is never resolved by relaxing the criterion. Requirements change only by explicit, recorded business decision.

### Temporary Folder Management

**CRITICAL REPOSITORY HYGIENE:** All agents must use temporary folders outside the repository structure for scratch work, analysis, and intermediate outputs.

- **Required:** Use `$env:TEMP` (Windows) or `/tmp` (Linux/Mac) for all temporary work
- **Pattern:** Create timestamped subfolders: `$env:TEMP\AnalyticsPlatform_<timestamp>_<agent>`
- **Behavior:** Log temp folder location at start; clean up or inform user after completion
- **Repository writes:** Only for final deliverables: `output/requirements.md`, `output/architecture-spec.md`, `output/fabric-blueprint.md`, `output/artifacts/`, `output/validation-report.md`, `output/validation-ledger.md`
- **Forbidden:** Creating temporary folders inside the repository (prevents accidental commits of sensitive/temporary data)

### Example Data - This Repository Is Public. All examples use synthetic identifiers of the form `00000000-0000-4000-8000-0000000000NN` and fictional names only; never commit real identifiers, credentials, tokens, or local paths. `.github/workflows/tenant-data-scan.yml` enforces the GUID, credential, and token rules on every push and pull request; neutral naming remains a human responsibility.

### Naming Conventions

- Output files: `output/<deliverable-name>.md`
- Generated artifacts: `output/artifacts/{notebooks,warehouse,pipelines}/`
- Knowledge base: `.resources/kb-<topic>.md`
- Prompts: `.prompts/<nn>-<name>.prompt.md` (numbered for workflow order)
