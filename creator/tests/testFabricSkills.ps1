param(
    [Parameter(Mandatory = $false)]
    [string]$directoryPath,
    [Parameter(Mandatory = $false)]
    [string]$testName,
    [Parameter(Mandatory = $false)]
    [string]$workspace,
    [Parameter(Mandatory = $false)]
    [int]$timeoutSeconds = 300,
    [Parameter(Mandatory = $false)]
    [int]$throttleLimit = 10,
    [Parameter(Mandatory = $false)]
    [string]$model = "claude-sonnet-4.5"
)

$ErrorActionPreference = "Stop"

# Load Copilot session telemetry helper (for per-test token usage capture).
. (Join-Path $PSScriptRoot "copilot-session-telemetry.ps1")

# Validate -throttleLimit. A value < 1 makes the parallel-jobs throttling loop
# (`while ... -ge $throttleLimit`) never progress and the run hangs indefinitely.
if ($throttleLimit -lt 1) {
    Write-Error "-throttleLimit must be >= 1 (got '$throttleLimit'). Use 1 for serial execution; 10 is the default."
    return
}

# Resolve the repository root (script lives under tests/)
$repoRoot = Split-Path -Parent $PSScriptRoot

# Reads each plugin's manifest at plugins/<name>/.github/plugin/plugin.json
# and returns the list of plugin names (from each manifest's `name` field --
# NOT the folder name, which could in principle drift). Used to derive the
# "other plugins to uninstall" set so shard isolation does not need a
# hardcoded list (adding a new plugin = adding plugins/<X>/, no edits to
# this runner). Sorts deterministically.
function Get-AllKnownPlugins {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )
    $pluginsDir = Join-Path $RepoRoot "plugins"
    if (-not (Test-Path $pluginsDir)) {
        return @()
    }
    $names = @()
    Get-ChildItem -Path $pluginsDir -Directory | ForEach-Object {
        $manifestPath = Join-Path $_.FullName ".github" "plugin" "plugin.json"
        if (Test-Path $manifestPath) {
            try {
                $m = Get-Content $manifestPath -Raw | ConvertFrom-Json
                if ($m.name) { $names += $m.name }
            } catch {
                Write-Host "WARN: Failed to parse $manifestPath ($($_.Exception.Message)); skipping." -ForegroundColor Yellow
            }
        }
    }
    return @($names | Sort-Object)
}

# CI MCP auth overlay: when CI_MCP_OVERLAY=true (set by .github/workflows/
# fabric-smoke-ephemeral.yml), patch the materialised .mcp.json for shards
# whose MCP servers need service-principal cert auth. Today this covers
# `powerbi-modeling-mcp` in the powerbi-authoring plugin. The materialised
# plugins/<x>/.mcp.json is gitignored on the internal repo (sync-step
# product), and the shipped marketplace.json comes from the manifests --
# so this overlay never reaches external users.
#
# The MCP server's `env` block receives CONCRETE values (not ${VAR}
# placeholders); Copilot CLI env-substitution behaviour for local plugin
# .mcp.json files is not officially documented, and concrete values are
# safer + easier to debug.
function Update-PluginMcpForCI {
    param(
        [Parameter(Mandatory = $true)][string]$PluginName,
        [Parameter(Mandatory = $true)][string]$RepoRoot
    )

    if ($env:CI_MCP_OVERLAY -ne 'true') { return }

    $azClientId = ($env:AZURE_CLIENT_ID ?? "").Trim()
    $azTenantId = ($env:AZURE_TENANT_ID ?? "").Trim()
    $azCertPath = ($env:AZURE_CLIENT_CERTIFICATE_PATH ?? "").Trim()
    if (-not $azClientId -or -not $azTenantId -or -not $azCertPath) {
        Write-Host "WARN: CI_MCP_OVERLAY=true but AZURE_* env not fully set; skipping MCP overlay for '$PluginName'." -ForegroundColor Yellow
        return
    }
    if (-not (Test-Path $azCertPath)) {
        Write-Host "WARN: AZURE_CLIENT_CERTIFICATE_PATH does not exist ($azCertPath); skipping MCP overlay for '$PluginName'." -ForegroundColor Yellow
        return
    }

    $mcpPath = Join-Path $RepoRoot "plugins" $PluginName ".mcp.json"
    if (-not (Test-Path $mcpPath)) { return }

    $mcp = Get-Content $mcpPath -Raw | ConvertFrom-Json
    if (-not $mcp.mcpServers) { return }

    $patched = @()
    if ($mcp.mcpServers.PSObject.Properties.Name -contains 'powerbi-modeling-mcp') {
        $server = $mcp.mcpServers.'powerbi-modeling-mcp'
        $serverArgs = @($server.args)
        if ($serverArgs -notcontains '--authmode=serviceprincipal') {
            $serverArgs += '--authmode=serviceprincipal'
        }
        # --skipconfirmation: bypass the MCP's Elicitation prompts (the MCP
        # raises these before the first write and the first query per
        # database; they would hang in headless CI where there is no user
        # to confirm). Documented in the upstream README under "Confirmation
        # prompts". Safe to set in CI because the smoke harness already
        # treats every test as auto-approved (--yolo + --no-ask-user).
        if ($serverArgs -notcontains '--skipconfirmation') {
            $serverArgs += '--skipconfirmation'
        }
        $server.args = $serverArgs
        $envBlock = [pscustomobject]([ordered]@{
                AZURE_CLIENT_ID               = $azClientId
                AZURE_TENANT_ID               = $azTenantId
                AZURE_CLIENT_CERTIFICATE_PATH = $azCertPath
            })
        if ($server.PSObject.Properties.Name -contains 'env') {
            $server.env = $envBlock
        }
        else {
            $server | Add-Member -NotePropertyName env -NotePropertyValue $envBlock -Force
        }
        $patched += 'powerbi-modeling-mcp'
    }

    if ($patched.Count -gt 0) {
        $json = $mcp | ConvertTo-Json -Depth 20
        [System.IO.File]::WriteAllText($mcpPath, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
        Write-Host "OK: patched $mcpPath for CI SP cert auth (servers: $($patched -join ', '))" -ForegroundColor Green
    }
}

# Post-install fallback: Copilot CLI installs plugins under a copy in
# $COPILOT_HOME (default $HOME/.copilot). If install reads the .mcp.json
# from the materialised source at install time, the pre-install patch
# above is sufficient. If install instead re-reads at runtime from the
# installed copy, this post-install patch keeps it in sync.
function Update-InstalledPluginMcpForCI {
    param([Parameter(Mandatory = $true)][string]$PluginName)

    if ($env:CI_MCP_OVERLAY -ne 'true') { return }
    $azClientId = ($env:AZURE_CLIENT_ID ?? "").Trim()
    $azTenantId = ($env:AZURE_TENANT_ID ?? "").Trim()
    $azCertPath = ($env:AZURE_CLIENT_CERTIFICATE_PATH ?? "").Trim()
    if (-not $azClientId -or -not $azTenantId -or -not $azCertPath) { return }
    # Mirror the Test-Path guard from Update-PluginMcpForCI: writing a path that
    # does not exist into the installed copy would overwrite a previously-good
    # config with a broken path, surfacing as confusing AAD errors later.
    if (-not (Test-Path $azCertPath)) {
        Write-Host "WARN: AZURE_CLIENT_CERTIFICATE_PATH does not exist ($azCertPath); skipping installed-plugin overlay for '$PluginName'." -ForegroundColor Yellow
        return
    }

    $installedRoot = if ($env:COPILOT_HOME) { $env:COPILOT_HOME } else { Join-Path $HOME ".copilot" }
    if (-not (Test-Path $installedRoot)) { return }
    # Search for any .mcp.json under installed-plugins/<name>/ or plugins/<name>/.
    $found = Get-ChildItem -Path $installedRoot -Filter ".mcp.json" -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -match [regex]::Escape($PluginName) }
    foreach ($file in $found) {
        try {
            $mcp = Get-Content $file.FullName -Raw | ConvertFrom-Json
            if (-not $mcp.mcpServers -or ($mcp.mcpServers.PSObject.Properties.Name -notcontains 'powerbi-modeling-mcp')) { continue }
            $server = $mcp.mcpServers.'powerbi-modeling-mcp'
            $serverArgs = @($server.args)
            if ($serverArgs -notcontains '--authmode=serviceprincipal') {
                $serverArgs += '--authmode=serviceprincipal'
            }
            if ($serverArgs -notcontains '--skipconfirmation') {
                $serverArgs += '--skipconfirmation'
            }
            $server.args = $serverArgs
            $envBlock = [pscustomobject]([ordered]@{
                    AZURE_CLIENT_ID               = $azClientId
                    AZURE_TENANT_ID               = $azTenantId
                    AZURE_CLIENT_CERTIFICATE_PATH = $azCertPath
                })
            if ($server.PSObject.Properties.Name -contains 'env') { $server.env = $envBlock }
            else { $server | Add-Member -NotePropertyName env -NotePropertyValue $envBlock -Force }
            $json = $mcp | ConvertTo-Json -Depth 20
            [System.IO.File]::WriteAllText($file.FullName, $json + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
            Write-Host "OK: also patched installed-plugin MCP at $($file.FullName)" -ForegroundColor Green
        }
        catch {
            Write-Host "WARN: failed to patch $($file.FullName) -- $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

# Validate that build_plugins.py has been run (materializes skills into plugin directories)
$pluginSkillsDir = Join-Path $repoRoot "plugins" "fabric-skills" "skills"
if (-not (Test-Path $pluginSkillsDir)) {
    Write-Host "ERROR: Plugin skills not materialized. Run 'python build/build_plugins.py' first." -ForegroundColor Red
    Write-Host "  Expected directory not found: $pluginSkillsDir" -ForegroundColor Red
    Write-Error "build_plugins.py must be run before executing tests."
    return
}

# Step 1-2: If directoryPath not provided, create a GUID-named temp directory
if (-not $directoryPath) {
    $guid = [System.Guid]::NewGuid().ToString()
    $directoryPath = Join-Path ([System.IO.Path]::GetTempPath()) $guid
    New-Item -ItemType Directory -Path $directoryPath -Force | Out-Null
    Write-Host "Created temp directory: $directoryPath"
}
else {
    if (-not (Test-Path $directoryPath)) {
        New-Item -ItemType Directory -Path $directoryPath -Force | Out-Null
    }
}
# Step 3 : Marketplace registration (per-plugin install moved into the
# group-by-plugin loop below, since different tests may target different
# plugins via the optional `plugin` field on each tests.json entry).
$marketplaceList = copilot plugin marketplace list 2>&1 | Out-String
if ($marketplaceList -match 'fabric-collection') {
    copilot plugin marketplace remove fabric-collection --force
}
copilot plugin marketplace add $repoRoot

# Helper: sweep stdio MCP child processes left behind by `copilot plugin
# uninstall` between plugin shards. Tolerant by design -- a missing match is
# the common case (not every plugin ships stdio MCPs).
function Invoke-StdioMcpSweep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PluginName
    )
    try {
        # Match by .mcp.json reference inside the plugin's install dir, or by
        # the npx command pattern these stdio MCPs tend to use. We avoid being
        # too broad on purpose -- a stray match on an unrelated node process
        # would be worse than leaving a stale MCP alive (the OS reaps them at
        # job end).
        $needle = "installed-plugins.*$([regex]::Escape($PluginName))"
        $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -and $_.CommandLine -match $needle }
        foreach ($p in $procs) {
            try {
                Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
                Write-Host "  swept stdio MCP child pid=$($p.ProcessId) for plugin '$PluginName'" -ForegroundColor DarkGray
            } catch {
                Write-Host "  (stdio MCP sweep skipped pid=$($p.ProcessId): $($_.Exception.Message))" -ForegroundColor DarkGray
            }
        }
    } catch {
        Write-Host "  (stdio MCP sweep error for '$PluginName': $($_.Exception.Message))" -ForegroundColor DarkGray
    }
}

# Step 4: Switch current directory to directoryPath
Push-Location $directoryPath
try {
    # Step 5: Read tests.json and run each test
    $testsJsonPath = Join-Path $repoRoot "tests" "tests.json"
    if (-not (Test-Path $testsJsonPath)) {
        Write-Error "tests.json not found at: $testsJsonPath"
        return
    }

    $tests = Get-Content $testsJsonPath -Raw | ConvertFrom-Json
    # Skip metadata entries (names starting with `_`, e.g. `_deprecated-tests-json-catalog`).
    # These are not real tests; they document the file's deprecation status and would
    # otherwise burn a full copilot --yolo invocation while always reporting pass
    # because their `expectedSkills` and `expectedResults` arrays are empty.
    $tests = @($tests | Where-Object { $_.name -and -not $_.name.StartsWith('_') })
    if ($testName -and $testName -ne 'all') {
        # Support comma-separated names: "a,b,c" runs just a, b, and c.
        $requested = $testName -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
        $tests = @($tests | Where-Object { $requested -contains $_.name })
        if ($tests.Count -eq 0) {
            Write-Error "No tests in tests.json matched -testName '$testName' (parsed as: $($requested -join ', '))"
            return
        }
        $missing = @($requested | Where-Object { $_ -notin ($tests.name) })
        if ($missing.Count -gt 0) {
            Write-Warning "Requested tests not found in tests.json (will be skipped): $($missing -join ', ')"
        }
        Write-Host "Running $($tests.Count) test(s): $((@($tests).name) -join ', ')" -ForegroundColor Cyan
    } else {
        Write-Host "Running all $($tests.Count) tests from tests.json" -ForegroundColor Cyan
    }

    # Resolve workspace name and ID for {{WORKSPACE}} / {{WORKSPACE_ID}} substitution
    $resolvedWorkspace = $workspace
    $resolvedWorkspaceId = $null
    $lastSetupPath = Join-Path $repoRoot "tests" "testdata" "last_setup.json"
    if (Test-Path $lastSetupPath) {
        $setupInfo = Get-Content $lastSetupPath -Raw | ConvertFrom-Json
        $resolvedWorkspaceId = $setupInfo.workspace_id
        if (-not $resolvedWorkspace) {
            $resolvedWorkspace = $setupInfo.workspace_name
        }
        Write-Host "Using workspace: $resolvedWorkspace (ID: $resolvedWorkspaceId)" -ForegroundColor Cyan
    }
    if (-not $resolvedWorkspace -and $env:FABRIC_TEST_WORKSPACE_NAME) {
        $resolvedWorkspace = $env:FABRIC_TEST_WORKSPACE_NAME
        Write-Host "Using workspace from env FABRIC_TEST_WORKSPACE_NAME: $resolvedWorkspace" -ForegroundColor Cyan
    }
    if (-not $resolvedWorkspace) {
        Write-Warning "No workspace specified. Tests with {{WORKSPACE}} placeholder will use it literally."
        Write-Warning "Provide -workspace, set FABRIC_TEST_WORKSPACE_NAME, or run setup_test_env.py first."
    }
    $dtFormat = "yyyy-MM-dd HH:mm:ss.fff"
    $allTestsStart = Get-Date
    Write-Host "Parallel throttle limit: $throttleLimit (concurrent copilot processes)" -ForegroundColor Cyan
    # Pass the path to copilot-session-telemetry.ps1 into each thread job so the
    # job can re-dot-source it in its own runspace.
    $telemetryHelperPath = Join-Path $PSScriptRoot "copilot-session-telemetry.ps1"

    # Thread-safe collections for results and output
    $resultsBag = [System.Collections.Concurrent.ConcurrentBag[hashtable]]::new()
    $outputLock = [object]::new()

    # ------------------------------------------------------------------
    # Group tests by their target plugin. Tests without an explicit
    # `plugin` field default to "fabric-skills" (the catch-all bundle).
    # The field may be a string OR a string array; when an array, the
    # FIRST entry decides the shard the test runs in (additional plugins
    # are accepted by the schema validator but only the primary one is
    # installed for the test's parallel batch). This keeps the runtime
    # behaviour deterministic and forward-compatible with a future
    # multi-plugin Vally schema.
    #
    # When ALL tests use the default plugin (no `plugin` field set), the
    # grouping collapses to a single shard and the behaviour is identical
    # to the pre-grouping path (one install, one parallel batch).
    # ------------------------------------------------------------------
    function Get-TestPrimaryPlugin {
        param($Test)
        $raw = $Test.plugin
        if ($null -eq $raw) { return "fabric-skills" }
        if ($raw -is [string]) {
            $v = $raw.Trim()
            if ([string]::IsNullOrWhiteSpace($v)) { return "fabric-skills" }
            return $v
        }
        if ($raw -is [System.Collections.IEnumerable] -and -not ($raw -is [string])) {
            foreach ($entry in $raw) {
                if ($entry -is [string]) {
                    $v = $entry.Trim()
                    if (-not [string]::IsNullOrWhiteSpace($v)) { return $v }
                }
            }
        }
        return "fabric-skills"
    }

    $knownPlugins = Get-AllKnownPlugins -RepoRoot $repoRoot

    $testsByPlugin = $tests | Group-Object { Get-TestPrimaryPlugin $_ }
    Write-Host ("Plugin shards: " + (($testsByPlugin | ForEach-Object { "$($_.Name)($($_.Count))" }) -join ', ')) -ForegroundColor Cyan

    $results = @()
    $allJobs = @()

    foreach ($shard in $testsByPlugin) {
        $shardPlugin = $shard.Name
        $shardTests = @($shard.Group)
        Write-Host ""
        Write-Host "=== Shard: plugin '$shardPlugin' ($($shardTests.Count) test(s)) ===" -ForegroundColor Cyan

        # Install the shard's plugin. Uninstall any previously-installed
        # fabric-collection plugin first so per-shard installs do not leak
        # skills/MCPs from the previous shard. We tolerate uninstall errors
        # (e.g. "not installed") since the first shard has nothing to remove.
        try {
            copilot plugin uninstall fabric-skills@fabric-collection 2>&1 | Out-Null
        } catch {}
        foreach ($otherPlugin in $knownPlugins) {
            if ($otherPlugin -ne $shardPlugin -and $otherPlugin -ne 'fabric-skills') {
                try { copilot plugin uninstall "$otherPlugin@fabric-collection" 2>&1 | Out-Null } catch {}
            }
        }
        # Sweep stdio MCP child processes from EVERY plugin we just
        # uninstalled (fabric-skills + every other known marketplace
        # plugin). Without this, an orphan stdio MCP child from a
        # previous shard can interfere with this shard's install.
        Invoke-StdioMcpSweep -PluginName 'fabric-skills'
        foreach ($otherPlugin in $knownPlugins) {
            if ($otherPlugin -ne $shardPlugin -and $otherPlugin -ne 'fabric-skills') {
                Invoke-StdioMcpSweep -PluginName $otherPlugin
            }
        }
        # CI MCP overlay (pre-install): patch the materialised
        # plugins/<shard>/.mcp.json so install reads the SP cert auth wiring.
        # No-op when CI_MCP_OVERLAY != 'true' (local dev runs unaffected).
        Update-PluginMcpForCI -PluginName $shardPlugin -RepoRoot $repoRoot
        copilot plugin install "$shardPlugin@fabric-collection"
        # CI MCP overlay: patch the installed plugin's .mcp.json after install
        # in case Copilot reads it at MCP-spawn time from the installed copy.
        # The pre-install patch above (in plugins/<x>/.mcp.json) covers the
        # install-time-copy case. Both run only when CI_MCP_OVERLAY=true.
        Update-InstalledPluginMcpForCI -PluginName $shardPlugin

        # Launch this shard's tests in parallel using thread jobs with throttling
        $jobs = @()
        foreach ($test in $shardTests) {
            $currentTestName = $test.name
            $safeName = $currentTestName -replace '[^a-zA-Z0-9_-]', '_'
            $outputFile = Join-Path $directoryPath "${safeName}_output.txt"
            $prompt = $test.prompt
            if ($resolvedWorkspace) {
                $prompt = $prompt -replace '{{WORKSPACE}}', $resolvedWorkspace
            }
        if ($resolvedWorkspaceId) {
            $prompt = $prompt -replace '{{WORKSPACE_ID}}', $resolvedWorkspaceId
        }
        # Anti-pattern guard: the agent must not reach for `Get-AzAccessToken`
        # or the PowerShell Az module in CI -- they prompt interactively and
        # hang the shard. If the agent needs Fabric REST in a shell fallback,
        # `az` (Azure CLI) is already authenticated as the smoke SP. Recommend
        # `az rest` (which uses the cached token implicitly without printing
        # it) and DO NOT mention any command that emits raw access tokens
        # into stdout -- per-test `_output.txt` is uploaded as a CI artifact
        # and any token printed by the agent would leak there.
        # This guidance does NOT override MCP-first routing; for skills that
        # ship an MCP server, the MCP path is still primary.
        $prompt += " IMPORTANT: If you need to call a Fabric REST endpoint from a shell, use the Azure CLI: az rest --method GET --url <endpoint> --resource https://api.fabric.microsoft.com (az reuses the cached token implicitly; never echo or print tokens). Do NOT use Get-AzAccessToken or the PowerShell Az module; they prompt interactively and will hang the test. Prefer the skill's MCP tools whenever the MCP supports the operation."
        $expectedSkills = $test.expectedSkills
        $expectedResults = @($test.expectedResults | ForEach-Object {
            $r = $_
            if ($resolvedWorkspaceId) { $r = $r -replace '{{WORKSPACE_ID}}', $resolvedWorkspaceId }
            $r
        })
        $flakyIssue = if ($test.flaky) { $test.flaky.githubIssue } else { $null }

        # Wait if we've hit the throttle limit
        while (@($jobs | Where-Object { $_.State -eq 'Running' }).Count -ge $throttleLimit) {
            Start-Sleep -Milliseconds 200
        }

        $job = Start-ThreadJob -ScriptBlock {
            param($testName, $prompt, $outputFile, $expectedSkills, $expectedResults, $dtFormat, $dirPath, $timeoutSeconds, $flakyIssue, $model, $telemetryHelperPath, $safeName)

            $testStart = Get-Date
            $lines = @()
            $errorMsg = $null
            $timedOut = $false

            # Per-test working directory: each test gets its own subdirectory
            # under the run's $dirPath. This serves two purposes:
            #  1. Isolation between parallel tests (up to $throttleLimit
            #     concurrent agents; default 10, configurable via -throttleLimit).
            #  2. The session.start record in events.jsonl captures this cwd,
            #     which lets us discover the matching session-state directory
            #     even when --resume=<new-uuid> doesn't pin the session ID
            #     (Copilot CLI 1.0.46+ regressed that behavior; see
            #     Find-CopilotSessionByCwd in copilot-session-telemetry.ps1).
            # Use $safeName (same sanitization as outputFile) so test names
            # containing characters invalid for Windows directories never break
            # New-Item or create unexpected nested paths.
            $perTestCwd = Join-Path $dirPath $safeName
            New-Item -ItemType Directory -Force -Path $perTestCwd | Out-Null

            # Generate a random session-id placeholder used only for
            # log lines and the fallback "no telemetry found" tokenUsage
            # record (we still want some identifier to reference). On any
            # supported CLI version the actual session-state directory is
            # discovered by cwd via Find-CopilotSessionByCwd below.
            $sessionId = [System.Guid]::NewGuid().ToString()
            $testStartUtc = [DateTime]::UtcNow

            # Run copilot as a separate process with a timeout.
            # --model pins the AI model so CI runs are reproducible and comparable across runs.
            # --no-ask-user: agent runs autonomously without stalling on
            #   ask_user prompts; required for headless smoke (no human to
            #   answer "Shall I proceed?" elicitations Rui observed).
            # --share is OPT-IN behind COPILOT_SHARE_TRANSCRIPT=true because
            #   the markdown transcript lands in the per-test cwd and that
            #   path is uploaded as a CI artifact -- transcripts may contain
            #   tokens or sensitive tool output and should not be published
            #   by default.
            # We do NOT pass --resume=<new-uuid> because that flag was
            # redefined on CLI 1.0.46+ to only resume EXISTING sessions; it
            # errors out for fresh UUIDs and prevents the test from running.
            # The agent generates its own session ID; we discover it after
            # the fact via Find-CopilotSessionByCwd matching on $perTestCwd.
            $modelFlag = if ([string]::IsNullOrWhiteSpace($model)) { "" } else { "--model `"$model`" " }
            $shareFlag = if ($env:COPILOT_SHARE_TRANSCRIPT -eq 'true') { "--share " } else { "" }
            try {
                $proc = Start-Process -FilePath "cmd.exe" `
                    -ArgumentList "/c", "copilot --yolo --no-ask-user $shareFlag$modelFlag-p `"$prompt`" > `"$outputFile`" 2>&1" `
                    -WorkingDirectory $perTestCwd `
                    -NoNewWindow -PassThru
                if (-not $proc.WaitForExit($timeoutSeconds * 1000)) {
                    $timedOut = $true
                    # Kill the entire process tree (cmd.exe + child copilot/node)
                    try { & taskkill /T /F /PID $proc.Id 2>&1 | Out-Null } catch {}
                    $errorMsg = "TIMEOUT: test exceeded ${timeoutSeconds}s limit"
                }
            }
            catch {
                $errorMsg = $_.ToString()
            }

            $testEnd = Get-Date
            $testDuration = ($testEnd - $testStart).TotalSeconds

            # Read the output
            $output = ""
            if (Test-Path $outputFile) {
                $output = Get-Content $outputFile -Raw -ErrorAction SilentlyContinue
                if (-not $output) { $output = "" }
            }

            # Build the display lines as structured objects (text + color)
            $lines += @{ Text = ""; Color = "White" }
            $lines += @{ Text = "=== Running test: $testName ==="; Color = "Cyan" }
            $startText = "  Starting test: $($testStart.ToString($dtFormat)) ... finished: $($testEnd.ToString($dtFormat)) duration: $([math]::Round($testDuration, 1)) s"
            $lines += @{ Text = $startText; Color = "White" }

            if ($errorMsg) {
                $lines += @{ Text = "  WARNING: copilot process returned an error: $errorMsg"; Color = "Yellow" }
            }

            # If timed out, mark as failed immediately
            if ($timedOut) {
                if ($flakyIssue) {
                    $lines += @{ Text = "  Test result: F (TIMEOUT — KNOWN FLAKY: $flakyIssue)"; Color = "Yellow" }
                    return @{
                        TestName   = $testName
                        Passed     = "F"
                        FlakyIssue = $flakyIssue
                        Lines      = $lines
                    }
                }
                $lines += @{ Text = "  Test result: N (TIMEOUT)"; Color = "Red" }
                return @{
                    TestName = $testName
                    Passed   = "N"
                    Lines    = $lines
                }
            }

            # Check expected skills
            $allSkillsFound = $true
            foreach ($skill in $expectedSkills) {
                if ($output -notmatch [regex]::Escape($skill)) {
                    $allSkillsFound = $false
                    $lines += @{ Text = "  MISSING skill: $skill"; Color = "Yellow" }
                }
                else {
                    $lines += @{ Text = "  Found skill: $skill"; Color = "Green" }
                }
            }

            # Check expected results
            $allResultsFound = $true
            foreach ($expected in $expectedResults) {
                if ($output -notmatch [regex]::Escape($expected)) {
                    $allResultsFound = $false
                    $lines += @{ Text = "  MISSING result: $expected"; Color = "Yellow" }
                }
                else {
                    $lines += @{ Text = "  Found result: $expected"; Color = "Green" }
                }
            }

            $passed = if ($allSkillsFound -and $allResultsFound) { "Y" } else { "N" }

            # If test failed but is marked flaky, downgrade to "F" (flaky failure)
            if ($passed -eq "N" -and $flakyIssue) {
                $passed = "F"
                $lines += @{ Text = "  KNOWN FLAKY — tracked at: $flakyIssue"; Color = "Yellow" }
            }
            elseif ($passed -eq "Y" -and $flakyIssue) {
                $lines += @{ Text = "  NOTE: test is marked flaky but passed this run ($flakyIssue)"; Color = "DarkYellow" }
            }

            $resultColor = switch ($passed) { "Y" { "Green" } "F" { "Yellow" } default { "Red" } }
            $lines += @{ Text = "  Test result: $passed"; Color = $resultColor }

            # Discovery strategy: walk ~/.copilot/session-state/* and find the
            # session whose session.start record has data.context.cwd ==
            # $perTestCwd. This is version-agnostic across CLI versions; the
            # session ID itself is not under our control (Copilot CLI assigns
            # one). We use $sessionId only as a fallback placeholder when
            # discovery returns nothing (so token-summary.jsonl always has an
            # identifier field).
            $tokenUsage = $null
            $telemetryError = $null
            $diagLines = [System.Collections.ArrayList]::new()
            try {
                if ($telemetryHelperPath -and (Test-Path $telemetryHelperPath)) {
                    . $telemetryHelperPath
                    $resolvedSessionId = $null
                    $cwdResolved = Find-CopilotSessionByCwd -Cwd $perTestCwd -MaxWaitSeconds 5 -MinTimestampUtc $testStartUtc -DiagnosticBuffer ([ref]$diagLines)
                    if ($cwdResolved) {
                        $resolvedSessionId = $cwdResolved
                    } else {
                        $resolvedSessionId = $sessionId
                        $telemetryError = "cwd-discovery returned null. trace: " + ($diagLines -join '; ')
                    }
                    # We already waited up to 5s in Find-CopilotSessionByCwd for
                    # the session-state directory + events.jsonl to appear. By the
                    # time we read here, the file already exists -- so a 5s budget
                    # on the inner telemetry read is just defensive padding for
                    # slow filesystems flushing the session.shutdown record.
                    $telemetry = Get-CopilotSessionTelemetry -SessionId $resolvedSessionId -MaxWaitSeconds 5
                    if ($telemetry -and $telemetry.found -and $telemetry.tokenUsage) {
                        $tu = $telemetry.tokenUsage
                        $inputTokens  = 0
                        $outputTokens = 0
                        if ($null -ne $tu.systemTokens)          { $inputTokens += [int]$tu.systemTokens }
                        if ($null -ne $tu.conversationTokens)    { $inputTokens += [int]$tu.conversationTokens }
                        if ($null -ne $tu.toolDefinitionsTokens) { $inputTokens += [int]$tu.toolDefinitionsTokens }
                        if ($null -ne $tu.currentTokens) {
                            $outputTokens = [Math]::Max(0, [int]$tu.currentTokens - $inputTokens)
                        }
                        $tokenUsage = @{
                            inputTokens       = $inputTokens
                            outputTokens      = $outputTokens
                            cacheReadTokens   = 0
                            cacheWriteTokens  = 0
                            totalApiDurationMs = $tu.totalApiDurationMs
                            sessionId         = $resolvedSessionId
                        }
                    } elseif (-not $telemetryError) {
                        $telemetryError = "telemetry not found for session $resolvedSessionId"
                    }
                }
            } catch {
                $telemetryError = $_.Exception.Message
            }
            if ($telemetryError) {
                $lines += @{ Text = "  (telemetry: $telemetryError)"; Color = "DarkGray" }
            }

            return @{
                TestName   = $testName
                Passed     = $passed
                FlakyIssue = $flakyIssue
                Lines      = $lines
                TokenUsage = $tokenUsage
            }
        } -ArgumentList $currentTestName, $prompt, $outputFile, $expectedSkills, $expectedResults, $dtFormat, $directoryPath, $timeoutSeconds, $flakyIssue, $model, $telemetryHelperPath, $safeName

        $jobs += $job
    }

    # Drain this shard's jobs before installing the next shard's plugin.
    # Lock + print loop is unchanged from the pre-shard version; results are
    # appended to the outer-scope $results array so the summary is one global
    # roll-up across all shards.
    $completedJobIds = @{}
    while ($completedJobIds.Count -lt $jobs.Count) {
        foreach ($job in $jobs) {
            if ($completedJobIds.ContainsKey($job.Id)) { continue }
            if ($job.State -eq 'Completed' -or $job.State -eq 'Failed') {
                [System.Threading.Monitor]::Enter($outputLock)
                try {
                    $completedJobIds[$job.Id] = $true

                    if ($job.State -eq 'Completed') {
                        $jobResult = Receive-Job -Job $job

                        foreach ($line in $jobResult.Lines) {
                            Write-Host $line.Text -ForegroundColor $line.Color
                        }

                        $resultEntry = @{
                            name   = $jobResult.TestName
                            passed = $jobResult.Passed
                        }
                        if ($jobResult.FlakyIssue) {
                            $resultEntry.flakyIssue = $jobResult.FlakyIssue
                        }
                        if ($jobResult.TokenUsage) {
                            $resultEntry.tokenUsage = $jobResult.TokenUsage
                        }
                        $results += $resultEntry
                    }
                    else {
                        $errInfo = Receive-Job -Job $job -ErrorAction SilentlyContinue
                        Write-Host ""
                        Write-Host "=== Test job FAILED ===" -ForegroundColor Red
                        Write-Host "  Error: $errInfo" -ForegroundColor Red
                    }
                }
                finally {
                    [System.Threading.Monitor]::Exit($outputLock)
                }

                Remove-Job -Job $job -Force
            }
        }
        Start-Sleep -Milliseconds 200
    }

    # Per-shard stdio MCP cleanup. Uninstalling a plugin via the CLI does not
    # always reap stdio MCP child processes (e.g. `npx <server>` spawns a node
    # subprocess). Without this sweep, a stale stdio MCP from shard N can
    # interfere with shard N+1's install -- a real CI footgun that surfaced
    # during planning.
    Invoke-StdioMcpSweep -PluginName $shardPlugin

    $allJobs += $jobs
    } # end foreach shard

    # Save results to testsResults.json
    $resultsPath = Join-Path $directoryPath "testsResults.json"
    $results | ConvertTo-Json -Depth 10 | Set-Content $resultsPath -Encoding UTF8

    $allTestsEnd = Get-Date
    $allTestsDuration = ($allTestsEnd - $allTestsStart).TotalSeconds

    Write-Host ""
    Write-Host "==============================" -ForegroundColor Cyan
    Write-Host "Tests started: $($allTestsStart.ToString($dtFormat)) tests finished: $($allTestsEnd.ToString($dtFormat)) duration: $([math]::Round($allTestsDuration, 1)) s"
    $passedCount = @($results | Where-Object { $_.passed -eq "Y" }).Count
    $flakyCount = @($results | Where-Object { $_.passed -eq "F" }).Count
    $failedCount = @($results | Where-Object { $_.passed -eq "N" }).Count
    $totalCount = $results.Count
    $summaryText = "Tests passed: $passedCount / $totalCount"
    if ($flakyCount -gt 0) {
        $summaryText += " ($flakyCount known-flaky failure$(if ($flakyCount -gt 1) { 's' }))"
    }
    # Exit status: flaky failures do not count as hard failures
    $allNonFlakyPassed = ($failedCount -eq 0)
    Write-Host $summaryText -ForegroundColor $(if ($allNonFlakyPassed) { "Green" } else { "Yellow" })
    Write-Host "Results saved to: $resultsPath" -ForegroundColor Green
    Write-Host "Test directory: $directoryPath"
}
finally {
    Pop-Location
}
