$token = (az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv)
$headers = @{Authorization="Bearer $token"}
$wsId = "00000000-0000-4000-8000-000000000027"
$rptId = "00000000-0000-4000-8000-000000000042"

# Download report definition (LRO)
$r = Invoke-WebRequest -Method Post -Uri "https://api.fabric.microsoft.com/v1/workspaces/$wsId/reports/$rptId/getDefinition" -Headers $headers -ContentType "application/json"
$loc = $r.Headers['Location'][0]
Start-Sleep -Seconds 4
$result = Invoke-RestMethod -Uri "$loc/result" -Headers $headers

# Extract visual parts
$visuals = $result.definition.parts | Where-Object { $_.path -like "*/visual.json" }
Write-Host "=== SwissRailwayVisitors FIELD REFERENCES ==="
Write-Host "Visual parts found: $($visuals.Count)"

foreach($v in $visuals) {
    $json = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($v.payload))
    $visualName = ($v.path -split '/')[-2]
    $pageName = ($v.path -split '/')[2]
    
    # Find all Entity/Property pairs
    $entityMatches = [regex]::Matches($json, '"Entity"\s*:\s*"([^"]+)"')
    $propertyMatches = [regex]::Matches($json, '"Property"\s*:\s*"([^"]+)"')
    
    if($entityMatches.Count -gt 0) {
        Write-Host ""
        Write-Host "  Page: $pageName / Visual: $visualName"
        $refs = @{}
        for($i=0; $i -lt $entityMatches.Count; $i++) {
            $entity = $entityMatches[$i].Groups[1].Value
            $prop = if($i -lt $propertyMatches.Count) { $propertyMatches[$i].Groups[1].Value } else { "?" }
            $key = "$entity.$prop"
            $refs[$key] = $true
        }
        $refs.Keys | Sort-Object | ForEach-Object { Write-Host "    $_" }
    } else {
        Write-Host "  Page: $pageName / Visual: $visualName (no field refs)"
    }
}

# Also extract from report-level filters
$reportJson = $result.definition.parts | Where-Object { $_.path -eq "definition/report.json" }
if($reportJson) {
    $json = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($reportJson.payload))
    $entityMatches = [regex]::Matches($json, '"Entity"\s*:\s*"([^"]+)"')
    $propertyMatches = [regex]::Matches($json, '"Property"\s*:\s*"([^"]+)"')
    if($entityMatches.Count -gt 0) {
        Write-Host ""
        Write-Host "  report.json (report-level filters/fields)"
        $refs = @{}
        for($i=0; $i -lt $entityMatches.Count; $i++) {
            $entity = $entityMatches[$i].Groups[1].Value
            $prop = if($i -lt $propertyMatches.Count) { $propertyMatches[$i].Groups[1].Value } else { "?" }
            $refs["$entity.$prop"] = $true
        }
        $refs.Keys | Sort-Object | ForEach-Object { Write-Host "    $_" }
    }
}

Write-Host ""
Write-Host "=== UNIQUE FIELD REFERENCES (ALL VISUALS) ==="
$allRefs = @{}
foreach($v in ($result.definition.parts | Where-Object { $_.path -like "*/visual.json" -or $_.path -eq "definition/report.json" })) {
    $json = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($v.payload))
    $entityMatches = [regex]::Matches($json, '"Entity"\s*:\s*"([^"]+)"')
    $propertyMatches = [regex]::Matches($json, '"Property"\s*:\s*"([^"]+)"')
    for($i=0; $i -lt $entityMatches.Count; $i++) {
        $entity = $entityMatches[$i].Groups[1].Value
        $prop = if($i -lt $propertyMatches.Count) { $propertyMatches[$i].Groups[1].Value } else { "?" }
        $allRefs["$entity.$prop"] = $true
    }
}
$allRefs.Keys | Sort-Object | ForEach-Object { Write-Host "  $_" }
Write-Host ""
Write-Host "Total unique field references: $($allRefs.Count)"
