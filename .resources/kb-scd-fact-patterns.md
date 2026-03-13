# SCD & Fact Pattern Reference

## Slowly Changing Dimension Decision Matrix

Use this matrix when the user describes a dimension attribute to determine the appropriate SCD strategy.

### Decision Flow

```
Is the attribute ever corrected (typo fix, data cleanup)?
  YES → SCD Type 1 (overwrite, no history of errors needed)
  NO  ↓

Does the business need to analyse history of this attribute?
  NO  → SCD Type 0 (retain original) or Type 1 (latest only)
  YES ↓

How many historical values must be accessible simultaneously?
  ONE prior value  → SCD Type 3 (previous + current columns)
  ALL values       ↓

Is the change frequency very high (>10% of rows per load)?
  YES → SCD Type 4 (split current + history tables for performance)
  NO  ↓

Do consumers need both current-state and point-in-time views easily?
  YES → SCD Type 6 (hybrid: overwrite current + keep history rows)
        or SCD Type 7 (dual key: surrogate + natural key exposed)
  NO  → SCD Type 2 (standard versioned rows)
```

## SCD2 Merge Pseudocode (Generic)

```
-- Step 1: Hash compare to detect changes
WITH source_hashed AS (
    SELECT
        BusinessKey,
        HASH(attr1, attr2, ..., attrN) AS RowHash,
        attr1, attr2, ..., attrN
    FROM staging_table
),
target_current AS (
    SELECT *
    FROM dim_table
    WHERE IsCurrent = TRUE
)

-- Step 2: Identify new, changed, and deleted
new_rows     = source_hashed WHERE BusinessKey NOT IN target_current
changed_rows = source_hashed JOIN target_current ON BusinessKey WHERE RowHash differs
deleted_rows = target_current WHERE BusinessKey NOT IN source_hashed

-- Step 3: Expire changed rows
UPDATE dim_table
SET ValidTo = @LoadTimestamp, IsCurrent = FALSE
WHERE BusinessKey IN (changed_rows.BusinessKey) AND IsCurrent = TRUE

-- Step 4: Expire deleted rows (soft delete)
UPDATE dim_table
SET ValidTo = @LoadTimestamp, IsCurrent = FALSE, IsDeleted = TRUE
WHERE BusinessKey IN (deleted_rows.BusinessKey) AND IsCurrent = TRUE

-- Step 5: Insert new and changed
INSERT INTO dim_table (SurrogateKey, BusinessKey, attr1..N, ValidFrom, ValidTo, IsCurrent, VersionNumber)
SELECT
    NEXT_SK(), BusinessKey, attr1..N,
    @LoadTimestamp,    -- ValidFrom
    '9999-12-31',      -- ValidTo (open-ended)
    TRUE,               -- IsCurrent
    COALESCE(prev.VersionNumber, 0) + 1
FROM (new_rows UNION ALL changed_rows) src
LEFT JOIN (max version per BusinessKey) prev ON src.BusinessKey = prev.BusinessKey
```

## SCD4 Split Pattern

```
dim_customer_current     (always latest, no history columns)
dim_customer_history     (all versions, with ValidFrom/ValidTo)

-- Lookup for reporting: join on BusinessKey + date range in history
-- Lookup for current state: direct join to _current table
```

## Fact Table Design Checklist

For every fact table, confirm:

1. [ ] Grain is stated in one sentence
2. [ ] All dimension FKs are identified
3. [ ] Measures classified: Additive / Semi-Additive / Non-Additive
4. [ ] Degenerate dimensions identified (e.g., InvoiceNumber)
5. [ ] Late-arriving fact strategy defined (insert with default dim key, then update?)
6. [ ] Late-arriving dimension strategy defined (insert placeholder, then retroactively fix?)
7. [ ] Null FK handling (point to "Unknown" member in dimension)
8. [ ] Snapshot frequency confirmed (for periodic/accumulating snapshots)
9. [ ] Fact table partitioning strategy (date-based for large tables)
10. [ ] Aggregate fact tables identified for performance

## Data Vault 2.0 Quick Reference

### Entity Types

| Entity | Purpose | Key | Metadata |
|---|---|---|---|
| **Hub** | Business key registry | HashKey (hash of BK) | LoadDate, RecordSource |
| **Link** | Relationship between hubs | HashKey (hash of FK combination) | LoadDate, RecordSource |
| **Satellite** | Descriptive attributes + history | Hub/Link HashKey (FK) | LoadDate, RecordSource, HashDiff |
| **PIT** (Point-in-Time) | Performance helper: snapshot of satellite state | Hub HashKey + SnapshotDate | Satellite FK pointers |
| **Bridge** | Performance helper: pre-joined link paths | Composite of Hub HashKeys | SnapshotDate |
| **Reference** | Shared code/lookup tables | Code value | LoadDate |

### Loading Rules
- Hubs & Links: INSERT only (never update, never delete)
- Satellites: INSERT new row when HashDiff changes
- PIT/Bridge: Rebuild or incremental refresh on schedule
