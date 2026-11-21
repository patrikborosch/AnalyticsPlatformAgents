param(
    [Parameter(Mandatory)][string]$ClusterUri,
    [Parameter(Mandatory)][string]$Database,
    [Parameter(Mandatory)][string]$SchemaFile
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $SchemaFile -PathType Leaf)) {
    throw "Cannot read schema file: $SchemaFile"
}

# A per-run temp file: a fixed path lets two concurrent runs overwrite each other's payload.
$BodyFile = [System.IO.Path]::GetTempFileName()

try {
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

    # The whole file goes in one `.execute database script`, not line by line. A script
    # produced by `.show database schema as csl script` contains multiline function bodies
    # and policies, so splitting on newlines would cut valid commands in half.
    # ThrowOnErrors stops at the first bad command instead of reporting partial success.
    Write-Host "=== Deploying schema from $SchemaFile ===" -ForegroundColor Cyan
    $script = Get-Content -LiteralPath $SchemaFile -Raw
    Invoke-Kusto -Endpoint mgmt -Command ".execute database script with (ThrowOnErrors=true) <|`n$script"

    # `.show` stays a management command even with a trailing `| project`.
    Write-Host "=== Verification ===" -ForegroundColor Cyan
    foreach ($cmd in @(
            ".show tables details | project TableName, TotalRowCount",
            ".show functions | project Name, Folder",
            ".show materialized-views | project Name, IsEnabled, IsHealthy"
        )) {
        Invoke-Kusto -Endpoint mgmt -Command $cmd
    }

    Write-Host "Schema deployment complete." -ForegroundColor Green
}
finally {
    Remove-Item $BodyFile -Force -ErrorAction SilentlyContinue
}
