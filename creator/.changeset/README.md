# `.changeset/` -- per-PR changelog fragments

**One file per PR.** Each PR adds a single markdown file under `.changeset/` describing what changed. At release time, `ReleaseScripts/StampUnreleased.ps1` reads every fragment, merges entries into the `## [Unreleased]` section of the internal `CHANGELOG.md`, and deletes the consumed fragments.

## Why fragments instead of editing CHANGELOG.md directly?

Editing `CHANGELOG.md` directly causes a merge conflict on every PR pair that's open at the same time (both PRs touch the same line range under `## [Unreleased]`). With one fragment per PR, each PR creates a uniquely-named file -- **zero file-level conflicts**.

This pattern is used by `changesets`, `release-please`, and many other modern release tools.

## How to add a changelog entry to your PR

1. Create a new file under `.changeset/` named `PR<number>-<short-slug>.md`, e.g.:
   - `PR306-workload-team-onboarding.md`
   - `PR289-dataflows-output-destinations.md`
   - `PR272-vally-smoke-harness.md`

   Don't have a PR number yet? Use `PR-DRAFT-<slug>.md` and rename when you open the PR. The script doesn't care about the filename shape (only that it's unique and not `README.md` / `.gitkeep`), but the `PR<number>-` convention makes the changelog history greppable.

2. Write your entries using **markdown subsections** (`### Added`, `### Changed`, `### Removed`, `### Fixed`). A single fragment can contribute to multiple subsections. Optionally mark the fragment as `audience: public` if its bullets should also reach the external `microsoft/skills-for-fabric` release notes (default: `internal`).

```markdown
# PR #306 -- short title describing the PR

audience: public   <!-- optional; omit or write `internal` for internal-only -->

### Added

- **`skills/foo-authoring-cli`** -- new skill for the foo workload...

### Fixed

- **`skills/bar-consumption-cli`** -- corrected the expectedResults regex...
```

3. Commit the file alongside your code changes. Push as part of your PR.

## Audience marker -- who decides public vs internal

A single optional line at the top of the fragment (case-insensitive) controls routing at release time:

| Value | Goes to internal `CHANGELOG.md`? | Goes to public `public/CHANGELOG.md`? |
|---|---|---|
| `audience: public` | Yes (all entries always do) | **Yes** -- bullets are also prepended into `public/CHANGELOG.md` `[Unreleased]` (auto-created if missing) |
| `audience: internal` | Yes | No |
| *(absent)* | Yes | No (safe default -- nothing leaks externally without explicit opt-in) |
| `audience: <anything-else>` | Yes (defaults to internal) | No + a warning is printed |

Pick `public` when the change is something external users of `microsoft/skills-for-fabric` would care about: a new user-facing skill, a renamed skill, a bug fix in a skill they invoke, public-facing docs. Pick `internal` (or leave absent) for: contributor tooling, CI workflows, internal helper scripts, infra refactors, anything under `.github/`, `ReleaseScripts/`, `tests/`. When unsure, leave it absent -- the release maintainer can hand-edit `public/CHANGELOG.md` to add a missing entry, but cannot easily un-publish a leaked one.

## Where + when fragments get consumed

The maintainer running `ReleaseScripts/CreateFullRelease.ps1` triggers it automatically -- the release script now calls `StampUnreleased.ps1` as Step 2b (right after regenerating the skill catalog, before stamping the version). Maintainers can also run it standalone:

```powershell
./ReleaseScripts/StampUnreleased.ps1 -DryRun     # preview only
./ReleaseScripts/StampUnreleased.ps1             # consume + delete fragments
```

What the script does:

1. Reads every `.changeset/*.md` (excluding `README.md` and `.gitkeep`)
2. For each fragment, parses the optional `audience:` marker (default: `internal`) and extracts every `### Added` / `### Changed` / `### Removed` / `### Fixed` subsection. Bullets are grouped by kind across all fragments AND by audience.
3. Prepends ALL new bullets into the matching subsection of `## [Unreleased]` in the internal `CHANGELOG.md` (creates the subsection if it doesn't exist yet)
4. Prepends ONLY public-audience bullets into the matching subsection of `## [Unreleased]` in `public/CHANGELOG.md`. If `public/CHANGELOG.md` has no `[Unreleased]` section (the normal between-release state), one is inserted at the top before the most recent versioned section.
5. Deletes the consumed fragment files

The maintainer then commits both the updated `CHANGELOG.md` (and `public/CHANGELOG.md` if it changed) and the fragment deletions: `chore(changelog): consume N changeset(s)`. The version-stamp follows in the same PR (`## [Unreleased]` -> `## [0.3.x] - YYYY-MM-DD`).

## Internal vs public CHANGELOG -- two different files

| File | Audience | Content | How it's updated |
|---|---|---|---|
| `CHANGELOG.md` (repo root) | **Internal** -- gim-home contributors + maintainers | All PRs reflected, may reference internal tools / contributors / PRs | Auto-populated from EVERY `.changeset/` fragment at release time |
| `public/CHANGELOG.md` | **Public** -- external users of microsoft/skills-for-fabric | Hand-curated PLUS auto-populated from fragments marked `audience: public` | Maintainer can still hand-edit (add/reword entries) before running `PublishToPublic.ps1`. `PublishToPublic.ps1` reads from `public/CHANGELOG.md` (NOT `CHANGELOG.md`) when extracting GitHub Release notes for the public repo. |

The separation is intentional. Internal entries often reference internal tooling, internal PR numbers, internal Microsoft-employee names, or context that doesn't make sense for external readers. The `audience: public` marker lets contributors opt-in PR-by-PR: their bullet shows up in both files at release time, the maintainer can still reword it for the public file before tagging.

This is the same intent behind the separate `compatibility/` directory (internal source of truth) vs flattening to root in the public repo (user-facing layout).