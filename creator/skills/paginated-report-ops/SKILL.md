---
name: paginated-report-ops
description: >
  Export, modify, and re-import Fabric Paginated Reports (.rdl) via REST APIs.
  Covers data source rebinding, renaming, folder placement, and known platform limitations.
  Use when the user wants to: (1) export a paginated report .rdl from Fabric,
  (2) change the data source / semantic model of a paginated report,
  (3) import a modified .rdl back into a Fabric workspace,
  (4) move paginated reports between workspace folders.
  Triggers: "paginated report", "rdl file", "change data source", "rebind paginated",
  "export report", "import rdl", "move report to folder".
---

# Paginated Report Operations — Skill

## Quick Reference

| Operation | API | Key Notes |
|---|---|---|
| Export .rdl | PBI `GET /groups/{wsId}/reports/{id}/Export` | Returns raw .rdl bytes |
| Import .rdl | PBI `POST /groups/{wsId}/imports?datasetDisplayName={name}.rdl` | **Must include `.rdl` extension** in displayName |
| Move to folder | Fabric `POST /workspaces/{wsId}/items/{id}/move` | Use `targetFolderId` in body |
| List folders | Fabric `GET /workspaces/{wsId}/folders` | Folders are NOT in generic items list |
| List folder items | Fabric `GET /workspaces/{wsId}/items?rootFolderId={fId}` | Filter items by folder |
| Get datasources | PBI `GET /groups/{wsId}/reports/{id}/datasources` | Inspect current bindings |
| Delete report | PBI `DELETE /groups/{wsId}/reports/{id}` | Clean up before re-import |
| Clone report | PBI `POST /groups/{wsId}/reports/{id}/Clone` | Server-side copy (no .rdl upload) |

## Workflow: Change Data Source of a Paginated Report

### Step 1 — Export the .rdl

```powershell
$pbiToken = (az account get-access-token --resource "https://analysis.windows.net/powerbi/api" --query accessToken -o tsv)
Invoke-RestMethod "https://api.powerbi.com/v1.0/myorg/groups/$wsId/reports/$reportId/Export" `
  -Headers @{ Authorization = "Bearer $pbiToken" } `
  -OutFile "report.rdl"
```

### Step 2 — Modify the .rdl XML

The .rdl is standard XML. Data source references appear in these locations:

| Line Pattern | Element | What to Change |
|---|---|---|
| `<wa:DataSourceName>` | Filter selections | Semantic model display name |
| `<DataSource Name="">` | DataSources section | Semantic model display name |
| `<ConnectString>...Initial Catalog=sobe_wowvirtualserver-{guid}...` | Connection string | Semantic model internal ID (GUID) |
| `<DataSourceName>` inside `<Query>` | Dataset queries | Semantic model display name |

**All** occurrences must be updated consistently. The `Initial Catalog` GUID format is:
```
sobe_wowvirtualserver-{semantic-model-id}
```

### Step 3 — Import the modified .rdl

```powershell
# CRITICAL: datasetDisplayName MUST include .rdl extension
$url = "https://api.powerbi.com/v1.0/myorg/groups/$wsId/imports?datasetDisplayName=ReportName.rdl&nameConflict=Abort"

# Use System.Net.Http.HttpClient for proper multipart encoding
Add-Type -AssemblyName System.Net.Http
$httpClient = [System.Net.Http.HttpClient]::new()
$httpClient.DefaultRequestHeaders.Authorization = [System.Net.Http.Headers.AuthenticationHeaderValue]::new("Bearer", $pbiToken)
$content = [System.Net.Http.MultipartFormDataContent]::new()
$fileContent = [System.Net.Http.ByteArrayContent]::new([System.IO.File]::ReadAllBytes($rdlPath))
$fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::new("application/octet-stream")
$content.Add($fileContent, "file", "ReportName.rdl")
$response = $httpClient.PostAsync($url, $content).Result
```

### Step 4 — Move to folder (optional)

```powershell
$fabricToken = (az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv)
$body = @{ targetFolderId = $folderId } | ConvertTo-Json
Invoke-RestMethod "https://api.fabric.microsoft.com/v1/workspaces/$wsId/items/$reportId/move" `
  -Method POST -Headers @{ Authorization = "Bearer $fabricToken"; "Content-Type" = "application/json" } `
  -Body $body
```

## Import API Details

| Parameter | Required | Notes |
|---|---|---|
| `datasetDisplayName` | Yes | **Must end in `.rdl`** — this is how the API identifies paginated report uploads |
| `nameConflict` | Recommended | `Abort` or `Overwrite` only for RDL files |
| `subfolderObjectId` | Optional | Import directly into a workspace folder |
| Content-Type | Yes | `multipart/form-data` with file as form data |

## Token Audiences

| API | Resource / Audience |
|---|---|
| Power BI REST API | `https://analysis.windows.net/powerbi/api` |
| Fabric REST API | `https://api.fabric.microsoft.com` |

Use PBI tokens for report CRUD; Fabric tokens for workspace/folder/item operations.

## Known Platform Limitations (as of April 2026)

| Operation | Status | Error |
|---|---|---|
| `Rebind` API | **Not supported** for paginated reports | `PowerBIOperationNotSupported` |
| `Clone` with `targetModelId` | **Not supported** for RDL reports | `InvalidRequest` |
| `UpdateDatasources` API | **Selector never matches** for PBIDATASET sources | `ItemNotFound` — datasource selector doesn't work with PBIDATASET provider |
| `updateDefinition` (Fabric) | **Not supported** for PaginatedReport items | `OperationNotSupportedForItem` |
| `SetAllConnections` API | **Endpoint doesn't exist** for paginated reports | 404 |
| Import via `Invoke-RestMethod` | **Unreliable** multipart encoding | Use `System.Net.Http.HttpClient` instead |

### Workaround for Data Source Change

Since no server-side rebind API works, the only reliable approach is:
1. **Export** the .rdl
2. **Modify** the XML (data source name + Initial Catalog GUID)
3. **Delete** the old report (if overwriting)
4. **Import** the modified .rdl via multipart POST with `.rdl` in displayName

## Finding Semantic Model IDs

To get the internal ID for the `Initial Catalog` connection string:

```powershell
# List all semantic models in workspace
$datasets = Invoke-RestMethod "https://api.powerbi.com/v1.0/myorg/groups/$wsId/datasets" `
  -Headers @{ Authorization = "Bearer $pbiToken" }
$datasets.value | Where-Object { $_.name -eq "YourModelName" } | Select-Object name, id
# Use the id in: sobe_wowvirtualserver-{id}
```

## Scripts

Two production-ready scripts are available in `creator/skills/paginated-report-ops/scripts/`:

| Script | Purpose |
|---|---|
| `Replace-PaginatedReportDataSource.ps1` | Export → modify .rdl → save locally |
| `Import-PaginatedReport.ps1` | Import .rdl into Fabric workspace with optional folder placement |
