#!/usr/bin/env python3
"""Report the character length of every custom instruction file used by Copilot code review.

Why this matters
----------------
Per https://docs.github.com/en/copilot/tutorials/customize-code-review, Copilot
code review only reads the first 4,000 CHARACTERS of any custom instruction
file. Anything beyond is silently dropped. This is a hard ceiling, not a
warning -- a long file is functionally truncated and the trailing rules become
invisible to Copilot reviewers.

The script reports each file's:

- Character count (Python ``len()``, which equals UTF-16 code units / .NET
  ``String.Length`` for pure-ASCII content -- our convention)
- Byte count (UTF-8 encoded; for ASCII matches the char count)
- Line count

Exit behaviour
--------------
- Exit 0 if every file is at or under the 4,000-character limit.
- Exit 1 if any file exceeds the limit. The script prints a per-file table
  AND a one-line "FAIL" verdict so the CI log clearly shows what to trim.

Files checked
-------------
- ``.github/copilot-instructions.md`` (repository-wide)
- ``.github/instructions/*.instructions.md`` (path-specific)

Usage
-----
::

    python .github/scripts/check_instruction_lengths.py           # cwd is the repo
    python .github/scripts/check_instruction_lengths.py <path>    # explicit repo path
"""
from __future__ import annotations

import sys
from pathlib import Path

LIMIT = 4000
# Soft warning threshold: files within 200 chars of the hard limit print a
# notice so future edits have a buffer to add a single bullet without going
# over. Not failure-causing.
SOFT_THRESHOLD = LIMIT - 200


def collect_files(repo: Path) -> list[Path]:
    instr_dir = repo / ".github" / "instructions"
    copilot_file = repo / ".github" / "copilot-instructions.md"
    files: list[Path] = []
    if instr_dir.is_dir():
        files.extend(sorted(instr_dir.glob("*.instructions.md")))
    if copilot_file.is_file():
        files.append(copilot_file)
    return files


def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    repo = Path(argv[0]) if argv else Path.cwd()
    if not repo.is_dir():
        print(f"ERROR: not a directory: {repo}", file=sys.stderr)
        return 2

    files = collect_files(repo)
    if not files:
        print(f"WARNING: no instruction files found under {repo}/.github/", file=sys.stderr)
        return 0

    over: list[tuple[Path, int]] = []
    warn: list[tuple[Path, int]] = []

    print(f"\n{'File':45s} {'chars':>8s} {'bytes':>8s} {'lines':>6s} {'status':>10s}")
    print("-" * 80)
    for p in files:
        text = p.read_text(encoding="utf-8")
        char_count = len(text)
        byte_count = len(text.encode("utf-8"))
        line_count = text.count("\n") + (0 if text.endswith("\n") else 1)
        if char_count > LIMIT:
            status = f"FAIL+{char_count - LIMIT}"
            over.append((p, char_count))
        elif char_count > SOFT_THRESHOLD:
            status = f"WARN-{LIMIT - char_count}"
            warn.append((p, char_count))
        else:
            status = "OK"
        rel = p.relative_to(repo) if p.is_relative_to(repo) else p
        print(f"{str(rel):45s} {char_count:>8d} {byte_count:>8d} {line_count:>6d} {status:>10s}")

    print()
    if over:
        print(f"FAIL: {len(over)} file(s) exceed the {LIMIT}-char Copilot code review limit.")
        print(f"  Copilot reads only the first {LIMIT} characters; rules beyond are silently dropped.")
        print(f"  See https://docs.github.com/en/copilot/tutorials/customize-code-review")
        for p, n in over:
            rel = p.relative_to(repo) if p.is_relative_to(repo) else p
            print(f"  - {rel}: {n} chars, {n - LIMIT} over")
        return 1
    if warn:
        print(f"OK with warnings: {len(warn)} file(s) are within 200 chars of the limit.")
        print(f"  Future edits may push these over; consider trimming proactively.")
        for p, n in warn:
            rel = p.relative_to(repo) if p.is_relative_to(repo) else p
            print(f"  - {rel}: {n} chars, {LIMIT - n} remaining")
    else:
        print("OK: all instruction files are well within the 4000-char limit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
