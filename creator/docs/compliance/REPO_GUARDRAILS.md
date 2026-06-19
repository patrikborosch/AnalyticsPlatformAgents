# Repository Guardrails Configuration Guide

## Overview

This document provides step-by-step instructions for configuring GitHub repository settings that enforce security and quality standards. These settings complement the code-based protections (CI workflows, CODEOWNERS) already in place.

## Prerequisites

- Repository admin access
- GitHub organization settings (if applicable)
- Four maintainer accounts ready:
  - Bogdan.Crivat@microsoft.com
  - Santhosh.Ravindran@microsoft.com
  - Jeffrey.Wang@microsoft.com
  - Cristian.Popa@microsoft.com

---

## Part 1: Access Control

### Step 1.1: Configure Repository Roles

**Path**: Repository → Settings → Collaborators and teams

1. **Remove all existing collaborators** except maintainers
2. **Add maintainers** with `Admin` role:
   - Add: `Bogdan.Crivat@microsoft.com` → Role: `Admin`
   - Add: `Santhosh.Ravindran@microsoft.com` → Role: `Admin`
   - Add: `Jeffrey.Wang@microsoft.com` → Role: `Admin`
   - Add: `Cristian.Popa@microsoft.com` → Role: `Admin`
3. **Set base permissions** (if in organization):
   - Base permission: `Read` (public repo) or `None` (private repo)

**Verification**:
- ✅ Only 4 users have Admin access
- ✅ All other contributors must use forks + PRs

---

### Step 1.2: Create Maintainers Team (Optional, if in org)

**Path**: Organization → Teams → New team

1. **Create team**: `fabricskills-maintainers`
2. **Add members**:
   - Bogdan.Crivat@microsoft.com
   - Santhosh.Ravindran@microsoft.com
   - Jeffrey.Wang@microsoft.com
   - Cristian.Petculescu@microsoft.com
3. **Add team to repository**:
   - Repository → Settings → Collaborators and teams
   - Add team: `fabricskills-maintainers` → Role: `Admin`

**Benefit**: Easier to manage permissions across multiple repos

---

## Part 2: Branch Protection

### Step 2.1: Protect Main Branch

**Path**: Repository → Settings → Branches → Add branch protection rule

**Branch name pattern**: `main`

#### 2.1.1: Require Pull Request

- ☑️ **Require a pull request before merging**
  - ☑️ **Require approvals**: `1`
  - ☑️ **Dismiss stale pull request approvals when new commits are pushed**
  - ☑️ **Require review from Code Owners**
  - ☐ **Restrict who can dismiss pull request reviews** (leave unchecked for flexibility)
  - ☑️ **Allow specified actors to bypass required pull requests** → Add maintainers (for break-glass)
  - ☑️ **Require approval of the most recent reviewable push**

#### 2.1.2: Require Status Checks

- ☑️ **Require status checks to pass before merging**
  - ☑️ **Require branches to be up to date before merging**
  - **Add required status checks** (check these as they appear after first workflow run):
    - `Secret Scan / TruffleHog Scan`
    - `Secret Scan / Gitleaks Scan`
    - `RAI Prompt Security / Scan for Prompt Injection Patterns`

**Note**: Status checks won't appear in the list until they've run at least once. After merging the security guardrails PR, come back and add them.

**Disabled Workflows** (preserved as `.disabled` files for future use):
- CI tests (ci.yml.disabled)
- CodeQL SAST (security-codeql.yml.disabled)
- Dependency review (dependency-review.yml.disabled)
- Linting (lint.yml.disabled)

**Active dependency updates**: Dependabot (`.github/dependabot.yml`) -- `github-actions` ecosystem only, grouped by maintainer org, weekly Monday 06:00 UTC. See PR #328.

#### 2.1.3: Other Settings

- ☑️ **Require conversation resolution before merging**
- ☑️ **Require signed commits** (optional, recommended for high-security environments)
- ☑️ **Require linear history** (prevents merge commits, enforces squash/rebase)
- ☑️ **Require deployments to succeed before merging** (if using environments)

#### 2.1.4: Restrictions

- ☑️ **Lock branch** (optional, for stable releases)
- ☑️ **Do not allow bypassing the above settings** (uncheck this to allow break-glass)
- ☑️ **Restrict who can push to matching branches** → Add: maintainers only
- ☑️ **Allow force pushes**: **Specify who can force push** → Add: maintainers only (for emergency rollback)
- ☑️ **Allow deletions**: ☐ Uncheck (prevent accidental deletion)

**Save changes**

---

### Step 2.2: Protect Bocrivat_main Branch

Repeat **Step 2.1** for branch pattern: `bocrivat_main`

---

## Part 3: Security Features

### Step 3.1: Enable Code Scanning (CodeQL)

**Path**: Repository → Settings → Code security and analysis

1. **Code scanning**:
   - Click **Set up** → **Advanced**
   - GitHub will create `.github/workflows/codeql.yml` (already done in this PR)
   - Or use existing `security-codeql.yml` workflow

**Verification**: After PR merge, go to Security → Code scanning alerts

---

### Step 3.2: Enable Secret Scanning

**Path**: Repository → Settings → Code security and analysis

1. **Secret scanning**:
   - ☑️ **Enable** (GitHub detects secrets)
   - ☑️ **Push protection** (blocks commits with secrets)

**Note**: Available for public repos and GitHub Advanced Security

**Verification**: Test by trying to commit a fake API key locally

---

### Step 3.3: Enable Dependabot

**Path**: Repository → Settings → Code security and analysis

1. **Dependabot alerts**:
   - ☑️ **Enable** (vulnerability alerts)
2. **Dependabot security updates**:
   - ☑️ **Enable** (auto-PRs for security patches)
3. **Dependabot version updates**:
   - Already configured in `.github/dependabot.yml` (this PR)

**Verification**: Check Security → Dependabot alerts

---

### Step 3.4: Enable Dependency Graph

**Path**: Repository → Settings → Code security and analysis

- ☑️ **Dependency graph**: Enable

**Benefits**: Powers Dependabot and Dependency Review

---

## Part 4: General Repository Settings

### Step 4.1: General Settings

**Path**: Repository → Settings → General

#### Features
- ☑️ **Issues**: Enable
- ☑️ **Sponsorships**: Disable (unless accepting donations)
- ☑️ **Preserve this repository**: Enable (important for long-term projects)
- ☑️ **Discussions**: Enable (for community Q&A)
- ☑️ **Projects**: Enable (for project management)

#### Pull Requests
- ☑️ **Allow squash merging**: Enable (preferred)
  - Default message: `Pull request title and description`
- ☑️ **Allow merge commits**: Disable (conflicts with linear history)
- ☑️ **Allow rebase merging**: Enable
- ☑️ **Automatically delete head branches**: Enable (cleanup after merge)

---

### Step 4.2: Webhook & Notifications

**Path**: Repository → Settings → Webhooks

**Optional**: Set up webhooks for:
- Security alerts → Microsoft Teams channel
- PR activity → Slack/Teams

---

## Part 5: GitHub Advanced Security (GHAS)

**Note**: GHAS required for private repositories. Free for public repos.

If you have GHAS:

**Path**: Repository → Settings → Code security and analysis

1. ☑️ **GitHub Advanced Security**: Enable
2. All features (CodeQL, Secret Scanning, Dependency Review) will be enabled automatically

---

## Part 6: Environments (Optional)

**Path**: Repository → Settings → Environments

For production deployments (future):

1. **Create environment**: `production`
2. **Environment protection rules**:
   - ☑️ **Required reviewers**: Add maintainers
   - ☑️ **Wait timer**: 5 minutes (cooling-off period)
   - ☑️ **Deployment branches**: Only `main`
3. **Environment secrets**: Add production secrets here (not in repository secrets)

---

## Part 7: Verification Checklist

After completing all steps, verify:

### Branch Protection
- [ ] `main` branch has protection rules
- [ ] `bocrivat_main` branch has protection rules
- [ ] Pull requests required before merge
- [ ] Code owner review required
- [ ] All status checks required
- [ ] Conversation resolution required
- [ ] Force push restricted to maintainers only
- [ ] Branch deletion disabled

### Access Control
- [ ] Only 4 users have Admin role
- [ ] Base permissions set to Read (or None)
- [ ] CODEOWNERS file in place (`.github/CODEOWNERS`)

### Security Features
- [ ] CodeQL enabled and running
- [ ] Secret scanning enabled
- [ ] Push protection enabled (if available)
- [ ] Dependabot alerts enabled
- [ ] Dependabot security/version updates enabled
- [ ] Dependency Review workflow running on PRs

### CI/CD
- [ ] All workflows running successfully
- [ ] Status checks appearing in PR checks
- [ ] Security scans completing without errors

### Documentation
- [ ] CONTRIBUTING.md updated
- [ ] SECURITY.md in place
- [ ] SUPPORT.md in place
- [ ] Issue/PR templates created
- [ ] RAI_THREAT_MODEL.md documented
- [ ] SECURITY_BASELINE.md documented

---

## Part 8: Break-Glass Procedure

In emergencies (security incident, critical bug), maintainers can:

### Temporary Override

1. **Disable branch protection** (Settings → Branches → Edit rule)
2. **Push fix directly** to main
3. **Document action** in incident report
4. **Re-enable protection** immediately after
5. **Create post-mortem** issue

**Justifications for break-glass**:
- Active security vulnerability being exploited
- Critical production outage
- All CI infrastructure down (cannot merge via PR)

**Do NOT use for**:
- Convenience
- Avoiding code review
- Rushing features

---

## Part 9: Required Status Checks Reference

After workflows run at least once, add these as required status checks:

### Security Scanning (Required)
```
Secret Scan / TruffleHog Scan
Secret Scan / Gitleaks Scan
RAI Prompt Security / Scan for Prompt Injection Patterns
```

### Optional (Not required for PR, runs on schedule)
```
Quality Check / Check Skills Quality
```

### Disabled Workflows (Available as .disabled files)

The following workflows are disabled to prevent PR blocking issues but can be re-enabled by renaming:

**CI/Testing** (`.github/workflows/ci.yml.disabled`)
- CI / Test (Python 3.9)
- CI / Test (Python 3.10)
- CI / Test (Python 3.11)
- CI / Integration Tests

**Linting** (`.github/workflows/lint.yml.disabled`)
- Lint / Python Lint
- Lint / Markdown Lint
- Lint / YAML Lint

**Security Analysis** (`.github/workflows/security-codeql.yml.disabled`)
- CodeQL / Analyze (python)
- CodeQL / Analyze (javascript-typescript)

**Dependency Management** (`.github/workflows/dependency-review.yml.disabled`)
- Dependency Review / Review Dependencies

Dependabot is now ACTIVE for the `github-actions` ecosystem (`.github/dependabot.yml`); see the "Active dependency updates" callout in section 2.1.2 above. PR-side dependency review remains disabled.

**Supply Chain** (`.github/workflows/ossf-scorecard.yml.disabled`)
- OpenSSF Scorecard / Scorecard Analysis

**To Re-enable**: Rename the `.disabled` file back to `.yml` and commit.

---

## Support

**Questions about configuration?**
- Open an issue in the repository
- Contact maintainers:
  - Bogdan.Crivat@microsoft.com
  - Santhosh.Ravindran@microsoft.com

**Security concerns?**
- Follow [SECURITY.md](../../SECURITY.md) reporting process

---

**Document Version**: 1.0  
**Last Updated**: 2026-02-11  
**Maintainers**: Bogdan Crivat, Santhosh Ravindran
