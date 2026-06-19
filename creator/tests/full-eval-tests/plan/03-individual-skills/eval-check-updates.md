# Eval Plan: check-updates

## Skill Overview
- **Skill:** `check-updates`
- **Category:** Utility (Read)
- **Purpose:** Check for FabricSkills marketplace updates at session start by comparing local version against GitHub remote version

## Pre-requisites
- FabricSkills installed locally with a valid `package.json` containing a `version` field
- Git remote `origin` configured pointing to the FabricSkills repository
- Network access to fetch from Git remote (for Method A) or GitHub API (for Method C)

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### CU-01: Read Local Version
- **Prompt:** "What version of FabricSkills do I have installed?"
- **Expected:** Skill reads `package.json` and returns the current local version (e.g., `v0.2.5`)
- **Pass criteria:** Output contains a valid semantic version matching the `version` field in the local `package.json`

### CU-02: Check for Updates (Standard)
- **Prompt:** "Check for FabricSkills updates"
- **Expected:** Skill fetches remote version, compares with local, and reports whether an update is available or the installation is up to date
- **Pass criteria:** Output contains either "up to date" confirmation or update-available notice with version numbers

### CU-03: Up-to-Date Confirmation
- **Prompt:** "Am I running the latest version of FabricSkills?"
- **Expected:** Skill checks remote version and displays a confirmation message (e.g., `✅ FabricSkills vX.Y.Z is up to date.`) if local matches remote
- **Pass criteria:** Output includes a clear up-to-date or update-available status with the local version number

### CU-04: Display Changelog
- **Prompt:** "What's new in FabricSkills?"
- **Expected:** Skill checks for updates and displays relevant CHANGELOG.md entries for versions between current and latest (or confirms current version is latest)
- **Pass criteria:** Output references CHANGELOG.md content or states no new changes are available

### CU-05: Update Commands
- **Prompt:** "How do I update FabricSkills?"
- **Expected:** Skill provides update commands for multiple installation methods (Copilot CLI, npm, Git clone)
- **Pass criteria:** Output includes at least two update methods with copy-pasteable commands

### CU-06: Session Cache — Skip Repeated Check
- **Prompt:** "Check for updates" (run twice in the same session within 7 days)
- **Expected:** Second invocation recognizes the check was already performed and skips the remote fetch
- **Pass criteria:** Second call completes faster and mentions that the check was already performed or is being skipped

### CU-07: Git CLI Method (Method A)
- **Prompt:** "Check for FabricSkills updates using git"
- **Expected:** Skill uses `git fetch origin main --quiet && git show origin/main:package.json` to get the remote version
- **Pass criteria:** Skill invokes git commands and extracts the remote version from the fetched `package.json`

### CU-08: Version Comparison Logic
- **Prompt:** "Check for updates to my Fabric skills"
- **Expected:** Skill performs semantic version comparison (major.minor.patch) between local and remote versions
- **Pass criteria:** The comparison result is logically correct — remote > local means update available, remote <= local means up to date

### CU-09: Network Error Handling
- **Prompt:** "Check for updates" (with network unavailable or remote unreachable)
- **Expected:** Skill handles the failure gracefully, shows a warning (e.g., `⚠️ Could not check for FabricSkills updates`), and does not block subsequent skill usage
- **Pass criteria:** No unhandled exception; output contains a graceful warning message and the agent continues normally

### CU-10: Negative — Ambiguous Prompt
- **Prompt:** "Update my skills"
- **Expected:** Skill asks for clarification — does the user want to check for updates, or actually perform an update?
- **Pass criteria:** Agent does not silently fail or assume intent; it either asks for clarification or provides both check and update options

## Write Operations (for consistency pairing)

_None — this skill is read-only and does not write data to Fabric._

## Expected Token Range
- 500–1500 tokens per invocation
