# Direct Lake Semantic Model Creation via API

## Overview

This guide documents the **correct approach** for creating Direct Lake semantic models programmatically via the Fabric Items API, based on verified production implementations.

Direct Lake semantic models enable zero-copy, high-performance access to OneLake delta tables without importing data. However, API-based creation has specific requirements that differ from Import or DirectQuery models.

---

## Critical Requirements

### 1. Use TMSL Format (model.bim), Not TMDL

**BLOCKING**: The Fabric Items API `/v1/workspaces/{id}/semanticModels` endpoint requires:
- `model.bim` (TMSL/JSON format) as the primary definition file
- `definition.pbism` as the metadata file

**It does NOT accept:**
- TMDL files (database.tmdl, model.tmdl, table/*.tmdl)
- Other formats like pbix or pbit

**Error if TMDL is used:**
```json
{
  "errorCode": "Workload_FailedToParseFile",
  "message": "Cannot read 'model.bim'. Missing required artifact 'model.bim'."
}
```

### 2. Use AzureStorage.DataLake M Expression for OneLake Connection

Direct Lake models **must not** use SQL/TDS data sources. Instead, they require an M expression that connects to OneLake using the `AzureStorage.DataLake` connector.

**❌ WRONG** — SQL TDS data source (causes validation error):
```json
{
  "dataSources": [
    {
      "type": "structured",
      "name": "EntityDataSource",
      "connectionDetails": {
        "protocol": "tds",
        "address": {
          "server": "lakehouse-sql-endpoint.datawarehouse.fabric.microsoft.com",
          "database": "LakehouseName"
        }
      }
    }
  ]
}
```

**✅ CORRECT** — M expression for OneLake:
```json
{
  "expressions": [
    {
      "name": "DirectLakeSource",
      "kind": "m",
      "expression": "let\\n    Source = AzureStorage.DataLake(\\\"https://onelake.dfs.fabric.microsoft.com/{workspaceId}/{lakehouseId}\\\", [HierarchicalNavigation=true])\\nin\\n    Source"
    }
  ]
}
```

### 3. Partition Source Must Reference the M Expression

Each Direct Lake table partition must:
- Use `mode: "directLake"`
- Have `source.type: "entity"`
- Reference the M expression name in `expressionSource`

**✅ CORRECT** partition structure:
```json
{
  "partitions": [
    {
      "name": "customers",
      "mode": "directLake",
      "source": {
        "type": "entity",
        "entityName": "customers",
        "expressionSource": "DirectLakeSource"
      }
    }
  ]
}
```

**❌ WRONG** — Using non-existent expression source:
```json
{
  "source": {
    "type": "entity",
    "entityName": "customers",
    "expressionSource": "DatabaseQuery"  // ← This expression doesn't exist!
  }
}
```

**Error if expression source is incorrect:**
```json
{
  "errorCode": "Dataset_Import_FailedToImportDataset",
  "message": "Direct Lake mode requires a Direct Lake data source. Tables in Direct Lake mode must be the SQL or OneLake datasource kind."
}
```

### 4. Minimal definition.pbism Structure

The `definition.pbism` file must have a minimal schema:

**✅ CORRECT:**
```json
{
  "version": "1.0"
}
```

**❌ WRONG** — Including artifacts array (causes schema validation error):
```json
{
  "version": "1.0",
  "artifacts": [
    {
      "name": "model.bim"
    }
  ]
}
```

**Error if artifacts are included:**
```json
{
  "errorCode": "Workload_FailedToParseFile",
  "message": "Property 'artifacts' has not been defined and the schema does not allow additional properties."
}
```

---

## Complete Working Example

### OneLake Path Structure

Given:
- Workspace ID: `00000000-0000-0000-0000-000000000000`
- Lakehouse ID: `00000000-0000-0000-0000-000000000000`
- Lakehouse Name: `ClaimData`
- Delta tables: `customers`, `policies`, `claims`

OneLake path:
```
https://onelake.dfs.fabric.microsoft.com/00000000-0000-0000-0000-000000000000/00000000-0000-0000-0000-000000000000
```

### model.bim Structure (Minimal)

```json
{
  "name": "InsuranceClaimsModel",
  "compatibilityLevel": 1604,
  "model": {
    "culture": "en-US",
    "defaultMode": "directLake",
    "dataAccessOptions": {
      "legacyRedirects": true,
      "returnErrorValuesAsNull": true
    },
    "defaultPowerBIDataSourceVersion": "powerBI_V3",
    "sourceQueryCulture": "en-US",
    "tables": [
      {
        "name": "customers",
        "columns": [
          {
            "name": "customer_id",
            "dataType": "int64",
            "sourceColumn": "customer_id"
          },
          {
            "name": "customer_name",
            "dataType": "string",
            "sourceColumn": "customer_name"
          }
        ],
        "partitions": [
          {
            "name": "customers",
            "mode": "directLake",
            "source": {
              "type": "entity",
              "entityName": "customers",
              "expressionSource": "DirectLakeSource"
            }
          }
        ]
      },
      {
        "name": "policies",
        "columns": [
          {
            "name": "policy_id",
            "dataType": "int64",
            "sourceColumn": "policy_id"
          },
          {
            "name": "customer_id",
            "dataType": "int64",
            "sourceColumn": "customer_id"
          }
        ],
        "partitions": [
          {
            "name": "policies",
            "mode": "directLake",
            "source": {
              "type": "entity",
              "entityName": "policies",
              "expressionSource": "DirectLakeSource"
            }
          }
        ]
      }
    ],
    "relationships": [
      {
        "name": "customers_to_policies",
        "fromTable": "customers",
        "fromColumn": "customer_id",
        "toTable": "policies",
        "toColumn": "customer_id",
        "crossFilteringBehavior": "oneDirection"
      }
    ],
    "expressions": [
      {
        "name": "DirectLakeSource",
        "kind": "m",
        "expression": "let\\n    Source = AzureStorage.DataLake(\\\"https://onelake.dfs.fabric.microsoft.com/00000000-0000-0000-0000-000000000000/00000000-0000-0000-0000-000000000000\\\", [HierarchicalNavigation=true])\\nin\\n    Source"
      }
    ]
  }
}
```

### definition.pbism

```json
{
  "version": "1.0"
}
```

### Deployment Script (PowerShell)

```powershell
# Variables
$workspaceId = "00000000-0000-0000-0000-000000000000"
$modelName = "InsuranceClaimsModel"

# Get access token
$token = (az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv)

# Read and encode files
$modelBim = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content -Raw "model.bim")))
$pbism = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes((Get-Content -Raw "definition.pbism")))

# Build request body
$body = @{
  displayName = $modelName
  definition = @{
    parts = @(
      @{
        path = "model.bim"
        payload = $modelBim
        payloadType = "InlineBase64"
      },
      @{
        path = "definition.pbism"
        payload = $pbism
        payloadType = "InlineBase64"
      }
    )
  }
} | ConvertTo-Json -Depth 10

# Deploy
$response = Invoke-WebRequest -Method Post `
  -Uri "https://api.fabric.microsoft.com/v1/workspaces/$workspaceId/semanticModels" `
  -Headers @{Authorization="Bearer $token"} `
  -Body $body `
  -ContentType "application/json"

# Get operation URL from Location header
$operationUrl = $response.Headers['Location'][0]
Write-Host "Operation URL: $operationUrl"

# Poll operation status
$token2 = (az account get-access-token --resource "https://analysis.windows.net/powerbi/api" --query accessToken -o tsv)
do {
  Start-Sleep -Seconds 5
  $op = Invoke-RestMethod -Method Get -Uri $operationUrl -Headers @{Authorization="Bearer $token2"}
  Write-Host "Status: $($op.status)"
} while ($op.status -eq "Running" -or $op.status -eq "NotStarted")

if ($op.status -eq "Succeeded") {
  Write-Host "SUCCESS! Semantic model created."
  if ($op.resourceId) {
    Write-Host "Resource ID: $($op.resourceId)"
  }
} else {
  Write-Host "FAILED!"
  Write-Host "Error Code: $($op.error.errorCode)"
  Write-Host "Error Message: $($op.error.message)"
}
```

---

## Common Errors and Solutions

| Error Code | Message Snippet | Root Cause | Solution |
|---|---|---|---|
| `Workload_FailedToParseFile` | "Missing required artifact 'model.bim'" | Using TMDL instead of TMSL | Convert to model.bim format |
| `Dataset_Import_FailedToImportDataset` | "Direct Lake mode requires a Direct Lake data source" | Using SQL TDS data source or wrong expression | Use AzureStorage.DataLake M expression |
| `Dataset_Import_FailedToImportDataset` | "Tables...must be the SQL or OneLake datasource kind" | Partition expressionSource references non-existent expression | Ensure expressionSource matches expression name |
| `Workload_FailedToParseFile` | "Property 'artifacts' has not been defined" | definition.pbism has invalid schema | Use minimal schema: `{"version": "1.0"}` |

---

## Verified Workflow: End-to-End

1. **Identify lakehouse details**
   - Get workspace ID and lakehouse ID
   - Construct OneLake path: `https://onelake.dfs.fabric.microsoft.com/{workspaceId}/{lakehouseId}`

2. **Inspect delta table schemas**
   - Query lakehouse tables to get column names and data types
   - Map Spark types to TMSL data types (int64, string, dateTime, decimal, boolean, int32)

3. **Create model.bim**
   - Set `compatibilityLevel: 1604` (or higher)
   - Set `defaultMode: "directLake"`
   - Add M expression with `AzureStorage.DataLake` connector
   - Add tables with columns mapping to delta table columns
   - Add partitions with `mode: "directLake"` and `expressionSource` referencing M expression
   - Add relationships between tables
   - Add DAX measures in a `_Measures` table (optional)

4. **Create definition.pbism**
   - Minimal schema: `{"version": "1.0"}`

5. **Deploy via REST API**
   - POST to `/v1/workspaces/{id}/semanticModels`
   - Include both files as base64-encoded parts
   - Capture operation URL from Location header

6. **Poll operation status**
   - Use Power BI API token audience (`https://analysis.windows.net/powerbi/api`)
   - Poll operation URL until status is `Succeeded` or `Failed`
   - If `Failed`, analyze error.errorCode and error.message

7. **Verify deployment**
   - List workspace items to confirm SemanticModel exists
   - Optional: Query semantic model metadata via Power BI API

---

## Best Practices

✅ **DO:**
- Always use `AzureStorage.DataLake` M expression for Direct Lake OneLake connection
- Map delta table column names exactly to semantic model column `sourceColumn` properties
- Use compatibility level 1604 or higher for Direct Lake support
- Include `defaultMode: "directLake"` at model level
- Reference the M expression name in partition `expressionSource`
- Use minimal `definition.pbism` schema
- Poll operation status with Power BI API token (different audience than Fabric API)
- Verify lakehouse tables exist and are accessible before referencing in model

❌ **DON'T:**
- Use SQL TDS data sources for Direct Lake models
- Include `dataSources` array with TDS protocol
- Use TMDL files for initial creation (convert to TMSL first)
- Include `artifacts` array in definition.pbism
- Reference non-existent expression names in partition sources
- Skip operation polling — deployment is async and may fail silently

---

## References

- [ITEM-DEFINITIONS-CORE.md § SemanticModel](../../common/ITEM-DEFINITIONS-CORE.md#semanticmodel)
- [tmdl-authoring-guide.md § Direct Lake Guidelines](./tmdl-authoring-guide.md#direct-lake-guidelines)
- External: [powerbi_agentic_plugins/plugins/powerbi/skills/powerbi-semantic-model/references/direct-lake-guidelines.md](https://github.com/example/powerbi_agentic_plugins)

---

## Document History

- **2026-04-10**: Initial version documenting verified Direct Lake semantic model creation workflow via Fabric Items API, including OneLake M expression requirement and common pitfalls
