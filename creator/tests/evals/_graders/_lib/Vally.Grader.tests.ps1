Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Describe 'Vally.Grader module' {
    BeforeAll {
        $modulePath = Join-Path $PSScriptRoot 'Vally.Grader.psm1'
        Import-Module $modulePath -Force
        $script:ScratchRoot = Join-Path (Split-Path -Parent $PSScriptRoot) '.test-scratch' | Join-Path -ChildPath 'Vally.Grader'
    }

    BeforeEach {
        if (Test-Path $script:ScratchRoot) { Remove-Item -Path $script:ScratchRoot -Recurse -Force }
        New-Item -ItemType Directory -Path $script:ScratchRoot -Force | Out-Null
        Remove-Item Env:\EVALUATE_GRADER_INPUT -ErrorAction SilentlyContinue
        Remove-Item Function:\az -ErrorAction SilentlyContinue
        $global:LASTEXITCODE = 0
    }

    AfterAll {
        if (Test-Path $script:ScratchRoot) { Remove-Item -Path $script:ScratchRoot -Recurse -Force }
        Remove-Item Env:\EVALUATE_GRADER_INPUT -ErrorAction SilentlyContinue
        Remove-Item Function:\az -ErrorAction SilentlyContinue
        Remove-Module Vally.Grader -Force -ErrorAction SilentlyContinue
    }

    # ---------- Read-EvaluateGraderInput ----------

    It 'throws clearly when EVALUATE_GRADER_INPUT is missing' {
        { Read-EvaluateGraderInput } | Should -Throw '*EVALUATE_GRADER_INPUT is not set*'
    }

    It 'parses grader input from a JSON file path' {
        $inputPath = Join-Path $script:ScratchRoot 'input.json'
        [System.IO.File]::WriteAllText($inputPath, '{"trajectory":{"id":"traj-1"}}', [System.Text.UTF8Encoding]::new($false))
        $env:EVALUATE_GRADER_INPUT = $inputPath

        $parsed = Read-EvaluateGraderInput

        $parsed.trajectory.id | Should -Be 'traj-1'
    }

    It 'parses grader input from raw JSON for direct unit tests (does not crash Test-Path on illegal chars)' {
        $env:EVALUATE_GRADER_INPUT = '{"config":{"name":"inline"}}'

        $parsed = Read-EvaluateGraderInput

        $parsed.config.name | Should -Be 'inline'
    }

    It 'parses grader input from raw JSON array' {
        $env:EVALUATE_GRADER_INPUT = '[1,2,3]'

        $parsed = Read-EvaluateGraderInput

        @($parsed).Count | Should -Be 3
    }

    It 'throws clearly for invalid grader input JSON' {
        $env:EVALUATE_GRADER_INPUT = '{not-json}'

        { Read-EvaluateGraderInput } | Should -Throw '*could not be parsed as JSON*'
    }

    It 'throws when EVALUATE_GRADER_INPUT is neither JSON nor existing file' {
        $env:EVALUATE_GRADER_INPUT = 'totally-not-a-real-path.json'

        { Read-EvaluateGraderInput } | Should -Throw "*neither inline JSON*nor an existing file*"
    }

    # ---------- Get-ResolvedWorkspaceId ----------

    It 'Get-ResolvedWorkspaceId returns a valid GUID' {
        $env:FABRIC_WORKSPACE_ID = '854cdd31-0d3d-48f9-9cfa-771d78b080d3'
        try {
            Get-ResolvedWorkspaceId | Should -Be '854cdd31-0d3d-48f9-9cfa-771d78b080d3'
        } finally {
            Remove-Item Env:\FABRIC_WORKSPACE_ID -ErrorAction SilentlyContinue
        }
    }

    It 'Get-ResolvedWorkspaceId throws on the literal placeholder' {
        $env:FABRIC_WORKSPACE_ID = '{{WORKSPACE_ID}}'
        try {
            { Get-ResolvedWorkspaceId } | Should -Throw '*FABRIC_WORKSPACE_ID is not set*'
        } finally {
            Remove-Item Env:\FABRIC_WORKSPACE_ID -ErrorAction SilentlyContinue
        }
    }

    It 'Get-ResolvedWorkspaceId rejects 36-char near-misses (all hyphens)' {
        $env:FABRIC_WORKSPACE_ID = '------------------------------------'
        try {
            { Get-ResolvedWorkspaceId } | Should -Throw '*not a valid workspace GUID*'
        } finally {
            Remove-Item Env:\FABRIC_WORKSPACE_ID -ErrorAction SilentlyContinue
        }
    }

    # ---------- Get-FabricAccessToken ----------

    It 'returns an access token from az CLI' {
        function global:az {
            $global:LASTEXITCODE = 0
            'token-123'
        }

        Get-FabricAccessToken -Resource 'https://api.fabric.microsoft.com' | Should -Be 'token-123'
    }

    It 'throws when az CLI token acquisition fails' {
        function global:az {
            $global:LASTEXITCODE = 7
            'not logged in'
        }

        { Get-FabricAccessToken -Resource 'https://api.fabric.microsoft.com' } | Should -Throw '*exit code 7*not logged in*'
    }

    It 'does NOT pass --headers Authorization on argv (regression: PR #282 bot-finding bearer-on-argv)' {
        # If a future refactor reintroduces explicit --headers Authorization
        # on the az rest path, the argv-leak finding from PR #282 review
        # comes back. This test pins the contract: az rest is called WITHOUT
        # an explicit Authorization header arg.
        $script:CapturedArgs = $null
        function global:az {
            $script:CapturedArgs = $args
            $global:LASTEXITCODE = 0
            '{"value":[]}'
        }

        Invoke-AzRestJson -Method get -Uri 'https://api.fabric.microsoft.com/v1/workspaces' | Out-Null

        $argString = ($script:CapturedArgs -join ' ')
        $argString | Should -Match '--only-show-errors'
        $argString | Should -Not -Match 'Authorization=Bearer'
    }

    # ---------- Invoke-AzRestJson ----------

    It 'Invoke-AzRestJson infers the Fabric resource from URI host' {
        $script:CapturedArgs = $null
        function global:az {
            $script:CapturedArgs = $args
            $global:LASTEXITCODE = 0
            '{"ok":true}'
        }

        Invoke-AzRestJson -Method get -Uri 'https://api.fabric.microsoft.com/v1/workspaces' | Out-Null

        ($script:CapturedArgs -join ' ') | Should -Match '--resource https://api.fabric.microsoft.com'
    }

    It 'Invoke-AzRestJson infers the Kusto resource from URI host' {
        $script:CapturedArgs = $null
        function global:az {
            $script:CapturedArgs = $args
            $global:LASTEXITCODE = 0
            '{"Tables":[]}'
        }

        Invoke-AzRestJson -Method post -Uri 'https://cluster.kusto.fabric.microsoft.com/v1/rest/mgmt' -Body '{}' | Out-Null

        ($script:CapturedArgs -join ' ') | Should -Match '--resource https://kusto.kusto.windows.net'
    }

    It 'Invoke-AzRestJson throws on unknown host (no silent default)' {
        { Invoke-AzRestJson -Method get -Uri 'https://example.com/foo' } | Should -Throw '*cannot infer Azure resource*'
    }

    # ---------- Write-GraderResult ----------

    It 'emits a valid GraderResult JSON payload with schemaVersion' {
        $json = Write-GraderResult -Name 'unit' -Passed $true -Score 1 -Evidence 'checked schema' -Metadata @{ key = 'value' }
        $result = $json | ConvertFrom-Json

        $result.schemaVersion | Should -Be 1
        $result.name | Should -Be 'unit'
        $result.kind | Should -Be 'code'
        $result.passed | Should -BeTrue
        $result.score | Should -Be 1
        $result.evidence | Should -Be 'checked schema'
        $result.metadata.key | Should -Be 'value'
    }

    It 'rejects passing results without evidence' {
        { Write-GraderResult -Name 'unit' -Passed $true -Score 1 -Evidence '' } | Should -Throw '*must include non-empty evidence*'
    }

    It 'rejects passing results with whitespace-only evidence' {
        { Write-GraderResult -Name 'unit' -Passed $true -Score 1 -Evidence "   `t  " } | Should -Throw '*must include non-empty evidence*'
    }

    It 'allows a failing result with empty evidence' {
        $json = Write-GraderResult -Name 'unit' -Passed $false -Score 0 -Evidence ''
        $result = $json | ConvertFrom-Json
        $result.passed | Should -BeFalse
        $result.score | Should -Be 0
        $result.evidence | Should -Be ''
    }

    It 'emits a single line on stdout' {
        $json = Write-GraderResult -Name 'unit' -Passed $true -Score 1 -Evidence 'ok'
        ($json -split "`n").Count | Should -Be 1
        ($json -split "`r").Count | Should -Be 1
    }

    # ---------- Invoke-WithPolling ----------

    It 'retries polling until a result appears' {
        $script:PollAttempts = 0
        $result = Invoke-WithPolling -Deadline 2 -Interval 0 -ScriptBlock {
            $script:PollAttempts++
            if ($script:PollAttempts -lt 3) { return $null }
            return 'ready'
        }

        $result | Should -Be 'ready'
        $script:PollAttempts | Should -Be 3
    }

    It 'returns null when polling deadline expires without a result' {
        $result = Invoke-WithPolling -Deadline 0 -Interval 0 -ScriptBlock { return $null }

        $result | Should -BeNullOrEmpty
    }

    It 'treats $false as a real result (not a "keep polling" sentinel)' {
        # Regression: the earlier version coerced everything through @() and
        # @($false).Count == 1, but the sentinel check was wrong and made
        # $false look like "no result yet". Fixed by checking $null only.
        $script:PollAttempts = 0
        $result = Invoke-WithPolling -Deadline 2 -Interval 0 -ScriptBlock {
            $script:PollAttempts++
            return $false
        }

        $result | Should -Be $false
        $script:PollAttempts | Should -Be 1
    }

    It 'treats empty string as a real result' {
        $result = Invoke-WithPolling -Deadline 0 -Interval 0 -ScriptBlock { return '' }

        $result | Should -Be ''
    }

    It 'treats 0 as a real result' {
        $result = Invoke-WithPolling -Deadline 0 -Interval 0 -ScriptBlock { return 0 }

        $result | Should -Be 0
    }

    It 'bails immediately on permanent failure (4xx exit code)' {
        # Regression: the earlier version retried EVERY exception until the
        # deadline, including unrecoverable failures like 401/403. A typo
        # could burn the full 24-hour ceiling. Now classification short-
        # circuits on permanent failures.
        $script:PollAttempts = 0
        $start = [System.Diagnostics.Stopwatch]::StartNew()
        try {
            Invoke-WithPolling -Deadline 60 -Interval 1 -ScriptBlock {
                $script:PollAttempts++
                throw 'az rest GET https://api.fabric.microsoft.com/foo failed (exit code 403): Forbidden'
            }
            throw 'should not reach here'
        } catch {
            $_.Exception.Message | Should -Match 'Polling aborted on permanent failure'
        }
        $start.Stop()

        $script:PollAttempts | Should -Be 1
        $start.Elapsed.TotalSeconds | Should -BeLessThan 5
    }

    It 'bails immediately on ConvertFrom-Json permanent failure' {
        $script:PollAttempts = 0
        {
            Invoke-WithPolling -Deadline 60 -Interval 1 -ScriptBlock {
                $script:PollAttempts++
                throw 'ConvertFrom-Json failed: invalid character'
            }
        } | Should -Throw '*Polling aborted on permanent failure*'

        $script:PollAttempts | Should -Be 1
    }

    It 'continues polling on transient errors (e.g. network blip)' {
        $script:PollAttempts = 0
        $result = Invoke-WithPolling -Deadline 5 -Interval 0 -ScriptBlock {
            $script:PollAttempts++
            if ($script:PollAttempts -lt 3) { throw 'connection reset by peer' }
            return 'recovered'
        }

        $result | Should -Be 'recovered'
        $script:PollAttempts | Should -Be 3
    }

    It 're-throws with last transient error message when deadline expires' {
        {
            Invoke-WithPolling -Deadline 0 -Interval 0 -ScriptBlock {
                throw 'connection reset by peer'
            }
        } | Should -Throw '*Polling did not produce a result*connection reset*'
    }

    It 'rejects Deadline > 3600 (1-hour ceiling, no more 24-hour budgets on typos)' {
        # Regression: the earlier ValidateRange ceiling was 86400 (1 day).
        # A typo (-Deadline 6000 instead of 600) could silently burn the
        # full budget. New ceiling is 3600 (1 hour), well above any
        # realistic Fabric eventual-consistency window.
        { Invoke-WithPolling -Deadline 3601 -Interval 1 -ScriptBlock { return 'x' } } | Should -Throw '*greater than the maximum allowed range of 3600*'
    }

    # ---------- Test-PermanentFailure ----------

    It 'classifies 4xx exit code as permanent' {
        $err = $null
        try { throw 'az rest GET foo failed (exit code 401): Unauthorized' } catch { $err = $_ }
        Test-PermanentFailure -ErrorRecord $err | Should -BeTrue
    }

    It 'classifies network blip as transient' {
        $err = $null
        try { throw 'connection reset by peer' } catch { $err = $_ }
        Test-PermanentFailure -ErrorRecord $err | Should -BeFalse
    }

    # ---------- Format-DiagnosticGuid / Uri / List ----------

    It 'Format-DiagnosticGuid produces a stable short SHA256 prefix' {
        $a = Format-DiagnosticGuid -Guid '854cdd31-0d3d-48f9-9cfa-771d78b080d3'
        $b = Format-DiagnosticGuid -Guid '854cdd31-0d3d-48f9-9cfa-771d78b080d3'
        $c = Format-DiagnosticGuid -Guid '00000000-0000-0000-0000-000000000000'

        $a | Should -Match '^sha256:[0-9a-f]{8}$'
        $a | Should -Be $b
        $a | Should -Not -Be $c
    }

    It 'Format-DiagnosticGuid returns empty for empty input' {
        Format-DiagnosticGuid -Guid '' | Should -Be ''
    }

    It 'Format-DiagnosticUri truncates the host' {
        $r = Format-DiagnosticUri -Uri 'https://trd-6etd7kt5rmf1tazqcd.z4.kusto.fabric.microsoft.com/v1/rest/mgmt'
        $r | Should -Match '^https://trd-6etd7kt5'
        $r | Should -Not -Match 'tazqcd'
    }

    It 'Limit-DiagnosticList caps long lists' {
        $items = 1..20 | ForEach-Object { "item$_" }
        $r = Limit-DiagnosticList -Items $items -Max 5
        $r | Should -Match 'item1, item2, item3, item4, item5 \(and 15 more\)'
    }

    It 'Limit-DiagnosticList passes through short lists unchanged' {
        $r = Limit-DiagnosticList -Items @('a','b','c') -Max 10
        $r | Should -Be 'a, b, c'
    }

    # ------------------------------------------------------------------
    # Helper invariants the diagnostic surface depends on. These are
    # the contracts that other graders implicitly rely on -- if the
    # output sizes or collision domain change, the failing trial
    # diagnostics either get truncated by the JSONL line cap or
    # collapse distinct workspaces onto the same short id.
    # ------------------------------------------------------------------

    It 'Format-DiagnosticGuid: 1000 distinct GUIDs map to 1000 distinct short ids (no collisions in normal verifier batches)' {
        # 1000 GUIDs is well above any single verifier run's GUID
        # cardinality (workspace + database + table + a handful of
        # query trips). 1000 random draws on a 2^32 space expects
        # ~0.00012 collisions; observing any in this test signals a
        # truncation bug, not bad luck.
        $shorts = @{}
        1..1000 | ForEach-Object {
            $g = [Guid]::NewGuid().ToString()
            $shorts[$g] = Format-DiagnosticGuid -Guid $g
        }
        $distinctShorts = ($shorts.Values | Sort-Object -Unique).Count
        $distinctShorts | Should -Be 1000
    }

    It 'Limit-DiagnosticList output is bounded even with very long items list' {
        # Verifiers feed Limit-DiagnosticList into a single-line
        # GraderResult JSON evidence field which gets written through
        # JSONL parsers that cap line length. The "and N more"
        # tail keeps the output O(Max) regardless of input size, so
        # a verifier that hands it 100k items still emits a short
        # string instead of OOM-ing the consumer.
        $items = 1..100000 | ForEach-Object { "veryLongDiagnosticItemNumber$_" }
        $r = Limit-DiagnosticList -Items $items -Max 5
        $r.Length | Should -BeLessThan 500
        $r | Should -Match '\(and 99995 more\)$'
    }

    It 'Invoke-AzRestJson removes the temp body file when az exits non-zero' {
        # Regression: if the finally block ever loses the bodyFile
        # cleanup (e.g. a refactor moves the scratch path out of the
        # try scope), every failing POST leaves a JSON body on disk.
        # On CI runners the scratch dir is wiped between jobs, but
        # on a developer laptop these accumulate.
        $previousLocation = Get-Location
        $cwd = Join-Path $script:ScratchRoot 'az-temp-cleanup'
        New-Item -ItemType Directory -Path $cwd -Force | Out-Null
        $scratchDir = Join-Path $cwd 'tests' | Join-Path -ChildPath '.vally-staging' | Join-Path -ChildPath 'grader-program'

        # Mock az to fail with a 4xx-shaped exit code AFTER the body
        # file has been written. The function's finally block is
        # responsible for cleanup regardless of exit code.
        function global:az { $global:LASTEXITCODE = 144; 'simulated error' }

        Set-Location -Path $cwd
        try {
            { Invoke-AzRestJson -Method post -Uri 'https://api.fabric.microsoft.com/v1/workspaces' -Body '{"k":"v"}' } |
                Should -Throw '*exit code 144*'

            if (Test-Path -LiteralPath $scratchDir) {
                $leftover = @(Get-ChildItem -LiteralPath $scratchDir -Filter 'body-*.json' -ErrorAction SilentlyContinue)
                $leftover.Count | Should -Be 0
            }
        } finally {
            Set-Location -Path $previousLocation
            Remove-Item Function:\az -ErrorAction SilentlyContinue
        }
    }

    # ------------------------------------------------------------------
    # Get-StimulusSkillTag: regression coverage for the "Skill" column
    # in the summarise step. If vally ever renames the field, these tests
    # fail loudly BEFORE a green-but-blank summary table ships.
    # The same logic is inlined in fabric-smoke-vally.yml (Summarise step);
    # if you change either you must change both.
    # ------------------------------------------------------------------
    It 'Get-StimulusSkillTag reads trajectory.stimulus.tags.skill from a real-shaped entry' {
        $entry = @{
            trajectory = @{
                stimulus = @{
                    name = 'Create basic Activator item'
                    tags = @{
                        type  = 'integration'
                        skill = 'activator-authoring-cli'
                        tier  = 'smoke'
                    }
                }
            }
            gradeResult = @{ passed = $true }
        }
        Get-StimulusSkillTag -Entry $entry | Should -Be 'activator-authoring-cli'
    }

    It 'Get-StimulusSkillTag returns (unknown-skill) when tags.skill is missing' {
        $entry = @{
            trajectory = @{
                stimulus = @{
                    name = 'Stim without skill tag'
                    tags = @{ type = 'integration'; tier = 'smoke' }
                }
            }
        }
        Get-StimulusSkillTag -Entry $entry | Should -Be '(unknown-skill)'
    }

    It 'Get-StimulusSkillTag returns (unknown-skill) when tags is missing' {
        $entry = @{ trajectory = @{ stimulus = @{ name = 'Stim with no tags object' } } }
        Get-StimulusSkillTag -Entry $entry | Should -Be '(unknown-skill)'
    }

    It 'Get-StimulusSkillTag returns (unknown-skill) when trajectory is missing' {
        $entry = @{ gradeResult = @{ passed = $true } }
        Get-StimulusSkillTag -Entry $entry | Should -Be '(unknown-skill)'
    }

    It 'Get-StimulusSkillTag returns (unknown-skill) for a null entry' {
        Get-StimulusSkillTag -Entry $null | Should -Be '(unknown-skill)'
    }

    It 'Get-StimulusSkillTag trims surrounding whitespace on the tag value' {
        $entry = @{ trajectory = @{ stimulus = @{ tags = @{ skill = '  eventhouse-authoring-cli  ' } } } }
        Get-StimulusSkillTag -Entry $entry | Should -Be 'eventhouse-authoring-cli'
    }

    It 'Get-StimulusSkillTag returns (unknown-skill) when tags.skill is whitespace-only' {
        $entry = @{ trajectory = @{ stimulus = @{ tags = @{ skill = '   ' } } } }
        Get-StimulusSkillTag -Entry $entry | Should -Be '(unknown-skill)'
    }

    It 'Get-StimulusSkillTag round-trips a real ConvertFrom-Json line shape' {
        # Pin the actual JSONL shape vally 0.5.0 writes -- this is the
        # field path the inline workflow logic depends on. A schema rename
        # upstream would surface here first.
        $jsonl = '{"trajectory":{"stimulus":{"name":"Create idempotent KQL table with retention","tags":{"type":"integration","skill":"eventhouse-authoring-cli","tier":"smoke"}}},"gradeResult":{"passed":true}}'
        $entry = $jsonl | ConvertFrom-Json
        Get-StimulusSkillTag -Entry $entry | Should -Be 'eventhouse-authoring-cli'
    }
}
