$token = (az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv)
$headers = @{Authorization="Bearer $token"}
$wsId = "00000000-0000-4000-8000-000000000027"

$legacyReports = @(
    @{name="MyReportTest"; id="00000000-0000-4000-8000-000000000030"},
    @{name="Rep_ExternalMirror"; id="00000000-0000-4000-8000-000000000034"},
    @{name="Rep_ExternalMirror_2"; id="00000000-0000-4000-8000-000000000024"},
    @{name="RefreshEveryMinute"; id="00000000-0000-4000-8000-000000000006"}
)

foreach($rpt in $legacyReports) {
    Write-Host "========================================"
    Write-Host "=== $($rpt.name) ==="
    Write-Host "========================================"
    
    try {
        $r = Invoke-WebRequest -Method Post -Uri "https://api.fabric.microsoft.com/v1/workspaces/$wsId/reports/$($rpt.id)/getDefinition" -Headers $headers -ContentType "application/json"
        if($r.StatusCode -eq 202) {
            $loc = $r.Headers['Location'][0]
            Start-Sleep -Seconds 4
            $result = Invoke-RestMethod -Uri "$loc/result" -Headers $headers
        } else {
            $result = $r.Content | ConvertFrom-Json
        }
    } catch {
        Write-Host "  ERROR: $($_.Exception.Message)"
        continue
    }
    
    $reportPart = $result.definition.parts | Where-Object { $_.path -eq "report.json" }
    if(-not $reportPart) { Write-Host "  No report.json found"; continue }
    
    $json = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($reportPart.payload))
    $reportObj = $json | ConvertFrom-Json
    
    # PBIRLegacy report.json has stringified JSON in "config", "sections[].config", visual configs etc.
    # The field references are in queryRef patterns within the full text (including escaped JSON)
    
    # Method 1: Extract queryRef from the raw text (handles escaped JSON)
    $allText = $json -replace '\\\\', '' -replace '\\"', '"'
    
    $queryRefs = [regex]::Matches($allText, '"queryRef"\s*:\s*"([^"]+)"')
    $entityProps = [regex]::Matches($allText, '"Entity"\s*:\s*"([^"]+)"')
    $propertyVals = [regex]::Matches($allText, '"Property"\s*:\s*"([^"]+)"')
    
    # Also look for Column patterns used in PBIRLegacy: "Column":{"Expression":{"SourceRef":...},"Property":"colname"}
    # And "Measure" patterns
    
    Write-Host ""
    if($queryRefs.Count -gt 0) {
        Write-Host "  queryRef fields:"
        $refs = @{}
        foreach($m in $queryRefs) {
            $refs[$m.Groups[1].Value] = $true
        }
        $refs.Keys | Sort-Object | ForEach-Object { Write-Host "    $_" }
        Write-Host "  Count: $($refs.Count)"
    }
    
    if($entityProps.Count -gt 0) {
        Write-Host ""
        Write-Host "  Entity/Property pairs:"
        $refs2 = @{}
        for($i=0; $i -lt $entityProps.Count; $i++) {
            $entity = $entityProps[$i].Groups[1].Value
            $prop = if($i -lt $propertyVals.Count) { $propertyVals[$i].Groups[1].Value } else { "?" }
            $refs2["$entity.$prop"] = $true
        }
        $refs2.Keys | Sort-Object | ForEach-Object { Write-Host "    $_" }
        Write-Host "  Count: $($refs2.Count)"
    }
    
    # Method 2: Also look for "Name":"tablename" within source expressions
    # Check for model extensions (report-level measures)
    if($allText -match '"modelExtensions"') {
        $measureMatches = [regex]::Matches($allText, '"name"\s*:\s*"([^"]+)"\s*,\s*"dataType"\s*:\s*\d+\s*,\s*"expression"\s*:\s*"([^"]+)"')
        if($measureMatches.Count -gt 0) {
            Write-Host ""
            Write-Host "  Report-level measures (modelExtensions):"
            foreach($m in $measureMatches) {
                Write-Host "    $($m.Groups[1].Value) = $($m.Groups[2].Value)"
            }
        }
    }
    
    Write-Host ""
}
