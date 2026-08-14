<#
.SYNOPSIS
    Full Power BI dependency analysis: Reports → Semantic Models → Columns/Measures.

.DESCRIPTION
    Discovers all reports in a Fabric workspace, resolves their semantic model bindings,
    extracts column/measure-level field references from report definitions (PBIR & PBIRLegacy),
    and queries semantic model metadata via DAX INFO functions.

    Outputs a structured JSON file and optionally a Markdown report.

.PARAMETER WorkspaceId
    The Fabric workspace GUID. If omitted, lists available workspaces for selection.

.PARAMETER OutputDir
    Directory for output files. Defaults to ./output.

.PARAMETER SkipReportFields
    Skip downloading report definitions (faster, item-level binding only).

.PARAMETER SkipModelMetadata
    Skip DAX INFO queries on semantic models.

.EXAMPLE
    .\full-dependency-analysis.ps1
    .\full-dependency-analysis.ps1 -WorkspaceId "00000000-0000-4000-8000-000000000027"
    .\full-dependency-analysis.ps1 -WorkspaceId "00000000-0000-4000-8000-000000000001" -SkipReportFields
#>
param(
    [string]$WorkspaceId,
    [string]$OutputDir = "./output",
    [switch]$SkipReportFields,
    [switch]$SkipModelMetadata
)

$ErrorActionPreference = "Continue"
Set-StrictMode -Version Latest

# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────
Write-Host "Authenticating..." -ForegroundColor Cyan
$fabricToken = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
$pbiToken    = az account get-access-token --resource "https://analysis.windows.net/powerbi/api" --query accessToken -o tsv

if (-not $fabricToken -or -not $pbiToken) {
    Write-Error "Failed to acquire tokens. Run 'az login' first."
    exit 1
}

$fabricHeaders = @{ Authorization = "Bearer $fabricToken" }
$pbiHeaders    = @{ Authorization = "Bearer $pbiToken" }

# ─────────────────────────────────────────────
# WORKSPACE SELECTION
# ─────────────────────────────────────────────
if (-not $WorkspaceId) {
    Write-Host "No workspace specified. Listing available workspaces..." -ForegroundColor Yellow
    $workspaces = (Invoke-RestMethod -Uri "https://api.fabric.microsoft.com/v1/workspaces" -Headers $fabricHeaders).value
    for ($i = 0; $i -lt $workspaces.Count; $i++) {
        Write-Host "  [$i] $($workspaces[$i].displayName)  ($($workspaces[$i].id))"
    }
    $selection = Read-Host "Enter workspace number"
    $WorkspaceId = $workspaces[[int]$selection].id
    Write-Host "Selected: $($workspaces[[int]$selection].displayName)" -ForegroundColor Green
}

# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────
function Invoke-DaxQuery {
    param([string]$DatasetId, [string]$Query)
    $body = @{
        queries = @(@{ query = $Query })
        serializerSettings = @{ includeNulls = $true }
    } | ConvertTo-Json -Depth 3
    try {
        $result = Invoke-RestMethod -Uri "https://api.powerbi.com/v1.0/myorg/datasets/$DatasetId/executeQueries" `
            -Method POST -Headers $pbiHeaders -Body $body -ContentType "application/json"
        return $result.results[0].tables[0].rows
    } catch {
        $sc = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
        if ($sc -eq 400) { return $null }  # query not supported (e.g. no calc dependencies)
        Write-Warning "  DAX query failed ($sc): $($_.Exception.Message)"
        return $null
    }
}

function Get-ReportDefinition {
    param([string]$WsId, [string]$ReportId)
    $uri = "https://api.fabric.microsoft.com/v1/workspaces/$WsId/reports/$ReportId/getDefinition"
    try {
        $resp = Invoke-WebRequest -Uri $uri -Method POST -Headers $fabricHeaders `
            -ContentType "application/json" -UseBasicParsing -ErrorAction Stop

        if ($resp.StatusCode -eq 200) {
            return ($resp.Content | ConvertFrom-Json)
        }

        # 202 = LRO accepted — get Location header then poll /result
        if ($resp.StatusCode -eq 202) {
            $loc = $resp.Headers['Location']
            if ($loc -is [array]) { $loc = $loc[0] }
            Start-Sleep -Seconds 5
            $result = Invoke-RestMethod -Uri "$loc/result" -Headers $fabricHeaders
            return $result
        }
    } catch {
        Write-Warning "  getDefinition failed: $($_.Exception.Message)"
    }
    return $null
}

function Extract-FieldRefs {
    param([object]$Definition, [string]$ReportFormat)
    $fieldRefs = [ordered]@{}       # key = "table.field", value = @{type; pages; visuals}
    $reportMeasures = @()

    foreach ($part in $Definition.definition.parts) {
        if (-not $part.payload) { continue }
        try {
            $decoded = [System.Text.Encoding]::UTF8.GetString(
                [System.Convert]::FromBase64String($part.payload))
        } catch { continue }

        $pageName  = if ($part.path -match 'pages/([^/]+)/') { $Matches[1] } else { "_report" }
        $visualName = if ($part.path -match 'visuals/([^/]+)/') { $Matches[1] } else { $part.path }

        # For PBIRLegacy: unescape nested JSON strings
        $searchText = $decoded -replace '\\\\', '' -replace '\\"', '"'

        # Pattern 1: queryRef (both PBIR and PBIRLegacy)
        $qrMatches = [regex]::Matches($searchText, '"queryRef"\s*:\s*"([^"]+)"')
        foreach ($qr in $qrMatches) {
            $ref = $qr.Groups[1].Value
            if (-not $fieldRefs.Contains($ref)) {
                $fieldRefs[$ref] = @{ pages = [System.Collections.Generic.HashSet[string]]::new(); visuals = [System.Collections.Generic.HashSet[string]]::new() }
            }
            [void]$fieldRefs[$ref].pages.Add($pageName)
            [void]$fieldRefs[$ref].visuals.Add($visualName)
        }

        # Pattern 2: Entity/Property (PBIR visual.json)
        $epMatches = [regex]::Matches($searchText, '"Entity"\s*:\s*"([^"]+)"')
        $propMatches = [regex]::Matches($searchText, '"Property"\s*:\s*"([^"]+)"')
        for ($i = 0; $i -lt $epMatches.Count; $i++) {
            $entity = $epMatches[$i].Groups[1].Value
            $prop = if ($i -lt $propMatches.Count) { $propMatches[$i].Groups[1].Value } else { "?" }
            $ref = "$entity.$prop"
            if (-not $fieldRefs.Contains($ref)) {
                $fieldRefs[$ref] = @{ pages = [System.Collections.Generic.HashSet[string]]::new(); visuals = [System.Collections.Generic.HashSet[string]]::new() }
            }
            [void]$fieldRefs[$ref].pages.Add($pageName)
            [void]$fieldRefs[$ref].visuals.Add($visualName)
        }

        # Pattern 3: Report-level measures (modelExtensions in PBIRLegacy)
        $measureMatches = [regex]::Matches($searchText,
            '"name"\s*:\s*"([^"]+)"\s*,\s*"dataType"\s*:\s*\d+\s*,\s*"expression"\s*:\s*"([^"]+)"')
        foreach ($mm in $measureMatches) {
            $reportMeasures += @{ name = $mm.Groups[1].Value; expression = $mm.Groups[2].Value }
        }
    }

    return @{
        fieldRefs      = $fieldRefs
        reportMeasures = $reportMeasures
    }
}

# ─────────────────────────────────────────────
# PHASE 1: Discover reports and semantic model bindings
# ─────────────────────────────────────────────
Write-Host "`n[Phase 1] Discovering reports and semantic model bindings..." -ForegroundColor Cyan

$pbiReports = (Invoke-RestMethod -Uri "https://api.powerbi.com/v1.0/myorg/groups/$WorkspaceId/reports" `
    -Headers $pbiHeaders).value

$pbiDatasets = (Invoke-RestMethod -Uri "https://api.powerbi.com/v1.0/myorg/groups/$WorkspaceId/datasets" `
    -Headers $pbiHeaders).value

# Build dataset lookup
$datasetLookup = @{}
foreach ($ds in $pbiDatasets) { $datasetLookup[$ds.id] = $ds }

# Build the analysis object
$analysis = @{
    workspaceId = $WorkspaceId
    timestamp   = (Get-Date -Format "o")
    reports     = @()
    models      = @()
}

Write-Host "  Found $($pbiReports.Count) reports, $($pbiDatasets.Count) semantic models"

foreach ($rpt in $pbiReports) {
    $dsName = if ($datasetLookup.ContainsKey($rpt.datasetId)) { $datasetLookup[$rpt.datasetId].name } else { "unknown" }
    $format = if ($rpt.reportType -eq "PaginatedReport") { "Paginated" } else { "unknown" }

    # Detect format via Fabric API
    $fabricItems = (Invoke-RestMethod -Uri "https://api.fabric.microsoft.com/v1/workspaces/$WorkspaceId/reports" `
        -Headers $fabricHeaders).value
    $fabricRpt = $fabricItems | Where-Object { $_.id -eq $rpt.id }

    # Determine format from definition parts count heuristic or type
    $reportEntry = @{
        name          = $rpt.name
        id            = $rpt.id
        datasetId     = $rpt.datasetId
        datasetName   = $dsName
        format        = "unknown"
        fieldRefs     = @()
        reportMeasures = @()
    }
    $analysis.reports += $reportEntry
    Write-Host "  Report: $($rpt.name) -> Model: $dsName ($($rpt.datasetId))"
}

# ─────────────────────────────────────────────
# PHASE 2: Extract field references from report definitions
# ─────────────────────────────────────────────
if (-not $SkipReportFields) {
    Write-Host "`n[Phase 2] Extracting field references from report definitions..." -ForegroundColor Cyan

    foreach ($rpt in $analysis.reports) {
        Write-Host "  Processing: $($rpt.name)..." -NoNewline
        $def = Get-ReportDefinition -WsId $WorkspaceId -ReportId $rpt.id

        if (-not $def) {
            Write-Host " FAILED" -ForegroundColor Red
            continue
        }

        $partCount = $def.definition.parts.Count
        $hasVisualJson = ($def.definition.parts | Where-Object { $_.path -like "*/visual.json" }).Count -gt 0
        $rpt.format = if ($hasVisualJson) { "PBIR" } else { "PBIRLegacy" }

        $extracted = Extract-FieldRefs -Definition $def -ReportFormat $rpt.format
        $rpt.fieldRefs = $extracted.fieldRefs.Keys | Sort-Object
        $rpt.reportMeasures = $extracted.reportMeasures

        # Store per-field detail for markdown output
        $rpt["_fieldDetail"] = $extracted.fieldRefs

        Write-Host " $($rpt.format), $partCount parts, $($rpt.fieldRefs.Count) fields" -ForegroundColor Green
    }
} else {
    Write-Host "`n[Phase 2] Skipped (report field extraction)" -ForegroundColor DarkGray
}

# ─────────────────────────────────────────────
# PHASE 3: Query semantic model metadata via DAX
# ─────────────────────────────────────────────
if (-not $SkipModelMetadata) {
    Write-Host "`n[Phase 3] Querying semantic model metadata..." -ForegroundColor Cyan

    # Only query models that have at least one report bound
    $boundDatasetIds = $analysis.reports | ForEach-Object { $_.datasetId } | Sort-Object -Unique

    foreach ($dsId in $boundDatasetIds) {
        $ds = $datasetLookup[$dsId]
        if (-not $ds) { continue }

        Write-Host "  Model: $($ds.name)..." -NoNewline

        $modelEntry = @{
            name          = $ds.name
            id            = $ds.id
            tables        = @()
            columns       = @()
            measures      = @()
            relationships = @()
            calcDependencies = @()
        }

        # Tables
        $tables = Invoke-DaxQuery -DatasetId $dsId -Query "EVALUATE INFO.VIEW.TABLES()"
        if ($tables) {
            $modelEntry.tables = @($tables | ForEach-Object {
                @{ name = $_.'[Name]'; storageMode = $_.'[StorageMode]'; isHidden = $_.'[IsHidden]' }
            })
        }

        # Columns
        $cols = Invoke-DaxQuery -DatasetId $dsId -Query "EVALUATE INFO.VIEW.COLUMNS()"
        if ($cols) {
            $modelEntry.columns = @($cols | ForEach-Object {
                @{ table = $_.'[Table]'; name = $_.'[Name]'; dataType = $_.'[DataType]'; isHidden = $_.'[IsHidden]' }
            })
        }

        # Measures
        $measures = Invoke-DaxQuery -DatasetId $dsId -Query "EVALUATE INFO.VIEW.MEASURES()"
        if ($measures) {
            $modelEntry.measures = @($measures | ForEach-Object {
                @{ table = $_.'[Table]'; name = $_.'[Name]'; displayFolder = $_.'[DisplayFolder]' }
            })
        }

        # Relationships
        $rels = Invoke-DaxQuery -DatasetId $dsId -Query "EVALUATE INFO.VIEW.RELATIONSHIPS()"
        if ($rels) {
            $modelEntry.relationships = @($rels | ForEach-Object {
                @{
                    fromTable  = $_.'[FromTable]'; fromColumn  = $_.'[FromColumn]'
                    toTable    = $_.'[ToTable]';   toColumn    = $_.'[ToColumn]'
                    cardinality = $_.'[Cardinality]'
                }
            })
        }

        # Calc Dependencies (may fail if no calculated objects exist)
        $deps = Invoke-DaxQuery -DatasetId $dsId -Query "EVALUATE INFO.CALCDEPENDENCY()"
        if ($deps) {
            $modelEntry.calcDependencies = @($deps | ForEach-Object {
                @{
                    objectTable = $_.'[TABLE]';    objectName = $_.'[OBJECT]';    objectType = $_.'[OBJECT_TYPE]'
                    refTable    = $_.'[REFERENCED_TABLE]'; refName = $_.'[REFERENCED_OBJECT]'; refType = $_.'[REFERENCED_OBJECT_TYPE]'
                }
            })
        }

        $analysis.models += $modelEntry
        $tCount = $modelEntry.tables.Count
        $cCount = $modelEntry.columns.Count
        $mCount = $modelEntry.measures.Count
        $rCount = $modelEntry.relationships.Count
        Write-Host " $tCount tables, $cCount cols, $mCount measures, $rCount rels" -ForegroundColor Green
    }
} else {
    Write-Host "`n[Phase 3] Skipped (model metadata)" -ForegroundColor DarkGray
}

# ─────────────────────────────────────────────
# PHASE 4: Cross-reference (used vs available)
# ─────────────────────────────────────────────
Write-Host "`n[Phase 4] Cross-referencing field usage..." -ForegroundColor Cyan

$modelLookup = @{}
foreach ($m in $analysis.models) { $modelLookup[$m.id] = $m }

foreach ($rpt in $analysis.reports) {
    $model = $modelLookup[$rpt.datasetId]
    if (-not $model) { continue }

    # Normalize model fields into a set for comparison
    $availableColumns = [System.Collections.Generic.HashSet[string]]::new(
        [StringComparer]::OrdinalIgnoreCase)
    foreach ($c in $model.columns) {
        [void]$availableColumns.Add("$($c.table).$($c.name)")
    }
    foreach ($m2 in $model.measures) {
        [void]$availableColumns.Add("$($m2.table).$($m2.name)")
    }

    # Classify report field refs
    $used = @()
    $implicit = @()
    foreach ($ref in $rpt.fieldRefs) {
        if ($ref -match '^(Sum|Count|Min|Max|Average|CountRows)\(') {
            $implicit += $ref
        } elseif ($availableColumns.Contains($ref)) {
            $used += $ref
        } else {
            $used += $ref  # still referenced, may just be differently cased
        }
    }

    # Find unused model fields (not referenced by this report)
    $usedNormalized = [System.Collections.Generic.HashSet[string]]::new(
        [StringComparer]::OrdinalIgnoreCase)
    foreach ($ref in $rpt.fieldRefs) {
        # Strip implicit aggregation wrappers
        $clean = $ref -replace '^(Sum|Count|Min|Max|Average|CountRows)\(([^)]+)\)$', '$2'
        [void]$usedNormalized.Add($clean)
    }

    $unusedFields = @()
    foreach ($af in $availableColumns) {
        if (-not $usedNormalized.Contains($af)) {
            $unusedFields += $af
        }
    }

    $rpt["usedFields"]    = $used
    $rpt["implicitAggs"]  = $implicit
    $rpt["unusedFields"]  = ($unusedFields | Sort-Object)

    Write-Host "  $($rpt.name): $($rpt.fieldRefs.Count) used, $($unusedFields.Count) unused model fields"
}

# ─────────────────────────────────────────────
# PHASE 5: Generate output files
# ─────────────────────────────────────────────
Write-Host "`n[Phase 5] Generating output..." -ForegroundColor Cyan

if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null }

# --- JSON output ---
$jsonPath = Join-Path $OutputDir "dependency-analysis.json"
$jsonOutput = @{
    workspaceId = $analysis.workspaceId
    timestamp   = $analysis.timestamp
    reports = @($analysis.reports | ForEach-Object {
        @{
            name           = $_.name
            id             = $_.id
            format         = $_.format
            datasetId      = $_.datasetId
            datasetName    = $_.datasetName
            fieldRefs      = $_.fieldRefs
            reportMeasures = $_.reportMeasures
            unusedFields   = $_.unusedFields
        }
    })
    models = $analysis.models
}
$jsonOutput | ConvertTo-Json -Depth 10 | Set-Content -Path $jsonPath -Encoding UTF8
Write-Host "  JSON: $jsonPath" -ForegroundColor Green

# --- Markdown output ---
$mdPath = Join-Path $OutputDir "dependency-analysis.md"
$md = [System.Text.StringBuilder]::new()

[void]$md.AppendLine("# Power BI Dependency Analysis")
[void]$md.AppendLine("")
[void]$md.AppendLine("**Workspace:** ``$($analysis.workspaceId)``  ")
[void]$md.AppendLine("**Generated:** $($analysis.timestamp)  ")
[void]$md.AppendLine("**Reports:** $($analysis.reports.Count) | **Semantic Models:** $($analysis.models.Count)")
[void]$md.AppendLine("")
[void]$md.AppendLine("---")
[void]$md.AppendLine("")

# Summary table
[void]$md.AppendLine("## Report → Semantic Model Bindings")
[void]$md.AppendLine("")
[void]$md.AppendLine("| Report | Format | Semantic Model | Fields Used | Unused Model Fields |")
[void]$md.AppendLine("|--------|--------|----------------|-------------|---------------------|")
foreach ($rpt in $analysis.reports) {
    $usedCount   = if ($rpt.fieldRefs) { $rpt.fieldRefs.Count } else { "-" }
    $unusedCount = if ($rpt.unusedFields) { $rpt.unusedFields.Count } else { "-" }
    [void]$md.AppendLine("| $($rpt.name) | $($rpt.format) | $($rpt.datasetName) | $usedCount | $unusedCount |")
}
[void]$md.AppendLine("")

# Per-report detail
[void]$md.AppendLine("---")
[void]$md.AppendLine("")
[void]$md.AppendLine("## Report Field References (Detail)")
[void]$md.AppendLine("")
foreach ($rpt in $analysis.reports) {
    [void]$md.AppendLine("### $($rpt.name)")
    [void]$md.AppendLine("")
    [void]$md.AppendLine("- **Format:** $($rpt.format)")
    [void]$md.AppendLine("- **Semantic Model:** $($rpt.datasetName) (``$($rpt.datasetId)``)")
    [void]$md.AppendLine("")

    if ($rpt.fieldRefs -and $rpt.fieldRefs.Count -gt 0) {
        [void]$md.AppendLine("#### Fields Used")
        [void]$md.AppendLine("")
        [void]$md.AppendLine("| Field Reference | Type |")
        [void]$md.AppendLine("|-----------------|------|")
        foreach ($ref in $rpt.fieldRefs) {
            $type = if ($ref -match '^(Sum|Count|Min|Max|Average|CountRows)\(') { "Implicit Agg" }
                    elseif ($ref -match '\.\d+$') { "Column" }
                    else { "Column/Measure" }
            [void]$md.AppendLine("| ``$ref`` | $type |")
        }
        [void]$md.AppendLine("")
    } else {
        [void]$md.AppendLine("*No field references extracted.*")
        [void]$md.AppendLine("")
    }

    if ($rpt.reportMeasures -and $rpt.reportMeasures.Count -gt 0) {
        [void]$md.AppendLine("#### Report-Level Measures")
        [void]$md.AppendLine("")
        [void]$md.AppendLine("| Measure | Expression |")
        [void]$md.AppendLine("|---------|------------|")
        foreach ($rm in $rpt.reportMeasures) {
            [void]$md.AppendLine("| ``$($rm.name)`` | ``$($rm.expression)`` |")
        }
        [void]$md.AppendLine("")
    }

    if ($rpt.unusedFields -and $rpt.unusedFields.Count -gt 0) {
        [void]$md.AppendLine("#### Unused Model Fields")
        [void]$md.AppendLine("")
        [void]$md.AppendLine("<details><summary>$($rpt.unusedFields.Count) fields not referenced by this report</summary>")
        [void]$md.AppendLine("")
        foreach ($uf in $rpt.unusedFields) {
            [void]$md.AppendLine("- ``$uf``")
        }
        [void]$md.AppendLine("")
        [void]$md.AppendLine("</details>")
        [void]$md.AppendLine("")
    }
}

# Per-model detail
[void]$md.AppendLine("---")
[void]$md.AppendLine("")
[void]$md.AppendLine("## Semantic Model Metadata")
[void]$md.AppendLine("")
foreach ($model in $analysis.models) {
    [void]$md.AppendLine("### $($model.name)")
    [void]$md.AppendLine("")
    [void]$md.AppendLine("**ID:** ``$($model.id)``  ")
    [void]$md.AppendLine("**Tables:** $($model.tables.Count) | **Columns:** $($model.columns.Count) | **Measures:** $($model.measures.Count) | **Relationships:** $($model.relationships.Count)")
    [void]$md.AppendLine("")

    # Tables and columns
    [void]$md.AppendLine("#### Tables & Columns")
    [void]$md.AppendLine("")
    $colsByTable = $model.columns | Group-Object { $_.table }
    foreach ($grp in $colsByTable) {
        $tableName = $grp.Name
        $tableInfo = $model.tables | Where-Object { $_.name -eq $tableName }
        $hidden = if ($tableInfo -and $tableInfo.isHidden) { " *(hidden)*" } else { "" }
        [void]$md.AppendLine("**$tableName**$hidden")
        [void]$md.AppendLine("")
        [void]$md.AppendLine("| Column | Data Type | Hidden |")
        [void]$md.AppendLine("|--------|-----------|--------|")
        foreach ($c in $grp.Group) {
            $colHidden = if ($c.isHidden) { "Yes" } else { "" }
            [void]$md.AppendLine("| $($c.name) | $($c.dataType) | $colHidden |")
        }
        [void]$md.AppendLine("")
    }

    # Measures
    if ($model.measures.Count -gt 0) {
        [void]$md.AppendLine("#### Measures")
        [void]$md.AppendLine("")
        [void]$md.AppendLine("| Table | Measure | Display Folder |")
        [void]$md.AppendLine("|-------|---------|----------------|")
        foreach ($m2 in $model.measures) {
            [void]$md.AppendLine("| $($m2.table) | $($m2.name) | $($m2.displayFolder) |")
        }
        [void]$md.AppendLine("")
    }

    # Relationships
    if ($model.relationships.Count -gt 0) {
        [void]$md.AppendLine("#### Relationships")
        [void]$md.AppendLine("")
        [void]$md.AppendLine("| From | → | To | Cardinality |")
        [void]$md.AppendLine("|------|---|-----|-------------|")
        foreach ($rel in $model.relationships) {
            [void]$md.AppendLine("| $($rel.fromTable)[$($rel.fromColumn)] | → | $($rel.toTable)[$($rel.toColumn)] | $($rel.cardinality) |")
        }
        [void]$md.AppendLine("")
    }

    # Calc Dependencies
    if ($model.calcDependencies.Count -gt 0) {
        [void]$md.AppendLine("#### Calculation Dependencies")
        [void]$md.AppendLine("")
        [void]$md.AppendLine("| Object | Type | → | Referenced Object | Ref Type |")
        [void]$md.AppendLine("|--------|------|---|-------------------|----------|")
        foreach ($dep in $model.calcDependencies) {
            [void]$md.AppendLine("| $($dep.objectTable).$($dep.objectName) | $($dep.objectType) | → | $($dep.refTable).$($dep.refName) | $($dep.refType) |")
        }
        [void]$md.AppendLine("")
    }
}

# Quality notes
[void]$md.AppendLine("---")
[void]$md.AppendLine("")
[void]$md.AppendLine("## Data Quality & Limitations")
[void]$md.AppendLine("")
[void]$md.AppendLine("| Capability | Quality | Method |")
[void]$md.AppendLine("|------------|---------|--------|")
[void]$md.AppendLine("| Report → Semantic Model binding | **HIGH** | Power BI REST API ``.datasetId`` |")
[void]$md.AppendLine("| Field refs from PBIR reports | **HIGH** | ``getDefinition`` → ``Entity``/``Property`` in ``visual.json`` |")
[void]$md.AppendLine("| Field refs from PBIRLegacy reports | **HIGH** | ``getDefinition`` → ``queryRef`` in ``report.json`` |")
[void]$md.AppendLine("| Semantic model tables/columns/rels | **HIGH** | DAX ``INFO.VIEW.*()`` |")
[void]$md.AppendLine("| Semantic model measures | **HIGH** | DAX ``INFO.VIEW.MEASURES()`` |")
[void]$md.AppendLine("| Measure expressions (DAX formulas) | **LIMITED** | Not returned via REST ``executeQueries``; requires XMLA |")
[void]$md.AppendLine("| Measure → column dependency graph | **LIMITED** | ``INFO.CALCDEPENDENCY()`` may fail via REST API |")
[void]$md.AppendLine("")

$md.ToString() | Set-Content -Path $mdPath -Encoding UTF8
Write-Host "  Markdown: $mdPath" -ForegroundColor Green

Write-Host "`nAnalysis complete." -ForegroundColor Green
Write-Host "  JSON:     $jsonPath"
Write-Host "  Markdown: $mdPath"
