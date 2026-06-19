#Requires -Version 7.0
<#
.SYNOPSIS
    Verifies that a service principal can see a specific Fabric capacity.

.DESCRIPTION
    Logs in as the supplied service principal (cert-based) and calls
    GET /v1/capacities. Confirms the pinned capacity GUID is present
    and Active. Use this before setting the FABRIC_CAPACITY_ID repo
    variable to avoid wiring CI to a capacity the SP cannot actually
    use (Contributor permission propagation lag, wrong tenant, etc).

    See docs/ephemeral-tenant-smoke.md ("Pinned capacity") for the
    grant procedure that this script verifies.

.PARAMETER tenant
    Tenant domain (e.g. msitprimary03192026.onmicrosoft.com).

.PARAMETER spLogin
    Service principal application (client) ID.

.PARAMETER spCertPath
    Path to the SP certificate PEM file.

.PARAMETER capacityId
    Capacity GUID to look for in the /v1/capacities response.

.EXAMPLE
    ./tests/verify-sp-capacity-access.ps1 `
        -tenant "msitprimary03192026.onmicrosoft.com" `
        -spLogin "38e8c89d-04ed-4f60-ae38-..." `
        -spCertPath "C:\temp\sp-cert.pem" `
        -capacityId "46661b2c-6d06-4733-a9af-8703a422d1c9"
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$tenant,
    [Parameter(Mandatory = $true)]
    [string]$spLogin,
    [Parameter(Mandatory = $true)]
    [string]$spCertPath,
    [Parameter(Mandatory = $true)]
    [string]$capacityId
)

$ErrorActionPreference = "Stop"

# Normalize the user-supplied capacity GUID so we compare against the REST
# response in a canonical form. Accepts both bare and brace-wrapped GUIDs.
$capacityId = $capacityId.Trim().TrimStart('{').TrimEnd('}')
$targetGuid = [Guid]::Empty
if (-not [Guid]::TryParse($capacityId, [ref]$targetGuid)) {
    Write-Error "-capacityId must be a valid GUID (got '$capacityId')."
    exit 1
}
$capacityId = $targetGuid.ToString()

if (-not (Test-Path -LiteralPath $spCertPath)) {
    Write-Error "Cert path not found: $spCertPath"
    exit 1
}

Write-Host "--- Verifying SP capacity access ---" -ForegroundColor Cyan
Write-Host "  Tenant:      $tenant"
Write-Host "  SP App ID:   $spLogin"
Write-Host "  Cert:        $spCertPath"
Write-Host "  Capacity ID: $capacityId"
Write-Host ""

# Login as the SP. Suppress the verbose subscription-listing output so the
# only signal that matters (the /v1/capacities probe below) stays readable.
az login --service-principal `
    --tenant $tenant `
    --username $spLogin `
    --certificate $spCertPath `
    --allow-no-subscriptions 1>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "az login as SP failed (exit $LASTEXITCODE)."
    exit 1
}

# Acquire a Fabric REST token (audience = https://api.fabric.microsoft.com).
# Cert-based login above does NOT require a subscription, but the token
# endpoint does require an explicit resource scope.
$token = az account get-access-token `
    --resource "https://api.fabric.microsoft.com" `
    --query accessToken -o tsv
if ($LASTEXITCODE -ne 0 -or -not $token) {
    Write-Error "az account get-access-token failed."
    exit 1
}

# Probe /v1/capacities. This is the same endpoint setup_test_env.py uses;
# a hit here proves the SP will see the capacity at smoke runtime.
$headers = @{ Authorization = "Bearer $token" }
$resp = Invoke-RestMethod -Uri "https://api.fabric.microsoft.com/v1/capacities" -Headers $headers -Method Get

if (-not $resp.value) {
    Write-Error "GET /v1/capacities returned no capacities at all. SP may lack any Fabric capacity access."
    exit 1
}

Write-Host "  SP sees $($resp.value.Count) capacity/capacities:" -ForegroundColor DarkGray
foreach ($cap in $resp.value) {
    $isMatch = $false
    $parsed = [Guid]::Empty
    if ([Guid]::TryParse($cap.id, [ref]$parsed)) {
        $isMatch = ($parsed -eq $targetGuid)
    }
    $marker = if ($isMatch) { "  <-- pinned" } else { "" }
    Write-Host ("    {0,-40}  id={1}  state={2}{3}" -f $cap.displayName, $cap.id, $cap.state, $marker)
}
Write-Host ""

$match = $resp.value | Where-Object {
    $parsed = [Guid]::Empty
    [Guid]::TryParse($_.id, [ref]$parsed) -and $parsed -eq $targetGuid
}
if (-not $match) {
    Write-Error "FAIL: capacity $capacityId is NOT visible to the SP. Check the Contributor permission grant in the Fabric admin portal and wait ~5 min for propagation."
    exit 1
}

if ($match.state -ne "Active") {
    Write-Error "FAIL: capacity $capacityId is visible but state=$($match.state) (not Active). Cannot pin CI to a non-active capacity."
    exit 1
}

Write-Host "OK: SP can see capacity '$($match.displayName)' (id=$capacityId, state=Active)." -ForegroundColor Green
Write-Host "Safe to set repo variable: gh variable set FABRIC_CAPACITY_ID --body $capacityId"
exit 0
