# Changelog

All notable changes to the skills-for-fabric marketplace will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- New `skills/eventhouse-consumption-cli/` — Read-only KQL queries against Fabric Eventhouse and KQL Databases via `az rest`
- New `skills/eventhouse-authoring-cli/` — KQL management commands (table management, ingestion, policies, materialized views, functions) via `az rest`
- New `common/EVENTHOUSE-CONSUMPTION-CORE.md` — KQL query patterns, operators, data types, performance best practices
- New `common/EVENTHOUSE-AUTHORING-CORE.md` — KQL management command reference, policies, ingestion patterns, schema evolution
- Updated `agents/FabricDataEngineer.agent.md` with KQL skill delegation
- Updated compatibility files (AGENTS.md, CLAUDE.md, .cursorrules, .windsurfrules) with KQL patterns and skill references
- New `agents/FabricDataEngineer.agent.md` data engineering orchestration agent for medallion resource guidance.
- New `agents/FabricAdmin.agent.md` administration orchestration agent for capacity, governance, cost optimization, and workspace documentation.
- New `agents/FabricAppDev.agent.md` application developer agents, for building applications connected to Fabric 
- **Consumer Skills**: `powerbi-consumption-cli`
- **spark-authoring-cli**: New `resources/notebook-api-operations.md` resource — step-by-step CLI guide for reading and updating Fabric notebook content via REST API. Covers: `getDefinition`/`updateDefinition` full LRO flow, base64 encode/decode patterns, cell modification examples, and an end-to-end script.
- **spark-authoring-cli** SKILL.md: Added 9 new TOC entries pointing to `notebook-api-operations.md` sections.
- **SPARK-AUTHORING-CORE.md**: Added 4 new gotchas (#11–#14): HTTP 411 empty body, HTTP 400 `updateMetadata` flag, `getDefinition` `/result` suffix, and source line `\n` requirement. Added `getDefinition` read pattern to Quick Reference decision guide.
- Hybrid architecture documentation updates describing Agents → Skills → Common layering and the skill-vs-agent decision framework.

### Changed
- Updated contributor and compatibility documentation to reflect agent-based orchestration in addition to skills.

## [0.1.6] - 2026-02-10

### Added
- Skills compatibility test for validating skill routing and disambiguation

### Changed
- Updated plugins to version 0.1.6

## [0.1.5] - 2026-02-09

### Added
- Functional tests for the project
- Skill routing tests replacing Fabric integration tests
- Check for updates in Spark consumption skill

### Changed
- Renamed data-engineering skills to Spark
- Refactored the plugins
- Stricter semantic similarity thresholds (30% error, 20% warning)
- Optimized skills with API parameterization and token reduction
- Updated quality check for content review

### Fixed
- Updated .gitignore to exclude pycache files
- Encoding issues and duplicate triggers
- Livy endpoints with versioned paths and MSIT authentication

## [0.1.4] - 2026-02-08
### Added
- Feature/data analyst odbc (#5)
- Fabric Data Agent skills (dev and eval) (#2)

### Changed
- Enhance Data Engineering Skills: Session Management & Notebook Execution (#8)
- Merge branch 'master' of https://github.com/gim-home/skills-for-fabric
- Rename skill to spark-sql-odbc (#7)
- Fabric Data Engineering Skills  + Comprehensive Security Infrastructure (#3)

### Fixed
- Repo path in README (#6)

## [0.1.3] - 2026-02-07

### Added
- Fixed update command

## [0.1.2] - 2026-02-07

### Added
- Automatic plugin updates

## [0.1.0] - 2026-02-04

### Added
- Initial release of Microsoft Fabric Skills marketplace
- **Developer Skills**: `sqldw-authoring-cli`
- **Consumer Skills**: `sqldw-consumption-cli`
- **End-to-End Skills**: tbd
- **Update Checking**: Automatic update notifications at session start
- Cross-tool compatibility (GitHub Copilot CLI, VS Code, Claude Code, Cursor, Windsurf, Codex/Jules)
- Installation scripts for Windows (`install.ps1`) and Unix (`install.sh`)
- MCP server registration scripts

[Unreleased]: https://github.com/gim-home/skills-for-fabric/compare/v0.1.6...HEAD
[0.1.6]: https://github.com/gim-home/skills-for-fabric/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/gim-home/skills-for-fabric/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/gim-home/skills-for-fabric/compare/v0.1.0...v0.1.4
[0.1.3]: https://github.com/gim-home/skills-for-fabric/compare/v0.1.0...v0.1.3
[0.1.2]: https://github.com/gim-home/skills-for-fabric/compare/v0.1.0...v0.1.2
[0.1.0]: https://github.com/gim-home/skills-for-fabric/releases/tag/v0.1.0
