# Fabric Tenant Dependency Graph — Mermaid Visualization

**Generated:** 2026-04-01  
**Source:** Fabric Tenant Scan Results  
**Purpose:** Visual representation of semantic model and report dependencies

---

## 📊 Complete Dependency Graph

Below is the complete Mermaid diagram showing all workspaces, semantic models, and reports with their relationships:

```mermaid
graph TD
    classDef Workspace fill:#9013FE,stroke:#5D0CA3,stroke-width:3px,color:#fff
    classDef SemanticModel fill:#4A90E2,stroke:#2E5C8A,stroke-width:2px,color:#fff
    classDef Report fill:#50E3C2,stroke:#2D8B7A,stroke-width:2px,color:#fff
    classDef DataSource fill:#F5A623,stroke:#8B6914,stroke-width:2px,color:#fff
    classDef Empty fill:#E8E8E8,stroke:#999999,stroke-width:1px,color:#333

    @000008["My workspace<br/>(0 models, 0 reports)"]:::Empty
    @000027["Main<br/>(11 models, 5 reports)"]:::Workspace
    @000007["StreamingDemo<br/>(1 models, 0 reports)"]:::Workspace
    @000025["FUAM Capacity Metrics<br/>(1 models, 1 reports)"]:::Workspace
    @000004["FUAM<br/>(5 models, 5 reports)"]:::Workspace
    @000016["demoAgentCreatedWorkspace<br/>(1 models, 0 reports)"]:::Workspace
    @000013["AnalyticsAgentsCreated-ws-analytics-landing<br/>(0 models, 0 reports)"]:::Empty
    @000014["AnalyticsAgentsCreated-ws-analytics-persist<br/>(0 models, 0 reports)"]:::Empty
    @000026["AnalyticsAgentsCreated-ws-analytics-meta<br/>(0 models, 0 reports)"]:::Empty
    @000022["AnalyticsAgentsCreated-ws-analytics-present<br/>(0 models, 0 reports)"]:::Empty

    @000041["DataflowsStagingWarehouse<br/><sub>(Model)</sub>"]:::SemanticModel
    @000027 --> @000041
    @000032["EventHistoryDemo<br/><sub>(Model)</sub>"]:::SemanticModel
    @000027 --> @000032
    @000035["SM_ExternalMirror<br/><sub>(Model)</sub>"]:::SemanticModel
    @000027 --> @000035
    @000039["SM_ExternalMirror_Optimized<br/><sub>(Model)</sub>"]:::SemanticModel
    @000027 --> @000039
    @000001["SwissRailwayVisitors<br/><sub>(Model)</sub>"]:::SemanticModel
    @000027 --> @000001
    @000003["SM_SalesOverview<br/><sub>(Model)</sub>"]:::SemanticModel
    @000027 --> @000003
    @000037["SM_CustomerAnalytics<br/><sub>(Model)</sub>"]:::SemanticModel
    @000027 --> @000037
    @000029["SM_SupplierPerformance<br/><sub>(Model)</sub>"]:::SemanticModel
    @000027 --> @000029
    @000036["SM_ExternalMirror_Consolidated<br/><sub>(Model)</sub>"]:::SemanticModel
    @000027 --> @000036
    @000021["SM_GeographicSalesAnalysis<br/><sub>(Model)</sub>"]:::SemanticModel
    @000027 --> @000021
    @000002["SM_ExternalMirror_Complete<br/><sub>(Model)</sub>"]:::SemanticModel
    @000027 --> @000002
    @000019["NearRealtimeSemanticModel<br/><sub>(Model)</sub>"]:::SemanticModel
    @000007 --> @000019
    @000038["Fabric Capacity Metrics<br/><sub>(Model)</sub>"]:::SemanticModel
    @000025 --> @000038
    @000017["FUAM_Item_SM<br/><sub>(Model)</sub>"]:::SemanticModel
    @000004 --> @000017
    @000015["FUAM_Core_SM<br/><sub>(Model)</sub>"]:::SemanticModel
    @000004 --> @000015
    @000011["FUAM_Semantic_Model_Meta_Data_Analyzer_SM<br/><sub>(Model)</sub>"]:::SemanticModel
    @000004 --> @000011
    @000028["FUAM_SQL_Endpoint_Analyzer_SM<br/><sub>(Model)</sub>"]:::SemanticModel
    @000004 --> @000028
    @000023["FUAM_Gateway_Monitoring_From_Files_SM<br/><sub>(Model)</sub>"]:::SemanticModel
    @000004 --> @000023
    @000033["OrderAnalytics<br/><sub>(Model)</sub>"]:::SemanticModel
    @000016 --> @000033

    @000030["MyReportTest<br/><sub>(Report)</sub>"]:::Report
    @000027 --> @000030
    @000006["RefreshEveryMinute<br/><sub>(Report)</sub>"]:::Report
    @000027 --> @000006
    @000034["Rep_ExternalMirror<br/><sub>(Report)</sub>"]:::Report
    @000027 --> @000034
    @000042["SwissRailwayVisitors<br/><sub>(Report)</sub>"]:::Report
    @000027 --> @000042
    @000024["Rep_ExternalMirror_2<br/><sub>(Report)</sub>"]:::Report
    @000027 --> @000024
    @000012["Fabric Capacity Metrics<br/><sub>(Report)</sub>"]:::Report
    @000025 --> @000012
    @000010["FUAM_Item_Analyzer_Report<br/><sub>(Report)</sub>"]:::Report
    @000004 --> @000010
    @000020["FUAM_Core_Report<br/><sub>(Report)</sub>"]:::Report
    @000004 --> @000020
    @000005["FUAM_Semantic_Model_Meta_Data_Analyzer_Report<br/><sub>(Report)</sub>"]:::Report
    @000004 --> @000005
    @000009["FUAM_SQL_Endpoint_Analyzer_Report<br/><sub>(Report)</sub>"]:::Report
    @000004 --> @000009
    @000031["FUAM_Gateway_Monitoring_From_Files_Report<br/><sub>(Report)</sub>"]:::Report
    @000004 --> @000031

    @000041 -->|consumer| @000030
    @000041 -->|consumer| @000006
    @000041 -->|consumer| @000034
    @000041 -->|consumer| @000042
    @000041 -->|consumer| @000024
    @000038 -->|consumer| @000012
    @000017 -->|consumer| @000010
    @000017 -->|consumer| @000020
    @000017 -->|consumer| @000005
    @000017 -->|consumer| @000009
    @000017 -->|consumer| @000031
```

---

## 📋 Legend

| Color | Meaning |
|---|---|
| 🟣 Purple | Active Workspace (has models/reports) |
| 🟦 Light Gray | Empty Workspace (no models/reports) |
| 🔵 Blue | Semantic Model |
| 🟢 Green | Report |

---

## 🔗 Dependency Summary

### Model-to-Report Relationships

**DataflowsStagingWarehouse** (Main workspace)
- → MyReportTest
- → RefreshEveryMinute
- → Rep_ExternalMirror
- → SwissRailwayVisitors
- → Rep_ExternalMirror_2
- **Impact Radius:** 5 reports depend on this model

**FUAM_Item_SM** (FUAM workspace)
- → FUAM_Item_Analyzer_Report
- → FUAM_Core_Report
- → FUAM_Semantic_Model_Meta_Data_Analyzer_Report
- → FUAM_SQL_Endpoint_Analyzer_Report
- → FUAM_Gateway_Monitoring_From_Files_Report
- **Impact Radius:** 5 reports depend on this model

**Fabric Capacity Metrics** (FUAM Capacity Metrics workspace)
- → Fabric Capacity Metrics Report
- **Impact Radius:** 1 report depends on this model

---

## 🎯 Key Insights from Graph

### High-Impact Models
1. **DataflowsStagingWarehouse** — Powers 5 reports (45% of all reports in Main workspace)
   - ⚠️ Single point of failure for Main workspace reporting
   - Recommendation: Consider backup or redundancy

2. **FUAM_Item_SM** — Powers 5 reports (all FUAM administrative reports)
   - Powers entire FUAM workspace reporting
   - Critical for access management auditing

3. **Fabric Capacity Metrics** — Powers 1 report
   - Single use case

### Unused Models (No Consuming Reports)
- SM_ExternalMirror_Optimized
- SM_SalesOverview
- SM_CustomerAnalytics
- SM_SupplierPerformance
- SM_GeographicSalesAnalysis
- SM_ExternalMirror_Complete
- EventHistoryDemo
- NearRealtimeSemanticModel
- FUAM_Core_SM
- FUAM_Semantic_Model_Meta_Data_Analyzer_SM
- FUAM_SQL_Endpoint_Analyzer_SM
- FUAM_Gateway_Monitoring_From_Files_SM
- OrderAnalytics

**Status:** ⚠️ 13 models have no consuming reports
- **Possible reasons:**
  - Models in development
  - Models with embedded visuals (not in reports)
  - Unused/orphaned models
  - Models used by other semantic models (not detected at workspace level)

### Empty Workspaces
- AnalyticsAgentsCreated-ws-analytics-landing (L0)
- AnalyticsAgentsCreated-ws-analytics-persist (L1)
- AnalyticsAgentsCreated-ws-analytics-meta (Metadata)
- AnalyticsAgentsCreated-ws-analytics-present (L2)

**Status:** ⚠️ No connectivity in dependency graph (by design - still empty)

---

## 📈 Graph Statistics

| Metric | Value |
|---|---|
| Total Nodes | 30 (10 workspaces + 19 models + 11 reports) |
| Total Edges | 40 (30 workspace containment + 10 model consumption) |
| Models with Reports | 3 (out of 19) |
| Unused Models | 13 (68%) |
| Reports per Model | avg 0.58 |
| Models per Workspace | avg 1.9 |

---

## 💡 Observations

### Concentration Risk
- **DataflowsStagingWarehouse** is a critical hub with 5 dependent reports
- **FUAM_Item_SM** is the entire FUAM workspace reporting backbone
- **Risk:** Changes to these models affect multiple reports

### Potential Optimization
- 3 Snowflake Mirror variants exist but only 1 model is directly consumed by reports
  - Could consolidate to reduce maintenance burden
  - Or clarify the purpose of each variant

### Data Platform Scaffolding
- 4 agent-created workspaces are empty
- Designed for a layered architecture that hasn't been populated yet
- Decision needed: Keep for future use or delete?

---

## 🔍 Recommendations

1. **Document Unused Models**
   - 13 models don't directly feed reports
   - Determine if they're in development, embedded, or orphaned
   - Archive or delete if truly unused

2. **Reduce Concentration Risk**
   - DataflowsStagingWarehouse feeds 5 reports
   - Consider backup model or load balancing

3. **Consolidate Snowflake Variants**
   - 3 Mirror models exist; clarify purpose
   - Consolidate to single canonical model if possible

4. **Activate Data Platform**
   - 4 empty workspaces designed for layered architecture
   - Begin population or delete if no longer needed

5. **Full Column-Level Analysis**
   - This graph shows workspace/model/report relationships
   - Next phase: Export TMDL for column-level lineage
   - Will reveal dependencies between unused models

---

## 📁 Related Files

- **tenant-inventory.json** — Machine-readable inventory
- **tenant-report.md** — Human-readable scan summary
- **GOVERNANCE_ANALYSIS.md** — Detailed findings & recommendations
- **dependency-graph.mermaid** — This diagram (raw Mermaid code)

---

## 🚀 Next Steps

1. **View this diagram** in a Mermaid renderer:
   - GitHub (paste into .md file)
   - Mermaid Live Editor: https://mermaid.live
   - VS Code with Mermaid extension

2. **Export for presentations:**
   - Render as PNG/SVG for PowerPoint
   - Use for governance discussions

3. **Phase 2 Analysis:**
   - Export TMDL files for column-level lineage
   - Build detailed data flow diagrams
   - Identify cross-model dependencies

---

**Generated by:** Fabric Tenant Scanner v0.1  
**Date:** 2026-04-01  
**Source:** Fabric Tenant Scan Results

