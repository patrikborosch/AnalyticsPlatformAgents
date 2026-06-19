# Combined Eval: Power BI Semantic Model Authoring + Consumption (Adventure Works DW — DirectQuery)

## Purpose
Verify that a DirectQuery semantic model with advanced features created by `semantic-model-authoring` against Adventure Works DW data in a Fabric data warehouse is correctly queryable and inspectable via `semantic-model-consumption` (DAX queries). Covers eight feature areas: (1) calculation groups with user-defined functions for YoY/YTD time intelligence, (2) inactive relationship with two USERELATIONSHIP measures, (3) user hierarchy, (4) non-English culture, (5) table/measure translations, (6) RLS security role, (7) role-member assignment, and (8) DAX data-validation queries.

## Flow
```
semantic-model-authoring (WRITE — DirectQuery model in EVAL_WORKSPACE)
  → Fabric Semantic Model
  → semantic-model-consumption (READ via DAX)
```

## Pre-requisites
- Fabric workspace with capacity assigned (semantic model target) — uses `EVAL_WORKSPACE` from Phase 0
- Shared `{{WAREHOUSE}}` provisioned by runner (Phase 0b)
- Authentication configured
- semantic-model-consumption skill available (DAX query via MCP ExecuteQuery)

## Data Setup (run FIRST)

This plan provisions its own Adventure Works data and semantic model.

1. Create tables `dbo.FactInternetSales`, `dbo.DimDate`, `dbo.DimSalesTerritory` in `{{WAREHOUSE}}` (or verify `eval_aw_dw` warehouse exists — see note below)
2. Delete semantic model `eval_pbi_dq_advanced` if pre-existing

> **Note:** The Adventure Works data warehouse (`eval_aw_dw`) is a heavyweight prerequisite. If it already exists from a prior run, reuse it. If not, the plan should create `eval_aw_dw` and populate it with the AW tables. This is the most time-consuming Data Setup across all plans (~3-5 min).

## Data Teardown (run LAST)

Clean up semantic model. The AW warehouse persists for reuse.
1. Delete semantic model `eval_pbi_dq_advanced` (PBC-09 already tests this — defensive cleanup)

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### PBC-01: Create DirectQuery Semantic Model
1. **Write (semantic-model-authoring):** "Create or replace a DirectQuery semantic model called `eval_pbi_dq_advanced` in my workspace connected to data warehouse `eval_aw_dw` in workspace `{{WORKSPACE}}`. Include:

   - **Tables:**
     (1) **FactInternetSales** — maps to `dbo.FactInternetSales`. Columns: OrderDateKey (int64), ShipDateKey (int64), SalesTerritoryKey (int64), SalesOrderNumber (string), SalesOrderLineNumber (int64), OrderQuantity (int64), UnitPrice (decimal), SalesAmount (decimal), TaxAmt (decimal), OrderDate (dateTime), ShipDate (dateTime).
     Measures:
       - `Total Sales` = `SUM(FactInternetSales[SalesAmount])` format `$#,##0.00`
       - `Total Tax` = `SUM(FactInternetSales[TaxAmt])` format `$#,##0.00`
       - `Sales by Ship Date` = `CALCULATE(SUM(FactInternetSales[SalesAmount]), USERELATIONSHIP(FactInternetSales[ShipDateKey], DimDate[DateKey]))` format `$#,##0.00`
       - `Tax by Ship Date` = `CALCULATE(SUM(FactInternetSales[TaxAmt]), USERELATIONSHIP(FactInternetSales[ShipDateKey], DimDate[DateKey]))` format `$#,##0.00`

     (2) **DimDate** — maps to `dbo.DimDate`. Columns: DateKey (int64, key), FullDateAlternateKey (dateTime), EnglishDayNameOfWeek (string), SpanishDayNameOfWeek (string), DayNumberOfMonth (int64), EnglishMonthName (string), SpanishMonthName (string), MonthNumberOfYear (int64), CalendarQuarter (int64), CalendarYear (int64).

     (3) **DimSalesTerritory** — maps to `dbo.DimSalesTerritory`. Columns: SalesTerritoryKey (int64, key), SalesTerritoryRegion (string), SalesTerritoryCountry (string), SalesTerritoryGroup (string).

   - **Relationships:**
     (a) **Active:** FactInternetSales[OrderDateKey] → DimDate[DateKey], many-to-one, single cross-filter direction.
     (b) **Inactive:** FactInternetSales[ShipDateKey] → DimDate[DateKey], many-to-one, single cross-filter direction, `isActive = false`.
     (c) **Active:** FactInternetSales[SalesTerritoryKey] → DimSalesTerritory[SalesTerritoryKey], many-to-one, single cross-filter direction.

   - **User Hierarchy on DimSalesTerritory:** `Territory Hierarchy` with levels SalesTerritoryGroup → SalesTerritoryCountry → SalesTerritoryRegion.

   - **Functions:**
     (a) `YoYPeriod` — DAX expression returning `SAMEPERIODLASTYEAR(DimDate[FullDateAlternateKey])`.
     (b) `YTDPeriod` — DAX expression returning `DATESYTD(DimDate[FullDateAlternateKey])`.

   - **Calculation Group:** table `Time Intelligence`, column `Time Calculation`, with items:
     - `Current Value` = `SELECTEDMEASURE()`
     - `YoY Change` = `VAR _current = SELECTEDMEASURE() VAR _prior = CALCULATE(SELECTEDMEASURE(), YoYPeriod()) RETURN IF(NOT ISBLANK(_prior), _current - _prior)`
     - `YTD Total` = `CALCULATE(SELECTEDMEASURE(), YTDPeriod())`

   - **Translation:** Add `es-ES` culture with translations — FactInternetSales → `Ventas por Internet`, DimDate → `Fecha`, DimSalesTerritory → `Territorio de Ventas`, Total Sales → `Ventas Totales`, Sales by Ship Date → `Ventas por Fecha de Envío`.

   - **Security Role:** `TerritoryManager` with modelPermission `read` and table permission on DimSalesTerritory filtering `[SalesTerritoryCountry] = \"United States\"`."

2. **Verify:** `GET /v1/workspaces/{id}/semanticModels` lists `eval_pbi_dq_advanced`; LRO completed successfully

### PBC-02: Verify Tables via DAX
1. **Read (powerbi-consumption):** "List all tables in the eval_pbi_dq_advanced semantic model"
2. **Verify:**
   - Tables named `FactInternetSales`, `DimDate`, `DimSalesTerritory`, and `Time Intelligence` exist
   - Query executes without error


### PBC-03: Verify Measures Including USERELATIONSHIP
1. **Read (powerbi-consumption):** "What measures exist in eval_pbi_dq_advanced? Show their names, expressions, format strings, and FormatStringDefinition values"
2. **Verify:**
   - `Total Sales` with expression `SUM(FactInternetSales[SalesAmount])` and format `$#,##0.00`
   - `Total Tax` with expression `SUM(FactInternetSales[TaxAmt])` and format `$#,##0.00`
   - `Sales by Ship Date` with expression containing `USERELATIONSHIP(FactInternetSales[ShipDateKey], DimDate[DateKey])` and format `$#,##0.00`
   - `Tax by Ship Date` with expression containing `USERELATIONSHIP(FactInternetSales[ShipDateKey], DimDate[DateKey])` and format `$#,##0.00`
   - Format string appears in the `FormatString` column for measures without a calculation group, or in the `FormatStringDefinition` column when a calculation group is present. Check both columns to confirm the format is `$#,##0.00` for all four measures.

### PBC-04: Verify Relationships Including Inactive
1. **Read (powerbi-consumption):** "Show the relationships in eval_pbi_dq_advanced semantic model, including whether each is active"
2. **Verify:**
   - 3 relationships total
   - FactInternetSales[OrderDateKey] → DimDate[DateKey]: many-to-one, single, **active**
   - FactInternetSales[ShipDateKey] → DimDate[DateKey]: many-to-one, single, **inactive**
   - FactInternetSales[SalesTerritoryKey] → DimSalesTerritory[SalesTerritoryKey]: many-to-one, single, **active**

### PBC-05: Verify Calculation Group and Functions
1. **Read (powerbi-consumption):** "Show the calculation groups, calculation items, and user-defined functions in eval_pbi_dq_advanced"
2. **Verify:**
   - Calculation group table `Time Intelligence` with column `Time Calculation`
   - 3 calculation items: `Current Value`, `YoY Change`, `YTD Total`
   - `Current Value` expression = `SELECTEDMEASURE()`
   - `YoY Change` expression references `YoYPeriod()` function
   - `YTD Total` expression references `YTDPeriod()` function
   - 2 user-defined functions exist: `YoYPeriod` (SAMEPERIODLASTYEAR-based) and `YTDPeriod` (DATESYTD-based)

### PBC-06: Verify Security Roles and RLS
1. **Read (powerbi-consumption):** "Show the security roles and their table permissions in eval_pbi_dq_advanced"
2. **Verify:**
   - Role named `TerritoryManager` with modelPermission `read`
   - Table permission on `DimSalesTerritory` with filter expression `[SalesTerritoryCountry] = "United States"`

### PBC-07: DAX Data Validation
1. **Read (powerbi-consumption):** "Run DAX queries against eval_pbi_dq_advanced to validate:
   (a) `Total Sales` in 2013,
   (b) `Sales by Ship Date` in 2013,
   (c) Sales grouped by `DimSalesTerritory[SalesTerritoryGroup]`"
2. **Verify:**
   - Total Sales (2013) = **$16,351,550.34**
   - Sales by Ship Date (2013) = **$16,281,620.14**
   - Sales by Territory Group: Europe **$8.93M** · North America **$11.37M** · Pacific **$9.06M**

### PBC-08: Scope Estimation
1. **Read (powerbi-consumption):** "How many tables, columns, measures, and relationships are in eval_pbi_dq_advanced?"
2. **Verify:**
   - 4 tables (FactInternetSales, DimDate, DimSalesTerritory, Time Intelligence)
   - 26 columns (11 FactInternetSales + 10 DimDate + 4 DimSalesTerritory + 1 Time Calculation)
   - 4 measures (Total Sales, Total Tax, Sales by Ship Date, Tax by Ship Date)
   - 3 relationships

### PBC-09: Cleanup
1. **Write (semantic-model-authoring):** "Delete eval_pbi_dq_advanced from my workspace"
2. **Read (powerbi-consumption):** "List tables in eval_pbi_dq_advanced" (should fail or return not found)
3. **Verify:** Model no longer accessible

## Consistency Scoring

```
consistency = (schema_match + measure_match + relationship_match + calcgroup_match
             + role_match) / 8
```

- **schema_match:** All columns present with correct types across all 3 data tables (1.0) or partial (0.0–0.9)
- **measure_match:** All 4 measures present with correct expressions and format strings; both USERELATIONSHIP measures reference the inactive relationship (1.0) or partial (0.0–0.9)
- **relationship_match:** All 3 relationships present with correct cardinality; inactive relationship correctly marked (1.0) or partial (0.0–0.9)
- **calcgroup_match:** Calculation group with all 3 items present; `YoY Change` and `YTD Total` reference user-defined functions (1.0) or partial (0.0–0.9)
- **role_match:** `TerritoryManager` role with correct modelPermission, filter expression, and role membership (1.0) or partial (0.0–0.9)

**Pass threshold:** consistency = 1.0 for all test cases

## Expected Token Range
- 3000–7000 tokens per combined test (model creation + DAX validation)
