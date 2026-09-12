param(
    [Parameter(Mandatory)][string]$ClusterUri,
    [Parameter(Mandatory)][string]$Database,
    [string]$BlobUri
)

$ErrorActionPreference = 'Stop'

# A per-run temp file: a fixed path lets two concurrent runs overwrite each other's
# payload between serialization and the request, so one invocation executes another's KQL.
$BodyFile = [System.IO.Path]::GetTempFileName()

try {
    # ConvertTo-Json escapes the command; ingestion mappings carry embedded double quotes.
    # az is a native command, so a failure does not stop PowerShell on its own -- check
    # $LASTEXITCODE after every call, and let stderr through rather than discarding it.
    function Invoke-Kusto {
        param(
            [Parameter(Mandatory)][ValidateSet('mgmt', 'query')][string]$Endpoint,
            [Parameter(Mandatory)][string]$Command
        )
        @{ db = $Database; csl = $Command } | ConvertTo-Json -Compress |
            Out-File $BodyFile -Encoding utf8NoBOM
        $response = az rest --method POST `
            --url "$ClusterUri/v1/rest/$Endpoint" `
            --resource "https://kusto.kusto.windows.net" `
            --headers "Content-Type=application/json" `
            --body "@$BodyFile"
        if ($LASTEXITCODE -ne 0) {
            throw "az rest failed with exit code $LASTEXITCODE for: $Command"
        }
        ($response | ConvertFrom-Json).Tables[0].Rows
    }

    Write-Host "=== Creating table ===" -ForegroundColor Cyan
    Invoke-Kusto -Endpoint mgmt -Command ".create-merge table Events (Timestamp: datetime, EventType: string, UserId: string, Properties: dynamic, Duration: real)"

    Write-Host "=== Creating CSV mapping ===" -ForegroundColor Cyan
    Invoke-Kusto -Endpoint mgmt -Command ".create-or-alter table Events ingestion csv mapping 'EventsCsvMapping' '[{`"column`":`"Timestamp`",`"datatype`":`"datetime`",`"ordinal`":0},{`"column`":`"EventType`",`"datatype`":`"string`",`"ordinal`":1},{`"column`":`"UserId`",`"datatype`":`"string`",`"ordinal`":2},{`"column`":`"Properties`",`"datatype`":`"dynamic`",`"ordinal`":3},{`"column`":`"Duration`",`"datatype`":`"real`",`"ordinal`":4}]'"

    if ($BlobUri) {
        Write-Host "=== Ingesting from $BlobUri ===" -ForegroundColor Cyan
        Invoke-Kusto -Endpoint mgmt -Command ".ingest into table Events (h'${BlobUri};impersonate') with (format='csv', ingestionMappingReference='EventsCsvMapping', ignoreFirstRecord=true)"
    }

    # A real query, so this one belongs on /v1/rest/query.
    Write-Host "=== Verifying ===" -ForegroundColor Cyan
    Invoke-Kusto -Endpoint query -Command "Events | count"
    Write-Host "Done." -ForegroundColor Green
}
finally {
    Remove-Item $BodyFile -Force -ErrorAction SilentlyContinue
}
