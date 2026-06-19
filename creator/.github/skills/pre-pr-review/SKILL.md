---
name: pre-pr-review
description: >
  Self-review your skill PR before requesting human / bot review. Runs three independent
  parallel reviews across different models, cross-verifies findings against Microsoft Learn,
  removes false positives, and presents consolidated findings for you to fix BEFORE you
  push the next commit. Adapted from the deep-review pattern used by maintainers.
  Use when your skill PR is functionally complete and you want a high-confidence pass
  catching the issues bot and reviewers usually flag. Triggers: "review my PR",
  "self-review", "pre-review", "deep review my PR", "review before submitting",
  "what will reviewers flag".
---

# Pre-PR Review -- Self-Review Your Skill PR Before Submitting

Run a rigorous, cross-verified review on YOUR OWN PR before a human or bot does. The same
3-reviewer cross-verification pattern maintainers use, scoped to the skill-quality
checklist that drives reviewer flags in this repo.

## When to Use

- After you've run [`pre-pr-check`](../pre-pr-check/SKILL.md) and local quality + Vally + full-eval pass
- Before pushing the commit you want a maintainer to review
- After addressing a review round, before re-pushing (catches new issues introduced by the fix)

## When NOT to Use

- Before local pre-PR-check passes -- you'll waste a review pass on issues lint already catches
- For docs-only PRs touching only `docs/`, `README.md`, `CONTRIBUTING.md` -- this skill targets skill/agent/common changes
- For draft PRs that are still mid-edit -- review the complete diff or you'll get noise

## Requirements

This skill is designed for **Copilot CLI** (or a compatible multi-agent coding assistant such as Claude Code) that exposes the `task` tool for spawning sub-agents in parallel. If your environment only supports a single agent at a time, you can still run the workflow sequentially -- replace each "launch in parallel" step with three serial passes against the same prompt, swapping the model between runs.

## Why Cross-Verification

Single-pass reviews produce a **~40% false-positive rate** on technical claims about Fabric / Power BI / DAX / M / KQL. Cross-verification has each independent pass validate the others' findings against public Microsoft Learn docs. Unanimous consensus has shown **near-100% accuracy** in maintainer use of this same pattern.

---

## Workflow Overview

```
Phase 1: Fetch PR diff, launch 3 independent parallel reviews
    |
Phase 2: Each reviewer cross-verifies the other two's findings against Microsoft Learn
    |
Phase 3: Consolidate -- remove false positives, revise partial, deduplicate
    |
Phase 4: Present findings to you for fix-up
    |
Phase 5 (optional): If your PR is open, post findings as PR comments AFTER your approval
```

Default behavior is to surface findings to you so you can fix them on your branch before pushing. Posting to the PR is opt-in.

---

## Phase 1 -- Independent Parallel Review

### Step 1.1: Fetch the PR diff

If you have a PR number:
```bash
gh pr view <PR_NUMBER> --json number,title,body,headRefOid,files
gh api repos/{owner}/{repo}/pulls/<PR_NUMBER> \
  -H "Accept: application/vnd.github.v3.diff" > pr-diff.txt
```

If you have a local branch but no PR yet:
```bash
git diff origin/main...HEAD > pr-diff.txt
```

### Step 1.2: Launch 3 reviews in parallel

Use the Copilot CLI / Claude Code `task` tool (the built-in sub-agent runner) with `agent_type: "code-review"` and `mode: "background"`, three times, with three different models. Provide each reviewer the full diff + the structured checklist below. If your CLI does not expose `task`, run the three reviews sequentially (same prompt, different models).

**Recommended model combination:**

| Reviewer | Model | Strength |
|---|---|---|
| 1 | `claude-opus-4.7-xhigh` | Deep reasoning, M / DAX precision |
| 2 | `gpt-5.5` | Broad knowledge, doc-grounded evidence |
| 3 | `gemini-3.1-pro-preview` | Fast, strong at structural / pattern issues |

If a model is unavailable, fall back to the closest peer (e.g. `claude-opus-4.7-high`, `gpt-5.4`).

### Step 1.3: Reviewer prompt (use for all 3)

```
You are reviewing a skill PR for the gim-home/skills-for-fabric repository against the
checklist below. Be precise. Cite file:line. Never flag style or formatting.

MUST-CHECK (block merge if wrong):
1. Correctness of guidance -- every CLI command, API endpoint, parameter name, SDK call,
   tool path actually exists and behaves as described. No fabricated --flags or method
   names. KQL / DAX / M / T-SQL syntax is real.
2. Doc fidelity -- matches current Microsoft Learn pages; URLs resolve; version-specific
   guidance is labeled.
3. Routing quality -- description starts with action verb, names the technology;
   trigger phrases land the right user request on this skill.
4. Disambiguation -- won't false-trigger for sibling skills (no overlapping trigger
   phrases unless qualified).
5. Security guidance -- recommends `az login` / service principal / managed identity
   (not hardcoded creds), parameterized queries, least-priv scopes.
6. Structural compliance -- YAML frontmatter present, update-check notice present,
   Must/Prefer/Avoid sections, examples present.
7. Governance & conventions -- no contributor-added or modified `agents/*.agent.md`
   (agents are core-team-only; a new skill's delegation reference needs explicit
   core-team approval in the PR). A new MCP server is justified versus the existing
   `az` / REST path, does not force a second sign-in on top of `az login`, and is not
   duplicated across `.mcp.json` / plugin manifests. The access-method name (`-cli`,
   etc.) matches the skill's actual primary surface.

SHOULD-CHECK (request changes):
8. Token budget -- SKILL.md ~5K tokens; total skill (SKILL.md + auto-loaded refs) <= 15K.
9. Scope discipline -- covers what it claims, no creep into sibling skill's territory.
10. Completeness -- Must/Prefer/Avoid lists cover the common failure modes.
11. Reference accuracy -- links to common/ files exist; cross-skill references valid.
12. Cross-tool compatibility -- CLAUDE.md, .cursorrules, AGENTS.md, .windsurfrules
    updated if conventions changed.
13. Eval coverage -- new skill has at least a minimal eval plan in
    tests/full-eval-tests/plan/03-individual-skills/.
14. Common-folder discipline -- duplicated content moved to common/ and referenced;
    nothing AI-authored landing in common/.

NICE-TO-HAVE (nit, non-blocking):
15. Examples are realistic and copy-pasteable.
16. Error / troubleshooting hints included where users hit walls.
17. Consistent voice with other skills in the same plugin bundle.

For each finding, return:
- Severity: MUST-CHECK / SHOULD-CHECK / NICE-TO-HAVE
- Dimension (from the list above)
- File and line
- What is wrong, what the fix should be
- Evidence (Microsoft Learn URL, or your reasoning if unverifiable)

PR diff:
<paste pr-diff.txt content here>
```

Wait for all 3 background agents to complete. In **Copilot CLI** the runtime surfaces this as a system notification automatically; in **Claude Code / VS Code / Cursor** the `task` (or equivalent sub-agent) call returns when the agent finishes -- check your assistant's docs for the wait/poll mechanism (e.g. `read_agent` in Copilot CLI, polling the agent list in VS Code). Collect findings.

---

## Phase 2 -- Cross-Verify

Re-launch the same 3 agents (background mode again) with this prompt, giving each reviewer the other two's findings:

```
You previously reviewed this PR. Now verify the OTHER TWO reviewers' findings against
official Microsoft documentation. For EACH finding, decide:

- CONFIRMED: cite the doc URL that supports it
- REFUTED: cite the doc URL that disproves it
- UNVERIFIABLE: cannot confirm or deny from public docs (explain why)

Key documentation sources:
- https://learn.microsoft.com/en-us/rest/api/fabric/
- https://learn.microsoft.com/en-us/fabric/
- https://learn.microsoft.com/en-us/power-query/
- https://learn.microsoft.com/en-us/powerquery-m/
- https://learn.microsoft.com/en-us/dax/
- https://learn.microsoft.com/en-us/sql/t-sql/
- https://learn.microsoft.com/en-us/kusto/query/

Also: do a fresh correctness scan -- flag any new correctness issue you missed in Round 1.

Other reviewers' findings to verify:
<paste R1 findings from the other two>

PR diff:
<paste pr-diff.txt content>
```

---

## Phase 3 -- Consolidate

Build the consensus matrix:

| # | Finding | R1 | R2 | R3 | Verdict |
|---|---|---|---|---|---|
| F1 | API path wrong | CONFIRMED | CONFIRMED | CONFIRMED | **CONFIRMED (3/3)** |
| F2 | Default value | CONFIRMED | REFUTED | -- | **DISPUTED** |
| F3 | M scoping claim | -- | REFUTED | REFUTED | **LIKELY FALSE** |

("--" means this reviewer originally raised the finding, so they did not verify it.)

| Consensus | Action |
|---|---|
| 2/2 or 3/3 CONFIRMED | Include in final findings |
| Mixed, 0 REFUTED | Include |
| Any REFUTED with documented evidence | Investigate; remove if evidence is strong |
| Majority REFUTED | Remove -- false positive |

Then:
1. **Remove false positives** -- anything REFUTED by 2+ with doc evidence, or by 1 with a definitive citation.
2. **Revise partials** -- if the core insight is valid but the specific claim is wrong, update to verified facts only.
3. **Deduplicate** -- merge same-issue findings from different angles; keep most precise description, combine evidence, use highest severity.
4. **Add new findings** -- include correctness issues newly surfaced in Round 2 by 2+ reviewers with doc evidence.

---

## Phase 4 -- Present to You

Output the consolidated findings as a numbered list:

```markdown
## Self-Review Findings -- PR #<NUMBER>

| # | Tier | Dimension | File:Line | Summary |
|---|---|---|---|---|
| 1 | MUST-CHECK | Correctness | skills/.../SKILL.md:42 | API path uses deprecated endpoint |
| 2 | MUST-CHECK | Doc fidelity | skills/.../SKILL.md:88 | URL returns 404; page moved |
| 3 | SHOULD-CHECK | Token budget | skills/.../SKILL.md:1 | Skill is 6.2K tokens; trim refs |

### Finding 1 -- MUST-CHECK: Correctness
**File:** `skills/.../SKILL.md:42`
**Issue:** The API path `/v1/workspaces/{id}/items/{itemId}/getDefinition` returns 404; the correct path per Microsoft Learn is `/v1/workspaces/{id}/items/{itemId}/definition`.
**Evidence:** https://learn.microsoft.com/en-us/rest/api/fabric/core/items/get-item-definition
**Suggested fix:** Replace `/getDefinition` with `/definition` on L42, L57, L91.

### Finding 2 -- ...
```

Then ask: **"Fix these locally first? Or post them as PR comments now?"**

Default recommendation: **fix locally first.** A clean PR avoids review-cycle ping-pong. Reserve "post as PR comments" for when you want a teammate's input on a disputed finding.

---

## Phase 5 -- Post as PR Comments (Opt-In Only)

Only execute when you explicitly request it AND a PR exists.

```python
import json
comments = []
for finding in approved_findings:
    comments.append({
        "path": finding["file"],
        "line": finding["line"],
        "body": f"**{finding['tier']}** -- {finding['dimension']}\n\n"
                f"{finding['description']}\n\n"
                f"**Evidence:** {finding['evidence']}"
    })
review = {"body": " ", "event": "COMMENT", "commit_id": "<HEAD_SHA>", "comments": comments}
with open("review.json", "w", encoding="utf-8") as f:
    json.dump(review, f)
```

```bash
gh api repos/{owner}/{repo}/pulls/<PR_NUMBER>/reviews \
  --method POST \
  --input review.json
```

Then cleanup: `rm pr-diff.txt review.json`.

---

## Must

- **Verify every finding against Microsoft Learn** -- correctness is #1
- **Use 3 independent reviewers across different models** -- single-model passes have ~40% false-positive rate
- **Cross-verify before presenting** -- never surface a finding that 2+ reviewers refuted with doc evidence
- **Present findings to you first** -- never auto-post PR comments
- **No implementation details in posted comments** -- never mention models, agents, AI, or the review methodology in anything that appears on the PR
- **All posted comments are inline** -- placed on exact file:line, never as review body text
- **Fetch the full diff** -- don't rely on file listings alone

## Prefer

- **Unanimous (3/3) findings** -- highest signal
- **MUST-CHECK first** -- those block merge
- **Specific doc URLs** as evidence, not general "the docs say"
- **Background mode** for the parallel reviewers -- 3x throughput vs sync
- **Python** for the JSON payload -- avoids PowerShell / bash escaping issues
- **Fix locally, then push** -- one clean force-push beats 5 review-then-fix rounds

## Avoid

- **Posting comments without your approval** -- always present findings first
- **Mentioning models, agents, or AI** in anything the PR author or reviewers will see
- **Flagging style / formatting** -- focus on the 17 checklist dimensions only
- **Using the review body for findings** -- use inline comments only
- **Trusting M language scoping claims** without verifying against the Power Query M spec -- dotted identifiers like `Lakehouse.Contents` are single tokens, not field access
- **Assuming API casing** -- different Fabric APIs use different conventions; verify `kind`, `type`, enum values against actual responses or docs
- **Running this on a PR with hundreds of files** -- split by changed-files focus or you'll exceed reviewer context

---

## Examples

### Example 1: Self-review a single-skill PR

**User prompt:** "Deep review my PR #289 before I request review."

**Workflow:**
1. Fetch diff for #289.
2. Launch 3 background reviewers with the checklist prompt.
3. After all 3 complete, launch round 2 with cross-verification.
4. Consolidate: 7 raw -> 4 confirmed, 2 refuted, 1 revised.
5. Present 5 findings (4 confirmed + 1 revised) to the user.
6. User fixes locally, commits, re-pushes.

### Example 2: Pre-push self-review (no PR yet)

**User prompt:** "I'm about to push my branch. Run a deep review on `git diff origin/main...HEAD`."

**Workflow:**
1. Capture local diff.
2. Same 3-reviewer + cross-verify flow.
3. Findings surface BEFORE the PR exists -- fix and push a clean first commit.

### Example 3: Handling a disputed finding

During Round 2, R1 claims `Lakehouse.Contents` shadows a local M variable. R2 and R3 refute, citing the M language spec where dotted identifiers are single tokens.

**Result:** Finding is removed before presenting (2/3 refuted with doc evidence). Cross-verification prevented a false positive that would have wasted a maintainer's time.

---

## Limitations

- **Model availability** -- fall back to peer models while keeping 3-reviewer minimum
- **Rate limits** -- 3 concurrent agents per round (6 total across two rounds); batch if rate-limited
- **Documentation lag** -- official docs may lag API reality; note when verification is inconclusive
- **Context window** -- PRs > 100KB diff may need to be split by changed-files; focus on changed files individually
- **Runtime correctness** -- some bugs only surface by actually running Vally / full-eval, not by docs review. Run [`pre-pr-check`](../pre-pr-check/SKILL.md) for runtime validation.

---

## See Also

- `.github/skills/pre-pr-check/SKILL.md` -- runtime validation (quality lint + Vally + full-eval) before submitting
- `.github/skills/quality-check/SKILL.md` -- structural lint deep-dive
- `CONTRIBUTING.md` -- the canonical checklist this skill internalizes
