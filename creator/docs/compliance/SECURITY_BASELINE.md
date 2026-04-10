# Security Baseline for skills-for-fabric Supply Chain

## Overview

This document defines supply chain security practices for the skills-for-fabric repository, following OpenSSF best practices and Microsoft Security Development Lifecycle (SDL).

## Dependency Management

### Python Dependencies

**Requirements Files**
- `requirements.txt`: Production dependencies (pinned versions)
- `requirements-dev.txt`: Development/testing dependencies
- Use `pip freeze` to generate pinned versions

**Best Practices**
```bash
# Pin exact versions in production
requests==2.31.0

# Allow patch updates for dev dependencies
pytest>=7.4.0,<8.0.0

# Document why each dependency is needed
# requests - HTTP client for API calls
```

**Dependency Updates**
- Dependabot automatically opens PRs for updates
- Review changelogs before merging
- Run full test suite after updates
- Check for breaking changes

### GitHub Actions

**Pinning Strategy**
```yaml
# ✅ GOOD: Pin to commit SHA
- uses: actions/checkout@692973e3d937129bcbf40652eb9f2f61becf3332 # v4.1.7

# ❌ BAD: Mutable tag reference
- uses: actions/checkout@v4
```

**Why Pin to SHA?**
- Tags can be moved (mutable)
- Commits are immutable
- Prevents supply chain attacks via compromised actions

**Updating Pinned Actions**
1. Check action repository for new releases
2. Verify release notes and changes
3. Update SHA and version comment
4. Test in PR before merging

## Vulnerability Scanning

### Automated Scans

**1. Dependency Review (PRs)**
- Blocks PRs introducing vulnerable dependencies
- Checks against GitHub Advisory Database
- Severity threshold: Moderate and above

**2. CodeQL (SAST)**
- Runs on every PR and push to main
- Languages: Python, JavaScript/TypeScript
- Queries: security-extended, security-and-quality

**3. Secret Scanning**
- TruffleHog: Verified secrets only
- Gitleaks: Comprehensive pattern matching
- Runs on PR and schedule (weekly)

**4. OpenSSF Scorecard**
- Evaluates repository security posture
- Checks: Branch protection, code review, pinned dependencies, etc.
- Runs weekly and on branch protection changes

### Manual Reviews

**Quarterly Security Audit**
- Review all dependencies for known CVEs
- Check for unmaintained packages
- Evaluate license compliance
- Update security documentation

## License Compliance

### Allowed Licenses

**Permissive (Preferred)**
- MIT
- Apache 2.0
- BSD (2-clause, 3-clause)
- ISC

**Copyleft (Blocked by CI)**
- GPL-2.0, GPL-3.0 (viral, OSS incompatible)
- AGPL-3.0 (network copyleft)
- SSPL (not OSI-approved)

**Review Required**
- LGPL (weak copyleft, case-by-case)
- MPL 2.0 (file-level copyleft)
- EPL (Eclipse Public License)

### License Checking

Dependency Review action automatically blocks:
```yaml
deny-licenses: GPL-2.0, GPL-3.0, AGPL-3.0
```

## Access Controls

### Repository Access

**Roles**
- **Admin**: Maintainers only (Bogdan Crivat, Santhosh Ravindran)
- **Write**: None (all contributions via PR)
- **Read**: Public (open source)

**Branch Protection**
- `main` and `bocrivat_main` branches protected
- Require PR before merge
- Require code owner approval
- Require status checks to pass
- No force pushes or deletions

### Secrets Management

**GitHub Secrets**
- Stored in repository/environment secrets
- Never commit to code
- Rotate regularly (quarterly minimum)
- Use least-privilege scoping

**Environment Variables**
- No secrets in environment variables in workflows
- Use GitHub Secrets or OIDC for authentication
- Prefer short-lived tokens over long-lived PATs

## Action Security

### Permissions Model

**Default Permissions: Read-Only**
```yaml
permissions:
  contents: read  # Default for all workflows
```

**Explicit Permissions**
```yaml
permissions:
  contents: read          # Read repository code
  security-events: write  # Upload SARIF for CodeQL
  pull-requests: write    # Comment on PRs
```

**Avoid**
- `permissions: write-all` (overly permissive)
- Permissions beyond what job needs

### Workflow Triggers

**Safe Triggers**
- `pull_request` (safe for forks, no write access)
- `push` (trusted code only)
- `schedule` (trusted environment)
- `workflow_dispatch` (manual trigger)

**Dangerous Triggers (Avoid)**
- `pull_request_target` (has write access, can leak secrets)
  - Only use with explicit security review
  - Never checkout untrusted code
  - Never run untrusted code

### Fork Security

**Preventing Secret Leakage**
```yaml
# ✅ GOOD: No secrets on pull_request from forks
on: pull_request

# ❌ BAD: Exposes secrets to fork PRs
on: pull_request_target
```

**Safe Forked PR Workflow**
1. Automated checks run without secrets
2. Maintainer reviews code
3. Maintainer triggers workflow with secrets (if needed)

## Provenance & Attestation

### Software Bill of Materials (SBOM)

**Generation** (Future Enhancement)
```bash
# Generate SBOM for releases
pip install pip-licenses
pip-licenses --format=json --output-file=sbom.json
```

**SPDX Format**
- Standard format for SBOMs
- Machine-readable
- Includes license info

### Signed Releases

**Future Enhancement: Sigstore**
```bash
# Sign release artifacts with Sigstore
cosign sign-blob --bundle=release.bundle release.tar.gz
```

**Benefits**
- Verifiable provenance
- Non-repudiation
- Supply chain transparency

## Incident Response

### Supply Chain Compromise

**Indicators**
- Unexpected dependency updates
- New dependencies not in PR
- Failed security scans
- Suspicious workflow runs

**Response**
1. **Contain**: Revert commit, disable workflow
2. **Investigate**: Review git history, check for backdoors
3. **Notify**: Inform users via security advisory
4. **Remediate**: Remove malicious code, rotate secrets
5. **Post-mortem**: Document lessons learned

### Compromised Action

**If Third-Party Action Compromised**
1. Unpin action (update to safe SHA)
2. Check for malicious behavior in past runs
3. Rotate any secrets that may have been exposed
4. Consider forking action for better control

## Security Checklist for Contributors

Before submitting a PR:

- [ ] No secrets committed
- [ ] New dependencies reviewed and justified
- [ ] Actions pinned to commit SHA
- [ ] Least-privilege permissions for workflows
- [ ] No `pull_request_target` unless absolutely necessary
- [ ] License compatibility checked
- [ ] Security scans pass locally

## Tools & Resources

### Scanning Tools

**Local Development**
```bash
# Check for secrets
pip install trufflehog
trufflehog filesystem . --json

# Check Python dependencies
pip install safety
safety check

# Lint workflows
# (Use actionlint or GitHub's workflow validator)
```

### Resources

- [OpenSSF Best Practices](https://bestpractices.coreinfrastructure.org/)
- [GitHub Security Hardening](https://docs.github.com/en/actions/security-guides)
- [SLSA Framework](https://slsa.dev/)
- [Sigstore](https://www.sigstore.dev/)
- [SPDX](https://spdx.dev/)

## Compliance Matrix

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Dependencies pinned | ✅ | requirements.txt uses exact versions |
| Actions pinned to SHA | ✅ | All workflows pin to commit SHA |
| Dependabot enabled | ✅ | .github/dependabot.yml |
| Vulnerability scanning | ✅ | CodeQL, Dependency Review |
| Secret scanning | ✅ | TruffleHog, Gitleaks |
| License compliance | ✅ | Dependency Review blocks GPL |
| Branch protection | ✅ | main/bocrivat_main protected |
| Code review required | ✅ | CODEOWNERS enforced |
| Least-privilege workflows | ✅ | Explicit permissions in all workflows |
| No secrets in forks | ✅ | No pull_request_target |
| SBOM generation | 🟡 | Roadmap item |
| Signed releases | 🟡 | Roadmap item |

**Legend**: ✅ Implemented | 🟡 Planned | ❌ Not Planned

---

**Document Version**: 1.0  
**Last Updated**: 2026-02-11  
**Owners**: Bogdan Crivat, Santhosh Ravindran
