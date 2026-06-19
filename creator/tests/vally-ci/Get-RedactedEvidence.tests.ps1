Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

BeforeAll {
    $script:ModulePath = Join-Path $PSScriptRoot 'Get-RedactedEvidence.ps1'
    . $script:ModulePath
}

Describe 'Get-RedactedEvidence' {
    Context 'empty / null inputs' {
        It 'returns empty string for $null' {
            (Get-Redactedevidence -Text $null) | Should -BeExactly ''
        }
        It 'returns empty string for empty input' {
            (Get-RedactedEvidence -Text '') | Should -BeExactly ''
        }
        It 'returns whitespace input verbatim (only-whitespace is not a leak vector)' {
            (Get-RedactedEvidence -Text '   ') | Should -BeExactly '   '
        }
    }

    Context 'GUID redaction' {
        It 'redacts a canonical lowercase GUID' {
            $r = Get-RedactedEvidence -Text 'workspaceId=2c4f7b6e-1a3d-4e5f-9c8a-7b6e5d4f3c2a in result'
            $r | Should -Match '\[REDACTED\]'
            $r | Should -Not -Match '2c4f7b6e-1a3d-4e5f-9c8a-7b6e5d4f3c2a'
        }
        It 'redacts an uppercase GUID (case-insensitive)' {
            $r = Get-RedactedEvidence -Text 'tenant: 2C4F7B6E-1A3D-4E5F-9C8A-7B6E5D4F3C2A'
            $r | Should -Match '\[REDACTED\]'
        }
        It 'redacts multiple GUIDs in the same string' {
            $r = Get-RedactedEvidence -Text 'a=11111111-2222-3333-4444-555555555555 b=66666666-7777-8888-9999-aaaaaaaaaaaa'
            ([regex]::Matches($r, '\[REDACTED\]')).Count | Should -BeExactly 2
        }
        It 'leaves non-GUID hex strings alone (length matters)' {
            (Get-RedactedEvidence -Text 'sha=2c4f7b6e1a3d4e5f9c8a7b6e5d4f3c2a') | Should -Match '2c4f7b6e1a3d4e5f9c8a7b6e5d4f3c2a'
        }
    }

    Context 'bearer token redaction' {
        It 'redacts a Bearer header' {
            $r = Get-RedactedEvidence -Text 'Authorization: Bearer eyJhbGciOiJSUzI1NiIs.token.signature'
            $r | Should -Not -Match 'eyJhbGciOiJSUzI1NiIs'
            $r | Should -Match '\[REDACTED\]'
        }
        It 'redacts lowercase bearer too (case-insensitive)' {
            $r = Get-RedactedEvidence -Text 'bearer secret_value_here'
            $r | Should -Match '\[REDACTED\]'
        }
    }

    Context 'tenant= query value' {
        It 'redacts a tenant= query parameter' {
            $r = Get-RedactedEvidence -Text 'https://login.microsoftonline.com/?tenant=my.onmicrosoft.com&foo=bar'
            $r | Should -Match 'tenant=\[REDACTED\]'
            $r | Should -Match 'foo=bar'
        }
        It 'redacts tenant= when followed by whitespace instead of &' {
            $r = Get-RedactedEvidence -Text 'tenant=contoso.com is the right tenant'
            $r | Should -Match 'tenant=\[REDACTED\]'
            $r | Should -Match 'is the right tenant'
        }
    }

    Context 'length cap' {
        It 'truncates strings longer than 500 chars with a horizontal ellipsis' {
            $long = ('A' * 600)
            $r = Get-RedactedEvidence -Text $long
            $r.Length | Should -BeExactly 500
            $r[-1] | Should -BeExactly ([char]0x2026)
        }
        It 'leaves strings <= 500 chars unchanged in length' {
            $exact = ('B' * 500)
            (Get-RedactedEvidence -Text $exact).Length | Should -BeExactly 500
            (Get-RedactedEvidence -Text 'short').Length | Should -BeLessThan 500
        }
    }

    Context 'safety: backslashes and quotes pass through' {
        It 'does not mutate cert paths beyond the GUID/bearer/tenant matchers' {
            $p = 'C:\Users\runneradmin\AppData\Local\Temp\sp-cert.pem'
            (Get-RedactedEvidence -Text $p) | Should -BeExactly $p
        }
    }
}
