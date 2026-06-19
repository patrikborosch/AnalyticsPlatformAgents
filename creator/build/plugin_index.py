"""Read the plugin-to-skills index directly from per-plugin manifests.

This module replaces the previously-emitted ``plugins/manifest.json``
denormalized artifact. The single source of truth for "which skills ship
inside plugin X" is now ``plugins/<name>/.github/plugin/plugin.json``.

Consumers (build tooling, smoke detector, tests, runners) should call
``load_plugin_index()`` instead of reading a generated index file. The
denormalized index introduced drift risk: every per-plugin manifest edit
required a separate `build/build_plugins.py` step to regenerate
``plugins/manifest.json``, and CI had to gate on drift. Reading directly
from the per-plugin manifests removes both the artifact and the drift gate.

Plugin emission order matches the order used by ``build_plugins.py`` for
marketplace generation: any names in ``build/marketplace.config.json``'s
``pluginOrder`` come first (in declared order), then the remainder
alphabetically. This keeps any consumer that iterates the index in a stable
order without re-deriving the rule.

Run as a script for a quick sanity check:
    python build/plugin_index.py
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
MARKETPLACE_CONFIG = REPO_ROOT / "build" / "marketplace.config.json"
MANIFEST_REL = Path(".github") / "plugin" / "plugin.json"


def _strip_skills_prefix(value: str) -> str:
    """Strip a leading ``./skills/`` (or ``skills/``) from a manifest reference.

    Per-plugin manifests reference skills via paths like
    ``./skills/<skill-name>``; consumers want just the trailing folder name.
    """
    v = value.strip()
    if v.startswith("./"):
        v = v[2:]
    if v.startswith("skills/"):
        v = v[len("skills/"):]
    return v


def _load_plugin_order(config_path: Path | None = None) -> list[str]:
    """Return ``pluginOrder`` from marketplace.config.json, or an empty list."""
    path = config_path or MARKETPLACE_CONFIG
    if not path.is_file():
        return []
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    order = cfg.get("pluginOrder", [])
    return list(order) if isinstance(order, list) else []


def load_plugin_index(
    plugins_dir: Path | None = None,
    config_path: Path | None = None,
) -> dict[str, list[str]]:
    """Return ``{plugin_name: [skill_name, ...]}`` derived from per-plugin manifests.

    - Plugin name comes from each manifest's ``name`` field (NOT the folder
      name, which may differ in theory and would silently drift).
    - Skill order within a plugin follows the manifest's ``skills`` array order.
    - Plugin emission order: any names in ``pluginOrder`` first (in declared
      order), then the rest alphabetically. Empty dict if ``plugins/`` is
      missing or no manifests are found.
    """
    root = plugins_dir or PLUGINS_DIR
    discovered: dict[str, list[str]] = {}
    if not root.is_dir():
        return discovered

    for plugin_dir in sorted(root.iterdir()):
        if not plugin_dir.is_dir():
            continue
        manifest_path = plugin_dir / MANIFEST_REL
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = manifest.get("name")
        if not isinstance(name, str) or not name:
            continue
        skills = [
            _strip_skills_prefix(s)
            for s in manifest.get("skills", [])
            if isinstance(s, str)
        ]
        discovered[name] = skills

    order = _load_plugin_order(config_path)
    ordered_names: list[str] = []
    for name in order:
        if name in discovered and name not in ordered_names:
            ordered_names.append(name)
    for name in sorted(discovered):
        if name not in ordered_names:
            ordered_names.append(name)

    return {name: discovered[name] for name in ordered_names}


def known_plugin_names(
    plugins_dir: Path | None = None,
    config_path: Path | None = None,
) -> set[str]:
    """Return the set of known plugin names (from each manifest's ``name``)."""
    return set(load_plugin_index(plugins_dir, config_path).keys())


if __name__ == "__main__":
    import sys

    index = load_plugin_index()
    if not index:
        print("No plugin manifests found under plugins/", file=sys.stderr)
        sys.exit(1)
    print(json.dumps({"plugins": {n: {"skills": s} for n, s in index.items()}}, indent=2))
