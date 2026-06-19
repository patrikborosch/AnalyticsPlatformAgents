# Eval Plan: fabriciq

## Skill Overview
- **Skill:** `fabriciq`
- **Category:** Power BI Data Analysis via FabricIQ MCP Tools
- **Purpose:** Query Power BI data through the Fabric MCP endpoint using multi-step orchestration — discover artifacts, inspect report metadata and semantic model schemas, resolve entity values, generate DAX queries, and execute them

## Pre-requisites
- Fabric workspace with capacity assigned — uses `EVAL_WORKSPACE` from Phase 0
- Authentication configured (`az login`)
- Shared `{{LAKEHOUSE}}` lakehouse provisioned by runner (Phase 0b)
- FabricIQ MCP server available (DiscoverArtifacts, GetReportMetadata, GetSemanticModelSchema, ValueSearch, ExecuteQuery tools)
- Semantic model `eval_sales_directlake` provisioned (shared with semantic-model-consumption eval — see that plan's Data Setup)

## Data Setup (run FIRST — before any test cases)

This plan reuses the `eval_sales_directlake` semantic model provisioned by the `semantic-model-consumption` eval plan. Ensure that plan's data setup has completed before running these cases.

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### FIQ-01: Discover a Semantic Model by Name
- **Prompt:** "Find the eval_sales_directlake semantic model"
- **Expected:** Agent calls `DiscoverArtifacts` with search text matching the model name and returns the artifact details
- **Pass criteria:**
  - Agent invokes `DiscoverArtifacts` tool (not manual REST calls)
  - Result includes the `eval_sales_directlake` semantic model with its artifact ID
  - Agent presents the finding clearly without exposing internal tool names

### FIQ-02: Inspect Semantic Model Schema
- **Prompt:** "What tables and measures are available in eval_sales_directlake in workspace {{WORKSPACE}}?"
- **Expected:** Agent discovers the artifact, then calls `GetSemanticModelSchema` to retrieve structure
- **Pass criteria:**
  - Agent invokes `GetSemanticModelSchema` tool
  - Response lists tables: SalesTransactions, Products
  - Response lists measures: Total Revenue, Average Price
  - Presentation is user-friendly (no raw JSON or tool names exposed)

### FIQ-03: Resolve Entity Values Before Querying
- **Prompt:** "What is the total revenue for Electronics products in eval_sales_directlake?"
- **Expected:** Agent calls `ValueSearch` to resolve "Electronics" to its exact column location, then generates and executes a DAX query with the resolved value
- **Pass criteria:**
  - Agent invokes `ValueSearch` with "Electronics" before generating DAX
  - Agent invokes `ExecuteQuery` with a DAX query filtering on the resolved column/value
  - Result shows a numeric total revenue value for Electronics
  - Answer leads with the finding and bolds the key number

### FIQ-04: End-to-End Data Question (Aggregation)
- **Prompt:** "Show me total revenue by product category from eval_sales_directlake"
- **Expected:** Agent orchestrates the full workflow: discover → schema → generate DAX → execute → present
- **Pass criteria:**
  - Agent invokes `GetSemanticModelSchema` (or uses cached schema from prior call)
  - Agent invokes `ExecuteQuery` with a DAX query that groups by category and sums revenue
  - Result shows a table with category names and revenue amounts
  - All 5 categories present (Electronics, Clothing, Food, Home, Sports)
  - Answer is formatted as a text table with bold key numbers

### FIQ-05: Follow-up Question (Same Artifact Context)
- **Prompt:** (following FIQ-04) "Which category has the highest average price?"
- **Expected:** Agent reuses the same artifact context and executes a new DAX query without re-discovering
- **Pass criteria:**
  - Agent does NOT call `DiscoverArtifacts` again (reuses artifact ID from prior turn)
  - Agent invokes `ExecuteQuery` with a DAX query computing average unit_price by category
  - Result identifies the category with the highest average price
  - Answer is concise and leads with the finding

### FIQ-06: Natural Language Question Without Mentioning Artifact
- **Prompt:** "What are the top 3 products by total sales amount?"
- **Expected:** Agent discovers the relevant semantic model, inspects schema, generates appropriate DAX, and presents results
- **Pass criteria:**
  - Agent invokes `DiscoverArtifacts` to find a suitable model (or reuses if in same session)
  - Agent generates DAX with TOPN or ORDER BY + top 3 logic
  - Agent invokes `ExecuteQuery` and presents top 3 products with sales amounts
  - No DAX syntax or tool names visible in the answer
