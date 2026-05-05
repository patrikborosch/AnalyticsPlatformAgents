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
    Write-Host "=== $($rpt.name) ==="
    
    # Download definition (LRO)
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
    
    # List parts
    Write-Host "  Parts: $($result.definition.parts.Count)"
    $result.definition.parts | ForEach-Object { Write-Host "    $($_.path)" }
    
    # Find report.json (PBIRLegacy main file)
    $reportPart = $result.definition.parts | Where-Object { $_.path -eq "report.json" }
    if(-not $reportPart) {
        $reportPart = $result.definition.parts | Where-Object { $_.path -like "*report.json" }
    }
    
    if($reportPart) {
        $json = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($reportPart.payload))
        
        # PBIRLegacy uses "queryRef" patterns like "Table.Column" or "Entity.Property"
        # Extract from queryRef patterns
        $queryRefs = [regex]::Matches($json, '"queryRef"\s*:\s*"([^"]+)"')
        if($queryRefs.Count -gt 0) {
            Write-Host ""
            Write-Host "  Field references (queryRef):"
            $refs = @{}
            foreach($m in $queryRefs) {
                $refs[$m.Groups[1].Value] = $true
            }
            $refs.Keys | Sort-Object | ForEach-Object { Write-Host "    $_" }
            Write-Host "  Total: $($refs.Count)"
        }
        
        # Also check for Entity/Property pattern
        $entityMatches = [regex]::Matches($json, '"Entity"\s*:\s*"([^"]+)"')
        $propertyMatches = [regex]::Matches($json, '"Property"\s*:\s*"([^"]+)"')
        if($entityMatches.Count -gt 0) {
            Write-Host ""
            Write-Host "  Field references (Entity/Property):"
            $refs2 = @{}
            for($i=0; $i -lt $entityMatches.Count; $i++) {
                $entity = $entityMatches[$i].Groups[1].Value
                $prop = if($i -lt $propertyMatches.Count) { $propertyMatches[$i].Groups[1].Value } else { "?" }
                $refs2["$entity.$prop"] = $true
            }
            $refs2.Keys | Sort-Object | ForEach-Object { Write-Host "    $_" }
        }
        
        # Show first 500 chars for structure analysis
        Write-Host ""
        Write-Host "  JSON structure preview (first 500 chars):"
        Write-Host "  $($json.Substring(0, [Math]::Min(500, $json.Length)))"
    }
    
    Write-Host ""
}
