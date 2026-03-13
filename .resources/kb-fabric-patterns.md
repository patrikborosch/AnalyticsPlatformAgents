# Fabric Implementation Patterns

## Pattern 1: Generic Metadata-Driven Ingestion (L0 Landing)

### Copy Activity Pattern (Pipeline)
For database sources (SQL Server, DB2, Oracle):

```
Pipeline: pl_ingest_<source_system>
Activity: Copy Data
  Source:
    Type: DatabaseSource (parameterised)
    Connection: from meta.Source.ConnectionString
    Query: Built from meta.SourceObject (table name + optional WHERE for incremental)
  Sink:
    Type: Lakehouse Table
    Target: lh_landing.raw_<source_object>
    Write Mode: Append
    Additional Columns:
      _BatchID: @pipeline().parameters.BatchID
      _LoadTimestamp: @utcnow()
      _SourceSystem: @pipeline().parameters.SourceName
      _SourceObject: @pipeline().parameters.ObjectName
```

### Notebook Pattern (Files)
For file sources (CSV, JSON, Parquet, Excel, XML):

```python
# nb_ingest_file — parameterised Notebook

# Parameters
batch_id = int(getArgument("batch_id"))
source_object_id = int(getArgument("source_object_id"))

# Read metadata
source_obj = spark.sql(f"""
    SELECT so.*, s.SourceName 
    FROM wh_meta.meta.SourceObject so
    JOIN wh_meta.meta.Source s ON so.SourceID = s.SourceID
    WHERE so.SourceObjectID = {source_object_id}
""").first()

# Read file based on format
file_path = f"Files/incoming/{source_obj.SourceName}/{source_obj.ObjectName}"
if source_obj.FileFormat == 'CSV':
    df = spark.read.csv(file_path, header=True, inferSchema=True, 
                         delimiter=source_obj.FileDelimiter or ',')
elif source_obj.FileFormat == 'JSON':
    df = spark.read.json(file_path)
elif source_obj.FileFormat == 'Parquet':
    df = spark.read.parquet(file_path)
elif source_obj.FileFormat == 'Excel':
    # Requires com.crealytics:spark-excel library
    df = spark.read.format("com.crealytics.spark.excel") \
        .option("header", "true").load(file_path)
elif source_obj.FileFormat == 'XML':
    df = spark.read.format("xml").option("rowTag", "record").load(file_path)

# Add system columns
from pyspark.sql.functions import lit, current_timestamp
df = df.withColumn("_BatchID", lit(batch_id)) \
       .withColumn("_LoadTimestamp", current_timestamp()) \
       .withColumn("_SourceSystem", lit(source_obj.SourceName)) \
       .withColumn("_SourceObject", lit(source_obj.ObjectName)) \
       .withColumn("_FileName", lit(file_path))

# Write to L0 landing table
df.write.mode("append").saveAsTable(f"raw_{source_obj.ObjectName.lower()}")
```

## Pattern 2: Generic SCD2 Merge (L1 Persistence)

### Full PySpark Implementation Pattern

```python
# nb_scd2_merge — the core generic SCD2 Notebook

from delta.tables import DeltaTable
from pyspark.sql.functions import (
    col, lit, current_timestamp, sha2, concat_ws, coalesce, max as spark_max
)

# Parameters
batch_id = int(getArgument("batch_id"))
source_object_id = int(getArgument("source_object_id"))
target_object_id = int(getArgument("target_object_id"))

# 1. Read metadata
mappings = spark.sql(f"""
    SELECT m.*, tr.RuleName, tr.RuleType, tr.RuleCode, tr.Parameters
    FROM wh_meta.meta.Mapping m
    LEFT JOIN wh_meta.meta.TransformationRule tr ON m.TransformationRuleID = tr.RuleID
    WHERE m.SourceObjectID = {source_object_id} 
    AND m.TargetObjectID = {target_object_id}
    AND m.IsActive = 1
    ORDER BY m.OrdinalPosition
""").collect()

target_obj = spark.sql(f"""
    SELECT * FROM wh_meta.meta.TargetObject WHERE TargetObjectID = {target_object_id}
""").first()

target_table = target_obj.ObjectName
bk_columns = target_obj.BusinessKeyColumns.split(",")

# 2. Read source batch from L0
source_table = spark.sql(f"""
    SELECT so.ObjectName FROM wh_meta.meta.SourceObject 
    WHERE SourceObjectID = {source_object_id}
""").first().ObjectName

source_df = spark.read.table(f"lh_landing.raw_{source_table.lower()}") \
    .filter(f"_BatchID = {batch_id}")

# 3. Build dynamic SELECT with injected transformations
select_exprs = []
scd_tracked_cols = []
for m in mappings:
    if m.RuleType and m.RuleType != 'DirectCopy':
        expr = m.RuleCode.replace("{source_column}", m.SourceColumn)
        if m.Parameters:
            for i, p in enumerate(m.Parameters.split(","), 1):
                expr = expr.replace(f"{{param{i}}}", p.strip())
        select_exprs.append(f"{expr} AS {m.TargetColumn}")
    else:
        select_exprs.append(f"`{m.SourceColumn}` AS {m.TargetColumn}")
    
    if m.IsSCDTracked:
        scd_tracked_cols.append(m.TargetColumn)

transformed_df = source_df.selectExpr(*select_exprs)

# 4. Compute _RowHash
transformed_df = transformed_df.withColumn(
    "_RowHash", sha2(concat_ws("||", *[col(c).cast("string") for c in scd_tracked_cols]), 256)
)

# 5. Record Delta version for rollback
delta_table = DeltaTable.forName(spark, target_table)
pre_load_version = spark.sql(f"DESCRIBE HISTORY {target_table} LIMIT 1") \
    .select("version").first()[0]

# 6. SCD2 MERGE
merge_condition = " AND ".join([f"tgt.{bk} = src.{bk}" for bk in bk_columns])
merge_condition += " AND tgt._IsCurrent = true"

# Step 6a: Expire changed and deleted rows
delta_table.alias("tgt").merge(
    transformed_df.alias("src"),
    merge_condition
).whenMatchedUpdate(
    condition="tgt._RowHash != src._RowHash",
    set={
        "_IsCurrent": lit(False),
        "_ValidTo": current_timestamp()
    }
).execute()

# Step 6b: Insert new and changed rows
# Get max SK for sequence
max_sk = spark.sql(f"SELECT COALESCE(MAX(SK_{target_table.replace('dim_','')}), 0) FROM {target_table}").first()[0]

# Build new version rows
new_and_changed = transformed_df.alias("src").join(
    spark.read.table(target_table).filter("_IsCurrent = true").alias("tgt"),
    [col(f"src.{bk}") == col(f"tgt.{bk}") for bk in bk_columns],
    "left"
).filter("tgt._IsCurrent IS NULL OR tgt._RowHash != src._RowHash")

# ... (Creator Agent completes with full column assignments, SK generation, INSERT)

# 7. Log result
rows_inserted = new_and_changed.count()
# Write to wh_meta.audit.LoadLog
```

## Pattern 3: Current-State Projection (L1 → L2)

### T-SQL Stored Procedure Pattern

```sql
CREATE PROCEDURE [present].[sp_refresh_current_state]
    @BatchID BIGINT,
    @TargetObjectID INT
AS
BEGIN
    SET NOCOUNT ON;
    
    DECLARE @TargetTable NVARCHAR(200);
    DECLARE @SourceTable NVARCHAR(200);
    DECLARE @BKColumns NVARCHAR(500);
    DECLARE @RowsAffected INT;
    
    -- Read metadata
    SELECT @TargetTable = t.ObjectName,
           @BKColumns = t.BusinessKeyColumns
    FROM [wh_meta].[meta].[TargetObject] t
    WHERE t.TargetObjectID = @TargetObjectID;
    
    -- Source is the L1 Lakehouse table (via Shortcut)
    -- Shortcut name matches the L1 table name
    SET @SourceTable = '[lh_persist_shortcut].[dbo].[' + @TargetTable + ']';
    
    -- Dynamic MERGE (generic pattern)
    -- Creator Agent generates the full dynamic SQL based on Mapping metadata
    -- Or: one stored procedure per table generated from metadata at deployment time
    
    BEGIN TRY
        -- MERGE current state
        -- ... (dynamic SQL built from metadata column list)
        
        SET @RowsAffected = @@ROWCOUNT;
        
        -- Log success
        INSERT INTO [wh_meta].[audit].[LoadLog] 
            (BatchID, PipelineID, TargetObjectID, OperationType, StartTime, EndTime,
             RowsInserted, Status)
        VALUES 
            (@BatchID, NULL, @TargetObjectID, 'Load', GETDATE(), GETDATE(),
             @RowsAffected, 'Success');
    END TRY
    BEGIN CATCH
        -- Log failure
        INSERT INTO [wh_meta].[audit].[LoadLog]
            (BatchID, TargetObjectID, OperationType, Status, ErrorMessage)
        VALUES
            (@BatchID, @TargetObjectID, 'Load', 'Failed', ERROR_MESSAGE());
        THROW;
    END CATCH
END;
```

## Pattern 4: Metadata-Driven Pipeline Orchestration

### Main Pipeline Activity Flow

```
pl_main_orchestrator
├── Set Variable: BatchID = @pipeline().RunId hash
├── Lookup: Get active PipelineSteps (ordered by StepOrder)
│   → Source: wh_meta.meta.PipelineStep WHERE PipelineID = @param AND IsActive = 1
├── ForEach: step in @activity('Lookup').output.value
│   ├── Switch: on step.StepType
│   │   ├── Case 'Extract':
│   │   │   ├── If Condition: SourceObject.ObjectType == 'File'
│   │   │   │   ├── True:  Notebook 'nb_ingest_file' (batch_id, source_object_id)
│   │   │   │   └── False: Copy Activity (parameterised source connection)
│   │   ├── Case 'Transform':
│   │   │   ├── If Condition: TargetObject.LoadPattern == 'SCD2'
│   │   │   │   ├── True:  Notebook 'nb_scd2_merge' (batch_id, source_id, target_id)
│   │   │   │   └── False: Notebook 'nb_incremental_load' (batch_id, source_id, target_id)
│   │   ├── Case 'Load':
│   │   │   └── Stored Procedure 'sp_refresh_current_state' (@BatchID, @TargetObjectID)
│   │   └── Case 'QualityCheck':
│   │       └── Notebook 'nb_quality_check' (batch_id, target_object_id)
│   │           ├── On Success: continue
│   │           └── On Failure: Notebook 'nb_rollback' → Fail Activity
│   └── On Each Failure: Log error, continue or fail based on Pipeline.ErrorHandling
└── Stored Procedure: sp_log_pipeline_complete (@BatchID, 'Complete')
```

## Pattern 5: Cross-Workspace Access via Shortcuts

### Setting Up Shortcuts

```
Scenario: L2 Warehouse needs to read L1 Lakehouse tables

1. In ws-present (Warehouse workspace):
   - Create Shortcut in wh_present pointing to:
     Source: OneLake → ws-persist → lh_persist → Tables → dim_customer
     Name: lh_persist_dim_customer

2. The Warehouse can now query:
   SELECT * FROM [lh_persist_dim_customer].[dbo].[dim_customer]
   
   Or via three-part naming if Lakehouse SQL Endpoint is used
```

### Cross-Database Queries (Warehouse → Lakehouse)

```sql
-- In Warehouse stored procedure:
-- Query Lakehouse tables via SQL Analytics Endpoint
SELECT * 
FROM [lh_persist].[dbo].[dim_customer]  -- three-part name via linked connection
WHERE _IsCurrent = 1
```

## Pattern 6: Delta Lake Configuration

### Recommended Delta Properties for L1 Tables

```python
# Set at table creation or via ALTER TABLE
spark.sql("""
    ALTER TABLE dim_customer SET TBLPROPERTIES (
        'delta.autoOptimize.optimizeWrite' = 'true',
        'delta.autoOptimize.autoCompact' = 'true',
        'delta.logRetentionDuration' = 'interval 30 days',
        'delta.deletedFileRetentionDuration' = 'interval 30 days'
    )
""")

# Z-ORDER for SCD2 lookup performance
spark.sql("OPTIMIZE dim_customer ZORDER BY (BK_Customer)")
```

### Partition Strategy

| Table Type | Partition Column | Rationale |
|---|---|---|
| L0 raw tables | `_BatchID` | Efficient batch-level reads and purges |
| L1 fact tables | Date FK column | Range scans for time-based queries |
| L1 dim tables | None (Z-ORDER on BK) | Dims are typically small enough; Z-ORDER on BK is more effective |
| L2 fact tables | Date column | Same as L1 |

## Pattern 7: Quality Check Implementation

```python
# nb_quality_check — generic quality check Notebook

batch_id = int(getArgument("batch_id"))
target_object_id = int(getArgument("target_object_id"))

# Read quality rules from metadata
rules = spark.sql(f"""
    SELECT * FROM wh_meta.meta.QualityRule
    WHERE TargetObjectID = {target_object_id}
""").collect()

target_obj = spark.sql(f"""
    SELECT ObjectName FROM wh_meta.meta.TargetObject 
    WHERE TargetObjectID = {target_object_id}
""").first()

failures = []
warnings = []

for rule in rules:
    if rule.RuleType == 'NotNull':
        count = spark.sql(f"""
            SELECT COUNT(*) FROM {target_obj.ObjectName} 
            WHERE {rule.RuleExpression.replace('IS NOT NULL', 'IS NULL')}
            AND _BatchID = {batch_id}
        """).first()[0]
        if count > 0:
            if rule.Severity == 'Rollback':
                failures.append(f"{rule.RuleName}: {count} NULL values found")
            else:
                warnings.append(f"{rule.RuleName}: {count} NULL values found")
    
    elif rule.RuleType == 'Unique':
        # Check for duplicates on BK where IsCurrent = true
        count = spark.sql(f"""
            SELECT COUNT(*) - COUNT(DISTINCT {rule.RuleExpression.split('(')[0].strip()})
            FROM {target_obj.ObjectName}
            WHERE _IsCurrent = true
        """).first()[0]
        if count > 0:
            if rule.Severity == 'Rollback':
                failures.append(f"{rule.RuleName}: {count} duplicate keys")
            else:
                warnings.append(f"{rule.RuleName}: {count} duplicate keys")
    
    # ... additional rule types

# Log results
for w in warnings:
    # Log warning to LoadLog
    pass

if failures:
    # Log failures and raise exception for pipeline to catch
    raise Exception(f"Quality check failed: {'; '.join(failures)}")

# Return success
mssparkutils.notebook.exit(f"QC passed. Warnings: {len(warnings)}")
```

## Pattern 8: Rollback via Delta Time Travel

```python
# nb_rollback — restore table to pre-load version

batch_id = int(getArgument("batch_id"))
target_object_id = int(getArgument("target_object_id"))

# Look up the pre-load version from RollbackSnapshot
snapshot_info = spark.sql(f"""
    SELECT * FROM wh_meta.audit.RollbackSnapshot
    WHERE BatchID = {batch_id} AND TargetObjectID = {target_object_id}
    AND Status = 'Active'
""").first()

target_table = spark.sql(f"""
    SELECT ObjectName FROM wh_meta.meta.TargetObject
    WHERE TargetObjectID = {target_object_id}
""").first().ObjectName

if snapshot_info:
    # RESTORE using Delta Time Travel
    version = snapshot_info.SnapshotLocation  # stored as version number
    spark.sql(f"RESTORE TABLE {target_table} TO VERSION AS OF {version}")
    
    # Mark snapshot as applied
    spark.sql(f"""
        UPDATE wh_meta.audit.RollbackSnapshot 
        SET Status = 'Applied' 
        WHERE SnapshotID = {snapshot_info.SnapshotID}
    """)
    
    # Trigger L2 rebuild for this table
    # Call sp_refresh_current_state via JDBC or pipeline
    
    # Log rollback
    # Write to wh_meta.audit.LoadLog
else:
    raise Exception(f"No active snapshot found for BatchID {batch_id}, TargetObjectID {target_object_id}")
```
