---
name: tmdl-advanced-features-guide
description: >
  TMDL syntax for advanced semantic model features: calculation groups, hierarchies,
  security roles, translations/cultures, perspectives, functions, calendar objects,
  inactive/named relationships, and model-level references.
---

# TMDL Advanced Features Guide

This guide covers TMDL syntax for features **not** in [tmdl-authoring-guide.md](./tmdl-authoring-guide.md). All examples are derived from working Fabric semantic models.

---

## File Layout for Advanced Features

Advanced features use additional folders and files beyond the basic structure:

```
definition.pbism
definition/database.tmdl
definition/model.tmdl
definition/relationships.tmdl          ← named/inactive relationships
definition/functions.tmdl              ← DAX functions
definition/tables/<TableName>.tmdl     ← includes hierarchies, calc groups
definition/roles/<RoleName>.tmdl       ← security roles
definition/cultures/<locale>.tmdl      ← translations
definition/perspectives/<Name>.tmdl    ← perspectives
```

---

## database.tmdl — Full Declaration

The database file **must** start with a `database` object declaration (GUID or name), not a bare property:

```tmdl
database 7124f8d8-6199-44fe-b35d-7f7f06b3e1c6
	compatibilityLevel: 1702
	compatibilityMode: powerBI
	language: 1033
```

> **Critical**: Using bare `compatibilityLevel:` without the `database` declaration causes `InvalidLineType: Property!` errors.

---

## model.tmdl — References

The model file declares properties and references to all tables, roles, perspectives, and cultures. Use `ref` declarations so the engine discovers the corresponding files:

```tmdl
model Model
	culture: en-US
	defaultPowerBIDataSourceVersion: powerBI_V3
	discourageImplicitMeasures
	sourceQueryCulture: en-US

ref table Sales
ref table Date
ref table 'Time Intelligence'

ref role RegionalManager

ref perspective 'Internet Sales'

ref cultureInfo en-US
ref cultureInfo fr-FR
```

> **Note**: `defaultPowerBIDataSourceVersion: powerBI_V3` is required for Import-mode models. Without it, the API returns `Import from JSON supported for V3 models only`.

---

## Calculation Groups

A calculation group is a special table with `calculationGroup` and `calculationItem` entries. The table must also have a column (the calculation group column) and a `calculationGroup` partition.

```tmdl
table 'Time Intelligence'

	calculationGroup

		calculationItem Current = SELECTEDMEASURE()

		calculationItem YTD = CALCULATE(SELECTEDMEASURE(), DATESYTD('Date'[Date]))

		calculationItem PY = CALCULATE(SELECTEDMEASURE(), SAMEPERIODLASTYEAR('Date'[Date]))

	column 'Time Intelligence'
		dataType: string

	partition 'Partition_Time Intelligence' = calculationGroup
```

### Key Rules

- `calculationGroup` is declared with **no name** — just the keyword indented under the table
- Each `calculationItem <Name> = <DAX>` is indented under `calculationGroup`
- Use `formatStringDefinition` (not `formatString`) for calculation items that override the measure's format
- The `column` name typically matches the table name
- The partition type must be `= calculationGroup` (not `= m` or `= calculated`)
- Multi-line DAX in calculation items uses triple backticks, same as measures

---

## Security Roles

Each role is a separate file in the `roles/` folder. The file declares access level and DAX filter expressions per table.

### File: `roles/RegionalManager.tmdl`

```tmdl
/// Access restricted to East region
role RegionalManager
	modelPermission: read

	tablePermission Sales = [Region] = "East"
```

### Key Rules

- `role <Name>` is the top-level declaration
- `modelPermission:` is required — use `read` (most common) or `readRefresh`
- `tablePermission <TableName> = <DAX filter>` — the DAX filter expression restricts rows
- One `tablePermission` per table; multiple tables can be filtered in the same role
- In `model.tmdl`, add `ref role <Name>` for each role

---

## Translations / Cultures

Each culture is a separate file in the `cultures/` folder.

### File: `cultures/fr-FR.tmdl`

```tmdl
cultureInfo fr-FR
	translations
		model Model
			table Sales
				caption: Ventes
				column Amount
					caption: Montant
```

### Key Rules

- `cultureInfo <locale>` is the top-level declaration (e.g., `fr-FR`, `zh-CN`, `ja-JP`)
- `translations` → `model Model` → table/column/measure nesting
- Use `caption:` for display name, `description:` for tooltips
- In `model.tmdl`, add `ref cultureInfo <locale>` for each culture
- Do **not** include `linguisticMetadata` — it is auto-managed

---

## Perspectives

Each perspective is a separate file in the `perspectives/` folder.

### File: `perspectives/Internet Sales.tmdl`

```tmdl
perspective 'Internet Sales'

	perspectiveTable 'Internet Sales'
		includeAll

	perspectiveTable Customer
		perspectiveColumn 'Marital Status'
		perspectiveColumn Education

	perspectiveTable _Measures
		perspectiveMeasure 'Internet Sales Amount'
```

### Key Rules

- `perspective <Name>` is the top-level declaration
- `perspectiveTable <TableName>` lists each included table
- Use `includeAll` to include every column/measure; otherwise list specific `perspectiveColumn` / `perspectiveMeasure`
- In `model.tmdl`, add `ref perspective <Name>` for each perspective

---

## Functions

Functions are DAX-defined reusable calculations declared in `functions.tmdl`.

```tmdl
/// Returns double the input value
function DoubleValue = DoubleValue(Value) = Value * 2

/// Year-to-date cumulative total
function YTDTotal = ```
		YTDTotal(Measure) =
		CALCULATE(
		    Measure,
		    DATESYTD('Date'[Date])
		)
		```
```

### Key Rules

- `function <Name> = <Signature> = <DAX>` for single-line; triple backticks for multi-line
- Declared in `definition/functions.tmdl` (top-level file, not inside a table)
- Do **not** add `lineageTag` — it is auto-generated

---

## Calendar Objects

Calendar objects provide date intelligence metadata on a Date table, declared inside the table after hierarchies.

```tmdl
table Date

	calendar 'Gregorian Calendar'

		calendarColumnGroup = year
			primaryColumn: Year

		calendarColumnGroup = month
			primaryColumn: 'Year Month Number'
			associatedColumn: Month

		calendarColumnGroup = date
			primaryColumn: Date
			associatedColumn: Day
```

### Key Rules

- `calendar '<Name>'` is declared inside the table definition
- `calendarColumnGroup = <granularity>` maps levels (year, quarter, month, week, date, monthOfYear, dayOfWeek)
- `primaryColumn:` = sort/numeric column; `associatedColumn:` = display/text columns
- Calendar objects are optional — they enhance time intelligence auto-detection


