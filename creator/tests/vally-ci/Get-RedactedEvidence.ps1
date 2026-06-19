# Shared producer-side evidence redactor for the Vally CI surface.
#
# Strips three pattern classes that are the highest-risk leak vectors for the
# internal-repo dashboard surface AND for any shard-artifact text file
# (transcripts, schema rows, etc.):
#   - GUIDs (workspace IDs, tenant IDs in canonical 8-4-4-4-12 form)
#   - Bearer tokens (anything after 'bearer ')
#   - tenant=... query-string values
#
# Each match is replaced with [REDACTED]. The final string is capped at 500
# chars total: the first 499 characters are kept and a single horizontal
# ellipsis is appended (so the rendered string is exactly 500 chars). Longer
# inputs lose their tail, not their head -- consistent with the
# Export-VallySchemaArtifact dashboard contract.
#
# Dot-source this file from any other vally-ci script that needs the
# function. Keep it global-scope (no `function script:` prefix) so dot-source
# consumers can call it as `Get-RedactedEvidence ...`. Unit tests live in
# Get-RedactedEvidence.tests.ps1 next to this file.

function Get-RedactedEvidence {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0)]
        [AllowEmptyString()]
        [AllowNull()]
        [string]$Text
    )
    if ([string]::IsNullOrEmpty($Text)) { return '' }
    $t = $Text
    # GUIDs (8-4-4-4-12, case-insensitive).
    $t = [regex]::Replace($t, '[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', '[REDACTED]', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    # Bearer tokens (covers 'Bearer <token>' and 'bearer <token>').
    $t = [regex]::Replace($t, 'bearer\s+\S+', '[REDACTED]', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    # tenant= query values (stop at & or whitespace).
    $t = [regex]::Replace($t, 'tenant=[^&\s]+', 'tenant=[REDACTED]', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    if ($t.Length -gt 500) {
        $t = $t.Substring(0, 499) + "`u{2026}"
    }
    return $t
}
