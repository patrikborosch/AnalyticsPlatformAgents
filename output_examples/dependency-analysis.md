# Power BI Dependency Analysis

**Workspace:** `00000000-0000-4000-8000-000000000027`  
**Generated:** 2026-04-01T09:32:19.1315703+02:00  
**Reports:** 5 | **Semantic Models:** 3

---

## Report → Semantic Model Bindings

| Report | Format | Semantic Model | Fields Used | Unused Model Fields |
|--------|--------|----------------|-------------|---------------------|
| RefreshEveryMinute | unknown | EventHistoryDemo | - | - |
| Rep_ExternalMirror | unknown | SM_ExternalMirror | - | - |
| MyReportTest | unknown | EventHistoryDemo | - | - |
| Rep_ExternalMirror_2 | unknown | SM_ExternalMirror | - | - |
| SwissRailwayVisitors | unknown | SwissRailwayVisitors | - | - |

---

## Report Field References (Detail)

### RefreshEveryMinute

- **Format:** unknown
- **Semantic Model:** EventHistoryDemo (`00000000-0000-4000-8000-000000000032`)

*No field references extracted.*

### Rep_ExternalMirror

- **Format:** unknown
- **Semantic Model:** SM_ExternalMirror (`00000000-0000-4000-8000-000000000035`)

*No field references extracted.*

### MyReportTest

- **Format:** unknown
- **Semantic Model:** EventHistoryDemo (`00000000-0000-4000-8000-000000000032`)

*No field references extracted.*

### Rep_ExternalMirror_2

- **Format:** unknown
- **Semantic Model:** SM_ExternalMirror (`00000000-0000-4000-8000-000000000035`)

*No field references extracted.*

### SwissRailwayVisitors

- **Format:** unknown
- **Semantic Model:** SwissRailwayVisitors (`00000000-0000-4000-8000-000000000001`)

*No field references extracted.*

---

## Semantic Model Metadata

### SwissRailwayVisitors

**ID:** `00000000-0000-4000-8000-000000000001`  
**Tables:** 0 | **Columns:** 0 | **Measures:** 0 | **Relationships:** 0

#### Tables & Columns

### EventHistoryDemo

**ID:** `00000000-0000-4000-8000-000000000032`  
**Tables:** 0 | **Columns:** 0 | **Measures:** 0 | **Relationships:** 0

#### Tables & Columns

### SM_ExternalMirror

**ID:** `00000000-0000-4000-8000-000000000035`  
**Tables:** 0 | **Columns:** 0 | **Measures:** 0 | **Relationships:** 0

#### Tables & Columns

---

## Data Quality & Limitations

| Capability | Quality | Method |
|------------|---------|--------|
| Report → Semantic Model binding | **HIGH** | Power BI REST API `.datasetId` |
| Field refs from PBIR reports | **HIGH** | `getDefinition` → `Entity`/`Property` in `visual.json` |
| Field refs from PBIRLegacy reports | **HIGH** | `getDefinition` → `queryRef` in `report.json` |
| Semantic model tables/columns/rels | **HIGH** | DAX `INFO.VIEW.*()` |
| Semantic model measures | **HIGH** | DAX `INFO.VIEW.MEASURES()` |
| Measure expressions (DAX formulas) | **LIMITED** | Not returned via REST `executeQueries`; requires XMLA |
| Measure → column dependency graph | **LIMITED** | `INFO.CALCDEPENDENCY()` may fail via REST API |


