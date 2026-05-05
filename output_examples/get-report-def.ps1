$token = az account get-access-token --resource "https://api.fabric.microsoft.com" --query accessToken -o tsv
$wsId = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
$rptId = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

$uri = "https://api.fabric.microsoft.com/v1/workspaces/$wsId/reports/$rptId/getDefinition"

try {
    $r = Invoke-WebRequest -Uri $uri -Method POST -Headers @{Authorization="Bearer $token"} -ContentType "application/json" -UseBasicParsing
    $body = $r.Content | ConvertFrom-Json
    Write-Output "Direct 200 response"
    $body.definition.parts | ForEach-Object { Write-Output "  $($_.path)" }
    # Save for parsing
    $r.Content | Out-File -FilePath "output/report-def-swiss.json" -Encoding utf8
} catch {
    $sc = [int]$_.Exception.Response.StatusCode
    Write-Output "Status: $sc"
    if ($sc -eq 202) {
        $loc = ""
        foreach ($h in $_.Exception.Response.Headers) {
            if ($h -eq "Location") { $loc = $_.Exception.Response.Headers.GetValues("Location")[0] }
        }
        Write-Output "Location: $loc"
        Write-Output "Polling in 8 seconds..."
        Start-Sleep -Seconds 8
        $poll = Invoke-WebRequest -Uri $loc -Headers @{Authorization="Bearer $token"} -UseBasicParsing
        Write-Output "Poll status: $($poll.StatusCode)"
        $pollBody = $poll.Content | ConvertFrom-Json
        $pollBody.definition.parts | ForEach-Object { Write-Output "  $($_.path)" }
        $poll.Content | Out-File -FilePath "output/report-def-swiss.json" -Encoding utf8
    } else {
        Write-Output "Error: $($_.Exception.Message)"
        Write-Output "Full: $_"
    }
}
