"""Unit tests for ``.github/scripts/diff_changed_test_names.py``.

Run with: python -m unittest tests/test_diff_changed_test_names.py -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / ".github" / "scripts"
sys.path.insert(0, str(SCRIPT_PATH))

import diff_changed_test_names as differ  # noqa: E402


class ChangedTestNamesTests(unittest.TestCase):
    def test_no_changes_returns_empty(self):
        tests = [{"name": "a", "prompt": "p"}, {"name": "b", "prompt": "q"}]
        self.assertEqual(differ.changed_test_names(tests, tests), [])

    def test_added_entry_is_returned(self):
        base = [{"name": "a", "prompt": "p"}]
        head = [{"name": "a", "prompt": "p"}, {"name": "b", "prompt": "q"}]
        self.assertEqual(differ.changed_test_names(base, head), ["b"])

    def test_modified_prompt_is_returned(self):
        base = [{"name": "a", "prompt": "old"}]
        head = [{"name": "a", "prompt": "new"}]
        self.assertEqual(differ.changed_test_names(base, head), ["a"])

    def test_modified_expected_results_is_returned(self):
        base = [{"name": "a", "prompt": "p", "expectedResults": ["x"]}]
        head = [{"name": "a", "prompt": "p", "expectedResults": ["x", "y"]}]
        self.assertEqual(differ.changed_test_names(base, head), ["a"])

    def test_modified_expected_skills_is_returned(self):
        base = [{"name": "a", "prompt": "p", "expectedSkills": ["s1"]}]
        head = [{"name": "a", "prompt": "p", "expectedSkills": ["s2"]}]
        self.assertEqual(differ.changed_test_names(base, head), ["a"])

    def test_deleted_entry_is_not_returned(self):
        # A test removed from head is gone -- we can't run it. Return empty.
        base = [{"name": "a", "prompt": "p"}, {"name": "b", "prompt": "q"}]
        head = [{"name": "a", "prompt": "p"}]
        self.assertEqual(differ.changed_test_names(base, head), [])

    def test_field_order_doesnt_trigger_change(self):
        # JSON parse should normalise; field-order shouldn't appear as a change.
        base = [{"name": "a", "prompt": "p", "area": "x"}]
        head = [{"area": "x", "prompt": "p", "name": "a"}]
        self.assertEqual(differ.changed_test_names(base, head), [])

    def test_mixed_add_modify_delete(self):
        base = [
            {"name": "keep-same", "prompt": "p1"},
            {"name": "modify-me", "prompt": "old"},
            {"name": "delete-me", "prompt": "gone"},
        ]
        head = [
            {"name": "keep-same", "prompt": "p1"},
            {"name": "modify-me", "prompt": "new"},
            {"name": "added", "prompt": "fresh"},
        ]
        result = differ.changed_test_names(base, head)
        self.assertEqual(sorted(result), sorted(["modify-me", "added"]))

    def test_entry_without_name_is_ignored(self):
        base = [{"prompt": "no-name"}, {"name": "a", "prompt": "p"}]
        head = [{"name": "a", "prompt": "p"}]
        # Defensively skip the no-name entry; net result: nothing changed.
        self.assertEqual(differ.changed_test_names(base, head), [])

    def test_empty_inputs_return_empty(self):
        self.assertEqual(differ.changed_test_names([], []), [])
        self.assertEqual(differ.changed_test_names([{"name": "a"}], []), [])
        self.assertEqual(differ.changed_test_names([], [{"name": "a"}]), ["a"])


class LoadTestsJsonTests(unittest.TestCase):
    def _write(self, tmp: Path, name: str, content: str) -> Path:
        p = tmp / name
        p.write_text(content, encoding="utf-8")
        return p

    def test_valid_json_loads_as_list(self):
        with TemporaryDirectory() as td:
            p = self._write(Path(td), "t.json", '[{"name": "a"}]')
            self.assertEqual(differ.load_tests_json(p), [{"name": "a"}])

    def test_malformed_json_raises(self):
        with TemporaryDirectory() as td:
            p = self._write(Path(td), "t.json", "{not json")
            with self.assertRaises(ValueError):
                differ.load_tests_json(p)

    def test_root_is_dict_raises(self):
        with TemporaryDirectory() as td:
            p = self._write(Path(td), "t.json", '{"name": "a"}')
            with self.assertRaises(ValueError):
                differ.load_tests_json(p)


class MainCliTests(unittest.TestCase):
    def test_missing_base_returns_2(self):
        with TemporaryDirectory() as td:
            head = Path(td) / "head.json"
            head.write_text("[]", encoding="utf-8")
            base = Path(td) / "nonexistent.json"
            rc = differ.main(["--base", str(base), "--head", str(head)])
            self.assertEqual(rc, 2)

    def test_unparseable_head_returns_2(self):
        with TemporaryDirectory() as td:
            base = Path(td) / "base.json"
            head = Path(td) / "head.json"
            base.write_text("[]", encoding="utf-8")
            head.write_text("not json", encoding="utf-8")
            rc = differ.main(["--base", str(base), "--head", str(head)])
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
