"""Unit tests for ``.github/scripts/check_instruction_lengths.py``.

Tests use a tmp_path to isolate from the real repo, exercising:
- empty repo (no instruction files) -> exit 0 with warning to stderr
- all files under limit -> exit 0
- one file exactly at the limit (4000 chars) -> exit 0
- one file 1 char over (4001 chars) -> exit 1
- file within 200 chars of limit -> exit 0 with WARN status

Run with:
    python -m unittest tests/test_check_instruction_lengths.py -v
"""
from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / ".github" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import check_instruction_lengths as checker  # noqa: E402


def _make_repo(tmp: Path, files: dict[str, int]) -> Path:
    """Create a fake repo layout with instruction files of the given char counts."""
    (tmp / ".github" / "instructions").mkdir(parents=True, exist_ok=True)
    for relpath, char_count in files.items():
        target = tmp / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("a" * char_count, encoding="utf-8")
    return tmp


class CheckInstructionLengthsTests(unittest.TestCase):
    def _run(self, repo: Path) -> tuple[int, str, str]:
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            exit_code = checker.main([str(repo)])
        return exit_code, out_buf.getvalue(), err_buf.getvalue()

    def test_no_files_returns_zero_with_warning(self):
        with TemporaryDirectory() as td:
            repo = Path(td)
            (repo / ".github").mkdir()
            code, _stdout, stderr = self._run(repo)
            self.assertEqual(code, 0)
            self.assertIn("no instruction files found", stderr)

    def test_all_files_under_limit_passes(self):
        with TemporaryDirectory() as td:
            repo = _make_repo(Path(td), {
                ".github/instructions/foo.instructions.md": 1000,
                ".github/instructions/bar.instructions.md": 2000,
                ".github/copilot-instructions.md": 500,
            })
            code, stdout, _stderr = self._run(repo)
            self.assertEqual(code, 0)
            self.assertIn("OK", stdout)

    def test_file_exactly_at_limit_passes(self):
        with TemporaryDirectory() as td:
            repo = _make_repo(Path(td), {
                ".github/instructions/edge.instructions.md": 4000,
            })
            code, stdout, _stderr = self._run(repo)
            self.assertEqual(code, 0)

    def test_file_one_over_limit_fails(self):
        with TemporaryDirectory() as td:
            repo = _make_repo(Path(td), {
                ".github/instructions/over.instructions.md": 4001,
            })
            code, stdout, _stderr = self._run(repo)
            self.assertEqual(code, 1)
            self.assertIn("FAIL", stdout)
            self.assertIn("over.instructions.md", stdout)

    def test_file_near_limit_warns_but_passes(self):
        with TemporaryDirectory() as td:
            repo = _make_repo(Path(td), {
                ".github/instructions/near.instructions.md": 3900,  # within 200 of 4000
            })
            code, stdout, _stderr = self._run(repo)
            self.assertEqual(code, 0)
            self.assertIn("WARN", stdout)

    def test_mixed_files_one_over_fails(self):
        with TemporaryDirectory() as td:
            repo = _make_repo(Path(td), {
                ".github/instructions/ok.instructions.md": 1000,
                ".github/instructions/over.instructions.md": 5000,
                ".github/copilot-instructions.md": 2000,
            })
            code, stdout, _stderr = self._run(repo)
            self.assertEqual(code, 1)
            self.assertIn("over.instructions.md", stdout)
            self.assertIn("1000", stdout)  # FAIL+1000

    def test_nonexistent_repo_path_returns_2(self):
        code, _stdout, stderr = self._run(Path("/nonexistent/repo/path"))
        self.assertEqual(code, 2)
        self.assertIn("not a directory", stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
