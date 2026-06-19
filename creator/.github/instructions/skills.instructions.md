---
applyTo: "skills/**/*.md"
---

# Skill Content Review Guidelines

## Purpose

Review `skills/**/*.md`. CI (`quality_checker.py`) already checks YAML frontmatter, update notice, encoding, links, trigger uniqueness, Jaccard < 30%, and common-infra leakage; do not re-flag those. Cite CONTRIBUTING.md per finding.

## Fabric REST API accuracy

If a skill or `references/` file names a Fabric REST API, verify against https://learn.microsoft.com/en-us/rest/api/fabric (full checklist in [`core-team-only.instructions.md`](core-team-only.instructions.md)).

## Vally eval coverage

Vally evals are the primary testing surface. For new skills or material behavior changes, require `tests/evals/<skill>/eval.yaml`; see `tests/evals/README.md` for grader policy, threshold semantics, and Layer 0/1/2 onboarding. Do not request new legacy smoke stims unless maintaining that fallback.

## SKILL.md structure

Warning-only or unenforced in CI; flag missing:

- CRITICAL NOTES on workspace/item resolution (list workspaces/items, then JMESPath filter)
- `Must` / `Prefer` / `Avoid` sections
- At least one `Examples` block (code or prompt/response)

## Naming convention

Skill folders MUST match one of:

- `{endpoint}-authoring-{access_method}` (developer workflows)
- `{endpoint}-consumption-{access_method}` (interactive query)
- `{endpoint}-operations-{access_method}` (workload operator)
- `e2e-{name}` (cross-workload end-to-end)
- Exceptions: `databricks-migration`, `hdinsight-migration`, `synapse-migration`

Flag new top-level skills with `-admin-` (use `FabricAdmin` agent), `-monitoring-` (use `-operations-`), or `-security-` (use `{endpoint}-{spec}-{authoring|consumption|operations}-cli`).

## Description quality

The frontmatter `description` MUST start with an action verb, name specific technologies/SDKs/tools, and distinguish from siblings. Flag vague phrasing like "Helps with X" or "Use this skill for Y".

## Anti-patterns from other tools

Flag ecosystem leakage:

- `dbutils.widgets` (Databricks) -- Fabric uses `notebookutils` parameter cells.
- `dbfs:/` URIs (Databricks) -- Fabric uses `abfss://` OneLake URIs.
- `mssparkutils.credentials.getToken('keyvault'...)` (Synapse) -- replace with `notebookutils`.
- HDInsight cluster CLI in skills not under `hdinsight-*`.

## Content that belongs in `common/`

`SKILL.md` MUST NOT inline `az login` flows, `az account get-access-token` recipes, `sqlcmd` setup / connection strings, tool-install commands, or workspace/item resolution via REST. These belong in `common/COMMON-CLI.md` or `common/COMMON-CORE.md`.

If 3+ `SKILL.md` files add the same paragraph/checklist, recommend extracting it to `common/<TOPIC>-CORE.md` and replacing each copy with a one-line link. Name the proposed file; `common/` additions need core-team approval, and a follow-up PR is acceptable.

## Size and copy-paste templates

`SKILL.md` over ~15,000 tokens (rough proxy: > 60 KB) is blocking -- split into `references/` or move shared content to `common/`. Flag long paste-ready code blocks (> 30 lines); skills should guide generation, not ship templates.

## Manual checks worth noting in the PR

The author may briefly mention manual evidence CI cannot capture (trigger-overlap pair scores for multi-skill PRs, baseline no-skill comparison for new skills, tenant-specific repro). This is optional; CI runs the heavy validators itself (Vally is the primary harness; legacy smoke is break-glass only) and reports via the sticky `Skill PR Validation` comment.
