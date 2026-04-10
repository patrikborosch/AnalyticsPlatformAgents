<#
.SYNOPSIS
    Repoint a local Power BI Report Server .rdl file to a Microsoft Fabric semantic model.

.DESCRIPTION
    Migration helper for moving paginated reports from Power BI Report Server (on-premise)
    to Microsoft Fabric. Reads an .rdl file from a local folder, replaces ALL data source
    references to point to a Fabric semantic model, and writes the modified .rdl to an
    output folder — ready for import via Import-PaginatedReport.ps1.

    The script performs two key operations:
      1. Looks up the target semantic model ID from the Fabric workspace (via Power BI REST API)
      2. Rewrites the .rdl XML: replaces the <DataSource> connection string and all
         <DataSourceName> references throughout the file

    On-prem .rdl files typically use SQL Server, Oracle, or other data providers.
    This script replaces them with the Fabric PBIDATASET provider pointing to the
    specified semantic model.

    Prerequisite: You must be logged in via 'az login' with access to the target workspace.

.PARAMETER RdlFolder
    Path to the folder containing the .rdl files from Power BI Report Server.
    Example: "\\fileserver\ReportBackups" or "C:\PBIRS\Reports"

.PARAMETER ReportName
    The name of the report (without .rdl extension). The script looks for <ReportName>.rdl
    in the RdlFolder.

.PARAMETER WorkspaceName
    The Fabric workspace that contains the target semantic model.

.PARAMETER TargetSemanticModel
    The display name of the Fabric semantic model to connect the report to.

.PARAMETER OutputFolder
    Folder where the modified .rdl will be saved. Created automatically if it doesn't exist.
    Defaults to a "modified" subfolder inside RdlFolder.

.EXAMPLE
    # Repoint a single report to a Fabric semantic model
    .\Replace-PaginatedReportDataSource.ps1 `
        -RdlFolder "C:\PBIRS\Reports" `
        -ReportName "SalesOverview" `
        -WorkspaceName "Main" `
        -TargetSemanticModel "SM_Sales"

.EXAMPLE
    # Batch-process all .rdl files in a folder
    Get-ChildItem "C:\PBIRS\Reports\*.rdl" | ForEach-Object {
        .\Replace-PaginatedReportDataSource.ps1 `
            -RdlFolder $_.DirectoryName `
            -ReportName $_.BaseName `
            -WorkspaceName "Main" `
            -TargetSemanticModel "SM_Sales" `
            -OutputFolder "C:\Migration\Ready"
    }
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory, HelpMessage = "Folder containing .rdl files from Power BI Report Server")]
    [string] $RdlFolder,

    [Parameter(Mandatory, HelpMessage = "Report name without .rdl extension")]
    [string] $ReportName,

    [Parameter(Mandatory, HelpMessage = "Fabric workspace containing the target semantic model")]
    [string] $WorkspaceName,

    [Parameter(Mandatory, HelpMessage = "Display name of the Fabric semantic model")]
    [string] $TargetSemanticModel,

    [string] $OutputFolder
)

$ErrorActionPreference = "Stop"

# ============================================================================
# STEP 1: Locate and read the local .rdl file
# ============================================================================
# The .rdl is an XML file exported from Power BI Report Server. It contains
# <DataSource> elements with connection strings pointing to the on-prem data source.
$rdlFile = Join-Path $RdlFolder "$ReportName.rdl"
if (-not (Test-Path $rdlFile)) {
    throw "Report file not found: $rdlFile`nCheck that the .rdl file exists in '$RdlFolder'."
}

Write-Host "Reading local .rdl file..." -ForegroundColor Cyan
Write-Host "  Source: $rdlFile"
$rdlContent = [System.IO.File]::ReadAllText($rdlFile, [System.Text.Encoding]::UTF8)
$fileSize = (Get-Item $rdlFile).Length
Write-Host "  File size: $fileSize bytes"

# ============================================================================
# STEP 2: Parse existing data sources from the .rdl XML
# ============================================================================
# We need to find all <DataSource Name="..."> elements and their connection strings
# so we know what to replace. On-prem reports may use SQL Server, Oracle, OLEDB, etc.
Write-Host "`nParsing existing data sources..." -ForegroundColor Cyan
[xml]$rdlXml = $rdlContent
$ns = @{ 
    rd = "http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition"
    wa = "http://schemas.microsoft.com/sqlserver/reporting/webauthoring"
}

# Find all DataSource elements (there may be multiple in complex reports)
$dataSources = $rdlXml.Report.DataSources.DataSource
if (-not $dataSources) { throw "No <DataSource> elements found in the .rdl file." }

$dsCount = @($dataSources).Count
Write-Host "  Found $dsCount data source(s):"
foreach ($ds in @($dataSources)) {
    $dsName = $ds.Name
    $connStr = $ds.ConnectionProperties.ConnectString
    $provider = $ds.ConnectionProperties.DataProvider
    Write-Host "    [$dsName] Provider=$provider" -ForegroundColor Gray
    Write-Host "    Connection: $($connStr.Substring(0, [Math]::Min(100, $connStr.Length)))..." -ForegroundColor Gray
}

# ============================================================================
# STEP 3: Look up the target semantic model ID from Microsoft Fabric
# ============================================================================
# The Fabric PBIDATASET connection string needs the semantic model's internal GUID
# in the format: Initial Catalog=sobe_wowvirtualserver-{guid}
# We use the Power BI REST API to resolve the model name → GUID.
Write-Host "`nLooking up semantic model '$TargetSemanticModel' in Fabric workspace '$WorkspaceName'..." -ForegroundColor Cyan

$pbiToken = az account get-access-token --resource "https://analysis.windows.net/powerbi/api" --query accessToken -o tsv
if (-not $pbiToken) { throw "Failed to acquire Power BI token. Run 'az login' first." }
$ph = @{ Authorization = "Bearer $pbiToken" }

# Resolve workspace by name
$workspaces = (Invoke-RestMethod "https://api.powerbi.com/v1.0/myorg/groups" -Headers $ph).value
$ws = $workspaces | Where-Object { $_.name -eq $WorkspaceName }
if (-not $ws) { throw "Workspace '$WorkspaceName' not found. Check the name and your access permissions." }
$wsId = $ws.id
Write-Host "  Workspace ID: $wsId"

# Resolve semantic model by name → get its GUID
$datasets = (Invoke-RestMethod "https://api.powerbi.com/v1.0/myorg/groups/$wsId/datasets" -Headers $ph).value
$targetDs = $datasets | Where-Object { $_.name -eq $TargetSemanticModel }
if (-not $targetDs) {
    Write-Host "`n  Available semantic models in '$WorkspaceName':" -ForegroundColor Yellow
    $datasets | ForEach-Object { Write-Host "    - $($_.name) (id: $($_.id))" }
    throw "Semantic model '$TargetSemanticModel' not found in workspace '$WorkspaceName'."
}
$semanticModelId = $targetDs.id
Write-Host "  Semantic model ID: $semanticModelId" -ForegroundColor Green

# ============================================================================
# STEP 4: Build the new Fabric PBIDATASET connection string
# ============================================================================
# Fabric paginated reports connect to semantic models using the PBIDATASET provider
# with a specific connection string format. This replaces whatever on-prem provider
# (SQL Server, Oracle, etc.) was used in the original report.
$newConnectString = "Data Source=pbiazure://api.powerbi.com/;Identity Provider=`"https://login.microsoftonline.com/common, https://analysis.windows.net/powerbi/api, f0b72488-7082-488a-a7e8-eada97bd842d`";Initial Catalog=sobe_wowvirtualserver-$semanticModelId;Integrated Security=ClaimsToken"

Write-Host "`nNew connection string:" -ForegroundColor Cyan
Write-Host "  Provider: PBIDATASET"
Write-Host "  Catalog:  sobe_wowvirtualserver-$semanticModelId"

# ============================================================================
# STEP 5: Replace data source references in the .rdl content
# ============================================================================
# We perform text-based replacement (not XML manipulation) because .rdl files
# reference the data source name in many places:
#   - <DataSource Name="...">           (DataSources section)
#   - <DataSourceName>...</DataSourceName> (in DataSets, FilterSelections)
#   - <ConnectString>...</ConnectString>   (connection string)
#   - <DataProvider>...</DataProvider>     (provider type)
#
# The text approach ensures we catch all occurrences consistently.
Write-Host "`nReplacing data source references..." -ForegroundColor Cyan
$newContent = $rdlContent
$totalReplacements = 0

foreach ($ds in @($dataSources)) {
    $oldName = $ds.Name
    $oldConnStr = $ds.ConnectionProperties.ConnectString
    $oldProvider = $ds.ConnectionProperties.DataProvider

    # 5a. Replace data source NAME everywhere it appears
    #     This covers <DataSource Name="...">, <DataSourceName>...</DataSourceName>,
    #     and <wa:DataSourceName>...</wa:DataSourceName>
    $nameMatches = ([regex]::Matches($newContent, [regex]::Escape($oldName))).Count
    if ($nameMatches -gt 0) {
        $newContent = $newContent -replace [regex]::Escape($oldName), $TargetSemanticModel
        $totalReplacements += $nameMatches
        Write-Host "  Replaced data source name '$oldName' → '$TargetSemanticModel' ($nameMatches occurrences)"
    }

    # 5b. Replace the full CONNECTION STRING
    #     Swaps the entire on-prem connection string for the Fabric PBIDATASET one
    $connMatches = ([regex]::Matches($newContent, [regex]::Escape($oldConnStr))).Count
    if ($connMatches -gt 0) {
        $newContent = $newContent -replace [regex]::Escape($oldConnStr), $newConnectString
        $totalReplacements += $connMatches
        Write-Host "  Replaced connection string ($connMatches occurrences)"
    }

    # 5c. Replace the DATA PROVIDER (e.g. SQL → PBIDATASET)
    #     Only replace within <DataProvider> tags to avoid false positives
    if ($oldProvider -and $oldProvider -ne "PBIDATASET") {
        $providerPattern = "(<DataProvider>)$([regex]::Escape($oldProvider))(</DataProvider>)"
        $providerMatches = ([regex]::Matches($newContent, $providerPattern)).Count
        if ($providerMatches -gt 0) {
            $newContent = $newContent -replace $providerPattern, '${1}PBIDATASET${2}'
            $totalReplacements += $providerMatches
            Write-Host "  Replaced data provider '$oldProvider' → 'PBIDATASET' ($providerMatches occurrences)"
        }
    }
}

Write-Host "  Total replacements: $totalReplacements" -ForegroundColor Green

# ============================================================================
# STEP 6: Verify no old data source references remain
# ============================================================================
# Safety check: scan the modified content for any leftover old references.
# This catches edge cases where a data source name appeared in an unexpected location.
Write-Host "`nVerifying replacements..." -ForegroundColor Cyan
$issues = @()
foreach ($ds in @($dataSources)) {
    $oldName = $ds.Name
    if ($oldName -ne $TargetSemanticModel) {
        $leftover = ([regex]::Matches($newContent, [regex]::Escape($oldName))).Count
        if ($leftover -gt 0) { $issues += "  '$oldName' still appears $leftover time(s)" }
    }
}
if ($issues.Count -gt 0) {
    Write-Warning "Potential leftover references found:"
    $issues | ForEach-Object { Write-Warning $_ }
    Write-Warning "Manual inspection of the output file is recommended."
} else {
    Write-Host "  All old references replaced successfully." -ForegroundColor Green
}

# ============================================================================
# STEP 7: Save the modified .rdl to the output folder
# ============================================================================
# The output file is ready for import into Fabric using Import-PaginatedReport.ps1
if (-not $OutputFolder) { $OutputFolder = Join-Path $RdlFolder "modified" }
if (-not (Test-Path $OutputFolder)) {
    New-Item -ItemType Directory -Path $OutputFolder -Force | Out-Null
    Write-Host "`nCreated output folder: $OutputFolder"
}
$outputFile = Join-Path $OutputFolder "$ReportName.rdl"
[System.IO.File]::WriteAllText($outputFile, $newContent, [System.Text.Encoding]::UTF8)

Write-Host "`n$('=' * 60)" -ForegroundColor Green
Write-Host "DONE — Report repointed to Fabric semantic model" -ForegroundColor Green
Write-Host "$('=' * 60)" -ForegroundColor Green
Write-Host "  Source file       : $rdlFile"
Write-Host "  Output file       : $outputFile"
Write-Host "  Target model      : $TargetSemanticModel"
Write-Host "  Model ID          : $semanticModelId"
Write-Host "  Replacements      : $totalReplacements"
Write-Host ""
Write-Host "Next step — import into Fabric:" -ForegroundColor Yellow
Write-Host "  .\Import-PaginatedReport.ps1 -WorkspaceName '$WorkspaceName' -RdlFilePath '$outputFile' -ReportName '$ReportName'"
