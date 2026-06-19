<#
.SYNOPSIS
Gather GitHub-Actions deep-link metadata for the current vally workflow
run: per-shard job IDs and uploaded artifact IDs. Used by
Export-VallySchemaArtifact.ps1 (Phase 3) to populate the per-skill
deepLinks.json sibling so the dashboard renderer can link a failing
chip directly to the GitHub job page that produced it.

.DESCRIPTION
Two GitHub REST calls per invocation (well under any rate-limit envelope
for the 5-shard summarise job):

  GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs       (paginated)
  GET /repos/{owner}/{repo}/actions/runs/{run_id}/artifacts  (paginated)

Hard-fails on any non-zero `gh` exit (same explicit-error pattern as
dashboard-build.yml:151-157 -- a swallowed failure here would silently
ship a dashboard with no per-shard deep links and look like "the
producer never wrote them"). Single retry with backoff on transient
failures (rate-limit / 502).

Shard label derivation: vally shard jobs are named like
"shard (1)" / "shard (2)" / ... (matrix job display name). The job's
`name` field is captured by gh as the matrix-rendered name. We extract
the trailing integer and present it as 'shard1', 'shard2', ... to match
the path-based shard label used in Aggregate-VallyResults.ps1 (which
parses shard\d+ from the artifact directory name). When the job name
does not match, the entry is included under its raw name so a future
matrix-name change is visible rather than silently dropped.

.PARAMETER RepoSlug
The owner/repo, e.g. 'gim-home/skills-for-fabric'. Typically passed
from $env:GITHUB_REPOSITORY.

.PARAMETER RunId
The numeric workflow run id from $env:GITHUB_RUN_ID.

.PARAMETER RunAttempt
Optional GITHUB_RUN_ATTEMPT. When provided, the artifact-listing pass
filters out artifacts that don't belong to this attempt (the per-shard
artifact name is `vally-smoke-results-<run_id>-<attempt>-shard<N>`
plus the schema artifact `smoke-results-schema-vally-<run_id>-<attempt>`).
Without filtering, a re-run sees artifacts from all attempts and the
renderer's first-match-wins picks one by dict insertion order. When
empty / not provided, all artifacts are returned (back-compat for
callers that don't know their attempt number).

.OUTPUTS
[hashtable] with keys:
  RunId           (string)     Echoed back.
  Jobs            (hashtable)  shardLabel -> job_id (int). Includes a
                                'summarise' entry when the summarise job
                                appears in the jobs list (Phase 4 may
                                render a top-level "summarise" deep link).
  Artifacts       (hashtable)  artifact-name (string) -> artifact_id (int).
                                Only artifacts associated with this run
                                (and, when RunAttempt is supplied, only
                                this attempt's artifacts).
#>
function Get-VallyDeepLinks {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoSlug,

        [Parameter(Mandatory = $true)]
        [string]$RunId,

        [Parameter(Mandatory = $false)]
        [AllowNull()]
        [AllowEmptyString()]
        [string]$RunAttempt
    )

    if ([string]::IsNullOrWhiteSpace($RepoSlug)) {
        throw "Get-VallyDeepLinks: RepoSlug is required (typically from `$env:GITHUB_REPOSITORY)."
    }
    if ([string]::IsNullOrWhiteSpace($RunId)) {
        throw "Get-VallyDeepLinks: RunId is required (typically from `$env:GITHUB_RUN_ID)."
    }

    $result = [ordered]@{
        RunId     = [string]$RunId
        Jobs      = @{}
        Artifacts = @{}
    }

    # Helper: invoke gh, capture stdout, throw on non-zero exit (with a
    # single retry on transient codes). Hard-fails like
    # dashboard-build.yml:151-157 -- no `|| true` here, ever.
    # stderr is dropped (2>$null) rather than merged with 2>&1 so a
    # warning printed by gh does not poison stdout and surface as a
    # JSON-parse failure for every record. These are listing calls,
    # not transcripts -- losing stderr noise is acceptable.
    function script:Invoke-Gh {
        param([string[]]$ArgList, [int]$MaxAttempts = 2)
        $attempt = 0
        while ($true) {
            $attempt++
            $stdout = & gh @ArgList 2>$null
            $exit = $LASTEXITCODE
            if ($exit -eq 0) { return $stdout }
            if ($attempt -ge $MaxAttempts) {
                throw "gh $($ArgList -join ' ') failed with exit $exit after $attempt attempt(s)."
            }
            # Backoff: 2s on retry (covers rate-limit hiccups and brief 5xx).
            Start-Sleep -Seconds 2
        }
    }

    # ---------------- Jobs ----------------
    # gh api emits one JSON object per matching record when --paginate is set
    # with --jq operating on .jobs[]. Each line is an individual job record
    # so a >100-job pagination boundary does not split a record across two
    # lines (gh stitches per .jobs[] element after concatenating pages).
    $jobsRaw = Invoke-Gh -ArgList @(
        'api',
        '--paginate',
        "repos/$RepoSlug/actions/runs/$RunId/jobs",
        '--jq', '.jobs[] | {id, name}'
    )
    # gh returns each JSON object on its own line when --jq is per-element.
    foreach ($line in @($jobsRaw -split "`r?`n")) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try {
            $job = $line | ConvertFrom-Json -ErrorAction Stop
        } catch {
            Write-Warning "Get-VallyDeepLinks: skipping malformed gh /jobs response line: $($_.Exception.Message)"
            continue
        }
        $name = [string]$job.name
        # IDs use [long] (Int64) -- real GitHub Actions job IDs are
        # routinely 10-11 digits (>2^31). [int] would overflow on
        # production runs and either throw or silently truncate.
        $id   = [long]$job.id
        # Matrix-rendered name has two common shapes depending on whether
        # the matrix has a single value or multiple keys per dimension:
        #   "shard (1)"          -- single-value matrix (the common case for
        #                          this workflow; matrix = { shard: [0, 1, ...] })
        #   "shard (shard=1)"    -- key-prefixed form some GitHub Actions
        #                          surfaces / versions emit when the matrix
        #                          variable name matches the job name
        # Accept both so the downstream lookup ("shard0", "shard1", ...)
        # works regardless of which form the runner produces.
        $m = [regex]::Match($name, '^\s*shard\s*\(\s*(?:shard\s*=\s*)?(\d+)\s*\)\s*$')
        if ($m.Success) {
            $shardLabel = "shard$($m.Groups[1].Value)"
            $result.Jobs[$shardLabel] = $id
            continue
        }
        # Other named jobs (setup / detect / summarise / grader-unit-tests /
        # nightly-alert): index by job name lowercased so the renderer can
        # reference 'summarise' / 'setup' for top-level deep links.
        $result.Jobs[$name.ToLowerInvariant()] = $id
    }

    # ---------------- Artifacts ----------------
    # When RunAttempt is supplied, filter to only artifacts whose name
    # ends with "-<attempt>" or "-<attempt>-shard<N>". A workflow re-run
    # carries artifacts from all attempts; without the filter, the
    # renderer's first-match-wins picks one by dict insertion order.
    $attemptFilter = $null
    if (-not [string]::IsNullOrWhiteSpace($RunAttempt)) {
        # Match: "<anything>-<runId>-<attempt>" or
        #        "<anything>-<runId>-<attempt>-shard<N>"
        # The runId anchors the attempt to avoid accidentally matching
        # a digit run inside an artifact name body.
        $attemptFilter = [regex]::new(
            ('-' + [regex]::Escape([string]$RunId) + '-' + [regex]::Escape([string]$RunAttempt) + '(-shard\d+)?$'),
            [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
        )
    }
    $artifactsRaw = Invoke-Gh -ArgList @(
        'api',
        '--paginate',
        "repos/$RepoSlug/actions/runs/$RunId/artifacts",
        '--jq', '.artifacts[] | {id, name}'
    )
    foreach ($line in @($artifactsRaw -split "`r?`n")) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try {
            $art = $line | ConvertFrom-Json -ErrorAction Stop
        } catch {
            Write-Warning "Get-VallyDeepLinks: skipping malformed gh /artifacts response line: $($_.Exception.Message)"
            continue
        }
        $artName = [string]$art.name
        if ($attemptFilter -and -not $attemptFilter.IsMatch($artName)) { continue }
        # IDs use [long] (Int64) -- real artifact IDs can exceed
        # 2^31 just like job IDs. [int] would overflow.
        $result.Artifacts[$artName] = [long]$art.id
    }

    return [hashtable]$result
}
