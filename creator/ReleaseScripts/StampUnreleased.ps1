#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Consume `.changeset/*.md` fragments into the internal CHANGELOG.md
    `## [Unreleased]` section, with optional public-audience routing to
    `public/CHANGELOG.md`.

.DESCRIPTION
    Per-PR changelog fragments live under `.changeset/` (one new file per PR).
    This script reads them all, parses out their `### Added` / `### Changed` /
    `### Removed` / `### Fixed` subsections, prepends each into the matching
    subsection of `## [Unreleased]` in `CHANGELOG.md`, and deletes the
    consumed fragments.

    Run this BEFORE stamping a version (`chore: stamp 0.3.x`). The release
    operator then moves `## [Unreleased]` to `## [0.3.x] - YYYY-MM-DD` and
    creates a fresh `## [Unreleased]` header as usual.

    Files skipped:
      - README.md
      - .gitkeep
      - Anything matching `*.example.md`

    Fragment format (each file under .changeset/):
      # PR #<number> -- <short description>            (optional title)

      audience: public                                  (optional; default: internal)

      ### Added                                         (one or more sections)
      - bullet 1
      - bullet 2

      ### Fixed
      - bullet 3

    Audience routing:
      - `audience: public`   -> bullets go to BOTH internal CHANGELOG.md and
                                public/CHANGELOG.md (which represents the
                                external microsoft/skills-for-fabric release).
      - `audience: internal` -> bullets go only to internal CHANGELOG.md.
      - audience: line absent -> defaults to `internal` (safe default; nothing
                                  leaks to external readers unless deliberately
                                  marked public by the contributor).

    public/CHANGELOG.md does not normally carry a `[Unreleased]` section
    (it is hand-curated per release). The script auto-creates one at the
    top of the file when the first public-audience fragment lands.

    See `.changeset/README.md` for full details and rationale.

.PARAMETER ChangesetDir
    Path to the changeset directory (default: .changeset)

.PARAMETER ChangelogPath
    Path to the internal CHANGELOG.md (default: CHANGELOG.md)

.PARAMETER PublicChangelogPath
    Path to the public CHANGELOG.md (default: public/CHANGELOG.md). Pass an
    empty string to skip public processing entirely (useful for tests).

.PARAMETER DryRun
    Print what would be consumed without modifying anything.

.EXAMPLE
    ./ReleaseScripts/StampUnreleased.ps1                    # consume + delete
    ./ReleaseScripts/StampUnreleased.ps1 -DryRun            # preview only
#>

param(
    [string]$ChangesetDir = ".changeset",
    [string]$ChangelogPath = "CHANGELOG.md",
    [string]$PublicChangelogPath = "public/CHANGELOG.md",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$validKinds = @('Added', 'Changed', 'Removed', 'Fixed')

if (-not (Test-Path $ChangesetDir)) {
    Write-Host "No $ChangesetDir directory; nothing to consume." -ForegroundColor Yellow
    exit 0
}

if (-not (Test-Path $ChangelogPath)) {
    Write-Error "$ChangelogPath not found; cannot stamp."
    exit 1
}

# Discover consumable fragments
$fragments = @(Get-ChildItem -Path $ChangesetDir -Filter '*.md' -File |
    Where-Object { $_.Name -ne 'README.md' -and $_.Name -notlike '*.example.md' })

if (-not $fragments) {
    Write-Host "No consumable fragments under $ChangesetDir; nothing to stamp." -ForegroundColor Yellow
    exit 0
}

Write-Host "Found $($fragments.Count) consumable fragment(s):" -ForegroundColor Cyan
$fragments | ForEach-Object { Write-Host "  $($_.Name)" }
Write-Host ""

# Parse each fragment -- extract bullets per kind AND per audience. A fragment
# may contribute to multiple kinds (e.g. PR adds + removes things). Audience
# determines routing: public bullets go to BOTH internal CHANGELOG.md AND
# public/CHANGELOG.md; internal bullets go only to internal. Default: internal.
$byKindInternal = @{}
$byKindPublic   = @{}
foreach ($k in $validKinds) {
    $byKindInternal[$k] = @()
    $byKindPublic[$k]   = @()
}

$kindsAlt = ($validKinds -join '|')

# Track audience distribution for the summary print
$publicFragmentCount = 0
$internalFragmentCount = 0

foreach ($f in $fragments) {
    # Force UTF-8 on the read to avoid silent mojibake under Windows PowerShell 5.1
    # (whose default is the system code page, e.g. cp1252 on US Windows). This
    # script writes UTF-8-no-BOM later, so the read must match.
    $raw = Get-Content $f.FullName -Raw -Encoding utf8
    $foundAny = $false

    # Parse the audience marker (case-insensitive, anywhere before the first
    # ### Kind heading). Accepted values: 'public' or 'internal'. Default: internal.
    # The regex matches the audience value at the start of a line and is forgiving
    # of trailing content on the same line (e.g. an HTML comment), since contributor
    # docs show `audience: public   <!-- optional ... -->`. We use `\b` after the
    # value so any non-word character (whitespace, comment, EOL) terminates the
    # capture, but we don't require the rest of the line to be empty.
    # Unknown values warn + fall back to internal (safe default; public exposure
    # requires explicit, valid marker).
    $audience = 'internal'  # safe default
    $audienceMatch = [regex]::Match($raw, '(?im)^audience:\s*([A-Za-z]+)\b')
    if ($audienceMatch.Success) {
        $rawValue = $audienceMatch.Groups[1].Value.Trim().ToLowerInvariant()
        if ($rawValue -in @('public', 'internal')) {
            $audience = $rawValue
        } else {
            Write-Warning "$($f.Name): audience: '$rawValue' is not a recognised value. Use 'public' or 'internal'. Defaulting to internal."
        }
    }
    if ($audience -eq 'public') { $publicFragmentCount++ } else { $internalFragmentCount++ }

    # For each `### Kind` heading, capture content until the next `### ` heading
    # (of any kind, not just Added|Changed|Removed|Fixed) or EOF. Non-Kind
    # subheadings get a warning -- they would otherwise be silently swallowed
    # into the previous Kind section.
    # (?ms) = multiline + dotall so . matches newlines.
    $matches = [regex]::Matches($raw, "(?ms)^###\s+($kindsAlt)\s*\r?\n(.+?)(?=^###\s|\z)")
    foreach ($m in $matches) {
        $kind = $m.Groups[1].Value.Trim()
        $body = $m.Groups[2].Value.Trim()
        if ($body) {
            $entry = @{ Name = $f.Name; Body = $body; Path = $f.FullName; Audience = $audience }
            # Internal CHANGELOG gets ALL bullets (regardless of audience).
            $byKindInternal[$kind] += $entry
            # Public CHANGELOG gets ONLY public-audience bullets.
            if ($audience -eq 'public') {
                $byKindPublic[$kind] += $entry
            }
            $foundAny = $true
        }
    }

    # Warn (don't fail) if the fragment has '### ...' headings that are not
    # exactly Added|Changed|Removed|Fixed. We must capture the FULL heading
    # text (not just the first token) -- otherwise a heading like
    # '### Added (Step 2)' would have $name = 'Added', match the allowed list,
    # and emit no warning, while the strict extraction regex above would still
    # silently drop the section.
    $allH3 = [regex]::Matches($raw, "(?m)^###\s+(.+?)\s*$")
    foreach ($h3 in $allH3) {
        $heading = $h3.Groups[1].Value
        if ($heading -notmatch "^(Added|Changed|Removed|Fixed)$") {
            Write-Warning "$($f.Name): heading '### $heading' is not a recognised kind and will be ignored. Use ### Added | Changed | Removed | Fixed (exact match, no trailing text)."
        }
    }

    if (-not $foundAny) {
        Write-Error "$($f.Name): no '### Added|Changed|Removed|Fixed' sections found. Add at least one subsection."
        exit 1
    }
}

# Alias for the existing per-kind merge logic below (operates on the internal map).
$byKind = $byKindInternal

# -----------------------------------------------------------------------------
# Helper: merge a per-kind bullet map into a target CHANGELOG.md
# -----------------------------------------------------------------------------
# Returns the rebuilt changelog text. If the target file has no '## [Unreleased]'
# section and $createUnreleasedIfMissing is true, one is inserted at the top
# (after any leading title + intro paragraph -- before the first '## [<version>]'
# heading). This is the path public/CHANGELOG.md takes since public is
# hand-curated and typically has no [Unreleased] between releases.
function Merge-FragmentsIntoChangelog {
    param(
        [string]$ChangelogText,
        [hashtable]$BulletsByKind,
        [string]$ChangelogLabel,                        # for error messages
        [bool]$CreateUnreleasedIfMissing = $false
    )

    # Locate ## [Unreleased] section
    $unreleasedMatch = [regex]::Match($ChangelogText, '(?ms)^## \[Unreleased\]\s*\r?\n(.*?)(?=^## \[|\z)')
    if (-not $unreleasedMatch.Success) {
        if (-not $CreateUnreleasedIfMissing) {
            throw "Could not find '## [Unreleased]' section in $ChangelogLabel."
        }
        # Insert a fresh [Unreleased] block just before the first '## [<version>]' heading.
        $firstVersionMatch = [regex]::Match($ChangelogText, '(?m)^## \[')
        if (-not $firstVersionMatch.Success) {
            # No version sections at all -- append to end.
            $ChangelogText = $ChangelogText.TrimEnd() + "`n`n## [Unreleased]`n"
        } else {
            $idx = $firstVersionMatch.Index
            $ChangelogText = $ChangelogText.Substring(0, $idx) + "## [Unreleased]`n`n" + $ChangelogText.Substring($idx)
        }
        # Re-locate now that we've inserted it.
        $unreleasedMatch = [regex]::Match($ChangelogText, '(?ms)^## \[Unreleased\]\s*\r?\n(.*?)(?=^## \[|\z)')
        if (-not $unreleasedMatch.Success) {
            throw "Failed to insert [Unreleased] section into $ChangelogLabel."
        }
    }

    $unreleasedHeader = '## [Unreleased]'
    $unreleasedBody = $unreleasedMatch.Groups[1].Value
    $beforeUnreleased = $ChangelogText.Substring(0, $unreleasedMatch.Index)
    $afterUnreleased = $ChangelogText.Substring($unreleasedMatch.Index + $unreleasedMatch.Length)

    # Merge: for each kind that has new entries, ensure the subsection exists in
    # unreleasedBody, then prepend the new entries at the top of that subsection.
    foreach ($kind in $validKinds) {
        if ($BulletsByKind[$kind].Count -eq 0) { continue }

        $newBullets = ($BulletsByKind[$kind] | ForEach-Object { $_.Body }) -join "`n"

        $sectionPattern = "(?ms)^### $kind\s*\r?\n"
        if ($unreleasedBody -match $sectionPattern) {
            # Section exists -- prepend new bullets right after the header.
            # Use Regex.Replace with a MatchEvaluator (not the static string overload):
            #   1) Avoids `$&` / `$N` backreferences in $newBullets being interpreted
            #      as backref placeholders -- bullets mentioning `$variable`, `${env:X}`,
            #      regex `$1`-`$9`, or PowerShell `$&` would otherwise be silently mangled.
            #   2) The instance method's 3-arg overload (input, evaluator, count) supports
            #      a real replacement count -- the static 4-arg overload's last arg is
            #      RegexOptions, not a count.
            $rx = New-Object System.Text.RegularExpressions.Regex($sectionPattern)
            $unreleasedBody = $rx.Replace(
                $unreleasedBody,
                [System.Text.RegularExpressions.MatchEvaluator] { param($m) "### $kind`n$newBullets`n" },
                1
            )
        } else {
            # Section missing -- add at the end of unreleasedBody
            $unreleasedBody = $unreleasedBody.TrimEnd() + "`n`n### $kind`n$newBullets`n"
        }
    }

    return $beforeUnreleased + $unreleasedHeader + "`n" + $unreleasedBody.TrimEnd() + "`n`n" + $afterUnreleased.TrimStart()
}

# -----------------------------------------------------------------------------
# Internal CHANGELOG.md: always update (gets ALL bullets, public + internal)
# -----------------------------------------------------------------------------
$changelog = Get-Content $ChangelogPath -Raw -Encoding utf8
$newChangelog = Merge-FragmentsIntoChangelog `
    -ChangelogText $changelog `
    -BulletsByKind $byKindInternal `
    -ChangelogLabel $ChangelogPath `
    -CreateUnreleasedIfMissing $false

# -----------------------------------------------------------------------------
# Public CHANGELOG.md: update only if (a) path is non-empty AND (b) at least
# one fragment opted in via audience: public. Auto-create the [Unreleased]
# section if missing (public is hand-curated and normally has no [Unreleased]
# between releases).
# -----------------------------------------------------------------------------
$newPublicChangelog = $null
$publicBulletTotal = ($validKinds | ForEach-Object { $byKindPublic[$_].Count } | Measure-Object -Sum).Sum
if ($PublicChangelogPath -and $publicBulletTotal -gt 0) {
    if (-not (Test-Path $PublicChangelogPath)) {
        Write-Error "$PublicChangelogPath not found but public-audience fragments exist; cannot route."
        exit 1
    }
    $publicChangelog = Get-Content $PublicChangelogPath -Raw -Encoding utf8
    $newPublicChangelog = Merge-FragmentsIntoChangelog `
        -ChangelogText $publicChangelog `
        -BulletsByKind $byKindPublic `
        -ChangelogLabel $PublicChangelogPath `
        -CreateUnreleasedIfMissing $true
}

if ($DryRun) {
    Write-Host "[DRY RUN] Would write:" -ForegroundColor Yellow
    Write-Host "  - $($fragments.Count) fragment(s) consumed ($publicFragmentCount public, $internalFragmentCount internal)"
    Write-Host "  - Internal CHANGELOG.md ($ChangelogPath):"
    foreach ($kind in $validKinds) {
        if ($byKindInternal[$kind].Count -gt 0) {
            Write-Host "      ### $kind : $($byKindInternal[$kind].Count) new contribution(s)"
        }
    }
    if ($newPublicChangelog) {
        Write-Host "  - Public CHANGELOG.md ($PublicChangelogPath):"
        foreach ($kind in $validKinds) {
            if ($byKindPublic[$kind].Count -gt 0) {
                Write-Host "      ### $kind : $($byKindPublic[$kind].Count) new public-audience contribution(s)"
            }
        }
    } else {
        Write-Host "  - Public CHANGELOG.md: not updated (no public-audience fragments)"
    }
    Write-Host "[DRY RUN] Would delete:" -ForegroundColor Yellow
    $fragments | ForEach-Object { Write-Host "  $($_.FullName)" }
    Write-Host ""
    Write-Host "Re-run without -DryRun to apply." -ForegroundColor Yellow
    exit 0
}

# Write the internal CHANGELOG.md (UTF-8 no BOM for cross-platform safety)
[System.IO.File]::WriteAllText((Resolve-Path $ChangelogPath), $newChangelog, [System.Text.UTF8Encoding]::new($false))
Write-Host "Updated $ChangelogPath ($publicFragmentCount public + $internalFragmentCount internal fragment(s))" -ForegroundColor Green

# Write the public CHANGELOG.md if any public-audience bullets were collected.
if ($newPublicChangelog) {
    [System.IO.File]::WriteAllText((Resolve-Path $PublicChangelogPath), $newPublicChangelog, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Updated $PublicChangelogPath ($publicFragmentCount public-audience fragment(s) routed)" -ForegroundColor Green
}

# Delete consumed fragments
foreach ($f in $fragments) {
    Remove-Item $f.FullName -Force
    Write-Host "Deleted $($f.Name)" -ForegroundColor DarkGray
}
Write-Host ""
$filesToCommit = "$ChangelogPath $ChangesetDir/"
if ($newPublicChangelog) { $filesToCommit = "$ChangelogPath $PublicChangelogPath $ChangesetDir/" }
Write-Host "Done. Review the updated changelogs, then commit:" -ForegroundColor Green
Write-Host "  git add $filesToCommit"
Write-Host "  git commit -m `"chore(changelog): consume $($fragments.Count) changeset(s)`""
