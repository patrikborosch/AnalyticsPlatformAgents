"""
Build script for skills-for-fabric plugins.

Reads each plugins/<name>/.github/plugin/plugin.json manifest (awesome-copilot
layout) and:

1. Materializes the plugin tree (skills/, agents/, common/, .mcp.json) by copying
   from the canonical sources at repo root: skills/, agents/, common/.
   This output is gitignored on the internal repo (sync-step product).

2. Generates BOTH marketplace files from the per-plugin manifests:
     - .github/plugin/marketplace.json   (Copilot CLI)
     - .claude-plugin/marketplace.json   (Claude Code)
   These are byte-identical and ARE committed. The marketplace's plugin list,
   skills/agents arrays, mcpServers, descriptions, keywords, etc. all derive
   from the per-plugin manifests. Marketplace-level metadata (collection name,
   owner, plugin order, aliases) lives in build/marketplace.config.json.
   Version comes from package.json. Optional `aliases` in the config emit
   duplicate marketplace entries (e.g., to keep a renamed plugin id resolvable
   for already-installed users running /plugin update).

The plugin-to-skills index (which skills ship inside each plugin) is no longer
emitted as a denormalized artifact. Consumers (smoke detector, runners, tests)
read it directly from the per-plugin manifests via `build/plugin_index.py`.

Manifest references skills and agents by relative path inside the plugin:
    "skills":  ["./skills/<name>", ...]
    "agents":  ["./agents/<name>.agent.md", ...]

The common/*.md closure is auto-derived: skills reference them via
../../common/X.md, which resolves correctly when common/ sits at
plugins/<name>/common/. We parse those links and copy only the files actually used.

Usage:
    python build/build_plugins.py            # build + regenerate marketplaces
    python build/build_plugins.py --clean    # delete materialized content first, then rebuild
    python build/build_plugins.py --purge    # delete materialized content and exit (no rebuild)
    python build/build_plugins.py --check    # CI gate: fail if marketplaces differ from generator output

Contributor flow: edit plugins/<name>/.github/plugin/plugin.json (e.g., add a
skill to its `skills` array), run this script, commit both the manifest change
and the regenerated marketplace files.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import posixpath
import re
import shutil
import sys
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
SKILLS_SRC = REPO_ROOT / "skills"
AGENTS_SRC = REPO_ROOT / "agents"
COMMON_SRC = REPO_ROOT / "common"

MARKETPLACE_CONFIG = REPO_ROOT / "build" / "marketplace.config.json"
PACKAGE_JSON = REPO_ROOT / "package.json"
MARKETPLACE_FILES = [
    REPO_ROOT / ".github" / "plugin" / "marketplace.json",
    REPO_ROOT / ".claude-plugin" / "marketplace.json",
]

COMMON_LINK_RE = re.compile(r"(?:\.\./)+common/((?:[a-z0-9_-]+/)*[a-z0-9_-]+\.md)", re.IGNORECASE)


MANIFEST_REL = Path(".github") / "plugin" / "plugin.json"


def load_manifests() -> list[tuple[Path, dict]]:
    manifests = []
    for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
        if not plugin_dir.is_dir():
            continue
        manifest_path = plugin_dir / MANIFEST_REL
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifests.append((plugin_dir, manifest))
    return manifests


def _strip_prefix(value: str, prefix: str) -> str:
    """Strip a leading ./<prefix>/ from a manifest reference, if present."""
    v = value.strip()
    if v.startswith("./"):
        v = v[2:]
    if v.startswith(prefix + "/"):
        v = v[len(prefix) + 1:]
    return v


# Matches relative markdown links to local .md files (used inside common files for transitive closure)
_LOCAL_MD_LINK_RE = re.compile(r"\]\((?!https?://|mailto:)([^)#\s]+\.md)(?:#[^)]*)?\)")


def collect_common_closure(skill_dirs: list[Path]) -> set[str]:
    """Walk every markdown file under each skill dir and collect referenced common
    file relative paths (e.g. 'FILE.md' or 'subdir/file.md'), then transitively
    scan those common files for further relative links within the common tree."""
    referenced: set[str] = set()
    for skill_dir in skill_dirs:
        for md_path in skill_dir.rglob("*.md"):
            text = md_path.read_text(encoding="utf-8", errors="replace")
            for match in COMMON_LINK_RE.finditer(text):
                referenced.add(match.group(1))

    # Transitive closure: common files may reference other files within common/
    queue = list(referenced)
    visited = set(referenced)
    while queue:
        rel_path = queue.pop()
        common_file = COMMON_SRC / rel_path
        if not common_file.is_file():
            continue
        text = common_file.read_text(encoding="utf-8", errors="replace")
        parent = PurePosixPath(rel_path).parent
        for match in _LOCAL_MD_LINK_RE.finditer(text):
            link = match.group(1)
            resolved = posixpath.normpath(str(parent / link))
            if resolved.startswith(".."):
                continue  # outside common tree
            if resolved not in visited and (COMMON_SRC / resolved).is_file():
                visited.add(resolved)
                referenced.add(resolved)
                queue.append(resolved)

    return referenced


def copytree_clean(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def build_plugin(plugin_dir: Path, manifest: dict, *, clean: bool = False) -> list[str]:
    name = manifest["name"]
    issues: list[str] = []
    skill_refs: list[str] = manifest.get("skills", [])
    agent_refs: list[str] = manifest.get("agents", [])
    mcp_servers = manifest.get("mcpServers", {})

    # Resolve manifest references (./skills/<name>, ./agents/<name>.agent.md) to
    # canonical sources under repo-root skills/ and agents/.
    skill_names = [_strip_prefix(s, "skills") for s in skill_refs]
    agent_files = [_strip_prefix(a, "agents") for a in agent_refs]
    agent_names = [Path(a).stem.replace(".agent", "") for a in agent_files]

    # Validate sources
    skill_src_dirs: list[Path] = []
    for s in skill_names:
        src = SKILLS_SRC / s
        if not src.is_dir():
            issues.append(f"[{name}] missing source skill: skills/{s}")
            continue
        skill_src_dirs.append(src)

    agent_src_files: list[Path] = []
    for a in agent_files:
        src = AGENTS_SRC / a
        if not src.is_file():
            issues.append(f"[{name}] missing source agent: agents/{a}")
            continue
        agent_src_files.append(src)

    if issues:
        return issues

    # Compute common closure from referenced links inside the included skills
    referenced_common = collect_common_closure(skill_src_dirs)
    common_rel_paths: list[str] = []
    for rel_path in sorted(referenced_common):
        src = COMMON_SRC / rel_path
        if not src.is_file():
            issues.append(f"[{name}] skill references missing common/{rel_path}")
            continue
        common_rel_paths.append(rel_path)

    if issues:
        return issues

    # Materialize
    skills_out = plugin_dir / "skills"
    agents_out = plugin_dir / "agents"
    common_out = plugin_dir / "common"
    mcp_out = plugin_dir / ".mcp.json"

    if clean:
        for d in (skills_out, agents_out, common_out):
            if d.exists():
                shutil.rmtree(d)
        if mcp_out.exists():
            mcp_out.unlink()

    # Skills (folder copy)
    skills_out.mkdir(parents=True, exist_ok=True)
    # Remove any stale skill folders not in this build
    for existing in skills_out.iterdir():
        if existing.is_dir() and existing.name not in skill_names:
            shutil.rmtree(existing)
    for src in skill_src_dirs:
        copytree_clean(src, skills_out / src.name)

    # Agents (single files)
    agents_out.mkdir(parents=True, exist_ok=True)
    for existing in agents_out.iterdir():
        if existing.is_file() and existing.stem.replace(".agent", "") not in agent_names:
            existing.unlink()
    for src in agent_src_files:
        copy_file(src, agents_out / src.name)

    # Common (computed closure — wipe and rebuild to handle subdirectories)
    if common_out.exists():
        shutil.rmtree(common_out)
    common_out.mkdir(parents=True, exist_ok=True)
    for rel_path in common_rel_paths:
        copy_file(COMMON_SRC / rel_path, common_out / rel_path)

    # .mcp.json: write a minimal envelope from manifest's mcpServers
    mcp_payload = {"mcpServers": mcp_servers or {}}
    mcp_out.write_text(json.dumps(mcp_payload, indent=2) + "\n", encoding="utf-8")

    return []


def snapshot_dir(root: Path) -> dict[str, bytes]:
    """Hash-able snapshot of file contents (used by --check)."""
    snap: dict[str, bytes] = {}
    if not root.exists():
        return snap
    for p in root.rglob("*"):
        if p.is_file():
            snap[str(p.relative_to(root)).replace("\\", "/")] = p.read_bytes()
    return snap


def _read_version() -> str:
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    return pkg["version"]


def _read_repo_url() -> str:
    """Read repository URL from package.json (single source of truth)."""
    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    repo = pkg.get("repository", {})
    url = repo.get("url", "") if isinstance(repo, dict) else str(repo)
    # Strip trailing .git for clean display URLs
    return url.removesuffix(".git")


def generate_marketplace(manifests: list[tuple[Path, dict]]) -> str:
    """Build the marketplace JSON content from per-plugin manifests + marketplace.config.json.

    Returns the JSON text (with trailing newline) that should be written to BOTH
    .github/plugin/marketplace.json and .claude-plugin/marketplace.json.

    Aliases (optional): if marketplace.config.json defines an `aliases` array, each
    alias produces an additional plugin entry that mirrors a canonical plugin's
    fields but under a different name (used to keep deprecated/renamed plugin ids
    resolvable so already-installed users can `/plugin update` again). The alias
    entry's description gets a configured `descriptionPrefix` prepended.
    """
    config = json.loads(MARKETPLACE_CONFIG.read_text(encoding="utf-8"))
    version = _read_version()
    repo_url = _read_repo_url()
    order: list[str] = config.get("pluginOrder", [])
    by_name = {m["name"]: (plugin_dir, m) for plugin_dir, m in manifests}

    # Determine emit order: configured order first, then anything else alphabetically.
    ordered: list[tuple[Path, dict]] = []
    for name in order:
        if name in by_name:
            ordered.append(by_name[name])
    for name in sorted(by_name):
        if name not in order:
            ordered.append(by_name[name])

    # Group aliases by their target plugin so each alias is emitted immediately
    # after its canonical entry (semantic grouping in `marketplace browse` output).
    # Validate alias config before emitting: every alias must have a known target,
    # alias names must not collide with canonical plugin names, and alias names
    # themselves must be unique. Each check fails fast with a clear message so a
    # misconfigured aliases array can't ship a marketplace.json that has two
    # entries with the same name (which would make /plugin install/update lookups
    # ambiguous).
    aliases_by_target: dict[str, list[dict]] = {}
    seen_alias_names: set[str] = set()
    for alias_def in config.get("aliases", []):
        alias_name = alias_def["alias"]
        of_name = alias_def["of"]
        if of_name not in by_name:
            raise SystemExit(
                f"build/marketplace.config.json: alias '{alias_name}' "
                f"references unknown plugin '{of_name}'"
            )
        if alias_name in by_name:
            raise SystemExit(
                f"build/marketplace.config.json: alias '{alias_name}' "
                f"collides with a canonical plugin of the same name"
            )
        if alias_name in seen_alias_names:
            raise SystemExit(
                f"build/marketplace.config.json: alias '{alias_name}' is declared more than once"
            )
        seen_alias_names.add(alias_name)
        aliases_by_target.setdefault(of_name, []).append(alias_def)

    plugin_entries = []
    for plugin_dir, m in ordered:
        canonical = {
            "name": m["name"],
            "source": f"./plugins/{plugin_dir.name}",
            "description": m["description"],
            "version": version,
            "skills": list(m.get("skills", [])),
            "agents": list(m.get("agents", [])),
            "mcpServers": m.get("mcpServers", {}),
            "repository": repo_url,
            "keywords": list(m.get("keywords", [])),
            "license": m.get("license", "MIT"),
        }
        plugin_entries.append(canonical)
        for alias_def in aliases_by_target.get(m["name"], []):
            plugin_entries.append({
                **canonical,
                "name": alias_def["alias"],
                "description": alias_def.get("descriptionPrefix", "") + canonical["description"],
            })

    marketplace = {
        "name": config["name"],
        "metadata": {
            "description": config["metadata"]["description"],
            "version": version,
        },
        "owner": config["owner"],
        "plugins": plugin_entries,
    }
    return json.dumps(marketplace, indent=2) + "\n"


def write_marketplaces(content: str) -> None:
    for path in MARKETPLACE_FILES:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def purge_materialized() -> int:
    """Delete materialized content (skills/, agents/, common/, .mcp.json) from every
    plugins/<name>/ directory. Leaves manifests and marketplace files alone.

    Returns the number of paths removed.
    """
    removed = 0
    if not PLUGINS_DIR.exists():
        return 0
    for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
        if not plugin_dir.is_dir():
            continue
        for sub in ("skills", "agents", "common"):
            target = plugin_dir / sub
            if target.exists():
                shutil.rmtree(target)
                print(f"  removed: {target.relative_to(REPO_ROOT)}".replace("\\", "/"))
                removed += 1
        mcp = plugin_dir / ".mcp.json"
        if mcp.exists():
            mcp.unlink()
            print(f"  removed: {mcp.relative_to(REPO_ROOT)}".replace("\\", "/"))
            removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true", help="Delete materialized content before rebuilding.")
    parser.add_argument("--purge", action="store_true", help="Delete materialized content (skills/agents/common/.mcp.json) from every plugin and exit.")
    parser.add_argument("--check", action="store_true", help="Fail if marketplace files would change (CI gate).")
    args = parser.parse_args()

    if args.purge:
        removed = purge_materialized()
        print(f"\nPurged {removed} path(s). Manifests and marketplace files left untouched.")
        return 0

    manifests = load_manifests()
    if not manifests:
        print("No plugin manifests found under plugins/", file=sys.stderr)
        return 1

    all_issues: list[str] = []
    for plugin_dir, manifest in manifests:
        issues = build_plugin(plugin_dir, manifest, clean=args.clean)
        if issues:
            all_issues.extend(issues)
        else:
            print(f"  built: {plugin_dir.name}")

    if all_issues:
        print("\nBuild failed:", file=sys.stderr)
        for i in all_issues:
            print(f"  - {i}", file=sys.stderr)
        return 2

    # Generate marketplace files from manifests
    generated = generate_marketplace(manifests)

    if args.check:
        diffs: list[str] = []
        for path in MARKETPLACE_FILES:
            on_disk = path.read_text(encoding="utf-8") if path.exists() else ""
            if on_disk != generated:
                diffs.append(str(path.relative_to(REPO_ROOT)).replace("\\", "/"))
        if diffs:
            print("\n--check failed: marketplace files differ from generator output:", file=sys.stderr)
            for d in diffs:
                print(f"  - {d}", file=sys.stderr)
            print("\nRun `python build/build_plugins.py` and commit the changes.", file=sys.stderr)
            return 3
        print("  marketplace files in sync with manifests")
    else:
        write_marketplaces(generated)
        for path in MARKETPLACE_FILES:
            print(f"  wrote: {path.relative_to(REPO_ROOT)}".replace("\\", "/"))

    print(f"\nDone. {len(manifests)} plugins built.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
