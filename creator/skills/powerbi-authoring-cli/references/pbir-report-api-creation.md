# PBIR Report Creation via API

## Overview

This guide documents how to create Power BI reports programmatically using the PBIR (Power BI Report) JSON format via the Fabric Items API. PBIR is the modern, text-based report format that enables version control and API-based deployments.

---

## PBIR File Structure

A PBIR report consists of multiple JSON files organized in a specific folder structure:

```
ReportName.Report/
├── definition.pbir              # Report metadata and semantic model reference
├── definition/
│   ├── report.json             # Report-level settings
│   ├── version.json            # Schema version
│   └── pages/
│       ├── pages.json          # Page index
│       └── pageName/
│           ├── page.json       # Page settings
│           └── visuals/
│               └── visualName/
│                   └── visual.json  # Visual definition with queries
└── StaticResources/
    └── RegisteredResources/
        └── theme.json          # Custom theme (optional but often required)
```

---

## Critical Requirements

### 1. definition.pbir Structure

The root definition file connects the report to a semantic model.

**For workspace deployment (byConnection):**
```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
  "version": "4.0",
  "datasetReference": {
    "byConnection": {
      "connectionString": "semanticmodelid=SEMANTIC_MODEL_ID"
    }
  }
}
```

**For local development (byPath):**
```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
  "version": "4.0",
  "datasetReference": {
    "byPath": {
      "path": "../SemanticModelName.SemanticModel"
    }
  }
}
```

### 2. Visual Query Structure

Each visual references fields from the semantic model using Entity (table) and Property (column/measure):

**Measure reference:**
```json
{
  "field": {
    "Measure": {
      "Expression": {
        "SourceRef": {
          "Entity": "_Measures"
        }
      },
      "Property": "Total Sales"
    }
  },
  "queryRef": "_Measures.Total Sales",
  "nativeQueryRef": "Total Sales"
}
```

**Column reference:**
```json
{
  "field": {
    "Column": {
      "Expression": {
        "SourceRef": {
          "Entity": "customers"
        }
      },
      "Property": "customer_name"
    }
  },
  "queryRef": "customers.customer_name",
  "nativeQueryRef": "customer_name",
  "active": true
}
```

### 3. Required Files for Deployment

**Minimum required files:**
- `definition.pbir`
- `definition/report.json`
- `definition/version.json`
- `definition/pages/pages.json`
- `definition/pages/{pageName}/page.json`
- At least one `definition/pages/{pageName}/visuals/{visualName}/visual.json`

**Often required (even if empty):**
- `StaticResources/RegisteredResources/theme.json`

**Missing theme.json error:**
If deployment fails with "The following file was not found: 'StaticResources/RegisteredResources/theme.json'", include an empty theme:
```json
{
  "name": "DefaultTheme",
  "dataColors": []
}
```

---

## Visual Types and Query Patterns

### Card Visual (KPI Cards)

**Visual type:** `cardVisual`

**Query structure for multi-card:**
```json
{
  "visualType": "cardVisual",
  "query": {
    "queryState": {
      "Data": {
        "projections": [
          {
            "field": {
              "Measure": {
                "Expression": {
                  "SourceRef": { "Entity": "_Measures" }
                },
                "Property": "Total Sales"
              }
            },
            "queryRef": "_Measures.Total Sales",
            "nativeQueryRef": "Total Sales"
          },
          {
            "field": {
              "Measure": {
                "Expression": {
                  "SourceRef": { "Entity": "_Measures" }
                },
                "Property": "Total Customers"
              }
            },
            "queryRef": "_Measures.Total Customers",
            "nativeQueryRef": "Total Customers"
          }
        ]
      }
    }
  }
}
```

### Slicer (Date/Category Filter)

**Visual type:** `slicer`

**Query structure:**
```json
{
  "visualType": "slicer",
  "query": {
    "queryState": {
      "Values": {
        "projections": [
          {
            "field": {
              "Column": {
                "Expression": {
                  "SourceRef": { "Entity": "dates" }
                },
                "Property": "date"
              }
            },
            "queryRef": "dates.date",
            "nativeQueryRef": "date",
            "active": true
          }
        ]
      }
    }
  }
}
```

### Bar Chart

**Visual type:** `barChart`

**Query structure:**
```json
{
  "visualType": "barChart",
  "query": {
    "queryState": {
      "Category": {
        "projections": [
          {
            "field": {
              "Column": {
                "Expression": {
                  "SourceRef": { "Entity": "products" }
                },
                "Property": "category"
              }
            },
            "queryRef": "products.category",
            "nativeQueryRef": "category",
            "active": true
          }
        ]
      },
      "Y": {
        "projections": [
          {
            "field": {
              "Measure": {
                "Expression": {
                  "SourceRef": { "Entity": "_Measures" }
                },
                "Property": "Total Sales"
              }
            },
            "queryRef": "_Measures.Total Sales",
            "nativeQueryRef": "Total Sales"
          }
        ]
      }
    }
  }
}
```

### Area Chart / Line Chart (Time Series)

**Visual type:** `areaChart` or `lineChart`

**Query structure:**
```json
{
  "visualType": "areaChart",
  "query": {
    "queryState": {
      "Category": {
        "projections": [
          {
            "field": {
              "Column": {
                "Expression": {
                  "SourceRef": { "Entity": "dates" }
                },
                "Property": "date"
              }
            },
            "queryRef": "dates.date",
            "nativeQueryRef": "date",
            "active": true
          }
        ]
      },
      "Y": {
        "projections": [
          {
            "field": {
              "Measure": {
                "Expression": {
                  "SourceRef": { "Entity": "_Measures" }
                },
                "Property": "Total Sales"
              }
            },
            "queryRef": "_Measures.Total Sales",
            "nativeQueryRef": "Total Sales"
          }
        ]
      }
    }
  }
}
```

---

## Deployment via Fabric Items API

### PowerShell Deployment Script

```powershell
# Variables
$workspaceId = "YOUR_WORKSPACE_ID"
$reportName = "MyReport"
$reportPath = "C:\path\to\ReportName.Report"

# Get token
$token = (az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv)

# Read and encode all required files
$pbir = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content -Raw "$reportPath\definition.pbir")))
$reportJson = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content -Raw "$reportPath\definition\report.json")))
$versionJson = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content -Raw "$reportPath\definition\version.json")))
$pagesJson = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content -Raw "$reportPath\definition\pages\pages.json")))
$pageJson = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content -Raw "$reportPath\definition\pages\mainPage\page.json")))
$themeJson = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content -Raw "$reportPath\StaticResources\RegisteredResources\theme.json")))

# Read visual files
$visual1 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content -Raw "$reportPath\definition\pages\mainPage\visuals\visual1\visual.json")))

# Build request body
$bodyObj = @{
  displayName = $reportName
  type = "Report"
  definition = @{
    parts = @(
      @{ path = "definition.pbir"; payload = $pbir; payloadType = "InlineBase64" },
      @{ path = "definition/report.json"; payload = $reportJson; payloadType = "InlineBase64" },
      @{ path = "definition/version.json"; payload = $versionJson; payloadType = "InlineBase64" },
      @{ path = "definition/pages/pages.json"; payload = $pagesJson; payloadType = "InlineBase64" },
      @{ path = "definition/pages/mainPage/page.json"; payload = $pageJson; payloadType = "InlineBase64" },
      @{ path = "definition/pages/mainPage/visuals/visual1/visual.json"; payload = $visual1; payloadType = "InlineBase64" },
      @{ path = "StaticResources/RegisteredResources/theme.json"; payload = $themeJson; payloadType = "InlineBase64" }
    )
  }
}

$bodyJson = $bodyObj | ConvertTo-Json -Depth 20

# Deploy
$response = Invoke-WebRequest -Method Post `
  -Uri "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/items" `
  -Headers @{Authorization="Bearer $token"} `
  -Body $bodyJson `
  -ContentType "application/json"

# Poll operation
if ($response.Headers.ContainsKey('Location')) {
  $opUrl = $response.Headers['Location'][0]
  $token2 = (az account get-access-token --resource "https://analysis.windows.net/powerbi/api" --query accessToken -o tsv)
  
  do {
    Start-Sleep -Seconds 5
    $op = Invoke-RestMethod -Method Get -Uri $opUrl -Headers @{Authorization="Bearer $token2"}
    Write-Host "Status: $($op.status)"
  } while ($op.status -eq "Running" -or $op.status -eq "NotStarted")
  
  if ($op.status -eq "Succeeded") {
    Write-Host "SUCCESS! Report ID: $($op.resourceId)"
  } else {
    Write-Host "FAILED: $($op.error.errorCode) - $($op.error.message)"
  }
}
```

---

## Template Report Adaptation Pattern

### Step-by-Step Workflow

1. **Copy template report structure**
   - Source: Template PBIR folder with pre-configured visuals
   - Destination: New report folder

2. **Update definition.pbir**
   - Change `byPath` to `byConnection` for workspace deployment
   - Set `semanticmodelid` to target semantic model ID

3. **Adapt visuals to semantic model**
   - **Title visual:** Update textbox value with report title
   - **KPI cards:** Replace measures in `Data.projections`
   - **Slicers:** Update `Values.projections` with filter columns
   - **Charts:** Update `Category` with dimension columns, `Y` with measures

4. **Verify field references**
   - All `Entity` values must match semantic model table names (case-sensitive)
   - All `Property` values must match column/measure names (case-sensitive)
   - `queryRef` follows pattern: `Entity.Property`
   - `nativeQueryRef` is just the `Property` name

5. **Include required static resources**
   - Always include `theme.json` even if using default theme
   - Include any custom images or resources referenced by visuals

6. **Deploy and verify**
   - Use Fabric Items API with all required parts
   - Poll operation until `Succeeded` or `Failed`
   - Verify report opens in workspace

---

## Common Errors and Solutions

| Error Code | Message Snippet | Root Cause | Solution |
|---|---|---|---|
| `Workload_MissingFileFromDefinition` | "The following file was not found: 'StaticResources/RegisteredResources/theme.json'" | Missing theme file in deployment payload | Include theme.json in parts array |
| `Workload_InvalidFieldReference` | "Field 'Entity.Property' does not exist" | Entity or Property name doesn't match semantic model | Verify table/column names are exact matches (case-sensitive) |
| `Workload_InvalidSemanticModelReference` | "Semantic model not found" | Wrong semantic model ID in definition.pbir | Get correct semantic model ID from workspace |
| `Workload_InvalidSchemaVersion` | "Schema version not supported" | Wrong $schema URL in visual.json | Use correct schema from template |

---

## Best Practices

✅ **DO:**
- Always use `byConnection` with semantic model ID for workspace deployments
- Include all visual files referenced in the report (don't skip logo, decorations, etc.)
- Base64-encode all file content before adding to payload
- Poll operation status with Power BI API token (different audience than Fabric token)
- Use template reports as starting points for consistent layouts
- Verify semantic model field names before deployment (case-sensitive)

❌ **DON'T:**
- Use `byPath` when deploying to workspace (only for local PBIP development)
- Skip theme.json — include it even if empty
- Hardcode visual queries — adapt to actual semantic model structure
- Mix up Entity (table) and Property (column/measure) references
- Forget to include page.json files for each page

---

## References

- [ITEM-DEFINITIONS-CORE.md § Report](../../common/ITEM-DEFINITIONS-CORE.md#report)
- External: [PBIR Format Documentation](https://learn.microsoft.com/power-bi/developer/projects/projects-report)
- Template: Use pre-built template reports from proven implementations

---

## Document History

- **2026-04-30**: Added "Updating Existing Reports" section for measure renames and visual field patching via `getDefinition`/`updateDefinition`
- **2026-04-10**: Initial version documenting verified PBIR report creation workflow via Fabric Items API, based on insurance demo implementation

---

## Updating Existing Reports (Measure/Field Rename)

When a semantic model measure or column is renamed, bound reports must be updated to reference the new name. This is done via the Fabric Items API `getDefinition` → modify → `updateDefinition` cycle.

### Workflow

1. **Fetch report definition** — POST `getDefinition` with `?type=PBIR`
2. **Decode `report.json`** — this file contains ALL visual field references
3. **Find-and-replace** the old measure/column name in the decoded content
4. **Re-encode and POST** all parts back via `updateDefinition`

### Where Measure Names Appear in report.json

Each visual references fields via multiple properties. A single measure may appear in **multiple locations**:

| Property | Format | Example |
|---|---|---|
| `Property` (inside field object) | Bare name | `"Property": "Total Sales"` |
| `queryRef` | `TableName.MeasureName` | `"queryRef": "Customer.Total Sales"` |
| `nativeQueryRef` | Bare name | `"nativeQueryRef": "Total Sales"` |

When renaming a measure, **all three** must be updated in every visual that references it.

### Python Example

```python
import requests, base64, json, time

WS_ID = "your-workspace-id"
RPT_ID = "your-report-id"
OLD_NAME = "Sum of L_EXTENDEDPRICE % difference from EUROPE"
NEW_NAME = "ExtPrice_PctDiff_vs_Europe"

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# 1. Get report definition (follows LRO if 202)
r = requests.post(
    f"https://api.fabric.microsoft.com/v1/workspaces/{WS_ID}/items/{RPT_ID}/getDefinition?type=PBIR",
    headers=headers
)
# ... poll LRO if 202 ...
parts = response_json["definition"]["parts"]

# 2. Find and replace in all parts
updated_parts = []
for p in parts:
    decoded = base64.b64decode(p["payload"]).decode("utf-8")
    if OLD_NAME in decoded:
        decoded = decoded.replace(OLD_NAME, NEW_NAME)
    updated_parts.append({
        "path": p["path"],
        "payload": base64.b64encode(decoded.encode("utf-8")).decode("ascii"),
        "payloadType": "InlineBase64"
    })

# 3. Push update (include ALL parts)
requests.post(
    f"https://api.fabric.microsoft.com/v1/workspaces/{WS_ID}/items/{RPT_ID}/updateDefinition",
    headers=headers,
    json={"definition": {"parts": updated_parts}}
)
```

### Key Rules for Report Updates

- **Include ALL parts** in `updateDefinition` — modified and unmodified. Omitting parts deletes them.
- **Do NOT include `.platform`** in the parts array — it causes errors.
- **String replacement is safe** for measure/column renames — the names appear as plain text in JSON.
- **Case-sensitive** — `queryRef`, `Property`, and `nativeQueryRef` values must match exactly.
- **Multiple visuals** may reference the same measure — always do a global replace across the full report.json content.
- **`getDefinition` for reports** requires `?type=PBIR` query parameter.
- **Token audience** for both get/update is Fabric API: `https://api.fabric.microsoft.com`

### Rebinding a Report to a Different Semantic Model

To point a report at a new/consolidated semantic model, update `definition.pbir`:

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
  "version": "4.0",
  "datasetReference": {
    "byConnection": {
      "connectionString": "semanticmodelid=NEW_SEMANTIC_MODEL_ID"
    }
  }
}
```

After rebinding, verify all `Entity` and `Property` references in `report.json` still match the new semantic model's table and measure names. If table/measure names differ between old and new SM, update `report.json` accordingly.
