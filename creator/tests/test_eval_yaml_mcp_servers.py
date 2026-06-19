"""Structural consistency check between plugins/**/.github/plugin/plugin.json
mcpServers declarations and tests/evals/<skill>/eval.yaml declarations.

Rule: for every plugin manifest whose `mcpServers` map contains a key, every
skill bundled in that plugin (`skills: ["./skills/<name>"]`) MUST declare the
SAME MCP server under its eval's `environment.mcpServers` -- so the Vally
session that loads the skill also has the MCP server attached. Otherwise the
agent can call tools the eval cannot validate.

Exceptions: meta-skills with no eval.yaml (e.g. check-updates) are skipped.

Why this exists: PR #322 cut over from a plugin-install-time MCP overlay to
native Vally `environment.mcpServers` declarations. A future contributor
adding a skill to powerbi-authoring (or adding a new MCP-bearing plugin)
without updating the corresponding eval.yaml would silently break the CI
gate. This test catches that drift at structural-lint time, before any
trial spawns.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = REPO_ROOT / "plugins"
EVALS_DIR = REPO_ROOT / "tests" / "evals"

# Skills bundled in MCP-bearing plugins that have no eval.yaml (and never
# need one). Update only when a new MCP-bearing meta-skill ships.
EVAL_LESS_SKILLS: set[str] = {"check-updates"}

# MCP servers this lint enforces.
#
# Why this is not "every server in every plugin manifest": Option C in
# PR #322 cut over only the powerbi-modeling-mcp server to Vally's native
# environment.mcpServers declaration. The FabricIQ MCP server (in
# fabric-consumption + fabric-skills plugins) is an HTTP MCP server against
# a Microsoft endpoint with its own auth path; it is intentionally NOT
# covered by Option C and stays on the legacy plugin-install discovery
# path. Adding it here would force every fabric-consumption / fabric-skills
# eval to declare a HTTP MCP block that today resolves via plugin install,
# which is out of scope for the cutover PR.
#
# Add a server name here only when its cutover PR also adds the matching
# environment.mcpServers block to every eval the lint will then enforce.
#
# Adding a new server to the enforcement scope requires three coordinated
# edits that MUST land in the same PR (otherwise staged evals run without
# auth and silently fail):
#   1. Append the server name to ENFORCED_MCP_SERVERS below.
#   2. Add an environment.mcpServers.<name> block to every eval.yaml that uses
#      it (mirror the powerbi-modeling-mcp block under tests/evals/*/eval.yaml).
#   3. Add a per-server CI staging helper in tests/run-vally-eval.ps1 alongside
#      Add-CiPowerBiMcpAuthToStagedEval and wire it into the staging loop.
# If (1) lands without (3), the staged eval has no auth injection; if (2) lands
# without (1), this lint stops enforcing the consistency. There is no single
# source of truth today. Follow-up (not blocking): drive the scope from a JSON
# manifest that the staging helpers and this lint both read, so adding a server
# is a one-line edit and the three-way consistency is structurally guaranteed.
# Tracked in issue #352.
ENFORCED_MCP_SERVERS: set[str] = {"powerbi-modeling-mcp"}


def _collect_mcp_bearing_skills() -> dict[str, set[str]]:
    """Return {mcp-server-name: {skill1, skill2, ...}} from plugin manifests.

    A skill appears under a given MCP server key if it is bundled in any
    plugin whose `mcpServers` map contains that key.
    """
    result: dict[str, set[str]] = {}
    if not PLUGINS_DIR.is_dir():
        return result
    for pj in PLUGINS_DIR.rglob("plugin.json"):
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            continue
        servers = data.get("mcpServers") or {}
        if not isinstance(servers, dict):
            continue
        skills = data.get("skills") or []
        for raw in skills:
            if not isinstance(raw, str):
                continue
            name = raw.replace("./skills/", "").strip()
            if not name:
                continue
            for server_name in servers.keys():
                result.setdefault(server_name, set()).add(name)
    return result


def _eval_mcp_servers(eval_path: Path) -> set[str]:
    """Return the set of mcpServers keys declared in an eval.yaml's
    `environment.mcpServers` block. Returns empty set if absent.
    """
    try:
        doc = yaml.safe_load(eval_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if not isinstance(doc, dict):
        return set()
    env = doc.get("environment") or {}
    if not isinstance(env, dict):
        return set()
    mcp = env.get("mcpServers") or {}
    if not isinstance(mcp, dict):
        return set()
    return set(mcp.keys())


class PluginEvalMcpConsistencyTests(unittest.TestCase):
    """Plugin manifests are the source of truth for which skills need which
    MCP servers. The eval.yaml `environment.mcpServers` block must match.
    """

    def test_every_mcp_bearing_skill_declares_its_servers_in_eval_yaml(self):
        skills_by_server = _collect_mcp_bearing_skills()
        violations: list[str] = []

        for server, skills in sorted(skills_by_server.items()):
            if server not in ENFORCED_MCP_SERVERS:
                # See ENFORCED_MCP_SERVERS comment above for the scoping
                # rationale (e.g. FabricIQ is intentionally excluded from
                # the Option C cutover).
                continue
            for skill in sorted(skills):
                if skill in EVAL_LESS_SKILLS:
                    continue
                eval_path = EVALS_DIR / skill / "eval.yaml"
                if not eval_path.is_file():
                    violations.append(
                        f"  Skill {skill!r} is bundled in a plugin with "
                        f"mcpServers[{server!r}] but tests/evals/{skill}/eval.yaml "
                        f"does not exist. Either add the eval or add {skill!r} "
                        f"to EVAL_LESS_SKILLS in this test file."
                    )
                    continue
                declared = _eval_mcp_servers(eval_path)
                if server not in declared:
                    violations.append(
                        f"  tests/evals/{skill}/eval.yaml must declare "
                        f"environment.mcpServers[{server!r}] (skill is bundled "
                        f"in a plugin that declares this server). Currently "
                        f"declared: {sorted(declared) or '(none)'}."
                    )

        if violations:
            self.fail(
                f"Plugin-vs-eval MCP consistency violated in "
                f"{len(violations)} location(s):\n" + "\n".join(violations) +
                "\n\nAdd the missing environment.mcpServers block to the "
                "eval.yaml (use the same shape as the 5 powerbi-modeling-mcp "
                "evals: type: stdio, command, args, timeout). See "
                "tests/evals/semantic-model-authoring/eval.yaml for the "
                "canonical example."
            )

    def test_eval_yaml_does_not_declare_unknown_mcp_servers(self):
        """Reverse direction: an eval.yaml that declares an MCP server which
        is not present in any plugin manifest is a red flag (either the
        plugin manifest is stale or the eval references a server that won't
        be installed in CI). Only enforced for servers in
        ENFORCED_MCP_SERVERS (the cutover scope).
        """
        known_servers = set(_collect_mcp_bearing_skills().keys())
        violations: list[str] = []
        for eval_path in sorted(EVALS_DIR.rglob("eval.yaml")):
            declared = _eval_mcp_servers(eval_path)
            # Only flag declared servers that ARE in our enforcement scope
            # but are NOT present in any plugin manifest. A user-declared
            # MCP server outside the enforcement scope is their business.
            in_scope = declared & ENFORCED_MCP_SERVERS
            unknown = in_scope - known_servers
            if unknown:
                rel = eval_path.relative_to(REPO_ROOT)
                violations.append(
                    f"  {rel}: declares mcpServers={sorted(unknown)} which is "
                    f"NOT bundled in any plugin manifest under plugins/**/plugin.json. "
                    f"Either remove the declaration or add the server to a plugin."
                )
        if violations:
            self.fail(
                f"Eval-side mcpServers references {len(violations)} unknown "
                f"server(s):\n" + "\n".join(violations)
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
