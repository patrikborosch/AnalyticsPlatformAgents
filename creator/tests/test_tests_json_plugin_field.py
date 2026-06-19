"""Unit tests for the optional ``plugin`` field in ``tests/tests.json``.

The ``plugin`` field tells the smoke runner and full-eval runner which plugin
to install before running a given test. It is optional; tests without the
field default to ``fabric-skills`` (the catch-all bundle).

Schema:
- omitted          -> defaults to ["fabric-skills"]
- string           -> treated as [<string>]
- list[str]        -> as-is

A non-existent plugin name fails validation. The set of known plugin names is
read directly from each per-plugin manifest at
``plugins/<name>/.github/plugin/plugin.json`` via ``build.plugin_index``.
(There is no longer a denormalized ``plugins/manifest.json`` artifact.)

Run via:
    python -m unittest tests/test_tests_json_plugin_field.py -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_JSON = REPO_ROOT / "tests" / "tests.json"
BUILD_DIR = REPO_ROOT / "build"

sys.path.insert(0, str(BUILD_DIR))
import plugin_index  # noqa: E402

DEFAULT_PLUGIN = "fabric-skills"


def normalize_plugin_field(value):
    """Normalize the ``plugin`` field to a list of plugin name strings.

    - None / missing -> [DEFAULT_PLUGIN]
    - str -> [str]
    - list[str] -> list[str]
    - anything else -> raises TypeError
    """
    if value is None:
        return [DEFAULT_PLUGIN]
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        if not all(isinstance(v, str) for v in value):
            raise TypeError(f"plugin list must contain strings only, got: {value!r}")
        if not value:
            raise ValueError("plugin list must not be empty")
        return list(value)
    raise TypeError(f"plugin field must be string or list[str], got: {type(value).__name__}")


def load_known_plugins() -> set:
    """Read the set of known plugin names directly from per-plugin manifests.

    Per-plugin manifests at ``plugins/<name>/.github/plugin/plugin.json`` are
    the committed source of truth and are always present in any checkout that
    has the ``plugins/`` tree.
    """
    return plugin_index.known_plugin_names()


class NormalizePluginFieldTests(unittest.TestCase):
    """Unit-level checks on the schema normalizer."""

    def test_missing_defaults_to_fabric_skills(self):
        self.assertEqual(normalize_plugin_field(None), [DEFAULT_PLUGIN])

    def test_string_is_wrapped(self):
        self.assertEqual(normalize_plugin_field("fabric-authoring"), ["fabric-authoring"])

    def test_list_passes_through(self):
        self.assertEqual(
            normalize_plugin_field(["fabric-authoring", "fabric-consumption"]),
            ["fabric-authoring", "fabric-consumption"],
        )

    def test_empty_list_rejected(self):
        with self.assertRaises(ValueError):
            normalize_plugin_field([])

    def test_non_string_list_rejected(self):
        with self.assertRaises(TypeError):
            normalize_plugin_field([1, 2, 3])

    def test_wrong_type_rejected(self):
        with self.assertRaises(TypeError):
            normalize_plugin_field({"plugin": "fabric-skills"})


class TestsJsonPluginFieldValidationTests(unittest.TestCase):
    """Catalog-level check: every plugin name in tests.json must be real.

    Fails loudly (not skipped) when no per-plugin manifests are discoverable,
    because the manifests are the committed source of truth -- a missing
    plugin tree is a repository-corruption signal, not an expected condition.
    """

    @classmethod
    def setUpClass(cls):
        cls.tests = json.loads(TESTS_JSON.read_text(encoding="utf-8"))
        cls.known_plugins = load_known_plugins()
        if not cls.known_plugins:
            raise AssertionError(
                "No per-plugin manifests discovered under plugins/*/.github/plugin/plugin.json. "
                "The plugin tree is required and must be present in the checkout."
            )

    def test_every_test_plugin_field_is_known(self):
        unknown = []
        for entry in self.tests:
            name = entry.get("name", "<unnamed>")
            raw = entry.get("plugin")
            try:
                plugins = normalize_plugin_field(raw)
            except (TypeError, ValueError) as exc:
                unknown.append((name, f"invalid field: {exc}"))
                continue
            for p in plugins:
                if p not in self.known_plugins:
                    unknown.append((name, f"unknown plugin '{p}'"))
        self.assertEqual(
            unknown, [],
            f"tests.json entries reference unknown plugin(s): {unknown}",
        )

    def test_default_is_fabric_skills_when_omitted(self):
        # Defensive: if defaults ever change, this test forces a deliberate
        # update rather than silent drift.
        self.assertEqual(normalize_plugin_field(None), ["fabric-skills"])


if __name__ == "__main__":
    unittest.main()

