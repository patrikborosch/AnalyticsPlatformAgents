# Shared helper for run-full-tests.ps1: launching a single copilot CLI invocation
# under monitoring, with cwd-based session-state discovery and EVAL-BAIL detection.
#
# This file is dot-sourced from BOTH the parent orchestrator (run-full-tests.ps1)
# AND from per-chain ThreadJobs (parallel execution). It depends on
# copilot-session-telemetry.ps1 being dot-sourced first by the caller.

function Get-RunStatus {
    param(
        [Parameter(Mandatory = $false)]
        [psobject]$Run,
        [Parameter(Mandatory = $false)]
        [string]$ErrorMessage
    )

    if ($Run -and $Run.BailedOut) {
        return "bailed_out"
    }

    if ($ErrorMessage) {
        return "error"
    }

    if ($Run -and $Run.ExitCode -ne 0) {
        return "error"
    }

    return "completed"
}

function Get-CopilotWatchdogVerdict {
    <#
    .SYNOPSIS
    Pure decision function for the per-plan Copilot watchdog. Kept side-effect
    free so the threshold logic is unit-testable without a real copilot run.

    .DESCRIPTION
    Stall (sustained inactivity) takes precedence over the hard ceiling: it is
    the common silent-hang case and fires sooner. A non-positive threshold
    disables that arm (lets callers opt out of either check). Returns an object
    with TimedOut/Reason/Code.
    #>
    param(
        [Parameter(Mandatory = $true)][double]$IdleSeconds,
        [Parameter(Mandatory = $true)][double]$ElapsedSeconds,
        [Parameter(Mandatory = $true)][int]$StallSeconds,
        [Parameter(Mandatory = $true)][int]$CeilingSeconds
    )
    if ($StallSeconds -gt 0 -and $IdleSeconds -ge $StallSeconds) {
        return [PSCustomObject]@{ TimedOut = $true; Reason = 'stall'; Code = 'EVAL-TIMEOUT-001' }
    }
    if ($CeilingSeconds -gt 0 -and $ElapsedSeconds -ge $CeilingSeconds) {
        return [PSCustomObject]@{ TimedOut = $true; Reason = 'ceiling'; Code = 'EVAL-TIMEOUT-002' }
    }
    return [PSCustomObject]@{ TimedOut = $false; Reason = $null; Code = $null }
}

function Invoke-CopilotMonitored {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Prompt,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string]$LogPath,
        [Parameter(Mandatory = $true)]
        [string]$BailOutCode,
        [Parameter(Mandatory = $true)]
        [string]$Context,
        [int]$UnknownOptionThreshold = 3,
        # Watchdog thresholds. These are deliberately NOT a flat wall-clock cut:
        # StallTimeoutMinutes is an IDLE timer (no run-log growth) so a healthy
        # plan that is mid long-running tool call is never mistaken for a hang;
        # HardCeilingMinutes is a generous absolute backstop for busy-loops that
        # keep emitting output forever. Both are env-overridable (see body).
        [int]$StallTimeoutMinutes = 20,
        [int]$HardCeilingMinutes = 60
    )

    # CI tunability without code changes. Env wins when set to a positive int;
    # raise these if a legitimately slow plan is ever cut (none observed: the
    # slowest real plan to date ran ~27 min end-to-end, with no single silent
    # gap near 20 min).
    if (($env:FULL_EVAL_PLAN_STALL_MINUTES -as [int]) -gt 0) {
        $StallTimeoutMinutes = [int]$env:FULL_EVAL_PLAN_STALL_MINUTES
    }
    if (($env:FULL_EVAL_PLAN_HARD_CEILING_MINUTES -as [int]) -gt 0) {
        $HardCeilingMinutes = [int]$env:FULL_EVAL_PLAN_HARD_CEILING_MINUTES
    }

    # Placeholder used only for failure-path identifiers. The actual session-state
    # directory is discovered via cwd matching after the run -- see comment below.
    $sessionId = [System.Guid]::NewGuid().ToString()
    $invocationStartUtc = [DateTime]::UtcNow

    if (Test-Path $LogPath) {
        Remove-Item -Path $LogPath -Force
    }

    $job = Start-Job -ScriptBlock {
        param($PromptArg, $WorkingDirectoryArg, $LogPathArg)

        Set-Location $WorkingDirectoryArg
        # Copilot CLI assigns its own session ID. Previously this harness
        # pinned the ID via `--resume=<new-uuid>` so the log directory name
        # was deterministic, but `--resume` was redefined in CLI 1.0.46+ to
        # only resume EXISTING sessions and errors out for fresh UUIDs.
        # The session is discovered after the run by matching the
        # session.start record's cwd against $WorkingDirectoryArg.
        #
        # --no-ask-user: agent runs non-interactively (no clarification
        #   prompts). Required for headless full-eval since there is no
        #   human to answer; without it some plans stall on "Shall I
        #   proceed?" elicitations.
        # --share is OPT-IN via COPILOT_SHARE_TRANSCRIPT=true because the
        #   markdown transcript lands in the per-test cwd which is uploaded
        #   as a CI artifact -- transcripts may include bearer tokens or
        #   sensitive tool output and should not be published by default.
        $shareFlag = if ($env:COPILOT_SHARE_TRANSCRIPT -eq 'true') { @('--share') } else { @() }
        & copilot --yolo --no-ask-user @shareFlag -p $PromptArg 2>&1 | Tee-Object -FilePath $LogPathArg -Append

        [PSCustomObject]@{
            __copilot_exit_code = if ($LASTEXITCODE -ne $null) { [int]$LASTEXITCODE } else { 0 }
        }
    } -ArgumentList $Prompt, $WorkingDirectory, $LogPath

    $unsupportedCount = 0
    # ----- Watchdog state -------------------------------------------------
    # Progress = the run log growing. The harness already assumes the log is
    # written in near-real-time (the EVAL-BAIL early-kill below greps it every
    # second), so log growth is a sound "agent is doing something" signal. We
    # cut ONLY on sustained log silence (stall) or a generous absolute ceiling
    # -- never a flat wall-clock cut -- so a healthy plan mid long-running tool
    # call (10-15 min Spark job, warehouse provision, etc.) is never killed.
    $watchdogSw = [System.Diagnostics.Stopwatch]::StartNew()
    $lastActivityUtc = [DateTime]::UtcNow
    $lastLogLength = -1L
    $stallWarned = $false
    $stallSeconds = $StallTimeoutMinutes * 60
    $ceilingSeconds = $HardCeilingMinutes * 60
    while ((Get-Job -Id $job.Id).State -eq 'Running') {
        Start-Sleep -Milliseconds 1000

        if (Test-Path $LogPath) {

            # Progress detection: any growth in the run log resets the stall
            # timer. A working agent streams reasoning + tool output, so its log
            # grows continuously; only a genuinely stuck session stays silent.
            try {
                $len = (Get-Item -LiteralPath $LogPath -ErrorAction Stop).Length
                if ($len -ne $lastLogLength) {
                    $lastLogLength = $len
                    $lastActivityUtc = [DateTime]::UtcNow
                    $stallWarned = $false
                }
            } catch {
                # Transient read failure (file locked mid-append, etc.) -- skip
                # this tick's progress update; the next iteration retries.
                Write-Verbose "Watchdog: could not read log size for ${LogPath}: $_"
            }

            # Detect agent-emitted bail-out codes (EVAL-BAIL-001, EVAL-BAIL-003).
            # The agent writes these when it cannot proceed on a test case. Kill the
            # job immediately so the runner can move to the next plan instead of
            # waiting for the full timeout.
            $agentBail = Select-String -Path $LogPath -Pattern "EVAL-BAIL-00[13]" 2>$null | Select-Object -First 1
            if ($agentBail) {
                $detectedCode = if ($agentBail.Line -match "(EVAL-BAIL-00[13])") { $matches[1] } else { "EVAL-BAIL-00x" }
                Stop-Job -Id $job.Id -ErrorAction SilentlyContinue
                Remove-Job -Id $job.Id -Force -ErrorAction SilentlyContinue
                $discoveredId = Find-CopilotSessionByCwd -Cwd $WorkingDirectory -MaxWaitSeconds 5 -MinTimestampUtc $invocationStartUtc
                $effectiveId = if ($discoveredId) { $discoveredId } else { $sessionId }
                $sessionTelemetry = Get-CopilotSessionTelemetry -SessionId $effectiveId -MaxWaitSeconds 5
                return [PSCustomObject]@{
                    ExitCode              = 998
                    UnsupportedOptionHits = $unsupportedCount
                    BailedOut             = $true
                    BailOutCode           = $detectedCode
                    Context               = $Context
                    SessionId             = $effectiveId
                    SessionPath           = (Join-Path (Get-CopilotSessionStateRoot) $effectiveId)
                    SessionTelemetry      = $sessionTelemetry
                }
            }
        }

        # ----- Watchdog: cut ONLY on sustained silence (stall) or hard ceiling
        $idleSeconds = ([DateTime]::UtcNow - $lastActivityUtc).TotalSeconds
        if ($stallSeconds -gt 0 -and -not $stallWarned -and $idleSeconds -ge ($stallSeconds / 2)) {
            Write-Warning "[$Context] No Copilot output for $([math]::Round($idleSeconds / 60, 1)) min (stall limit ${StallTimeoutMinutes} min). Benign if mid long-running tool call; will terminate only after sustained silence."
            $stallWarned = $true
        }
        $verdict = Get-CopilotWatchdogVerdict -IdleSeconds $idleSeconds -ElapsedSeconds $watchdogSw.Elapsed.TotalSeconds -StallSeconds $stallSeconds -CeilingSeconds $ceilingSeconds
        if ($verdict.TimedOut) {
            $timeoutMsg = if ($verdict.Reason -eq 'stall') {
                "$($verdict.Code): no Copilot output for $([math]::Round($idleSeconds / 60, 1)) min (stall limit ${StallTimeoutMinutes} min) -- session presumed hung"
            } else {
                "$($verdict.Code): plan exceeded hard ceiling of ${HardCeilingMinutes} min wall-clock"
            }
            Write-Warning "[$Context] $timeoutMsg -- terminating and continuing to next plan."
            Stop-Job -Id $job.Id -ErrorAction SilentlyContinue
            Remove-Job -Id $job.Id -Force -ErrorAction SilentlyContinue
            $discoveredId = Find-CopilotSessionByCwd -Cwd $WorkingDirectory -MaxWaitSeconds 5 -MinTimestampUtc $invocationStartUtc
            $effectiveId = if ($discoveredId) { $discoveredId } else { $sessionId }
            $sessionTelemetry = Get-CopilotSessionTelemetry -SessionId $effectiveId -MaxWaitSeconds 5
            return [PSCustomObject]@{
                ExitCode              = 997
                UnsupportedOptionHits = $unsupportedCount
                BailedOut             = $false
                BailOutCode           = $verdict.Code
                TimedOut              = $true
                ErrorMessage          = $timeoutMsg
                Context               = $Context
                SessionId             = $effectiveId
                SessionPath           = (Join-Path (Get-CopilotSessionStateRoot) $effectiveId)
                SessionTelemetry      = $sessionTelemetry
            }
        }
    }

    $jobOutput = Receive-Job -Id $job.Id -Keep 2>$null
    $jobExitCode = 0
    if ($jobOutput) {
        $exitRecord = $jobOutput | Where-Object { $_ -is [PSCustomObject] -and $_.PSObject.Properties.Name -contains '__copilot_exit_code' } | Select-Object -Last 1
        if ($exitRecord) {
            $jobExitCode = [int]$exitRecord.__copilot_exit_code
        }
    }
    Remove-Job -Id $job.Id -Force -ErrorAction SilentlyContinue

    if (Test-Path $LogPath) {
        # Stream the captured log to the console (Out-Host) rather than to the
        # success stream. Returning $LogPath content via the success stream would
        # otherwise be concatenated with the returned PSCustomObject and produce
        # an Object[] from this function, breaking single-value comparisons by
        # the caller (e.g. `if ($run.ExitCode -eq 0)` still works due to
        # property-access projection, but `$run -is [PSCustomObject]` does not).
        Get-Content -Path $LogPath | Out-Host
    }

    if (Test-Path $LogPath) {
        $unsupportedCount = (Select-String -Path $LogPath -SimpleMatch "unknown option '--no-warnings'" 2>$null).Count
    }

    # Surface a threshold-based bail when too many unknown-option warnings were
    # emitted. All current callers pass [int]::MaxValue to disable this path;
    # honoring $UnknownOptionThreshold + $BailOutCode keeps the documented
    # function contract intact and lets future callers opt back in by passing a
    # finite threshold.
    if ($UnknownOptionThreshold -lt [int]::MaxValue -and $unsupportedCount -ge $UnknownOptionThreshold) {
        $discoveredId = Find-CopilotSessionByCwd -Cwd $WorkingDirectory -MaxWaitSeconds 5 -MinTimestampUtc $invocationStartUtc
        $effectiveId = if ($discoveredId) { $discoveredId } else { $sessionId }
        $sessionTelemetry = Get-CopilotSessionTelemetry -SessionId $effectiveId -MaxWaitSeconds 5
        return [PSCustomObject]@{
            ExitCode              = 999
            UnsupportedOptionHits = $unsupportedCount
            BailedOut             = $true
            BailOutCode           = $BailOutCode
            Context               = $Context
            SessionId             = $effectiveId
            SessionPath           = (Join-Path (Get-CopilotSessionStateRoot) $effectiveId)
            SessionTelemetry      = $sessionTelemetry
        }
    }

    # Discover the session by cwd. When the parent orchestrator runs plans in
    # parallel, every plan uses a UNIQUE $WorkingDirectory (per-plan subfolder
    # under $TestFolder), so cwd uniquely identifies the session even with
    # concurrent copilot processes. Defense-in-depth: $MinTimestampUtc rejects
    # candidates whose session-state directory predates this invocation.
    $discoveredId = Find-CopilotSessionByCwd -Cwd $WorkingDirectory -MaxWaitSeconds 10 -MinTimestampUtc $invocationStartUtc
    $effectiveId = if ($discoveredId) { $discoveredId } else { $sessionId }
    $sessionTelemetry = Get-CopilotSessionTelemetry -SessionId $effectiveId -MaxWaitSeconds 5

    return [PSCustomObject]@{
        ExitCode              = $jobExitCode
        UnsupportedOptionHits = $unsupportedCount
        BailedOut             = $false
        BailOutCode           = $null
        Context               = $Context
        SessionId             = $effectiveId
        SessionPath           = (Join-Path (Get-CopilotSessionStateRoot) $effectiveId)
        SessionTelemetry      = $sessionTelemetry
    }
}
