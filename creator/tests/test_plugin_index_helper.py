"""Unit tests for the plugin-index helper in ``build/plugin_index.py``.

This helper replaces the previously-emitted ``plugins/manifest.json`` artifact.
It reads each per-plugin manifest at
``plugins/<name>/.github/plugin/plugin.json`` and returns a
``{plugin_name: [skill_name, ...]}`` mapping. The denormalized
``plugins/manifest.json`` file is no longer emitted or read by any consumer.

Run via:
    python -m unittest tests/test_plugin_index_helper.py -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = REPO_ROOT / "build"
PLUGINS_DIR = REPO_ROOT / "plugins"
MARKETPLACE_CONFIG = BUILD_DIR / "marketplace.config.json"

sys.path.insert(0, str(BUILD_DIR))
import plugin_index  # noqa: E402


def reference_index_from_disk() -> dict[str, list[str]]:
    """Recompute the expected plugin index from raw per-plugin manifests.

    Order: marketplace.config.json pluginOrder first (in declared order),
    then any plugin not listed there, sorted alphabetically. Skill order
    within a plugin preserves the manifest's ``skills`` array order.
    """
    config = json.loads(MARKETPLACE_CONFIG.read_text(encoding="utf-8"))
    order = config.get("pluginOrder", [])
    discovered: dict[str, list[str]] = {}
    for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
        if not plugin_dir.is_dir():
            continue
        manifest_path = plugin_dir / ".github" / "plugin" / "plugin.json"
        if not manifest_path.exists():
            continue
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        skills = []
        for s in m.get("skills", []):
            v = s.strip()
            if v.startswith("./"):
                v = v[2:]
            if v.startswith("skills/"):
                v = v[len("skills/"):]
            skills.append(v)
        discovered[m["name"]] = skills

    ordered_names: list[str] = []
    for name in order:
        if name in discovered and name not in ordered_names:
            ordered_names.append(name)
    for name in sorted(discovered):
        if name not in ordered_names:
            ordered_names.append(name)

    return {n: discovered[n] for n in ordered_names}


class PluginIndexHelperRepositoryTests(unittest.TestCase):
    """Catalog-level: helper matches the reference reconstruction from disk."""

    def test_helper_matches_reference(self):
        actual = plugin_index.load_plugin_index()
        expected = reference_index_from_disk()
        self.assertEqual(actual, expected)

    def test_helper_includes_all_configured_plugins(self):
        config = json.loads(MARKETPLACE_CONFIG.read_text(encoding="utf-8"))
        expected_names = set(config.get("pluginOrder", []))
        actual = plugin_index.load_plugin_index()
        missing = expected_names - set(actual.keys())
        self.assertEqual(missing, set(), f"index missing expected plugins: {missing}")

    def test_each_plugin_entry_is_list_of_strings(self):
        actual = plugin_index.load_plugin_index()
        for name, skills in actual.items():
            self.assertIsInstance(skills, list, f"plugin {name} skills is not a list")
            for s in skills:
                self.assertIsInstance(s, str, f"plugin {name} skill entry is not a string: {s!r}")

    def test_known_plugin_names_matches_keys(self):
        index = plugin_index.load_plugin_index()
        names = plugin_index.known_plugin_names()
        self.assertEqual(names, set(index.keys()))


class PluginIndexHelperUnitTests(unittest.TestCase):
    """Pure-helper checks against in-memory fake plugin trees."""

    def _make_plugin(self, root: Path, name: str, skills: list[str]) -> None:
        manifest_dir = root / name / ".github" / "plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text(
            json.dumps({"name": name, "skills": [f"./skills/{s}" for s in skills]}),
            encoding="utf-8",
        )

    def test_empty_plugins_dir_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(plugin_index.load_plugin_index(Path(tmp)), {})

    def test_strips_skills_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_plugin(root, "plugin-a", ["skill-x", "skill-y"])
            index = plugin_index.load_plugin_index(root)
            self.assertEqual(index, {"plugin-a": ["skill-x", "skill-y"]})

    def test_uses_manifest_name_not_folder_name(self):
        # Folder is "wrong-folder" but manifest name is "actual-name".
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_dir = root / "wrong-folder" / ".github" / "plugin"
            manifest_dir.mkdir(parents=True)
            (manifest_dir / "plugin.json").write_text(
                json.dumps({"name": "actual-name", "skills": ["./skills/foo"]}),
                encoding="utf-8",
            )
            index = plugin_index.load_plugin_index(root)
            self.assertEqual(list(index.keys()), ["actual-name"])

    def test_plugin_order_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_plugin(root, "alpha", [])
            self._make_plugin(root, "beta", [])
            self._make_plugin(root, "gamma", [])
            # Config places gamma first, then alpha; beta should fall to sorted remainder.
            cfg = root / "marketplace.config.json"
            cfg.write_text(json.dumps({"pluginOrder": ["gamma", "alpha"]}), encoding="utf-8")
            index = plugin_index.load_plugin_index(root, cfg)
            self.assertEqual(list(index.keys()), ["gamma", "alpha", "beta"])

    def test_skips_manifests_with_missing_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_plugin(root, "good", ["s"])
            bad_dir = root / "bad" / ".github" / "plugin"
            bad_dir.mkdir(parents=True)
            (bad_dir / "plugin.json").write_text(json.dumps({"skills": []}), encoding="utf-8")
            index = plugin_index.load_plugin_index(root)
            self.assertEqual(list(index.keys()), ["good"])

    def test_skips_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_plugin(root, "good", ["s"])
            bad_dir = root / "bad" / ".github" / "plugin"
            bad_dir.mkdir(parents=True)
            (bad_dir / "plugin.json").write_text("not json", encoding="utf-8")
            index = plugin_index.load_plugin_index(root)
            self.assertEqual(list(index.keys()), ["good"])

    def test_skill_order_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_plugin(root, "p", ["z", "a", "m"])
            index = plugin_index.load_plugin_index(root)
            self.assertEqual(index["p"], ["z", "a", "m"])


if __name__ == "__main__":
    unittest.main()
