# Contributing to Fabric Skills

Thank you for your interest in contributing to Microsoft Fabric Skills!

> **TL;DR for your first PR**
> 1. Read [Skill Authoring Guide](docs/skill-authoring-guide.md).
> 2. Fork the repo and write your skill under `skills/<your-skill-name>/SKILL.md`.
> 3. From the repo root in Copilot CLI, invoke **`/pre-pr-check`** -- walks you through quality lint + ephemeral smoke + filtered full-eval for the skills you changed. **Run it interactively, not under autopilot / auto-approve** -- it pauses for you to `az login` in your own terminal and to run the tests for each step; an autonomous agent will skip those and report a green pass that never ran.
>    - **Before running it, do the one-time ephemeral-tenant login** (Vally eval run against the shared ephemeral test tenant, not your corp tenant). Join the `PBI-Test-UserAcc-Access` AAD security group (if you just joined, propagation can take time), then open `aka.ms/fabrictenants` (MSIT tab), download `AdminCert01.pfx` for the current MsitPrimary tenant and install it, and `az login --tenant msitprimary<date>.onmicrosoft.com` as `AdminUser01`. Full steps: [ephemeral-tenant-smoke.md](docs/ephemeral-tenant-smoke.md).
> 4. Then invoke **`/pre-pr-review`** -- runs a cross-verified self-review against the same checklist maintainers / bots use. **Iterate with it**: fix each finding or push back with evidence if you disagree, then re-run, until you and the agent agree the PR is ready to merge.
> 5. Push and open your PR. CI auto-runs Skill PR Validation + PR-touched smoke + PR-touched full-eval; results land as sticky comments.
> 6. In the PR description, briefly note any manual checks CI doesn't run -- trigger-overlap pair scores for multi-skill PRs, baseline-no-skills delta for new skills, tenant-specific repro. Don't paste smoke / eval output; CI already shows it.
> 
> Everything below is reference (governance, naming, plugin manifests, etc.). For your first PR, the 6 steps above are the critical path.

## Quick Start

### Fork & Branch

> **You must work from a personal fork.** Direct pushes to branches on `gim-home/skills-for-fabric` are not permitted -- contributors do not have write access to this repository. All contributions flow through a fork + pull request.

1. **Fork** the repository on GitHub at <https://github.com/gim-home/skills-for-fabric> (click the **Fork** button). This creates `https://github.com/<your-username>/skills-for-fabric` under your account.
2. **Clone your fork** locally (not the upstream repo):

```bash
git clone https://github.com/<your-username>/skills-for-fabric.git
   cd skills-for-fabric
```

3. **Add the upstream remote** so you can pull in changes from `gim-home`:

```bash
git remote add upstream https://github.com/gim-home/skills-for-fabric.git
   git remote -v   # verify: origin -> your fork, upstream -> gim-home
```

4. **Create a dedicated branch** for your contribution:

```bash
   git checkout -b <your-branch-name>   # e.g., add-realtime-authoring-skill
```

5. Make your changes, test locally, then **push to your fork** and open a PR against `gim-home/skills-for-fabric:main`:

```bash
   git push origin <your-branch-name>
```

> Do **not** commit directly to `main` -- neither on your fork nor (you can't anyway) upstream. Always work on a feature branch so the PR diff stays clean and reviewable.

To keep your fork's `main` in sync with upstream:

```bash
git fetch upstream
git checkout main
git reset --hard upstream/main
git push origin main --force-with-lease
```

### Learn the Repo

1. Read the **[Skill Authoring Guide](docs/skill-authoring-guide.md)** -- comprehensive how-to
2. Read the **[Contributor Kit](docs/contributor-kit.md)** -- ownership + coverage expectations
3. Read the **[Vally eval guide](tests/evals/README.md)** -- canonical test harness for new and changed skill behavior
4. Read the **[Testing Guide](docs/testing-guide.md)** -- local commands, full-eval runner, plus legacy manual-only smoke break-glass context
5. Skim the **[Ephemeral Tenant Smoke](docs/ephemeral-tenant-smoke.md)** -- break-glass only; nightly CI runs Vally on the same shared tenant
6. Review the **[Quality Requirements](docs/quality-requirements.md)** -- what makes a good skill
7. Check the **[Skill Catalog](docs/skill-catalog.md)** -- see existing skills as examples

### Before You Submit (use these two skills)

Two `.github/skills/` skills automate the pre-PR check + self-review flow. Invoke them via Copilot CLI from the repo root:

| Skill | When | Invoke | What it does |
| --- | --- | --- | --- |
| [**`pre-pr-check`**](.github/skills/pre-pr-check/SKILL.md) | Before pushing | `/pre-pr-check` or "verify my PR locally" | Walks you through quality lint + ephemeral smoke + filtered full-eval for the skills you changed |
| [**`pre-pr-review`**](.github/skills/pre-pr-review/SKILL.md) | After local checks pass, before requesting human review | `/pre-pr-review` or "deep review my PR" | Runs 3 parallel cross-verified reviews against the same checklist maintainers / bots use |

Running both before pushing typically eliminates 80%+ of the bot / reviewer round-trips.

> **Run `pre-pr-check` interactively -- do NOT hand it to an autopilot / auto-approve agent.** Each step pauses for something only you can do in your own terminal: an interactive `az login` against the ephemeral tenant (Copilot CLI cannot pop the browser), then running the Vally / full-eval steps and reading their output before moving on. An autonomous agent will skip the login and the per-step waits and report a green pass that never actually ran -- the worst kind of false confidence right before review. Drive it yourself, one step at a time.
>
> **`pre-pr-review` is a loop, not a one-shot.** Treat its findings as a conversation: fix what is real, push back with evidence on what is not, then re-run it so the next pass sees your changes. Repeat until you and the agent converge on "ready" -- a clean pass after every finding has been addressed or consciously dismissed. Stopping after one pass with open findings just moves the same flags onto the human reviewer's plate.

### EXAMPLE:  [**Create a new skill**](prompt_examples/skills-creator/CreateAFabricSkill.txt) -- see how to use CLI to create a skill

## Scope of Contributions

**Skills only** -- The agent definitions under `agents/` are **fixed** and maintained by the core team. Do not create, rename, or modify agent files. All contributions should focus on **skills** (under `skills/`) and their supporting documentation.

If you believe an agent change is needed, open an issue describing the gap and the team will evaluate it.

## Skill Category Governance

### Approved Categories

All skills MUST belong to one of the three approved skill categories:

| Category | Naming Pattern | Purpose |
| --- | --- | --- |
| **Authoring** | `{endpoint}-authoring-{access_method}` | Developer workflows -- DDL/DML, CI/CD, SDK, deployment |
| **Consumption** | `{endpoint}-consumption-{access_method}` | Interactive data exploration -- read-only queries, schema discovery, ad-hoc analysis |
| **Operations** | `{endpoint}-operations-{access_method}` | Workload operator workflows -- monitoring, diagnostics, performance investigation, system views, DMVs, troubleshooting within a single workload |

> **What does the `{access_method}` slot mean?** It is the third segment of the full pattern `{endpoint}-{category}-{access_method}` and identifies *how* the skill drives Fabric. Most shipping skills use `cli` -- driving Fabric through command-line tools (`az rest`, `az login`, `sqlcmd`, `curl`, `jq`) and delegating auth/tooling to [`common/COMMON-CLI.md`](common/COMMON-CLI.md). Some skills (e.g. `semantic-model-consumption`) drive Fabric through MCP-server tools instead; the access-method discriminator distinguishes them.
> 
> The slot is a **discriminator**, not decoration. It exists so the same endpoint and category can ship parallel skills for other access methods -- e.g., `sqldw-authoring-sdk` (Fabric Python/.NET SDK), `sqldw-authoring-mcp` (MCP server tools), or `sqldw-authoring-portal` (Fabric portal walk-throughs). Do not invent new access-method values without first adding the corresponding `common/` documentation and updating the validators.
> 
> **Status today:** `cli` is the only access method with shipping skills and a defined runtime baseline ([`common/COMMON-CLI.md`](common/COMMON-CLI.md)). `mcp` is in limited use (see [CLI vs. MCP](#cli-vs-mcp-choosing-an-access-method)). **`sdk` and `portal` are reserved -- no skills currently ship in those modes.** `portal` is expected to land soon for workflows the UI is best at (some portal-only, some paired with a CLI counterpart for the parts the API can't cover); the first `-portal` or `-sdk` skill needs an issue + core-team sign-off before the PR, same governance bar as `-mcp` (user-visible benefit, runtime/auth model, the `common/` companion doc, eval expectations).
> 
> **Choosing between `-cli` and `-mcp` is a real architectural decision, not a label.** `-cli` is the default for new skills, and `-cli` → `-mcp` migrations of shipped skills require an issue + core-team sign-off before the PR. See [CLI vs. MCP: Choosing an Access Method](#cli-vs-mcp-choosing-an-access-method) for the rationale and the migration gate.

New skills MUST fit within one of these three categories. Do **not** create skills in other categories (e.g., security, migration, upgrade, GPU acceleration) without explicit approval from the core team.

> **Operations is the workload-operator category.** Concerns like **monitoring**, **diagnostics**, **performance tuning**, and **troubleshooting** within a single workload fall under Operations. The persona is the **workload operator** -- typically the same developer who authored the workload, now investigating its runtime behavior (not a tenant or capacity admin).
> 
> **Tenant, workspace, and capacity administration do NOT belong in workload categories.** Cross-workload governance work (tenant settings, capacity management, workspace-level policies, cross-workload security governance) belongs in the **FabricAdmin agent** (`agents/FabricAdmin.agent.md`), which is maintained by the core team. Workload teams must not create or modify agent files directly -- if your scenario needs the `FabricAdmin` agent extended, open an issue describing the gap and the core team will evaluate it. If you're tempted to create a `{endpoint}-admin-cli`, stop and ask whether the work is actually tenant/workspace-level -- if yes, file a request against `FabricAdmin` instead.
> 
> **Known exceptions -- project-shaped skills.** Migration skills (`databricks-migration`, `hdinsight-migration`, `synapse-migration`) do not follow the three-category pattern because they are one-time, project-scoped workflows rather than ongoing workload interactions. New project-shaped skills (e.g., upgrade flows) may be proposed as named top-level skills, but require the same governance bar as a new category.

### Why Three Categories

Constraining to three categories is a deliberate governance decision, not a technical limitation:

1. **Context window discipline** -- Every additional skill consumes LLM context. Uncontrolled growth degrades model quality for all users, not just the new skill's audience.
2. **Platform cost** -- Each skill adds overhead in plugin registration, marketplace metadata, and folder management. The cost compounds across the ecosystem.
3. **Collection-based installation** -- Most users install the full skill collection. Internally, skills are structured into categories for hygiene; externally, the collection is opaque. Adding categories does not improve the end-user experience for 99% of users.
4. **Intentional design over reactive creation** -- Skills must be designed with purpose, not created reactively because an upstream team requests one. The bar is: *"Can we achieve the same outcome without a new skill? Show that it's not possible."*

### Proposing a New Category

If you believe a scenario genuinely cannot be served by Authoring, Consumption, or Operations:

1. Open an issue with the title `[New Category Proposal]: {name}`
2. Include:

    - **Scenario description** -- What user problem does this solve?
    - **Proof of insufficiency** -- Demonstrate that the existing three categories cannot cover this scenario (include example prompts and expected vs. actual behavior)
    - **Impact assessment** -- How many skills would this category add? What is the context window cost?

3. The core team will review. Approval requires demonstrating a clear functional gap, not just organizational convenience.

### Specialization via Compound Endpoints

If a scenario needs specialization (e.g., SQL security, GPU acceleration), the preferred pattern is a **compound-endpoint skill** that still fits within the three categories:

```javascript
{endpoint}-{specialization}-{authoring|consumption|operations}-{access_method}
```

**Examples:**

- `sqldw-security-authoring-cli` -- SQL security authoring workflows (CLI access)
- `spark-gpu-authoring-cli` -- GPU-accelerated Spark authoring (CLI access)

This is preferred over:

- ❌ A new top-level category (e.g., `sqldw-security-cli` as a 4th category)
- ❌ A sub-skill concept (not a shipped platform feature)

compound-endpoint skills must still pass the same bar as any new skill:

1. **Minimum 5 eval prompts** covering the specialization's distinct behaviors
2. **Baseline validation** proving the existing parent skill (e.g., `sqldw-authoring-cli`) cannot handle these prompts adequately
3. **Trigger-overlap check** against sibling skills -- especially the parent endpoint (e.g., `sqldw-authoring-cli`) where trigger overlap is most likely
4. **Ownership clarity** in `.github/skill-ownership.yml` -- the specialization team owns the compound skill, separate from the parent endpoint team

If the baseline test shows the parent skill already handles the prompts well, the compound skill is not needed -- add the content to the parent instead.

## Key Guidelines (Summary)

For detailed documentation, see the `docs/` folder. Here's the quick summary:

### Skill Structure

Each skill lives in its own folder under `skills/` with a `SKILL.md` file.

```javascript
skills/my-skill/
├── SKILL.md              # Required
└── references/           # Optional
```

### Naming Convention

- **Developer skills**: `{endpoint}-authoring-{access_method}` (e.g., `sqldw-authoring-cli`)
- **Consumer skills**: `{endpoint}-consumption-{access_method}` (e.g., `sqldw-consumption-cli`)
- **Operations skills**: `{endpoint}-operations-{access_method}` (e.g., `sqldw-operations-cli`)
- **Agents** (core team only, not contributor-authored): `{persona}` (e.g., `FabricDataEngineer`, `FabricAdmin`) for cross-endpoint orchestration -- workload teams must not add or modify these

### What Goes Where

| Content Type | Location | Editable by | See Guide |
| --- | --- | --- | --- |
| Agent definition | `agents/{persona}.agent.md` | Core team only | [Architecture Overview](docs/architecture-overview.md) |
| Skill definition | `skills/{name}/SKILL.md` | Contributors | [Skill Authoring](docs/skill-authoring-guide.md) |
| Shared reference docs | `common/` | Core team only | [Common Folder](docs/common-folder-guide.md) |
| Plugin manifest (`skills` / `mcpServers` arrays of existing plugins) | `plugins/<name>/.github/plugin/plugin.json` | Contributors (existing plugins only) | [Plugins](docs/plugins-guide.md) |
| Creating a new plugin | `plugins/<new-name>/...` | Core team only -- file an issue | [Plugins](docs/plugins-guide.md) |
| Marketplace files | `.claude-plugin/marketplace.json`, `.github/plugin/marketplace.json` | **Auto-generated** by `python build/build_plugins.py` from per-plugin manifests | [Plugins](docs/plugins-guide.md) |
| Marketplace-level metadata (collection name, owner) | `build/marketplace.config.json` | Core team only | [Plugins](docs/plugins-guide.md) |
| MCP server config | `mcp-setup/` and `mcpServers` block in plugin manifests | Contributors (when their skill needs one) | [MCP Servers](docs/mcp-servers-guide.md) |

### Plugin Manifest Update (Required For New Skills)

Adding a skill to `skills/` is not enough -- it must also be referenced from at least one plugin manifest, otherwise it does not ship to users.

When you add a new skill, edit the relevant plugin manifest(s) per this routing table:

| Skill suffix | Add `"./skills/<name>"` to these manifests |
| --- | --- |
| `-authoring-cli` | `plugins/fabric-authoring/.github/plugin/plugin.json` **and** `plugins/fabric-skills/.github/plugin/plugin.json` |
| `-consumption-cli` | `plugins/fabric-consumption/...` **and** `plugins/fabric-skills/...` |
| `-operations-cli` | `plugins/fabric-operations/...` **and** `plugins/fabric-skills/...` |
| `e2e-*` (cross-workload) | `plugins/fabric-skills/...` and the relevant axis if applicable |
| Migration / project-shaped (sanctioned exceptions) | `plugins/fabric-skills/...` only |

Always include `fabric-skills` (the union bundle) in addition to the axis plugin. Forgetting the union is the most common contribution mistake.

After editing the manifest(s), **run the build** -- this regenerates the marketplace files and materializes the plugin trees so you can install locally:

```bash
python build/build_plugins.py
```

The build does two things:

1. **Materializes** `plugins/<name>/{skills,agents,common,.mcp.json}` (gitignored -- used for local install testing).
2. **Regenerates** `.github/plugin/marketplace.json` and `.claude-plugin/marketplace.json` from your manifest changes (committed, kept in sync automatically). The plugin-to-skills mapping consumed by the PR-touched smoke detector and runners is read directly from each `plugins/<name>/.github/plugin/plugin.json` at runtime via `build/plugin_index.py`, so there is no separate denormalized index file to keep in sync.

**You must commit the regenerated marketplace files** along with your manifest change. Do **not** edit them by hand -- your edits will be reverted on the next build. CI runs `python build/build_plugins.py --check` and will fail loudly if they drift.

#### Test the plugin locally

After running the build, install your repo as a local marketplace and verify your skill shows up:

```bash
# In Copilot CLI / Claude Code, register this repo as a marketplace
/plugin marketplace add D:\FabricSkills

# Browse the collection -- your new skill should appear under the right plugin
/plugin marketplace browse fabric-collection

# Install the plugin you added the skill to
/plugin install fabric-authoring@fabric-collection
```

If your skill does **not** show up in `browse`, you forgot to re-run `python build/build_plugins.py` after editing the manifest -- the marketplace was not regenerated.

#### Clean up the materialized plugin trees

The build writes `plugins/<name>/{skills,agents,common,.mcp.json}` for local install. These are gitignored, but you can delete them when you're done testing to keep your working tree tidy:

```bash
python build/build_plugins.py --purge
```

This removes only the materialized content. Manifests, marketplace files, and tracked files are untouched.

See [docs/plugins-guide.md](docs/plugins-guide.md) for full details.

### What to Avoid

- ❌ Executable scripts or implementation code in skills (use guidance and principles instead)
- ❌ Skills over 15,000 tokens (split or move content to common/)
- ❌ Overlapping trigger phrases with other skills
- ❌ Vague descriptions without action verbs or technologies
- ❌ Code templates that users copy-paste (enable LLM to generate code on-demand)
- ❌ **Creating or modifying agent files** -- agents are fixed; contribute skills only

See: [Quality Requirements](docs/quality-requirements.md)

### Delegate Authentication & Tooling to Common

Skills must **not** include their own authentication flows, token acquisition logic, or tool installation instructions. These concerns are handled centrally in [COMMON-CLI.md](common/COMMON-CLI.md) and [COMMON-CORE.md](common/COMMON-CORE.md).

Specifically, do **not** embed any of the following inside a skill:

| Topic | Where it belongs |
| --- | --- |
| Azure CLI login / `az login` | [COMMON-CLI.md](common/COMMON-CLI.md) |
| Token acquisition (`az account get-access-token`) | [COMMON-CLI.md](common/COMMON-CLI.md) |
| `az rest` patterns and `--resource` usage | [COMMON-CLI.md](common/COMMON-CLI.md) |
| `sqlcmd` setup and connection strings | [COMMON-CLI.md](common/COMMON-CLI.md) |
| Tool install commands (e.g., `pip install`, `npm install`, download links) | [COMMON-CLI.md](common/COMMON-CLI.md) |
| Workspace/item resolution via REST | [COMMON-CORE.md](common/COMMON-CORE.md) |

Instead, reference the common documentation in your skill's **Prerequisite Knowledge** section:

```markdown
## Prerequisite Knowledge

Read these companion documents:

- [COMMON-CORE.md](../../common/COMMON-CORE.md) -- Fabric REST API patterns, auth
- [COMMON-CLI.md](../../common/COMMON-CLI.md) -- CLI implementation (az, sqlcmd, curl, jq)
```

This keeps authentication consistent across all skills and avoids divergent solutions.

### CLI vs. MCP: Choosing an Access Method

`-cli` is the default for new skills. `-mcp` is allowed when it delivers something the CLI baseline cannot, and `-cli` → `-mcp` migrations of shipped skills require an issue + core-team sign-off before the PR. For setup mechanics see [docs/mcp-servers-guide.md](docs/mcp-servers-guide.md); this section is the policy on *when*.

#### `-mcp` means *remote* MCP

`-mcp` in this repo means a **remote HTTP MCP endpoint** -- Fabric-hosted, workload-team-hosted, or org-hosted -- with its own auth/scope model. **Local stdio MCP is rejected by default.** A local stdio server is one the user runs as a child process of their AI client (`npx -y @vendor/...`, `pip install ... && python -m ...`, standalone binary on PATH). Running in the user's `az login` context, it can't deliver centralized policy / typed contracts / server-side caches (the user can always bypass it with `az rest`), and strictly adds install burden, supply-chain surface, and round-trip cost on top of the CLI baseline. "Wrap the `sqlcmd` / `az rest` calls a `-cli` skill already makes in a local MCP" is not a migration -- it is a packaging change that degrades the skill. Don't open an issue for it.

#### Tradeoff at a glance

| Concern | `-cli` (default) | `-mcp` (remote) |
| --- | --- | --- |
| Auth | `az login` only, shared via [`common/COMMON-CLI.md`](common/COMMON-CLI.md) | Server's own auth *on top of* `az login` (users still need both for control-plane ops) |
| LLM efficiency | One deterministic shell command per tool call | Tool discovery + JSON-arg construction + server round trip per call |
| Runtime surface | None beyond `az` / `sqlcmd` / `curl` / `jq` | Hosted endpoint to operate -- scopes, config, audit, SLA |
| Right when | The CLI/REST surface exists and the model can drive it directly | Typed contracts, server-side caches, persistent sessions, centralized policy enforcement, or genuinely no CLI/REST path the model can reach |

"MCP feels cleaner" or "newer is better" is not a justification.

#### Migration gate: `-cli` → `-mcp`

Open an issue before the PR -- same pattern as `agents/` and `common/` changes. Cover:

1. **User-visible benefit** the CLI baseline cannot deliver.
2. **Auth & runtime impact** -- does the server reuse `az` creds; what new processes / scopes / network paths.
3. **Security & operations** -- credential storage, logged scopes, audit trail, supply-chain; also any *gains* (read-only enforcement, row caps, tenant scoping the CLI can't enforce).
4. **Remote-server design** -- host, owner, SLA, scopes/audience, telemetry.
5. **Side-by-side eval** against the skill's existing eval prompts (quality, latency, tokens-per-prompt). Net-positive is the bar; a wash is not enough.

PRs that swap a working CLI path (`sqlcmd`, `az rest`) for an MCP tool without the issue thread are closed and redirected. Greenfield `-mcp` skills follow the same pattern; the eval comparison (item 5) is required at PR time rather than in the issue.

### Multi-Skill Contributions

When a PR introduces or modifies **more than one skill**, you must verify that the skills are sufficiently distinct:

1. **Run the Jaccard similarity check** between every pair of affected skills:

```bash
   python .github/workflows/quality_checker.py
```

   The quality checker reports Jaccard similarity scores for all skill-pair descriptions. For your changed skills, confirm:

    - **< 20%** -- Good, no action needed
    - **20-30%** -- Review and consider differentiating descriptions
    - **≥ 30%** -- Must differentiate before merge (Critical)

2. **Differentiate overlapping descriptions** by adding technology qualifiers, persona distinctions, or endpoint specifics. See [Quality Requirements -- Jaccard](docs/quality-requirements.md) for examples.
3. **Mention the scores in your PR description** so reviewers can verify -- a short bullet like "Jaccard A vs B: 18%, A vs C: 24%" is enough.

## Minimum Evaluation Prompts

### Requirement

Every skill MUST be submitted with **at least 5 evaluation prompts**. These prompts:

- Are stored in the skill's individual eval plan under `tests/full-eval-tests/plan/03-individual-skills/`
- Are executed **nightly** (21:00 UTC cron, all plans) AND on every PR that touches a covered skill (CI auto-narrows to matching plans) via `tests/run-full-tests.ps1`
- Must cover the skill's core scenarios (not just happy-path trivial cases)

### Baseline Validation (No-Skill Test)

Before submitting a new skill, you MUST validate that the **evaluation prompts fail or produce inferior results without the skill loaded**. This proves the skill adds genuine value.

**Process:**

1. **Run prompts without the skill**: Remove or unlink the skill from your local environment, then run each of the 5+ evaluation prompts against the base agent (no skill loaded).
2. **Record baseline results**: Document what the model produces without the skill -- incorrect output, missing context, hallucinated APIs, or generic responses.
3. **Run prompts with the skill**: Re-enable the skill and run the same prompts.
4. **Note the delta in your PR description**: include a short comparison showing how the skill improved the output (incorrect APIs hallucinated without it, generic responses, etc.). One paragraph is enough.

If the model already handles the prompts well without the skill, the skill is not needed. This is the practical application of the governance bar: *"Show me that it's not possible to do without a skill."*

### Eval Prompt Quality

Each evaluation prompt must include:

| Field | Description |
| --- | --- |
| **Case ID** | Unique identifier (e.g., `SA-01`) |
| **Prompt** | The exact user prompt to send |
| **Expected Result** | What a correct response looks like |
| **Pass Criteria** | Objective criteria for pass/fail |

See existing eval plans in `tests/full-eval-tests/plan/03-individual-skills/` for examples.

### Adding a Vally eval to your skill

Vally is the required PR and nightly harness for new or changed skill behavior. Add or update `tests/evals/<skill>/eval.yaml` with at least Layer 0 coverage (`skill-invocation`, `completed`, crash-pattern rejection, output assertion, and budget graders). `tests/evals/README.md` is the canonical guide and includes the Layer 0 template plus the eventhouse Layer 1+2 worked example. Keep legacy smoke (`tests/tests.json` and `tests/run-smoke-tests.ps1`) manual-only unless you are maintaining the break-glass path.

## Testing Your Skill Locally

> **Mandatory**: You must test your skill locally **before** opening a PR.
> PRs that fail basic quality or coverage checks will be sent back for revision.
> Skill PRs auto-trigger the Vally gate from `tests/evals/` and still run the fast repository checks. Full-eval plans remain available for deeper manual evidence. Legacy smoke is manual-only break-glass.

### Install Pre-commit Hook (Recommended)

Install the pre-commit hook to run quality and security checks automatically before each commit:

```bash
# Windows (PowerShell)
Copy-Item .github\hooks\pre-commit .git\hooks\pre-commit

# macOS/Linux
cp .github/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

The hook runs on your machine (Windows/Linux/Mac) and blocks commits with critical issues.

### GitHub Copilot CLI

There are two ways to test a skill locally -- use both at different stages.

**1. Symlink the canonical skill (fast iteration on content):**

```bash
# Windows
New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.copilot\skills\{skill-name}" -Target ".\skills\{skill-name}"

# macOS/Linux
ln -s $(pwd)/skills/{skill-name} ~/.copilot/skills/{skill-name}
```

Use this while iterating on `SKILL.md` content. Edits take effect on the next session.

**2. Install through the materialized plugin (validates manifest + plugin shape -- required before PR):**

```bash
python build/build_plugins.py --clean
```

This materializes `plugins/<plugin>/{skills,agents,common,.mcp.json}` on disk (gitignored). Then point your CLI at the plugin folder, e.g. for Copilot CLI dev:

```javascript
/plugin install file://<repo-root>/plugins/fabric-authoring
```

Use this once before opening the PR. It is the only test that catches a missing manifest entry -- the symlink path bypasses plugins entirely.

Then start a new Copilot CLI session and test prompts that should trigger your skill.

### Verifying Skill Loading

In Copilot CLI, you can check which skills are loaded:

```javascript
/skills list
```

## Cross-Tool Compatibility

When adding a new skill or agent, update these compatibility files if needed:

- `compatibility/CLAUDE.md` - Add skill reference
- `compatibility/.cursorrules` - Add relevant rules
- `compatibility/AGENTS.md` - Add for Codex/Jules
- `compatibility/.windsurfrules` - Add for Windsurf
- `compatibility/GEMINI.md` - No action needed; it imports `@./AGENTS.md` and mirrors it automatically

## Pull Request Checklist

- [ ] **Pre-PR check passed locally** -- quality lint + ephemeral smoke + filtered full-eval for changed skills (use [`.github/skills/pre-pr-check`](.github/skills/pre-pr-check/SKILL.md) or see [Testing Your Skill Locally](#testing-your-skill-locally))
- [ ] **Pre-PR review run** -- self-review via [`.github/skills/pre-pr-review`](.github/skills/pre-pr-review/SKILL.md) before requesting human review
- [ ] **Skill category compliance** -- skill belongs to Authoring, Consumption, or Operations (see [Skill Category Governance](#skill-category-governance))
- [ ] Skill folder and `SKILL.md` created
- [ ] **Plugin manifest(s) updated** -- skill added to the appropriate `plugins/<name>/.github/plugin/plugin.json` per the [routing table](#plugin-manifest-update-required-for-new-skills); `python build/build_plugins.py` succeeds locally
- [ ] **Regenerated marketplace files committed** -- the build updates `.github/plugin/marketplace.json` and `.claude-plugin/marketplace.json`; commit those changes alongside your manifest edits (CI runs `--check` mode and fails on drift)
- [ ] `.github/skill-ownership.yml` updated for every added/renamed/moved skill (new TEAMS must include a `contact` block before they own any skill -- see [contributor-kit.md](docs/contributor-kit.md#ownership-manifest))
- [ ] `.github/coverage-policy.yml` updated if a new coverage exemption is added or tracked debt is paid down
- [ ] **No agent files modified** -- agents under `agents/` are core-team-owned; gaps must be raised via issue, not PR
- [ ] **No `common/` files modified** -- `common/` is core-team-owned; coordinate via issue for changes
- [ ] **Marketplace files NOT hand-edited** -- they are generated from per-plugin manifests by `build/build_plugins.py`; manual edits will be reverted
- [ ] Description is clear and discoverable
- [ ] Reference documentation links are valid
- [ ] At least one example provided
- [ ] **Minimum 5 eval prompts** submitted in `tests/full-eval-tests/plan/03-individual-skills/`
- [ ] **Baseline validation** -- prompts tested without the skill to confirm the skill adds value (delta worth noting in the PR description for new skills)
- [ ] Tested locally with Copilot CLI
- [ ] Vally eval coverage added/updated in `tests/evals/<skill>/eval.yaml` for new or changed skill behavior
- [ ] Full-eval evidence considered for deeper paired or handoff workflows
- [ ] Legacy manual-only smoke break-glass results recorded only when that fallback path is intentionally used
- [ ] **Trigger-overlap pair scores** -- if multi-skill PR, confirm all pair-wise scores < 30% via `python .github/workflows/quality_checker.py` (worth noting borderline pairs in the PR description)
- [ ] **No auth/tooling embedded in skill** -- authentication, tokens, `sqlcmd`, `az rest` patterns delegate to `common/`
- [ ] **Access-method choice justified** -- new `-mcp` skills and `-cli` → `-mcp` migrations link to the design issue + side-by-side eval comparison required by [CLI vs. MCP: Choosing an Access Method](#cli-vs-mcp-choosing-an-access-method). `-cli` skills do not need this.
- [ ] Updated compatibility files (if applicable)
- [ ] Added a `.changeset/` fragment for your changelog entry (see [`.changeset/README.md`](.changeset/README.md))
- [ ] Updated relevant specs/docs if behavior changed (see `docs/`)
- [ ] **Security**: No hardcoded secrets or credentials
- [ ] **Security**: Reviewed against docs/RAI\_THREAT\_MODEL.md
- [ ] **Security**: Added tests for prompt injection resistance (if applicable)

## Automated Quality Checks

When you submit a PR that modifies files in `skills/`, an automated quality check runs. The check validates:

### Critical Issues (Block PR)

| Check | Description |
| --- | --- |
| **YAML Frontmatter** | Must have `name` and `description` fields |
| **Update Notice** | Must include the update check blockquote (except `check-updates`) |
| **Description Length** | Frontmatter description must stay within the check-in limit |
| **Encoding Integrity** | Skill markdown files must be valid UTF-8 and free of high-confidence mojibake markers |
| **Common-Infra Compliance** | Generic auth/token/sqlcmd guidance must reference the shared `common/` docs |
| **Cross-References** | All relative links must point to existing files |
| **Trigger Uniqueness** | Trigger phrases must not conflict with other skills |
| **Semantic Disambiguation** | Descriptions must not overlap >30% with other skills |

Other guidance, including the recommended workspace/item discovery instructions, is
still part of the authoring standard but is not yet a separate blocking check in the
quality checker.

### Warnings (Review Recommended)

| Check | Description |
| --- | --- |
| **Must/Prefer/Avoid Sections** | Should include guidance sections |
| **Examples** | Should include code or prompt/response examples |
| **Code Block Tags** | All code blocks should have language tags (e.g., `bash`, `sql`) -- the opening triple-backtick fence followed by a language identifier |
| **Description Quality** | Should start with action verb, mention technologies |
| **Naming Convention** | Should follow `{endpoint}-authoring-{access}`, `{endpoint}-consumption-{access}`, or `{endpoint}-operations-{access}` pattern |
| **External Links** | URLs should be accessible (sampled, rate-limited) |

### Running Locally

Test your skill before submitting. For the full command matrix and the distinction
between the asset audit, Vally harness, legacy manual-only smoke break-glass path, and full-eval runner, see the
**[Testing Guide](docs/testing-guide.md)**.

```bash
# Install dependencies
pip install PyYAML requests pytest

# Run quality check
python .github/workflows/quality_checker.py

# Verify plugin manifests resolve (catches typos, missing common refs, forgotten union-bundle entry)
python build/build_plugins.py

# Audit legacy smoke / eval asset coverage
python tests/coverage_gap_report.py

# Enforce new-skill ownership / coverage policy
python tests/coverage_enforcement.py --base-ref origin/main

# Validate ownership manifest coverage
python -m unittest tests/test_skill_ownership_manifest.py -v

# Run repo tests (or the specific test files you changed)
pytest tests/ -v
```

> `docs/skill-catalog.md` is refreshed manually by maintainers -- do not regenerate it in feature PRs (it causes conflicts when multiple skill PRs are open).

### Manual checks worth mentioning in the PR description

CI runs the heavy validators automatically on every PR: quality lint, semantic / unit tests, ownership validation, coverage enforcement, **PR-touched smoke** (only the tests matching changed skills), and **PR-touched full-eval** (only the plans matching changed skills). The sticky `Skill PR Validation` comment summarizes the result.

You do NOT need to paste smoke / individual-eval / combined-eval results in the PR description -- CI captures all of that, and pasting it manually goes stale on the next push. Instead, briefly mention any of these that apply:

- **Trigger-overlap pair scores** for multi-skill PRs (CI flags pairs > 30% but does not show the pair-wise table). A short bullet like "A vs B: 18%, A vs C: 24%" is enough.
- **Baseline (no-skills) comparison** for new skills -- a paragraph noting how output differs without the skill loaded. This proves the skill adds value over the base model.
- **Tenant-specific repro** or anything else you couldn't put in CI -- screenshots, manual eval against a specific workspace state, etc.
- **Vally eval evidence** -- if you ran `tests/run-vally-eval.ps1` against a tenant for new or changed skill behavior, mention the eval spec (e.g., `tests/evals/<skill>/eval.yaml`) and the pass rate. CI runs Vally too, but tenant-specific notes are worth surfacing.
- **Legacy manual-only smoke break-glass** -- record only when the fallback path was intentionally used.

For local pre-PR validation, use [`.github/skills/pre-pr-check`](.github/skills/pre-pr-check/SKILL.md) (covers the runtime checks CI runs, Vally-first) and [`.github/skills/pre-pr-review`](.github/skills/pre-pr-review/SKILL.md) (cross-verified self-review), or see the **[Testing Guide](docs/testing-guide.md)** for the canonical command list.

Notes:

- `tests/coverage_gap_report.py` is an **asset audit**, not a behavior test. It confirms whether the repo sees your skill as missing legacy smoke / eval assets.
- `tests/coverage_enforcement.py` is the **blocking policy check** for new-skill ownership / smoke / eval requirements.
- `tests/run-vally-eval.ps1` is the **primary harness** for new or changed skill behavior; pass `-EvalDirs <skill>` to scope a single skill.
- `tests/run-full-tests.ps1` is the current **full eval suite runner**; record the per-skill result and merged summary when you use it.

### Fixing Common Issues

| Issue | Fix |
| --- | --- |
| Missing frontmatter | Add `---` delimited YAML at file start with `name:` and `description:` |
| Missing update notice | Add the blockquote from CONTRIBUTING.md template |
| Broken reference | Fix relative path or update referenced file location |
| Untagged code block | Add a language identifier (e.g., `bash`, `sql`) immediately after the opening triple-backtick fence |
| Semantic conflict | Differentiate description from conflicting skill |

## Maintaining the Changelog

When adding or modifying skills, **add a changeset fragment under `.changeset/`** instead of editing `CHANGELOG.md` directly. This eliminates merge conflicts on `CHANGELOG.md` when multiple PRs are open at the same time.

### Per-PR changelog entry (contributors)

1. Create a new file under `.changeset/` named `PR<number>-<short-slug>.md`, e.g. `PR306-workload-team-onboarding.md`. (No PR number yet? Use `PR-DRAFT-<slug>.md` and rename when you open the PR.)
2. Use **markdown subsections** (`### Added`, `### Changed`, `### Removed`, `### Fixed`). A single fragment can contribute to multiple subsections. Optionally mark `audience: public` if external users of `microsoft/skills-for-fabric` should also see your bullet (default: `internal`):

```markdown
# PR #306 -- short title describing the PR

audience: public   <!-- optional; omit or write `internal` for contributor-only -->

### Added

- **`skills/dataflows-consumption-cli`** -- one-bullet summary of what changed and why.

### Fixed

- **`skills/foo-authoring-cli`** -- corrected the expectedResults regex...
```

3. Commit the file alongside your changes. **Do not edit `CHANGELOG.md` directly** -- the release script consumes your fragment into `## [Unreleased]` at release time.

See [`.changeset/README.md`](.changeset/README.md) for full details on the audience marker + how the public vs internal routing works.

### Public vs internal CHANGELOG

`public/CHANGELOG.md` is auto-populated at release time from fragments marked `audience: public` AND can still be hand-curated by release maintainers for the public mirror at `microsoft/skills-for-fabric`. Use `audience: public` when the change is something external skills-for-fabric users would care about (new user-facing skill, rename, skill bug fix, public docs). Leave the marker absent or use `audience: internal` for contributor tooling, CI, internal helpers, infra refactors. When unsure, leave it absent -- maintainers can hand-add a missing entry, but a leaked public entry is harder to undo.

### Release-time consumption (maintainers)

Run `ReleaseScripts/StampUnreleased.ps1` BEFORE stamping a version to consume all pending fragments into the internal `CHANGELOG.md` `## [Unreleased]` section, then delete the consumed fragments. The maintainer then moves `## [Unreleased]` to `## [0.3.x] - YYYY-MM-DD` and curates the consumer-facing highlights into `public/CHANGELOG.md`.

```powershell
.\ReleaseScripts\StampUnreleased.ps1 -DryRun     # preview
.\ReleaseScripts\StampUnreleased.ps1             # consume + delete fragments
```

## Creating a Release (Maintainers)

To create a full release (consume changesets, version stamp, tag, and GitHub release):

```powershell
# Consume pending changesets first
.\ReleaseScripts\StampUnreleased.ps1

# Then run the release script
.\ReleaseScripts\CreateFullRelease.ps1                  # preview only
.\ReleaseScripts\CreateFullRelease.ps1 -CommitAndPush
```

The release script then:

1. Shows the 3 most recent version tags and suggests the next patch version
2. Stamps the version in `package.json`, `marketplace.json`, and related files
3. Commits, tags, pushes, and creates a GitHub Release

**Prerequisites:** `git`, `python`, and `gh` (GitHub CLI) must be installed and in PATH.

The skill catalog (`docs/skill-catalog.md`) is **refreshed manually by maintainers** -- contributors do not regenerate in feature PRs (it causes conflicts when multiple skill PRs are open). Maintainers can refresh by running `python .github/scripts/generate_skill_catalog.py` from the repo root.

## Documentation

For detailed contributor guides:

| Guide | Purpose |
| --- | --- |
| [Architecture Overview](docs/architecture-overview.md) | Repository structure |
| [Skill Authoring Guide](docs/skill-authoring-guide.md) | Create skills (comprehensive) |
| [Common Folder Guide](docs/common-folder-guide.md) | Shared reference docs |
| [Plugins Guide](docs/plugins-guide.md) | Skill bundling |
| [Quality Requirements](docs/quality-requirements.md) | Quality standards |
| [Testing Guide](docs/testing-guide.md) | Tests and CI/CD |
| [MCP Servers Guide](docs/mcp-servers-guide.md) | MCP registration |
| [Skill Catalog](docs/skill-catalog.md) | Existing skills |

For planning documents (ADRs, specs, RFCs): see [docs/README.md](docs/README.md)

## Questions?

Open an issue or ask in discussions!

For suggestions, requests for review, or help, you can also reach the team in the official [Creator Copilot and Fabric Skills Teams channel](https://teams.microsoft.com/l/channel/19%3Aa3c6a06efa184d45b398741f71fefd1a%40thread.tacv2/Creator%20Copilot%20and%20Fabric%20Skills?groupId=15ad1733-5282-4599-abd1-90e81fa4f4a6&tenantId=72f988bf-86f1-41af-91ab-2d7cd011db47).