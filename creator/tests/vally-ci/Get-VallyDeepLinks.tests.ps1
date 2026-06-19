Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Describe 'Get-VallyDeepLinks' {
    BeforeAll {
        $scriptPath = Join-Path $PSScriptRoot 'Get-VallyDeepLinks.ps1'
        . $scriptPath
        $script:ScratchRoot = Join-Path (Split-Path -Parent $PSScriptRoot) '.test-scratch' | Join-Path -ChildPath 'Get-VallyDeepLinks'
        # Real gh.exe is on PATH in CI + dev. We shadow it for tests by
        # injecting a 'gh' function into the script scope; PowerShell
        # function lookup wins over the external binary.
    }

    BeforeEach {
        if (Test-Path $script:ScratchRoot) { Remove-Item -Path $script:ScratchRoot -Recurse -Force }
        New-Item -ItemType Directory -Path $script:ScratchRoot -Force | Out-Null
        # Reset any prior mock.
        Remove-Item -Path Function:\gh -ErrorAction SilentlyContinue
        $global:GhCalls = @()
        $global:GhResponses = @{}
    }

    AfterAll {
        if (Test-Path $script:ScratchRoot) { Remove-Item -Path $script:ScratchRoot -Recurse -Force }
        Remove-Item -Path Function:\gh -ErrorAction SilentlyContinue
    }

    # Helper: install a gh function that returns fixed JSON for known calls.
    function script:Install-GhMock {
        param(
            [hashtable]$JobsResponse,
            [hashtable]$ArtifactsResponse,
            [int]$ExitCode = 0
        )
        # Build JSONL responses per gh subcommand. The function pattern-matches
        # arguments using the URI fragment ('runs/.../jobs' vs 'runs/.../artifacts').
        # StrictMode-safe: hashtable property access on a missing key throws
        # PropertyNotFoundException under pwsh + Set-StrictMode -Version Latest
        # (Linux CI). Use IDictionary.Contains() instead. Same pattern as
        # Aggregate-VallyResults.ps1's Get-Prop helper.
        $jobsLines = @()
        if ($JobsResponse -and $JobsResponse.Contains('jobs') -and $JobsResponse['jobs']) {
            foreach ($j in $JobsResponse['jobs']) {
                $jobsLines += ($j | ConvertTo-Json -Compress)
            }
        }
        $artLines = @()
        if ($ArtifactsResponse -and $ArtifactsResponse.Contains('artifacts') -and $ArtifactsResponse['artifacts']) {
            foreach ($a in $ArtifactsResponse['artifacts']) {
                $artLines += ($a | ConvertTo-Json -Compress)
            }
        }
        $global:GhJobsLines = $jobsLines
        $global:GhArtLines  = $artLines
        $global:GhExit      = $ExitCode

        function global:gh {
            $global:GhCalls += ,@($args)
            $argStr = ($args -join ' ')
            if ($global:GhExit -ne 0) {
                $global:LASTEXITCODE = $global:GhExit
                Write-Output "mock failure"
                return
            }
            if ($argStr -match '/jobs') {
                $global:LASTEXITCODE = 0
                if ($global:GhJobsLines.Count -gt 0) { $global:GhJobsLines | ForEach-Object { Write-Output $_ } }
                return
            }
            if ($argStr -match '/artifacts') {
                $global:LASTEXITCODE = 0
                if ($global:GhArtLines.Count -gt 0) { $global:GhArtLines | ForEach-Object { Write-Output $_ } }
                return
            }
            $global:LASTEXITCODE = 1
            Write-Output "mock: unhandled gh call: $argStr"
        }
    }

    Context 'happy path: maps shard names to job IDs, artifacts to artifact IDs' {
        It 'returns expected Jobs and Artifacts hashtables' {
            Install-GhMock -JobsResponse @{
                jobs = @(
                    @{ id = 999111; name = 'shard (1)' }
                    @{ id = 999112; name = 'shard (2)' }
                    @{ id = 999113; name = 'shard (3)' }
                    @{ id = 999200; name = 'summarise' }
                    @{ id = 999300; name = 'setup' }
                )
            } -ArtifactsResponse @{
                artifacts = @(
                    @{ id = 555001; name = 'vally-smoke-results-12345-1-shard1' }
                    @{ id = 555002; name = 'vally-smoke-results-12345-1-shard2' }
                    @{ id = 555003; name = 'vally-smoke-results-12345-1-shard3' }
                    @{ id = 555900; name = 'smoke-results-schema-vally-12345-1' }
                )
            }

            $links = Get-VallyDeepLinks -RepoSlug 'owner/repo' -RunId '12345'
            $links.RunId | Should -Be '12345'
            $links.Jobs['shard1']     | Should -Be 999111
            $links.Jobs['shard2']     | Should -Be 999112
            $links.Jobs['shard3']     | Should -Be 999113
            $links.Jobs['summarise']  | Should -Be 999200
            $links.Jobs['setup']      | Should -Be 999300
            $links.Artifacts['vally-smoke-results-12345-1-shard1']   | Should -Be 555001
            $links.Artifacts['smoke-results-schema-vally-12345-1']   | Should -Be 555900
        }

        It 'accepts the key-prefixed matrix-job name shape "shard (shard=N)"' {
            # Some GitHub Actions surfaces / versions render matrix
            # jobs as "<name> (<key>=<value>)" instead of "<name>
            # (<value>)" when the matrix dimension key matches the
            # job name. Accept both shapes so downstream consumers
            # always find their shard0/shard1/... keys.
            Install-GhMock -JobsResponse @{
                jobs = @(
                    @{ id = 1001; name = 'shard (shard=0)' }
                    @{ id = 1002; name = 'shard (shard=1)' }
                    @{ id = 1003; name = 'shard (2)' }
                )
            } -ArtifactsResponse @{ artifacts = @() }
            $links = Get-VallyDeepLinks -RepoSlug 'owner/repo' -RunId '99'
            $links.Jobs['shard0'] | Should -Be 1001
            $links.Jobs['shard1'] | Should -Be 1002
            $links.Jobs['shard2'] | Should -Be 1003
        }

        It 'handles 11-digit (Int64-range) job and artifact IDs without overflow' {
            # Real GitHub Actions job + artifact IDs are routinely 10-11
            # digits (> Int32.MaxValue = 2147483647). If the code casts
            # to [int] it either throws or silently truncates. Smoke this
            # with realistic ID widths.
            $bigJobId      = [long]79962575230   # 11 digits, observed in a real run
            $bigArtifactId = [long]50000000123   # 11 digits, slightly past Int32 max
            Install-GhMock -JobsResponse @{
                jobs = @(@{ id = $bigJobId; name = 'shard (0)' })
            } -ArtifactsResponse @{
                artifacts = @(@{ id = $bigArtifactId; name = 'smoke-results-schema-vally-12345-1' })
            }
            $links = Get-VallyDeepLinks -RepoSlug 'owner/repo' -RunId '12345'
            $links.Jobs['shard0'] | Should -Be $bigJobId
            $links.Artifacts['smoke-results-schema-vally-12345-1'] | Should -Be $bigArtifactId
            # Defensive: verify type is Int64 so a future refactor that
            # narrows it back to Int32 fails this test.
            $links.Jobs['shard0'].GetType().FullName | Should -Be 'System.Int64'
            $links.Artifacts['smoke-results-schema-vally-12345-1'].GetType().FullName | Should -Be 'System.Int64'
        }
    }

    Context 'hard-fail on gh non-zero (no || true swallowing)' {
        It 'throws when gh exits non-zero' {
            Install-GhMock -JobsResponse @{} -ArtifactsResponse @{} -ExitCode 1
            { Get-VallyDeepLinks -RepoSlug 'owner/repo' -RunId '12345' } |
                Should -Throw -ExpectedMessage '*gh*failed*'
        }
    }

    Context 'required parameters' {
        It 'throws when RepoSlug is empty' {
            { Get-VallyDeepLinks -RepoSlug '' -RunId '12345' } | Should -Throw '*RepoSlug*'
        }
        It 'throws when RunId is empty' {
            { Get-VallyDeepLinks -RepoSlug 'owner/repo' -RunId '' } | Should -Throw '*RunId*'
        }
    }

    Context 'stretch: artifact filtering by run_attempt (fix #9)' {
        It 'filters artifacts to only those matching RunAttempt' {
            # A re-run yields artifacts from attempt 1 AND attempt 2.
            # Without -RunAttempt the renderer's first-match-wins picks
            # one by dict insertion order. With -RunAttempt=2 only the
            # attempt-2 artifacts appear.
            Install-GhMock -JobsResponse @{ jobs = @(@{ id = 1; name = 'shard (1)' }) } `
                           -ArtifactsResponse @{
                artifacts = @(
                    @{ id = 100; name = 'vally-smoke-results-12345-1-shard1' }
                    @{ id = 101; name = 'vally-smoke-results-12345-1-shard2' }
                    @{ id = 200; name = 'vally-smoke-results-12345-2-shard1' }
                    @{ id = 201; name = 'vally-smoke-results-12345-2-shard2' }
                    @{ id = 999; name = 'smoke-results-schema-vally-12345-2' }
                )
            }
            $links = Get-VallyDeepLinks -RepoSlug 'owner/repo' -RunId '12345' -RunAttempt '2'
            $links.Artifacts.Keys.Count | Should -Be 3
            $links.Artifacts['vally-smoke-results-12345-2-shard1'] | Should -Be 200
            $links.Artifacts['vally-smoke-results-12345-2-shard2'] | Should -Be 201
            $links.Artifacts['smoke-results-schema-vally-12345-2'] | Should -Be 999
            $links.Artifacts.ContainsKey('vally-smoke-results-12345-1-shard1') | Should -BeFalse
        }
        It 'returns all artifacts when RunAttempt is empty (back-compat)' {
            Install-GhMock -JobsResponse @{ jobs = @(@{ id = 1; name = 'shard (1)' }) } `
                           -ArtifactsResponse @{
                artifacts = @(
                    @{ id = 100; name = 'vally-smoke-results-12345-1-shard1' }
                    @{ id = 200; name = 'vally-smoke-results-12345-2-shard1' }
                )
            }
            $links = Get-VallyDeepLinks -RepoSlug 'owner/repo' -RunId '12345'
            $links.Artifacts.Keys.Count | Should -Be 2
        }
    }

    Context 'malformed gh response (fix #4)' {
        It 'emits a Write-Warning and skips the bad line rather than silently dropping it' {
            # Install a mock that returns one good JSONL line followed by
            # garbage. The function must skip the garbage with a warning
            # and still parse the good record.
            $global:GhJobsLines = @(
                ('{"id": 42, "name": "shard (1)"}'),
                ('this is not json {{{')
            )
            $global:GhArtLines = @()
            $global:GhExit    = 0
            function global:gh {
                $argStr = ($args -join ' ')
                if ($argStr -match '/jobs') {
                    $global:LASTEXITCODE = 0
                    $global:GhJobsLines | ForEach-Object { Write-Output $_ }
                    return
                }
                $global:LASTEXITCODE = 0
            }
            $warnings = @()
            $links = Get-VallyDeepLinks -RepoSlug 'owner/repo' -RunId '12345' -WarningVariable warnings -WarningAction SilentlyContinue
            $links.Jobs['shard1'] | Should -Be 42
            ($warnings -join ' ') | Should -Match 'malformed gh /jobs response'
        }
    }

    Context 'fix #11 regression-pin: log-line-offset feature removed' {
        It 'output does NOT carry a StimLogOffsets key' {
            Install-GhMock -JobsResponse @{ jobs = @(@{ id = 1; name = 'shard (1)' }) } `
                           -ArtifactsResponse @{ artifacts = @() }
            $links = Get-VallyDeepLinks -RepoSlug 'owner/repo' -RunId '12345'
            $links.Contains('StimLogOffsets') | Should -BeFalse
        }
        It 'does NOT accept a -LogRoot parameter' {
            Install-GhMock -JobsResponse @{ jobs = @() } -ArtifactsResponse @{ artifacts = @() }
            { Get-VallyDeepLinks -RepoSlug 'owner/repo' -RunId '12345' -LogRoot 'C:\nope' } |
                Should -Throw -ExpectedMessage '*LogRoot*'
        }
    }
}
