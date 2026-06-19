function Get-CopilotSessionStateRoot {
    return Join-Path $HOME ".copilot\session-state"
}

function Get-CopilotSessionEventsPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SessionId
    )

    return Join-Path (Join-Path (Get-CopilotSessionStateRoot) $SessionId) "events.jsonl"
}

function Find-CopilotSessionByCwd {
    <#
    .SYNOPSIS
    Discover a Copilot CLI session by matching the cwd recorded in session.start.

    .OUTPUTS
    The session ID (directory name) if found, otherwise $null.
    If $DiagnosticBuffer is provided (caller passes [ref] to a resizable list, e.g. [System.Collections.Generic.List[string]]), the
    function writes step-by-step trace lines into it so callers running inside
    a ThreadJob can surface failure detail without standalone re-running.
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$Cwd,
        [int]$MaxWaitSeconds = 5,
        [DateTime]$MinTimestampUtc = [DateTime]::MinValue,
        # Declared as [PSReference] WITHOUT a default value (NOT [ref]$X = $null).
        # PowerShell's argument transformer rejects a literal $null default for
        # [ref] / [PSReference] parameters, throwing
        #   "Cannot process argument transformation on parameter 'DiagnosticBuffer'.
        #    Reference type is expected in argument."
        # on every caller that omits -DiagnosticBuffer. Omitting the default lets the
        # binder leave $DiagnosticBuffer as $null (its natural unbound value) and
        # keeps the caller contract (pass [ref] to a resizable list, e.g.
        # [System.Collections.Generic.List[string]]). The _diag helper below
        # defensively checks .Value -is [IList] so non-list refs are still safe.
        [System.Management.Automation.PSReference]$DiagnosticBuffer
    )

    function _diag {
        param([string]$Message)
        if ($DiagnosticBuffer -and $DiagnosticBuffer.Value -is [System.Collections.IList]) {
            if ($DiagnosticBuffer.Value.IsFixedSize) { return }
            [void]$DiagnosticBuffer.Value.Add($Message)
        }
    }

    $sessionRoot = Get-CopilotSessionStateRoot
    if (-not (Test-Path $sessionRoot)) {
        _diag "sessionRoot not found: $sessionRoot"
        return $null
    }
    _diag "sessionRoot: $sessionRoot"

    try {
        $normalizedTarget = (Resolve-Path -LiteralPath $Cwd -ErrorAction Stop).Path
    } catch {
        $normalizedTarget = $Cwd
    }
    $normalizedTarget = $normalizedTarget.TrimEnd('\','/').ToLowerInvariant()
    _diag "normalizedTarget: $normalizedTarget"

    $useMinTs = $MinTimestampUtc -ne [DateTime]::MinValue
    $candidateMtimeFloor = if ($useMinTs) { $MinTimestampUtc } else { [DateTime]::UtcNow.AddHours(-1) }
    _diag "useMinTs=$useMinTs candidateMtimeFloor=$candidateMtimeFloor"

    $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)
    $candidateCount = 0
    $cwdMatches = 0
    while ((Get-Date) -lt $deadline) {
        # Sort candidates by LastWriteTimeUtc descending so the most-recently-
        # active session wins when multiple session-state directories share a
        # cwd (e.g. full-eval reuses $TestFolder across sequential plans). The
        # outer LastWriteTimeUtc >= candidateMtimeFloor filter combined with
        # MinTimestampUtc disambiguates between this invocation's session and
        # prior invocations in the same harness.
        $candidates = Get-ChildItem -LiteralPath $sessionRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTimeUtc -ge $candidateMtimeFloor } |
            Sort-Object LastWriteTimeUtc -Descending
        $candidateCount = @($candidates).Count

        foreach ($candidate in $candidates) {
            $eventsPath = Join-Path $candidate.FullName "events.jsonl"
            if (-not (Test-Path $eventsPath)) { continue }
            # Read up to the first 10 lines and find the session.start record.
            # Today's Copilot CLI always emits session.start as the first line,
            # but scanning a small prefix instead of assuming line 1 protects
            # against future CLI changes that might prepend other events.
            $startEvent = $null
            try {
                $reader = [System.IO.File]::OpenText($eventsPath)
                try {
                    for ($i = 0; $i -lt 10; $i++) {
                        $line = $reader.ReadLine()
                        if ($null -eq $line) { break }
                        if ([string]::IsNullOrWhiteSpace($line)) { continue }
                        try {
                            $candidateEvent = $line | ConvertFrom-Json
                        } catch { continue }
                        if ($candidateEvent.type -eq 'session.start') {
                            $startEvent = $candidateEvent
                            break
                        }
                    }
                } finally { $reader.Dispose() }
            } catch { continue }
            if (-not $startEvent) { continue }
            $eventCwd = $startEvent.data.context.cwd
            if ([string]::IsNullOrWhiteSpace($eventCwd)) { continue }
            $normalizedCandidate = $eventCwd.TrimEnd('\','/').ToLowerInvariant()
            if ($normalizedCandidate -ne $normalizedTarget) { continue }
            $cwdMatches++

            # First cwd match wins. The candidate list is pre-sorted by
            # LastWriteTimeUtc descending (above), so this returns the most-
            # recently-active session that matches the target cwd. Combined
            # with the MinTimestampUtc outer filter, this disambiguates between
            # multiple sessions sharing a cwd (e.g. full-eval call sites that
            # reuse $TestFolder across sequential Copilot invocations).
            _diag "matched $($candidate.Name) (candidates=$candidateCount cwdMatches=$cwdMatches)"
            return $candidate.Name
        }
        Start-Sleep -Milliseconds 250
    }
    _diag "no match (candidates=$candidateCount cwdMatches=$cwdMatches normalizedTarget=$normalizedTarget)"
    return $null
}

function Get-CopilotSessionTelemetry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SessionId,
        [int]$MaxWaitSeconds = 5
    )

    $sessionPath = Join-Path (Get-CopilotSessionStateRoot) $SessionId
    $eventsPath = Get-CopilotSessionEventsPath -SessionId $SessionId
    $deadline = (Get-Date).AddSeconds($MaxWaitSeconds)

    while (-not (Test-Path $eventsPath) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 250
    }

    if (-not (Test-Path $eventsPath)) {
        return [PSCustomObject]@{
            found                = $false
            sessionId            = $SessionId
            sessionPath          = $sessionPath
            eventsPath           = $eventsPath
            shutdownRecorded     = $false
            eventCount           = 0
            assistantTurnCount   = 0
            toolCallCount        = 0
            skillInvocationCount = 0
            skillsUsed           = @()
            skillInvocations     = @()
            tokenUsage           = $null
        }
    }

    $events = [System.Collections.Generic.List[object]]::new()
    foreach ($line in Get-Content -Path $eventsPath -Encoding UTF8) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        try {
            [void]$events.Add(($line | ConvertFrom-Json))
        }
        catch {
            continue
        }
    }

    $sessionStart = $events | Where-Object { $_.type -eq "session.start" } | Select-Object -First 1
    $sessionShutdown = $events | Where-Object { $_.type -eq "session.shutdown" } | Select-Object -Last 1

    $firstTimestamp = $null
    $lastTimestamp = $null
    if ($events.Count -gt 0) {
        try {
            $firstTimestamp = [DateTimeOffset]::Parse($events[0].timestamp)
        }
        catch {
        }

        try {
            $lastTimestamp = [DateTimeOffset]::Parse($events[$events.Count - 1].timestamp)
        }
        catch {
        }
    }

    $durationSeconds = $null
    if ($firstTimestamp -and $lastTimestamp) {
        $durationSeconds = [math]::Round(($lastTimestamp - $firstTimestamp).TotalSeconds, 1)
    }

    $skillEvents = @($events | Where-Object { $_.type -eq "skill.invoked" })
    $skillCounts = @{}
    foreach ($event in $skillEvents) {
        $skillName = $event.data.name
        if (-not $skillName) {
            continue
        }

        if (-not $skillCounts.ContainsKey($skillName)) {
            $skillCounts[$skillName] = @{
                name  = $skillName
                path  = $event.data.path
                count = 0
            }
        }

        $skillCounts[$skillName].count++
    }

    $skillsUsed = @($skillCounts.Keys | Sort-Object)
    $skillInvocations = @()
    foreach ($skillName in $skillsUsed) {
        $skillInvocations += [PSCustomObject]$skillCounts[$skillName]
    }

    $sessionContext = $null
    if ($sessionStart) {
        $sessionContext = $sessionStart.data.context
    }

    $tokenUsage = $null
    if ($sessionShutdown) {
        $tokenUsage = [PSCustomObject]@{
            currentModel          = $sessionShutdown.data.currentModel
            currentTokens         = $sessionShutdown.data.currentTokens
            systemTokens          = $sessionShutdown.data.systemTokens
            conversationTokens    = $sessionShutdown.data.conversationTokens
            toolDefinitionsTokens = $sessionShutdown.data.toolDefinitionsTokens
            totalPremiumRequests  = $sessionShutdown.data.totalPremiumRequests
            totalApiDurationMs    = $sessionShutdown.data.totalApiDurationMs
            modelMetrics          = $sessionShutdown.data.modelMetrics
        }
    }

    return [PSCustomObject]@{
        found                = $true
        sessionId            = $SessionId
        sessionPath          = $sessionPath
        eventsPath           = $eventsPath
        shutdownRecorded     = [bool]$sessionShutdown
        eventCount           = $events.Count
        copilotVersion       = if ($sessionStart) { $sessionStart.data.copilotVersion } else { $null }
        workingDirectory     = if ($sessionContext) { $sessionContext.cwd } else { $null }
        repository           = if ($sessionContext) { $sessionContext.repository } else { $null }
        branch               = if ($sessionContext) { $sessionContext.branch } else { $null }
        startTime            = if ($sessionStart) { $sessionStart.data.startTime } elseif ($firstTimestamp) { $firstTimestamp.ToString("o") } else { $null }
        endTime              = if ($lastTimestamp) { $lastTimestamp.ToString("o") } else { $null }
        durationSeconds      = $durationSeconds
        assistantTurnCount   = @($events | Where-Object { $_.type -eq "assistant.turn_start" }).Count
        toolCallCount        = @($events | Where-Object { $_.type -eq "tool.execution_start" }).Count
        skillInvocationCount = $skillEvents.Count
        skillsUsed           = $skillsUsed
        skillInvocations     = $skillInvocations
        tokenUsage           = $tokenUsage
    }
}

function Get-EvalResultTelemetry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ResultPath
    )

    if (-not (Test-Path $ResultPath)) {
        return $null
    }

    $content = Get-Content -Path $ResultPath -Raw -Encoding UTF8

    $workspaceName = $null
    $workspaceId = $null
    $workspaceWithIdMatch = [regex]::Match($content, '(?im)^\*\*Workspace:\*\*\s*(.+?)\s*\(([^()\r\n]+)\)\s*$')
    if ($workspaceWithIdMatch.Success) {
        $workspaceName = $workspaceWithIdMatch.Groups[1].Value.Trim()
        $workspaceId = $workspaceWithIdMatch.Groups[2].Value.Trim()
    }
    else {
        $workspaceOnlyMatch = [regex]::Match($content, '(?im)^\*\*Workspace:\*\*\s*(.+?)\s*$')
        if ($workspaceOnlyMatch.Success) {
            $workspaceName = $workspaceOnlyMatch.Groups[1].Value.Trim()
        }
    }

    $runDate = $null
    $runDateMatch = [regex]::Match($content, '(?im)^\*\*Run Date:\*\*\s*(.+?)\s*$')
    if ($runDateMatch.Success) {
        $runDate = $runDateMatch.Groups[1].Value.Trim()
    }

    $statusCounts = [ordered]@{
        PASS  = $null
        FAIL  = $null
        ERROR = $null
        SKIP  = $null
    }

    $totalCount = $null
    $totalsMatch = [regex]::Match($content, '(?ims)^## Totals\s*(.+?)(?:^##\s|\z)')
    if ($totalsMatch.Success) {
        $totalsSection = $totalsMatch.Groups[1].Value

        foreach ($status in @("PASS", "FAIL", "ERROR", "SKIP")) {
            $statusMatch = [regex]::Match($totalsSection, "(?im)^\|\s*$status\s*\|\s*(\d+)\s*\|")
            if ($statusMatch.Success) {
                $statusCounts[$status] = [int]$statusMatch.Groups[1].Value
            }
        }

        $totalMatch = [regex]::Match($totalsSection, '(?im)^\|\s*Total\s*\|\s*(\d+)\s*\|')
        if ($totalMatch.Success) {
            $totalCount = [int]$totalMatch.Groups[1].Value
        }
    }

    $attemptCounts = New-Object System.Collections.Generic.List[int]
    foreach ($match in [regex]::Matches($content, '(?im)Attempt Count[^0-9]*(\d+)')) {
        [void]$attemptCounts.Add([int]$match.Groups[1].Value)
    }
    foreach ($match in [regex]::Matches($content, '(?im)failed after\s+(\d+)\s+attempts')) {
        [void]$attemptCounts.Add([int]$match.Groups[1].Value)
    }

    $knownRetryCount = 0
    $maxAttemptCount = $null
    if ($attemptCounts.Count -gt 0) {
        $maxAttemptCount = ($attemptCounts | Measure-Object -Maximum).Maximum
        foreach ($attemptCount in $attemptCounts) {
            if ($attemptCount -gt 1) {
                $knownRetryCount += ($attemptCount - 1)
            }
        }
    }

    return [PSCustomObject]@{
        resultPath    = $ResultPath
        runDate       = $runDate
        workspaceName = $workspaceName
        workspaceId   = $workspaceId
        statusCounts  = [PSCustomObject]$statusCounts
        totalCount    = $totalCount
        retrySignals  = [PSCustomObject]@{
            retryMentions        = ([regex]::Matches($content, '(?im)\bretry\b')).Count
            attemptCountMentions = @($attemptCounts)
            maxAttemptCount      = $maxAttemptCount
            knownRetryCount      = $knownRetryCount
            maxRetryBailoutCount = ([regex]::Matches($content, 'EVAL-BAIL-003')).Count
        }
    }
}
