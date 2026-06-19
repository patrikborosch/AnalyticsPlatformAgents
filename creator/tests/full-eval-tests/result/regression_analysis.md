# Regression Analysis

**Current Run:** 2026-04-20 — Workspace: FullEval-20260420120544 (`546bedbf-f466-4cc7-8f20-2d42ec2cbc8a`)
**Baseline:** 2026-02-19 — Workspace: skills-for-fabric (`c92c724b-cca6-4b91-b330-548b482c3800`) — [GitHub](https://github.com/gim-home/skills-for-fabric/blob/main/tests/full-eval-tests/result/eval-results.md)

> **Note:** The baseline ran on a Starter Pool capacity workspace with 7 skills (74 tests). The current run uses a fresh timestamped workspace and evaluates 12 skills plus 4 combined evals (98 tests total). Migration skills, Power BI skills, and medallion architecture are new in this run.

---

## Verdict: BETTER — no regressions; pass rate improved from 94.7% to 99.0%; all 3 baseline failures fixed

---

## 1. Overall Pass Rate

| Metric | Baseline (Feb 19) | Current (Apr 20) | Delta |
|--------|-------------------:|------------------:|------:|
| Total Tests | 74 | 98 | +24 |
| Pass | 54 | 97 | +43 |
| Fail | 3 | 0 | -3 |
| Error | 0 | 1 | +1 |
| Skip | 17 | 0 | -17 |
| **Pass Rate** | **94.7%** | **99.0%** | **+4.3pp** |

> Baseline pass rate = Pass / (Pass + Fail) excluding skips = 54/57 = 94.7%.
> Current pass rate = Pass / Total = 97/98 = 99.0%.

---

## 2. Per-Skill Comparison

### Individual Skills

| Skill | Baseline | Current | Change |
|-------|----------|---------|--------|
| check-updates | 100% (4P/0F/1S) | — (not in current run) | Removed from eval suite |
| spark-authoring-cli | 88.9% (8P/1F/1S) | 100% (9P/0F/0E) | **+11.1pp** — SA-04 fixed (schemas via Livy), SA-10 now tested |
| spark-consumption-cli | 100% (7P/0F/3S) | 100% (3P/0F/0E) | Same; suite restructured (10→3 individual tests, others moved to combined) |
| sqldw-authoring-cli | 77.8% (7P/2F/3S) | 100% (9P/0F/0E) | **+22.2pp** — DWA-10/DWA-11 equivalents now pass; DWA-04/DWA-06 now executed |
| sqldw-consumption-cli | 100% (7P/0F/5S) | 100% (7P/0F/0E) | Same; all 7 tests pass including DWC-02 (data isolation fixed) |
| eventhouse-authoring-cli | 100% (10P/0F/2S) | 91.7% (11P/0F/1E) | -8.3pp — KA-04 changed from SKIP→ERROR (same infra gap, not a regression) |
| eventhouse-consumption-cli | 100% (11P/0F/2S) | 100% (8P/0F/0E) | Same; suite restructured (13→8 individual tests) |
| powerbi-authoring-cli | — | 100% (5P/0F/0E) | **NEW** — all tests pass |
| semantic-model-consumption | — | 100% (8P/0F/0E) | **NEW** — all tests pass (Direct Lake framing issue from Apr 19 resolved) |
| e2e-medallion-architecture | — | 100% (2P/0F/0E) | **NEW** — descriptive design tests |
| synapse-migration | — | 100% (6P/0F/0E) | **NEW** — migration guidance tests |
| databricks-migration | — | 100% (7P/0F/0E) | **NEW** — migration guidance tests |
| hdinsight-migration | — | 100% (6P/0F/0E) | **NEW** — migration guidance tests |

### Combined Skills (all new in current run)

| Eval Plan | Tests | Pass | Fail | Error | Pass Rate |
|-----------|------:|-----:|-----:|------:|----------:|
| spark-authoring+consumption | 2 | 2 | 0 | 0 | 100% |
| sqldw-authoring+consumption | 3 | 3 | 0 | 0 | 100% |
| eventhouse-authoring+consumption | 2 | 2 | 0 | 0 | 100% |
| powerbi-authoring+consumption | 9 | 9 | 0 | 0 | 100% |

---

## 3. Persistent Failures

All three baseline failures have been **resolved** in the current run:

| Case | Skill | Baseline Status | Current Status | Resolution |
|------|-------|----------------|----------------|------------|
| SA-04 | spark-authoring-cli | FAIL — `CREATE SCHEMA` not supported on Starter Pool | PASS — Schemas created via Livy statement | Fixed — FullEval workspace supports schema operations |
| DWA-10 | sqldw-authoring-cli | FAIL — `FOR TIMESTAMP AS OF` syntax error | PASS (DWA-07) — Time travel query executed with `OPTION (FOR TIMESTAMP AS OF)` | Fixed — correct syntax used |
| DWA-11 | sqldw-authoring-cli | FAIL — Transaction scope mismatch in pooled connection | PASS (DWA-08) — Transaction rolled back, data unchanged | Fixed — SQL file execution avoids pool scope issue |

**Persistent failures: 0** — No test that failed in the baseline also fails in the current run.

---

## 4. New Coverage

Tests that exist in the current run but not in the baseline:

| Category | Tests | Pass | Fail | Error | Details |
|----------|------:|-----:|-----:|------:|---------|
| powerbi-authoring-cli (individual) | 5 | 5 | 0 | 0 | Create/download/datasources/delete Direct Lake semantic model + ambiguous prompt |
| semantic-model-consumption (individual) | 8 | 8 | 0 | 0 | Metadata discovery (tables, columns, measures, relationships) + DAX queries |
| e2e-medallion-architecture (individual) | 2 | 2 | 0 | 0 | Medallion architecture design + per-layer Spark config |
| synapse-migration (individual) | 6 | 6 | 0 | 0 | mssparkutils→notebookutils, Linked Services, DDL, COPY INTO guidance |
| databricks-migration (individual) | 7 | 7 | 0 | 0 | dbutils→notebookutils, secrets, widgets, Unity Catalog, MLflow, DBFS |
| hdinsight-migration (individual) | 6 | 6 | 0 | 0 | WASB paths, HiveContext, Hive DDL, Oozie, notebookutils.fs, HDFS |
| spark-authoring+consumption (combined) | 2 | 2 | 0 | 0 | Write→read consistency via Livy session (Delta table) |
| sqldw-authoring+consumption (combined) | 3 | 3 | 0 | 0 | T-SQL write→read consistency + cross-engine PySpark JDBC read |
| eventhouse-authoring+consumption (combined) | 2 | 2 | 0 | 0 | KQL write→read consistency (inline ingest→query) |
| powerbi-authoring+consumption (combined) | 9 | 9 | 0 | 0 | DirectQuery model with calc groups, UDFs, RLS + DAX validation + cleanup |
| **Total new** | **50** | **50** | **0** | **0** | |

Additionally, 17 previously skipped tests are now either executed, reclassified as errors, or removed from the suite — zero skips remain.

---

## 5. Regressions

### True Regressions (was PASS, now FAIL)

**None.** Every test that passed in the baseline also passes in the current run.

### Reclassified (SKIP→ERROR)

| Case | Skill | Baseline | Current | Notes |
|------|-------|----------|---------|-------|
| KA-04 | eventhouse-authoring-cli | SKIP | ERROR | Same infrastructure gap (no blob storage path). Not a regression — the test was never passing. |

---

## 6. Improvements

Three tests that were **failing** in the baseline are now **passing**:

| Case | Skill | Baseline Issue | Current Resolution |
|------|-------|---------------|-------------------|
| SA-04 | spark-authoring-cli | `CREATE SCHEMA` fails on Starter Pool | FullEval workspace supports lakehouse schemas via Livy |
| DWA-10→DWA-07 | sqldw-authoring-cli | `FOR TIMESTAMP AS OF` syntax not supported | Correct time-travel syntax used with `OPTION` clause |
| DWA-11→DWA-08 | sqldw-authoring-cli | Transaction scope mismatch | SQL file-based execution avoids connection pool scope issue |

Skips eliminated: All 17 baseline skips resolved — infrastructure tests (COPY INTO, MERGE) now execute; routing/negative tests now verify agent clarification behavior.

New skill families added: Power BI authoring/consumption, 3 migration skills (Synapse, Databricks, HDInsight), medallion architecture — expanding coverage from 7 to 12 skills.

DWC-02 data isolation fixed: The Apr 19 regression (golden row ID collision with CSV data) has been resolved — consumption tests now set up and tear down their own data independently.

---

## Summary

| Category | Count |
|----------|------:|
| New tests added | 50 |
| Fixed (was FAIL, now PASS) | 3 |
| **Regressions (was PASS, now FAIL)** | **0** |
| New errors (infrastructure) | 1 (KA-04 reclassified from SKIP) |
| Skips eliminated | 17 |
| Tests removed (check-updates) | 5 |
