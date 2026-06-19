# Security Policy

## Reporting Security Vulnerabilities

**DO NOT** open public GitHub issues for security vulnerabilities.

Instead, please report security vulnerabilities responsibly:

### For Microsoft Employees

- Email: **Bogdan.Crivat@microsoft.com**, **Santhosh.Ravindran@microsoft.com**, **jewang@microsoft.com**, and **cristp@microsoft.com**
- Internal Teams channel: skills-for-fabric Security
- Incident Response: Follow Microsoft MSRC procedures

### For External Researchers

- Microsoft Security Response Center (MSRC): https://msrc.microsoft.com/create-report
- Email: secure@microsoft.com
- Include "skills-for-fabric" in the subject line

### What to Include

When reporting a security vulnerability, please include:

1. **Description**: Clear description of the vulnerability
2. **Impact**: Potential impact and attack scenarios
3. **Reproduction**: Step-by-step instructions to reproduce
4. **Proof of Concept**: Code or prompts demonstrating the issue
5. **Suggested Fix**: If you have recommendations
6. **Disclosure Timeline**: Your expected disclosure timeline

## Security Best Practices

### For Contributors

When contributing to skills-for-fabric, follow these security practices:

#### No Secrets in Code
- Never commit API keys, tokens, credentials, or secrets
- Use GitHub Secrets or Environment Variables for CI/CD
- Review `git diff` before committing
- Use secret scanning tools locally

#### Prompt Injection Prevention
- Review [docs/compliance/RAI_THREAT_MODEL.md](docs/compliance/RAI_THREAT_MODEL.md)
- Use clear delimiters between instructions and user content
- Validate all inputs before processing
- Never echo or reveal system prompts
- Test against injection attempts (see tests/redteam/)

#### Tool Safety
- Validate all tool parameters
- Use allowlists, not denylists
- Require user confirmation for high-risk actions
- Implement least privilege access
- No arbitrary code execution

#### Dependency Security
- Keep dependencies updated (Dependabot helps)
- Review dependency changes in PRs
- Check for known vulnerabilities
- Use dependency review action

#### Input/Output Handling
- Sanitize all external inputs
- Validate data types and ranges
- Redact sensitive data in outputs
- Never expose internal implementation details

## Threat Model

skills-for-fabric is subject to unique AI/LLM security threats. See our comprehensive threat model:

📖 **[RAI Threat Model](docs/compliance/RAI_THREAT_MODEL.md)**

Key threat categories:
- **Prompt Injection**: Malicious instructions in user inputs
- **Sensitive Info Disclosure**: Leaking secrets, prompts, or PII
- **Excessive Agency**: Unauthorized actions or tool abuse
- **Supply Chain**: Compromised dependencies or malicious contributions
- **Data Exfiltration**: Unauthorized data access or transmission

## Security Features

### Automated Security Scanning

All pull requests undergo:

✅ **Secret Scanning**: TruffleHog + Gitleaks detect credentials
✅ **Prompt Security Scan**: Custom scanner for injection patterns

**Optional Advanced Checks** (available but disabled by default):
- CodeQL SAST analysis
- Dependency review and vulnerability blocking
- Automated dependency updates (Dependabot)
- Python/Markdown/YAML linting
- CI test automation
- OpenSSF Scorecard for supply chain security

These can be re-enabled by renaming `.disabled` files in `.github/workflows/`.

### Branch Protection

- Only maintainers can merge to `main`
- Require code owner approval
- All status checks must pass
- Conversation resolution required
- No force pushes or deletions

### Access Controls

- **Maintainers**: Bogdan Crivat, Santhosh Ravindran, Jeffrey Wang, Cristian Petculescu
- **Contributors**: Read-only, submit PRs
- **CODEOWNERS**: Enforced approval requirements

## Secure Development Lifecycle

### Design Phase
- Review threat model
- Identify security requirements
- Plan mitigations

### Development Phase
- Follow secure coding practices
- Use security linters (bandit, CodeQL)
- Write security tests

### Review Phase
- Code owner security review
- Automated security scans
- Red-team testing for skills

### Release Phase
- Security sign-off required
- Document security posture
- Publish security advisories if needed

## Known Security Limitations

As an open-source AI skills repository:

1. **Prompt Engineering is Probabilistic**: No guarantee of 100% injection resistance
2. **User Responsibility**: Users must configure appropriate access controls
3. **Tool Execution Environment**: Security depends on deployment environment
4. **Third-party Dependencies**: Inherited risks from dependencies

## Security Updates

- Security patches are prioritized
- Critical fixes may bypass normal review cycle (break-glass procedure)
- Security advisories published via GitHub Security Advisories
- Subscribe to repository notifications for security updates

## Compliance

This project follows:

- Microsoft Security Development Lifecycle (SDL)
- OpenSSF Best Practices
- OWASP AI Security & Privacy Guide
- Microsoft Responsible AI Standard

## Break-Glass Procedure

In security emergencies, maintainers may:

1. **Bypass branch protection** (with documentation)
2. **Merge without full CI** (if CI itself is compromised)
3. **Force revert commits** (for immediate threat mitigation)
4. **Temporarily disable workflows** (if workflow is exploited)

All break-glass actions must be:
- Documented in incident report
- Reviewed post-incident
- Addressed with long-term fixes

## Security Champions

- **Bogdan Crivat** (@Bogdan.Crivat@microsoft.com)
- **Santhosh Ravindran** (@Santhosh.Ravindran@microsoft.com)
- **Jeffrey Wang** (@jewang@microsoft.com)
- **Cristian Petculescu** (@cristp@microsoft.com)

## Additional Resources

- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
- [docs/compliance/RAI_THREAT_MODEL.md](docs/compliance/RAI_THREAT_MODEL.md) - AI security threats
- [docs/compliance/SECURITY_BASELINE.md](docs/compliance/SECURITY_BASELINE.md) - Supply chain security
- [docs/compliance/REPO_GUARDRAILS.md](docs/compliance/REPO_GUARDRAILS.md) - Repository protections

---

**Thank you for helping keep skills-for-fabric secure!** 🔒
