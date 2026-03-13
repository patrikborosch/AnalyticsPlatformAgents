# Fabric Data Type Mapping Reference

## Logical → Physical Type Mapping

### Lakehouse (Apache Spark / Delta Lake)

| Logical Type | Spark Type | PySpark Type | Delta Manifest Type | Notes |
|---|---|---|---|---|
| TINYINT | `TINYINT` | `ByteType()` | `byte` | 8-bit signed integer |
| SMALLINT | `SMALLINT` | `ShortType()` | `short` | 16-bit signed integer |
| INT | `INT` | `IntegerType()` | `integer` | 32-bit signed integer |
| BIGINT | `BIGINT` | `LongType()` | `long` | 64-bit (surrogate keys, BatchID) |
| DECIMAL(p,s) | `DECIMAL(p,s)` | `DecimalType(p,s)` | `decimal(p,s)` | Exact numeric (money, prices) |
| FLOAT | `FLOAT` | `FloatType()` | `float` | 32-bit IEEE 754 |
| DOUBLE | `DOUBLE` | `DoubleType()` | `double` | 64-bit IEEE 754 |
| BOOLEAN | `BOOLEAN` | `BooleanType()` | `boolean` | true/false |
| VARCHAR(n) | `STRING` | `StringType()` | `string` | Unbounded — enforce length via QC |
| CHAR(n) | `STRING` | `StringType()` | `string` | No fixed-width in Spark |
| TEXT | `STRING` | `StringType()` | `string` | Long text |
| DATE | `DATE` | `DateType()` | `date` | Calendar date only |
| DATETIME | `TIMESTAMP` | `TimestampType()` | `timestamp` | Date + time (microsecond precision) |
| TIMESTAMP_NTZ | `TIMESTAMP_NTZ` | `TimestampNTZType()` | `timestamp_ntz` | Without timezone (Spark 3.4+) |
| BINARY | `BINARY` | `BinaryType()` | `binary` | Raw bytes (hash storage) |
| BINARY (as hex) | `STRING` | `StringType()` | `string` | SHA-256 hex string (64 chars) |

### Warehouse (T-SQL)

| Logical Type | T-SQL Type | Storage | Notes |
|---|---|---|---|
| TINYINT | `TINYINT` | 1 byte | 0 to 255 |
| SMALLINT | `SMALLINT` | 2 bytes | -32,768 to 32,767 |
| INT | `INT` | 4 bytes | Standard integer |
| BIGINT | `BIGINT` | 8 bytes | Surrogate keys, BatchIDs |
| DECIMAL(p,s) | `DECIMAL(p,s)` | 5-17 bytes | Exact numeric, max p=38 |
| FLOAT | `FLOAT` | 8 bytes | Approximate numeric |
| REAL | `REAL` | 4 bytes | 32-bit approximate |
| BOOLEAN | `BIT` | 1 bit | 0 or 1 |
| VARCHAR(n) | `VARCHAR(n)` | n+2 bytes | Variable-length, n ≤ 8000 |
| VARCHAR(MAX) | `VARCHAR(MAX)` | up to 2GB | Long text |
| NVARCHAR(n) | `NVARCHAR(n)` | 2n+2 bytes | Unicode, n ≤ 4000 |
| CHAR(n) | `CHAR(n)` | n bytes | Fixed-width |
| DATE | `DATE` | 3 bytes | Calendar date only |
| DATETIME | `DATETIME2(3)` | 7 bytes | Millisecond precision (recommended over DATETIME) |
| DATETIME (high precision) | `DATETIME2(7)` | 8 bytes | 100-nanosecond precision |
| BINARY | `VARBINARY(32)` | 32 bytes | SHA-256 raw bytes |
| BINARY (as hex) | `VARCHAR(64)` | 66 bytes | SHA-256 hex string |
| UNIQUEIDENTIFIER | `UNIQUEIDENTIFIER` | 16 bytes | GUID |

### Eventhouse (KQL / Kusto)

| Logical Type | KQL Type | Notes |
|---|---|---|
| INT | `int` | 32-bit signed |
| BIGINT | `long` | 64-bit signed |
| DECIMAL | `decimal` | 128-bit exact |
| FLOAT/DOUBLE | `real` | 64-bit IEEE 754 |
| BOOLEAN | `bool` | true/false |
| VARCHAR | `string` | Unicode text |
| DATE | `datetime` | No date-only — stored as datetime midnight |
| DATETIME | `datetime` | Tick resolution (100ns) |
| TIMESPAN | `timespan` | Duration |
| BINARY | `string` | Store hex-encoded |
| GUID | `guid` | 128-bit GUID |
| JSON | `dynamic` | Semi-structured JSON object |

## Type Mapping Between Layers

When data flows between layers (Lakehouse → Warehouse), types must be compatible:

| Spark (L1 Lakehouse) | T-SQL (L2 Warehouse) | Auto-Compatible | Notes |
|---|---|---|---|
| `STRING` | `VARCHAR(n)` | Yes | Specify max length in Warehouse DDL |
| `INT` | `INT` | Yes | Direct mapping |
| `BIGINT` | `BIGINT` | Yes | Direct mapping |
| `DECIMAL(p,s)` | `DECIMAL(p,s)` | Yes | Match precision and scale |
| `DOUBLE` | `FLOAT` | Yes | Both 64-bit |
| `BOOLEAN` | `BIT` | Yes | Spark true/false → SQL 1/0 |
| `DATE` | `DATE` | Yes | Direct mapping |
| `TIMESTAMP` | `DATETIME2(3)` | Yes | Precision may differ — use DATETIME2(6) for microseconds |
| `BINARY` | `VARBINARY(n)` | Yes | Specify length in Warehouse |

## SCD2 System Column Types

| Column | Lakehouse (Spark) | Warehouse (T-SQL) | Notes |
|---|---|---|---|
| `SK_<Entity>` | `BIGINT` | `BIGINT` | Surrogate key — monotonically increasing |
| `BK_<Entity>` | `STRING` | `VARCHAR(50-200)` | Business key — size depends on source |
| `_RowHash` | `STRING` (SHA-256 hex) | `VARCHAR(64)` | 64-char hex string |
| `_ValidFrom` | `TIMESTAMP` | `DATETIME2(3)` | Version start |
| `_ValidTo` | `TIMESTAMP` | `DATETIME2(3)` | Version end (9999-12-31 for current) |
| `_IsCurrent` | `BOOLEAN` | `BIT` | Active version flag |
| `_VersionNumber` | `INT` | `INT` | Version counter |
| `_IsDeleted` | `BOOLEAN` | `BIT` | Soft-delete flag |
| `_BatchID` | `BIGINT` | `BIGINT` | Load batch reference |
| `_LoadTimestamp` | `TIMESTAMP` | `DATETIME2(3)` | Row write time |
