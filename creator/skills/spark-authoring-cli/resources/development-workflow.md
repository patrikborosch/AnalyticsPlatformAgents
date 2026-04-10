# Development Workflow — Skill Resource

Essential workflow patterns for Spark notebook development in Microsoft Fabric.

## Recommended patterns

### Must

1. **Always validate notebook JSON structure** before deployment — malformed JSON causes deployment failures
2. **Use base64 encoding** for notebook content in Fabric API calls — required by REST API specification
3. **Test locally first** with sample data before deploying to Fabric — catch logic errors early
4. **Use parameterized notebooks** for reusability across environments — avoid hardcoded values
5. **Follow PySpark best practices** — proper DataFrame operations, avoid driver memory issues

### Prefer

1. **Local development workflow** — develop in Jupyter locally, validate, then deploy to Fabric
2. **Session reuse** over creating new sessions — faster iteration during development
3. **Incremental development** — test small changes before full deployments

### Avoid

1. **Don't hardcode connection strings** or workspace IDs — use parameters and configuration
2. **Don't skip local testing** — always validate transformation logic before deploying
3. **Don't commit secrets** to notebooks — use secure parameter passing and Azure Key Vault

---

## Notebook Lifecycle

### Development Phase
Guide LLM to generate notebooks following:
1. **Local development**: Create `.ipynb` file with Jupyter, use local Spark session for testing
2. **Cell structure**: Organize as Parameters → Setup → Logic → Validation → Cleanup
3. **Parameter cell**: First code cell should define configurable parameters with defaults
4. **Imports cell**: Import all dependencies upfront to catch missing packages early
5. **Validation cell**: Add checks at end to validate output (row counts, schema, sample data)

### Deployment Phase
Prompt LLM to generate deployment commands:
1. **Convert to JSON**: Notebook must be valid JSON with cells array
2. **Base64 encode**: Content must be base64-encoded for Fabric REST API
3. **Create notebook item**: POST to `/workspaces/{id}/items` with type="Notebook"
4. **Update definition**: POST to `/workspaces/{id}/items/{notebookId}/updateDefinition` with payload

### Execution Phase
Guide LLM for execution patterns:
1. **On-demand execution**: POST to Livy sessions endpoint to run notebook interactively
2. **Pipeline execution**: Embed notebook in pipeline activity with parameter overrides
3. **Scheduled execution**: Create a schedule via Job Scheduling in COMMON-CLI.md
4. **Monitoring**: Query Livy session state or pipeline run status to track progress

---

## Parameterization Patterns

### When to Parameterize
Tell LLM to make these configurable:
- **Data paths**: Source file paths, target table names, partition values
- **Processing dates**: Date ranges for incremental loads, effective dates
- **Environment settings**: Workspace IDs, lakehouse IDs (different per dev/test/prod)
- **Business logic**: Thresholds, filters, feature flags

### Parameter Injection Methods

Guide LLM to implement one of these patterns:

**Method 1: Default Parameters in Notebook**
- First code cell should define parameters with default values
- Parameters: paths, table names, processing dates, business thresholds
- LLM generates: variable assignments that can be overridden by pipeline

**Method 2: Pipeline Activity Parameters**
- Pipeline JSON definition includes parameters section
- Parameters mapped to notebook parameter names
- LLM generates: Pipeline JSON with "parameters" object, notebook references
- Use expressions like @formatDateTime() for dynamic values

**Method 3: Livy Session Parameters**
- Pass parameters via Livy API during session creation or statement execution
- LLM generates: API calls with parameter payload in request body

**Method 4: Variable Library**
- Create a Variable Library item to store config (lakehouse names, workspace IDs, feature flags)
- Use Value Sets (`valueSets/dev.json`, `valueSets/prod.json`) to promote across environments without code changes
- Boolean values are returned as strings — compare with `.lower() == "true"`, not `bool()`

*In Notebooks:*
- Read with `notebookutils.variableLibrary.getLibrary("LibName").variable_name` (dot notation)
- **NEVER** use `.get("lib", "var")` — it does not exist and causes runtime failure

*In Data Pipelines:*
1. Declare `libraryVariables` in pipeline `properties` (sibling to `activities`):
   ```json
   "libraryVariables": {
     "notebook_id": {
       "libraryName": "sales_analytics_config",
       "libraryId": "<variable-library-item-id>",
       "variableName": "notebook_id",
       "type": "String"
     }
   }
   ```
2. Reference via expression syntax in activity `typeProperties`:
   ```json
   "notebookId": {
     "value": "@pipeline().libraryVariables.notebook_id",
     "type": "Expression"
   }
   ```
- Each entry needs `libraryName`, `libraryId`, `variableName`, and `type`
- Use `@pipeline().libraryVariables.<name>` — not `@variables()` (that is for regular pipeline variables)

### Configuration Management
Guide LLM to generate:
- **Environment-specific configs**: Separate JSON files for dev/test/prod with workspace IDs, paths
- **Config loading pattern**: Read from OneLake Files or environment variables
- **Validation**: Assert required parameters are present before proceeding

---

## Local Testing Strategy

### Setup Local Environment
Prompt LLM to generate setup for:
1. **Install PySpark**: `pip install pyspark delta-spark` for local Spark session
2. **Install Jupyter**: `pip install jupyter notebook` for interactive development
3. **Sample data**: Create small CSV/Parquet files locally to simulate Fabric data
4. **Mock Fabric paths**: Use local file paths during dev, swap to `abfss://` for Fabric deployment

### Testing Transformation Logic
Guide LLM to test:
- **Create test DataFrame**: Use `spark.createDataFrame()` with sample data and explicit schema
- **Run transformation**: Execute the notebook's core logic on test data
- **Assert results**: Validate output row count, column values, schema matches expectations
- **Edge cases**: Test with nulls, empty DataFrames, duplicate keys

### Local vs Fabric Differences
Make LLM aware of:
- **Spark session**: Local requires explicit creation; Fabric provides pre-configured `spark` object
- **OneLake access**: Local can't access OneLake; use local files or mounted Azure Storage
- **Livy API**: Only available in Fabric; local testing can't validate Livy-specific features
- **Lakehouse tables**: Local uses Hive metastore; Fabric uses OneLake managed tables

---

## Debugging Patterns

### Livy Session Debugging
When errors occur in Fabric, guide LLM to:
1. **Check session state**: GET `/livyapi/versions/2023-12-01/sessions/{id}` to see if session is idle/busy/error
2. **Retrieve session log**: GET session log endpoint to see driver/executor logs
3. **Statement-level debugging**: Execute statements individually to isolate failing code
4. **Resource issues**: Check if error is memory-related (OOM), timeout, or network connectivity

### Common Error Patterns

**Schema mismatch**:
- Symptom: "Cannot merge incompatible schemas"
- Fix: Ensure source DataFrame columns match target table schema exactly
- Prevention: Define explicit schemas, validate before write

**Path not found**:
- Symptom: "Path does not exist: abfss://..."
- Fix: Verify lakehouse ID, file path, check OneLake permissions
- Prevention: Test paths with `.ls()` or simple read before complex operations

**Out of memory**:
- Symptom: "java.lang.OutOfMemoryError" or driver/executor crashes
- Fix: Add `.repartition()` or `.coalesce()`, reduce data volume, increase executor memory
- Prevention: Avoid `.collect()`, limit `.count()` calls, cache judiciously

**Livy session timeout**:
- Symptom: Session in "dead" state or statements not executing
- Fix: Recreate session, check network connectivity, verify lakehouse accessibility
- Prevention: Use session heartbeat, handle long-running operations with checkpoints

### Logging Best Practices
Prompt LLM to add logging:
- **Progress indicators**: Log after each major step (read, transform, write)
- **Row counts**: Log DataFrame counts to track data flow
- **Timing**: Record start/end timestamps for performance analysis
- **Error context**: Log input parameters, DataFrame sample when errors occur

### Incremental Debugging Strategy
Guide LLM to debug systematically:
1. **Isolate failure**: Comment out sections to identify failing cell
2. **Simplify input**: Test with small sample (`.limit(100)`) to reproduce faster
3. **Add visibility**: Insert `.show()` and `.printSchema()` to inspect intermediate state
4. **Check assumptions**: Validate data types, nulls, distributions match expectations
5. **Divide and conquer**: Break complex transformations into smaller steps with validation between
