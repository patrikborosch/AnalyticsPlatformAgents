# Tenant Rotation Runbook

> **What this is for:** the Fabric Shared Test Tenant pattern at `aka.ms/fabrictenants` provisions new ephemeral tenants every ~90 days. This runbook walks through the manual refresh when our smoke / eval CI loses access because the tenant rotated.
>
> **Audience:** a human OR an AI agent (the steps are kept simple enough for either).

## Detection

You'll notice rotation needed when one of these happens:

| Symptom | Meaning |
|---|---|
| `AADSTS50034: user account does not exist in tenant` | Old tenant deleted; need new one |
| `AADSTS700016: app not found` | SP needs reprovisioning in new tenant |
| Smoke workflow auto-files a GitHub issue tagged `fabric-tenant-rotation` after detecting an AAD rotation code in run logs | Same as above, detected by the workflow's `Detect tenant-rotation errors` step (`.github/workflows/fabric-smoke-ephemeral.yml`) |
| Smoke workflow fails with "no workspaces visible" + new tenant ID in failure log | Old SP exists but in wrong tenant |

## Pre-conditions

- [ ] You are a member of AAD group `PBI-Test-UserAcc-Access` (auto-approved for Azure Data Org members; 24-48h propagation)
- [ ] You have access to `aka.ms/fabrictenants` (intranet wiki)
- [ ] You have local `az`, `openssl` (via Git for Windows), and PowerShell
- [ ] You know the Key Vault name we use to store SP secrets in production

## Step 1 — Identify the new tenant

1. Open `aka.ms/fabrictenants`.
2. Find the `MsitPrimary` row in the MSIT Accounts table. Note:
   - **Tenant domain** (e.g., `msitprimary03192026.onmicrosoft.com`)
   - **Tenant ID** (GUID below the cluster name)
   - **Admin UPN** (e.g., `AdminUser01@msitprimary03192026.onmicrosoft.com`)
   - **Certificate link** (`AdminCert01`)
   - **Expiry date** (e.g., `2-Jun-26`)

> Capture these in a note before continuing. They go into Key Vault in step 5.

## Step 2 — Download the new admin cert

Click the **`AdminCert01`** link in the wiki and save to:

```text
C:\temp\fabric-shared-tenant\AdminCert01.pfx
```

Most certs are passwordless; if a password is shown next to the link, save it too.

## Step 3 — Log in as the new tenant admin

```powershell
# Install the cert in Windows cert store so az can pick it up via browser CBA.
# Most PBI test certs are passwordless — only pass -Password if a password is shown next to the link on the wiki.
$importArgs = @{
    FilePath = "C:\temp\fabric-shared-tenant\AdminCert01.pfx"
    CertStoreLocation = "Cert:\CurrentUser\My"
}
# If the wiki shows a password for this cert, uncomment and set it:
# $importArgs.Password = ConvertTo-SecureString -String "<password>" -AsPlainText -Force
Import-PfxCertificate @importArgs

# Log in (browser opens, select the cert when prompted)
az login --tenant "<NEW-TENANT-DOMAIN>.onmicrosoft.com" --allow-no-subscriptions
```

Verify:

```powershell
az account show --query "{user:user.name, tenant:tenantId}" -o table
# Should show: AdminUser01@<new-tenant>.onmicrosoft.com  +  the new tenant ID
```

## Step 4 — Re-provision the smoke service principal in the new tenant

The SP from the previous rotation only exists in the OLD tenant. AAD doesn't carry app registrations across rotated tenants. You need a fresh SP.

```powershell
# Create the app registration
$createResult = az ad app create `
    --display-name "fabric-skills-smoke-test" `
    --sign-in-audience AzureADMyOrg | ConvertFrom-Json
$appId = $createResult.appId

# Create the service principal
$sp = az ad sp create --id $appId | ConvertFrom-Json
$spObjectId = $sp.id

# Generate a self-signed cert (2-year validity matches AAD default cap)
$cert = New-SelfSignedCertificate `
    -Subject "CN=fabric-skills-smoke-test" `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -KeyExportPolicy Exportable `
    -KeySpec Signature `
    -KeyLength 2048 `
    -KeyAlgorithm RSA `
    -HashAlgorithm SHA256 `
    -NotAfter (Get-Date).AddYears(2)

$pfxPath = "C:\temp\fabric-shared-tenant\fabric-smoke-sp.pfx"
$cerPath = "C:\temp\fabric-shared-tenant\fabric-smoke-sp.cer"
# Export with EMPTY password (PowerShell needs a SecureString; empty SecureString = empty PFX password).
# This must stay aligned with the openssl `-passin "pass:"` (empty) in the workflow PEM conversion.
$emptySecure = New-Object System.Security.SecureString
Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $emptySecure | Out-Null
Export-Certificate -Cert $cert -FilePath $cerPath | Out-Null

# Upload public cert to the app registration
az ad app credential reset --id $appId --cert "@$cerPath" --append | Out-Null

# Convert PFX -> PEM for az CLI consumption. The empty-password PFX above pairs with `pass:` (NOT `pass: `).
& "C:\Program Files\Git\usr\bin\openssl.exe" pkcs12 `
    -in $pfxPath `
    -out "C:\temp\fabric-shared-tenant\fabric-smoke-sp.pem" `
    -nodes `
    -passin "pass:"

Write-Host "App ID:        $appId"
Write-Host "SP Object ID:  $spObjectId"
Write-Host "Tenant ID:     $(az account show --query tenantId -o tsv)"
Write-Host "Cert PFX:      $pfxPath"
Write-Host "Cert PEM:      C:\temp\fabric-shared-tenant\fabric-smoke-sp.pem"
```

Save the four values printed at the end — they go into the Key Vault in step 5.

## Step 5 — Refresh Key Vault secrets

Update the production Key Vault (name documented in `ephemeral-tenant-smoke.md`) with the new values:

```powershell
$KV = "<fabric-smoke-kv-name>"  # production KV

# New tenant identifiers
az keyvault secret set --vault-name $KV --name "TENANT-ID"     --value "<NEW-TENANT-ID>"
az keyvault secret set --vault-name $KV --name "TENANT-DOMAIN" --value "<NEW-TENANT>.onmicrosoft.com"
az keyvault secret set --vault-name $KV --name "ADMIN-UPN"     --value "AdminUser01@<NEW-TENANT>.onmicrosoft.com"
az keyvault secret set --vault-name $KV --name "CERT-EXPIRY"   --value "<YYYY-MM-DD from wiki>"

# New SP identifiers
az keyvault secret set --vault-name $KV --name "SP-APP-ID"     --value "<NEW-SP-APP-ID>"
az keyvault secret set --vault-name $KV --name "SP-OBJECT-ID"  --value "<NEW-SP-OBJECT-ID>"

# Upload the new SP cert (base64-encoded PFX). Write the base64 file
# with UTF8 *without BOM* — a BOM corrupts base64 decoding on the KV side.
$pfxBytes = [System.IO.File]::ReadAllBytes("C:\temp\fabric-shared-tenant\fabric-smoke-sp.pfx")
$base64 = [Convert]::ToBase64String($pfxBytes)
$tmp = New-TemporaryFile
# PowerShell 7+: -Encoding utf8NoBOM; PS 5.1: write bytes directly via WriteAllText with new UTF8Encoding($false)
if ($PSVersionTable.PSVersion.Major -ge 6) {
    Set-Content -Path $tmp -Value $base64 -Encoding utf8NoBOM
} else {
    [System.IO.File]::WriteAllText($tmp, $base64, [System.Text.UTF8Encoding]::new($false))
}
az keyvault secret set --vault-name $KV --name "SP-CERT" --file $tmp --encoding base64
Remove-Item $tmp
```

> **Don't update GitHub Actions secrets yet.** They reference KV-stored values, not raw values, so the workflow picks up the new SP automatically on the next run.

## Step 6 — Validate

Trigger the smoke workflow with `workflow_dispatch`:

```powershell
gh workflow run "Fabric Smoke (Shared Test Tenant)" `
    --field "test-names=dataflows-consumption-list-and-inspect"
```

Watch the run; if it returns Y for the test, rotation is complete.

If it returns N or errors with AAD codes, check:
- Tenant ID typo
- SP not yet propagated to the directory (wait 1-2 min, retry)
- Cert format issue (re-export PFX → PEM)

## Step 7 — Clean up + notify

```powershell
# Remove the local PFX files so they aren't lying around
Remove-Item "C:\temp\fabric-shared-tenant\AdminCert01.pfx" -ErrorAction SilentlyContinue
Remove-Item "C:\temp\fabric-shared-tenant\fabric-smoke-sp.pfx" -ErrorAction SilentlyContinue
Remove-Item "C:\temp\fabric-shared-tenant\fabric-smoke-sp.pem" -ErrorAction SilentlyContinue
Remove-Item "C:\temp\fabric-shared-tenant\fabric-smoke-sp.cer" -ErrorAction SilentlyContinue
```

Close the `fabric-tenant-rotation` GitHub issue that the monitor opened. Reference this runbook + the workflow run that confirmed success.

## What to do if smoke workflow fails with rotation-related errors

If the workflow detects `AADSTS50034` or `AADSTS700016` and the maintainer team has not been notified, the workflow should:

1. Open a new GitHub issue tagged `fabric-tenant-rotation` and `auto-filed`
2. Assign one of the maintainers from `.github/CODEOWNERS` (the workflow uses `@mschaumberg_microsoft` as the default; update there if the on-call rotation changes)
3. Link to this runbook
4. Include the offending tenant ID + cert thumbprint + the AAD error code

The detection step is built into `.github/workflows/fabric-smoke-ephemeral.yml` (when that workflow lands).

## AI-runnable variant

If a Copilot agent is running this:

```
Step 1: Open https://aka.ms/fabrictenants. Read the MsitPrimary row.
Step 2: Save AdminCert01 to C:\temp\fabric-shared-tenant\AdminCert01.pfx.
Step 3: Run the powershell block from Step 3 above.
Step 4: Run the powershell block from Step 4 above. Capture appId + spObjectId + tenantId + cert paths.
Step 5: Run the powershell block from Step 5 above, substituting the values from Step 1 + Step 4.
Step 6: Run: gh workflow run "Fabric Smoke (Shared Test Tenant)" --field "test-names=dataflows-consumption-list-and-inspect"
Step 7: Run the cleanup block from Step 7 above.
Step 8: gh issue close <rotation-issue-id> --comment "Refreshed via runbook 2026-XX-XX; workflow run <url> green."
```

## Related

- `docs/ephemeral-tenant-smoke.md` — architecture overview
- `aka.ms/fabrictenants` — current rotation status
- ADO 2088637 — credentials decision (rescoped to this work)
- PowerBIClients pattern: `dev.azure.com/powerbi/PowerBIClients/_search?text=Ephemeral%20Test` (their `tenant-rotation` skill is a precedent)
