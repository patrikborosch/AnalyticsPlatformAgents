---
applyTo: "{README.md,CHANGELOG.md,.changeset/**,compatibility/**,.github/skill-ownership.yml,.github/coverage-policy.yml}"
---

# Skill Metadata Sync Review Guidelines

## Purpose

Apply when reviewing the cross-cutting metadata files that must stay in sync whenever the skill catalog changes. CI does not check that these files were updated when a skill is added, renamed, or removed -- humans must catch this. Cite CONTRIBUTING.md "Pull Request Checklist" per finding.

## `.changeset/` fragment (not direct CHANGELOG.md edits)

For any PR adding, renaming, removing, or materially expanding a skill, a `.changeset/PR<number>-<slug>.md` fragment MUST be added in the PR diff. The fragment uses markdown subsections:

- `### Added` for new skills
- `### Changed` for renames or behavior changes
- `### Removed` for deletions
- `### Fixed` for bug fixes affecting skill behavior

A single fragment may contain multiple subsections. The entry must name the skill explicitly (e.g. `spark-operations-cli`, not "the Spark skill"). Flag PRs that touch `skills/` but do not add a `.changeset/` fragment.

**Do NOT flag PRs for missing direct `CHANGELOG.md` edits.** `CHANGELOG.md` is auto-populated from fragments at release time by `ReleaseScripts/StampUnreleased.ps1`. Direct edits cause merge conflicts and are no longer required. See `.changeset/README.md`.

Do NOT require `public/CHANGELOG.md` updates for normal skill PRs. That file is a release-curated consumer changelog; only flag it when a PR specifically changes public release notes, public release packaging, or `ReleaseScripts/PublishToPublic.ps1` in a way that affects public-facing release content.

## README.md skill catalog

The README skill-catalog tables (Authoring Skills / Consumption Skills / Operations Skills) are hand-edited and not auto-generated.

- New skill -> flag if a row was not added to the appropriate table.
- Renamed skill -> flag if the existing row still references the old name.
- Removed skill -> flag if the row was not removed.
- Modified description in `SKILL.md` -> flag if the README row's short description is now stale.

## Ownership manifest

CI (`test_skill_ownership_manifest.py`) already enforces missing, extra, and stale ownership entries against `skills/`. Do NOT re-flag those. Limit review to semantic gaps CI cannot judge:

- Stale-looking ownership area or team values (e.g. an area name that no longer matches the org structure, or a team that has been renamed).
- Newly added entries with empty or placeholder area / contact metadata.

## Coverage policy

CI (`coverage_enforcement.py`) already enforces non-empty `reason` fields and detects untracked / stale allow-missing debt. Do NOT re-flag those. Limit review to:

- Vacuous `reason` strings (non-empty but uninformative, e.g. "TBD", "todo", "needs work", "fix later").
- PR-body claims of coverage exemption that are not actually reflected in `.github/coverage-policy.yml`.

## Compatibility files

When a skill is added or renamed, the following must be updated:

- `compatibility/CLAUDE.md`
- `compatibility/AGENTS.md`
- `compatibility/.cursorrules`
- `compatibility/.windsurfrules`

These four compatibility files mirror the same skill catalog for external editors / CLIs and drift in lock-step. `.github/copilot-instructions.md` is repo-wide Copilot guidance and is NOT part of this rename-sync set; only flag it when the contributor explicitly changed something else in repo-wide guidance (workflow conventions, branch policy, agent instructions, etc.).

Flag PRs that update one but not the others -- partial updates cause drift across editor/CLI integrations. Name the exact files missing the rename.
