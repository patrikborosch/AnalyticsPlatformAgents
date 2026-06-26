#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Register (or remove) a Windows Scheduled Task that runs local-sync.ps1 daily, so the global
    Copilot / VS Code environment stays on the newest AnalyticsPlatformAgents content automatically.

.EXAMPLE
    pwsh -File tools/register-local-sync-task.ps1
.EXAMPLE
    pwsh -File tools/register-local-sync-task.ps1 -Time 07:45 -IncludeUpstream
.EXAMPLE
    pwsh -File tools/register-local-sync-task.ps1 -Unregister
#>
[CmdletBinding()]
param(
    [string] $TaskName = 'AnalyticsPlatformAgents-LocalSync',
    [string] $Time     = '08:30',
    [switch] $IncludeUpstream,
    [switch] $Unregister
)

$ErrorActionPreference = 'Stop'

if (-not $IsWindows) { throw 'This registrar targets Windows Task Scheduler. On macOS/Linux use cron with tools/local-sync.ps1.' }

$script = Join-Path $PSScriptRoot 'local-sync.ps1'
if (-not (Test-Path $script)) { throw "local-sync.ps1 not found at $script" }

if ($Unregister) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Unregistered scheduled task '$TaskName'."
    }
    else {
        Write-Host "Scheduled task '$TaskName' not found."
    }
    return
}

$pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
$exe = if ($pwshCmd) { $pwshCmd.Source } else { (Get-Command powershell).Source }

$argLine = "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
if ($IncludeUpstream) { $argLine += ' -IncludeUpstream' }

$action    = New-ScheduledTaskAction -Execute $exe -Argument $argLine
$trigger   = New-ScheduledTaskTrigger -Daily -At $Time
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Registered scheduled task '$TaskName' to run daily at $Time."
Write-Host "Run now:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Remove:   pwsh -File `"$PSCommandPath`" -Unregister"
