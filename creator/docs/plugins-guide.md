# Plugins Guide

Plugins bundle skills, agents, and shared reference docs for installation by Copilot CLI / Claude Code marketplaces. This guide describes the **Stage 2 manifest model** used in the internal repo.

> **Two-repo model.** The internal repo (`gim-home/skills-for-fabric`) holds **manifests + canonical sources only**. The public repo (`microsoft/skills-for-fabric`) is what end users install from and contains **materialized plugin trees** produced by `build/build_plugins.py` during the sync-to-public step. Internal contributors never commit materialized plugin content.

## Plugin Lineup

All plugins live under a single marketplace (`fabric-collection`):

| Plugin | Target user | Skill suffix it bundles |
|---|---|---|
| `fabric-skills` | Everyone — full union bundle | All shipping skills |
| `fabric-authoring` | Developers (DDL, DML, CI/CD, automation) | `*-authoring-cli` |
| `fabric-consumption` | Users exploring data (queries, exploration) | `*-consumption-cli` |
| `fabric-operations` | Workload operators (monitoring, diagnostics) | `*-operations-cli` |

Every plugin includes `check-updates`. **`fabric-skills` is the union** — every skill in any other plugin is also in `fabric-skills`.

> Creating a new plugin is a core-team decision. Contributors add their skill to the existing plugins per the routing table below; they do not create new plugin folders.

## Repository Layout (Internal)

```
gim-home/skills-for-fabric/                 (this repo)
│
├── .claude-plugin/marketplace.json         ← GENERATED from per-plugin manifests, committed
├── .github/plugin/marketplace.json         ← GENERATED, byte-identical mirror, committed
│
├── agents/                                 ← canonical (core-team-owned)
├── common/                                 ← canonical (core-team-owned)
├── skills/                                 ← canonical (contributor edits here)
│
├── plugins/<name>/.github/plugin/plugin.json   ← MANIFEST (contributor edits arrays)
│   plugins/<name>/{skills,agents,common}/  ← GITIGNORED — built locally for testing only
│   plugins/<name>/.mcp.json                ← GITIGNORED
│
├── build/build_plugins.py                  ← materializer + marketplace generator
├── build/marketplace.config.json           ← marketplace-level metadata (collection name, owner)
└── tests/, docs/, ReleaseScripts/          ← internal-only; stripped during sync to public
```

## Manifest Format (`plugins/<name>/.github/plugin/plugin.json`)

This is the source of truth for plugin composition. The layout follows the awesome-copilot convention.

```json
{
  "$schema": "https://json-schema.org/draft-07/schema",
  "name": "fabric-authoring",
  "description": "Developer skills for authoring Microsoft Skills for Fabric solutions...",
  "version": "0.3.0",
  "license": "MIT",
  "repository": "https://github.com/gim-home/skills-for-fabric",
  "keywords": ["fabric", "microsoft-fabric", "authoring", "developer"],
  "skills": [
    "./skills/check-updates",
    "./skills/sqldw-authoring-cli",
    "./skills/spark-authoring-cli",
    "./skills/eventhouse-authoring-cli",
    "./skills/semantic-model-authoring",
    "./skills/e2e-medallion-architecture"
  ],
  "agents": [
    "./agents/FabricAdmin.agent.md",
    "./agents/FabricDataEngineer.agent.md",
    "./agents/FabricAppDev.agent.md"
  ],
  "mcpServers": {}
}
```

| Field | Required | Notes |
|---|---|---|
| `name`, `description`, `version`, `license`, `keywords`, `repository` | Yes | Plugin metadata |
| `skills` | Yes | Paths relative to plugin root: `./skills/<skill-folder-name>` |
| `agents` | Yes | Paths relative to plugin root: `./agents/<agent>.agent.md` |
| `mcpServers` | No | Inline MCP server config; written to `.mcp.json` at build time |

`common/*.md` files are **auto-derived** by parsing `../../common/X.md` references inside the included skills. Contributors do not list common files explicitly.

## Adding or Modifying a Skill

When you add a new skill (or rename/move one):

1. **Edit canonical source** — `skills/<skill-name>/SKILL.md`. Reference common modules via `../../common/COMMON-CLI.md` etc.
2. **Add the skill to the relevant manifest(s)** per the routing table below.
3. **Run the build** — this materializes plugins for local testing AND regenerates both marketplace files:
   ```bash
   python build/build_plugins.py
   ```
4. **Test the materialized plugin** locally (see "Local Testing" below).
5. **Add tests** under `tests/full-eval-tests/plan/03-individual-skills/` (minimum 5 eval prompts; see [Testing Guide](testing-guide.md)).
6. **Commit everything together:** the new skill folder, manifest edits, **and the regenerated `marketplace.json` files**. CI runs `build_plugins.py --check` and fails if marketplaces are stale.
7. **Add a `.changeset/PR<number>-<slug>.md` fragment** with a `### Added` / `### Changed` / `### Fixed` subsection describing the change. See [`.changeset/README.md`](../.changeset/README.md). Do **not** edit `CHANGELOG.md` directly -- it is auto-populated from fragments at release time.

### Routing Table

A skill's name suffix determines which plugins ship it:

| Skill suffix | Add `"./skills/<name>"` to these manifests |
|---|---|
| `-authoring-cli` | `plugins/fabric-authoring/.github/plugin/plugin.json` **and** `plugins/fabric-skills/.github/plugin/plugin.json` |
| `-consumption-cli` | `plugins/fabric-consumption/...` **and** `plugins/fabric-skills/...` |
| `-operations-cli` | `plugins/fabric-operations/...` **and** `plugins/fabric-skills/...` |
| `e2e-*` (cross-workload) | `plugins/fabric-skills/...` and the relevant axis if the workflow targets one |
| Migration (sanctioned exceptions) | `plugins/fabric-skills/...` only (a `fabric-migration` plugin is planned) |

**Always add to `fabric-skills`** — it's the union bundle. Forgetting this is the most common mistake.

### What you should NOT edit in a contribution PR

| Path | Reason |
|---|---|
| `agents/` | Core-team-owned per [CONTRIBUTING.md](../CONTRIBUTING.md) |
| `common/` | Core-team-owned per [CONTRIBUTING.md](../CONTRIBUTING.md); changes go through a separate PR |
| Creating a new `plugins/<new-name>/` folder | Core-team governance decision; file an issue |
| `.claude-plugin/marketplace.json` and `.github/plugin/marketplace.json` | **Auto-generated** — do not hand-edit. Run `python build/build_plugins.py` to regenerate from your manifest changes. Manual edits are reverted on the next build. |
| `build/marketplace.config.json` | Core-team-owned (collection name, owner, plugin order) |
| `package.json` `version` | Bumped during release, not in skill PRs |

You **can and should** edit:
- `skills/<your-skill>/...` — canonical content
- `plugins/fabric-*/.github/plugin/plugin.json` — `skills` / `mcpServers` arrays of existing plugins
- `tests/...` — your evals
- `CHANGELOG.md` — `[Unreleased]` entry
- The regenerated `.github/plugin/marketplace.json` and `.claude-plugin/marketplace.json` (commit them, but never hand-edit)

## Local Build & Testing

```bash
# Build: materializes plugins + regenerates marketplace files
python build/build_plugins.py

# Clean rebuild of materialized plugin trees
python build/build_plugins.py --clean

# Delete materialized content (skills/, agents/, common/, .mcp.json) and exit.
# Leaves manifests and marketplace files alone. Use this to keep your working
# tree tidy after testing — the materialized trees are gitignored anyway.
python build/build_plugins.py --purge

# CI gate: fails if marketplace files don't match what the manifests would generate
python build/build_plugins.py --check
```

After a successful build:

- `plugins/<name>/skills/`, `agents/`, `common/`, and `.mcp.json` exist locally (gitignored).
- `.github/plugin/marketplace.json` and `.claude-plugin/marketplace.json` are regenerated (committed).
- Use the materialized output to install the plugin into your local Copilot CLI / Claude Code session and exercise your skill end-to-end.

### Testing via marketplace browse (verifies marketplace.json is correct)

```bash
/plugin marketplace add <repo-root>
/plugin marketplace browse fabric-collection
/plugin install fabric-authoring@fabric-collection
```

If your new skill doesn't appear in `browse` output, you forgot step 3 above (run the build) — the marketplace was not regenerated.

## Build Script Behavior

`build/build_plugins.py` reads each `plugins/<name>/.github/plugin/plugin.json` and:

1. Validates that every `./skills/<x>` references an existing `skills/<x>/` folder.
2. Validates that every `./agents/<x>.agent.md` references an existing `agents/<x>.agent.md`.
3. Walks each included skill's markdown for `../../common/X.md` references and copies the closure into `plugins/<name>/common/`.
4. Writes `plugins/<name>/.mcp.json` from the manifest's `mcpServers` block.
5. **Regenerates** `.github/plugin/marketplace.json` and `.claude-plugin/marketplace.json` from the per-plugin manifests + `build/marketplace.config.json` + `package.json` version. Both files are byte-identical.
6. Fails non-zero with a clear message if any reference is unresolved.

`--check` mode skips writing the marketplace files and instead **fails** if the on-disk marketplaces differ from what the manifests would generate. This is the CI gate that catches "contributor edited the manifest but forgot to commit the regenerated marketplace."

Run it before every PR — it catches the bulk of contribution mistakes (typoed skill name in manifest, skill referencing a `common/` file that doesn't exist, marketplace stale relative to manifest).

## .mcp.json Per Plugin

Generated from each manifest's `mcpServers` block. Current state:

| Plugin | MCP servers |
|---|---|
| `fabric-skills` | `FabricIQ` |
| `fabric-authoring` | (empty) |
| `fabric-consumption` | `FabricIQ` |
| `fabric-operations` | (empty) |

If your skill needs a new MCP server, add it to `mcp-setup/` and to the `mcpServers` block in the manifest(s) of the plugins that should expose it.

## Sync to Public (`microsoft/skills-for-fabric`)

> This is a core-team responsibility. Contributors do not run the sync.

Today the sync is manual: a core-team member runs `python build/build_plugins.py --clean` against an internal checkout at the release tag, copies the curated subset of files (canonical sources, materialized `plugins/`, `mcp-setup/`, `compatibility/`, root docs) into a fresh public-repo working copy, strips internal-only artifacts (`tests/`, `ReleaseScripts/`, `docs/compliance/`), and pushes. The public repo's commit history shows this as a single cleanup commit per release.

Stage 3 (planned) automates this.

## Installation (End Users — From Public Repo)

```bash
# Full bundle
/plugin marketplace add microsoft/skills-for-fabric
/plugin install fabric-skills@fabric-collection

# By persona
/plugin install fabric-authoring@fabric-collection
/plugin install fabric-consumption@fabric-collection
/plugin install fabric-operations@fabric-collection
```

## Cross-Tool Compatibility

For non-Copilot-CLI tools, the public repo ships compatibility files at the
project root, so they are picked up automatically when the repo is cloned.
Internally, the canonical sources live under `compatibility/` in this repo and
are flattened to the public-repo root by the release flow:

| Tool | Internal source | Public repo location |
|---|---|---|
| Claude Code | `compatibility/CLAUDE.md` | `CLAUDE.md` |
| Cursor | `compatibility/.cursorrules` | `.cursorrules` |
| Codex / Jules | `compatibility/AGENTS.md` | `AGENTS.md` |
| Windsurf | `compatibility/.windsurfrules` | `.windsurfrules` |
| Gemini CLI | `compatibility/GEMINI.md` | `GEMINI.md` |

The internal repo's root `AGENTS.md` is a separate, contributor-only file
(matching the role of `.github/copilot-instructions.md` for Copilot) and is
not shipped to the public repo.

End users who clone the public repo get all four files at the project root
already — no copy step needed.

## Troubleshooting

| Issue | Solution |
|---|---|
| `build_plugins.py` reports "missing source skill: skills/X" | Skill folder doesn't exist or is misspelled in the manifest |
| `build_plugins.py` reports "skill references missing common/X.md" | Edit the skill to use an existing common file, or coordinate with core team to add it |
| Skill loads fine locally but isn't in `fabric-skills` after build | You forgot to add it to `plugins/fabric-skills/.github/plugin/plugin.json` |
| Materialized output looks wrong | `python build/build_plugins.py --clean` to rebuild from scratch |

## See Also

- [Skill Authoring Guide](skill-authoring-guide.md)
- [Common Folder Guide](common-folder-guide.md)
- [MCP Servers Guide](mcp-servers-guide.md)
- [Architecture Overview](architecture-overview.md)
- [Testing Guide](testing-guide.md)
