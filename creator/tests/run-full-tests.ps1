param(
    [Parameter(Mandatory = $false)]
    [string]$TestFolder,
    [Parameter(Mandatory = $false)]
    [switch]$SkipCleanup,
    [Parameter(Mandatory = $false)]
    [string]$tenant = "E2EAPIMSIT2.onmicrosoft.com",
    [Parameter(Mandatory = $false)]
    [switch]$skipLogin,
    [Parameter(Mandatory = $false)]
    [switch]$SkipWarehouse,
    [Parameter(Mandatory = $false)]
    [switch]$SkipLakehouse,
    [Parameter(Mandatory = $false)]
    [string]$spLogin,
    [Parameter(Mandatory = $false)]
    [string]$spCertPath,
    [Parameter(Mandatory = $false)]
    [string]$spObjectId,
    # Optional comma/semicolon/space-separated list of plan basenames or wildcards
    # (e.g. "eval-dataflows-authoring", "eval-probe-*", "eval-medallion,eval-probe-*").
    # PR-touched orchestrator passes exact basenames; per-plugin probe / manual
    # dispatch can pass wildcards. Validation is strict: any pattern that matches
    # zero catalog plans fails BEFORE workspace/warehouse/lakehouse provisioning, so
    # an orchestrator typo never strands tenant resources. Empty = run all (default).
    [Parameter(Mandatory = $false)]
    [string]$PlanFilter,
    [Parameter(Mandatory = $false)]
    [string]$capacityId,
    [Parameter(Mandatory = $false)]
    [int]$ThrottleLimit = 4
)

$ErrorActionPreference = "Stop"

# Validate SP login parameters: both must be set, or neither.
if (($spLogin -and -not $spCertPath) -or (-not $spLogin -and $spCertPath)) {
    Write-Error "-spLogin and -spCertPath must be provided together (got spLogin='$spLogin', spCertPath='$spCertPath'). Pass both to use a service principal, or neither to use the current az identity."
    return
}

# Validate -capacityId. The workflow guardrail trims + rejects whitespace-only
# before invoking this script, but when called locally we must apply the same
# validation so a typo or stray-space flag produces an actionable error early
# rather than a confusing REST failure on workspace create.
if ($PSBoundParameters.ContainsKey('capacityId') -and $null -ne $capacityId) {
    $capacityId = $capacityId.Trim().TrimStart('{').TrimEnd('}')
    if ([string]::IsNullOrWhiteSpace($capacityId)) {
        Write-Error "-capacityId must not be empty or whitespace-only. Omit the flag entirely to use discovery."
        return
    }
    $parsedGuid = [Guid]::Empty
    if (-not [Guid]::TryParse($capacityId, [ref]$parsedGuid)) {
        Write-Error "-capacityId must be a valid GUID (got '$capacityId'). Use the bare GUID form without braces."
        return
    }
    $capacityId = $parsedGuid.ToString()
}

# Validate -ThrottleLimit. A value < 1 makes the throttle loop never progress
# (the orchestrator would wait forever for a free slot). Use 1 for legacy
# serial behavior, 4 (default) for parallel. Hard cap at 8 to keep memory +
# Copilot session-state IO predictable on hosted runners.
if ($ThrottleLimit -lt 1) {
    Write-Error "-ThrottleLimit must be >= 1 (got '$ThrottleLimit'). Use 1 for serial execution; 4 is the default."
    return
}
if ($ThrottleLimit -gt 8) {
    Write-Warning "-ThrottleLimit '$ThrottleLimit' exceeds practical cap of 8 on hosted runners; capping to 8."
    $ThrottleLimit = 8
}

# Ensure Start-ThreadJob is available (ThreadJob module ships with PowerShell 7+;
# on Windows PowerShell 5.1 it must be installed separately).
if (-not (Get-Command Start-ThreadJob -ErrorAction SilentlyContinue)) {
    try { Import-Module ThreadJob -ErrorAction Stop } catch {
        Write-Error "Start-ThreadJob is required for parallel orchestration. Install the ThreadJob module (Install-Module ThreadJob) or run under PowerShell 7+."
        return
    }
}


# Resolve paths
$evalSource = Join-Path $PSScriptRoot "full-eval-tests"
$repoRoot   = Split-Path -Parent $PSScriptRoot

$telemetryHelperPath = Join-Path $PSScriptRoot "copilot-session-telemetry.ps1"
$copilotInvokePath   = Join-Path $PSScriptRoot "copilot-invoke.ps1"
. $telemetryHelperPath
. $copilotInvokePath

# ---------------------------------------------------------------------------
# Validate -PlanFilter against the in-repo plan catalog BEFORE any provisioning.
# Each pattern (exact basename OR wildcard like "eval-probe-*") must match at
# least one catalog plan; unmatched patterns hard-fail so a CI-orchestrator typo
# never silently runs zero plans (and, more importantly, so we exit BEFORE
# creating any Fabric resources that would then strand on the shared tenant).
# Trim whitespace-only input so " " behaves identically to "" (run all). The
# in-repo catalog under $evalSource/plan/ is the source-of-truth for plan
# basenames; the runtime $TestFolder copy is byte-identical because it is
# produced by a recursive Copy-Item later in this script. The matching
# filter is applied to the runtime $evalPlans list further below.
# Accepts comma / semicolon / whitespace as separators (matches PR #271's
# per-plugin probe path) and strips an optional trailing .md so a caller
# passing "eval-probe-*.md" works the same as "eval-probe-*".
# ---------------------------------------------------------------------------
$PlanFilter = if ($PlanFilter) { $PlanFilter.Trim() } else { '' }
$planFilterSet = @()
if ($PlanFilter) {
    $planFilterSet = @($PlanFilter -split '[,;\s]+' | ForEach-Object { $_.Trim() -replace '\.md$', '' } | Where-Object { $_ })
    if ($planFilterSet.Count -gt 0) {
        $sourcePlansDir = Join-Path $evalSource "plan"
        if (-not (Test-Path $sourcePlansDir)) {
            Write-Error "Cannot validate -PlanFilter: source plans directory '$sourcePlansDir' does not exist."
            return
        }
        $catalogNames = @(Get-ChildItem -Path $sourcePlansDir -Filter "eval-*.md" -File -Recurse | ForEach-Object { $_.BaseName })
        if ($catalogNames.Count -eq 0) {
            Write-Error "Cannot validate -PlanFilter: no eval-*.md files found under '$sourcePlansDir'."
            return
        }
        # A pattern is valid if at least one catalog BaseName matches it via
        # -like (wildcard) -- which collapses to exact match when the pattern
        # contains no wildcard chars.
        $unknown = @($planFilterSet | Where-Object {
            $pattern = $_
            -not ($catalogNames | Where-Object { $_ -like $pattern })
        })
        if ($unknown.Count -gt 0) {
            Write-Error "PlanFilter pattern(s) match no plans: [$($unknown -join ', ')]. Known plans: [$($catalogNames -join ', ')]"
            return
        }
        Write-Host "PlanFilter validated against catalog: $($planFilterSet.Count) pattern(s) match the in-repo catalog of $($catalogNames.Count) plan(s)."
    }
    else {
        Write-Host "PlanFilter contained only whitespace/empty tokens after trim; treating as no filter (run all plans)."
        $PlanFilter = ''
    }
}

# Create or resolve TestFolder
if (-not $TestFolder) {
    $guid = [System.Guid]::NewGuid().ToString()
    $TestFolder = Join-Path ([System.IO.Path]::GetTempPath()) $guid
}
if (-not (Test-Path $TestFolder)) {
    New-Item -ItemType Directory -Path $TestFolder -Force | Out-Null
}

# -------------------------------------------------------------------
# Provision workspace (dynamic, like smoke tests)
# -------------------------------------------------------------------
$timestamp = (Get-Date).ToString("yyyyMMddHHmmss")
$workspaceName = "FullEval-$timestamp"
$fabricApi = "https://api.fabric.microsoft.com/v1"

# Shared infrastructure item names — timestamped to avoid cross-run collisions
$warehouseName   = "EvalWarehouse$timestamp"
$lakehouseName   = "eval_sales_lh_$timestamp"
$eventhouseName  = "EvalEventhouse$timestamp"
$kqlDbName       = "EvalKQLDB$timestamp"

# -------------------------------------------------------------------
# Prerequisites
# -------------------------------------------------------------------
# Test user:  apitestadmin@E2EAPIMSIT2.onmicrosoft.com
#
# Authentication uses a certificate downloaded from Azure Key Vault:
#   https://ms.portal.azure.com/#view/Microsoft_Azure_KeyVault/ListObjectVersionsRBACBlade/~/overview/objectType/certificates/objectId/https%3A%2F%2Fe2eapimsit2-ga.vault.azure.net%2Fcertificates%2FE2EAPIMSIT2-apitestadmin/vaultResourceUri/%2Fsubscriptions%2F70a05e70-7ce4-45b3-9503-0bbf83c2a864%2FresourceGroups%2FProdTestTenants%2Fproviders%2FMicrosoft.KeyVault%2Fvaults%2FE2EAPIMSIT2-GA/vaultId/%2Fsubscriptions%2F70a05e70-7ce4-45b3-9503-0bbf83c2a864%2FresourceGroups%2FProdTestTenants%2Fproviders%2FMicrosoft.KeyVault%2Fvaults%2FE2EAPIMSIT2-GA
#
# To get access to the Key Vault, request this entitlement:
#   https://coreidentity.microsoft.com/manage/Entitlement/entitlement/pbitestusera-3iqq
# -------------------------------------------------------------------

Write-Host ""
Write-Host "==============================" -ForegroundColor Cyan
Write-Host "  Full Eval Prerequisites" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan
Write-Host "  Test user:    apitestadmin@E2EAPIMSIT2.onmicrosoft.com"
Write-Host "  Certificate:  Download from Azure Key Vault:"
Write-Host "    https://ms.portal.azure.com/#view/Microsoft_Azure_KeyVault/ListObjectVersionsRBACBlade/~/overview/objectType/certificates/objectId/https%3A%2F%2Fe2eapimsit2-ga.vault.azure.net%2Fcertificates%2FE2EAPIMSIT2-apitestadmin/vaultResourceUri/%2Fsubscriptions%2F70a05e70-7ce4-45b3-9503-0bbf83c2a864%2FresourceGroups%2FProdTestTenants%2Fproviders%2FMicrosoft.KeyVault%2Fvaults%2FE2EAPIMSIT2-GA/vaultId/%2Fsubscriptions%2F70a05e70-7ce4-45b3-9503-0bbf83c2a864%2FresourceGroups%2FProdTestTenants%2Fproviders%2FMicrosoft.KeyVault%2Fvaults%2FE2EAPIMSIT2-GA"
Write-Host "  Entitlement:  https://coreidentity.microsoft.com/manage/Entitlement/entitlement/pbitestusera-3iqq"
Write-Host ""

Write-Host "========================================="
Write-Host "  Full Eval Runner"
Write-Host "========================================="
Write-Host "  Test folder: $TestFolder"
Write-Host "  Workspace:   $workspaceName"
Write-Host "========================================="

if (-not $skipLogin) {
    if ($spLogin -and $spCertPath) {
        # Service principal login (CI path).
        Write-Host "`n--- Logging in as service principal: $spLogin (tenant $tenant) ---" -ForegroundColor Yellow
        if (-not (Test-Path $spCertPath)) {
            Write-Error "spCertPath '$spCertPath' does not exist"
            return
        }
        az login --service-principal --tenant $tenant --username $spLogin --certificate $spCertPath --allow-no-subscriptions | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Service principal login failed (LASTEXITCODE=$LASTEXITCODE)"
            return
        }
        Write-Host "  Logged in as SP."
    } else {
        # Interactive login (local dev path).
        Write-Host "`n--- Logging in to $tenant ---"
        az login --tenant $tenant
        if ($LASTEXITCODE -ne 0) {
            Write-Error "az login failed with exit code $LASTEXITCODE"
            return
        }
        Write-Host "  Logged in."
    }
}

$token = (az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv)
if (-not $token) {
    Write-Error "Failed to get Fabric access token"
    return
}
$headers = @{ "Authorization" = "Bearer $token"; "Content-Type" = "application/json" }

# Discover capacity (or use pinned capacity when caller supplied -capacityId)
Write-Host "`n--- Discovering Fabric capacity ---"
if ($capacityId) {
    Write-Host "  Using pinned Fabric capacity: $capacityId" -ForegroundColor Cyan
} else {
    $capsResp = Invoke-RestMethod -Uri "$fabricApi/capacities" -Headers $headers -Method Get
    foreach ($cap in $capsResp.value) {
        if ($cap.state -eq "Active" -and -not $capacityId) {
            $capacityId = $cap.id
            Write-Host "  Using capacity: $($cap.displayName) ($capacityId)"
        }
    }
    if (-not $capacityId) {
        Write-Error "No active Fabric capacity found."
        return
    }
}

# Create workspace
Write-Host "`n--- Creating workspace: $workspaceName ---"
$wsBody = @{ displayName = $workspaceName; capacityId = $capacityId } | ConvertTo-Json
$ws = Invoke-RestMethod -Uri "$fabricApi/workspaces" -Headers $headers -Method Post -Body $wsBody
if (-not $ws.id) {
    Write-Error "Failed to create workspace: $($ws | ConvertTo-Json -Depth 5)"
    return
}
$workspaceId = $ws.id
Write-Host "  Created: $workspaceName ($workspaceId)"

# Wait for capacity assignment
for ($i = 0; $i -lt 24; $i++) {
    $wsCheck = Invoke-RestMethod -Uri "$fabricApi/workspaces/$workspaceId" -Headers $headers -Method Get
    if ($wsCheck.capacityAssignmentProgress -eq "Completed") { break }
    Write-Host "  Waiting for capacity assignment..."
    Start-Sleep -Seconds 5
}
Write-Host "  Capacity assigned.`n"

# Clean and copy eval framework
Get-ChildItem -Path $TestFolder -Recurse -Force | Remove-Item -Recurse -Force
Copy-Item -Path (Join-Path $evalSource "*") -Destination $TestFolder -Recurse -Force
Write-Host "Copied eval framework to: $TestFolder"

# Replace placeholders in copied eval plans
Get-ChildItem -Path $TestFolder -Filter "*.md" -Recurse | ForEach-Object {
    $content = Get-Content -Path $_.FullName -Raw
    if ($content -match '\{\{(WORKSPACE|WAREHOUSE|LAKEHOUSE|EVENTHOUSE|KQLDB)') {
        $content = $content -replace '\{\{WORKSPACE_ID\}\}', $workspaceId
        $content = $content -replace '\{\{WORKSPACE\}\}', $workspaceName
        $content = $content -replace '\{\{WAREHOUSE\}\}', $warehouseName
        $content = $content -replace '\{\{LAKEHOUSE\}\}', $lakehouseName
        $content = $content -replace '\{\{EVENTHOUSE\}\}', $eventhouseName
        $content = $content -replace '\{\{KQLDB\}\}', $kqlDbName
        Set-Content -Path $_.FullName -Value $content -NoNewline
        Write-Host "  Substituted placeholders in: $($_.Name)"
    }
}

# Reinstall the local plugin marketplace (per-plugin plugin install moved into
# the per-plugin outer loop further down, since each plan may now opt into a
# specific plugin via YAML front-matter `plugin: <name>`. Plans without that
# field default to "fabric-skills" and the behaviour matches the historical
# single install when only one plugin is used.)
$marketplaceList = copilot plugin marketplace list 2>&1 | Out-String
if ($marketplaceList -match 'fabric-collection') {
    copilot plugin marketplace remove fabric-collection --force
}
copilot plugin marketplace add $repoRoot

# Helper: parse a leading YAML front-matter block from an eval plan markdown
# file and return the `plugin:` value if present. Defaults to "fabric-skills"
# when the plan has no front-matter or no `plugin:` key. The parser only
# recognises a simple `key: value` shape (no nested YAML), which is all the
# plan-level metadata needs today.
function Get-EvalPlanPlugin {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PlanPath
    )
    if (-not (Test-Path $PlanPath)) { return "fabric-skills" }
    $raw = Get-Content $PlanPath -Raw -ErrorAction SilentlyContinue
    if (-not $raw) { return "fabric-skills" }
    if (-not ($raw -match '^\s*---\s*\r?\n([\s\S]*?)\r?\n---\s*\r?\n')) {
        return "fabric-skills"
    }
    $front = $Matches[1]
    foreach ($line in $front -split "`n") {
        if ($line -match '^\s*plugin\s*:\s*(.+?)\s*$') {
            $value = $Matches[1].Trim().Trim('"', "'")
            if (-not [string]::IsNullOrWhiteSpace($value)) { return $value }
        }
    }
    return "fabric-skills"
}

# Track which plugin is currently installed so we only reinstall when the next
# plugin group needs a different one. First iteration always installs. Plugin
# install failures fail loud — silent stale state would be much worse than a
# clear failure here.
$script:currentInstalledPlugin = $null
function Sync-PluginInstallation {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Plugin
    )
    if ($script:currentInstalledPlugin -eq $Plugin) { return }
    if ($null -ne $script:currentInstalledPlugin) {
        $prev = $script:currentInstalledPlugin
        copilot plugin uninstall "$prev@fabric-collection" 2>&1 | Out-Null
        $uninstallExit = $LASTEXITCODE
        # Best-effort stdio MCP sweep: stdio MCPs spawned by the previous
        # plugin may linger past `plugin uninstall` (npx subprocess); leaving
        # them alive can compete for stdin with the next plugin's MCPs AND can
        # hold a lock that makes `plugin uninstall` itself return non-zero.
        # All ThreadJobs from the previous plugin group have already joined
        # before this is called, so killing matching processes is safe. Run the
        # sweep BEFORE any uninstall retry so the retry has a clean slate.
        try {
            $needle = "installed-plugins.*$([regex]::Escape($prev))"
            $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                Where-Object { $_.CommandLine -and $_.CommandLine -match $needle }
            foreach ($p in $procs) {
                try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop }
                catch { Write-Warning "Failed to stop lingering MCP process $($p.ProcessId): $_" }
            }
        } catch {
            Write-Warning "MCP process sweep failed for previous plugin '$prev': $_"
        }
        # `copilot plugin uninstall` is intermittently flaky on Windows: a
        # lingering stdio-MCP npx subprocess can hold a lock and make the first
        # uninstall return non-zero even though the plugin is effectively gone.
        # Do NOT abort here -- a non-fatal uninstall hiccup must not discard a
        # multi-hour eval run (this exact throw aborted the 2026-06-13 nightly
        # at the cosmetic post-processing reset). Retry once after the sweep,
        # then fall through to install regardless: the `plugin install` below is
        # the real correctness gate and fails loudly if the switch genuinely
        # cannot proceed with stale state.
        if ($uninstallExit -ne 0) {
            Write-Warning "First 'plugin uninstall $prev@fabric-collection' returned exit $uninstallExit; retrying once after MCP sweep."
            copilot plugin uninstall "$prev@fabric-collection" 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Retry uninstall of '$prev@fabric-collection' also returned non-zero; proceeding to install '$Plugin' anyway (install will fail if state is genuinely stale)."
            }
        }
    }
    copilot plugin install "$Plugin@fabric-collection"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to install plugin '$Plugin@fabric-collection' (exit code $LASTEXITCODE)."
        throw "plugin install failed"
    }
    $script:currentInstalledPlugin = $Plugin
}

# ---------------------------------------------------------------------------
# Discover eval plan files
# ---------------------------------------------------------------------------
$plansDir = Join-Path $TestFolder "plan"
$evalPlans = @()
if (Test-Path $plansDir) {
    $evalPlans += Get-ChildItem -Path $plansDir -Filter "eval-*.md" -File -Recurse
}

if ($evalPlans.Count -eq 0) {
    Write-Error "No eval plan files found."
    return
}

# ---------------------------------------------------------------------------
# Apply the validated -PlanFilter to the runtime $evalPlans. Validation of the
# filter against the in-repo plan catalog happens BEFORE workspace creation
# (see early block near the top of the script); we only need to apply the
# now-known-good filter to the FileInfo objects whose FullName paths are
# anchored under $TestFolder for downstream chain dispatch. Match against
# BaseName so both exact basenames (PR-touched path) and wildcards (per-plugin
# probe path / manual dispatch, e.g. "eval-probe-*") work identically.
# ---------------------------------------------------------------------------
if ($planFilterSet.Count -gt 0) {
    $beforeCount = $evalPlans.Count
    $evalPlans = @($evalPlans | Where-Object {
        $name = $_.BaseName
        foreach ($pattern in $planFilterSet) {
            if ($name -like $pattern) { return $true }
        }
        return $false
    })
    if ($evalPlans.Count -eq 0) {
        Write-Error "PlanFilter '$PlanFilter' matched 0 plans on disk under '$plansDir'. Filter pattern(s)=[$($planFilterSet -join ',')]. The catalog validation passed earlier but the runtime copy is missing those plan files; this should never happen."
        return
    }
    Write-Host "`nPlanFilter applied: $beforeCount -> $($evalPlans.Count) plan(s) selected."
}

Write-Host "`nFound $($evalPlans.Count) eval plan(s) to execute:`n"
$evalPlans | ForEach-Object { Write-Host "  - $($_.Name)" }

# ---------------------------------------------------------------------------
# Run workspace cleanup (Phase 0)
# ---------------------------------------------------------------------------
$cleanupTelemetry = $null
if ($SkipCleanup) {
    Write-Host "`n--- Phase 0: Workspace Cleanup (SKIPPED via -SkipCleanup) ---"
    $cleanupTelemetry = [PSCustomObject]@{
        phase                = "cleanup"
        status               = "skipped"
        durationSeconds      = 0
        error                = $null
        exitCode             = $null
        bailOutCode          = $null
        unsupportedOptionHits = 0
        logPath              = $null
        session              = $null
    }
}
else {
    Write-Host "`n--- Phase 0: Workspace Cleanup ---"
    $cleanupPrompt = @"
The eval workspace is '$workspaceName' (ID: $workspaceId). It was just created and is empty.
Follow plan/00-overview.md — Phase 0 workspace provisioning is already done. Confirm the workspace is ready.
"@
    $cleanupLog = Join-Path $TestFolder "phase0-cleanup.log"
    $cleanupRun = $null
    $cleanupError = $null
    $cleanupStart = Get-Date
    try {

        Write-Host "========================================="
        Write-Host "  INVOCATION:"
        Write-Host $cleanupPrompt
        Write-Host "========================================="

        $cleanupRun = Invoke-CopilotMonitored `
            -Prompt $cleanupPrompt `
            -WorkingDirectory $TestFolder `
            -LogPath $cleanupLog `
            -BailOutCode "EVAL-SUITE-021" `
            -Context "Phase 0 cleanup"


        if ($cleanupRun.ExitCode -ne 0) {
            Write-Warning "Cleanup exited with code $($cleanupRun.ExitCode)."
        }
    }
    catch {
        $cleanupError = $_.ToString()
        Write-Warning "Cleanup error: $cleanupError"
    }

    $cleanupDuration = [math]::Round(((Get-Date) - $cleanupStart).TotalSeconds, 1)
    $cleanupTelemetry = [PSCustomObject]@{
        phase                = "cleanup"
        status               = (Get-RunStatus -Run $cleanupRun -ErrorMessage $cleanupError)
        durationSeconds      = $cleanupDuration
        error                = $cleanupError
        exitCode             = if ($cleanupRun) { $cleanupRun.ExitCode } else { $null }
        bailOutCode          = if ($cleanupRun) { $cleanupRun.BailOutCode } else { $null }
        unsupportedOptionHits = if ($cleanupRun) { $cleanupRun.UnsupportedOptionHits } else { 0 }
        logPath              = $cleanupLog
        session              = if ($cleanupRun) { $cleanupRun.SessionTelemetry } else { $null }
    }

} # end -not SkipCleanup

# ---------------------------------------------------------------------------
# Phase 0b: Shared Infrastructure Provisioning
# ---------------------------------------------------------------------------
$infraTelemetry = $null
if ($SkipCleanup) {
    Write-Host "`n--- Phase 0b: Shared Infrastructure (SKIPPED via -SkipCleanup) ---"
    $infraTelemetry = [PSCustomObject]@{
        phase           = "infra-provisioning"
        status          = "skipped"
        durationSeconds = 0
        error           = $null
        exitCode        = $null
        bailOutCode     = $null
        unsupportedOptionHits = 0
        logPath         = $null
        session         = $null
    }
}
else {
    Write-Host "`n--- Phase 0b: Shared Infrastructure Provisioning ---"

    # Build optional steps depending on skip flags
    $warehouseStep = ""
    $lakehouseStep = ""
    $verifyItems = @()
    if (-not $SkipWarehouse) {
        $warehouseStep = @"

## Create Warehouse
``````powershell
`$body = @{ displayName = "$warehouseName"; type = "Warehouse" } | ConvertTo-Json
Invoke-RestMethod -Uri `$baseUrl -Method Post -Headers `$headers -Body `$body -ContentType "application/json"
``````
"@
        $verifyItems += $warehouseName
    }
    else {
        Write-Host "  (Warehouse creation skipped via -SkipWarehouse)"
    }
    if (-not $SkipLakehouse) {
        $lakehouseStep = @"

## Create Lakehouse
``````powershell
`$body = @{ displayName = "$lakehouseName"; type = "Lakehouse" } | ConvertTo-Json
Invoke-RestMethod -Uri `$baseUrl -Method Post -Headers `$headers -Body `$body -ContentType "application/json"
``````
"@
        $verifyItems += $lakehouseName
    }
    else {
        Write-Host "  (Lakehouse creation skipped via -SkipLakehouse)"
    }
    $verifyItems += @($eventhouseName, $kqlDbName)
    $verifyList = ($verifyItems -join ', ')

    $infraPrompt = @"
The eval workspace is '$workspaceName' (ID: $workspaceId).
Provision the shared infrastructure items using the EXACT PowerShell code below.
IMPORTANT: Use Invoke-RestMethod (NOT az rest) to avoid PowerShell JSON escaping issues.
Use -ContentType "application/json" as a parameter (NOT inside `$headers).
If a create call returns 409, the item already exists — skip it and continue.

## Setup — Get bearer token
``````powershell
`$token = (az account get-access-token --resource https://api.fabric.microsoft.com | ConvertFrom-Json).accessToken
`$headers = @{ Authorization = "Bearer `$token" }
`$baseUrl = "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/items"
``````
$warehouseStep
$lakehouseStep
## Create Eventhouse
``````powershell
`$body = @{ displayName = "$eventhouseName"; type = "Eventhouse" } | ConvertTo-Json
`$resp = Invoke-RestMethod -Uri `$baseUrl -Method Post -Headers `$headers -Body `$body -ContentType "application/json"
`$eventhouseId = `$resp.id
Write-Host "Eventhouse ID: `$eventhouseId"
``````

## Create KQL Database inside the Eventhouse
``````powershell
`$body = @{ displayName = "$kqlDbName"; type = "KQLDatabase"; creationPayload = @{ databaseType = "ReadWrite"; parentEventhouseItemId = `$eventhouseId } } | ConvertTo-Json -Depth 3
Invoke-RestMethod -Uri `$baseUrl -Method Post -Headers `$headers -Body `$body -ContentType "application/json"
``````

## Verify items exist
``````powershell
(Invoke-RestMethod -Uri `$baseUrl -Method Get -Headers `$headers).value | Select-Object displayName, type, id | Format-Table
``````
Confirm $verifyList all appear. Report the IDs.
"@
    $infraLog = Join-Path $TestFolder "phase0b-infra.log"
    $infraRun = $null
    $infraError = $null
    $infraStart = Get-Date
    try {
        Write-Host "========================================="
        Write-Host "  INVOCATION:"
        Write-Host $infraPrompt
        Write-Host "========================================="

        $infraRun = Invoke-CopilotMonitored `
            -Prompt $infraPrompt `
            -WorkingDirectory $TestFolder `
            -LogPath $infraLog `
            -BailOutCode "EVAL-SUITE-022" `
            -Context "Phase 0b infra provisioning"

        if ($infraRun.ExitCode -ne 0) {
            Write-Warning "Infra provisioning exited with code $($infraRun.ExitCode)."
        }
    }
    catch {
        $infraError = $_.ToString()
        Write-Warning "Infra provisioning error: $infraError"
    }

    $infraDuration = [math]::Round(((Get-Date) - $infraStart).TotalSeconds, 1)
    $infraTelemetry = [PSCustomObject]@{
        phase           = "infra-provisioning"
        status          = (Get-RunStatus -Run $infraRun -ErrorMessage $infraError)
        durationSeconds = $infraDuration
        error           = $infraError
        exitCode        = if ($infraRun) { $infraRun.ExitCode } else { $null }
        bailOutCode     = if ($infraRun) { $infraRun.BailOutCode } else { $null }
        unsupportedOptionHits = if ($infraRun) { $infraRun.UnsupportedOptionHits } else { 0 }
        logPath         = $infraLog
        session         = if ($infraRun) { $infraRun.SessionTelemetry } else { $null }
    }
} # end Phase 0b

# ---------------------------------------------------------------------------
# Result folder
# ---------------------------------------------------------------------------
$resultDest = Join-Path $evalSource "result"
if (-not (Test-Path $resultDest)) {
    New-Item -ItemType Directory -Path $resultDest -Force | Out-Null
}

$telemetryPath = Join-Path $resultDest "eval-run-telemetry.json"
$runnerTelemetry = [ordered]@{
    schemaVersion = 1
    generatedAt   = (Get-Date).ToString("o")
    runner        = [ordered]@{
        script            = "tests/run-full-tests.ps1"
        repoRoot          = $repoRoot
        evalSource        = $evalSource
        testFolder        = $TestFolder
        resultDestination = $resultDest
        skipCleanup       = [bool]$SkipCleanup
        skipWarehouse     = [bool]$SkipWarehouse
        skipLakehouse     = [bool]$SkipLakehouse
        planFilter        = $PlanFilter
        throttleLimit     = $ThrottleLimit
    }
    cleanup       = $cleanupTelemetry
    infraProvisioning = $infraTelemetry
    plans         = @()
    postProcessing = @()
    suite         = $null
}

# ---------------------------------------------------------------------------
# Run eval plans in parallel chains
#
# A "chain" is an ordered group of plans that MUST run sequentially because
# the consumption plan depends on the authoring plan having created items
# (e.g. eval-spark-authoring writes a lakehouse table that eval-spark-consumption
# reads). Standalone plans form a chain of length 1.
#
# Chains are dispatched to up to $ThrottleLimit ThreadJobs concurrently. The
# per-plan working directory is unique ($TestFolder/<planName>), which lets
# Find-CopilotSessionByCwd disambiguate parallel Copilot sessions.
#
# Suite-level bailout (EVAL-SUITE-010: SKIP detected in a plan result) is
# signalled via a shared ManualResetEventSlim. Each chain checks the flag
# before starting its next plan; in-flight plans complete normally.
# ---------------------------------------------------------------------------

# Plans that require a Warehouse item (uses {{WAREHOUSE}} placeholder)
$warehousePlans = @(
    'eval-sqldw-authoring',
    'eval-sqldw-consumption',    
    'eval-sqldw-authoring-plus-consumption',
    'eval-semantic-model-authoring-plus-consumption',
    'eval-semantic-model-authoring'
)

# Plans that require a Lakehouse item (uses {{LAKEHOUSE}} placeholder)
$lakehousePlans = @(    
    'eval-powerbi-consumption',
    'eval-semantic-model-consumption',
    'eval-spark-authoring',
    'eval-spark-consumption',
    'eval-spark-authoring-plus-consumption',
    'eval-sqldw-consumption',
    'eval-semantic-model-authoring'
)

# Group plans by their declared plugin (YAML front-matter `plugin: <name>`,
# default "fabric-skills"). Plugin groups run SEQUENTIALLY in the outer loop
# below: each group reinstalls its plugin once, then dispatches PR #256's
# parallel chain orchestration WITHIN the group. Day-1 (every plan defaults
# to "fabric-skills") collapses to a single group whose behaviour is
# identical to the pre-grouping single-install path.
$planByPlugin = @{}
foreach ($plan in $evalPlans) {
    $planPluginName = Get-EvalPlanPlugin -PlanPath $plan.FullName
    if (-not $planByPlugin.ContainsKey($planPluginName)) {
        $planByPlugin[$planPluginName] = @()
    }
    $planByPlugin[$planPluginName] += $plan
}
$pluginGroupOrder = @($planByPlugin.Keys | Sort-Object)
Write-Host "`n========================================="
Write-Host "  Plugin groups: $($pluginGroupOrder.Count)"
foreach ($pn in $pluginGroupOrder) {
    Write-Host "  [$pn] $($planByPlugin[$pn].Count) plan(s)"
}
Write-Host "========================================="

$absoluteOverviewPath = Join-Path $TestFolder "plan" "00-overview.md"

# Shared cross-thread state -- accumulates across plugin groups.
# - $bailoutEvent: signals EVAL-SUITE-010 (SKIP detected) suite-wide. The outer
#   plugin loop checks this BEFORE starting the next plugin group, emitting
#   synthetic skipped_bailout records for every un-run plan in remaining groups
#   so the dashboard still sees the expected plan count.
# - $telemetryBag/$summaryBag: thread-safe accumulators populated by jobs and
#   by the outer loop's bailout-skip path.
# - $outputLock: held during console writes to keep multi-line banners
#   from interleaving across chains.
$bailoutEvent = [System.Threading.ManualResetEventSlim]::new($false)
$telemetryBag = [System.Collections.Concurrent.ConcurrentBag[psobject]]::new()
$summaryBag   = [System.Collections.Concurrent.ConcurrentBag[psobject]]::new()
$bailoutInfoBag = [System.Collections.Concurrent.ConcurrentBag[psobject]]::new()
$outputLock   = [object]::new()

# Global suite soft budget: ONE wall-clock deadline for the ENTIRE eval run
# (across all plugin groups), computed once here -- NOT a fresh budget per group.
# Plugin groups run sequentially, so a per-group budget would let group 1 burn
# the full budget and group 2 then start a fresh one (e.g. 2 x 270 = 540 min >
# the GitHub timeout-minutes: 360), which could still kill the job BEFORE
# telemetry + merged summary are written -- the red, data-less run the
# 2026-06-11 nightly hit. Per-plan watchdogs (Invoke-CopilotMonitored) already
# bound individual plans; this is the suite-level backstop. Default 270 min
# leaves ~90 min under the 360 min workflow timeout for the plugin reset + the
# two post-processing Invoke-CopilotMonitored calls (merged-summary + regression),
# each itself watchdog-capped. Env-tunable via FULL_EVAL_SUITE_SOFT_BUDGET_MINUTES.
$suiteSoftBudgetMinutes = 270
if (($env:FULL_EVAL_SUITE_SOFT_BUDGET_MINUTES -as [int]) -gt 0) {
    $suiteSoftBudgetMinutes = [int]$env:FULL_EVAL_SUITE_SOFT_BUDGET_MINUTES
}
$suiteDeadline = (Get-Date).AddMinutes($suiteSoftBudgetMinutes)
$suiteBudgetExceeded = $false

# Outer loop: per-plugin group. Sequential to keep plugin install state safe
# (Copilot CLI's installed-plugins config is global per user account on the
# runner -- 4 parallel `copilot plugin install` calls would race on the same
# directory). Inside each group we use PR #256's parallel chain orchestration.
foreach ($pluginName in $pluginGroupOrder) {
    # Suite-wide bailout from a previous plugin group: skip every remaining
    # plan and emit synthetic telemetry so the dashboard still counts them.
    # We do NOT switch plugin here -- there is nothing to run.
    if ($bailoutEvent.IsSet) {
        Write-Host "`n[$pluginName] SKIPPING entire plugin group -- suite bailout (EVAL-SUITE-010)" -ForegroundColor Yellow
        foreach ($plan in $planByPlugin[$pluginName]) {
            $skippedRelPath = $plan.FullName.Replace($TestFolder, "").TrimStart("\", "/")
            $telemetryBag.Add([PSCustomObject]@{
                plan = $plan.BaseName; planPath = $skippedRelPath; status = 'skipped_bailout'
                durationSeconds = 0; error = 'Suite bailed out (EVAL-SUITE-010) before this plugin group started.'
                exitCode = $null; bailOutCode = 'EVAL-SUITE-010'; unsupportedOptionHits = 0
                logPath = $null; session = $null; result = $null; chainKey = $null
                plugin = $pluginName
            })
            $summaryBag.Add([PSCustomObject]@{
                Plan = $plan.BaseName; Duration = 0; Error = 'skipped: suite bailout'
            })
        }
        continue
    }

    # Suite soft budget exhausted while an earlier plugin group was running:
    # skip every remaining plan with a synthetic ERROR row (not skipped_bailout)
    # so the gate counts them as failures rather than silently dropping them --
    # a plan that never ran because we hit the deadline is a failure-to-run, not
    # an opt-out skip. Mirrors the EVAL-SUITE-010 bailout-skip branch above.
    if ($suiteBudgetExceeded) {
        Write-Host "`n[$pluginName] SKIPPING entire plugin group -- suite soft budget exhausted (EVAL-SUITE-SOFT-BUDGET)" -ForegroundColor Yellow
        foreach ($plan in $planByPlugin[$pluginName]) {
            $skippedRelPath = $plan.FullName.Replace($TestFolder, "").TrimStart("\", "/")
            $telemetryBag.Add([PSCustomObject]@{
                plan = $plan.BaseName; planPath = $skippedRelPath; status = 'error'
                durationSeconds = 0; error = "Suite soft budget ($suiteSoftBudgetMinutes min) exhausted before this plugin group started."
                exitCode = $null; bailOutCode = 'EVAL-SUITE-SOFT-BUDGET'; unsupportedOptionHits = 0
                logPath = $null; session = $null; result = $null; chainKey = $null
                plugin = $pluginName
            })
            $summaryBag.Add([PSCustomObject]@{
                Plan = $plan.BaseName; Duration = 0; Error = 'error: suite soft budget exhausted'
            })
        }
        continue
    }

    $pluginPlans = $planByPlugin[$pluginName]
    Write-Host "`n========================================="
    Write-Host "  Plugin group: $pluginName ($($pluginPlans.Count) plan(s))"
    Write-Host "========================================="
    Sync-PluginInstallation -Plugin $pluginName

# Group plans into execution chains. Authoring + consumption + combined
# (`*-authoring-plus-consumption`) plans for the same workload share a chain
# key and execute sequentially (authoring -> consumption -> combined); all
# other plans are standalone chains of length 1.
#
# The combined plan MUST share its workload's chain because it touches the
# same shared resources (warehouse schemas, activator target item names,
# lakehouse paths) as the pair plans and would otherwise race them in
# parallel execution.
$planByChain = @{}
foreach ($plan in $pluginPlans) {
    if ($plan.BaseName -match '^eval-(?<key>.+)-authoring-plus-consumption$') {
        $chainKey = $matches['key']
    } elseif ($plan.BaseName -match '^eval-(?<key>.+)-(authoring|consumption)$') {
        $chainKey = $matches['key']
    } else {
        $chainKey = $plan.BaseName
    }
    if (-not $planByChain.ContainsKey($chainKey)) {
        $planByChain[$chainKey] = @()
    }
    $planByChain[$chainKey] += $plan
}
foreach ($chainKey in @($planByChain.Keys)) {
    $planByChain[$chainKey] = @(
        $planByChain[$chainKey] | Sort-Object @{ Expression = {
            switch -Regex ($_.BaseName) {
                'authoring-plus-consumption$' { 2; break }
                'authoring$'                  { 0; break }
                'consumption$'                { 1; break }
                default                        { 3 }
            }
        }}
    )
}
$chainKeys = @($planByChain.Keys | Sort-Object)

Write-Host "`n========================================="
Write-Host "  Parallel execution: $($chainKeys.Count) chain(s), throttle=$ThrottleLimit"
Write-Host "========================================="
foreach ($k in $chainKeys) {
    $chainNames = ($planByChain[$k] | ForEach-Object { $_.BaseName }) -join ' -> '
    Write-Host "  [$k] $chainNames"
}
Write-Host ""

$chainJobs = @()
foreach ($chainKey in $chainKeys) {
    while (@($chainJobs | Where-Object { $_.State -eq 'Running' }).Count -ge $ThrottleLimit) {
        Start-Sleep -Milliseconds 500
    }

    $planManifest = @($planByChain[$chainKey] | ForEach-Object {
        [PSCustomObject]@{
            baseName = $_.BaseName
            fullPath = $_.FullName
            relPath  = $_.FullName.Replace($TestFolder, "").TrimStart("\", "/")
        }
    })

    $job = Start-ThreadJob -Name "chain-$chainKey" -ScriptBlock {
        param(
            $chainKey,
            $planManifest,
            $testFolder,
            $resultDest,
            $workspaceName,
            $workspaceId,
            $warehousePlans,
            $lakehousePlans,
            $skipWarehouse,
            $skipLakehouse,
            $telemetryHelperPath,
            $copilotInvokePath,
            $absoluteOverviewPath,
            $planPluginName
        )

        . $telemetryHelperPath
        . $copilotInvokePath

        $sharedBailout = $using:bailoutEvent
        $sharedTelemetry = $using:telemetryBag
        $sharedSummary = $using:summaryBag
        $sharedBailoutInfo = $using:bailoutInfoBag
        $sharedOutputLock = $using:outputLock

        function Write-ChainBanner {
            param([string[]]$Lines, [System.ConsoleColor]$Color = [System.ConsoleColor]::Cyan)
            [System.Threading.Monitor]::Enter($sharedOutputLock)
            try {
                foreach ($line in $Lines) {
                    Write-Host $line -ForegroundColor $Color
                }
            } finally {
                [System.Threading.Monitor]::Exit($sharedOutputLock)
            }
        }

        $chainTelemetry = @()
        $chainSummary = @()

        try {
        foreach ($pf in $planManifest) {
            $planName = $pf.baseName
            $planRelPath = $pf.relPath
            $planFullPath = $pf.fullPath

            # Honor suite-wide bailout: emit a synthetic skipped-bailout record
            # for THIS plan and `continue` to the next plan in the chain so that
            # every remaining plan also gets its own telemetry record (the
            # branch fires again on the next iteration). Do NOT change to
            # `break` -- that would leave the remaining plans missing from
            # telemetry entirely, which would understate the suite's plan count
            # in dashboards and run summaries.
            if ($sharedBailout.IsSet) {
                Write-ChainBanner @("  [$chainKey] SKIPPING $planName -- suite bailout (EVAL-SUITE-010)") ([System.ConsoleColor]::Yellow)
                $chainTelemetry += [PSCustomObject]@{
                    plan = $planName; planPath = $planRelPath; status = 'skipped_bailout'
                    durationSeconds = 0; error = 'Suite bailed out (EVAL-SUITE-010) before this plan started.'
                    exitCode = $null; bailOutCode = 'EVAL-SUITE-010'; unsupportedOptionHits = 0
                    logPath = $null; session = $null; result = $null; chainKey = $chainKey
                    plugin = $planPluginName
                }
                $chainSummary += [PSCustomObject]@{ Plan = $planName; Duration = 0; Error = 'skipped: suite bailout' }
                continue
            }

            if ($skipWarehouse -and ($warehousePlans -contains $planName)) {
                Write-ChainBanner @("  [$chainKey] SKIPPING $planName (warehouse unavailable)") ([System.ConsoleColor]::Yellow)
                $chainTelemetry += [PSCustomObject]@{
                    plan = $planName; planPath = $planRelPath; status = 'skipped_warehouse'
                    durationSeconds = 0; error = 'Warehouse creation unavailable in this environment'
                    exitCode = $null; bailOutCode = $null; unsupportedOptionHits = 0
                    logPath = $null; session = $null; result = $null; chainKey = $chainKey
                    plugin = $planPluginName
                }
                $chainSummary += [PSCustomObject]@{ Plan = $planName; Duration = 0; Error = 'skipped: warehouse unavailable' }
                continue
            }

            if ($skipLakehouse -and ($lakehousePlans -contains $planName)) {
                Write-ChainBanner @("  [$chainKey] SKIPPING $planName (lakehouse unavailable)") ([System.ConsoleColor]::Yellow)
                $chainTelemetry += [PSCustomObject]@{
                    plan = $planName; planPath = $planRelPath; status = 'skipped_lakehouse'
                    durationSeconds = 0; error = 'Lakehouse creation unavailable in this environment'
                    exitCode = $null; bailOutCode = $null; unsupportedOptionHits = 0
                    logPath = $null; session = $null; result = $null; chainKey = $chainKey
                    plugin = $planPluginName
                }
                $chainSummary += [PSCustomObject]@{ Plan = $planName; Duration = 0; Error = 'skipped: lakehouse unavailable' }
                continue
            }

            # Per-plan working directory: required for cwd-based Copilot session
            # discovery when multiple Copilot processes run in parallel.
            # Read-only fixture directories (evalsets/, plan/) are exposed via
            # Windows junctions so that plan files referencing
            # 'evalsets/data-generation/<file>' or 'plan/01-data-generation.md'
            # by relative path resolve to the same content the serial harness
            # uses. The result/ subdirectory is a per-plan REAL dir to keep
            # parallel writes isolated.
            $planCwd = Join-Path $testFolder $planName
            if (-not (Test-Path $planCwd)) {
                New-Item -ItemType Directory -Path $planCwd -Force | Out-Null
            }
            foreach ($linkName in @('evalsets', 'plan')) {
                $linkPath = Join-Path $planCwd $linkName
                $targetPath = Join-Path $testFolder $linkName
                if ((Test-Path $targetPath) -and (-not (Test-Path $linkPath))) {
                    try {
                        New-Item -ItemType Junction -Path $linkPath -Target $targetPath -ErrorAction Stop | Out-Null
                    } catch {
                        # Junction creation can fail on filesystems that don't
                        # support reparse points (e.g. some network drives).
                        # Fall back to copying so the agent still finds files.
                        Copy-Item -Path $targetPath -Destination $linkPath -Recurse -Force
                    }
                }
            }
            $planResultDir = Join-Path $planCwd "result"
            if (-not (Test-Path $planResultDir)) {
                New-Item -ItemType Directory -Path $planResultDir -Force | Out-Null
            }

            $skillPrompt = @"
The eval workspace is '$workspaceName' (ID: $workspaceId). Use this workspace for all operations.
Follow the canonical rules in '$absoluteOverviewPath' and execute eval plan '$planFullPath'.
Enforce Bailout Conditions exactly as defined in 00-overview.md.
Write the result file to '$($planCwd -replace '\\','/')/result/$planName-results.md'.
"@

            Write-ChainBanner @(
                "=========================================",
                "  [$chainKey] Running: $planName",
                "  Plan: $planFullPath",
                "  CWD:  $planCwd",
                "========================================="
            ) ([System.ConsoleColor]::Cyan)

            $testStart = Get-Date
            $errorMsg = $null
            $planRunLog = Join-Path $testFolder "$planName-run.log"
            $cliUnsupportedOptionCount = 0
            $planRun = $null

            try {
                $planRun = Invoke-CopilotMonitored `
                    -Prompt $skillPrompt `
                    -WorkingDirectory $planCwd `
                    -LogPath $planRunLog `
                    -BailOutCode "EVAL-SUITE-020" `
                    -Context $planName `
                    -UnknownOptionThreshold ([int]::MaxValue)

                if ($planRun.ExitCode -ne 0) {
                    if ($planRun.BailedOut) {
                        Write-ChainBanner @("  [$chainKey] $planName bailed out ($($planRun.BailOutCode)) -- continuing to next plan in chain") ([System.ConsoleColor]::Yellow)
                    } elseif ($planRun.TimedOut) {
                        # Runner watchdog terminated a stalled / over-ceiling plan.
                        # Surface the timeout reason so telemetry records WHY
                        # (EVAL-TIMEOUT-001 stall / -002 hard ceiling) rather than
                        # a bare exit code.
                        $errorMsg = $planRun.ErrorMessage
                        Write-ChainBanner @("  [$chainKey] $planName TIMED OUT ($($planRun.BailOutCode)) -- $errorMsg -- continuing to next plan in chain") ([System.ConsoleColor]::Red)
                    } else {
                        $errorMsg = "copilot exited with code $($planRun.ExitCode)"
                    }
                }
            } catch {
                $errorMsg = $_.ToString()
            }

            $testDuration = ((Get-Date) - $testStart).TotalSeconds
            Write-ChainBanner @("  [$chainKey] Finished $planName -- $([math]::Round($testDuration, 1)) s") ([System.ConsoleColor]::Green)
            if ($errorMsg) {
                Write-ChainBanner @("  [$chainKey] $planName error: $errorMsg") ([System.ConsoleColor]::Red)
            }

            if (Test-Path $planRunLog) {
                $cliUnsupportedOptionCount = (Select-String -Path $planRunLog -SimpleMatch "unknown option '--no-warnings'" 2>$null).Count
            }

            # Collect result files. The agent may write to:
            #   $planCwd/result/{plan-name}-results.md    (canonical location)
            #   $planCwd/{plan-name}-results.md           (root fallback)
            #   $testFolder/result/                       (legacy location, rare)
            #   $testFolder/                              (legacy root, rare)
            $candidateSources = @(
                (Join-Path $planCwd "result"),
                $planCwd,
                (Join-Path $testFolder "result"),
                $testFolder
            )
            $mdFiles = @()
            foreach ($src in $candidateSources) {
                if (Test-Path $src) {
                    $mdFiles += Get-ChildItem -Path $src -Filter "$planName-results.md" -File -ErrorAction SilentlyContinue
                }
            }
            $mdFiles = $mdFiles | Sort-Object LastWriteTime -Descending
            $planResultTelemetry = $null
            if ($mdFiles.Count -gt 0) {
                $primary = $mdFiles[0]
                # $resultDest is shared by all chains, but each chain writes a
                # different plan's result file, so there is no concurrent
                # write contention on a single file.
                Copy-Item -Path $primary.FullName -Destination $resultDest -Force
                # Also stage in $testFolder/result so the merged-summary phase
                # (which runs serially with cwd=$testFolder and reads from
                # 'result/' relative to that cwd) sees every plan's result file.
                $stagedSummaryDir = Join-Path $testFolder "result"
                if (-not (Test-Path $stagedSummaryDir)) {
                    New-Item -ItemType Directory -Path $stagedSummaryDir -Force | Out-Null
                }
                Copy-Item -Path $primary.FullName -Destination $stagedSummaryDir -Force

                $copiedPlanResultPath = Join-Path $resultDest $primary.Name
                if (Test-Path $copiedPlanResultPath) {
                    $planResultTelemetry = Get-EvalResultTelemetry -ResultPath $copiedPlanResultPath
                }

                $planText = Get-Content -Path $primary.FullName -Raw
                if ($planText -match '(?im)^\|[^\r\n]*\|\s*SKIP(?:PED)?\s*\|') {
                    if (-not $sharedBailout.IsSet) {
                        $sharedBailoutInfo.Add([PSCustomObject]@{
                            sourcePlan = $planName
                            sourceFile = $primary.Name
                            reason     = "Detected SKIP/SKIPPED in $($primary.Name)."
                            code       = "EVAL-SUITE-010"
                        })
                        $sharedBailout.Set()
                    }
                    Write-ChainBanner @("  [$chainKey] EVAL-SUITE-010: SKIP detected in $($primary.Name) -- signalling suite bailout") ([System.ConsoleColor]::Red)
                }
            }

            $planStatus = (Get-RunStatus -Run $planRun -ErrorMessage $errorMsg)
            if ($planStatus -eq 'completed' -and $mdFiles.Count -eq 0) {
                # Plan exited successfully but never wrote <plan>-results.md. The merged
                # summary cannot see it, so surface this as an explicit failure mode
                # rather than letting the run look successful with missing data.
                $planStatus = 'completed_missing_result'
                if (-not $errorMsg) {
                    $errorMsg = "Plan exited successfully but produced no $planName-results.md file."
                }
                Write-ChainBanner @("  [$chainKey] $planName completed but no result file found -- flagged as completed_missing_result") ([System.ConsoleColor]::Red)
            }

            $chainTelemetry += [PSCustomObject]@{
                plan = $planName
                planPath = $planRelPath
                status = $planStatus
                durationSeconds = [math]::Round($testDuration, 1)
                error = $errorMsg
                exitCode = if ($planRun) { $planRun.ExitCode } else { $null }
                bailOutCode = if ($planRun) { $planRun.BailOutCode } else { $null }
                unsupportedOptionHits = if ($planRun) { $planRun.UnsupportedOptionHits } else { $cliUnsupportedOptionCount }
                logPath = $planRunLog
                session = if ($planRun) { $planRun.SessionTelemetry } else { $null }
                result = $planResultTelemetry
                chainKey = $chainKey
                plugin = $planPluginName
            }
            $chainSummary += [PSCustomObject]@{
                Plan = $planName
                Duration = [math]::Round($testDuration, 1)
                Error = $errorMsg
            }
        }
        } catch {
            # A terminating error inside the chain loop (e.g. session-telemetry
            # helper missing, junction create permission denied) would otherwise
            # lose the chain entirely. Capture it for the parent and emit a
            # chain_failed record for every plan that hasn't reported yet.
            $reportedPlans = @($chainTelemetry | ForEach-Object { $_.plan })
            foreach ($pf in $planManifest) {
                if ($reportedPlans -notcontains $pf.baseName) {
                    $chainTelemetry += [PSCustomObject]@{
                        plan = $pf.baseName; planPath = $pf.relPath; status = 'chain_failed'
                        durationSeconds = 0; error = "Chain '$chainKey' aborted before this plan: $($_.Exception.Message)"
                        exitCode = $null; bailOutCode = $null; unsupportedOptionHits = 0
                        logPath = $null; session = $null; result = $null; chainKey = $chainKey
                        plugin = $planPluginName
                    }
                    $chainSummary += [PSCustomObject]@{
                        Plan = $pf.baseName; Duration = 0; Error = "chain aborted: $($_.Exception.Message)"
                    }
                }
            }
            Write-ChainBanner @(
                "  [$chainKey] CHAIN FAILED before completion: $($_.Exception.Message)",
                "  [$chainKey] Remaining plans flagged as chain_failed."
            ) ([System.ConsoleColor]::Red)
        } finally {
            # Flush in `finally` so a parent Stop-Job at the suite soft budget
            # still publishes every plan this chain completed. Stop-Job raises
            # PipelineStoppedException inside the runspace, which runs ONLY
            # `finally` -- not `catch`, and it skips any statement after the
            # try/catch. With the flush here, stopping a straggler chain loses
            # only its in-flight plan; without it, ALL of the chain's
            # accumulated telemetry would be dropped -- recreating the red,
            # data-less run the soft budget exists to prevent.
            foreach ($t in $chainTelemetry) { $sharedTelemetry.Add($t) }
            foreach ($s in $chainSummary)   { $sharedSummary.Add($s) }
        }
    } -ArgumentList @(
        $chainKey,
        $planManifest,
        $TestFolder,
        $resultDest,
        $workspaceName,
        $workspaceId,
        $warehousePlans,
        $lakehousePlans,
        [bool]$SkipWarehouse,
        [bool]$SkipLakehouse,
        $telemetryHelperPath,
        $copilotInvokePath,
        $absoluteOverviewPath,
        $pluginName
    )

    $chainJobs += $job
}

# Wait for this group's chains, bounded by the GLOBAL suite deadline computed
# once before the plugin loop (not a fresh per-group budget). Remaining time
# shrinks as earlier groups consume it, so the whole run stays under the
# deadline and the GitHub hard timeout (timeout-minutes: 360) cannot fire before
# telemetry + merged summary are written. Per-plan watchdogs in
# Invoke-CopilotMonitored already bound individual plans; this is the
# suite-level backstop (a chain with many plans, or a hang in result collection
# / plugin switch).
$remainingSec = [int][Math]::Max(0, ($suiteDeadline - (Get-Date)).TotalSeconds)
$null = $chainJobs | Wait-Job -Timeout $remainingSec
$stragglerJobs = @($chainJobs | Where-Object { $_.State -eq 'Running' })
if ($stragglerJobs.Count -gt 0) {
    # Global deadline reached. Set the flag so any remaining plugin groups are
    # skipped with synthetic error rows at the top of the loop, then stop this
    # group's stragglers: their finally blocks flush completed-plan telemetry,
    # and the Stopped-chain handler below synthesizes error rows for their un-run
    # plans so nothing silently passes the gate.
    $suiteBudgetExceeded = $true
    Write-Warning ("Suite soft budget of {0} min reached with {1} chain(s) still running: {2}. Stopping them so telemetry + merged summary are written before the hard workflow timeout; remaining plugin groups (if any) are skipped with error rows. Each stopped chain flushes its completed-plan telemetry in a finally block, and its un-run plans are recorded below as errors so they cannot silently pass the gate." -f $suiteSoftBudgetMinutes, $stragglerJobs.Count, ($stragglerJobs.Name -join ', '))
    foreach ($sj in $stragglerJobs) {
        Stop-Job -Job $sj -ErrorAction SilentlyContinue
    }
    # Wait for the stopped chains to reach 'Stopped' -- their finally blocks run
    # and flush completed-plan telemetry to the shared bags -- before the drain
    # below. A fixed sleep could race a slow finally; Wait-Job settles it.
    $stragglerJobs | Wait-Job -Timeout 30 | Out-Null
}
$failedChainJobs = @()
foreach ($j in $chainJobs) {
    Receive-Job -Job $j -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_) { Write-Host $_ }
    }
    if ($j.State -eq 'Failed' -or $j.State -eq 'Stopped') {
        $failedChainJobs += $j
        $chainKeyName = ($j.Name -replace '^chain-', '')
        $errReasons = @()
        foreach ($cj in $j.ChildJobs) {
            if ($cj.JobStateInfo.Reason) {
                $errReasons += $cj.JobStateInfo.Reason.ToString()
            }
            foreach ($er in @($cj.Error.ReadAll())) {
                $errReasons += $er.ToString()
            }
        }
        $reasonText = ($errReasons -join ' | ')
        Write-Host "[chain] Chain job '$($j.Name)' state=$($j.State): $reasonText" -ForegroundColor Red
        if ($j.State -eq 'Stopped') {
            # Suite soft-budget Stop-Job: the chain's `finally` flushed its
            # COMPLETED plans, but its in-flight + not-yet-started plans never
            # reported (the catch{} that emits chain_failed does NOT run on
            # Stop-Job -- only finally runs). Synthesize an `error` record for
            # every expected plan of this chain that is absent from telemetry so
            # a stopped chain cannot silently drop plans and let the gate pass on
            # partial data.
            $reportedPlanNames = @($telemetryBag.ToArray() | ForEach-Object { $_.plan })
            foreach ($pf in @($planByChain[$chainKeyName])) {
                if ($reportedPlanNames -notcontains $pf.BaseName) {
                    $telemetryBag.Add([PSCustomObject]@{
                        plan = $pf.BaseName
                        planPath = $pf.FullName.Replace($TestFolder, "").TrimStart("\", "/")
                        status = 'error'
                        durationSeconds = 0
                        error = "Chain '$chainKeyName' stopped at the suite soft budget ($suiteSoftBudgetMinutes min) before this plan completed."
                        exitCode = $null; bailOutCode = 'EVAL-SUITE-SOFT-BUDGET'; unsupportedOptionHits = 0
                        logPath = $null; session = $null; result = $null
                        chainKey = $chainKeyName; plugin = $pluginName
                    })
                }
            }
        } else {
            # State=Failed: high-level chain-level signal for the post-processing
            # dashboard. Plan-level chain_failed records may also have been
            # emitted inside the catch{} in the chain body.
            $telemetryBag.Add([PSCustomObject]@{
                plan = "(chain) $($j.Name)"
                planPath = $null
                status = 'chain_failed'
                durationSeconds = 0
                error = "ThreadJob failed: $reasonText"
                exitCode = $null; bailOutCode = $null; unsupportedOptionHits = 0
                logPath = $null; session = $null; result = $null
                chainKey = $chainKeyName
                plugin = $pluginName
            })
        }
    }
}
$chainJobs | Remove-Job -Force -ErrorAction SilentlyContinue
if ($failedChainJobs.Count -gt 0) {
    Write-Warning "$($failedChainJobs.Count) chain job(s) reported State=Failed or State=Stopped; see telemetry for details."
}

}  # end foreach $pluginName in $pluginGroupOrder

# Reset to fabric-skills for post-processing (merged summary + regression
# analysis below invoke Copilot again and must run under a stable, known
# plugin -- otherwise the last plugin group's plugin would still be active.
# No-op when the suite ran only a single fabric-skills group.
if ($script:currentInstalledPlugin -ne "fabric-skills") {
    Write-Host "`n--- Resetting plugin to fabric-skills for post-processing ---"
    # The eval itself is already complete here: every plugin group ran above
    # and per-plan telemetry is captured. This reset only re-establishes a
    # known plugin for the merged-summary + regression post-processing that
    # invokes Copilot again. A failure switching plugins must NOT discard a
    # finished run (the 2026-06-13 nightly lost ~2.5h of completed work this
    # way). Warn and continue; post-processing degrades to telemetry-only if
    # the merged summary cannot run.
    try {
        Sync-PluginInstallation -Plugin "fabric-skills"
    } catch {
        Write-Warning "Failed to reset plugin to fabric-skills for post-processing: $_. Continuing; merged-summary / regression analysis may be skipped or degraded."
    }
}

# Drain shared bags into final structures, sorted alphabetically by plan name.
$summary = @($summaryBag.ToArray() | Sort-Object Plan)
foreach ($rec in @($telemetryBag.ToArray() | Sort-Object plan)) {
    $runnerTelemetry.plans += $rec
}

$suiteBailOut = $bailoutEvent.IsSet
$suiteBailOutCode = $null
$suiteBailOutReason = $null
if ($suiteBailOut) {
    $bailInfo = @($bailoutInfoBag.ToArray() | Sort-Object sourcePlan) | Select-Object -First 1
    if ($bailInfo) {
        $suiteBailOutCode = $bailInfo.code
        $suiteBailOutReason = $bailInfo.reason
        Write-Error "$($suiteBailOutCode): $($suiteBailOutReason) Suite aborted to avoid invalid downstream dependency assumptions."
    } else {
        $suiteBailOutCode = "EVAL-SUITE-010"
        $suiteBailOutReason = "SKIP detected in a plan result."
        Write-Error "$($suiteBailOutCode): $($suiteBailOutReason)"
    }
}

# ---------------------------------------------------------------------------
# Print execution summary
# ---------------------------------------------------------------------------
Write-Host "`n========================================="
Write-Host "  Eval Execution Summary"
Write-Host "========================================="
$summary | Format-Table -AutoSize
Write-Host "Total plans executed: $($summary.Count)"
Write-Host "Results copied to: $resultDest"

# ---------------------------------------------------------------------------
# Generate merged eval-results.md summary
# ---------------------------------------------------------------------------
if (-not $suiteBailOut) {
    Write-Host "`n--- Generating merged summary ---"

    # Build the list of individual result files that were produced
    $resultFiles = Get-ChildItem -Path $resultDest -Filter "eval-*-results.md" -File `
        | Where-Object { $_.Name -ne "eval-results.md" }

    if ($resultFiles.Count -gt 0) {
        $summaryPrompt = @"
The eval workspace is '$workspaceName' (ID: $workspaceId).
Follow plan/00-overview.md and generate the merged summary in full-eval-tests/result/eval-results.md.
"@
        $summaryLog = Join-Path $TestFolder "merged-summary.log"
        $summaryRun = $null
        $summaryError = $null
        $summaryStart = Get-Date

        try {
            $summaryRun = Invoke-CopilotMonitored `
                -Prompt $summaryPrompt `
                -WorkingDirectory $TestFolder `
                -LogPath $summaryLog `
                -BailOutCode "EVAL-SUITE-030" `
                -Context "Merged summary generation" `
                -UnknownOptionThreshold ([int]::MaxValue)

            if ($summaryRun.ExitCode -ne 0 -and -not $summaryRun.BailedOut) {
                $summaryError = "copilot exited with code $($summaryRun.ExitCode)"
            }
        }
        catch {
            $summaryError = $_.ToString()
            Write-Warning "Summary generation error: $summaryError"
        }

        $summaryDuration = [math]::Round(((Get-Date) - $summaryStart).TotalSeconds, 1)
        $summaryResultPath = $null

        # Copy the generated summary back (copilot writes into $TestFolder's copy)
        $summaryFile = Join-Path $TestFolder "full-eval-tests" "result" "eval-results.md"
        if (Test-Path $summaryFile) {
            Copy-Item -Path $summaryFile -Destination $resultDest -Force
            $summaryResultPath = Join-Path $resultDest "eval-results.md"
            Write-Host "Merged summary: $summaryResultPath"
        }
        # Also check if copilot wrote it directly in the TestFolder root
        $summaryFileAlt = Get-ChildItem -Path $TestFolder -Filter "eval-results.md" -File 2>$null | Select-Object -First 1
        if ($summaryFileAlt -and $summaryFileAlt.FullName -ne $summaryFile) {
            Copy-Item -Path $summaryFileAlt.FullName -Destination $resultDest -Force
            $summaryResultPath = Join-Path $resultDest "eval-results.md"
            Write-Host "Merged summary (alt): $summaryResultPath"
        }

        $runnerTelemetry.postProcessing += [PSCustomObject]@{
            phase                = "merged-summary"
            status               = (Get-RunStatus -Run $summaryRun -ErrorMessage $summaryError)
            durationSeconds      = $summaryDuration
            error                = $summaryError
            exitCode             = if ($summaryRun) { $summaryRun.ExitCode } else { $null }
            bailOutCode          = if ($summaryRun) { $summaryRun.BailOutCode } else { $null }
            unsupportedOptionHits = if ($summaryRun) { $summaryRun.UnsupportedOptionHits } else { 0 }
            logPath              = $summaryLog
            session              = if ($summaryRun) { $summaryRun.SessionTelemetry } else { $null }
            resultPath           = $summaryResultPath
        }
    }
    else {
        Write-Warning "No individual result files found to summarize."
        $runnerTelemetry.postProcessing += [PSCustomObject]@{
            phase                = "merged-summary"
            status               = "skipped"
            durationSeconds      = 0
            error                = "No individual result files found to summarize."
            exitCode             = $null
            bailOutCode          = $null
            unsupportedOptionHits = 0
            logPath              = $null
            session              = $null
            resultPath           = $null
        }
    }

    # ---------------------------------------------------------------------------
    # Regression analysis
    # ---------------------------------------------------------------------------
    Write-Host "`n--- Regression Analysis ---"
    $regressionsPrompt = @"
The eval workspace is '$workspaceName' (ID: $workspaceId).
Follow plan/00-overview.md and generate full-eval-tests/result/regression_analysis.md.
"@
    $regressionLog = Join-Path $TestFolder "regression-analysis.log"
    $regressionRun = $null
    $regressionError = $null
    $regressionStart = Get-Date

    try {
        $regressionRun = Invoke-CopilotMonitored `
            -Prompt $regressionsPrompt `
            -WorkingDirectory $TestFolder `
            -LogPath $regressionLog `
            -BailOutCode "EVAL-SUITE-031" `
            -Context "Regression analysis generation" `
            -UnknownOptionThreshold ([int]::MaxValue)

        if ($regressionRun.ExitCode -ne 0 -and -not $regressionRun.BailedOut) {
            $regressionError = "copilot exited with code $($regressionRun.ExitCode)"
        }
    }
    catch {
        $regressionError = $_.ToString()
        Write-Warning "Regression analysis error: $regressionError"
    }

    $regressionDuration = [math]::Round(((Get-Date) - $regressionStart).TotalSeconds, 1)
    $regressionResultPath = $null

    # Copy regression analysis back
    $regressionFile = Get-ChildItem -Path $TestFolder -Filter "regression_analysis.md" -Recurse -File 2>$null |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($regressionFile) {
        Copy-Item -Path $regressionFile.FullName -Destination $resultDest -Force
        $regressionResultPath = Join-Path $resultDest "regression_analysis.md"
        Write-Host "Regression analysis: $regressionResultPath"
    }

    $runnerTelemetry.postProcessing += [PSCustomObject]@{
        phase                = "regression-analysis"
        status               = (Get-RunStatus -Run $regressionRun -ErrorMessage $regressionError)
        durationSeconds      = $regressionDuration
        error                = $regressionError
        exitCode             = if ($regressionRun) { $regressionRun.ExitCode } else { $null }
        bailOutCode          = if ($regressionRun) { $regressionRun.BailOutCode } else { $null }
        unsupportedOptionHits = if ($regressionRun) { $regressionRun.UnsupportedOptionHits } else { 0 }
        logPath              = $regressionLog
        session              = if ($regressionRun) { $regressionRun.SessionTelemetry } else { $null }
        resultPath           = $regressionResultPath
    }
}

$runnerTelemetry.suite = [ordered]@{
    totalPlansDiscovered = $evalPlans.Count
    executedPlans        = $summary.Count
    suiteBailOut         = $suiteBailOut
    suiteBailOutCode     = $suiteBailOutCode
    suiteBailOutReason   = $suiteBailOutReason
    resultDestination    = $resultDest
    workspaceName        = $workspaceName
    workspaceId          = $workspaceId
}
$runnerTelemetry.generatedAt = (Get-Date).ToString("o")
$runnerTelemetry | ConvertTo-Json -Depth 20 | Set-Content -Path $telemetryPath -Encoding UTF8
Write-Host "Telemetry written to: $telemetryPath"

# ---------------------------------------------------------------------------
# Workspace cleanup — delete if no suite bail-out
# ---------------------------------------------------------------------------
if (-not $suiteBailOut) {
    Write-Host "`n--- Deleting eval workspace: $workspaceName ($workspaceId) ---"
    try {
        # Refresh token in case the run was long
        $token = (az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv)
        $headers = @{ "Authorization" = "Bearer $token"; "Content-Type" = "application/json" }
        Invoke-RestMethod -Uri "$fabricApi/workspaces/$workspaceId" -Headers $headers -Method Delete
        Write-Host "  Workspace deleted."
    }
    catch {
        Write-Warning "  Failed to delete workspace: $_"
        Write-Warning "  Clean up manually: $workspaceName ($workspaceId)"
    }
}
else {
    Write-Warning "Suite bailed out — workspace preserved for investigation: $workspaceName ($workspaceId)"
}

if ($suiteBailOut) {
    Write-Error "${suiteBailOutCode}: $suiteBailOutReason"
    exit 10
}
