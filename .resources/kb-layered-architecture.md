# Layered Architecture Reference

## Layer Contracts

Each layer enforces entry and exit contracts to maintain data quality and architectural integrity.

### L0 — Landing / Raw / Bronze

**Purpose:** Bit-exact copy of source data. No transformations.

| Aspect | Specification |
|---|---|
| Entry Contract | Data arrives from registered source via approved connector |
| Schema | Source-native (may be schemaless for files) |
| Transformations | NONE — store exactly as received |
| Persistence | Immutable append (never overwrite, never delete) |
| Retention | Configurable per source (default: keep forever) |
| Metadata Added | `_LoadTimestamp`, `_SourceSystem`, `_BatchID`, `_FileName` (if file) |
| Exit Contract | Data is complete for the batch, file/table is registered in catalogue |

### L1 — Cleansed / Conformed / Silver

**Purpose:** Technical cleansing and conforming without business logic.

| Aspect | Specification |
|---|---|
| Entry Contract | Valid L0 batch exists and is complete |
| Schema | Typed, conformed column names, consistent casing |
| Transformations | Type casting, NULL handling, trimming, deduplication, key conforming |
| Persistence | Overwrite (current state) or append with dedup |
| Metadata Added | `_ValidFrom`, `_RecordHash`, `_IsDeleted` (for CDC) |
| Exit Contract | No NULLs in mandatory fields, no duplicates on business key, types valid |

### L2 — Business / Curated / Gold / DWH Core

**Purpose:** Business rules applied, dimensional model built, history managed.

| Aspect | Specification |
|---|---|
| Entry Contract | L1 data passes all quality gates |
| Schema | Star Join, Snowflake, or Data Vault as per architecture decision |
| Transformations | Business rules, SCD processing, fact loading, key lookups |
| Persistence | SCD for dimensions, append/merge for facts |
| Metadata Added | `_SurrogateKey`, `_ValidFrom`, `_ValidTo`, `_IsCurrent`, `_VersionNumber` |
| Exit Contract | Referential integrity maintained, all FK resolved, business rules applied |

### L3 — Consumption / Semantic / Mart

**Purpose:** Use-case-specific aggregations and denormalisations.

| Aspect | Specification |
|---|---|
| Entry Contract | L2 data is complete for the reporting period |
| Schema | Flat/wide tables, materialised views, semantic model entities |
| Transformations | Aggregation, pivoting, KPI calculations, denormalisation |
| Persistence | Rebuild/refresh on schedule |
| Metadata Added | `_RefreshTimestamp` |
| Exit Contract | Matches expected row counts / KPI validation, ready for consumption |

### L4 — Real-Time / Hot / Stream

**Purpose:** Low-latency event data for operational or near-real-time analytics.

| Aspect | Specification |
|---|---|
| Entry Contract | Event arrives via stream/topic from registered producer |
| Schema | Event schema (Avro/JSON/Protobuf), may be semi-structured |
| Transformations | Windowed aggregations, enrichment joins, deduplication |
| Persistence | Windowed/time-bound retention, append to hot store |
| Metadata Added | `_EventTime`, `_ProcessingTime`, `_PartitionKey` |
| Exit Contract | Event processed within SLA, duplicates handled, dead-letter for failures |

## Layer Flow Rules

1. Data flows **forward only**: L0 → L1 → L2 → L3 (and L4 parallel)
2. **No backward dependencies**: L1 must not read from L2
3. **Cross-layer shortcuts forbidden** unless documented in an ADR
4. L4 (real-time) may feed into L1 or L2 via a micro-batch bridge
5. Each layer transition = exactly one pipeline step type

## Quality Gate Template

At every layer boundary, apply:

```
Quality Gate: L{N} → L{N+1}
├── Schema Validation: Column names, types, nullability match target contract
├── Completeness Check: Row count within expected range (±threshold)
├── Uniqueness Check: No duplicates on declared business key
├── Freshness Check: Data timestamp within SLA window
├── Referential Integrity: All foreign keys resolve (L2+ only)
└── Business Rule Validation: Custom rules per object (L2+ only)

On FAIL:
├── Severity = WARN  → Log warning, continue, flag for review
└── Severity = FAIL  → Halt pipeline, send alert, do NOT promote data
```
