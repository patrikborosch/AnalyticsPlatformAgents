"""Tests for the Sensei-inspired trigger-overlap heuristic and the structural
``has_triggers_field`` check.

History: this PR originally shipped a 5-axis description rubric scorer too,
but the rubric's stylistic axes (action_verb, distinguisher, use_case_enumeration)
produced false positives against legitimate descriptions in the live catalogue.
The rubric was dropped; the one real structural axis (``trigger_list``) was
folded into ``analyze_structural_compliance.has_triggers_field`` instead, and
emitted as a normal structural WARNING.
"""

import math

from skill_validation import (
    _extract_trigger_list_field,
    analyze_structural_compliance,
    find_trigger_overlap,
)


# --------------------------------------------------------------------------- #
# Anti-trigger keyword detection (Triggers: field set overlap)
# --------------------------------------------------------------------------- #

def _make_skill(description: str):
    """Helper to shape input the way the quality checker passes it in."""
    return {"description": description, "triggers": set(), "path": "fake"}


def test_extract_trigger_list_field_normalises_quoted_phrases():
    triggers = _extract_trigger_list_field(
        'Use when. Triggers: "Create Table", "load from ADLS", "MERGE".'
    )

    assert triggers == {"create table", "load from adls", "merge"}


def test_extract_trigger_list_stops_at_sentence_boundary():
    """Prose following the ``Triggers:`` field must not contaminate the set."""
    description = (
        'Execute T-SQL. Triggers: "create table", "merge", "select rows". '
        'Do NOT trigger for "tutorial requests" or "general help".'
    )

    triggers = _extract_trigger_list_field(description)

    assert triggers == {"create table", "merge", "select rows"}


def test_extract_trigger_list_keeps_internal_periods():
    """Regression for the Copilot-reviewer finding (PR #198): periods *inside* a
    trigger phrase (e.g. ``"v1.5 query"``, ``"Gen2.1 dataflow"``) must not
    truncate the field. Only periods that end a sentence (period + whitespace
    or end-of-string) should terminate the capture."""
    description = (
        'Execute T-SQL. Triggers: "v1.5 query", "Gen2.1 dataflow", '
        '"COPY INTO".'
    )

    triggers = _extract_trigger_list_field(description)

    assert triggers == {"v1.5 query", "gen2.1 dataflow", "copy into"}


def test_find_trigger_overlap_reports_pair_above_threshold():
    """Two skills whose Triggers: sets overlap heavily are reported."""
    skill_a_desc = (
        "Execute T-SQL. Triggers: "
        '"create table", "merge into warehouse", "COPY INTO", "alter table".'
    )
    skill_b_desc = (
        "Run T-SQL queries. Triggers: "
        '"create table", "merge into warehouse", "COPY INTO", "select rows".'
    )
    all_skills = {
        "sqldw-authoring-cli": _make_skill(skill_a_desc),
        "sqldw-consumption-cli": _make_skill(skill_b_desc),
    }

    overlaps = find_trigger_overlap(all_skills)

    assert len(overlaps) == 1
    overlap = overlaps[0]
    assert {overlap["skill1"], overlap["skill2"]} == {"sqldw-authoring-cli", "sqldw-consumption-cli"}
    assert overlap["overlap"] > 0.5
    assert {"create table", "merge into warehouse", "copy into"} <= set(overlap["shared_triggers"])


def test_find_trigger_overlap_ignores_disjoint_sets():
    """Skills with no shared triggers are not reported."""
    all_skills = {
        "sqldw": _make_skill(
            'Run SQL. Triggers: "create table", "merge", "select rows", "alter".'
        ),
        "spark": _make_skill(
            'Run Spark. Triggers: "submit notebook", "diagnose OOM", "executor log", "shuffle spill".'
        ),
    }

    overlaps = find_trigger_overlap(all_skills)

    assert overlaps == []


def test_find_trigger_overlap_skips_small_trigger_sets():
    """Pairs are skipped when either skill has fewer than ``min_trigger_count``
    triggers so a single shared phrase doesn't dominate the overlap ratio."""
    all_skills = {
        "skill_a": _make_skill('Triggers: "shared phrase", "unique a".'),
        "skill_b": _make_skill('Triggers: "shared phrase", "unique b".'),
    }

    overlaps = find_trigger_overlap(all_skills, min_trigger_count=3)

    assert overlaps == []


def test_find_trigger_overlap_excludes_check_updates():
    """The ``check-updates`` utility skill is intentionally not compared."""
    triggers_csv = '"alpha", "beta", "gamma", "delta"'
    all_skills = {
        "check-updates": _make_skill(f"Triggers: {triggers_csv}."),
        "other-skill": _make_skill(f"Triggers: {triggers_csv}."),
    }

    overlaps = find_trigger_overlap(all_skills)

    assert overlaps == []


def test_find_trigger_overlap_threshold_is_strict():
    """Exactly-at-threshold overlap (== 0.5) must NOT be reported — the
    contract is ``overlap > threshold`` (strictly greater).

    Bot-review (PR #198): an earlier draft used 2-character trigger phrases
    (``"x1"``, ``"y1"`` …) which the ``_extract_trigger_list_field`` length
    filter (``len(phrase) > 2``) dropped silently — that left both skills with
    only 2 triggers, below ``min_trigger_count=3``, so the pair was skipped
    before the strictness branch was reached and the test would have passed
    even with ``>=``. Use ≥ 3-char trigger phrases so the strictness branch
    actually executes.
    """
    all_skills = {
        # Smaller set has 4 triggers, larger has 4; intersection of size 2
        # gives 2 / min(4, 4) = 0.5 exactly.
        "skill_a": _make_skill(
            'Triggers: "uniq_a1", "uniq_a2", "shared_one", "shared_two".'
        ),
        "skill_b": _make_skill(
            'Triggers: "uniq_b1", "uniq_b2", "shared_one", "shared_two".'
        ),
    }

    # Sanity-pin the precondition the bot pointed out: both sets must clear the
    # minimum size, otherwise the pair would be skipped before the strict-`>`
    # branch is reached.
    from skill_validation import _extract_trigger_list_field
    assert len(_extract_trigger_list_field(all_skills["skill_a"]["description"])) >= 3
    assert len(_extract_trigger_list_field(all_skills["skill_b"]["description"])) >= 3

    overlaps = find_trigger_overlap(all_skills, overlap_threshold=0.5)

    assert overlaps == []


def test_find_trigger_overlap_stores_raw_overlap_for_consistent_display():
    """Regression for the Copilot-reviewer finding (PR #198): the stored
    ``overlap`` must be the raw float, and a precomputed ``overlap_pct`` is
    rounded once for display. Storing a 2-decimal value previously caused
    edge-case overlaps (e.g. 7/13 ≈ 0.538) to render with a percent that did
    not match the raw fraction the threshold was actually applied to."""
    # 7 of 13 = 0.5384... ; rounded once gives 54%. The buggy old code stored
    # 0.54 and then printed int(0.54*100)=54 (consistent in this exact case),
    # but stored 0.53 for 7/14=0.5 -> not reported, and 0.51 for 9/17≈0.529
    # which then displayed as int(0.51*100)=51 even though raw was 52.9%.
    triggers_a = {f"phrase{i}" for i in range(17)}
    triggers_b = set(list(triggers_a)[:9]) | {"only_b_1", "only_b_2", "only_b_3", "only_b_4"}
    all_skills = {
        "a": {"description": "Triggers: " + ", ".join(f'"{t}"' for t in triggers_a) + ".", "triggers": set(), "path": ""},
        "b": {"description": "Triggers: " + ", ".join(f'"{t}"' for t in triggers_b) + ".", "triggers": set(), "path": ""},
    }

    overlaps = find_trigger_overlap(all_skills)

    assert len(overlaps) == 1
    overlap = overlaps[0]
    # Raw float stored, not rounded to 2dp.
    assert isinstance(overlap["overlap"], float)
    assert overlap["overlap"] > 0.5
    # Display percent is computed once via ``math.ceil`` so it can never
    # disagree with the ``> 0.5`` threshold decision (round() would map
    # 0.501 -> 50, contradicting the "exceeded 50%" flag reason).
    assert overlap["overlap_pct"] == math.ceil(overlap["overlap"] * 100)
    assert overlap["overlap_pct"] > 50  # ceil guarantees >50 for every flagged pair
    # And the reason string uses the same display percent.
    assert f"({overlap['overlap_pct']}%)" in overlap["reason"]


# --------------------------------------------------------------------------- #
# Structural check: explicit ``Triggers:`` field in description
# --------------------------------------------------------------------------- #

def _structural(description: str, skill_name: str = "demo-skill"):
    """Wrap a description in the minimal shape ``analyze_structural_compliance``
    expects (frontmatter + body content)."""
    return analyze_structural_compliance(
        content="# demo\n",
        frontmatter={"name": skill_name, "description": description},
        skill_name=skill_name,
    )


def test_has_triggers_field_true_when_field_present():
    checks = _structural(
        "Execute T-SQL. Use when the user wants to run queries. "
        'Triggers: "create table", "COPY INTO".'
    )
    assert checks["has_triggers_field"] is True


def test_has_triggers_field_false_when_field_missing():
    """A description with no ``Triggers:`` field fails the check, even if it
    mentions the word "trigger" in prose."""
    checks = _structural(
        "Execute T-SQL queries. The agent should trigger this skill when the "
        "user wants to run a SQL query against a warehouse."
    )
    assert checks["has_triggers_field"] is False


def test_has_triggers_field_singular_form_accepted():
    """``Trigger:`` (singular) is also accepted — some older authors used it."""
    checks = _structural('Run things. Trigger: "do it now".')
    assert checks["has_triggers_field"] is True

