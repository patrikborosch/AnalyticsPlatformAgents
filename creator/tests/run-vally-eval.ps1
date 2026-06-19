<#
.SYNOPSIS
    Run Vally evaluations for skills-for-fabric with workspace substitution.

.DESCRIPTION
    Automates the local Vally eval workflow:
    1. Checks Node >= 22 is available
    2. Substitutes {{WORKSPACE}} placeholders in eval.yaml files
    3. Stages substituted copies to tests/.vally-staging/ (gitignored)
    4. Invokes npx @microsoft/vally-cli eval

.PARAMETER Workspace
    The Fabric workspace name to substitute into prompts. If not provided,
    prompts for it interactively.

.PARAMETER WorkspaceId
    The Fabric workspace GUID to substitute for {{WORKSPACE_ID}} in eval.yaml
    files. Required by Layer 2 program graders that template the workspace
    ID into live Fabric REST URLs, and by graders that need to assert the
    agent referenced the SPECIFIC provisioned workspace (e.g.
    document-workspace-agent). If not provided, the wrapper falls back to
    FABRIC_WORKSPACE_ID env var, tests/testdata/last_setup.json, or live
    Fabric workspace discovery in that order. When all sources are empty,
    the wrapper hard-fails with a clear error rather than letting the
    literal {{WORKSPACE_ID}} token slip into output-matches regex
    (crashing vally with an invalid-regex error) or into az rest URLs in
    Layer 2 graders (404).

.PARAMETER Skill
    Run only the eval for a specific skill (directory name under tests/evals/).
    Example: -Skill eventhouse-consumption-cli

.PARAMETER Suite
    Run a named suite from .vally.yaml (e.g., smoke, consumption, authoring, operations).
    Ignored if -Skill is specified.

.PARAMETER Runs
    Number of trials per stimulus. Default: 5.

.PARAMETER DryRun
    Only stage files (substitute {{WORKSPACE}}) without running Vally. Useful
    for inspecting the staged eval.yaml before spending tokens.

.PARAMETER SkillDir
    Override the skill discovery root. Use for composition matrix tests where
    you want to limit which skills are loaded. Path relative to repo root.

.PARAMETER ShardIndex
    Zero-based shard index for matrix sharding. Used with -ShardCount to run a
    deterministic slice of the discovered eval dirs (round-robin partition).

.PARAMETER ShardCount
    Total number of shards. When greater than 1, only the eval dirs assigned to
    -ShardIndex are staged and run. Ignored when -Skill is specified.

.PARAMETER EvalDirs
    Comma-separated list of eval directory names (under tests/evals/) to restrict
    the run to. When set, only those dirs are discovered/staged, overriding the
    full directory scan. Sharding (-ShardIndex/-ShardCount) still applies on top of
    the filtered set. Used by the PR-scoped smoke workflow to run only the evals
    matching the skills a PR touched. Ignored when -Skill is specified. Pass the
    literal "ALL" (or leave empty) to run the full discovered set.

.PARAMETER Workers
    Number of concurrent stimulus sessions passed to vally (--workers). 0 (the
    default) leaves vally's own default (5) in place.

.PARAMETER MaxRetries
    Max vally retries per stimulus on transient errors (timeout, rate-limit).
    Vally's default is 2 (which can amplify a session.idle timeout to
    3x the trial wall-time). Pass 0 to fail fast on first attempt; this
    matches our CI default since the flaky stims are the only ones that
    benefit from retries and they amplify wall-time without changing
    pass/fail outcomes. When omitted, vally's default applies.

.PARAMETER Baseline
    Run in baseline mode: every staged eval.yaml has its `environment.skills` block
    rewritten to an empty list so the agent runs without any Fabric skills loaded.
    Used to produce an apples-to-apples "with skills vs without skills" comparison
    that quantifies per-stim skill ROI. Other settings (prompts, graders, constraints,
    threshold) are unchanged. Baseline mode is informational, not a gate -- many
    graders will legitimately fail (skill-invocation, output-contains for skill-only
    outputs) because the agent can't call the Fabric APIs the prompt expects. That's
    the wanted signal: it's the delta to skills-loaded that shows the skill's value.

.EXAMPLE
    .\tests\run-vally-eval.ps1 -Workspace "skills-for-fabric-test-20260524" -Skill eventhouse-consumption-cli -Runs 3

.EXAMPLE
    .\tests\run-vally-eval.ps1 -Workspace "skills-for-fabric-test-20260524" -Suite smoke -Runs 1

.EXAMPLE
    .\tests\run-vally-eval.ps1 -Workspace "skills-for-fabric-test-20260524" -DryRun
#>

#Requires -Version 7.0

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$Workspace,

    [Parameter(Mandatory = $false)]
    [ValidateScript({
        if ([string]::IsNullOrWhiteSpace($_)) { return $true }
        $parsed = [Guid]::Empty
        if ([Guid]::TryParse($_.Trim(), [ref]$parsed)) { return $true }
        throw "-WorkspaceId must be a GUID (e.g. '11111111-2222-3333-4444-555555555555') or empty. Got: '$_'. The value is templated into live Fabric REST URLs by Layer 2 program graders; a typo here surfaces as a confusing 4xx far away from the cause."
    })]
    [string]$WorkspaceId,

    [Parameter(Mandatory = $false)]
    [string]$Skill,

    [Parameter(Mandatory = $false)]
    [string]$Suite,

    [Parameter(Mandatory = $false)]
    [int]$Runs = 5,

    [Parameter(Mandatory = $false)]
    [switch]$DryRun,

    [Parameter(Mandatory = $false)]
    [string]$SkillDir,

    [Parameter(Mandatory = $false)]
    [int]$ShardIndex = -1,

    [Parameter(Mandatory = $false)]
    [int]$ShardCount = 1,

    [Parameter(Mandatory = $false)]
    [string]$EvalDirs,

    [Parameter(Mandatory = $false)]
    [int]$Workers = 0,

    [Parameter(Mandatory = $false)]
    [int]$MaxRetries,

    [Parameter(Mandatory = $false)]
    [switch]$Baseline,

    [Parameter(Mandatory = $false)]
    [string]$ResultsDir
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -Baseline pins --skill-dir to an empty root to produce the WITHOUT-skills
# floor; -SkillDir overrides --skill-dir to a chosen scope. Both append to
# --skill-dir, and vally-cli (yargs) silently keeps the last value, so passing
# both together silently disables baseline mode while still labelling the run
# [BASELINE MODE] in stdout -- producing a near-zero skill-ROI delta that
# looks like "skills do not help" instead of erroring loudly. Enforce mutex
# at parse time so the failure is loud and immediate.
if ($Baseline -and $SkillDir) {
    Write-Error "-Baseline and -SkillDir are mutually exclusive. Baseline mode pins --skill-dir to an empty root and silently dropping the override would invalidate the WITHOUT-skills comparison."
    exit 1
}

$gitRoot = git rev-parse --show-toplevel 2>$null
if ($gitRoot) {
    $RepoRoot = Convert-Path $gitRoot
} else {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}

# --- Step 0: MCP service-principal cert auth (CI staging only) ---
# Native Vally MCP path. Each eval that needs powerbi-modeling-mcp declares it
# inline under `environment.mcpServers`. Committed YAML uses the interactive
# args (no --authmode=serviceprincipal, no env block) so local dev runs use
# the browser auth flow unchanged. In CI, the staging loop below adds the SP
# auth args + AZURE_* env to the STAGED copy under tests/.vally-staging/,
# leaving committed YAML untouched. Gate: $env:CI_MCP_OVERLAY -eq 'true'.
# See Add-CiPowerBiMcpAuthToStagedEval near the staging loop below.

# --- Step 1: Node version check ---
$nodeVersion = (node --version 2>$null)
if (-not $nodeVersion) {
    Write-Error "Node.js not found. Install Node 22+ (fnm install 22 && fnm use 22)."
    exit 1
}
$major = [int]($nodeVersion -replace '^v(\d+)\..*', '$1')
if ($major -lt 22) {
    Write-Error "Node $nodeVersion found but Node 22+ required (copilot-sdk needs Promise.withResolvers). Use: fnm use 22"
    exit 1
}
Write-Host "[OK] Node $nodeVersion" -ForegroundColor Green

# --- Step 2: Workspace ---
if (-not $Workspace) {
    $Workspace = Read-Host "Enter Fabric workspace name (e.g., skills-for-fabric-test-YYYYMMDD-HHmmss)"
    if (-not $Workspace) {
        Write-Error "Workspace name is required."
        exit 1
    }
}
Write-Host "[OK] Workspace: $Workspace" -ForegroundColor Green

function Assert-WorkspaceGuid {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Value,
        [Parameter(Mandatory = $true)]
        [string]$Source
    )
    if ([string]::IsNullOrWhiteSpace($Value)) { return }
    $parsed = [Guid]::Empty
    if (-not [Guid]::TryParse($Value.Trim(), [ref]$parsed)) {
        throw "Workspace ID from $Source is not a valid GUID: '$Value'. Fix the source (parameter, env var, or last_setup.json) before re-running -- the value is templated into live Fabric REST URLs by Layer 2 program graders and a typo here surfaces as a confusing 4xx far away from the cause."
    }
}

# Validate the -WorkspaceId script parameter at the earliest possible
# point so a typo in the caller (CI workflow, local dev) fails here
# instead of five layers deep when az rest 4xx-s on a bogus workspace.
# The same value is later templated into live Fabric REST URLs by Layer 2
# program graders, so the early-fail contract has to hold at this entry
# site, not only at the ValidateScript attribute on the param itself.
Assert-WorkspaceGuid -Value $WorkspaceId -Source '-WorkspaceId parameter'

$script:ResolvedWorkspaceId = if ($WorkspaceId) { $WorkspaceId.Trim() } else { '' }
function Get-WorkspaceIdForSubstitution {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkspaceName
    )

    if (-not [string]::IsNullOrWhiteSpace($script:ResolvedWorkspaceId)) {
        return $script:ResolvedWorkspaceId
    }

    if (-not [string]::IsNullOrWhiteSpace($env:FABRIC_WORKSPACE_ID)) {
        # FABRIC_WORKSPACE_ID is trusted as a string but NOT trusted as a GUID
        # until parsed -- the workflow surfaces it from setup outputs, but a
        # local dev run might point this at a wrong/stale value. Validating
        # here keeps the early-fail contract advertised on the parameter path.
        Assert-WorkspaceGuid -Value $env:FABRIC_WORKSPACE_ID -Source 'FABRIC_WORKSPACE_ID env var'
        $script:ResolvedWorkspaceId = $env:FABRIC_WORKSPACE_ID.Trim()
        Write-Host "[OK] Workspace ID from FABRIC_WORKSPACE_ID: $script:ResolvedWorkspaceId" -ForegroundColor Green
        return $script:ResolvedWorkspaceId
    }

    $lastSetupPath = Join-Path $RepoRoot "tests" | Join-Path -ChildPath "testdata" | Join-Path -ChildPath "last_setup.json"
    if (Test-Path $lastSetupPath) {
        try {
            $lastSetup = Get-Content $lastSetupPath -Raw -Encoding utf8 | ConvertFrom-Json -ErrorAction Stop
            if ($lastSetup.workspace_id -and $lastSetup.workspace_name -eq $WorkspaceName) {
                Assert-WorkspaceGuid -Value ([string]$lastSetup.workspace_id) -Source "tests/testdata/last_setup.json"
                $script:ResolvedWorkspaceId = [string]$lastSetup.workspace_id
                Write-Host "[OK] Workspace ID from tests/testdata/last_setup.json: $script:ResolvedWorkspaceId" -ForegroundColor Green
                return $script:ResolvedWorkspaceId
            }
        } catch {
            Write-Warning "Could not read $lastSetupPath while resolving {{WORKSPACE_ID}}: $($_.Exception.Message)"
        }
    }

    Write-Host "[INFO] Resolving workspace ID for '$WorkspaceName' with Fabric workspace discovery." -ForegroundColor Cyan
    # Capture stderr to a temp file (not merged with stdout) so warnings or
    # progress text from az do not corrupt the JSON payload we ConvertFrom-Json
    # below. --only-show-errors further suppresses non-error stderr noise.
    $stderrFile = [System.IO.Path]::GetTempFileName()
    try {
        $workspaceJson = & az rest --method get --resource "https://api.fabric.microsoft.com" --url "https://api.fabric.microsoft.com/v1/workspaces" -o json --only-show-errors 2>$stderrFile
        $exitCode = $LASTEXITCODE
        $stderrText = if (Test-Path -LiteralPath $stderrFile) { (Get-Content -LiteralPath $stderrFile -Raw -ErrorAction SilentlyContinue) } else { '' }
    } finally {
        if (Test-Path -LiteralPath $stderrFile) { Remove-Item -LiteralPath $stderrFile -Force -ErrorAction SilentlyContinue }
    }
    if ($exitCode -ne 0) {
        $text = ($workspaceJson | Out-String).Trim()
        $detail = if ($text) { $text } else { $stderrText }
        throw "Could not resolve {{WORKSPACE_ID}} because az rest workspace discovery failed (exit code $exitCode): $detail"
    }

    $workspaceList = ($workspaceJson | Out-String) | ConvertFrom-Json -ErrorAction Stop
    $workspaceMatches = @($workspaceList.value | Where-Object { $_.displayName -eq $WorkspaceName } | Select-Object -First 1)
    $match = if ($workspaceMatches.Count -gt 0) { $workspaceMatches[0] } else { $null }
    if (-not $match -or [string]::IsNullOrWhiteSpace([string]$match.id)) {
        throw "Could not resolve {{WORKSPACE_ID}} because workspace '$WorkspaceName' was not returned by Fabric workspace discovery."
    }

    Assert-WorkspaceGuid -Value ([string]$match.id) -Source "Fabric workspace discovery (az rest /v1/workspaces)"
    $script:ResolvedWorkspaceId = [string]$match.id
    Write-Host "[OK] Workspace ID from Fabric discovery: $script:ResolvedWorkspaceId" -ForegroundColor Green
    return $script:ResolvedWorkspaceId
}

# --- Step 3: Discover eval.yaml files ---
$evalsDir = Join-Path (Join-Path $RepoRoot "tests") "evals"
$stagingDir = Join-Path (Join-Path $RepoRoot "tests") ".vally-staging"

if ($Skill) {
    $evalFiles = @(Get-ChildItem -Path (Join-Path $evalsDir $Skill) -Filter "eval.yaml" -ErrorAction Stop)
    if ($evalFiles.Count -eq 0) {
        Write-Error "No eval.yaml found for skill '$Skill' at $evalsDir\$Skill\"
        exit 1
    }
} else {
    $evalFiles = @(Get-ChildItem -Path $evalsDir -Recurse -Filter "eval.yaml")
    if ($evalFiles.Count -eq 0) {
        Write-Error "No eval.yaml files found under $evalsDir"
        exit 1
    }
    # Optional eval-dir filter: when -EvalDirs is a non-empty, non-"ALL" CSV,
    # restrict the discovered set to those directory names only. Used by the
    # PR-scoped smoke workflow to run only the evals mapped to the skills a PR
    # touched. Applied BEFORE sharding so the round-robin partition only
    # distributes the filtered subset. An empty value or "ALL" is a no-op
    # (full discovered set runs).
    if (-not [string]::IsNullOrWhiteSpace($EvalDirs) -and $EvalDirs.Trim() -ne 'ALL') {
        $wanted = @($EvalDirs.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        $wantedSet = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
        foreach ($w in $wanted) { [void]$wantedSet.Add($w) }
        $evalFiles = @($evalFiles | Where-Object { $wantedSet.Contains($_.Directory.Name) })
        Write-Host "[OK] -EvalDirs filter '$EvalDirs' selected $($evalFiles.Count) eval.yaml file(s)" -ForegroundColor Green
        if ($evalFiles.Count -eq 0) {
            Write-Warning "-EvalDirs filter '$EvalDirs' matched no eval.yaml directories; nothing to run."
            exit 0
        }
    }
    # Optional sharding: deterministically partition the discovered eval dirs
    # across $ShardCount shards (round-robin over the sorted file list) and keep
    # only this shard's slice. Used by the matrix smoke workflow to fan the
    # smoke suite across parallel jobs. Stimulus-level tag filters (-Suite) still
    # apply within each shard's eval specs.
    if ($ShardCount -gt 1) {
        if ($ShardIndex -lt 0 -or $ShardIndex -ge $ShardCount) {
            Write-Error "ShardIndex ($ShardIndex) must be in range 0..$($ShardCount - 1) when ShardCount is $ShardCount."
            exit 1
        }
        $sorted = @($evalFiles | Sort-Object -Property FullName)
        $evalFiles = @(for ($idx = 0; $idx -lt $sorted.Count; $idx++) {
            if (($idx % $ShardCount) -eq $ShardIndex) { $sorted[$idx] }
        })
        Write-Host "[OK] Shard $ShardIndex/$ShardCount selected $($evalFiles.Count) eval.yaml file(s)" -ForegroundColor Green
        if ($evalFiles.Count -eq 0) {
            Write-Warning "Shard $ShardIndex/$ShardCount has no eval.yaml files; nothing to run."
            exit 0
        }
    }
}
Write-Host "[OK] Found $($evalFiles.Count) eval.yaml file(s)" -ForegroundColor Green

# --- Step 3b: Resolve suite -> stimulus tag filters (before staging so a
# dry run validates suite resolution without spending tokens) ---
# Vally 0.5.0 rejects --suite when combined with --eval-spec ("--suite cannot
# be combined with --eval-spec"). Because we MUST use --eval-spec to point at
# the substituted copies under tests/.vally-staging/, translate the suite's
# tags filter into one or more --tag flags, which are stimulus-level filters
# that ARE compatible with --eval-spec. This preserves the suite semantics
# ("run only stimuli tagged X") without re-engineering the staging mechanic.
$suiteTagPairs = @()
if ($Suite -and -not $Skill) {
    $vallyConfigPath = Join-Path $RepoRoot ".vally.yaml"
    if (-not (Test-Path $vallyConfigPath)) {
        Write-Error ".vally.yaml not found at $vallyConfigPath -- cannot resolve suite '$Suite'"
        exit 1
    }
    # Resolve suites.<name>.filter.<key> with a real YAML parser (PyYAML)
    # instead of an indentation-sensitive hand-rolled parser. Python and
    # PyYAML are already required dev dependencies (tests/requirements-dev.txt)
    # and are installed on the CI runner, so suite resolution is robust to
    # reformatting of .vally.yaml (tabs, comments, quoting, flow style).
    #
    # Filter shape: native vally `filter.<key>: <value(s)>` (NOT a `tags.`
    # nested layer). The previous `filter.tags.<key>` shape only worked via
    # this wrapper; native `vally eval --suite <name>` rejected it. The
    # current shape is identical between the two paths so suites stay
    # portable between the wrapper and the upstream CLI.
    #
    # Find a usable Python 3 interpreter. On Linux runners `python` is
    # frequently Python 2 (or absent), so try `python3` first and fall back
    # to `python`. -CommandType Application restricts to real executables
    # and skips the Windows App Installer "python" stub that opens the
    # Microsoft Store dialog instead of running anything. The ordered
    # Select-Object -First 1 avoids the v7 `??` operator (which would also
    # fail-open on a non-singleton array result).
    $python = @('python3', 'python') |
        ForEach-Object { Get-Command $_ -CommandType Application -ErrorAction SilentlyContinue } |
        Where-Object { $_ } |
        Select-Object -First 1
    if (-not $python) {
        Write-Error "Python 3 (with PyYAML) is required to resolve suite '$Suite' from .vally.yaml. Install Python 3 and 'pip install pyyaml'."
        exit 1
    }
    $pyScript = @'
import sys
import yaml

# Keys at the suite definition layer that are NOT tag filters. Anything else
# under `filter:` is treated as `<key>=<value(s)>` and passed to vally as a
# --tag arg. Vally's own native suite shape uses the same convention, so the
# wrapper's resolution stays portable.
RESERVED_FILTER_KEYS = set()

cfg_path, suite = sys.argv[1], sys.argv[2]
with open(cfg_path, encoding="utf-8") as fh:
    cfg = yaml.safe_load(fh) or {}
suites = cfg.get("suites", {}) or {}
if suite not in suites:
    sys.stderr.write("suite '%s' not found in .vally.yaml\n" % suite)
    sys.exit(2)
flt = (suites[suite] or {}).get("filter", {}) or {}
# Legacy `filter.tags.X` shape -- emit a clear migration error if anyone
# hand-edits .vally.yaml back to the deprecated form, instead of silently
# dropping the filter and producing a confusing "no tag filters" downstream.
if "tags" in flt and isinstance(flt["tags"], dict):
    sys.stderr.write(
        "suite '%s' uses the deprecated filter.tags.<key> shape. "
        "Migrate to filter.<key> (see .vally.yaml head comment).\n" % suite
    )
    sys.exit(4)
tag_pairs = {k: v for k, v in flt.items() if k not in RESERVED_FILTER_KEYS}
if not tag_pairs:
    sys.stderr.write("suite '%s' has no filter keys\n" % suite)
    sys.exit(3)
for key, val in tag_pairs.items():
    if isinstance(val, (list, tuple)):
        values = ",".join(str(v) for v in val)
    else:
        values = str(val)
    print("%s=%s" % (key, values))
'@
    $tagOutput = $pyScript | & $python.Source - $vallyConfigPath $Suite
    $pyExit = $LASTEXITCODE
    if ($pyExit -ne 0) {
        Write-Error "Could not resolve suite '$Suite' from .vally.yaml (python/PyYAML exit code $pyExit). Verify the suite exists and PyYAML is installed."
        exit 1
    }
    $suiteTagPairs = @($tagOutput | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '=' })
    if ($suiteTagPairs.Count -eq 0) {
        Write-Error "Suite '$Suite' resolved to no tag filters in .vally.yaml."
        exit 1
    }
    Write-Host "[OK] Suite '$Suite' resolves to: $($suiteTagPairs -join ' ')" -ForegroundColor Green
}



# --- MCP staging helpers (CI-only SP cert auth injection) ---
# Vally has no native ${env:VAR} expansion in eval.yaml (only ${eval.<key>}
# metadata vars are recognised; see the @microsoft/vally-cli package source
# at packages/core/src/experiment/interpolate.ts). Committed eval.yaml
# therefore uses the INTERACTIVE form of the powerbi-modeling-mcp args (no
# --authmode=serviceprincipal, no env block), keeping local-dev runs working
# with the browser auth flow unchanged.
#
# In CI ($env:CI_MCP_OVERLAY -eq 'true'), the staging loop rewrites the
# STAGED copy to append --authmode=serviceprincipal --skipconfirmation and
# inject the AZURE_CLIENT_ID / AZURE_TENANT_ID / AZURE_CLIENT_CERTIFICATE_PATH
# env block from process env. Committed YAML is untouched; staged copies live
# under tests/.vally-staging/ (gitignored). This replaces the legacy
# plugin-install-time overlay that used to live in
# tests/vally-ci/Apply-McpCiOverlay.ps1.
function script:ConvertTo-YamlSingleQuotedString {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function script:Add-CiPowerBiMcpAuthToStagedEval {
    <#
    .SYNOPSIS
        Rewrite a staged eval.yaml string to add SP cert auth + env block to
        the powerbi-modeling-mcp server, when running in CI.
    .DESCRIPTION
        Sentinel: looks for `^    powerbi-modeling-mcp:` (the actual MCP
        server key in the staged content) so this fires for ANY eval that
        declares the server, not just files containing wrapper-internal
        placeholders.
        No-op when CI_MCP_OVERLAY is not 'true' (local dev path).
        Throws (fail-fast) when CI_MCP_OVERLAY is set but the required
        AZURE_* env vars are empty or the cert file does not exist.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Content,
        [Parameter(Mandatory = $true)][string]$RelativePath
    )

    if ($env:CI_MCP_OVERLAY -ne 'true') { return $Content }
    if ($Content -notmatch '(?m)^\s{4}powerbi-modeling-mcp:\s*$') { return $Content }

    $azClientId = ($env:AZURE_CLIENT_ID ?? '').Trim()
    $azTenantId = ($env:AZURE_TENANT_ID ?? '').Trim()
    $azCertPath = ($env:AZURE_CLIENT_CERTIFICATE_PATH ?? '').Trim()

    if (-not $azClientId -or -not $azTenantId -or -not $azCertPath) {
        throw "Eval '$RelativePath' declares powerbi-modeling-mcp and CI_MCP_OVERLAY=true, but AZURE_CLIENT_ID / AZURE_TENANT_ID / AZURE_CLIENT_CERTIFICATE_PATH are required and at least one is empty."
    }
    if (-not (Test-Path -LiteralPath $azCertPath)) {
        throw "Eval '$RelativePath' declares powerbi-modeling-mcp and CI_MCP_OVERLAY=true, but AZURE_CLIENT_CERTIFICATE_PATH does not exist on disk: $azCertPath"
    }

    # The base args block (interactive form) is what committed evals carry.
    # We do an exact string replace to add the SP cert auth flags + env block.
    # If the user reformats this block (whitespace / quoting / line order),
    # the Replace will not match and the helper throws so the drift is loud.
    $baseArgs = @'
      args:
        - "-y"
        - "@microsoft/powerbi-modeling-mcp@latest"
        - "--start"
'@

    $ciArgs = @"
      args:
        - "-y"
        - "@microsoft/powerbi-modeling-mcp@latest"
        - "--start"
        - "--authmode=serviceprincipal"
        - "--skipconfirmation"
      env:
        AZURE_CLIENT_ID: $(ConvertTo-YamlSingleQuotedString $azClientId)
        AZURE_TENANT_ID: $(ConvertTo-YamlSingleQuotedString $azTenantId)
        AZURE_CLIENT_CERTIFICATE_PATH: $(ConvertTo-YamlSingleQuotedString $azCertPath)
"@

    # Normalise line endings of both the haystack and the needle to LF so the
    # exact-match Replace works regardless of whether the eval.yaml on disk
    # uses CRLF (Windows checkout) or LF (Linux runner). The output is also
    # LF; the WriteAllText caller does not re-CRLF, which matches the rest of
    # the staging pipeline's behaviour (UTF-8 no-BOM, LF preserved).
    $contentLF  = $Content  -replace "`r`n", "`n"
    $baseArgsLF = $baseArgs -replace "`r`n", "`n"
    $ciArgsLF   = $ciArgs   -replace "`r`n", "`n"
    if (-not $contentLF.Contains($baseArgsLF)) {
        throw "Eval '$RelativePath' declares powerbi-modeling-mcp but the expected base args block was not found verbatim. Reformatting the powerbi-modeling-mcp args block under tests/evals/<skill>/eval.yaml will break the CI staging rewrite. Keep the args in the canonical form used by the 5 powerbi-authoring evals."
    }
    return $contentLF.Replace($baseArgsLF, $ciArgsLF)
}

# --- Step 4: Stage with {{WORKSPACE}} substitution ---
if (Test-Path $stagingDir) {
    Remove-Item -Recurse -Force $stagingDir
}
New-Item -ItemType Directory -Path $stagingDir -Force | Out-Null

# Copy shared eval support folders that staged eval.yaml files reference with
# relative environment.files paths, for example ../_graders.
foreach ($supportDirName in @('_graders')) {
    $sourceSupportDir = Join-Path $evalsDir $supportDirName
    if (Test-Path $sourceSupportDir) {
        Copy-Item -Path $sourceSupportDir -Destination (Join-Path $stagingDir $supportDirName) -Recurse -Force
    }
}

$stagedFiles = @()
foreach ($evalFile in $evalFiles) {
    $relativePath = $evalFile.FullName.Substring($evalsDir.Length + 1)
    $destPath = Join-Path $stagingDir $relativePath
    $destDir = Split-Path -Parent $destPath

    New-Item -ItemType Directory -Path $destDir -Force | Out-Null

    $content = Get-Content $evalFile.FullName -Raw -Encoding utf8
    $substituted = $content.Replace('{{WORKSPACE}}', $Workspace)
    if ($substituted.Contains('{{WORKSPACE_ID}}')) {
        # Resolve the workspace GUID lazily ONLY when an eval actually
        # uses {{WORKSPACE_ID}}, so evals that don't need it never trigger
        # a Fabric workspace-discovery round trip. The helper walks the
        # ingest sites in priority order: -WorkspaceId param,
        # FABRIC_WORKSPACE_ID env, last_setup.json, live discovery.
        $workspaceIdForEval = Get-WorkspaceIdForSubstitution -WorkspaceName $Workspace
        if ([string]::IsNullOrWhiteSpace($workspaceIdForEval)) {
            # Hard-fail with a clear error instead of letting the literal
            # `{{WORKSPACE_ID}}` slip into output-matches regex (which would
            # crash vally with an invalid-regex error far from the cause)
            # or into az rest URLs (which would 404 in Layer 2 graders).
            Write-Error "Eval '$relativePath' uses {{WORKSPACE_ID}} but no workspace GUID resolved. Pass -WorkspaceId, set FABRIC_WORKSPACE_ID, populate tests/testdata/last_setup.json, or ensure the workspace exists in the Fabric tenant for live discovery."
            exit 1
        }
        $substituted = $substituted.Replace('{{WORKSPACE_ID}}', $workspaceIdForEval)
    }
    if ($Baseline) {
        # Rewrite environment.skills to an empty list so the agent runs with
        # NO Fabric skills loaded. Match the multi-line skills: block (key on its
        # own line, followed by one or more "    - <path>" entries) and replace
        # with "  skills: []" (preserving the standard 2-space indent under env).
        # Uses a multi-line regex; if the eval has no environment.skills block,
        # this is a no-op (some evals may omit it entirely).
        $rx = [regex]::new('(?m)^(\s+)skills:\s*\n(\1\s+-\s+\S+.*\n)+', 'Multiline')
        $substituted = $rx.Replace($substituted, '$1skills: []' + "`n")
    }
    # MCP CI auth injection -- no-op when CI_MCP_OVERLAY is not 'true' or when
    # the staged eval does not declare powerbi-modeling-mcp. See helper above.
    $substituted = Add-CiPowerBiMcpAuthToStagedEval -Content $substituted -RelativePath $relativePath
    [System.IO.File]::WriteAllText($destPath, $substituted, [System.Text.UTF8Encoding]::new($false))

    $stagedFiles += $destPath
}
Write-Host "[OK] Staged $($stagedFiles.Count) file(s) to tests/.vally-staging/" -ForegroundColor Green
if ($Baseline) {
    Write-Host "[BASELINE MODE] environment.skills rewritten to empty list in all staged eval.yaml files." -ForegroundColor Magenta
    Write-Host "[BASELINE MODE] Agent will run WITHOUT Fabric skills. Many graders will legitimately fail; this is informational signal, not a gate." -ForegroundColor Magenta
}

if ($DryRun) {
    Write-Host "`n[DRY RUN] Staging complete. Inspect files at:" -ForegroundColor Yellow
    foreach ($f in $stagedFiles) {
        Write-Host "  $f" -ForegroundColor Gray
    }
    if ($suiteTagPairs.Count -gt 0) {
        Write-Host "[DRY RUN] Suite '$Suite' would apply tag filters:" -ForegroundColor Yellow
        foreach ($pair in $suiteTagPairs) {
            Write-Host "  --tag $pair" -ForegroundColor Gray
        }
    }
    exit 0
}

# --- Step 5: Build vally command ---
$vallyVersion = "@microsoft/vally-cli@0.5.0"
$baseArgs = @("--yes", $vallyVersion, "eval")
$baseArgs += "--output-dir"
# If a caller supplies -ResultsDir (CI does, pointing at runner.temp), write
# vally output there directly. Otherwise default to repo-local
# tests/.vally-results for local runs. Direct-write avoids a post-vally
# Copy-Item that races vally's own cleanup handler on Windows EBUSY exits --
# without this, the timestamped output dir (results.jsonl + per-trial
# trajectory JSONs) gets cleaned up before the workflow's stage step runs,
# and workload teams lose the artefacts they need to debug Layer 2 verifier
# failures from CI.
if ($PSBoundParameters.ContainsKey('ResultsDir') -and -not [string]::IsNullOrWhiteSpace($ResultsDir)) {
    New-Item -ItemType Directory -Path $ResultsDir -Force | Out-Null
    $baseArgs += $ResultsDir
} else {
    $baseArgs += (Join-Path (Join-Path $RepoRoot "tests") ".vally-results")
}

if ($Skill) {
    # Single skill mode: pass --eval-spec directly
    $baseArgs += "--eval-spec"
    $baseArgs += $stagedFiles[0]
} else {
    # All mode: pass each staged eval.yaml as a separate --eval-spec
    foreach ($staged in $stagedFiles) {
        $baseArgs += "--eval-spec"
        $baseArgs += $staged
    }
    if ($suiteTagPairs.Count -gt 0) {
        Write-Host "  Applying suite '$Suite' tag filters:" -ForegroundColor DarkGray
        foreach ($pair in $suiteTagPairs) {
            Write-Host "    --tag $pair" -ForegroundColor DarkGray
            $baseArgs += "--tag"
            $baseArgs += $pair
        }
    }
}

$baseArgs += "--runs"
$baseArgs += $Runs.ToString()

if ($Workers -gt 0) {
    $baseArgs += "--workers"
    $baseArgs += $Workers.ToString()
}

if ($PSBoundParameters.ContainsKey('MaxRetries')) {
    $baseArgs += "--max-retries"
    $baseArgs += $MaxRetries.ToString()
}

if ($Baseline) {
    # Point vally at an empty skill tree so discoverSkills() finds 0 skills.
    # Rewriting environment.skills to [] in the staged eval.yaml is necessary
    # (so vally doesn't re-inject any) but NOT sufficient -- vally's project
    # discovery still reads $RepoRoot/.vally.yaml's paths.skills: skills/ and
    # finds all 26 source skills. --skill-dir overrides the discovery root.
    #
    # CRITICAL: results must land at $RepoRoot/tests/.vally-results/ (the
    # canonical path that the shard step's "Stage the produced results dir"
    # block copies into RUNNER_TEMP for the summarise job). Set the baseline
    # .vally.yaml's paths.results to an ABSOLUTE path back to the canonical
    # results dir; otherwise vally writes to <empty-root>/results/ which the
    # rest of the workflow never sees, and summarise reports 0/0.
    $emptySkillRoot = Join-Path $RepoRoot 'tests/.vally-baseline-skill-root'
    $canonicalResults = Join-Path $RepoRoot 'tests/.vally-results'
    if (Test-Path $emptySkillRoot) {
        Remove-Item -Recurse -Force $emptySkillRoot
    }
    New-Item -ItemType Directory -Path "$emptySkillRoot/skills" -Force | Out-Null
    # Forward-slash form is portable for YAML on Windows + Linux runners.
    $resultsPathYaml = ($canonicalResults -replace '\\', '/')
    $baselineCfg = @"
paths:
  skills: skills/
  evals: evals/
  results: $resultsPathYaml
"@
    [System.IO.File]::WriteAllText(
        (Join-Path $emptySkillRoot '.vally.yaml'),
        $baselineCfg,
        [System.Text.UTF8Encoding]::new($false))
    $baseArgs += "--skill-dir"
    $baseArgs += $emptySkillRoot
    Write-Host "[BASELINE MODE] vally --skill-dir = $emptySkillRoot (0 skills discovered)" -ForegroundColor Magenta
    Write-Host "[BASELINE MODE] vally results.path = $resultsPathYaml (canonical, NOT under skill-dir)" -ForegroundColor Magenta
}

if ($SkillDir) {
    $skillDirPath = Join-Path $RepoRoot $SkillDir
    if (-not (Test-Path $skillDirPath)) {
        Write-Error "SkillDir not found: $skillDirPath"
        exit 1
    }
    $baseArgs += "--skill-dir"
    $baseArgs += $skillDirPath
}

# --- Step 6: Execute ---
Write-Host "`n[RUN] npx $($baseArgs -join ' ')" -ForegroundColor Cyan
Write-Host "      Runs: $Runs | Model: claude-sonnet-4.6 | Timeout: 10m per trial" -ForegroundColor Gray
Write-Host ""

& npx @baseArgs

$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Warning "Vally exited with code $exitCode"
}

Write-Host "`n[DONE] Results at: tests/.vally-results/" -ForegroundColor Green
exit $exitCode
