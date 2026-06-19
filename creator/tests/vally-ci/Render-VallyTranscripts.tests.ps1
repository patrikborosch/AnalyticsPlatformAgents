Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

BeforeAll {
    $script:ScriptPath = Join-Path $PSScriptRoot 'Render-VallyTranscripts.ps1'
    $script:ScratchRoot = Join-Path ([System.IO.Path]::GetTempPath()) "render-vally-transcripts-test-$([guid]::NewGuid())"
    New-Item -Path $script:ScratchRoot -ItemType Directory -Force | Out-Null
}

AfterAll {
    if (Test-Path $script:ScratchRoot) { Remove-Item $script:ScratchRoot -Recurse -Force }
}

function script:New-VallyFixture {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][hashtable[]]$Trials
    )
    $outDir = Join-Path $Root "vally-output/$(Get-Date -Format yyyyMMdd-HHmmss)"
    New-Item -Path $outDir -ItemType Directory -Force | Out-Null
    $jsonlPath = Join-Path $outDir 'results.jsonl'
    $lines = foreach ($t in $Trials) {
        $t | ConvertTo-Json -Compress -Depth 12
    }
    Set-Content -Path $jsonlPath -Value $lines -Encoding utf8
    return $jsonlPath
}

function script:New-Trial {
    [CmdletBinding()]
    param(
        [string]$EvalName,
        [string]$StimName,
        [bool]$Passed = $true,
        [double]$Score = 1.0,
        [string]$Prompt = 'Test prompt',
        [object[]]$Events = @()
    )
    return @{
        gradeResult = @{
            stimulusName = $StimName
            passed       = $Passed
            score        = $Score
            details      = @(
                @{ name = 'completed'; passed = $true; score = 1; evidence = 'Agent session completed successfully' }
            )
        }
        trajectory  = @{
            stimulus = @{
                name   = $StimName
                prompt = $Prompt
                tags   = @{ skill = $EvalName; tier = 'smoke' }
            }
            events   = $Events
        }
    }
}

Describe 'Render-VallyTranscripts' {
    Context 'per-stim trial counter' {
        It 'numbers trials per (eval, stim) pair so 4 stims at runs=1 all read as trial1' {
            $root = Join-Path $script:ScratchRoot 'per-stim-counter'
            New-Item -Path $root -ItemType Directory -Force | Out-Null
            $null = New-VallyFixture -Root $root -Trials @(
                (New-Trial -EvalName 'demo-eval' -StimName 'Refresh' -Prompt 'r'),
                (New-Trial -EvalName 'demo-eval' -StimName 'Apply' -Prompt 'a'),
                (New-Trial -EvalName 'demo-eval' -StimName 'Prepare' -Prompt 'p'),
                (New-Trial -EvalName 'demo-eval' -StimName 'List' -Prompt 'l')
            )
            $outDir = Join-Path $root 'transcripts'
            & $script:ScriptPath -ResultsRoot $root -OutputDir $outDir | Out-Null
            # @(...) wrappers force array semantics so .Count works under
            # Set-StrictMode -Version Latest (single-item Get-ChildItem or
            # Where-Object pipe results would otherwise be a scalar).
            $files = @(Get-ChildItem $outDir -File)
            $files.Count | Should -BeExactly 4
            (@($files | Where-Object Name -like '*Refresh*trial1.txt')).Count | Should -BeExactly 1
            (@($files | Where-Object Name -like '*Apply*trial1.txt')).Count   | Should -BeExactly 1
            (@($files | Where-Object Name -like '*Prepare*trial1.txt')).Count | Should -BeExactly 1
            (@($files | Where-Object Name -like '*List*trial1.txt')).Count    | Should -BeExactly 1
            # No filename ends in trial2 because each stim only has one trial.
            (@($files | Where-Object Name -like '*trial2.txt')).Count | Should -BeExactly 0
        }

        It 'numbers the same stim 1..N across runs (runs=3 -> trial1/trial2/trial3)' {
            $root = Join-Path $script:ScratchRoot 'multi-run-counter'
            New-Item -Path $root -ItemType Directory -Force | Out-Null
            $null = New-VallyFixture -Root $root -Trials @(
                (New-Trial -EvalName 'demo-eval' -StimName 'Same' -Prompt 'first'),
                (New-Trial -EvalName 'demo-eval' -StimName 'Same' -Prompt 'first'),
                (New-Trial -EvalName 'demo-eval' -StimName 'Same' -Prompt 'first')
            )
            $outDir = Join-Path $root 'transcripts'
            & $script:ScriptPath -ResultsRoot $root -OutputDir $outDir | Out-Null
            $files = @(Get-ChildItem $outDir -File)
            $files.Count | Should -BeExactly 3
            (@($files | Where-Object Name -like '*Same*trial1.txt')).Count | Should -BeExactly 1
            (@($files | Where-Object Name -like '*Same*trial2.txt')).Count | Should -BeExactly 1
            (@($files | Where-Object Name -like '*Same*trial3.txt')).Count | Should -BeExactly 1
        }
    }

    Context 'evidence redaction' {
        It 'redacts GUIDs from user_message + tool_call args' {
            $root = Join-Path $script:ScratchRoot 'redact-test'
            New-Item -Path $root -ItemType Directory -Force | Out-Null
            $wsId = '2c4f7b6e-1a3d-4e5f-9c8a-7b6e5d4f3c2a'
            $events = @(
                @{ type = 'user_message'; data = @{ content = "Connect to workspace $wsId please." } },
                @{ type = 'tool_call'; data = @{ toolName = 'mcp_call'; arguments = @{ workspaceId = $wsId } } }
            )
            $null = New-VallyFixture -Root $root -Trials @(
                (New-Trial -EvalName 'demo' -StimName 'guid-leak' -Prompt "Use $wsId" -Events $events)
            )
            $outDir = Join-Path $root 'transcripts'
            & $script:ScriptPath -ResultsRoot $root -OutputDir $outDir | Out-Null
            $f = Get-ChildItem $outDir -File | Select-Object -First 1
            $content = Get-Content $f.FullName -Raw
            $content | Should -Match '\[REDACTED\]'
            $content | Should -Not -Match $wsId
        }

        It 'redacts bearer tokens from tool_result content' {
            $root = Join-Path $script:ScratchRoot 'bearer-test'
            New-Item -Path $root -ItemType Directory -Force | Out-Null
            $events = @(
                @{ type = 'tool_result'; data = @{ toolName = 'http_call'; success = $true; result = 'Authorization: Bearer eyJsupersecretToken' } }
            )
            $null = New-VallyFixture -Root $root -Trials @(
                (New-Trial -EvalName 'demo' -StimName 'bearer-leak' -Events $events)
            )
            $outDir = Join-Path $root 'transcripts'
            & $script:ScriptPath -ResultsRoot $root -OutputDir $outDir | Out-Null
            $f = Get-ChildItem $outDir -File | Select-Object -First 1
            $content = Get-Content $f.FullName -Raw
            $content | Should -Match '\[REDACTED\]'
            $content | Should -Not -Match 'eyJsupersecretToken'
        }
    }

    Context 'graceful no-input' {
        It 'exits 0 with helpful message when no results.jsonl found' {
            $root = Join-Path $script:ScratchRoot 'empty-tree'
            New-Item -Path $root -ItemType Directory -Force | Out-Null
            $outDir = Join-Path $root 'transcripts'
            # Calling the script directly should exit 0 (the script uses `exit 0` mid-body
            # which would terminate our test runner). We test by invoking via pwsh subprocess.
            $output = pwsh -NoLogo -NoProfile -File $script:ScriptPath -ResultsRoot $root -OutputDir $outDir 2>&1
            $LASTEXITCODE | Should -BeExactly 0
            ($output -join "`n") | Should -Match 'No results.jsonl found'
        }
    }
}
