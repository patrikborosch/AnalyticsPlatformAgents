param(
    [Parameter(Mandatory = $false)]
    [string]$tenant = "E2EAPIMSIT2.onmicrosoft.com",
    [Parameter(Mandatory = $false)]
    [string]$testName,
    [Parameter(Mandatory = $false)]
    [switch]$skipLogin,
    [Parameter(Mandatory = $false)]
    [switch]$skipSetup,
    [Parameter(Mandatory = $false)]
    [switch]$SkipCleanup,
    [Parameter(Mandatory = $false)]
    [string]$spObjectId,
    [Parameter(Mandatory = $false)]
    [string]$spLogin,
    [Parameter(Mandatory = $false)]
    [string]$spCertPath,
    [Parameter(Mandatory = $false)]
    [int]$throttleLimit = 10,
    [Parameter(Mandatory = $false)]
    [int]$timeoutSeconds = 900,
    [Parameter(Mandatory = $false)]
    [string]$resultsDir,
    [Parameter(Mandatory = $false)]
    [string]$model = "claude-sonnet-4.5",
    [Parameter(Mandatory = $false)]
    [string]$capacityId
)

$ErrorActionPreference = "Stop"

# Validate -throttleLimit. A value < 1 makes the downstream parallel-jobs
# throttling loop never progress and the run hangs indefinitely.
if ($throttleLimit -lt 1) {
    Write-Error "-throttleLimit must be >= 1 (got '$throttleLimit'). Use 1 for serial execution; 10 is the default."
    return
}

# Validate -timeoutSeconds. Anything under ~15s is unrealistic for any real
# Copilot CLI test (cold-start alone is ~10s). Zero or negative would cause
# WaitForExit to throw or fire immediately.
if ($timeoutSeconds -lt 15) {
    Write-Error "-timeoutSeconds must be >= 15 (got '$timeoutSeconds'). Copilot CLI cold-start alone is ~10s; 900 is the default."
    return
}

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
        Write-Error "-capacityId must not be empty or whitespace-only. Omit the flag entirely to use discovery + rotation."
        return
    }
    $parsedGuid = [Guid]::Empty
    if (-not [Guid]::TryParse($capacityId, [ref]$parsedGuid)) {
        Write-Error "-capacityId must be a valid GUID (got '$capacityId'). Use the bare GUID form without braces."
        return
    }
    $capacityId = $parsedGuid.ToString()
}
$testsRoot = $PSScriptRoot
$repoRoot = Split-Path -Parent $testsRoot
$testdataDir = Join-Path $testsRoot "testdata"
$setupScript = Join-Path $testdataDir "setup_test_env.py"
$lastSetupJson = Join-Path $testdataDir "last_setup.json"
$testRunner = Join-Path $testsRoot "testFabricSkills.ps1"

# -------------------------------------------------------------------
# Validate build_plugins.py has been run
# -------------------------------------------------------------------
$pluginSkillsDir = Join-Path (Join-Path $repoRoot "plugins") "fabric-skills" | Join-Path -ChildPath "skills"
if (-not (Test-Path $pluginSkillsDir)) {
    Write-Host "ERROR: Plugin skills not materialized. Run 'python build/build_plugins.py' first." -ForegroundColor Red
    Write-Error "build_plugins.py must be run before executing tests."
    return
}

# -------------------------------------------------------------------
# Prerequisites
# -------------------------------------------------------------------
# Two supported auth modes:
#
# (A) Shared ephemeral tenant + service principal -- the path nightly CI uses.
#     Pass -tenant <current rotation>.onmicrosoft.com -spLogin <app-id>
#     -spCertPath <pem> -spObjectId <oid>. Setup is documented in
#     docs/ephemeral-tenant-smoke.md.
#
# (B) Legacy E2EAPIMSIT2.onmicrosoft.com + user CBA cert -- still supported for
#     Microsoft contributors with the pbitestusera-3iqq entitlement. Default
#     when -tenant is not passed (kept for backward compat).
# -------------------------------------------------------------------

Write-Host ""
Write-Host "==============================" -ForegroundColor Cyan
Write-Host "  Smoke Test Prerequisites" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan
if ($spLogin) {
    Write-Host "  Auth mode:    Service principal (CI-equivalent path)"
    Write-Host "  Tenant:       $tenant"
    Write-Host "  SP app id:    $spLogin"
    Write-Host "  Cert path:    $spCertPath"
    Write-Host "  Setup docs:   docs/ephemeral-tenant-smoke.md"
}
elseif ($tenant -eq "E2EAPIMSIT2.onmicrosoft.com") {
    Write-Host "  Auth mode:    Legacy user CBA (E2EAPIMSIT2)"
    Write-Host "  Test user:    apitestadmin@E2EAPIMSIT2.onmicrosoft.com"
    Write-Host "  Certificate:  Download from Azure Key Vault:"
    Write-Host "    https://ms.portal.azure.com/#view/Microsoft_Azure_KeyVault/ListObjectVersionsRBACBlade/~/overview/objectType/certificates/objectId/https%3A%2F%2Fe2eapimsit2-ga.vault.azure.net%2Fcertificates%2FE2EAPIMSIT2-apitestadmin/vaultResourceUri/%2Fsubscriptions%2F70a05e70-7ce4-45b3-9503-0bbf83c2a864%2FresourceGroups%2FProdTestTenants%2Fproviders%2FMicrosoft.KeyVault%2Fvaults%2FE2EAPIMSIT2-GA/vaultId/%2Fsubscriptions%2F70a05e70-7ce4-45b3-9503-0bbf83c2a864%2FresourceGroups%2FProdTestTenants%2Fproviders%2FMicrosoft.KeyVault%2Fvaults%2FE2EAPIMSIT2-GA"
    Write-Host "  Entitlement:  https://coreidentity.microsoft.com/manage/Entitlement/entitlement/pbitestusera-3iqq"
}
else {
    Write-Host "  Auth mode:    Browser CBA (interactive login)"
    Write-Host "  Tenant:       $tenant"
    Write-Host "  Setup docs:   docs/ephemeral-tenant-smoke.md"
    Write-Host "  Tip:          Pass -spLogin/-spCertPath/-spObjectId for the CI-equivalent path"
    Write-Host "  Reminder:     Approved test tenants are the current rotation from aka.ms/fabrictenants or E2EAPIMSIT2.onmicrosoft.com -- do not target personal tenants." -ForegroundColor Yellow
}
Write-Host ""

# -------------------------------------------------------------------
# Step 1a: SP login (runs whether or not we skip setup, so that
# -skipSetup callers also switch identity to the SP if they asked for it).
# -------------------------------------------------------------------
if ($spLogin -and $spCertPath) {
    Write-Host "`nLogging in as service principal: $spLogin" -ForegroundColor Yellow
    if (-not (Test-Path $spCertPath)) {
        Write-Error "spCertPath '$spCertPath' does not exist"
        return
    }
    az login --service-principal --tenant $tenant --username $spLogin --certificate $spCertPath --allow-no-subscriptions | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Service principal login failed (LASTEXITCODE=$LASTEXITCODE)"
        return
    }
    $skipLogin = $true  # already logged in; tell setup script not to re-login
}

# -------------------------------------------------------------------
# Step 1b: Run setup_test_env.py to provision workspace + lakehouse
# -------------------------------------------------------------------
if (-not $skipSetup) {
    Write-Host "`n=== Provisioning test environment ===" -ForegroundColor Cyan

    $setupArgs = @()
    if ($tenant) { $setupArgs += "--tenant", $tenant }
    if ($skipLogin) { $setupArgs += "--skip-login" }
    if ($spObjectId) { $setupArgs += "--sp-object-id", $spObjectId }
    if ($capacityId) {
        Write-Host "  Using pinned Fabric capacity: $capacityId" -ForegroundColor Cyan
        $setupArgs += "--capacity-id", $capacityId
    }

    & python $setupScript @setupArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Error "setup_test_env.py failed with exit code $LASTEXITCODE"
        return
    }
}

# -------------------------------------------------------------------
# Step 2: Read workspace name from last_setup.json
# -------------------------------------------------------------------
if (-not (Test-Path $lastSetupJson)) {
    Write-Error "last_setup.json not found at $lastSetupJson. Run setup first."
    return
}

$setupInfo = Get-Content $lastSetupJson -Raw | ConvertFrom-Json
$workspaceName = $setupInfo.workspace_name

if (-not $workspaceName) {
    Write-Error "workspace_name not found in last_setup.json"
    return
}

if (-not $setupInfo.data_loaded) {
    Write-Warning "Data was not loaded into the lakehouse. Some tests may fail."
}

Write-Host "`nWorkspace: $workspaceName" -ForegroundColor Green
Write-Host "Lakehouse: $($setupInfo.lakehouse_name) ($($setupInfo.lakehouse_id))" -ForegroundColor Green
if ($setupInfo.eventhouse_name) {
    Write-Host "Eventhouse: $($setupInfo.eventhouse_name) ($($setupInfo.eventhouse_id))" -ForegroundColor Green
    Write-Host "KQL Database: $($setupInfo.kql_database_name)" -ForegroundColor Green
    if (-not $setupInfo.weather_loaded) {
        Write-Warning "Weather data was not loaded into the Eventhouse. Eventhouse tests may fail."
    }
}

# -------------------------------------------------------------------
# Step 3: Run testFabricSkills.ps1 with the provisioned workspace
# -------------------------------------------------------------------
Write-Host "`n=== Running smoke tests ===" -ForegroundColor Cyan

$runnerArgs = @{ workspace = $workspaceName; throttleLimit = $throttleLimit; timeoutSeconds = $timeoutSeconds; model = $model }
if ($testName) { $runnerArgs["testName"] = $testName }
if ($resultsDir) { $runnerArgs["directoryPath"] = $resultsDir }

& $testRunner @runnerArgs

# -------------------------------------------------------------------
# Step 4: If ALL tests passed, delete the workspace (cleanup)
# -------------------------------------------------------------------
$latestResultsDir = Get-ChildItem "$env:TEMP" -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName "testsResults.json") } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($latestResultsDir) {
    $resultsFile = Join-Path $latestResultsDir.FullName "testsResults.json"
    $results = Get-Content $resultsFile -Raw | ConvertFrom-Json
    $failedCount = @($results | Where-Object { $_.passed -ne "Y" }).Count

    if ($failedCount -eq 0 -and $results.Count -gt 0) {
        $wsId = $setupInfo.workspace_id
        if ($SkipCleanup) {
            Write-Host "`n=== All $($results.Count) tests passed -- workspace KEPT (-SkipCleanup) ===" -ForegroundColor Yellow
            Write-Host "  Workspace: $workspaceName" -ForegroundColor Yellow
            Write-Host "  ID: $wsId" -ForegroundColor Yellow
            Write-Host "  Delete manually when done: az rest --method DELETE --url https://api.fabric.microsoft.com/v1/workspaces/$wsId --resource https://api.fabric.microsoft.com" -ForegroundColor Yellow
        }
        else {
            Write-Host "`n=== All $($results.Count) tests passed -- deleting workspace ===" -ForegroundColor Green
            try {
                az rest --method DELETE --url "https://api.fabric.microsoft.com/v1/workspaces/$wsId" --resource "https://api.fabric.microsoft.com" 2>&1 | Out-Null
                Write-Host "  Deleted workspace: $workspaceName ($wsId)" -ForegroundColor Green
            }
            catch {
                Write-Warning "  Failed to delete workspace: $_"
            }
        }
    }
    else {
        Write-Host "`n=== $failedCount test(s) failed — keeping workspace for investigation ===" -ForegroundColor Yellow
        Write-Host "  Workspace: $workspaceName" -ForegroundColor Yellow
        Write-Host "  ID: $($setupInfo.workspace_id)" -ForegroundColor Yellow
    }
}
