#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Publishes a release to the public microsoft/skills-for-fabric repo.

.DESCRIPTION
    Two-phase release flow for the public repo. Each phase is its own explicit
    invocation; the operator chooses which phase to run.

    PHASE 1 — Publish content (default, no flag):
      Builds plugin packages, scrubs internal references, and creates/updates a
      PR on microsoft/skills-for-fabric. Does NOT push directly to main.
        1. Build plugin packages (build_plugins.py --clean)
        2. Clone the public repo to a temp directory
        3. Sync publishable content (plugins/, marketplace, package.json, etc.)
        4. Scrub internal references (MSIT URLs, gim-home org, test tenant)
        5. Create a branch, commit, push, and open/update the PR

    PHASE 2 — Tag + GitHub Release (-PublishRelease):
      Run AFTER the phase-1 PR has been reviewed and merged. Tags the merged
      commit on public main and creates a GitHub Release using the curated
      `[$Version]` section from `public/CHANGELOG.md` as the release notes.
      (Headings in `public/CHANGELOG.md` are formatted `## [$Version] - <date>`
      with no `v` prefix inside the brackets.)

      Hard-fails (does not silently do nothing) when its preconditions are not
      met — see "PublishRelease preconditions" below.

    Prerequisites:
      - git, python, gh CLI installed
      - Authenticated to GitHub with push access to microsoft/skills-for-fabric
      - Run from the gim-home/skills-for-fabric repo root

.PARAMETER PublicRepo
    The public GitHub repo (default: microsoft/skills-for-fabric)

.PARAMETER Version
    Version tag to use. If not provided, reads from package.json (internal HEAD).

.PARAMETER DryRun
    Phase-1 only: show what would be synced without making any changes to the
    public repo. Ignored when -PublishRelease is set.

.PARAMETER PublishRelease
    Run PHASE 2 instead of PHASE 1. Preconditions (evaluated in order):
      1. $Version must be strictly greater than the latest published release on
         the public repo. The first release on a fresh repo (404 from
         /releases/latest) is exempt.
      2. Public main HEAD must be the merge of release/v$Version (commit subject
         matching "Merge pull request .* from .*/release/v$Version" or
         "Release v$Version from internal repo").
      3. If the GitHub Release for v$Version already exists, the script exits 0
         with a pointer at the release page (idempotent — no work to do). If only
         the tag exists but no Release does, the script continues so the Release
         can be created on top of the orphan tag (recovery from a previous run
         that pushed the tag but failed at `gh release create`).
    On precondition 1 or 2 violation, the script Write-Fail's with a clear
    message instead of silently doing nothing.

.EXAMPLE
    .\PublishToPublic.ps1                           # Phase 1: create/update PR
    .\PublishToPublic.ps1 -DryRun                   # Phase 1 preview
    .\PublishToPublic.ps1 -PublishRelease           # Phase 2: tag + release (run after PR merge)
    .\PublishToPublic.ps1 -PublicRepo myorg/myrepo  # Different target
#>

param(
    [string]$PublicRepo = "microsoft/skills-for-fabric",
    [string]$Version = "",
    [switch]$DryRun,
    [switch]$PublishRelease
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Helpers ──────────────────────────────────────────────────────────────────

function Write-Step  { param([string]$msg) Write-Host "`n▶ $msg" -ForegroundColor Cyan }
function Write-Ok    { param([string]$msg) Write-Host "  ✅ $msg" -ForegroundColor Green }
function Write-Warn  { param([string]$msg) Write-Host "  ⚠️  $msg" -ForegroundColor Yellow }
function Write-Fail  { param([string]$msg) Write-Host "  ❌ $msg" -ForegroundColor Red; exit 1 }

# ── Configuration ────────────────────────────────────────────────────────────

# Files/folders to sync to public repo
$SyncItems = @(
    "plugins/",
    ".github/plugin/",
    ".github/copilot-instructions.md",
    ".claude-plugin/",
    ".mcp.json",
    "agents/",
    "common/",
    "skills/",
    "mcp-setup/",
    "prompt_examples/",
    "package.json",
    "LICENSE",
    "CODE_OF_CONDUCT.md",
    ".gitignore",
    ".gitleaks.toml"
)

# Compatibility files: live under compatibility/ in the internal repo, but get
# flattened to the public repo root so downstream tools (Claude Code, Cursor,
# Codex/Jules, Windsurf, Gemini CLI) pick them up automatically. The internal AGENTS.md is
# contributor-focused and never shipped (see $ExcludePatterns); the user-facing
# version is compatibility/AGENTS.md and replaces it at the public root.
$CompatibilityFlattens = @(
    @{ Source = "compatibility/CLAUDE.md";       Target = "CLAUDE.md" },
    @{ Source = "compatibility/.cursorrules";    Target = ".cursorrules" },
    @{ Source = "compatibility/.windsurfrules";  Target = ".windsurfrules" },
    @{ Source = "compatibility/AGENTS.md";       Target = "AGENTS.md" },
    @{ Source = "compatibility/GEMINI.md";       Target = "GEMINI.md" }
)

# Files/folders to EXCLUDE (never sync)
$ExcludePatterns = @(
    "tests/",
    "ReleaseScripts/",
    "build/",
    ".github/workflows/",
    ".github/scripts/",
    ".github/skills/",
    ".github/acl/",
    ".github/instructions/",
    ".github/coverage-policy.yml",
    ".github/skill-ownership.yml",
    ".github/ISSUE_TEMPLATE/",
    ".github/CODEOWNERS",
    ".github/SECURITY-WORKFLOW.md",
    ".github/compliance/",
    ".github/dependabot.yml",
    ".github/hooks/",
    ".github/policies/",
    "testdata/",
    "quality-report.json",
    "skill_validation.py",
    "pytest.ini",
    "install.ps1",
    "install.sh",
    "plugin.json",
    "docs/",
    "CONTRIBUTING.md",
    "SUPPORT.md",
    ".github/pull_request_template.md",
    "AGENTS.md",
    "SECURITY.md",
    "SECURITY-GUIDELINES.md",
    "compatibility/",
    "public/"
)

# Internal references to scrub
# NOTE: Order matters — specific patterns before general ones (e.g.,
# 'gim-home/skills-for-fabric' before bare 'gim-home') to avoid partial replacements.
$Scrubs = @(
    @{ Find = "msitapi.fabric.microsoft.com";  Replace = "api.fabric.microsoft.com" },
    @{ Find = "gim-home/skills-for-fabric";    Replace = "microsoft/skills-for-fabric" },
    @{ Find = "gim-home";                      Replace = "microsoft" }
)

# Patterns to detect (warn but don't auto-scrub — may need manual review)
$WarnPatterns = @(
    "E2EAPIMSIT2",
    "e2eapimsit2-ga.vault.azure.net",
    "apitestadmin",
    "pbitestusera"
)

# ── 1. Pre-flight checks ────────────────────────────────────────────────────

Write-Step "Pre-flight checks"

foreach ($tool in @('git', 'python', 'gh')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Fail "'$tool' is not installed or not in PATH."
    }
}

if (-not (Test-Path 'package.json')) {
    Write-Fail "Run this script from the gim-home/skills-for-fabric repo root."
}

if (-not (Test-Path 'build/build_plugins.py')) {
    Write-Fail "build/build_plugins.py not found. Are you running from the repo root?"
}

if (-not (Test-Path 'public/README.md')) {
    Write-Fail "public/README.md not found. This file is required as the public repo README source."
}

if (-not (Test-Path 'public/CHANGELOG.md')) {
    Write-Fail "public/CHANGELOG.md not found. This file is required as the public repo changelog source."
}

if (-not (Test-Path 'public/SECURITY.md')) {
    Write-Fail "public/SECURITY.md not found. This file is required as the public repo security policy source."
}

# Read version
if (-not $Version) {
    $pkg = Get-Content 'package.json' -Raw | ConvertFrom-Json
    $Version = $pkg.version
}

# Normalize: strip a single leading 'v' so the user can pass either
# "-Version 0.3.2" or "-Version v0.3.2" without breaking Compare-Version
# (which would try to cast "v0" to [int]) or producing "vv0.3.2" tags.
if ($Version -match '^v') { $Version = $Version.Substring(1) }

Write-Ok "Version: $Version"
Write-Ok "Target: $PublicRepo"

$branchName = "release/v$Version"

# ── PHASE 2 — Tag + GitHub Release (when -PublishRelease is set) ────────────
#
# This phase is intentionally distinct from phase 1 and runs only with an
# explicit flag. It assumes the phase-1 PR has been reviewed + merged on the
# public repo. The script verifies that assumption against the public remote
# and fails loudly if any precondition is violated, so a wrong invocation is
# obvious instead of silently doing nothing useful.
if ($PublishRelease) {
    if ($DryRun) { Write-Warn "-DryRun is ignored in -PublishRelease mode" }

    Write-Step "Publishing release v$Version on $PublicRepo"

    # --- Helper: compare two MAJOR.MINOR.PATCH strings.
    # Returns -1 if $a < $b, 0 if equal, 1 if $a > $b.
    # Pre-release suffixes (e.g. "0.3.2-beta") are stripped before comparison;
    # the comparison is intentionally coarse so we catch the common mistake
    # (publishing v0.2.0 after v0.3.0) without needing a full SemVer parser.
    function script:Compare-Version([string]$a, [string]$b) {
        $stripPre = { param($v) ($v -split '-')[0] }
        $aParts = (& $stripPre $a) -split '\.'
        $bParts = (& $stripPre $b) -split '\.'
        for ($i = 0; $i -lt 3; $i++) {
            $av = if ($i -lt $aParts.Length) { [int]$aParts[$i] } else { 0 }
            $bv = if ($i -lt $bParts.Length) { [int]$bParts[$i] } else { 0 }
            if ($av -lt $bv) { return -1 }
            if ($av -gt $bv) { return  1 }
        }
        return 0
    }

    # --- Precondition 1: idempotent short-circuit.
    # If the GitHub Release already exists, this is a clean no-op rerun.
    # If only the tag exists but no Release does, treat it as orphan-tag recovery:
    # a previous run pushed the tag but `gh release create` failed (network, auth,
    # rate limit, EMU). Keep going so we can create the Release on the existing
    # tag; the tag-creation step downstream is skipped automatically because the
    # tag already exists.
    $existingRelease = gh api "/repos/$PublicRepo/releases/tags/v$Version" 2>$null
    if ($LASTEXITCODE -eq 0 -and $existingRelease) {
        Write-Warn "Release v$Version already exists on $PublicRepo. Nothing to do."
        Write-Host "  Release page: https://github.com/$PublicRepo/releases/tag/v$Version" -ForegroundColor DarkGray
        exit 0
    }
    $existingTag = gh api "/repos/$PublicRepo/git/refs/tags/v$Version" 2>$null
    $tagAlreadyPushed = ($LASTEXITCODE -eq 0 -and $existingTag)
    if ($tagAlreadyPushed) {
        Write-Warn "Tag v$Version exists on $PublicRepo but no Release does — recovering from a previous orphan-tag failure. Will create the Release on the existing tag."
    }

    # --- Precondition 2: $Version must be greater than the latest published
    # release on the public repo. Prevents a typo or wrong-flag invocation from
    # publishing an older version (e.g. v0.2.0 after v0.3.0) which would corrupt
    # the user-visible release ordering. The first release on a fresh repo is
    # exempt: `/releases/latest` returns 404 when no published release exists,
    # which we treat as "anything is fine".
    $latestRelease = gh api "/repos/$PublicRepo/releases/latest" --jq '.tag_name' 2>&1
    $latestExit = $LASTEXITCODE
    if ($latestExit -ne 0) {
        # 404 = no releases yet (bootstrap case); any other error is a real failure.
        if ("$latestRelease" -match 'Not Found' -or "$latestRelease" -match '"status":\s*"404"') {
            Write-Ok "No prior release on $PublicRepo (bootstrap). Skipping version-ordering check."
        } else {
            Write-Fail "gh api /repos/$PublicRepo/releases/latest failed with exit $latestExit. Output: $latestRelease"
        }
    } else {
        $latestStripped = $latestRelease -replace '^v', ''
        $cmp = Compare-Version $Version $latestStripped
        if ($cmp -le 0) {
            $relation = if ($cmp -eq 0) { "equal to" } else { "less than" }
            Write-Warn "Requested v$Version is $relation the latest published release (v$latestStripped) on $PublicRepo."
            Write-Host "  Publishing this would corrupt release ordering for end users." -ForegroundColor Yellow
            Write-Host "  If you intend to retroactively publish a historical release, do it via the web UI" -ForegroundColor Yellow
            Write-Host "    https://github.com/$PublicRepo/releases/new" -ForegroundColor Yellow
            Write-Host "  and uncheck 'Set as the latest release'." -ForegroundColor Yellow
            Write-Fail "Phase-2 precondition not met: version must be greater than latest published release."
        }
        Write-Ok "v$Version is greater than the latest release (v$latestStripped)"
    }

    # --- Precondition 3: public main HEAD must be the merge of release/v$Version.
    # We accept either commit subject the publish flow could have produced.
    # `gh api` is invoked separately for sha and message; if either call fails
    # (auth, rate-limit, network), bail with a pointer at the API failure so we
    # don't misreport it as a "PR not merged" issue.
    $publicMainSha = gh api "/repos/$PublicRepo/commits/main" --jq '.sha' 2>&1
    $shaExit = $LASTEXITCODE
    if ($shaExit -ne 0 -or [string]::IsNullOrWhiteSpace($publicMainSha)) {
        Write-Fail "gh api /repos/$PublicRepo/commits/main (sha) failed with exit $shaExit. Output: $publicMainSha"
    }
    $publicMainMsg = gh api "/repos/$PublicRepo/commits/main" --jq '.commit.message' 2>&1
    $msgExit = $LASTEXITCODE
    if ($msgExit -ne 0 -or [string]::IsNullOrWhiteSpace($publicMainMsg)) {
        Write-Fail "gh api /repos/$PublicRepo/commits/main (message) failed with exit $msgExit. Output: $publicMainMsg"
    }

    # Match only against the commit subject (first line) so a regex that happens
    # to appear in a multi-line commit body can't produce a false positive.
    $publicMainSubject = ($publicMainMsg -split "`r?`n")[0]

    # Derive the owner from $PublicRepo (e.g. "microsoft" from "microsoft/skills-for-fabric")
    # so the user-facing guidance text matches the actual target repo.
    $publicOwner = ($PublicRepo -split '/')[0]

    $expectedSubjects = @(
        "^Release v$Version from internal repo$",
        "^Merge pull request .* from .*/release/v$Version$"
    )
    $atReleaseCommit = $false
    foreach ($pat in $expectedSubjects) {
        if ($publicMainSubject -match $pat) { $atReleaseCommit = $true; break }
    }
    if (-not $atReleaseCommit) {
        Write-Warn "Public $PublicRepo main is NOT at the v$Version release commit."
        Write-Host "  Current main HEAD: $($publicMainSha.Substring(0, 8))" -ForegroundColor Yellow
        Write-Host "  Current subject  : $publicMainSubject" -ForegroundColor Yellow
        Write-Host "" -ForegroundColor Yellow
        Write-Host "  Expected one of:" -ForegroundColor Yellow
        Write-Host "    - Release v$Version from internal repo" -ForegroundColor Yellow
        Write-Host "    - Merge pull request <N> from $publicOwner/release/v$Version" -ForegroundColor Yellow
        Write-Host "" -ForegroundColor Yellow
        Write-Host "  Likely the phase-1 PR (release/v$Version) hasn't been merged yet." -ForegroundColor Yellow
        Write-Host "  Run WITHOUT -PublishRelease first to create/update the PR; get it merged;" -ForegroundColor Yellow
        Write-Host "  then re-run with -PublishRelease." -ForegroundColor Yellow
        Write-Fail "Phase-2 precondition not met. See guidance above."
    }
    Write-Ok "Public main is at the v$Version release commit ($($publicMainSha.Substring(0, 8)))"

    # --- Extract the [v$Version] section from internal public/CHANGELOG.md.
    # We read from the internal repo (HEAD) rather than the public clone because
    # this is the canonical curated source; the publish step copied it verbatim.
    Write-Step "Extracting release notes from public/CHANGELOG.md"
    $changelogLines = Get-Content 'public/CHANGELOG.md'
    $startPattern = "^## \[$([regex]::Escape($Version))\]"
    $nextPattern  = "^## \["
    $startIdx = -1
    for ($i = 0; $i -lt $changelogLines.Length; $i++) {
        if ($changelogLines[$i] -match $startPattern) { $startIdx = $i; break }
    }
    if ($startIdx -lt 0) {
        Write-Fail "Could not find '## [$Version]' section in public/CHANGELOG.md. Add a curated section for this version before running -PublishRelease."
    }
    $endIdx = $changelogLines.Length
    for ($i = $startIdx + 1; $i -lt $changelogLines.Length; $i++) {
        if ($changelogLines[$i] -match $nextPattern) { $endIdx = $i; break }
    }
    $notes = ($changelogLines[$startIdx..($endIdx - 1)] -join "`n").TrimEnd()
    Write-Ok "Extracted $($endIdx - $startIdx) lines of release notes"

    # --- Create the lightweight tag on public main, then the GitHub Release.
    # In the orphan-tag-recovery path the tag already exists from a previous
    # run, so we skip the create and go straight to the Release.
    if ($tagAlreadyPushed) {
        Write-Step "Skipping tag creation (tag v$Version already exists from a previous run)"
    } else {
        Write-Step "Tagging v$Version on $PublicRepo main"
        $tagRef = gh api -X POST "/repos/$PublicRepo/git/refs" `
            -f "ref=refs/tags/v$Version" `
            -f "sha=$publicMainSha" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Failed to create tag v$Version on $PublicRepo : $tagRef"
        }
        Write-Ok "Tag v$Version -> $($publicMainSha.Substring(0, 8))"
    }

    Write-Step "Creating GitHub Release"
    $notesFile = Join-Path ([System.IO.Path]::GetTempPath()) "release-notes-v$Version-$(Get-Random).md"
    $notes | Set-Content $notesFile -Encoding utf8NoBOM
    try {
        $releaseUrl = gh release create "v$Version" `
            --repo $PublicRepo `
            --title "v$Version" `
            --notes-file $notesFile
        $releaseExit = $LASTEXITCODE
    } finally {
        Remove-Item $notesFile -Force -ErrorAction SilentlyContinue
    }
    if ($releaseExit -ne 0 -or [string]::IsNullOrWhiteSpace($releaseUrl)) {
        Write-Warn "gh release create exited $releaseExit. The Release wasn't created."
        if (-not $tagAlreadyPushed) {
            Write-Host "  The tag v$Version was pushed in this run and is now orphan (no Release)." -ForegroundColor Yellow
            Write-Host "  Re-running -PublishRelease will detect this and retry the Release step on the existing tag." -ForegroundColor Yellow
        } else {
            Write-Host "  The tag v$Version was already present from a previous run." -ForegroundColor Yellow
            Write-Host "  Re-running -PublishRelease will retry the Release step again." -ForegroundColor Yellow
        }
        Write-Host "  Inspect manually: https://github.com/$PublicRepo/releases" -ForegroundColor Yellow
        Write-Fail "Release not published. See guidance above for retry."
    }
    Write-Ok "Release published: $releaseUrl"
    Write-Host "`n🎉 v$Version is now live on $PublicRepo`n" -ForegroundColor Green
    exit 0
}

# --- 1b. Public release parity gate (block if a prior release was never published) ---
# Phase 1 (content PR) and Phase 2 (-PublishRelease = tag + Release) are decoupled
# manual steps. If a previous Phase 1 merged but its Phase 2 was skipped, the public
# repo already carries content for a version with no GitHub Release; publishing more
# on top buries that gap. Block here so the operator clears it first. Reuses the same
# detector the weekly Public Release Parity workflow runs (--no-issue: detect + exit
# non-zero, file no issue). Exit 2 = an already-shipped version has no release.
Write-Step "Checking public release parity (prior release must be published)"
python .github/scripts/check_public_release_parity.py --no-issue --public-repo $PublicRepo
$parityExit = $LASTEXITCODE
if ($parityExit -eq 2) {
    if ($DryRun) {
        Write-Warn "A version already shipped to $PublicRepo has no GitHub Release (see above). A real run BLOCKS here until you publish it via Phase 2."
    } else {
        Write-Fail "A version already shipped to $PublicRepo has no GitHub Release (see above). Run Phase 2 for it first ( .\ReleaseScripts\PublishToPublic.ps1 -PublishRelease -Version <that-version> ), then re-run Phase 1."
    }
} elseif ($parityExit -ne 0) {
    Write-Warn "Could not verify public release parity (exit $parityExit). Proceeding -- double-check $PublicRepo Releases manually."
} else {
    Write-Ok "Public release parity OK -- the latest shipped version is released."
}

# ── 2. Build plugin packages ────────────────────────────────────────────────

Write-Step "Building plugin packages"

python build/build_plugins.py --clean
if ($LASTEXITCODE -ne 0) { Write-Fail "build_plugins.py failed." }
Write-Ok "Plugins built"

# ── 3. Clone public repo ────────────────────────────────────────────────────

Write-Step "Cloning public repo"

$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "publish-public-$(Get-Random)"
$publicDir = Join-Path $tempDir "public"

gh repo clone $PublicRepo $publicDir 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to clone $PublicRepo" }
Write-Ok "Cloned to $publicDir"

# Check out the target branch before syncing so retries update the existing
# public release branch instead of discarding copied content afterward.
Push-Location $publicDir
$remoteBranch = git ls-remote --heads origin $branchName 2>$null
if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to check for branch $branchName on origin" }
if ($remoteBranch) {
    git fetch origin $branchName 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to fetch branch $branchName from origin" }
    git checkout -f $branchName
    if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to check out existing branch $branchName" }
} else {
    git checkout -b $branchName
    if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to create and check out branch $branchName" }
}
Pop-Location

# ── 4. Sync content ─────────────────────────────────────────────────────────

Write-Step "Syncing publishable content"

$internalRoot = Get-Location

# Clear existing generated/public content in public repo (will be replaced)
$clearDirs = @("plugins", "skills", "agents", "common", "compatibility", "docs", ".github", ".claude-plugin", "mcp-setup", "prompt_examples")
foreach ($dir in $clearDirs) {
    $target = Join-Path $publicDir $dir
    if (Test-Path $target) {
        Remove-Item $target -Recurse -Force
        Write-Host "  Cleared: $dir" -ForegroundColor DarkGray
    }
}

# Copy each sync item
foreach ($item in $SyncItems) {
    $src = Join-Path $internalRoot $item
    $dst = Join-Path $publicDir $item

    if (-not (Test-Path $src)) {
        Write-Host "  Skip (not found): $item" -ForegroundColor DarkGray
        continue
    }

    # Create parent directory
    $dstParent = Split-Path $dst -Parent
    if (-not (Test-Path $dstParent)) {
        New-Item -ItemType Directory -Path $dstParent -Force | Out-Null
    }

    if ((Get-Item $src).PSIsContainer) {
        Copy-Item $src $dst -Recurse -Force
    } else {
        Copy-Item $src $dst -Force
    }
    Write-Host "  Synced: $item" -ForegroundColor DarkGray
}

# Remove excluded items that may have been copied as part of a parent directory
foreach ($pattern in $ExcludePatterns) {
    $target = Join-Path $publicDir $pattern
    if (Test-Path $target) {
        Remove-Item $target -Recurse -Force
        Write-Host "  Excluded: $pattern" -ForegroundColor DarkGray
    }
}

$publicReadmeSource = Join-Path $internalRoot "public/README.md"
$publicReadmeTarget = Join-Path $publicDir "README.md"
Copy-Item $publicReadmeSource $publicReadmeTarget -Force
Write-Host "  Published: public/README.md -> README.md" -ForegroundColor DarkGray

$publicChangelogSource = Join-Path $internalRoot "public/CHANGELOG.md"
$publicChangelogTarget = Join-Path $publicDir "CHANGELOG.md"
Copy-Item $publicChangelogSource $publicChangelogTarget -Force
Write-Host "  Published: public/CHANGELOG.md -> CHANGELOG.md" -ForegroundColor DarkGray

$publicSecuritySource = Join-Path $internalRoot "public/SECURITY.md"
$publicSecurityTarget = Join-Path $publicDir "SECURITY.md"
Copy-Item $publicSecuritySource $publicSecurityTarget -Force
Write-Host "  Published: public/SECURITY.md -> SECURITY.md" -ForegroundColor DarkGray

# Publish curated docs (default-deny). The internal docs/ folder is contributor-only
# and is intentionally NOT in $SyncItems, so a new file under docs/ stays private by
# default. The allow-list below is currently EMPTY: no docs are published to the public
# repo. To publish a doc in future, add its "docs/<file>.md" path here -- a deliberate,
# reviewable action rather than an implicit folder sync. Each entry maps to the same
# path under the public repo's docs/ folder.
$PublicDocs = @()
foreach ($doc in $PublicDocs) {
    $docSource = Join-Path $internalRoot $doc
    $docTarget = Join-Path $publicDir $doc
    if (Test-Path $docSource) {
        $docTargetDir = Split-Path $docTarget -Parent
        if (-not (Test-Path $docTargetDir)) {
            New-Item -ItemType Directory -Path $docTargetDir -Force | Out-Null
        }
        Copy-Item $docSource $docTarget -Force
        Write-Host "  Published: $doc" -ForegroundColor DarkGray
    } else {
        Write-Warning "  Allow-listed doc not found, skipping: $doc"
    }
}

# Flatten compatibility/ files to public repo root. compatibility/ itself is in
# $ExcludePatterns, so the folder will not be shipped — only these flattened
# copies remain at the root. AGENTS.md here intentionally overwrites the
# excluded internal contributor AGENTS.md with the user-facing version.
foreach ($flatten in $CompatibilityFlattens) {
    $compatSource = Join-Path $internalRoot $flatten.Source
    $compatTarget = Join-Path $publicDir $flatten.Target
    if (-not (Test-Path $compatSource)) {
        Write-Fail "$($flatten.Source) not found. This file is required for the public repo."
    }
    Copy-Item $compatSource $compatTarget -Force
    Write-Host "  Published: $($flatten.Source) -> $($flatten.Target)" -ForegroundColor DarkGray
}

$publicPackagePath = Join-Path $publicDir "package.json"
if (Test-Path $publicPackagePath) {
    $publicPackage = Get-Content $publicPackagePath -Raw | ConvertFrom-Json
    if ($publicPackage.PSObject.Properties.Name -contains "files") {
        $removedPackageFiles = @("compatibility/**", "install.ps1", "install.sh", "plugin.json")
        $originalPackageFiles = @($publicPackage.files)
        $filteredPackageFiles = @($originalPackageFiles | Where-Object { $removedPackageFiles -notcontains $_ })
        if ($filteredPackageFiles.Count -ne $originalPackageFiles.Count) {
            $publicPackage.files = $filteredPackageFiles
            $publicPackage | ConvertTo-Json -Depth 10 | Set-Content $publicPackagePath -NoNewline
            Write-Host "  Removed stale files entries from package.json" -ForegroundColor DarkGray
        }
    }
}

Write-Ok "Content synced"

# ── 4b. Strip plugin gitignore lines ─────────────────────────────────────────
# The internal repo gitignores materialized plugin content (build artifacts).
# The public repo needs these committed so `copilot plugin install` works
# from a GitHub URL (git clone only gets tracked files).

$gitignorePath = Join-Path $publicDir ".gitignore"
if (Test-Path $gitignorePath) {
    $lines = Get-Content $gitignorePath
    $filtered = $lines | Where-Object {
        $_ -notmatch '^plugins/\*/' -and
        $_ -notmatch '^# Plugin build artifacts' -and
        $_ -notmatch '^# by build/build_plugins\.py\. Internal repo' -and
        $_ -notmatch '^# manifests \+ canonical sources/' -and
        $_ -notmatch '^# today\) runs the build'
    }
    Set-Content $gitignorePath $filtered
    Write-Host "  Stripped plugin gitignore lines from .gitignore" -ForegroundColor DarkGray
}

# ── 5. Scrub internal references ────────────────────────────────────────────

Write-Step "Scrubbing internal references"

$scrubCount = 0
$textExtensions = @("*.json", "*.md", "*.yml", "*.yaml", "*.ps1", "*.sh", "*.py", "*.txt")
$textFileNames = @(".cursorrules", ".windsurfrules", ".gitignore", ".gitleaks.toml")

function Get-PublicTextFiles {
    $filesByPath = @{}

    foreach ($ext in $textExtensions) {
        $files = Get-ChildItem $publicDir -Recurse -Force -Filter $ext -File -ErrorAction SilentlyContinue
        foreach ($f in $files) {
            $filesByPath[$f.FullName] = $f
        }
    }

    $namedFiles = Get-ChildItem $publicDir -Recurse -Force -File -ErrorAction SilentlyContinue |
        Where-Object { $textFileNames -contains $_.Name }
    foreach ($f in $namedFiles) {
        $filesByPath[$f.FullName] = $f
    }

    return $filesByPath.Values
}

$textFiles = @(Get-PublicTextFiles)

foreach ($scrub in $Scrubs) {
    foreach ($f in $textFiles) {
        $content = Get-Content $f.FullName -Raw -ErrorAction SilentlyContinue
        if ($content -and $content.Contains($scrub.Find)) {
            $content = $content.Replace($scrub.Find, $scrub.Replace)
            Set-Content $f.FullName $content -NoNewline
            $scrubCount++
            Write-Host "  Scrubbed '$($scrub.Find)' in: $($f.FullName.Replace($publicDir, '.'))" -ForegroundColor DarkGray
        }
    }
}
Write-Ok "$scrubCount file(s) scrubbed"

# ── 6. Warn about remaining internal references ─────────────────────────────

Write-Step "Checking for remaining internal references"

$warnings = 0
foreach ($pattern in $WarnPatterns) {
    foreach ($f in $textFiles) {
        $content = Get-Content $f.FullName -Raw -ErrorAction SilentlyContinue
        if ($content -and $content.Contains($pattern)) {
            $warnings++
            Write-Warn "Found '$pattern' in: $($f.FullName.Replace($publicDir, '.'))"
        }
    }
}

if ($warnings -eq 0) {
    Write-Ok "No remaining internal references found"
} else {
    Write-Warn "$warnings file(s) still contain internal references — review before merging the PR"
}

# ── 7. Validate markdown links ───────────────────────────────────────────────

Write-Step "Validating markdown links (no broken references to excluded files)"

$brokenLinks = 0
$mdFiles = Get-ChildItem $publicDir -Recurse -Force -Filter "*.md" -File
foreach ($md in $mdFiles) {
    $content = Get-Content $md.FullName -Raw -ErrorAction SilentlyContinue
    if (-not $content) { continue }

    # Match markdown links: [text](path) — skip http/https/mailto
    $linkPattern = '\[([^\]]*?)\]\((?!https?://|mailto:)([^)#]+?)(?:#[^)]*)?\)'
    $matches_found = [regex]::Matches($content, $linkPattern)

    foreach ($m in $matches_found) {
        $linkPath = $m.Groups[2].Value.Trim()
        if ($linkPath.StartsWith('/')) { continue }  # absolute paths

        $resolvedPath = Join-Path (Split-Path $md.FullName) $linkPath
        $resolvedPath = [System.IO.Path]::GetFullPath($resolvedPath)

        if (-not (Test-Path $resolvedPath)) {
            $relFile = $md.FullName.Replace($publicDir, '.')
            $brokenLinks++
            Write-Warn "Broken link in $relFile -> $linkPath"
        }
    }
}

if ($brokenLinks -eq 0) {
    Write-Ok "All markdown links are valid"
} else {
    Write-Warn "$brokenLinks broken link(s) found — these reference files not included in the public repo"
}

# ── 8. Dry run summary ──────────────────────────────────────────────────────

if ($DryRun) {
    Write-Step "Dry run complete"

    Push-Location $publicDir
    $changes = git status --short
    Pop-Location

    Write-Host "`nChanges that would be committed:" -ForegroundColor Yellow
    $changes | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
    Write-Host "`nPublic repo clone at: $publicDir" -ForegroundColor Green
    Write-Host "Review the content, then re-run without -DryRun to publish.`n"
    exit 0
}

# ── 9. Create PR on public repo ─────────────────────────────────────────────

Write-Step "Creating PR on $PublicRepo"

Push-Location $publicDir
git add -A
git add -f plugins/ 2>&1 | Out-Null  # force-add gitignored plugin content
$changes = git diff --cached --stat
if (-not $changes) {
    Write-Warn "No changes to commit — public repo is already up to date."
    Pop-Location
    exit 0
}

git commit -m "Release v$Version from internal repo"
git push origin $branchName 2>&1
$pushExit = $LASTEXITCODE

# Bail immediately if `git push` failed. Continuing here is dangerous: if the PR
# already exists from a previous attempt, `gh pr list` will return its URL and
# the script will declare "PR ready" even though this attempt's commit never
# reached the remote branch.
if ($pushExit -ne 0) {
    Pop-Location
    Write-Warn "git push origin $branchName returned a non-zero exit code ($pushExit)."
    Write-Host "  The release commit did not reach $PublicRepo. Inspect the push output above" -ForegroundColor Yellow
    Write-Host "  and re-run this script once the push succeeds." -ForegroundColor Yellow
    Write-Fail "Public branch was not updated. Aborting before PR creation."
}

# Capture the public-repo PR URL. `gh pr list` returns "" when no PR yet exists, so
# `$prUrl` may be empty even after a successful `gh pr create` — we treat empty +
# zero-exit as a failure and exit non-zero with a clear actionable message. The
# common cause is Enterprise Managed User (EMU) `gh` tokens: they have push rights
# but no GraphQL `createPullRequest` access against external orgs, so the script
# can land the branch but not open the PR. The branch URL printed by `git push`
# is the manual fallback.
$prUrl = gh pr list --repo $PublicRepo --head $branchName --state open --json url --jq '.[0].url // empty'
$prCreateExit = 0
if (-not $prUrl) {
    $prUrl = gh pr create `
        --repo $PublicRepo `
        --title "Release v$Version" `
        --body "Auto-synced from internal repo release v$Version.`n`nNEXT STEP after this PR is merged: a maintainer must run Phase 2 to create the public tag + GitHub Release (the content below does NOT create a release on its own):`n  .\ReleaseScripts\PublishToPublic.ps1 -PublishRelease -Version $Version`n`nChanges:`n$changes" `
        --base main `
        --head $branchName
    $prCreateExit = $LASTEXITCODE
}

Pop-Location

if ($prCreateExit -ne 0 -or [string]::IsNullOrWhiteSpace($prUrl)) {
    Write-Warn "Could not create the PR on $PublicRepo via the API."
    Write-Host "  The branch was pushed successfully. Open the PR manually:" -ForegroundColor Yellow
    Write-Host "    https://github.com/$PublicRepo/compare/main...${branchName}?expand=1" -ForegroundColor Yellow
    Write-Host "  (Common cause: Enterprise Managed User 'gh' tokens cannot createPullRequest" -ForegroundColor Yellow
    Write-Host "   across orgs from CLI — use the web UI for this step.)" -ForegroundColor Yellow
    Write-Fail "Public PR was not created. See the URL above to finish manually."
}

Write-Ok "PR ready: $prUrl"

# ── 10. Cleanup ───────────────────────────────────────────────────────────────

Write-Step "Cleanup"
# Leave temp dir for review — user can delete manually
Write-Host "  Public repo clone at: $publicDir" -ForegroundColor Green
Write-Host "  Delete when done: Remove-Item '$tempDir' -Recurse -Force`n"

Write-Host "🎉 Publish to $PublicRepo complete!" -ForegroundColor Green

# --- 11. Phase-2 reminder (publish the release; do not stop at the content PR) ---
# Phase 1 only opens/updates the content PR. The public tag + GitHub Release are
# created by Phase 2 (-PublishRelease), a SEPARATE manual run after the PR merges.
# Forgetting Phase 2 ships content with no release/tag (happened for v0.3.2/v0.3.3),
# so make the next step loud here. The Public Release Parity workflow is the backstop.
Write-Step "NEXT STEP (REQUIRED): publish the release (Phase 2)"
Write-Warn "The content PR is open, but the public tag + GitHub Release do NOT exist yet."
Write-Host "  After the PR above is reviewed and merged, run:" -ForegroundColor Yellow
Write-Host "    .\ReleaseScripts\PublishToPublic.ps1 -PublishRelease -Version $Version" -ForegroundColor Green
Write-Warn "Skip it and $PublicRepo has content with no release -- the weekly Public Release Parity check will open a tracking issue."
