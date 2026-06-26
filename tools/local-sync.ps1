#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Hop 2 of the update chain: publish AnalyticsPlatformAgents agents + custom skills into the
    global Copilot / VS Code environment so they are available in EVERY workspace.

.DESCRIPTION
    1. git pull (fast-forward only) the repository.
    2. Copy CUSTOM skills (those NOT owned by upstream skills-for-fabric) into ~/.agents/skills/.
       Upstream skills stay served by the installed skills-for-fabric plugin (kept fresh via
       '/plugin update fabric-skills@fabric-collection' / the weekly check-updates prompt), so we
       do not duplicate them. Use -IncludeUpstream to mirror ALL skills instead.
    3. Copy creator/common into ~/.agents/common/ so skills' '../../common/...' references resolve.
    4. Copy agents/*.agent.md into the VS Code user prompts folder (user-level agents that roam).

    Upstream ownership is read from creator/.upstream-manifest.json (produced by sync-upstream-skills.ps1);
    if that file is absent it falls back to the installed plugin's skills directory.

.EXAMPLE
    pwsh -File tools/local-sync.ps1
.EXAMPLE
    pwsh -File tools/local-sync.ps1 -IncludeUpstream   # mirror every skill globally
#>
[CmdletBinding()]
param(
    [string] $RepoRoot    = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string] $AgentsDest  = (Join-Path $HOME '.agents'),
    [string] $PromptsDest = (Join-Path $env:APPDATA 'Code/User/prompts'),
    [switch] $IncludeUpstream,
    [switch] $NoPull
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$creator = Join-Path $RepoRoot 'creator'

# --- 1. Pull latest -----------------------------------------------------------------------
if (-not $NoPull) {
    Write-Host "Pulling latest in $RepoRoot ..."
    git -C $RepoRoot pull --ff-only 2>&1 | Write-Host
}

# --- 2. Determine upstream-owned skill names ----------------------------------------------
$upstreamSkills = @()
$manifest = Join-Path $creator '.upstream-manifest.json'
if (Test-Path $manifest) {
    $rels = @((Get-Content $manifest -Raw | ConvertFrom-Json))
    $upstreamSkills = $rels |
        Where-Object { $_ -match '^skills/([^/]+)/' } |
        ForEach-Object { ($_ -split '/')[1] } |
        Sort-Object -Unique
}
if (-not $upstreamSkills) {
    # Fallback: treat whatever the installed plugin ships as upstream-owned.
    $pluginSkills = Join-Path $HOME '.copilot/installed-plugins/fabric-collection/skills-for-fabric/skills'
    if (Test-Path $pluginSkills) {
        $upstreamSkills = Get-ChildItem $pluginSkills -Directory | Select-Object -ExpandProperty Name
    }
}

# --- 3. Copy skills -----------------------------------------------------------------------
$skillsSrc  = Join-Path $creator 'skills'
$skillsDest = Join-Path $AgentsDest 'skills'
New-Item -ItemType Directory -Path $skillsDest -Force | Out-Null

$copied = 0
Get-ChildItem $skillsSrc -Directory | ForEach-Object {
    $name       = $_.Name
    $isUpstream = $upstreamSkills -contains $name
    if ($IncludeUpstream -or -not $isUpstream) {
        $dest = Join-Path $skillsDest $name
        if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
        Copy-Item $_.FullName $dest -Recurse -Force
        $copied++
        $tag = if ($isUpstream) { ' (upstream, forced)' } else { ' (custom)' }
        Write-Host "skill -> $name$tag"
    }
}

# --- 4. Copy common (needed by skills' '../../common' references) --------------------------
$commonSrc = Join-Path $creator 'common'
if (Test-Path $commonSrc) {
    $commonDest = Join-Path $AgentsDest 'common'
    if (Test-Path $commonDest) { Remove-Item $commonDest -Recurse -Force }
    Copy-Item $commonSrc $commonDest -Recurse -Force
    Write-Host "common -> $commonDest"
}

# --- 5. Copy agents (*.agent.md) into the VS Code user prompts folder ----------------------
New-Item -ItemType Directory -Path $PromptsDest -Force | Out-Null
$agentCount = 0
$agentsSrc = Join-Path $RepoRoot 'agents'
if (Test-Path $agentsSrc) {
    Get-ChildItem $agentsSrc -Filter '*.agent.md' -File | ForEach-Object {
        Copy-Item $_.FullName (Join-Path $PromptsDest $_.Name) -Force
        $agentCount++
        Write-Host "agent -> $($_.Name)"
    }
}

Write-Host ''
Write-Host "Done. $copied skill(s) and $agentCount agent(s) synced to the global environment."
Write-Host "Upstream skills remain served by the installed skills-for-fabric plugin"
Write-Host "(run '/plugin update fabric-skills@fabric-collection' or let check-updates prompt weekly)."
