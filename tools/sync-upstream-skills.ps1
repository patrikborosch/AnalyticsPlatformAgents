#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Overlay-sync upstream skills-for-fabric content into creator/, preserving local custom additions.

.DESCRIPTION
    Resolves the latest upstream release tag (or an explicit -Ref), shallow-clones it, and refreshes
    ONLY upstream-owned files under creator/. Any skill or file you added that upstream does not ship is
    tracked via creator/.upstream-manifest.json and is never deleted or overwritten.

    Runs both in CI (GitHub Actions, ubuntu pwsh) and locally. When $env:GITHUB_OUTPUT is set it emits:
        changed (true|false), tag, pr_title, changelog

.NOTES
    Custom modifications should be NEW skill folders, not in-place edits of upstream skills — an in-place
    edit of an upstream-owned file WILL be overwritten on sync (the PR diff lets you catch that).
#>
[CmdletBinding()]
param(
    [string]   $RepoRoot      = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]   $UpstreamRepo  = 'gim-home/skills-for-fabric',
    [string]   $Ref           = '',
    [string[]] $MirrorDirs    = @('skills', 'common', 'docs', 'mcp-setup', 'prompt_examples', 'agents'),
    [string[]] $MirrorFiles   = @('CHANGELOG.md')
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$creator      = Join-Path $RepoRoot 'creator'
$manifestPath = Join-Path $creator  '.upstream-manifest.json'
$versionPath  = Join-Path $creator  '.upstream-version.json'

function Set-Output {
    param([string]$Name, [string]$Value)
    if ($env:GITHUB_OUTPUT) {
        if ($Value -match "`n") {
            $delim = "EOF_$([guid]::NewGuid().ToString('N'))"
            Add-Content -Path $env:GITHUB_OUTPUT -Value "$Name<<$delim`n$Value`n$delim"
        }
        else {
            Add-Content -Path $env:GITHUB_OUTPUT -Value "$Name=$Value"
        }
    }
}

# --- 1. Resolve target tag -----------------------------------------------------------------
$cloneUrl = "https://github.com/$UpstreamRepo.git"
if (-not [string]::IsNullOrWhiteSpace($Ref)) {
    $target = $Ref
}
else {
    Write-Host "Resolving latest release tag for $UpstreamRepo ..."
    $target = ''

    # Method A: GitHub releases API via gh (reliable; uses GH_TOKEN/GITHUB_TOKEN in CI, keyring locally).
    if (Get-Command gh -ErrorAction SilentlyContinue) {
        $t = gh api "repos/$UpstreamRepo/releases/latest" --jq '.tag_name' 2>$null
        if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($t)) { $target = $t.Trim() }
    }

    # Method B: parse remote tags via git. Clear any inherited auth header (actions/checkout sets
    # http.https://github.com/.extraheader in the local repo config, which can break ls-remote here).
    if ([string]::IsNullOrWhiteSpace($target)) {
        $lines = git -c 'http.https://github.com/.extraheader=' ls-remote --tags --refs $cloneUrl 2>$null
        $tags = foreach ($l in $lines) {
            if ($l -match 'refs/tags/(.+)$') {
                $tg = $Matches[1]
                $sv = ($tg.TrimStart('v', 'V') -split '-')[0]
                $parsed = $null
                if ([version]::TryParse($sv, [ref]$parsed)) {
                    [pscustomobject]@{ Tag = $tg; Ver = $parsed }
                }
            }
        }
        if ($tags) { $target = ($tags | Sort-Object Ver -Descending | Select-Object -First 1).Tag }
    }

    if ([string]::IsNullOrWhiteSpace($target)) { throw "Could not resolve latest release tag for $UpstreamRepo" }
}
Write-Host "Target ref: $target"

# --- 2. Short-circuit if already at target ------------------------------------------------
$current = ''
if (Test-Path $versionPath) {
    try { $current = (Get-Content $versionPath -Raw | ConvertFrom-Json).tag } catch { $current = '' }
}
if ($current -eq $target -and [string]::IsNullOrWhiteSpace($Ref)) {
    Write-Host "Already at $target -- nothing to do."
    Set-Output 'changed' 'false'
    Set-Output 'tag' $target
    return
}

# --- 3. Clone upstream at ref --------------------------------------------------------------
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("sff_" + [guid]::NewGuid().ToString('N'))
Write-Host "Cloning $cloneUrl @ $target -> $tmp"
git clone --depth 1 --branch $target $cloneUrl $tmp 2>&1 | Write-Host
if ($LASTEXITCODE -ne 0) {
    Write-Host "Shallow branch clone failed; falling back to full clone + checkout."
    git clone $cloneUrl $tmp 2>&1 | Write-Host
    git -C $tmp checkout $target 2>&1 | Write-Host
    if ($LASTEXITCODE -ne 0) { throw "Unable to clone/checkout $UpstreamRepo @ $target" }
}

try {
    # --- 4. Enumerate upstream files to mirror --------------------------------------------
    $newFiles = New-Object System.Collections.Generic.List[string]
    foreach ($d in $MirrorDirs) {
        $src = Join-Path $tmp $d
        if (Test-Path $src) {
            Get-ChildItem $src -Recurse -File | ForEach-Object {
                $rel = $_.FullName.Substring($tmp.Length).TrimStart('\', '/').Replace('\', '/')
                $newFiles.Add($rel)
            }
        }
    }
    foreach ($f in $MirrorFiles) {
        if (Test-Path (Join-Path $tmp $f)) { $newFiles.Add($f) }
    }
    if ($newFiles.Count -eq 0) { throw "No upstream files found to mirror -- aborting to avoid data loss." }
    $newSet = [System.Collections.Generic.HashSet[string]]::new([string[]]$newFiles)

    # --- 5. Load previous manifest --------------------------------------------------------
    $oldFiles = @()
    if (Test-Path $manifestPath) {
        try { $oldFiles = @((Get-Content $manifestPath -Raw | ConvertFrom-Json)) } catch { $oldFiles = @() }
    }

    # --- 6. Delete upstream-owned files that upstream removed (custom files untouched) ----
    foreach ($rel in $oldFiles) {
        if (-not $newSet.Contains($rel)) {
            $dest = Join-Path $creator $rel
            if (Test-Path $dest) { Remove-Item $dest -Force; Write-Host "removed: $rel" }
        }
    }

    # --- 7. Copy upstream files into creator/ (overwrite) ---------------------------------
    foreach ($rel in $newFiles) {
        $src     = Join-Path $tmp $rel
        $dest    = Join-Path $creator $rel
        $destDir = Split-Path $dest -Parent
        if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
        Copy-Item $src $dest -Force
    }

    # --- 8. Prune now-empty directories under mirrored roots ------------------------------
    foreach ($d in $MirrorDirs) {
        $root = Join-Path $creator $d
        if (Test-Path $root) {
            Get-ChildItem $root -Recurse -Directory | Sort-Object FullName -Descending | ForEach-Object {
                if (-not (Get-ChildItem $_.FullName -Force)) { Remove-Item $_.FullName -Force }
            }
        }
    }

    # --- 9. Write manifest + version stamp ------------------------------------------------
    ($newFiles | Sort-Object -Unique) | ConvertTo-Json -Depth 2 -AsArray | Set-Content $manifestPath -Encoding utf8
    [pscustomobject]@{
        tag       = $target
        repo      = $UpstreamRepo
        syncedUtc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    } | ConvertTo-Json | Set-Content $versionPath -Encoding utf8

    # --- 10. Changelog excerpt (entries newer than the previously-synced version) ---------
    $excerpt = ''
    $clPath  = Join-Path $tmp 'CHANGELOG.md'
    if (Test-Path $clPath) {
        $cl = Get-Content $clPath -Raw
        if ($current) {
            $idx = $cl.IndexOf($current)
            if ($idx -gt 0) { $excerpt = $cl.Substring(0, $idx).TrimEnd() }
        }
        if (-not $excerpt) { $excerpt = (($cl -split "`n") | Select-Object -First 40) -join "`n" }
    }

    $prevLabel = if ($current) { "``$current``" } else { 'none' }
    $title = "chore: sync skills-for-fabric to $target"
    $body  = @"
Automated overlay sync of upstream ``$UpstreamRepo`` to **$target** (was: $prevLabel).

Custom skills and agents are preserved (tracked via ``creator/.upstream-manifest.json``). Review the diff for any
in-place edits to upstream-owned files that were intentionally overwritten.

---

$excerpt
"@

    Write-Host "Sync complete: $current -> $target"
    Set-Output 'changed'   'true'
    Set-Output 'tag'       $target
    Set-Output 'pr_title'  $title
    Set-Output 'changelog' $body
}
finally {
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }
}
