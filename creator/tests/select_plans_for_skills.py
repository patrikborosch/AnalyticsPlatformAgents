#!/usr/bin/env python3
"""
Map touched skills (from a PR's changed files) to the full-eval plan files
that exercise them.

Used by .github/workflows/fabric-full-eval-pr-touched.yml to decide which
plans to feed into the run-full-tests.ps1 -PlanFilter param. The orchestrator
workflow auto-runs on every PR that touches a covered skill (no label
required); fork PRs from non-write contributors are gated by GitHub-native
"Approve and run workflows", same trust model as smoke. This helper is
restored from the base branch by the orchestrator before being executed,
so a PR cannot tamper with the gate logic itself.

Reuses indexing primitives from coverage_gap_report.py:
- Individual plans (03-individual-skills/eval-*.md) carry `- **Skill:** ` + backtick + skill-name + backtick
  metadata that maps the plan to a single skill folder.
- Combined plans (04-combined-skills/eval-*.md) participate when any of
  their named skills (anywhere in the body) matches a touched skill.

Skipping is done at orchestrator level (no eval coverage -> don't run an
unrelated sanity plan); see Phase A.x.4 design notes.

Outputs JSON to stdout with:
  {
    "matched_plans": [...basenames...],
    "participant_skills": {"<plan-basename>": [...skill-names...]},
    "unmatched_skills": [...skills the author DIRECTLY touched that have no eval plan...],
    "plugin_skills_without_eval": [...plugin-bundled skills lacking eval coverage,
                                     diagnostic-only, not author-visible warning...],
    "touched_skills": [...skills extracted from skills/<name>/ paths +
                       skills bundled by any touched plugin manifest...],
    "touched_plugins": [...plugin folder names from plugins/<name>/ paths...],
    "plugin_skills": [...skills derived from touched plugin manifests...],
    "infrastructure_change": false,
    "infrastructure_files": [...paths matching INFRA_PREFIXES...],
    "gate_scope_plans": [...plans exercising touched skills, computed even on
                          infra/run-all; PR-touched gate hard-fails only on these...],
    "all_known_plans": [...]
  }

When infrastructure_change=True (common/, tests/full-eval-tests/, or
build/build_plugins.py touched), plugin expansion is SKIPPED so the
output isn't polluted with plugin-bundled skills on a non-plugin
infra change. touched_skills then contains only direct skills/<name>/
edits, and plugin_skills is empty. matched_plans is also empty
(infra wins -> orchestrator runs all plans via empty plan-filter).

Usage:
    python tests/select_plans_for_skills.py --skills <csv>
    python tests/select_plans_for_skills.py --changed-files <path>
    cat changed_files.txt | python tests/select_plans_for_skills.py --changed-files -
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Import indexing helpers from the existing coverage_gap_report module so the
# detection logic stays consistent with the advisory coverage report.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from coverage_gap_report import (  # noqa: E402  (path adjust above)
    COMBINED_EVALS_DIR,
    INDIVIDUAL_EVALS_DIR,
    REPO_ROOT,
    SKILLS_DIR,
    discover_skills,
    extract_individual_eval_skill,
)


# Note: coverage_gap_report wraps sys.stdout/stderr at import time on win32,
# so we deliberately skip wrapping again here (double-wrap raises "I/O
# operation on closed file." when the first wrapper's __del__ fires).


# Paths within the repo that, when touched, must escalate to "run all plans"
# because the change can affect every skill's runtime behavior. Keep this
# list narrow -- "true infrastructure" only. `plugins/<name>/...` changes
# are handled separately: they don't escalate to run-all, they expand to
# the skills listed in the touched plugin's manifest (see
# expand_plugin_changes_to_skills below). This avoids the cost-spam case
# where a single-plugin-manifest PR forced the full ~35-plan suite to run
# (~3-4h on the shared-tenant capacity), blocking the queue for everyone.
INFRA_PREFIXES = (
    "common/",
    "tests/full-eval-tests/",
    "build/build_plugins.py",
)

# Paths matching this prefix are NOT classified as infrastructure (they do
# not trigger run-all). Instead, the touched plugin's current manifest is
# read and the listed skills are added to the touched-skills set so they
# flow through the existing per-skill plan mapping.
PLUGIN_PREFIX_PATTERN = re.compile(r"^plugins/([^/]+)/")

# Individual / combined eval *plan-file* edits are NOT infrastructure even
# though they live under the tests/full-eval-tests/ INFRA_PREFIX. A change to
# plan/03-individual-skills/eval-<x>.md or plan/04-combined-skills/eval-<x>.md
# affects only that plan and the skill(s) it exercises, so it must map to that
# skill's plans rather than escalating the entire ~35-plan suite to run-all
# (which dragged unrelated environmental bails into PR-touched gates). Other
# paths under tests/full-eval-tests/ (shared phases 00-02, runner helpers,
# data fixtures) remain infrastructure and still escalate.
EVAL_PLAN_PATH_PATTERN = re.compile(
    r"^tests/full-eval-tests/plan/(?:03-individual-skills|04-combined-skills)/(eval-[^/]+)\.md$"
)


def extract_touched_skills_from_paths(paths: list[str]) -> list[str]:
    """Return distinct skill folder names from `skills/<name>/...` paths."""
    out: list[str] = []
    seen: set[str] = set()
    pat = re.compile(r"^skills/([^/]+)/")
    for p in paths:
        m = pat.match(p.strip())
        if not m:
            continue
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def is_infrastructure_change(paths: list[str]) -> tuple[bool, list[str]]:
    """Return (is_infra, infra_files) for change-list classification.

    Individual / combined eval plan-file edits are excluded: they map to a
    specific skill's plans via EVAL_PLAN_PATH_PATTERN (see
    extract_skills_from_touched_plan_files) and must not escalate to run-all.
    """
    hits = [
        p
        for p in paths
        if any(p.strip().startswith(pref) for pref in INFRA_PREFIXES)
        and not EVAL_PLAN_PATH_PATTERN.match(p.strip())
    ]
    return (bool(hits), hits)


def extract_skills_from_touched_plan_files(
    paths: list[str], skill_names: list[str]
) -> tuple[list[str], list[str]]:
    """Map touched eval plan-file paths to the skill(s) they exercise.

    - Individual plan (03-individual-skills/eval-<x>.md): resolve via the
      ``**Skill:**`` metadata line (extract_individual_eval_skill).
    - Combined plan (04-combined-skills/eval-<x>.md): any discovered skill
      whose folder name appears in the plan body participates (mirrors the
      combined-index logic in build_plan_index / coverage_gap_report).

    Returns ``(skills, unresolved_paths)``:
    - ``skills``: deduped, stable-ordered skill folder names resolved from the
      touched plan files.
    - ``unresolved_paths``: touched plan-file paths that resolved to NO known
      skill (missing/deleted file, broken ``**Skill:**`` metadata, a combined
      plan whose body names no known skill, or a malformed / non-UTF-8 plan
      file). The caller escalates these to an infrastructure (run-all) change
      so a broken plan-file edit does not silently skip eval.
    """
    out: list[str] = []
    seen: set[str] = set()
    unresolved: list[str] = []
    skill_set = set(skill_names)
    for p in paths:
        stripped = p.strip()
        m = EVAL_PLAN_PATH_PATTERN.match(stripped)
        if not m:
            continue
        basename = m.group(1)  # e.g. "eval-spark-authoring"
        if "/03-individual-skills/" in stripped:
            plan_path = INDIVIDUAL_EVALS_DIR / f"{basename}.md"
            if not plan_path.is_file():
                unresolved.append(stripped)
                continue
            # extract_individual_eval_skill reads the plan as UTF-8; guard both
            # OSError (race-deleted / permission) and UnicodeDecodeError (a
            # malformed / accidentally-binary plan file). Either way treat the
            # plan as unresolved so it escalates to run-all rather than crashing
            # the selector (which would fail the gate entirely).
            try:
                skill = extract_individual_eval_skill(plan_path)
            except (OSError, UnicodeDecodeError):
                unresolved.append(stripped)
                continue
            candidates = [skill] if skill else []
        else:
            plan_path = COMBINED_EVALS_DIR / f"{basename}.md"
            if not plan_path.is_file():
                unresolved.append(stripped)
                continue
            try:
                content = plan_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                unresolved.append(stripped)
                continue
            candidates = [s for s in skill_names if s in content]
        resolved_any = False
        for skill in candidates:
            if skill and skill in skill_set:
                resolved_any = True
                if skill not in seen:
                    seen.add(skill)
                    out.append(skill)
        if not resolved_any:
            unresolved.append(stripped)
    return out, unresolved


def extract_touched_plugins_from_paths(paths: list[str]) -> list[str]:
    """Return distinct plugin folder names from `plugins/<name>/...` paths.

    Example: paths = ["plugins/powerbi-authoring/.github/plugin/plugin.json"]
             -> ["powerbi-authoring"]
    """
    out: list[str] = []
    seen: set[str] = set()
    for p in paths:
        m = PLUGIN_PREFIX_PATTERN.match(p.strip())
        if not m:
            continue
        name = m.group(1)
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def expand_plugin_changes_to_skills(plugin_names: list[str], repo_root: Path) -> list[str]:
    """For each touched plugin, return the skill names listed in its manifest.

    Reads `plugins/<plugin>/.github/plugin/plugin.json` at HEAD and parses the
    `skills` array (entries like "./skills/<skill-name>"). Returns a deduped,
    stable-ordered list of skill folder names.

    Every skip path emits a stderr WARNING line so the GitHub Actions step
    log makes "why didn't my eval run?" answerable without reading source.
    The defensive read (never crashing) is what keeps the gate moving; the
    warnings are what make the silent-skip decision auditable.

    Edge cases (all warn to stderr):
    - Missing manifest (typo or pre-creation): skipped, warns. The plugin
      change still appears in touched_plugins for the orchestrator to log.
      Combined with the `force_run_all` signal in main(), a missing manifest
      on a touched plugin escalates to run-all (defensive).
    - Malformed JSON / OS error / UnicodeDecodeError: skipped, warns.
      Surfacing the parse error as a crash here would block the gate; the
      skill content itself would fail elsewhere (build, smoke).
    - Non-list `skills` field, or non-string entry: skipped, warns.
    - Entry doesn't match the documented `./skills/<name>` form (e.g. a
      contributor wrote `./skills/foo/SKILL.md`): skipped, warns. The
      manifest schema accepts only the folder form.
    - Skill removed from manifest between base and HEAD: we only see HEAD,
      so the removed skill's plans are NOT triggered. This is acceptable:
      removing a skill from a plugin does not change the skill's content,
      and the skill folder itself stays untouched.
    """
    plugins_dir = repo_root / "plugins"
    out: list[str] = []
    seen: set[str] = set()
    for plugin in plugin_names:
        manifest_path = plugins_dir / plugin / ".github" / "plugin" / "plugin.json"
        if not manifest_path.is_file():
            rel = manifest_path.relative_to(repo_root) if manifest_path.is_absolute() else manifest_path
            print(
                f"WARNING: plugin '{plugin}' has no manifest at {rel}; skipping "
                f"(plugin-bundled skills cannot be inferred).",
                file=sys.stderr,
            )
            continue
        # Defensive read: catch (a) JSON parse failures (malformed manifest),
        # (b) OS-level read errors (race-deleted file, permission), and
        # (c) UnicodeDecodeError (a contributor accidentally wrote bytes that
        # are not valid UTF-8). All three must be silent skips -- crashing
        # the selector would block the gate decision entirely. Each emits a
        # distinct stderr line so the failure mode is debuggable from logs.
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(
                f"WARNING: plugin '{plugin}' manifest is not valid JSON "
                f"({exc.__class__.__name__}: {exc}); skipping.",
                file=sys.stderr,
            )
            continue
        except UnicodeDecodeError as exc:
            print(
                f"WARNING: plugin '{plugin}' manifest is not valid UTF-8 "
                f"({exc.__class__.__name__}); skipping.",
                file=sys.stderr,
            )
            continue
        except OSError as exc:
            print(
                f"WARNING: plugin '{plugin}' manifest could not be read "
                f"({exc.__class__.__name__}: {exc}); skipping.",
                file=sys.stderr,
            )
            continue
        # Type-check the skills field BEFORE iterating: `manifest.get("skills",
        # []) or []` collapses None / empty list to [], but a wrong-type value
        # (string / dict / number) is truthy and would iterate, producing
        # garbage matches or crashing on dict iteration order changes. Reject
        # anything that isn't a list.
        entries = manifest.get("skills", [])
        if not isinstance(entries, list):
            print(
                f"WARNING: plugin '{plugin}' manifest 'skills' field is "
                f"{type(entries).__name__}, not list; skipping.",
                file=sys.stderr,
            )
            continue
        for entry in entries:
            if not isinstance(entry, str):
                print(
                    f"WARNING: plugin '{plugin}' manifest 'skills' entry "
                    f"{entry!r} is {type(entry).__name__}, not str; ignored.",
                    file=sys.stderr,
                )
                continue
            # Entries are "./skills/<name>" or similar. Reject file-form
            # (./skills/foo/SKILL.md) or sub-path forms -- the manifest
            # schema documents folder form only.
            m = re.match(r"^\.?/?skills/([^/]+)/?$", entry.strip())
            if not m:
                print(
                    f"WARNING: plugin '{plugin}' manifest 'skills' entry "
                    f"{entry!r} did not match expected './skills/<name>' "
                    f"folder form; ignored.",
                    file=sys.stderr,
                )
                continue
            name = m.group(1)
            if name not in seen:
                seen.add(name)
                out.append(name)
    return out


def build_plan_index(skill_names: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """Build a skill -> [plan-basenames] index across individual + combined plans.

    Returns:
      - plan_by_skill: {skill_name: [plan_basename, ...]}
      - all_known_plans: sorted list of every plan basename discovered on disk
    """
    plan_by_skill: dict[str, list[str]] = {s: [] for s in skill_names}
    all_known: set[str] = set()

    # Individual plans: rely on the **Skill:** metadata line. Guard the per-file
    # read (extract_individual_eval_skill reads UTF-8): a malformed / non-UTF-8
    # or race-deleted plan file must NOT crash the whole selector -- skip it from
    # the index (it still appears in all_known). The touched-file path
    # (extract_skills_from_touched_plan_files) separately escalates a malformed
    # TOUCHED plan to run-all.
    for plan_path in sorted(INDIVIDUAL_EVALS_DIR.glob("eval-*.md")):
        all_known.add(plan_path.stem)
        try:
            skill_name = extract_individual_eval_skill(plan_path)
        except (OSError, UnicodeDecodeError):
            continue
        if skill_name and skill_name in plan_by_skill:
            plan_by_skill[skill_name].append(plan_path.stem)

    # Combined plans: scan the plan body for any skill folder name (matches
    # the existing combined-index logic in coverage_gap_report). Same defensive
    # read as above -- an unreadable combined plan is skipped from the index.
    for plan_path in sorted(COMBINED_EVALS_DIR.glob("eval-*.md")):
        all_known.add(plan_path.stem)
        try:
            content = plan_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for skill_name in skill_names:
            if skill_name in content and skill_name in plan_by_skill:
                plan_by_skill[skill_name].append(plan_path.stem)

    return plan_by_skill, sorted(all_known)


def read_changed_files(arg: str) -> list[str]:
    """Read a file path (or `-` for stdin) and return non-empty lines."""
    if arg == "-":
        text = sys.stdin.read()
    else:
        text = Path(arg).read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--skills",
        help="Comma-separated list of touched skill folder names (e.g. 'dataflows-authoring-cli,dataflows-consumption-cli').",
    )
    src.add_argument(
        "--changed-files",
        help="Path to a file containing one changed-file path per line (or '-' for stdin).",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print the JSON output.",
    )
    args = parser.parse_args()

    skill_names = discover_skills(SKILLS_DIR)
    plan_by_skill, all_known_plans = build_plan_index(skill_names)

    if args.skills is not None:
        touched_skills = [s.strip() for s in args.skills.split(",") if s.strip()]
        infrastructure_change = False
        infra_files: list[str] = []
        touched_plugins: list[str] = []
        plugin_skills: list[str] = []
        direct_touched: list[str] = list(touched_skills)
    else:
        changed_paths = read_changed_files(args.changed_files)
        infrastructure_change, infra_files = is_infrastructure_change(changed_paths)
        direct_touched = extract_touched_skills_from_paths(changed_paths)
        # Eval plan-file edits (individual/combined) are not infrastructure
        # (see is_infrastructure_change). Fold the skill(s) those plan files
        # exercise into direct_touched so a plan-only edit maps to the skill's
        # plans through the normal per-skill path instead of escalating the
        # whole suite to run-all.
        plan_file_skills, unresolved_plan_paths = extract_skills_from_touched_plan_files(
            changed_paths, skill_names
        )
        for s in plan_file_skills:
            if s not in direct_touched:
                direct_touched.append(s)
        # A touched eval plan-file that resolves to NO known skill (broken
        # **Skill:** metadata, deleted plan, or a combined plan naming no known
        # skill) escalates to an infrastructure (run-all) change instead of
        # silently skipping eval. Without this, such an edit leaves
        # touched_count at 0 and the PR-touched orchestrator skips the eval
        # entirely -- losing the pre-carve-out safety behavior.
        if unresolved_plan_paths:
            infrastructure_change = True
            for up in unresolved_plan_paths:
                if up not in infra_files:
                    infra_files.append(up)
        touched_plugins = extract_touched_plugins_from_paths(changed_paths)
        # Plugin manifest changes contribute to touched_skills ONLY when this
        # is NOT a true-infrastructure change. If common/ (or another infra
        # path) is also touched, infra wins and we run all plans; expanding
        # the plugin's skill list in that case would pollute touched_skills /
        # plugin_skills with skills that the author never asked to evaluate,
        # making the step summary misleading. On infra change we leave both
        # empty (matched_plans is already empty via the bypass below).
        if infrastructure_change:
            plugin_skills = []
            touched_skills = list(direct_touched)
        else:
            # Read the current plugin manifest at HEAD to find which skills
            # the touched plugin(s) bundle, then add those to the touched-
            # skills set. Direct skill-file changes union with plugin-bundled
            # skills, in stable order (direct first, plugin extras after).
            plugin_skills = expand_plugin_changes_to_skills(touched_plugins, REPO_ROOT)
            touched_skills = list(direct_touched)
            seen_skills: set[str] = set(direct_touched)
            for s in plugin_skills:
                if s not in seen_skills:
                    seen_skills.add(s)
                    touched_skills.append(s)

    # Defensive escalation (Avi F-R1): if a plugin was touched but the
    # manifest yielded ZERO skills AND the author didn't touch any skill
    # directly, we have no signal for which plans to run. Before the
    # plugin-narrowing split, this same case would have been classified as
    # infrastructure and escalated to run-all. Preserve that safety net so a
    # malformed / empty / missing manifest cannot silently bypass the eval
    # gate -- the worst that happens is one PR runs all plans unnecessarily;
    # the best is we catch a regression a contributor's manifest typo would
    # otherwise hide. The infra path takes precedence (no double-signal).
    force_run_all = (
        bool(touched_plugins)
        and not plugin_skills
        and not direct_touched
        and not infrastructure_change
    )
    if force_run_all:
        force_run_all_reason = (
            f"Plugin(s) {touched_plugins} touched but the manifest(s) yielded "
            f"zero skills (missing, malformed, empty, or unrecognized entries). "
            f"Escalating to run-all defensively to avoid a silent eval bypass. "
            f"See stderr WARNING line(s) above for the specific cause."
        )
    else:
        force_run_all_reason = ""

    matched_plans: list[str] = []
    participants: dict[str, list[str]] = {}
    # Skills the AUTHOR directly touched that have no eval coverage. Plugin-
    # bundled skills that lack coverage go into `plugin_skills_without_eval`
    # instead, so the sticky comment doesn't accuse the author of "touching"
    # skills they only pulled in transitively via a plugin manifest tweak.
    unmatched: list[str] = []
    plugin_skills_without_eval: list[str] = []

    if infrastructure_change or force_run_all:
        # Caller decides whether infrastructure / force-run-all -> run-all
        # or skip. We surface the flags and leave matched_plans empty so the
        # orchestrator can choose. The workflow treats both as run-all.
        pass
    else:
        seen_plans: set[str] = set()
        direct_set = set(direct_touched) if args.skills is None else set(touched_skills)
        for skill in touched_skills:
            plans = plan_by_skill.get(skill, [])
            if not plans:
                # Author-visible warning only for skills the author DIRECTLY
                # touched. Plugin-bundled uncovered skills go in the
                # diagnostic bucket so the sticky message is accurate.
                if skill in direct_set:
                    unmatched.append(skill)
                else:
                    plugin_skills_without_eval.append(skill)
                continue
            for plan_name in plans:
                if plan_name not in seen_plans:
                    seen_plans.add(plan_name)
                    matched_plans.append(plan_name)
                participants.setdefault(plan_name, [])
                if skill not in participants[plan_name]:
                    participants[plan_name].append(skill)

    # Gate scope (PR-touched hard-fail scope): the plans that exercise the
    # touched skills, computed UNCONDITIONALLY -- including on infra /
    # force-run-all runs, where matched_plans is intentionally emptied to
    # trigger run-all. The PR-touched gate uses this to hard-fail only on the
    # touched skills' plans, so an unrelated environmental bail in some other
    # plan (surfaced only because an infra change escalated to run-all) does
    # not block the PR. Empty when no skill was touched (pure-infra change) --
    # the gate then falls back to whole-suite gating.
    gate_scope_plans: list[str] = []
    seen_gate: set[str] = set()
    for skill in touched_skills:
        for plan_name in plan_by_skill.get(skill, []):
            if plan_name not in seen_gate:
                seen_gate.add(plan_name)
                gate_scope_plans.append(plan_name)

    result = {
        "matched_plans": matched_plans,
        "participant_skills": participants,
        "unmatched_skills": unmatched,
        "plugin_skills_without_eval": plugin_skills_without_eval,
        "touched_skills": touched_skills,
        "touched_plugins": touched_plugins,
        "plugin_skills": plugin_skills,
        "infrastructure_change": infrastructure_change,
        "infrastructure_files": infra_files,
        "force_run_all": force_run_all,
        "force_run_all_reason": force_run_all_reason,
        "gate_scope_plans": gate_scope_plans,
        "all_known_plans": all_known_plans,
    }

    if args.pretty:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        json.dump(result, sys.stdout)
        sys.stdout.write("\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
