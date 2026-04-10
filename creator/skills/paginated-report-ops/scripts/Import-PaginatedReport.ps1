<#
.SYNOPSIS
    Import a paginated report (.rdl) into a Microsoft Fabric workspace.

.DESCRIPTION
    Uploads an .rdl file to a Fabric workspace via the Power BI Import REST API.
    Designed as the second step in a PBIRS-to-Fabric migration workflow:
      1. Replace-PaginatedReportDataSource.ps1  — repoints .rdl to a Fabric semantic model
      2. Import-PaginatedReport.ps1 (this script) — uploads the modified .rdl into Fabric

    Key technical details:
      - Uses System.Net.Http.HttpClient for proper multipart/form-data encoding
        (PowerShell's Invoke-RestMethod corrupts multipart payloads for .rdl files)
      - The datasetDisplayName parameter MUST include the .rdl extension — this is how
        the Power BI Import API distinguishes paginated report uploads from .pbix uploads
      - For RDL files, only nameConflict values 'Abort' and 'Overwrite' are supported
      - Folder placement uses the subfolderObjectId query parameter with a fallback to
        the Fabric REST API move endpoint if direct placement doesn't work

    Prerequisite: You must be logged in via 'az login' with Contributor access to the
    target workspace.

.PARAMETER WorkspaceName
    The name of the Fabric workspace to import into.

.PARAMETER RdlFilePath
    Path to the .rdl file to import. Can be a local path or UNC path.
    Example: "C:\Migration\Ready\SalesReport.rdl" or "\\server\share\reports\SalesReport.rdl"

.PARAMETER ReportName
    Display name for the imported report in Fabric. If omitted, defaults to the
    .rdl filename without extension (e.g. "SalesReport.rdl" → "SalesReport").

.PARAMETER FolderName
    Optional. Name of an existing workspace folder to place the report in.
    The folder must already exist in the workspace. If omitted, the report is
    placed at the workspace root.

.PARAMETER Overwrite
    If specified, deletes any existing paginated report with the same name before
    importing. Without this switch, the import aborts if a name conflict exists.

.EXAMPLE
    # Simple import — report name derived from filename, placed at workspace root
    .\Import-PaginatedReport.ps1 -WorkspaceName "Main" -RdlFilePath ".\SalesReport.rdl"

.EXAMPLE
    # Import with rename, folder placement, and overwrite
    .\Import-PaginatedReport.ps1 `
        -WorkspaceName "Main" `
        -RdlFilePath ".\SalesReport.rdl" `
        -ReportName "Sales Overview" `
        -FolderName "PaginatedReports" `
        -Overwrite

.EXAMPLE
    # Batch-import all modified .rdl files from a migration folder
    Get-ChildItem "C:\Migration\Ready\*.rdl" | ForEach-Object {
        .\Import-PaginatedReport.ps1 `
            -WorkspaceName "Main" `
            -RdlFilePath $_.FullName `
            -FolderName "Migrated Reports" `
            -Overwrite
    }
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory, HelpMessage = "Fabric workspace name")]
    [string] $WorkspaceName,

    [Parameter(Mandatory, HelpMessage = "Path to the .rdl file to import")]
    [string] $RdlFilePath,

    [string] $ReportName,
    [string] $FolderName,
    [switch] $Overwrite
)

$ErrorActionPreference = "Stop"

# ============================================================================
# STEP 1: Validate input file
# ============================================================================
# Confirm the .rdl file exists and resolve its full path (handles relative paths
# and UNC paths). If no ReportName is provided, derive it from the filename.
if (-not (Test-Path $RdlFilePath)) { throw "File not found: $RdlFilePath" }
$rdlFullPath = (Resolve-Path $RdlFilePath).Path
if (-not $ReportName) { $ReportName = [System.IO.Path]::GetFileNameWithoutExtension($rdlFullPath) }

Write-Host "Import Paginated Report to Fabric" -ForegroundColor Green
Write-Host "  File        : $rdlFullPath"
Write-Host "  Report name : $ReportName"
Write-Host "  Workspace   : $WorkspaceName"
if ($FolderName) { Write-Host "  Folder      : $FolderName" }
if ($Overwrite)  { Write-Host "  Overwrite   : Yes" -ForegroundColor Yellow }

# ============================================================================
# STEP 2: Acquire authentication tokens
# ============================================================================
# Two separate tokens are needed:
#   - Power BI token (analysis.windows.net) — for the Import API and report operations
#   - Fabric token (api.fabric.microsoft.com) — for folder resolution and move operations
# Both are obtained from 'az login' credentials.
Write-Host "`nAcquiring tokens..." -ForegroundColor Cyan
$pbiToken = az account get-access-token --resource "https://analysis.windows.net/powerbi/api" --query accessToken -o tsv
if (-not $pbiToken) { throw "Failed to acquire Power BI token. Run 'az login' first." }
$ph = @{ Authorization = "Bearer $pbiToken"; "Content-Type" = "application/json" }

$fabricToken = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
if (-not $fabricToken) { throw "Failed to acquire Fabric token. Run 'az login' first." }
$fh = @{ Authorization = "Bearer $fabricToken"; "Content-Type" = "application/json" }
Write-Host "  Tokens acquired."

# ============================================================================
# STEP 3: Resolve the Fabric workspace by name
# ============================================================================
# The Import API requires a workspace GUID. We look it up by display name
# using the Power BI Groups API.
Write-Host "`nResolving workspace '$WorkspaceName'..." -ForegroundColor Cyan
$workspaces = (Invoke-RestMethod "https://api.powerbi.com/v1.0/myorg/groups" -Headers $ph).value
$ws = $workspaces | Where-Object { $_.name -eq $WorkspaceName }
if (-not $ws) { throw "Workspace '$WorkspaceName' not found. Check the name and your access permissions." }
$wsId = $ws.id
Write-Host "  Workspace ID: $wsId"

# ============================================================================
# STEP 4: Resolve the target folder (if specified)
# ============================================================================
# Workspace folders in Fabric are accessed via a dedicated Fabric REST API endpoint
# (not the Power BI API). The folder GUID is used as subfolderObjectId in the
# import URL or for a post-import move operation.
$folderId = $null
if ($FolderName) {
    Write-Host "Resolving folder '$FolderName'..." -ForegroundColor Cyan
    $folders = (Invoke-RestMethod "https://api.fabric.microsoft.com/v1/workspaces/$wsId/folders" -Headers $fh).value
    $folder = $folders | Where-Object { $_.displayName -eq $FolderName }
    if (-not $folder) {
        Write-Host "  Available folders:" -ForegroundColor Yellow
        $folders | ForEach-Object { Write-Host "    - $($_.displayName)" }
        throw "Folder '$FolderName' not found in workspace '$WorkspaceName'."
    }
    $folderId = $folder.id
    Write-Host "  Folder ID: $folderId"
}

# ============================================================================
# STEP 5: Handle existing report (if -Overwrite specified)
# ============================================================================
# If a paginated report with the same name already exists in the workspace,
# we delete it first to avoid import conflicts. The Power BI Import API's
# "Overwrite" nameConflict mode is unreliable for RDL files, so explicit
# delete + fresh import is more dependable.
if ($Overwrite) {
    Write-Host "`nChecking for existing report '$ReportName'..." -ForegroundColor Cyan
    $reports = (Invoke-RestMethod "https://api.powerbi.com/v1.0/myorg/groups/$wsId/reports" -Headers $ph).value
    $existing = $reports | Where-Object { $_.name -eq $ReportName -and $_.reportType -eq "PaginatedReport" }
    if ($existing) {
        Write-Host "  Deleting existing report (ID: $($existing.id))..." -ForegroundColor Yellow
        Invoke-RestMethod "https://api.powerbi.com/v1.0/myorg/groups/$wsId/reports/$($existing.id)" `
            -Method DELETE -Headers $ph
        # Brief pause to let Fabric propagate the deletion
        Start-Sleep -Seconds 3
        Write-Host "  Deleted."
    } else {
        Write-Host "  No existing report found — proceeding with fresh import."
    }
}

# ============================================================================
# STEP 6: Build the Import API URL
# ============================================================================
# CRITICAL: The datasetDisplayName parameter MUST include the .rdl extension.
# This is how the Power BI Import API identifies the upload as a paginated report
# rather than a .pbix file. Without the extension, the import will fail.
#
# URL parameters:
#   - datasetDisplayName: report name WITH .rdl extension
#   - nameConflict: Abort (fail if exists) or Overwrite
#   - subfolderObjectId: optional folder GUID for direct placement
$displayName = [System.Uri]::EscapeDataString("$ReportName.rdl")
$nameConflict = if ($Overwrite) { "Overwrite" } else { "Abort" }
$url = "https://api.powerbi.com/v1.0/myorg/groups/$wsId/imports?datasetDisplayName=$displayName&nameConflict=$nameConflict"
if ($folderId) { $url += "&subfolderObjectId=$folderId" }

# ============================================================================
# STEP 7: Upload the .rdl via multipart/form-data
# ============================================================================
# We use System.Net.Http.HttpClient instead of PowerShell's Invoke-RestMethod
# because Invoke-RestMethod does not produce correct multipart boundaries for
# binary file uploads — this causes "RequestedFileIsEncryptedOrCorrupted" errors.
# HttpClient handles the multipart encoding correctly.
Write-Host "`nUploading .rdl ($((Get-Item $rdlFullPath).Length) bytes)..." -ForegroundColor Cyan
Add-Type -AssemblyName System.Net.Http
$httpClient = [System.Net.Http.HttpClient]::new()
$httpClient.Timeout = [System.TimeSpan]::FromMinutes(5)
$httpClient.DefaultRequestHeaders.Authorization = `
    [System.Net.Http.Headers.AuthenticationHeaderValue]::new("Bearer", $pbiToken)

$multipart = [System.Net.Http.MultipartFormDataContent]::new()
$fileBytes = [System.IO.File]::ReadAllBytes($rdlFullPath)
$fileContent = [System.Net.Http.ByteArrayContent]::new($fileBytes)
$fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::new("application/octet-stream")
$multipart.Add($fileContent, "file", "$ReportName.rdl")

try {
    # Send the import request — expects HTTP 200 or 202 (Accepted)
    $response = $httpClient.PostAsync($url, $multipart).Result
    $statusCode = [int]$response.StatusCode
    $body = $response.Content.ReadAsStringAsync().Result

    if ($statusCode -notin @(200, 202)) {
        throw "Import failed (HTTP $statusCode): $body"
    }

    $importResult = $body | ConvertFrom-Json
    $importId = $importResult.id
    Write-Host "  Import accepted (ID: $importId). Polling for completion..." -ForegroundColor Cyan

    # ========================================================================
    # STEP 8: Poll for import completion
    # ========================================================================
    # The import is asynchronous. We poll the import status every 2 seconds
    # until it succeeds, fails, or times out (60 seconds max).
    $maxAttempts = 30
    for ($i = 0; $i -lt $maxAttempts; $i++) {
        Start-Sleep -Seconds 2
        $status = Invoke-RestMethod "https://api.powerbi.com/v1.0/myorg/groups/$wsId/imports/$importId" -Headers $ph
        if ($status.importState -eq "Succeeded") {
            $newReport = $status.reports[0]

            # ==================================================================
            # STEP 9: Verify the imported report
            # ==================================================================
            # Confirm the report was created and display its properties.
            # Also check the data source binding to verify it points to the
            # expected Fabric semantic model.
            Write-Host "`nImport succeeded!" -ForegroundColor Green
            Write-Host "  Report name : $($newReport.name)"
            Write-Host "  Report ID   : $($newReport.id)"
            Write-Host "  Report type : $($newReport.reportType)"

            try {
                $ds = (Invoke-RestMethod "https://api.powerbi.com/v1.0/myorg/groups/$wsId/reports/$($newReport.id)/datasources" -Headers $ph).value
                $ds | ForEach-Object {
                    Write-Host "  Data source : $($_.name) → $($_.connectionDetails.database)" -ForegroundColor Cyan
                }
            } catch {}

            # ==================================================================
            # STEP 10: Ensure report is in the target folder
            # ==================================================================
            # The subfolderObjectId parameter in the import URL should place the
            # report directly in the folder. However, this doesn't always work
            # reliably. As a fallback, we check if the report ended up in the
            # folder and use the Fabric move API if it didn't.
            if ($folderId) {
                $items = (Invoke-RestMethod "https://api.fabric.microsoft.com/v1/workspaces/$wsId/items?rootFolderId=$folderId" -Headers $fh).value
                $inFolder = $items | Where-Object { $_.id -eq $newReport.id }
                if (-not $inFolder) {
                    Write-Host "  Moving to folder '$FolderName'..." -ForegroundColor Cyan
                    $moveBody = @{ targetFolderId = $folderId } | ConvertTo-Json
                    Invoke-RestMethod "https://api.fabric.microsoft.com/v1/workspaces/$wsId/items/$($newReport.id)/move" `
                        -Method POST -Headers $fh -Body $moveBody
                    Write-Host "  Moved to folder." -ForegroundColor Green
                } else {
                    Write-Host "  Already in folder '$FolderName'." -ForegroundColor Green
                }
            }

            Write-Host "`n$('=' * 50)" -ForegroundColor Green
            Write-Host "Report '$ReportName' imported successfully." -ForegroundColor Green
            Write-Host "$('=' * 50)" -ForegroundColor Green
            return
        } elseif ($status.importState -eq "Failed") {
            throw "Import failed: $($status.error | ConvertTo-Json -Compress)"
        }
        Write-Host "  Polling... ($($status.importState))" -NoNewline
    }
    throw "Import timed out after $maxAttempts attempts."
} finally {
    # Always dispose the HttpClient to release connections
    $httpClient.Dispose()
}
