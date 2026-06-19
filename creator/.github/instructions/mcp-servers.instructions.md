---
applyTo: "{**/.mcp.json,mcp-setup/**,plugins/**/plugin.json,skills/**/SKILL.md}"
---

# MCP Server Review Guidelines

## Purpose

Apply when a PR introduces or changes an MCP server -- a new key in a `.mcp.json`, a new `mcpServers` block in a plugin manifest, an `mcp-setup/` template, or a SKILL.md that depends on a newly added server. CI does not judge whether a new MCP server is warranted, how it authenticates, or whether its definition is duplicated. Contributors may add an MCP server when their skill needs one (CONTRIBUTING.md "What Goes Where"); the goal is to confirm the addition is justified, cheap to authenticate, and defined once -- not to block MCP usage.

## Justify the need

A new MCP server is a new dependency and a new surface. When a PR adds one, the description should say why MCP is needed instead of the `az` / REST / CLI path that other `-cli` skills already use. Flag a new server that arrives with no rationale; ask for a one-line justification (a capability the CLI/REST path lacks, or multi-step orchestration the tool encapsulates). This is guidance, not a blocker -- a clear rationale resolves it.

## Authentication cost (double auth)

Skills here authenticate through `az` token acquisition, delegated to `common/COMMON-CLI.md`. A server that needs its OWN sign-in on top of `az login` makes the user authenticate twice. Flag a new server whose auth is additive to `az`; ask whether the `az`-acquired token can be reused, or whether the capability can ride on an already-registered server. Call out the double-auth cost explicitly so the author can weigh it.

## Single source of truth

A server definition (endpoint, headers, allow-listed tools) duplicated across `.mcp.json`, plugin manifests, and marketplace files drifts -- one copy is updated and the others silently diverge. Flag the same server defined in more than one hand-edited place; recommend one canonical definition. Marketplace files are generated (see [`plugins.instructions.md`](plugins.instructions.md)), so the concern is the hand-edited `.mcp.json` and `plugins/*/plugin.json` sources. A new top-level server key is cross-cutting -- note it for core-team awareness.

## Surface naming

A skill whose primary surface is MCP tools (not `az` / `curl` / `sqlcmd`) should encode that in its access-method name instead of defaulting to `-cli`. Flag the mismatch and ask the author to reconcile; do not prescribe a new access-method value (e.g. `-mcp`), since new values need `common/` docs plus validator updates first (CONTRIBUTING.md "What does the `{access_method}` slot mean?").

## Tool-name specificity (do not over-flag)

Listing exact MCP operation or tool names in body prose helps decision-tree guidance, but the level of specificity is the author's maintainability call -- exact names drift when tools are renamed. Do NOT flag a contributor for deliberately collapsing named operations into a generic reference (e.g. "the model-authoring MCP tools") as long as the reader can still tell which tool family or surface to use. Flag only when genericization makes the guidance unactionable or resolves to the wrong tool. The "name specific technologies/SDKs/tools" rule in [`skills.instructions.md`](skills.instructions.md) governs the frontmatter `description`, not body prose.
