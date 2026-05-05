$tkn = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
$wsId = "00000000-0000-4000-8000-000000000027"

$reportsDef = @(
    @{ Name="MyReportTest"; Id="00000000-0000-4000-8000-000000000030" },
    @{ Name="Rep_ExternalMirror"; Id="00000000-0000-4000-8000-000000000034" }
)

function Get-ReportFields {
    param([string]$rptName, [string]$rptId)
    
    Write-Output "=== Report: $rptName ==="
    $resp = Invoke-WebRequest -Uri "https://api.fabric.microsoft.com/v1/workspaces/$wsId/reports/$rptId/getDefinition" -Method POST -Headers @{Authorization="Bearer $tkn"} -ContentType "application/json" -UseBasicParsing
    
    if ($resp.StatusCode -eq 202) {
        $loc = ($resp.Headers["Location"])[0]
        Write-Output "  LRO polling $loc..."
        Start-Sleep -Seconds 10
        $poll = Invoke-RestMethod -Uri $loc -Headers @{Authorization="Bearer $tkn"}
        Write-Output "  Poll status: $($poll.status)"
        
        if ($poll.status -eq "Succeeded") {
            $result = Invoke-RestMethod -Uri "$loc/result" -Headers @{Authorization="Bearer $tkn"}
            Write-Output "  Parts: $($result.definition.parts.Count)"
            
            $fieldRefs = [System.Collections.Generic.HashSet[string]]::new()
            foreach ($part in $result.definition.parts) {
                if ($part.payload) {
                    try {
                        $decoded = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($part.payload))
                        $matches = [regex]::Matches($decoded, '"queryRef"\s*:\s*"([^"]+)"')
                        foreach ($m in $matches) { [void]$fieldRefs.Add($m.Groups[1].Value) }
                    } catch { }
                }
            }
            
            Write-Output "  Fields ($($fieldRefs.Count)):"
            foreach ($f in ($fieldRefs | Sort-Object)) { Write-Output "    -> $f" }
        }
    } elseif ($resp.StatusCode -eq 200) {
        $body = $resp.Content | ConvertFrom-Json
        Write-Output "  Parts: $($body.definition.parts.Count)"
        
        $fieldRefs = [System.Collections.Generic.HashSet[string]]::new()
        foreach ($part in $body.definition.parts) {
            if ($part.payload) {
                try {
                    $decoded = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($part.payload))
                    $matches = [regex]::Matches($decoded, '"queryRef"\s*:\s*"([^"]+)"')
                    foreach ($m in $matches) { [void]$fieldRefs.Add($m.Groups[1].Value) }
                } catch { }
            }
        }
        
        Write-Output "  Fields ($($fieldRefs.Count)):"
        foreach ($f in ($fieldRefs | Sort-Object)) { Write-Output "    -> $f" }
    }
}

foreach ($rpt in $reportsDef) {
    Get-ReportFields -rptName $rpt.Name -rptId $rpt.Id
    Write-Output ""
}
