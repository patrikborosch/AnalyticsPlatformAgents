[CmdletBinding()]
param()

# Sibling of tests/evals/_graders/_run-unit-tests.ps1 (draft PR #282). Two
# runners are intentional: each owns its own .ps1 module set so a regression
# in one cannot mask a regression in the other. Do NOT generalise this into
# a shared runner without first landing PR #282.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$gitRoot = (& git rev-parse --show-toplevel 2>$null)
if (-not $gitRoot) {
    throw 'Could not resolve repository root with git rev-parse.'
}
$repoRoot = Convert-Path $gitRoot
Set-Location $repoRoot

$moduleRoot = Join-Path $repoRoot 'tests' | Join-Path -ChildPath 'vally-ci'
$testFiles = @(Get-ChildItem -Path $moduleRoot -Recurse -Filter '*.tests.ps1' -File | Sort-Object FullName)
if ($testFiles.Count -eq 0) {
    throw "No Pester tests found under $moduleRoot."
}

$pester = Get-Module -ListAvailable -Name Pester |
    Where-Object {
        $_.Version.Major -ge 5 -and
        (Test-Path (Join-Path (Split-Path -Parent $_.Path) 'Pester.ps1'))
    } |
    Sort-Object Version -Descending |
    Select-Object -First 1
if (-not $pester) {
    throw 'Pester 5+ is not installed or is missing Pester.ps1. Install Pester 5.6.1 before running vally-ci unit tests.'
}

Import-Module $pester.Path -Force
Write-Host "[vally-ci] Running $($testFiles.Count) Pester test file(s)." -ForegroundColor Cyan
$pesterResult = Invoke-Pester -Path $testFiles.FullName -PassThru
if ($pesterResult.FailedCount -gt 0) {
    throw "Pester vally-ci tests failed: $($pesterResult.FailedCount) failed, $($pesterResult.PassedCount) passed."
}
Write-Host "[vally-ci] Pester tests passed: $($pesterResult.PassedCount)." -ForegroundColor Green
exit 0
