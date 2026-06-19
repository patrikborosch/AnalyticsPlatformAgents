---
name: quality-check
description: >
  Run local quality checks on skills-for-fabric before committing. Validates all skills in the skills/ folder
  for structural compliance, semantic disambiguation, broken references, and content quality. Use before
  submitting a PR to catch issues early. Triggers: "check my skills", "run quality check", "validate skills",
  "pre-commit check", "lint skills".
---

# Local Quality Check

Run quality checks on all skills before committing to catch issues early.

## When to Use

- Before creating a PR with skill changes
- After adding or modifying a skill
- To validate cross-references and semantic conflicts

## Prerequisites

Ensure Python 3.8+ and dependencies are installed:

```bash
pip install PyYAML requests
```

## Running the Check

### From Repository Root

```bash
# Navigate to skills-for-fabric root
cd /path/to/skills-for-fabric

# Run quality checker
python .github/workflows/quality_checker.py
```

### PowerShell (Windows)

```powershell
cd C:\path\to\skills-for-fabric
python .github\workflows\quality_checker.py
```

## Understanding Results

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed (or only warnings) |
| 1 | Critical issues found - must fix before PR |
| 2 | Script error |

### Output Report

The checker creates `quality-report.json` with detailed findings. Key sections:

```json
{
  "overall_status": "PASSED|WARNING|CRITICAL",
  "critical_count": 0,
  "warning_count": 3,
  "semantic_conflicts": [],
  "duplicate_triggers": [],
  "broken_references": [],
  "structural_issues": [],
  "content_warnings": [],
  "skills": { ... }
}
```

## Quality Checks Performed

### Critical (Must Fix)

| Check | What It Validates |
|-------|-------------------|
| YAML Frontmatter | `name` and `description` fields present |
| Description Length | Description ≤ 1023 characters |
| Update Notice | Blockquote with update check instructions |
| Cross-References | All `[text](path)` links resolve to existing files |
| Trigger Uniqueness | No duplicate trigger phrases across skills |
| Semantic Disambiguation | Descriptions don't overlap >70% with other skills |

### Warnings (Should Fix)

| Check | What It Validates |
|-------|-------------------|
| Description Length Warning | Description approaching limit (≥ 900 chars) |
| Must/Prefer/Avoid | Guidance sections present |
| Examples | Code examples or prompt/response pairs |
| Code Block Tags | Language tags on fenced code blocks |
| Description Quality | Mentions technologies |
| Naming Convention | Follows `{endpoint}-authoring/consumption/monitoring-{access}` |
| External Links | URLs are accessible (sampled) |

## Fixing Common Issues

### Missing Frontmatter

Add at the top of SKILL.md:

```yaml
---
name: my-skill-name
description: >
  Clear description ...
---
```

### Missing Update Notice

Add after frontmatter:

```markdown
> **Update Check — ONCE PER SESSION (mandatory)**
> The first time this skill is used in a session, run the **check-updates** skill before proceeding.
> - **GitHub Copilot CLI / VS Code**: invoke the `check-updates` skill.
> - **Claude Code / Cowork / Cursor / Windsurf / Codex**: compare local vs remote package.json version.
> - Skip if the check was already performed earlier in this session.

> **CRITICAL NOTES**
> 1. To find the workspace details (including its ID) from workspace name: list all workspaces and, then, use JMESPath filtering
> 2. To find the item details (including its ID) from workspace ID, item type, and item name: list all items of that type in that workspace and, then, use JMESPath filtering
```

### Broken Reference

Check the path exists. Common mistake:
- Wrong: `../sqlep-consumption-cli/SKILL.md`
- Right: `../sqldw-consumption-cli/SKILL.md`

### Untagged Code Block

Add language after opening fence:
- Wrong: ` ``` `
- Right: ` ```bash ` or ` ```sql `

### Semantic Conflict

Differentiate your skill's description from the conflicting skill. Make trigger phrases unique.

## Must

- Run quality check before every PR
- Fix all critical issues before submitting
- Review warnings and fix where appropriate
- After running the automated check, review all skills in the skills/ folder for content quality: Is the content appropriate? Redundant ())things you know already)? Too verbose? Too lightweight? Comment and make suggestions without changing anything yet
  
## Prefer

- Run check after each significant change
- Keep `quality-report.json` out of commits (add to .gitignore)
- Address warnings to improve skill discoverability

## Avoid

- Submitting PRs with critical issues
- Ignoring semantic conflicts (causes AI routing problems)
- Leaving broken cross-references
