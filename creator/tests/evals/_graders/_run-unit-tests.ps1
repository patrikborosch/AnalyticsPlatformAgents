[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$gitRoot = (& git rev-parse --show-toplevel 2>$null)
if (-not $gitRoot) {
    throw 'Could not resolve repository root with git rev-parse.'
}
$repoRoot = Convert-Path $gitRoot
Set-Location $repoRoot

$graderRoot = Join-Path $repoRoot 'tests' | Join-Path -ChildPath 'evals' | Join-Path -ChildPath '_graders'
$testFiles = @(Get-ChildItem -Path $graderRoot -Recurse -Filter '*.tests.ps1' -File | Sort-Object FullName)
if ($testFiles.Count -eq 0) {
    throw "No Pester tests found under $graderRoot."
}

$pester = Get-Module -ListAvailable -Name Pester |
    Where-Object {
        $_.Version.Major -ge 5 -and
        (Test-Path (Join-Path (Split-Path -Parent $_.Path) 'Pester.ps1'))
    } |
    Sort-Object Version -Descending |
    Select-Object -First 1
if (-not $pester) {
    throw 'Pester 5+ is not installed or is missing Pester.ps1. Install Pester 5.6.1 before running grader unit tests.'
}

Import-Module $pester.Path -Force
Write-Host "[grader-unit] Running $($testFiles.Count) Pester test file(s)." -ForegroundColor Cyan
$pesterResult = Invoke-Pester -Path $testFiles.FullName -PassThru
if ($pesterResult.FailedCount -gt 0) {
    throw "Pester grader tests failed: $($pesterResult.FailedCount) failed, $($pesterResult.PassedCount) passed."
}
Write-Host "[grader-unit] Pester tests passed: $($pesterResult.PassedCount)." -ForegroundColor Green
exit 0
