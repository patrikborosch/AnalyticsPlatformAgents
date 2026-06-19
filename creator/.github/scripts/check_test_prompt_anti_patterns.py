#!/usr/bin/env python3
"""Reject test prompts that explicitly name a skill folder.

ANTI-PATTERN being prevented
----------------------------
A `tests/tests.json` entry whose `prompt` reads like::

    Using the activator-authoring-cli skill, create an Activator named ...

Naming a skill by its folder name in the prompt short-circuits the very
thing the smoke catalog is supposed to verify -- that the skill's
`description` / triggers route correctly for natural user phrasings.
Real users phrase requests as ``Create an Activator named X``, not
``Using the activator-authoring-cli skill, create ...``. If a prompt
only routes because we hand-named the skill, the routing test becomes
self-fulfilling and a regression in the skill's description goes
unnoticed.

The right fix when a test prompt fails to route is on the skill side
(strengthen the skill's `description`, add disambiguation triggers), not
on the prompt side (hand-name the skill).

Detection
---------
Two ingredients must combine for a finding:

1. A verb-of-invocation pattern (case-insensitive): ``using``, ``use``,
   ``via``, ``through``, ``invoke``, optionally followed by ``the``.
2. Immediately followed by a token that matches an existing
   ``skills/<name>/`` folder name + the literal word ``skill``.

Both conditions are required, which keeps false positives low: a prompt
mentioning the skill name in passing (e.g. discussing it as a topic) but
without a verb-of-invocation does NOT trigger.

Exit codes
----------
* 0 -- no violations
* 1 -- one or more violations (each printed to stderr with file:line context)
* 2 -- internal error (e.g. tests.json missing / unparseable)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TESTS_JSON = REPO_ROOT / "tests" / "tests.json"
DEFAULT_SKILLS_DIR = REPO_ROOT / "skills"


VERB_OF_INVOCATION = r"(?:using|use|via|through|invoke)"
# Skill-folder shape per CONTRIBUTING.md: <endpoint>-<authoring|consumption|operations>-cli
SKILL_NAME_SHAPE = r"[a-z][a-z0-9-]*-(?:authoring|consumption|operations)-cli"
ANTI_PATTERN_REGEX = re.compile(
    rf"\b{VERB_OF_INVOCATION}\s+(?:the\s+)?(?P<skill>{SKILL_NAME_SHAPE})\s+skill\b",
    re.IGNORECASE,
)


def load_skill_folders(skills_dir: Path) -> set[str]:
    """Return the set of skill folder names directly under ``skills/``.

    Anything that isn't a directory (e.g. README files at the top level) is
    skipped. The set is used to cross-reference matches: a verb-of-invocation
    pattern that names a skill not in this set is left alone (could be a
    typo or a deprecated name -- not this check's responsibility).
    """
    if not skills_dir.is_dir():
        return set()
    return {p.name for p in skills_dir.iterdir() if p.is_dir()}


def find_violations(
    tests_json: list[dict[str, Any]],
    skill_folders: set[str],
) -> list[dict[str, Any]]:
    """Scan every entry's ``prompt`` and return all anti-pattern matches.

    Returns one dict per match (so a prompt with two distinct anti-patterns
    yields two violations).
    """
    violations: list[dict[str, Any]] = []
    for entry in tests_json:
        prompt = entry.get("prompt") or ""
        if not isinstance(prompt, str):
            continue
        for match in ANTI_PATTERN_REGEX.finditer(prompt):
            matched_skill = match.group("skill").lower()
            if matched_skill not in skill_folders:
                # Skill name doesn't correspond to a real folder; not our
                # check's concern. Other validators handle reference rot.
                continue
            violations.append({
                "name": entry.get("name", "<unnamed>"),
                "prompt": prompt,
                "matched_phrase": match.group(0),
                "matched_skill": matched_skill,
                "position": match.start(),
            })
    return violations


def format_violation(v: dict[str, Any]) -> str:
    """Format a single violation for stderr / CI log consumption."""
    return (
        f"  - test '{v['name']}': prompt names skill '{v['matched_skill']}' explicitly\n"
        f"    matched phrase: '{v['matched_phrase']}'\n"
        f"    prompt preview: '{v['prompt'][:200]}{'...' if len(v['prompt']) > 200 else ''}'"
    )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tests-json",
        type=Path,
        default=DEFAULT_TESTS_JSON,
        help="Path to tests/tests.json (default: %(default)s)",
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=DEFAULT_SKILLS_DIR,
        help="Path to skills/ directory used to cross-reference matches (default: %(default)s)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.tests_json.is_file():
        print(f"ERROR: tests.json not found at {args.tests_json}", file=sys.stderr)
        return 2

    try:
        tests_json = json.loads(args.tests_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: tests.json is not valid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(tests_json, list):
        print(f"ERROR: tests.json root is not a list", file=sys.stderr)
        return 2

    skill_folders = load_skill_folders(args.skills_dir)
    if not skill_folders:
        print(
            f"WARNING: no skill folders found under {args.skills_dir}; "
            "anti-pattern check requires the cross-reference and cannot proceed.",
            file=sys.stderr,
        )
        return 2

    violations = find_violations(tests_json, skill_folders)
    if not violations:
        print(f"OK: no skill-name anti-patterns found in {len(tests_json)} test prompts.")
        return 0

    print(f"\nANTI-PATTERN FOUND: {len(violations)} test prompt(s) explicitly name a skill folder.\n", file=sys.stderr)
    for v in violations:
        print(format_violation(v), file=sys.stderr)
        print(file=sys.stderr)
    print(
        "Why this is a problem:\n"
        "  Prompts that name a skill explicitly (e.g. 'Using the X skill, do Y')\n"
        "  short-circuit skill-routing testing. The smoke catalog then stops\n"
        "  verifying that the skill's description + triggers route correctly\n"
        "  for natural user phrasings.\n"
        "\n"
        "How to fix:\n"
        "  1. Rewrite the prompt as a real user would phrase it (drop the\n"
        "     'Using the X skill' prefix).\n"
        "  2. If the agent then fails to route to the intended skill, the\n"
        "     fix is on the skill side: strengthen the skill's `description`\n"
        "     field and/or add disambiguation triggers in SKILL.md.\n"
        "\n"
        "See .github/instructions/tests.instructions.md, 'Prompt anti-patterns'\n"
        "section for the full rule + rationale.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
