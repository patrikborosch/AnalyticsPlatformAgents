#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Creates a full release: updates skill catalog, stamps version, and optionally commits/pushes/releases.

.DESCRIPTION
    Interactive PowerShell script that combines catalog generation and version stamping
    into a single local release workflow. Replaces the sync-skill-catalog and sync-version
    GitHub Actions workflows.

    By default, makes all local changes (catalog, version stamps) without committing.
    Use -CommitAndPush to also commit, tag, push, and create a GitHub Release.

.EXAMPLE
    .\CreateFullRelease.ps1                   # Local changes only
    .\CreateFullRelease.ps1 -CommitAndPush    # Full release with push and GitHub Release
#>

param(
    [switch]$CommitAndPush
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Helpers ──────────────────────────────────────────────────────────────────

function Write-Step  { param([string]$msg) Write-Host "`n▶ $msg" -ForegroundColor Cyan }
function Write-Ok    { param([string]$msg) Write-Host "  ✅ $msg" -ForegroundColor Green }
function Write-Warn  { param([string]$msg) Write-Host "  ⚠️  $msg" -ForegroundColor Yellow }
function Write-Fail  { param([string]$msg) Write-Host "  ❌ $msg" -ForegroundColor Red; exit 1 }

function Update-JsonVersion {
    param([string]$Path, [string]$Version)
    $json = Get-Content $Path -Raw | ConvertFrom-Json
    $json.version = $Version
    $json | ConvertTo-Json -Depth 10 | Set-Content $Path -Encoding utf8NoBOM
    Write-Ok "Updated $Path"
}

# ── 1. Pre-flight checks ────────────────────────────────────────────────────

Write-Step "Pre-flight checks"

foreach ($tool in @('git', 'python')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Fail "'$tool' is not installed or not in PATH."
    }
}
if ($CommitAndPush) {
    if (-not (Get-Command 'gh' -ErrorAction SilentlyContinue)) {
        Write-Fail "'gh' CLI is not installed or not in PATH (required for -CommitAndPush)."
    }
}
Write-Ok "Required tools are available"

# Ensure we're at the repo root
if (-not (Test-Path 'package.json')) {
    Write-Fail "Run this script from the repository root."
}

# Check clean working tree (skip when --commit-and-push, since a prior local-only run may have left changes)
if (-not $CommitAndPush) {
    $status = git status --porcelain
    if ($status) {
        Write-Fail "Working tree is not clean. Commit or stash your changes first."
    }
}

# Check we're on main
$branch = git rev-parse --abbrev-ref HEAD
if ($branch -ne 'main') {
    Write-Fail "You must be on the 'main' branch (currently on '$branch')."
}

# Pull latest
git pull --ff-only origin main 2>$null
Write-Ok "On branch 'main', working tree clean, up to date"

# ── 2. Update skill catalog ─────────────────────────────────────────────────

Write-Step "Updating skill catalog"

python .github/scripts/generate_skill_catalog.py
if ($LASTEXITCODE -ne 0) { Write-Fail "Catalog generation failed." }

$catalogChanged = $false
$catalogDiff = git diff --name-only docs/skill-catalog.md
if ($catalogDiff) {
    git add docs/skill-catalog.md
    $catalogChanged = $true
    Write-Ok "Skill catalog updated and staged"
} else {
    Write-Ok "Skill catalog already up to date (regenerate manually with python .github/scripts/generate_skill_catalog.py if you want to refresh)"
}

# ── 2b. Consume pending changeset fragments ─────────────────────────────────

Write-Step "Consuming .changeset/ fragments into [Unreleased]"

$stampScript = Join-Path $PSScriptRoot "StampUnreleased.ps1"
if (Test-Path $stampScript) {
    & $stampScript
    if ($LASTEXITCODE -ne 0) { Write-Fail "StampUnreleased.ps1 failed." }
    # The script wrote CHANGELOG.md + deleted fragments; stage both.
    $changesetDiff = git status --porcelain CHANGELOG.md .changeset/ | Where-Object { $_ }
    if ($changesetDiff) {
        git add CHANGELOG.md .changeset/
        Write-Ok "CHANGELOG.md + .changeset/ deletions staged"
    } else {
        Write-Ok "No pending fragments to consume"
    }
} else {
    Write-Warn "StampUnreleased.ps1 not found at $stampScript; skipping changeset consumption (legacy flow)"
}

# Reminder to curate the public changelog
Write-Host ""
Write-Warn "Reminder: review the updated CHANGELOG.md and manually curate the public-appropriate"
Write-Warn "subset into public/CHANGELOG.md under the matching ## [<version>] section."
Write-Warn "PublishToPublic.ps1 reads public/CHANGELOG.md (not CHANGELOG.md) for the GitHub Release notes."

# ── 3. Show recent versions & prompt for new version ────────────────────────

Write-Step "Recent version tags"

$tags = git tag -l 'v*' --sort=-version:refname | Select-Object -First 3
if ($tags) {
    foreach ($t in $tags) {
        $date = git log -1 --format='%ai' $t 2>$null
        Write-Host "  $t  ($date)"
    }
    $latestTag = $tags[0]
} else {
    Write-Warn "No existing version tags found."
    $latestTag = 'v0.0.0'
}

# Suggest next patch version
$versionParts = ($latestTag -replace '^v', '') -split '\.'
$major = [int]$versionParts[0]
$minor = [int]$versionParts[1]
$patch = [int]$versionParts[2] + 1
$suggestedVersion = "$major.$minor.$patch"

Write-Host ""
$input = Read-Host "  Enter version [$suggestedVersion]"
$newVersion = if ($input.Trim()) { $input.Trim() -replace '^v', '' } else { $suggestedVersion }
$newTag = "v$newVersion"

Write-Host ""
Write-Ok "Will release as $newTag"

# ── 4. Stamp version in JSON files ──────────────────────────────────────────

Write-Step "Stamping version $newVersion in JSON files"

# package.json
Update-JsonVersion -Path 'package.json' -Version $newVersion

# plugin.json (root, if exists)
if (Test-Path 'plugin.json') {
    Update-JsonVersion -Path 'plugin.json' -Version $newVersion
}

# plugins/**/plugin.json
$pluginFiles = Get-ChildItem -Path 'plugins' -Filter 'plugin.json' -Recurse -ErrorAction SilentlyContinue
foreach ($f in $pluginFiles) {
    Update-JsonVersion -Path $f.FullName -Version $newVersion
}

# marketplace.json -- regenerate via build_plugins.py so the JSON encoding matches
# what the build script writes (Python json.dumps default ensure_ascii=True escapes
# non-ASCII chars as \uXXXX). Editing marketplace.json directly with ConvertTo-Json
# writes literal Unicode bytes, which then disagrees with `python build/build_plugins.py
# --check` after the stamp. Delegating to the build script keeps it single-source-of-truth:
# the script reads versions from package.json and regenerates both marketplace files from
# the per-plugin manifests.
$marketplacePath = '.github/plugin/marketplace.json'
$claudeMarketplacePath = '.claude-plugin/marketplace.json'

# The build script creates the marketplace files from manifests, so they don't need
# to pre-exist. But the marketplace.json paths are stable parts of the repo layout,
# so a missing one indicates the script is running outside the expected layout --
# fail loudly rather than silently skipping the regeneration + sanity gate (which
# would produce a release stamp that looks successful but leaves marketplaces stale).
if (-not (Test-Path 'build/build_plugins.py')) {
    Write-Fail "build/build_plugins.py not found. Are you running from the repo root?"
}

python build/build_plugins.py
if ($LASTEXITCODE -ne 0) { Write-Fail "build_plugins.py failed while regenerating marketplace files." }

if (-not (Test-Path $marketplacePath)) {
    Write-Fail "$marketplacePath was not produced by build_plugins.py -- check the build script output for errors."
}
if (-not (Test-Path $claudeMarketplacePath)) {
    Write-Fail "$claudeMarketplacePath was not produced by build_plugins.py -- check the build script output for errors."
}
Write-Ok "Regenerated $marketplacePath"
Write-Ok "Regenerated $claudeMarketplacePath"

# Sanity check: the regenerated files should be in sync with the manifests we
# just stamped. If --check fails here, something is wrong (e.g. version mismatch
# between package.json and a plugin.json), and we want to surface it BEFORE
# committing.
python build/build_plugins.py --check
if ($LASTEXITCODE -ne 0) { Write-Fail "build_plugins.py --check failed after stamp. Inspect the diff and try again." }
Write-Ok "Marketplace files in sync with manifests"

# ── 5. Commit, tag, push, release (only with --commit-and-push) ──────────────

if (-not $CommitAndPush) {
    Write-Step "Local changes complete"
    Write-Warn "Skipping commit/push/release (run with -CommitAndPush to publish)."
    Write-Host "`n📝 Release $newTag prepared locally. Review changes and re-run with -CommitAndPush." -ForegroundColor Green
    exit 0
}

Write-Step "Committing changes"

git add package.json
if (Test-Path 'plugin.json')                     { git add plugin.json }
if (Test-Path '.github/plugin/marketplace.json')  { git add .github/plugin/marketplace.json }
if (Test-Path '.claude-plugin/marketplace.json')  { git add .claude-plugin/marketplace.json }
$pluginFiles | ForEach-Object { git add $_.FullName } 2>$null

$hasStagedChanges = git diff --cached --quiet; $staged = $LASTEXITCODE -ne 0
if ($catalogChanged -or $staged) {
    git commit -m "chore: release $newTag"
    Write-Ok "Committed: chore: release $newTag"
} else {
    Write-Warn "No file changes to commit (version may already match)."
}

# ── 6. Tag ───────────────────────────────────────────────────────────────────

Write-Step "Creating tag $newTag"

$localTagExists  = git tag -l $newTag
$remoteTagExists = git ls-remote --tags origin $newTag 2>$null

if ($localTagExists -and $remoteTagExists) {
    Write-Warn "Tag $newTag already exists locally and on remote -- skipping tag creation."
} elseif ($localTagExists) {
    Write-Warn "Tag $newTag already exists locally -- will push existing tag."
} else {
    git tag $newTag
    Write-Ok "Tag $newTag created"
}

# ── 7. Push ──────────────────────────────────────────────────────────────────

Write-Step "Pushing to origin"
git push origin main --follow-tags
if (-not $remoteTagExists) {
    git push origin $newTag
}
Write-Ok "Pushed main and tag $newTag"

# ── 8. Create GitHub Release ────────────────────────────────────────────────

Write-Step "Creating GitHub Release"

# Derive repo owner/name from git remote to avoid requiring gh repo set-default
$remoteUrl = git remote get-url origin
if ($remoteUrl -match '(?:github\.com[:/])([^/]+/[^/.]+?)(?:\.git)?$') {
    $ghRepo = $Matches[1]
} else {
    Write-Fail "Could not parse GitHub owner/repo from remote URL: $remoteUrl"
}

$existingRelease = gh release view $newTag --repo $ghRepo 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Warn "GitHub Release $newTag already exists -- skipping."
} else {
    gh release create $newTag --generate-notes --title $newTag --repo $ghRepo
    Write-Ok "GitHub Release $newTag created"
}

Write-Host "`n🎉 Release $newTag complete!" -ForegroundColor Green
