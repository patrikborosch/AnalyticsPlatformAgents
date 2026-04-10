# Notebook Execution Troubleshooting

## Common Execution Failures and Resolutions

This guide documents real-world notebook execution failures and their verified solutions.

---

## Issue 1: Missing Kernel Info and Kernelspec

### Symptoms
- Notebook creation via API succeeds
- Job submission returns `202 Accepted` and operation ID
- Job status immediately shows `Failed`
- No detailed error message in job response
- Notebook appears valid when viewed in portal but won't execute

### Root Cause
The notebook metadata is missing required kernel configuration fields:
- `kernel_info` object
- `kernelspec` object with proper Fabric kernel identifiers

These fields are automatically added when notebooks are created through the Fabric UI, but API-created notebooks require explicit metadata.

### Verification
Retrieve the notebook definition and check for these metadata fields:

```json
{
  "metadata": {
    "kernel_info": {
      "name": "synapse_pyspark"
    },
    "kernelspec": {
      "name": "synapse_pyspark",
      "display_name": "Synapse PySpark"
    }
  }
}
```

If these are missing, the notebook will fail to execute.

### Solution: Add Required Kernel Metadata

**Option 1: Update via updateDefinition API**

1. Get current notebook definition
2. Add kernel metadata to the `.ipynb` JSON structure
3. Re-encode and upload via `updateDefinition`

Required metadata addition:
```json
{
  "metadata": {
    "kernel_info": {
      "name": "synapse_pyspark"
    },
    "kernelspec": {
      "name": "synapse_pyspark",
      "display_name": "Synapse PySpark"
    },
    "dependencies": {
      "lakehouse": {
        "default_lakehouse": "<LAKEHOUSE_ID>",
        "default_lakehouse_name": "<LAKEHOUSE_NAME>",
        "default_lakehouse_workspace_id": "<WORKSPACE_ID>"
      }
    }
  }
}
```

**Option 2: Include in Initial Notebook Creation**

When creating notebooks via API, always include the kernel metadata from the start:

```bash
# Create notebook with proper metadata
NOTEBOOK_CONTENT=$(cat <<'EOF'
{
  "nbformat": 4,
  "nbformat_minor": 5,
  "metadata": {
    "kernel_info": {
      "name": "synapse_pyspark"
    },
    "kernelspec": {
      "name": "synapse_pyspark",
      "display_name": "Synapse PySpark"
    },
    "dependencies": {
      "lakehouse": {
        "default_lakehouse": "YOUR_LAKEHOUSE_ID",
        "default_lakehouse_name": "YOUR_LAKEHOUSE_NAME",
        "default_lakehouse_workspace_id": "YOUR_WORKSPACE_ID"
      }
    }
  },
  "cells": [
    {
      "cell_type": "code",
      "metadata": {},
      "source": ["print('Hello World')\\n"],
      "outputs": [],
      "execution_count": null
    }
  ]
}
EOF
)

ENCODED=$(echo "$NOTEBOOK_CONTENT" | base64 -w 0)

# Include in item creation payload
az rest --method post \
  --url "https://api.fabric.microsoft.com/v1/workspaces/$WORKSPACE_ID/items" \
  --resource "https://api.fabric.microsoft.com" \
  --headers "Content-Type=application/json" \
  --body "{
    \"displayName\": \"MyNotebook\",
    \"type\": \"Notebook\",
    \"definition\": {
      \"parts\": [
        {
          \"path\": \"notebook-content.py\",
          \"payload\": \"$ENCODED\",
          \"payloadType\": \"InlineBase64\"
        }
      ]
    }
  }"
```

### Verification After Fix

1. **Update the notebook** with kernel metadata
2. **Wait 2-3 seconds** for definition to propagate
3. **Submit a new job** (do NOT retry the failed job ID)
4. **Monitor job status** — should show `Running` then `Completed`

### Best Practices

✅ **DO:**
- Always include `kernel_info` and `kernelspec` in notebook metadata
- Include lakehouse binding in `dependencies.lakehouse` if accessing lakehouse data
- Use standard Fabric kernel names: `synapse_pyspark`, `synapse_spark`, `synapse_sparkr`, `synapse_sql`
- Verify notebook structure with a small test execution before running production jobs

❌ **DON'T:**
- Create notebooks without kernel metadata and expect them to execute
- Retry failed job IDs after fixing metadata (create new job instead)
- Assume API-created notebooks have the same metadata as UI-created notebooks
- Skip validation step after notebook creation

### Related Issues

- **411 Length Required on updateDefinition**: Ensure `Content-Length` header is set (some HTTP clients require explicit setting)
- **Notebook shows as valid in portal but won't run**: Missing kernel metadata is often the culprit
- **Job fails immediately with no error**: Check for kernel metadata fields

### References

- [notebook-api-operations.md § Default Lakehouse Binding](./notebook-api-operations.md#default-lakehouse-binding)
- [SPARK-AUTHORING-CORE.md § Notebook Execution & Job Management](../../common/SPARK-AUTHORING-CORE.md#notebook-execution--job-management)
- [ITEM-DEFINITIONS-CORE.md § Notebook](../../common/ITEM-DEFINITIONS-CORE.md#notebook)

---

## Issue 2: Job Submission Returns Unreadable Response

### Symptoms
- POST to `/jobs/instances?jobType=RunNotebook` returns `202 Accepted`
- Response body is empty or "No Content"
- Unable to extract operation ID or job instance ID from response

### Root Cause
The response header `Location` contains the operation URL, but some HTTP clients don't expose headers easily. The job ID is embedded in the URL.

### Solution: Extract from Location Header or Query Recent Jobs

**Option 1: Parse Location Header**
```bash
RESPONSE=$(az rest --method post \
  --url "https://api.fabric.microsoft.com/v1/workspaces/$WORKSPACE_ID/items/$NOTEBOOK_ID/jobs/instances?jobType=RunNotebook" \
  --resource "https://api.fabric.microsoft.com" \
  --body '{}' \
  --headers "Content-Type=application/json" \
  --output-format json \
  --include-headers)

JOB_ID=$(echo "$RESPONSE" | grep -i "location:" | sed 's/.*\/instances\///g' | tr -d '\r')
```

**Option 2: Query Recent Jobs (Fallback)**
```bash
# Query jobs from last 1 minute
az rest --method get \
  --url "https://api.fabric.microsoft.com/v1/workspaces/$WORKSPACE_ID/items/$NOTEBOOK_ID/jobs/instances" \
  --resource "https://api.fabric.microsoft.com" \
  | jq -r '.value[] | select(.startTimeUtc > (now - 60)) | .id' \
  | head -1
```

---

## Checklist: Pre-Flight Checks Before Notebook Execution

Before submitting a notebook job, verify:

- [ ] Workspace has active capacity assigned (not paused)
- [ ] Notebook exists and has valid content
- [ ] Notebook metadata includes `kernel_info` and `kernelspec`
- [ ] If accessing lakehouse, `dependencies.lakehouse` is configured
- [ ] No recent duplicate jobs in the last 5 minutes
- [ ] Cell source arrays use proper `\n` line endings

After job submission:

- [ ] Capture job instance ID immediately
- [ ] Poll job status at 10-30 second intervals
- [ ] Check for `Running` status before declaring success
- [ ] If `Failed`, retrieve full job details for error analysis
- [ ] Do NOT retry POST with same parameters — use GET to check existing job

---

## Quick Reference: Notebook Execution Flow

```mermaid
graph TD
    A[Create/Update Notebook] --> B{Has kernel_info & kernelspec?}
    B -->|No| C[Add kernel metadata via updateDefinition]
    B -->|Yes| D[Submit Job: POST /jobs/instances]
    C --> D
    D --> E{Response readable?}
    E -->|No| F[Query recent jobs API]
    E -->|Yes| G[Extract job ID from response/headers]
    F --> G
    G --> H[Poll GET /jobs/instances/{id}]
    H --> I{Status?}
    I -->|NotStarted/Running| J[Wait 10-30s]
    J --> H
    I -->|Completed| K[Success: Retrieve outputs]
    I -->|Failed| L[Get job details for error]
    L --> M{Missing kernel metadata?}
    M -->|Yes| C
    M -->|No| N[Other error: debug further]
```

---

## Document History

- **2026-04-10**: Initial version documenting kernel metadata requirement (Issue 1) and job response handling (Issue 2)
