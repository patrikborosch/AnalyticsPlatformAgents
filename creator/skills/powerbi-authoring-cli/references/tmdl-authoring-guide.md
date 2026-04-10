---
name: tmdl-authoring-guide
description: >
  TMDL syntax rules, modeling best practices, naming conventions, column and measure rules,
  relationship guidelines, Direct Lake configuration, and format string reference for
  Power BI semantic model authoring.
---

# TMDL Authoring Guide

## TMDL Syntax Rules

- **TMDL uses tab indentation** — every nesting level must use exactly one tab character (`\t`), **not spaces**. When building TMDL strings in PowerShell, use `` `t `` for tabs; in Bash, use `$'\t'` or literal tabs. Spaces cause TMDL validation errors on create/update.
- Objects are declared by TOM type followed by name: `table Customer`, `column ProductId`, `measure 'Total Sales'`
- Names with spaces or special characters (`.`, `=`, `:`, `'`) must be wrapped in **single quotes**: `column 'Order Date'`
- Descriptions use `///` placed **above** the object — do not use the `description` property:
  ```tmdl
  /// Revenue by product category
  measure 'Total Sales' = SUM(Sales[Amount])
  ```
- `//` comments are **not supported** in TMDL
- Do **not** add `lineageTag` on new objects — it is auto-generated
- Multi-line DAX must be enclosed in triple backticks:
  ```tmdl
  measure 'Profit Margin' = ```
          DIVIDE(
              [Total Revenue] - [Total Cost],
              [Total Revenue]
          )
          ```
      formatString: 0.00%
  ```
- Place **measures before columns** in table definitions
- `formatString` is required on every measure

---

## Modeling Best Practices

### Naming Conventions

- **Tables**: business-friendly, no `Fact`/`Dim` prefixes. Plural for fact tables (`Sales`), singular for dimensions (`Product`)
- **Columns**: readable with spaces (`Order Date`, `Unit Price`)
- **Measures**: clear patterns (`Total Sales`, `# Customers`). Time intelligence: `[measure]`, `[measure (ly)]`, `[measure (ytd)]`

### Column Rules

| Property | Rule |
|---|---|
| `dataType` | Required. Use `int64`, `decimal`, `string`, `dateTime`, `boolean`. Avoid `double` |
| `sourceColumn` | Must map exactly to partition source column name |
| `isHidden` | Set for ID columns, foreign keys, system columns |
| `summarizeBy` | `none` for non-aggregatable numerics (IDs, postal codes, year numbers) |
| `isAvailableInMdx` | `false` for hidden columns not used in sort-by or hierarchies |
| `dataCategory` | Set for geographic columns (`City`, `Country`) and coordinates |
| `sortByColumn` | For text needing non-alphabetical sort (month names → month number) |

### Measure & DAX Rules

- Always set `formatString` (see table below)
- Use `DIVIDE()` instead of `/` for safe division
- **Never** use `IFERROR` — causes performance degradation
- Prefix `VAR` names with `_` in complex DAX: `VAR _totalSales = ...`
- Use `displayFolder` to organize measures into logical groups
- **Never** set `dataType` on measures — it is inferred from DAX
- Add `///` descriptions to explain business logic

### Format String Reference

| Type | Format | Output |
|---|---|---|
| Currency | `\$#,##0.00` | $1,234.56 |
| Percentage | `0.00%` | 45.67% |
| Integer | `#,##0` | 1,234 |
| Decimal | `#,##0.00` | 1,234.56 |
| Thousands | `#,##0,K` | 1,234K |
| Millions | `#,##0,,M` | 1M |

---

## Relationships

Declared in `relationships.tmdl` or inline in table files.

```tmdl
relationship 'Sales to Date'
	fromColumn: Sales.'Order Date'
	toColumn: Date.Date

/// Inactive — use with USERELATIONSHIP() in DAX
relationship 'Sales - Ship Date to Date'
	isActive: false
	fromColumn: Sales.'Ship Date'
	toColumn: Date.Date
```

### Key Rules

- Create relationships **before** measures that depend on them
- `fromColumn:` = many-side (fact); `toColumn:` = one-side (dimension)
- Default: `crossFilteringBehavior: oneDirection`; add `bothDirections` only when needed
- `isActive: false` for role-playing dimensions; use `USERELATIONSHIP()` in DAX
- Prefer integer keys over string keys for performance
- Both sides must have matching `dataType`
- Set `isKey: true` on dimension primary key columns
- Hide foreign keys on fact tables (`isHidden: true`)
- No composite keys — use a single surrogate integer key
- No surrogate keys on fact tables — use natural keys where possible

---

## Hierarchies

Hierarchies are declared **inside** a table definition. Each level maps to an existing column in the same table.

```tmdl
table Geography

	column Continent
		dataType: string
		sourceColumn: Continent

	column Country
		dataType: string
		sourceColumn: Country

	column City
		dataType: string
		sourceColumn: City

	hierarchy 'Geography Hierarchy'

		level Continent
			column: Continent

		level Country
			column: Country

		level City
			column: City
```

### Key Rules

- A table can have multiple hierarchies

- Levels are ordered top-down (coarsest → finest)
- Each `level` must reference a `column:` that exists in the same table
- Level names can differ from column names
- Use `///` descriptions **above** the level for documentation

---

## Direct Lake Guidelines

Direct Lake mode connects a semantic model directly to Lakehouse/Warehouse delta tables without data import.

- **All** partitions must use `EntityPartitionSource` — no M/Power Query
- A **named expression** pointing to the Lakehouse/Warehouse must be defined before tables:
  ```tmdl
  expression DL_Lakehouse =
      let
          Source = AzureStorage.DataLake("https://onelake.dfs.fabric.microsoft.com/<WorkspaceId>/<LakehouseId>", [HierarchicalNavigation=true])
      in
          Source
  ```
- Each table partition references the expression:
  ```tmdl
  partition Sales = entity
      mode: directLake
      source
          entityName: Sales
          schemaName: dbo
          expressionSource: DL_Lakehouse
  ```
- `dataType: binary` columns are **not supported**
- Columns map directly via `sourceColumn` — no transforms

---

## Calculated Tables

Tables can be sourced from DAX expressions using a calculated partition:

```tmdl
table _Measures

	measure 'Total Sales' = SUM(Sales[Amount])
		formatString: $#,##0.00

	column Dummy
		isHidden
		sourceColumn: [Dummy]

	partition _Measures = calculated
		mode: import
		source = ROW("Dummy", BLANK())
```

### Key Rules

- Use `partition <Name> = calculated` with `source = <DAX>`
- Calculated partitions use `mode: import`
- Useful for measures-only tables (`ROW("Dummy", BLANK())`) and computed date tables

---

## Date/Calendar Table

- Prefer an existing date table from the source over auto-generated
- Ensure **contiguous date range** with no gaps
- Set `dataCategory: Time` on the date table
- Configure `sortByColumn` for month name columns (sort by month number)
- Disable auto-date tables if a proper calendar table exists

---

## Parameters

Use named expressions for connection parameters (Server, Database):

```tmdl
expression Server = "myserver.database.windows.net" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]

expression Database = "MyDatabase" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]
```

Reference in partition M expressions via `#"Server"` and `#"Database"`.

---

## Annotations

Annotations store metadata as key-value pairs. They can appear on tables, columns, measures, relationships, roles, and perspectives.

```tmdl
table Sales

	column 'Unit Price'
		dataType: decimal
		sourceColumn: UnitPrice

		annotation SummarizationSetBy = Automatic
		annotation PBI_FormatHint = {"currencyCulture":"en-US"}

	partition Sales = m
		mode: import
		source = ...

	annotation PBI_ResultType = Table
```

### Key Rules

- `annotation <Key> = <Value>` — indented under the object it annotates
- Do **not** add `PBI_*` annotations manually — they are Power BI internal metadata
- Custom annotations can be used for documentation or tooling metadata
