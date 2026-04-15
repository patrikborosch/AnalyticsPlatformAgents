---
name: paginated-report-authoring
description: >
  Author Fabric Paginated Reports (.rdl) from scratch, connecting to semantic models
  via PBIDATASET. Covers RDL XML structure, namespace requirements, data source
  configuration, DAX dataset queries, Tablix layout, conditional formatting,
  page setup, and known schema validation pitfalls.
  Use when the user wants to: (1) create a new paginated report from scratch,
  (2) add datasets or tables to an existing .rdl, (3) connect an .rdl to a Fabric
  semantic model, (4) fix RDL validation or schema errors, (5) design report layout
  with headers, sections, and page footers.
  Triggers: "create paginated report", "new rdl", "author rdl", "build paginated",
  "add tablix", "add dataset", "rdl from scratch", "rdl layout", "paginated report design",
  "fix rdl error", "rdl schema error", "connect rdl to semantic model".
---

# Paginated Report Authoring — Skill

## RDL File Structure Overview

A valid Power BI Paginated Report `.rdl` file uses the **RDL 2016 schema** with four
XML namespaces. Every element in the report body belongs to the default namespace.

```xml
<?xml version="1.0" encoding="utf-8"?>
<Report MustUnderstand="df"
  xmlns="http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition"
  xmlns:rd="http://schemas.microsoft.com/SQLServer/reporting/reportdesigner"
  xmlns:am="http://schemas.microsoft.com/sqlserver/reporting/authoringmetadata"
  xmlns:df="http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition/defaultfontfamily">

  <df:DefaultFontFamily>Segoe UI</df:DefaultFontFamily>
  <AutoRefresh>0</AutoRefresh>

  <DataSources>...</DataSources>
  <DataSets>...</DataSets>

  <ReportSections>
    <ReportSection>
      <Body>...</Body>
      <Page>...</Page>
      <Width>...</Width>          <!-- REQUIRED — must match PageWidth -->
    </ReportSection>
  </ReportSections>

  <rd:ReportUnitType>mm</rd:ReportUnitType>
  <rd:ReportServerUrl>https://app.powerbi.com</rd:ReportServerUrl>
  <rd:ReportID>...</rd:ReportID>
</Report>
```

## Connecting to a Fabric Semantic Model (PBIDATASET)

### DataSource Template

```xml
<DataSource Name="{WorkspaceName}_{ModelName}">
  <rd:SecurityType>None</rd:SecurityType>
  <ConnectionProperties>
    <DataProvider>PBIDATASET</DataProvider>
    <ConnectString>Data Source=pbiazure://api.powerbi.com/;Identity Provider="https://login.microsoftonline.com/organizations, https://analysis.windows.net/powerbi/api, f0b72488-7082-488a-a7e8-eada97bd842d";Initial Catalog=sobe_wowvirtualserver-{semantic-model-guid};Integrated Security=ClaimsToken</ConnectString>
  </ConnectionProperties>
  <rd:DataSourceID>{any-guid}</rd:DataSourceID>
  <rd:PowerBIWorkspaceName>{WorkspaceName}</rd:PowerBIWorkspaceName>
  <rd:PowerBIDatasetName>{ModelName}</rd:PowerBIDatasetName>
</DataSource>
```

**Key rules:**
- `DataProvider` must be `PBIDATASET` (not `SQL`)
- `Integrated Security=ClaimsToken` — required in the ConnectString for semantic models
- `rd:SecurityType` must be `None`
- The `Identity Provider` string is a fixed constant (same for all tenants)
- The `Initial Catalog` format is always `sobe_wowvirtualserver-{guid}`
- Do NOT add `IntegratedSecurity` as a separate XML element — it goes inside `ConnectString`

### Finding the Semantic Model GUID

```powershell
$pbiToken = (az account get-access-token --resource "https://analysis.windows.net/powerbi/api" --query accessToken -o tsv)
$datasets = (Invoke-RestMethod "https://api.powerbi.com/v1.0/myorg/groups/$wsId/datasets" `
  -Headers @{ Authorization = "Bearer $pbiToken" }).value
$datasets | Where-Object { $_.name -eq "YourModelName" } | Select-Object name, id
```

### Connecting to a Fabric SQL Endpoint (Warehouse / Lakehouse SQL)

For SQL-based connections (not semantic model), use a different pattern:

```xml
<DataSource Name="MyWarehouse">
  <rd:SecurityType>None</rd:SecurityType>
  <ConnectionProperties>
    <DataProvider>SQL</DataProvider>
    <ConnectString>Data Source={sql-endpoint-hostname};Initial Catalog={database-name};Encrypt=True;TrustServerCertificate=False;</ConnectString>
    <IntegratedSecurity>false</IntegratedSecurity>
  </ConnectionProperties>
</DataSource>
```

**SQL endpoint rules:**
- Do NOT include any `Authentication=` keyword in the ConnectString — it causes credential conflicts in Report Builder
- `IntegratedSecurity` must be `false` (as a separate element)
- `rd:SecurityType` must be `None`
- Credentials are handled by Report Builder UI dialog or the Fabric service at runtime

## DAX Dataset Queries

PBIDATASET sources use **DAX** queries, not SQL. Every dataset query starts with `EVALUATE`.

### DataField Format

Fields from the semantic model use `tablename[columnname]` notation.
Computed measure columns use `[MeasureName]` (no table prefix).

```xml
<Field Name="customer_id">
  <DataField>customers[customer_id]</DataField>        <!-- table column -->
  <rd:TypeName>System.String</rd:TypeName>
</Field>
<Field Name="TotalClaimed">
  <DataField>[TotalClaimed]</DataField>                 <!-- computed measure -->
  <rd:TypeName>System.Double</rd:TypeName>
</Field>
```

### Common DAX Query Patterns

**Aggregation with SUMMARIZECOLUMNS:**
```dax
EVALUATE
SUMMARIZECOLUMNS(
  table[group_col_1],
  table[group_col_2],
  "MeasureName1", SUM(table[amount]),
  "MeasureName2", COUNTROWS(table),
  "MeasureName3", AVERAGEX(FILTER(table, NOT ISBLANK(table[col])), table[col])
)
ORDER BY table[group_col_1], table[group_col_2]
```

**Top N with TOPN:**
```dax
EVALUATE
TOPN(50,
  SUMMARIZECOLUMNS(
    table1[col1],
    table2[col2],
    "Measure1", CALCULATE(COUNTROWS(related_table)),
    "Measure2", CALCULATE(SUM(related_table[amount]))
  ),
  [Measure1], DESC
)
ORDER BY [Measure1] DESC
```

**Cross-table queries:** SUMMARIZECOLUMNS automatically handles relationships defined
in the semantic model. Include columns from multiple tables and the engine resolves joins.

### Type Mapping

| DAX / Lakehouse Type | RDL TypeName |
|---|---|
| string | `System.String` |
| integer, long | `System.Int64` |
| double, decimal | `System.Double` |
| date, datetime | `System.DateTime` |
| boolean | `System.Boolean` |

## Report Layout

### Page Setup

Use **millimeters** as the unit. Set `<rd:ReportUnitType>mm</rd:ReportUnitType>`.

| Page Size | Width | Height | Use Case |
|---|---|---|---|
| A4 Portrait | 210mm | 297mm | Standard documents |
| A4 Landscape | 297mm | 210mm | Wide tables |
| A3 Landscape | 420mm | 297mm | Very wide tables (10+ columns) |
| US Letter | 216mm | 279mm | US standard |

**CRITICAL:** The `<Width>` element inside `<ReportSection>` **must be present** and should
match `<PageWidth>`. Omitting it causes `rsInvalidReportDefinition` on import.

```xml
<ReportSection>
  <Body>...</Body>
  <Page>
    <PageFooter>...</PageFooter>
    <PageHeight>297mm</PageHeight>
    <PageWidth>420mm</PageWidth>
    <LeftMargin>10mm</LeftMargin>
    <RightMargin>10mm</RightMargin>
    <TopMargin>10mm</TopMargin>
    <BottomMargin>10mm</BottomMargin>
    <Style />
  </Page>
  <Width>420mm</Width>   <!-- MUST match PageWidth -->
</ReportSection>
```

### Body Structure

The `<Body>` contains `<ReportItems>` and a `<Height>`. Set body height large enough to
contain all report items. It auto-shrinks at render time but must be >= the tallest
item's Top + Height.

```xml
<Body>
  <ReportItems>
    <!-- Rectangles, Textboxes, Tablixes positioned with Top/Left/Width/Height -->
  </ReportItems>
  <Style />
  <Height>800mm</Height>
</Body>
```

### Section Headers

Use `<Rectangle>` with a dark background and a child `<Textbox>` for section titles:

```xml
<Rectangle Name="SectionHeader">
  <ReportItems>
    <Textbox Name="SectionTitle">
      <CanGrow>false</CanGrow>
      <Paragraphs>
        <Paragraph>
          <TextRuns>
            <TextRun>
              <Value>Section Title Here</Value>
              <Style>
                <FontFamily>Segoe UI</FontFamily>
                <FontSize>12pt</FontSize>
                <FontWeight>Bold</FontWeight>
                <Color>White</Color>
              </Style>
            </TextRun>
          </TextRuns>
          <Style />
        </Paragraph>
      </Paragraphs>
      <Style>
        <Border><Style>None</Style></Border>
      </Style>
      <Left>5mm</Left>
      <Top>3mm</Top>
      <Width>247mm</Width>
      <Height>8mm</Height>
    </Textbox>
  </ReportItems>
  <Style>
    <Border><Style>None</Style></Border>
    <BackgroundColor>#2E6DA4</BackgroundColor>
  </Style>
  <Left>0mm</Left>
  <Top>37mm</Top>           <!-- position below previous element -->
  <Width>257mm</Width>
  <Height>14mm</Height>
</Rectangle>
```

### Tablix (Data Table)

A Tablix has three main parts: `TablixBody` (columns + rows), `TablixColumnHierarchy`,
and `TablixRowHierarchy`.

**Structural rules:**
- Number of `<TablixColumn>` must match number of `<TablixCell>` in every `<TablixRow>`
- Number of `<TablixMember>` in ColumnHierarchy must match number of `<TablixColumn>`
- RowHierarchy has one `<TablixMember>` per `<TablixRow>` — header row uses
  `<KeepWithGroup>After</KeepWithGroup>`, data row uses `<Group Name="..."/>`
- Every `<Textbox>` name must be unique across the entire report

```xml
<Tablix Name="TablixName">
  <TablixBody>
    <TablixColumns>
      <TablixColumn><Width>38mm</Width></TablixColumn>
      <TablixColumn><Width>30mm</Width></TablixColumn>
      <!-- one per column -->
    </TablixColumns>
    <TablixRows>
      <!-- Header row -->
      <TablixRow>
        <Height>8mm</Height>
        <TablixCells>
          <TablixCell>
            <CellContents>
              <Textbox Name="Hdr_Col1">
                <!-- header styling: Bold, White text, colored background -->
              </Textbox>
            </CellContents>
          </TablixCell>
          <!-- one cell per column -->
        </TablixCells>
      </TablixRow>
      <!-- Data row -->
      <TablixRow>
        <Height>7mm</Height>
        <TablixCells>
          <TablixCell>
            <CellContents>
              <Textbox Name="Data_Col1">
                <!-- data: =Fields!fieldname.Value -->
              </Textbox>
            </CellContents>
          </TablixCell>
        </TablixCells>
      </TablixRow>
    </TablixRows>
  </TablixBody>
  <TablixColumnHierarchy>
    <TablixMembers>
      <TablixMember />   <!-- one per column -->
      <TablixMember />
    </TablixMembers>
  </TablixColumnHierarchy>
  <TablixRowHierarchy>
    <TablixMembers>
      <TablixMember>
        <KeepWithGroup>After</KeepWithGroup>   <!-- header row -->
      </TablixMember>
      <TablixMember>
        <Group Name="DatasetName_Detail" />    <!-- data row -->
      </TablixMember>
    </TablixMembers>
  </TablixRowHierarchy>
  <DataSetName>DS_MyDataset</DataSetName>
  <Left>0mm</Left>
  <Top>51mm</Top>
  <Width>228mm</Width>
  <Style>
    <Border><Style>None</Style></Border>
  </Style>
</Tablix>
```

### Conditional Formatting

Use expressions in `<Color>`, `<BackgroundColor>`, `<FontWeight>` etc.:

```xml
<!-- Alternating row colors -->
<BackgroundColor>=IIF(RowNumber(Nothing) MOD 2 = 0, "#F0F4FA", "White")</BackgroundColor>

<!-- Status color coding -->
<Color>=Switch(
  Fields!status.Value = "Approved", "#1A7A1A",
  Fields!status.Value = "Rejected", "#B22222",
  Fields!status.Value = "Pending", "#CC7700",
  True, "Black"
)</Color>

<!-- Risk profile coloring -->
<Color>=Switch(
  Fields!risk_profile.Value = "High", "#B22222",
  Fields!risk_profile.Value = "Low", "#1A7A1A",
  True, "#CC7700"
)</Color>
```

### Number / Date Formatting

```xml
<!-- Currency, no decimals -->
<Value>=Format(Fields!amount.Value, "N0")</Value>

<!-- Currency with 2 decimals -->
<Value>=Format(Fields!amount.Value, "N2")</Value>

<!-- Date -->
<Value>=Format(Fields!date_col.Value, "yyyy-MM-dd")</Value>

<!-- Nullable with dash fallback -->
<Value>=IIF(IsNothing(Fields!days.Value), "—", Format(Fields!days.Value, "N0"))</Value>

<!-- Concatenate fields -->
<Value>=Fields!first_name.Value &amp; " " &amp; Fields!last_name.Value</Value>
```

### PageFooter

`Globals!PageNumber`, `Globals!TotalPages`, and `Globals!ExecutionTime` are **only valid
inside `<PageHeader>` or `<PageFooter>`**. Placing them in `<Body>` causes a validation error.

```xml
<Page>
  <PageFooter>
    <PrintOnFirstPage>true</PrintOnFirstPage>
    <PrintOnLastPage>true</PrintOnLastPage>
    <ReportItems>
      <Textbox Name="PageFooterLeft">
        <!-- Static text: "Report Title · Confidential" -->
        <Left>0mm</Left><Top>3mm</Top><Width>100mm</Width><Height>6mm</Height>
      </Textbox>
      <Textbox Name="PageFooterCenter">
        <Value>=Format(Globals!ExecutionTime, "dd MMM yyyy HH:mm")</Value>
        <!-- centered -->
      </Textbox>
      <Textbox Name="PageFooterRight">
        <Value>=Globals!PageNumber &amp; " / " &amp; Globals!TotalPages</Value>
        <!-- right-aligned -->
      </Textbox>
    </ReportItems>
    <Style>
      <Border><Style>None</Style></Border>
    </Style>
    <Height>12mm</Height>
  </PageFooter>
  <!-- PageHeight, PageWidth, margins follow -->
</Page>
```

## Common Errors and Fixes

| Error | Root Cause | Fix |
|---|---|---|
| `ReportItems incomplete content` | `<ReportItems />` self-closing in a `<Rectangle>` | Remove empty `<ReportItems />` or add at least one child element |
| `PageNumber/TotalPages only in header/footer` | `Globals!PageNumber` used in `<Body>` | Move the textbox into `<PageFooter>` inside `<Page>` |
| `Integrated security credential type conflict` | `Authentication=...` keyword in SQL ConnectString | Remove all `Authentication=` keywords from ConnectString; set `IntegratedSecurity=false`, `rd:SecurityType=None` |
| `rsInvalidReportDefinition: ReportSection missing Width` | No `<Width>` in `<ReportSection>` | Add `<Width>{PageWidth}</Width>` as child of `<ReportSection>` after `<Page>` |
| `RequestedFileIsEncryptedOrCorrupted` on import | Using `Invoke-RestMethod` for multipart upload | Use `System.Net.Http.HttpClient` and include `.rdl` in `datasetDisplayName` (see `paginated-report-ops` skill) |
| `UnsupportedItemType: PaginatedReport` | Using Fabric Items API to create report | Use the **Power BI Import API** instead (`POST /groups/{wsId}/imports`) |
| Every dataset must be referenced | Orphan `<DataSet>` not bound to any Tablix | Remove unused datasets or add a Tablix with matching `<DataSetName>` |

## Design Checklist

Before generating or importing an .rdl, verify:

- [ ] All four XML namespaces present on `<Report>` root element
- [ ] `<df:DefaultFontFamily>` set
- [ ] `<ReportSection>` has `<Width>` matching `<PageWidth>`
- [ ] `<Body>` has `<Height>` >= tallest item's Top + Height
- [ ] No empty `<ReportItems />` — either omit or populate
- [ ] `Globals!PageNumber` / `Globals!TotalPages` only in `<PageHeader>` or `<PageFooter>`
- [ ] All `<Textbox>` `Name` attributes are unique across the entire report
- [ ] TablixColumn count = TablixCell count per row = TablixMember count in ColumnHierarchy
- [ ] TablixRow count = TablixMember count in RowHierarchy
- [ ] Every `<DataSet>` is referenced by at least one Tablix's `<DataSetName>`
- [ ] PBIDATASET: `Integrated Security=ClaimsToken` inside ConnectString, `rd:SecurityType=None`
- [ ] SQL endpoint: no `Authentication=` keyword in ConnectString, `IntegratedSecurity=false`
- [ ] XML is well-formed (no case mismatches like `</border>` vs `</Border>`)

## Reference Documentation

- [Report Definition Language (RDL) specification](https://learn.microsoft.com/en-us/power-bi/paginated-reports/report-definition-language) — official RDL element reference, schema details, and supported features for Power BI paginated reports

## Companion Skill

For importing the finished `.rdl` into a Fabric workspace (including multipart upload,
folder placement, and overwrite handling), see the **`paginated-report-ops`** skill.
