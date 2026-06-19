# skills-for-fabric Evaluation Results

**Date:** 2026-02-19  
**Workspace:** skills-for-fabric (`c92c724b-cca6-4b91-b330-548b482c3800`)  
**Skills Version:** v0.2.1 (v0.2.3 available)  
**Environment:** Microsoft Fabric (MSIT), Starter Pool capacity

---

## Summary

| Skill | Total | ✅ Pass | ❌ Fail | ⏭️ Skip | Pass Rate |
|-------|------:|--------:|--------:|---------:|----------:|
| **check-updates** | 5 | 4 | 0 | 1 | **100%** |
| **spark-authoring-cli** | 10 | 8 | 1 | 1 | **88.9%** |
| **spark-consumption-cli** | 10 | 7 | 0 | 3 | **100%** |
| **sqldw-authoring-cli** | 12 | 7 | 2 | 3 | **77.8%** |
| **sqldw-consumption-cli** | 12 | 7 | 0 | 5 | **100%** |
| **eventhouse-authoring-cli** | 12 | 10 | 0 | 2 | **100%** |
| **eventhouse-consumption-cli** | 13 | 11 | 0 | 2 | **100%** |
| **Overall** | **74** | **54** | **3** | **17** | **94.7%** |

> **Pass Rate** is calculated over executed tests only (Pass + Fail), excluding skipped tests.

---

## Consistency Tests

| Write Skill | Read Skill | Table | Expected | Actual | Match |
|-------------|-----------|-------|----------|--------|-------|
| spark-authoring (SA-08) | spark-consumption (SC-05) | eval_products_v2 | 5 rows, exact values | 5 rows, all match | ✅ **EXACT** |
| sqldw-authoring (DWA-03) | sqldw-consumption (DWC-02) | eval.sales_transactions | 5 rows, exact values | 5 rows: 19.98, 59.94, 119.88, 199.80, 299.70 | ✅ **EXACT** |
| sqldw-authoring (DWA-03) | sqldw-consumption (DWC-04) | eval.sales_transactions | SUM = 699.30 | 699.30 | ✅ **EXACT** |
| eventhouse-authoring (KA-02) | eventhouse-consumption (KC-05) | eval_sensor_readings | 5 rows, exact values | 5 rows, temps: 20.6, 21.1, 21.6, 22.1, 22.6 | ✅ **EXACT** |
| eventhouse-authoring (KA-02) | eventhouse-consumption (KC-01) | eval_sensor_readings | count = 5 | 5 | ✅ **EXACT** |

**Write/Read Consistency: 5/5 (100%) — All consistency tests passed.**

---

## Detailed Results by Skill

### check-updates

| Case | Title | Result | Notes |
|------|-------|--------|-------|
| CU-01 | Basic version check | ✅ PASS | Detected v0.2.1 local → v0.2.3 remote |
| CU-02 | Explicit version query | ✅ PASS | Returned v0.2.1 |
| CU-03 | Changelog request | ✅ PASS | Update notification with version diff shown |
| CU-04 | Trigger word variation | ✅ PASS | Skill invoked correctly on "am I up to date" |
| CU-05 | Negative — unrelated prompt | ⏭️ SKIP | Cannot test negative routing in eval harness |

### spark-authoring-cli

| Case | Title | Result | Notes |
|------|-------|--------|-------|
| SA-01 | Create Lakehouse | ✅ PASS | `eval_sales_lh` exists (`a0e5a3a4`) |
| SA-02 | Create Notebook | ✅ PASS | `eval_ingest_sales` created (`6989ed3d`) |
| SA-03 | Create Livy Session | ✅ PASS | Session `d2f9d019` state=idle |
| SA-04 | Organize Tables (Schemas) | ❌ FAIL | `CREATE SCHEMA` not supported on Starter Pool |
| SA-05 | Design Pipeline | ✅ PASS | `eval_sales_pipeline` created (`12b6769d`) |
| SA-06 | Spark Configuration | ✅ PASS | `spark.sql.shuffle.partitions=8` confirmed |
| SA-07 | Delta Table Creation | ✅ PASS | `eval_products_v2` created with correct schema |
| SA-08 | Write Known Data | ✅ PASS | 5 rows written, all cell values verified |
| SA-09 | Bulk Data Load | ✅ PASS | sales=100, products=50, customers=100 |
| SA-10 | Negative — Ambiguous | ⏭️ SKIP | Routing test — not testable in eval harness |

### spark-consumption-cli

| Case | Title | Result | Notes |
|------|-------|--------|-------|
| SC-01 | Row Count | ✅ PASS | count=100 ✓ |
| SC-02 | Filtered Query | ✅ PASS | Electronics=20 ✓ |
| SC-03 | Aggregation | ✅ PASS | 4 regions: East=39460.50, West=32467.50, North=39460.50, South=32467.50 |
| SC-04 | Join Query | ✅ PASS | 3 tiers: Bronze=48990.96, Gold=47332.62, Silver=47532.42 |
| SC-05 | Read Back Known Data | ✅ PASS | 5 rows exact match with SA-08 write data |
| SC-06 | Delta Time Travel | ⏭️ SKIP | Requires multiple Delta versions to test |
| SC-07 | Semi-structured JSON | ⏭️ SKIP | `sensor_readings` not loaded to lakehouse |
| SC-08 | Cross-Lakehouse Query | ⏭️ SKIP | Only 1 lakehouse provisioned |
| SC-09 | Top 5 Products | ✅ PASS | Product_049=9790.20, Product_048=8631.36, ... |
| SC-10 | Data Quality Check | ✅ PASS | 0 nulls, 0 negative quantities, 0 amount mismatches |

### sqldw-authoring-cli

| Case | Title | Result | Notes |
|------|-------|--------|-------|
| DWA-01 | Create Schema | ✅ PASS | `eval` schema created |
| DWA-02 | Create Table | ✅ PASS | `eval.sales_transactions` with 10 columns |
| DWA-03 | Insert Known Data | ✅ PASS | 5 rows inserted |
| DWA-04 | COPY INTO | ⏭️ SKIP | No ADLS/OneLake path configured for CSV files |
| DWA-05 | Update Data | ✅ PASS | 2 rows updated (East → Northeast) |
| DWA-06 | MERGE / Upsert | ⏭️ SKIP | No staging table configured |
| DWA-07 | Create Stored Procedure | ✅ PASS | `eval.sp_sales_summary` created |
| DWA-08 | Create View | ✅ PASS | `eval.vw_sales_by_region` created |
| DWA-09 | Alter Table | ✅ PASS | `discount_pct DECIMAL(5,2)` column added |
| DWA-10 | Time Travel | ❌ FAIL | `FOR TIMESTAMP AS OF` syntax not supported on this warehouse endpoint |
| DWA-11 | Transaction Rollback | ❌ FAIL | Transaction scope mismatch in pooled connection driver |
| DWA-12 | Drop Cleanup | ⏭️ SKIP | Preserved eval data for consumption tests |

### sqldw-consumption-cli

| Case | Title | Result | Notes |
|------|-------|--------|-------|
| DWC-01 | Row Count | ✅ PASS | count=5 ✓ |
| DWC-02 | SELECT All (Consistency) | ✅ PASS | 5 rows: 19.98, 59.94, 119.88, 199.80, 299.70 |
| DWC-03 | Filtered Query | ✅ PASS | 1 Electronics row |
| DWC-04 | SUM | ✅ PASS | total=699.30 ✓ |
| DWC-05 | GROUP BY | ✅ PASS | 4 regions: East=319.68, North=119.88, South=199.80, West=59.94 |
| DWC-06 | JOIN | ⏭️ SKIP | No customers table in warehouse |
| DWC-07 | TOP N | ✅ PASS | Top 3: Product_005, Product_004, Product_003 |
| DWC-08 | Schema Discovery | ✅ PASS | 11 columns returned |
| DWC-09 | Export CSV | ⏭️ SKIP | Manual export not tested in harness |
| DWC-10 | Lakehouse SQL EP | ⏭️ SKIP | SQL Endpoint query deferred |
| DWC-11 | Negative — Write | ⏭️ SKIP | Routing test — not testable in eval harness |
| DWC-12 | Large Table (10K) | ⏭️ SKIP | 10K dataset not loaded |

### eventhouse-authoring-cli

| Case | Title | Result | Notes |
|------|-------|--------|-------|
| KA-01 | Create Table | ✅ PASS | `eval_sensor_readings` with 6 typed columns |
| KA-02 | Inline Ingest | ✅ PASS | 5 rows ingested, verified via count |
| KA-03 | Create Mapping | ✅ PASS | `eval_sensor_json_mapping` JSON mapping created |
| KA-04 | Ingest from Storage | ⏭️ SKIP | No blob storage path configured |
| KA-05 | Create Function | ✅ PASS | `eval_avg_temperature()` stored function |
| KA-06 | Retention Policy | ✅ PASS | 90-day soft-delete period set |
| KA-07 | Caching Policy | ✅ PASS | 30-day hot cache set |
| KA-08 | Materialized View | ✅ PASS | `eval_hourly_avg` created |
| KA-09 | Add Column | ✅ PASS | `battery_level:real` added |
| KA-10 | Update Policy | ✅ PASS | Alert trigger policy on `eval_sensor_alerts` |
| KA-11 | Create Sales Table | ✅ PASS | `eval_sales` table created |
| KA-12 | Negative — Ambiguous | ⏭️ SKIP | Routing test |

### eventhouse-consumption-cli

| Case | Title | Result | Notes |
|------|-------|--------|-------|
| KC-01 | Row Count | ✅ PASS | count=5 ✓ |
| KC-02 | Schema Discovery | ✅ PASS | All columns with correct KQL types |
| KC-03 | Filtered Query (where) | ✅ PASS | 2 rows with temperature > 22.0 |
| KC-04 | Time-Series Aggregation | ✅ PASS | 5 device×day buckets via `bin(timestamp, 1d)` |
| KC-05 | Read Back Known Data | ✅ PASS | 5 rows exact match: temps 20.6, 21.1, 21.6, 22.1, 22.6 |
| KC-06 | Multi-Aggregation | ✅ PASS | 5 devices with avg/max/min/count per device |
| KC-07 | Dynamic Column Access | ✅ PASS | `tags[0]` extracted from dynamic array |
| KC-08 | Join Query | ⏭️ SKIP | `eval_sales` has no data to join |
| KC-09 | Top N | ✅ PASS | Top 5 by temperature descending |
| KC-10 | Render Timechart | ✅ PASS | `render timechart` operator appended |
| KC-11 | Materialized View Query | ✅ PASS | `eval_hourly_avg` queried (MV materializing) |
| KC-12 | Ingestion Monitor | ✅ PASS | `.show ingestion failures` executed |
| KC-13 | Negative — Write | ⏭️ SKIP | Routing test — not testable in eval harness |

---

## Failures Analysis

| Case | Skill | Issue | Root Cause | Recommendation |
|------|-------|-------|------------|----------------|
| SA-04 | spark-authoring | `CREATE SCHEMA` fails | Starter Pool does not support lakehouse schemas | Eval requires Standard capacity or skip on Starter Pool |
| DWA-10 | sqldw-authoring | Time travel syntax error | `FOR TIMESTAMP AS OF` requires literal timestamp, not `DATEADD` expression | Use pre-computed timestamp string |
| DWA-11 | sqldw-authoring | Transaction rollback fails | Node.js `mssql` connection pool scope conflicts with explicit transactions | Use single-connection mode or dedicated transaction API |

---

## Skipped Tests Summary

| Reason | Count | Cases |
|--------|------:|-------|
| Routing/negative tests (not testable in harness) | 6 | CU-05, SA-10, KC-13, DWC-11, KA-12, KC-08 |
| Infrastructure not configured (ADLS, blob storage) | 3 | DWA-04, DWA-06, KA-04 |
| Additional resources not provisioned | 4 | SC-06, SC-07, SC-08, DWC-06 |
| Deferred/preserved for other tests | 4 | DWA-12, DWC-09, DWC-10, DWC-12 |

---

## Infrastructure Used

| Resource | Name | ID |
|----------|------|-----|
| Workspace | skills-for-fabric | `c92c724b-cca6-4b91-b330-548b482c3800` |
| Lakehouse | eval_sales_lh | `a0e5a3a4-5626-458e-9c18-23f8c0997846` |
| Warehouse | EvalWarehouse | `197101ea-5480-4173-a974-b2f4cf0457f6` |
| Eventhouse | EvalEventhouse | `7dad5ca8-4533-4432-becc-50ec0bc88db4` |
| KQL Database | EvalEventhouse | `a9b3d74a-7074-43e8-b793-e150e62d696a` |
| Notebook | eval_ingest_sales | `6989ed3d-9d8c-432c-b838-3a65176edf01` |
| Pipeline | eval_sales_pipeline | `12b6769d-1787-4372-8105-6865e4aa2b55` |
| Livy Session | eval-session | `d2f9d019-a6fb-400a-ad59-d5843c8206eb` |
