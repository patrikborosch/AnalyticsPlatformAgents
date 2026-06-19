#!/usr/bin/env python3
"""Compute which tests in ``tests/tests.json`` changed between two revisions.

Used by ``fabric-smoke-pr-touched.yml``'s detect step. When a PR touches
``tests/tests.json``, we want to run ONLY the test entries that actually
changed (added or modified) rather than the entire 48-entry catalog. This
matches the test scope to the change scope, reduces tenant capacity
contention, and produces a cleaner PR comment.

Behavior
--------
- Reads two revisions of ``tests/tests.json``: ``--base`` (e.g. the PR's
  merge-base on main) and ``--head`` (the PR HEAD's version).
- Returns the **names** of tests where the entry's JSON content differs
  between the two revisions, treating ADDED entries as "changed" too.
- DELETED entries are NOT in the result -- the test no longer exists so
  there's nothing to run.
- If either file is missing or unparseable, exits 2 with an error message;
  the caller is expected to fall back to running the full catalog.

Output format
-------------
Comma-separated test names on stdout (e.g. ``activator-authoring-create-basic,
activator-authoring-notify-me-routing``). Empty stdout means no test entries
changed.

Exit codes
----------
- 0 on success (including "no changes detected", which prints nothing)
- 2 on usage / parse errors
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def changed_test_names(base_tests: list[dict], head_tests: list[dict]) -> list[str]:
    """Return names of test entries that were ADDED or MODIFIED between base and head.

    Deletion (a name present in base but missing from head) is NOT returned: the
    test is gone, so the caller cannot run it. The caller's other path-filter
    logic (touched skills) still covers tests that match those skills.

    Entries with no ``name`` field are ignored (defensive; ``tests.json`` schema
    requires ``name``, but we don't want to crash on a malformed entry).
    """
    base_by_name = {t["name"]: t for t in base_tests if isinstance(t, dict) and t.get("name")}
    head_by_name = {t["name"]: t for t in head_tests if isinstance(t, dict) and t.get("name")}

    changed: list[str] = []
    for name, head_entry in head_by_name.items():
        base_entry = base_by_name.get(name)
        if base_entry != head_entry:
            # Either added (base_entry is None) or modified
            changed.append(name)
    return changed


def load_tests_json(path: Path) -> list[dict]:
    """Load a ``tests.json`` file. Returns the list of test entries.

    Raises ValueError on parse errors or unexpected root types.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"failed to parse {path}: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError(f"{path}: root is not a list")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="Path to base-revision tests.json")
    parser.add_argument("--head", type=Path, required=True, help="Path to head-revision tests.json")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.base.is_file():
        print(f"ERROR: base file not found: {args.base}", file=sys.stderr)
        return 2
    if not args.head.is_file():
        print(f"ERROR: head file not found: {args.head}", file=sys.stderr)
        return 2

    try:
        base_tests = load_tests_json(args.base)
        head_tests = load_tests_json(args.head)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    changed = changed_test_names(base_tests, head_tests)
    if changed:
        print(",".join(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
