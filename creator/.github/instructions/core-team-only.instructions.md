---
applyTo: "{agents/**,common/**}"
---

# Core-Team-Only Files Review Guidelines

## Purpose

Apply when reviewing changes under `agents/` or `common/`. Both directories are core-team-owned per CONTRIBUTING.md "Scope of Contributions" and "What Goes Where". Contributors must not modify these files directly. Cite the relevant CONTRIBUTING.md section per finding.

## Agent files

Agent definition files at `agents/<persona>.agent.md` (e.g. `FabricDataEngineer.agent.md`, `FabricAdmin.agent.md`, `FabricAppDev.agent.md`, `FabricMigrationEngineer.agent.md`) are fixed and maintained by the core team.

Flag contributor-authored changes under `agents/` unless the PR clearly has core-team approval for the agent update. Recommended reviewer comment:

- "Agent files are core-team-owned per CONTRIBUTING.md 'Scope of Contributions'. If this new skill needs agent delegation, get explicit core-team approval in this PR. The agent reference can be added in the same PR by a core-team reviewer/committer, or tracked in an issue if the team chooses to defer it."

A legitimate reason for a skill PR to touch `agents/` is adding or updating a delegation reference for a brand-new skill, but only with explicit core-team approval. Prefer resolving that during the same PR review when the need is obvious, rather than relying on a separate follow-up PR.

## Common files

Files under `common/` (notably `common/COMMON-CORE.md` and `common/COMMON-CLI.md`) are shared references used by ALL skills for auth, tooling, REST patterns, and workspace/item resolution.

Flag ANY change under `common/` that is not part of a coordinated core-team PR. Recommended reviewer comment:

- "Common files are core-team-only per CONTRIBUTING.md 'What Goes Where'. If shared guidance needs to change, please open an issue first so the change can be evaluated and rolled out consistently across all skills."

If the contributor is hitting a real shared-guidance gap, the proper sequence is:

1. File an issue describing the gap with concrete examples.
2. The core team updates `common/`.
3. The contributor's skill PR follows up referencing the updated common docs.

For coordinated core-team changes under `common/` or `agents/`, also verify Fabric REST API accuracy (see the next section). Common files and agent docs set the canonical examples that every skill inherits, so drift here propagates to every `-cli` skill that follows the pattern.

## Fabric REST API accuracy (common/ and agents/ changes)

When a `common/` or `agents/` change adds or modifies a Fabric REST API endpoint, request/response shape, or example, verify against the official docs at https://learn.microsoft.com/en-us/rest/api/fabric. Common-doc drift propagates to every skill that inherits the pattern.

Check:

- Endpoint path matches the documented `Interface` section
- Field names match the documented response shape (e.g. Workspace has `displayName`, not `name` -- examples using `name` silently break filter queries; caught in PR #226)
- Query parameters match documented names and types
- Request body schemas match (required vs optional, enum values)
- Response codes match (e.g. 201 vs 202 LRO)

Most common drift: a plausible-sounding field name that does not exist on the response object. Recommended comment: cite the Learn URL directly with the correct field name. If the Learn doc itself appears stale, prefer empirical verification (sample `az rest` call captured in the PR body) and still link Learn for future audit.

## Why this matters

Skills delegate auth, tooling setup, and Fabric REST patterns to `common/`. Agents delegate cross-workload orchestration to skills. Drift in either layer breaks consistency across the entire skill catalog and can introduce inconsistent auth flows or routing across editor integrations.
