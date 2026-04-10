# How to Retrieve Semantic Model Properties

Semantic model properties are spread across **three distinct API surfaces** due to gaps in the Fabric API. This guide maps each property category to the correct retrieval method.

For authentication, variable setup, and audience details, see [SKILL.md § Authentication & API Audiences](../SKILL.md#authentication--api-audiences).

---

## Property-to-API Mapping

| Property Category | API Surface | Endpoint Pattern | SKILL.md Section |
|---|---|---|---|
| Name, ID, Description, Type | Fabric Items | `GET .../semanticModels/{id}` | [Agentic Workflow](../SKILL.md#agentic-workflow) step 2 |
| Owner, Storage Mode, Created Date | Power BI Datasets | `GET .../datasets/{id}` | — (see [below](#owner-storage-mode--operational-metadata)) |
| Query Scale-Out Settings | Power BI Datasets | `GET .../datasets/{id}` | — (see [below](#owner-storage-mode--operational-metadata)) |
| Full TMDL Schema | Fabric Items | `POST .../semanticModels/{id}/getDefinition?format=TMDL` | [Get/Download Definition](../SKILL.md#getdownload-definition) |
| Refresh History & Status | Power BI Datasets | `GET .../datasets/{id}/refreshes` | [Refresh Operations](../SKILL.md#refresh-operations) |
| Refresh Execution Details | Power BI Datasets | `GET .../datasets/{id}/refreshes/{refreshId}` | — (see [below](#refresh-history-response-properties)) |
| Refresh Schedule (Import) | Power BI Datasets | `GET .../datasets/{id}/refreshSchedule` | [Refresh Operations](../SKILL.md#refresh-operations) |
| Refresh Schedule (DirectQuery/LiveConnection) | Power BI Datasets | `GET .../datasets/{id}/directQueryRefreshSchedule` | — (see [below](#directquery--liveconnection-refresh-schedule)) |
| Data Sources | Power BI Datasets | `GET .../datasets/{id}/datasources` | [Data Sources & Parameters](../SKILL.md#data-sources--parameters) |
| Gateway Data Sources | Power BI Datasets | `GET .../datasets/{id}/Default.GetBoundGatewayDatasources` | — |
| Discoverable Gateways | Power BI Datasets | `GET .../datasets/{id}/Default.DiscoverGateways` | — |
| Parameters | Power BI Datasets | `GET .../datasets/{id}/parameters` | [Data Sources & Parameters](../SKILL.md#data-sources--parameters) |
| Permissions | Power BI Datasets | `GET .../datasets/{id}/users` | [Permissions](../SKILL.md#permissions) |
| Upstream Dataflow Links | Power BI Datasets | `GET .../datasets/upstreamDataflows` | — (see [below](#upstream-dataflow-links)) |
| Query Scale-Out Sync Status | Power BI Datasets | `GET .../datasets/{id}/queryScaleOut/syncStatus` | — |
| Tables, Columns, Measures | TMDL Definition | Decode `definition/tables/*.tmdl` parts | [TMDL File Structure](../SKILL.md#tmdl-file-structure) |
| Relationships | TMDL Definition | Decode `definition/relationships.tmdl` part | [TMDL File Structure](../SKILL.md#tmdl-file-structure) |
| M Expressions / Connections | TMDL Definition | Decode `definition/expressions*` parts | [TMDL File Structure](../SKILL.md#tmdl-file-structure) |

---

## Owner, Storage Mode & Operational Metadata

These properties are **only available** via the Power BI Datasets API — the Fabric Items API does not expose them.

```bash
az rest --method get \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$MODEL_ID"
```

**Properties returned**:

| Property | Description |
|---|---|
| `configuredBy` | Owner / last configured by (user principal name) |
| `createdDate` | ISO 8601 creation timestamp |
| `targetStorageMode` | `Abf` (Direct Lake), `PremiumFiles` (Import on Fabric), `Import` |
| `isRefreshable` | Whether the model supports refresh (always `false` for DirectQuery/LiveConnection) |
| `isEffectiveIdentityRequired` | RLS requires effective identity in embed scenarios |
| `isEffectiveIdentityRolesRequired` | RLS roles must be specified |
| `isOnPremGatewayRequired` | On-premises gateway needed for data sources |
| `isInPlaceSharingEnabled` | Whether the dataset can be shared with external users to consume in their own tenant |
| `addRowsAPIEnabled` | Push dataset rows API enabled |
| `queryScaleOutSettings` | Object: `maxReadOnlyReplicas` (0–64, -1 = auto), `autoSyncReadOnlyReplicas` (bool) |
| `upstreamDataflows` | Array of dependent dataflow references (`groupId`, `targetDataflowId`) |
| `description` | Dataset description (also available via Fabric Items API) |
| `webUrl` | Browser URL to the dataset |
| `createReportEmbedURL` | URL for report creation embedding |
| `qnaEmbedURL` | URL for Q&A embedding |

> **Note**: Callers with only Read permission receive a limited response (`id` and `name` only). Write permission on the dataset is required to get the full property set.

---

## Refresh History Response Properties

For refresh commands, see [SKILL.md § Refresh Operations](../SKILL.md#refresh-operations). Each refresh entry in the response contains:

| Property | Description |
|---|---|
| `requestId` | Unique request identifier |
| `id` | Refresh ID (use for cancel or detail queries) |
| `refreshType` | `ViaEnhancedApi`, `Scheduled`, `OnDemand`, `ViaXmlaEndpoint` |
| `startTime` / `endTime` | ISO 8601 timestamps |
| `status` | `Completed`, `Failed`, `Unknown`, `Disabled`, `Cancelled` |
| `extendedStatus` | Additional status detail |
| `serviceExceptionJson` | Error details when failed (includes `errorCode`, `errorDescription`) |
| `refreshAttempts[]` | Per-attempt details with individual start/end times |

---

## Data Source Response Properties

For data source commands, see [SKILL.md § Data Sources & Parameters](../SKILL.md#data-sources--parameters). Each data source entry contains:

| Property | Description |
|---|---|
| `datasourceType` | e.g., `AzureDataLakeStorage`, `Sql`, `AnalysisServices` |
| `connectionDetails` | Object with `server`, `database`, or `path` |
| `datasourceId` | Data source unique identifier |
| `gatewayId` | Associated gateway (if on-premises) |

For Direct Lake models, the M expression in the TMDL definition reveals the source Lakehouse/Warehouse connection path. See [tmdl-authoring-guide.md § Direct Lake Guidelines](./tmdl-authoring-guide.md#direct-lake-guidelines).

---

## DirectQuery / LiveConnection Refresh Schedule

Import models use `refreshSchedule` (see [SKILL.md § Refresh Operations](../SKILL.md#refresh-operations)). DirectQuery and LiveConnection models use a **separate endpoint** with different properties:

```bash
az rest --method get \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/$MODEL_ID/directQueryRefreshSchedule"
```

| Property | Description |
|---|---|
| `frequency` | Interval in minutes between refreshes: `15`, `30`, `60`, `120`, `180` |
| `days[]` | Days to execute (used with `times` instead of `frequency`) |
| `times[]` | Times of day to execute (used with `days` instead of `frequency`) |
| `localTimeZoneId` | Time zone ID |

> The schedule uses **either** `frequency` (automatic interval) **or** `days` + `times` (fixed schedule), not both.

---

## Upstream Dataflow Links

Returns dataflow dependencies for all datasets in a workspace (not per-dataset):

```bash
az rest --method get \
  --resource "https://analysis.windows.net/powerbi/api" \
  --url "$PBI/groups/$WS_ID/datasets/upstreamDataflows"
```

| Property | Description |
|---|---|
| `datasetObjectId` | The dataset ID |
| `dataflowObjectId` | The upstream dataflow ID |
| `workspaceObjectId` | The workspace containing the dataflow |

---

## Per-Table Storage Mode

The model-level `targetStorageMode` (above) gives the overall mode. For per-table detail, inspect partition definitions in the TMDL:

```bash
# After retrieving TMDL via getDefinition (see SKILL.md § Get/Download Definition):
echo "$RESULT" | jq -r '.definition.parts[] | select(.path | startswith("definition/tables/")) | .payload' | base64 -d | grep -i "mode:"
```

Values: `directLake`, `import`, `directQuery`
