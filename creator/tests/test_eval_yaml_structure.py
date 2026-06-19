"""Structural lint for tests/evals/<skill>/eval.yaml files.

Enforces the Layer-0 required grader set on every stim of every eval.yaml,
and warns when Layer-1 (`tool-calls`) or Layer-2 (`program`) graders are
absent so workload teams know which stims are still L0-only.

L0 required graders (fail if missing):
  - skill-invocation     (route + sibling disambiguation)
  - completed            (skill must signal completion)
  - output-not-matches   (crash pattern rejection)
  - wall-time            (capped duration)
  - token-budget         (capped tokens)
  - tool-call-count      (capped tool calls)
  - turn-count           (capped turns)
  - error-count          (no recoverable errors leaked to user)

L1+L2 deterministic graders:
  - tool-calls           (Layer 1: required/disallowed endpoint matchers)
  - program              (Layer 2: PowerShell verifier invocation)
  REQUIRED on every stim (hard-fail if missing) EXCEPT the specific legacy
  stims named in ``L1L2_GRANDFATHERED`` (a dir -> frozen set of stim names),
  which predate the requirement and only emit a stderr WARN. A brand-new eval
  dir, OR a brand-new stim added to a grandfathered eval, must ship both layers
  from day 1 -- the baseline is keyed per stim, not per dir, so new test cases
  cannot skip the layers. That baseline is meant to SHRINK as teams add the
  layers and delete graduated stim names. The ``eventhouse-authoring-cli``
  pilot is the worked example carrying both.

  A stim that builds nothing in Fabric to verify (offline / codegen / pure-
  advice, e.g. "write this SQL" or "review this query") may instead opt out of
  L1+L2 with a per-stim ``l1l2_exempt: "<reason>"`` string; the reason is
  mandatory and surfaced as a WARN so the gap stays auditable.

Run locally:
    python -m unittest tests/test_eval_yaml_structure.py -v

In CI: wired into `.github/workflows/quality-check.yml` as a unittest target.
"""
from __future__ import annotations

import sys
import unittest
from unittest import mock
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
EVALS_DIR = REPO_ROOT / "tests" / "evals"

L0_REQUIRED = {
    "skill-invocation",
    "completed",
    "output-not-matches",
    "wall-time",
    "token-budget",
    "tool-call-count",
    "turn-count",
    "error-count",
}

L1_SUGGESTED = "tool-calls"
L2_SUGGESTED = "program"

# Per-stim L1+L2 grandfather baseline: each eval dir name maps to the frozen
# set of EXACT stim names that predate the deterministic-grader requirement and
# are allowed to remain L0-only. Those named stims emit a stderr WARN (see
# test_warn_when_l1_or_l2_missing) instead of hard-failing. The
# eventhouse-authoring-cli pilot is intentionally absent: it is the worked
# example carrying a Layer-1 `tool-calls` grader AND a Layer-2 `program`
# verifier on every stim.
#
# Crucially this is keyed per STIM, not per dir. A brand-new stim added to a
# grandfathered eval is NOT in this baseline, so it must ship L1+L2 from day 1
# exactly like a stim in a brand-new eval dir (test_new_stims_require_l1_and_l2).
# This closes the gap where new test cases could be added to a grandfathered
# eval and silently skip the two deterministic layers.
#
# The baseline is meant to SHRINK, never grow: when a workload team adds the
# two layers to a named stim, DELETE that stim from its set here -- the
# stale-entry test (test_grandfather_list_has_no_stale_entries) fails until you
# do. Do NOT add new stim names to keep fresh work L0-only.
L1L2_GRANDFATHERED: dict[str, frozenset[str]] = {
    'activator-authoring-cli': frozenset({
        'Create basic Activator item',
        'Create temperature alert rule',
        'Create workspace event notification rule',
    }),
    'activator-consumption-cli': frozenset({
        'List Activator items and find named item',
        'Show alerts and summarize Activator items',
        'Inspect specific Activator item details',
    }),
    'dataflows-authoring-cli': frozenset({
        'Create-or-update Gen2 dataflow and refresh',
        'List supported connection types and SQL credentialType',
        'executeQuery preview before updateDefinition',
        'updateDefinition adds Doubled shared query',
        'Configure Dataflow Gen2 output destination to lakehouse',
        'Configure Dataflow Gen2 output destination to warehouse',
    }),
    'dataflows-consumption-cli': frozenset({
        'List dataflows and decode definition',
        'Execute named Dataflow Gen2 query',
        'Execute ad-hoc Dataflow Gen2 custom M query',
        'Inspect Dataflow Gen2 refresh history',
    }),
    'dataflows-save-as-authoring-cli': frozenset({'Produce Gen1-to-Gen2 migration readiness snapshot'}),
    'document-workspace-agent': frozenset({'Document workspace properties'}),
    'eventhouse-consumption-cli': frozenset({
        'KQL basic row count',
        'KQL analytical aggregation query',
        'Routing negative - eventstream prompt routed to eventhouse',
    }),
    'eventstream-authoring-cli': frozenset({
        'Create basic Eventstream',
        'Add Event Hub source to Eventstream',
        'Add filter operator to Eventstream',
        'Deploy full Eventstream topology',
    }),
    'eventstream-consumption-cli': frozenset({
        'List Eventstreams in workspace',
        'Inspect Eventstream topology',
        'Check Eventstream retention and throughput',
    }),
    'fabriciq': frozenset({'Ask Power BI SalesBenchmark total sales'}),
    'powerbi-report-authoring': frozenset({'Add report page and validate PBIR'}),
    'powerbi-report-design': frozenset({'Choose Power BI report design archetype'}),
    'powerbi-report-management': frozenset({'Publish local PBIP report to Fabric workspace'}),
    'powerbi-report-planning': frozenset({'Plan a Power BI executive sales report'}),
    'search-consumption-cli': frozenset({'Find lakehouse by name across tenant'}),
    'semantic-model-authoring': frozenset({
        'Refresh semantic model and inspect history',
        'Apply semantic model naming conventions',
        'Prepare semantic model for AI consumption',
        'List semantic model user permissions',
    }),
    'semantic-model-consumption': frozenset({'Run DAX TotalSales2023 against SalesBenchmark semantic model'}),
    'spark-authoring-cli': frozenset({
        'Run sanity notebook and report status',
        'Codegen -- read parquet from default lakehouse Files',
        'Codegen -- mount ADLS Gen2 via notebookutils',
        'Codegen -- %%configure session memory + native execution',
        'Codegen -- %%sql cross-lakehouse query',
        'Codegen -- read builtin resource file via nbResPath',
        'Codegen -- detect pipeline runtime context',
        'Codegen -- PostgreSQL via Fabric connections',
        'Codegen -- notebook DAG via runMultiple',
    }),
    'spark-consumption-cli': frozenset({'Livy session sanity calculation'}),
    'spark-consumption-cli-isolated': frozenset({'Livy session sanity calculation (isolated)'}),
    'spark-operations-cli': frozenset({
        'Diagnose failed notebook run',
        'Diagnose failed pipeline Spark activity',
        'Check Livy session health',
    }),
    'sqldw-consumption-cli': frozenset({
        'SQL endpoint basic row count',
        'SQL endpoint average trip distance by vendor',
    }),
    'sqldw-operations-cli': frozenset({'DW slow query analysis from queryinsights'}),
    'synapse-migration': frozenset({
        'Routing positive -- Spark migration phases',
        'Routing positive -- Lake Database to Lakehouse migration',
    }),
}

# Synthetic L0 requirement: every stim must have at least ONE positive
# output assertion (output-matches OR output-contains). Without this, a stim
# can pass L0 with only routing + completion + crash-rejection + budgets,
# producing zero evidence that the expected behaviour happened. Documented
# in the L0 template in tests/evals/README.md.
#
# Opt out per-stim with `l0_exempt: [positive-output-assertion]` ONLY when
# the prompt has no testable positive output (e.g., routing-negative stims
# that confirm a sibling skill was NOT invoked, or stims whose assertions
# fully live in L1 tool-calls + L2 program graders). The exempt list MUST
# carry a TODO comment for the grandfathered ones so the gap is visible.
POSITIVE_OUTPUT_ASSERTION_KEY = "positive-output-assertion"
POSITIVE_OUTPUT_ASSERTION_GRADERS = {"output-matches", "output-contains"}

# The complete set of names that may legitimately appear in a stim's
# `l0_exempt` list: every required L0 grader type plus the synthetic
# `positive-output-assertion` key. `l0_exempt` lists GRADER-TYPE names that do
# not apply to a stim -- it does NOT list skill names. A typo here (e.g.
# `skill-invokation`) would silently grant no exemption and could mask a real
# L0 gap, so any value outside this set is rejected by
# test_l0_exempt_values_are_known_grader_names.
L0_EXEMPTABLE = L0_REQUIRED | {POSITIVE_OUTPUT_ASSERTION_KEY}


def _discover_eval_yamls():
    if not EVALS_DIR.is_dir():
        return []
    # Skip the `.vally-results/` staging directory: when run-vally-eval.ps1
    # is pointed at `tests/evals/.vally-results/` (or any nested staging
    # path), those are produced artefacts, not source eval.yaml specs, and
    # must not be linted as if they were authored.
    return sorted(
        p for p in EVALS_DIR.rglob("eval.yaml")
        if ".vally-results" not in p.parts
    )


def _grader_types_per_stim(eval_doc):
    """Extract per-stim grader types as a list of ``(name, types, exempt)``.

    Non-list / non-mapping substructures are silently skipped here so this
    helper never raises ``AttributeError`` on structurally-malformed eval
    YAML (e.g., ``stimuli: {}`` instead of ``stimuli: []``). The dedicated
    ``test_stimuli_and_graders_are_lists`` owns the canonical FAIL message
    for shape drift; this helper defers to it so each root cause produces
    exactly one failure surface.
    """
    if not isinstance(eval_doc, dict):
        return []
    stims = eval_doc.get("stimuli") or []
    if not isinstance(stims, list):
        return []
    out = []
    for s in stims:
        if not isinstance(s, dict):
            continue
        graders = s.get("graders") or []
        if not isinstance(graders, list):
            continue
        types = [g.get("type") for g in graders if isinstance(g, dict) and g.get("type")]
        # Per-stim exemption: a top-level `l0_exempt` field lists L0 grader
        # type names that legitimately do not apply to this stim (e.g.,
        # `skill-invocation` for multi-skill agent composition stims where
        # no single required skill exists).
        exempt_raw = s.get("l0_exempt") or []
        exempt = set(exempt_raw) if isinstance(exempt_raw, (list, tuple, set)) else set()
        out.append((s.get("name") or "<unnamed>", types, exempt))
    return out


def _load_eval_yaml_or_none(path):
    """Parse an eval.yaml; return None on YAMLError so the L0/L1+L2 tests can
    skip it without raising. `test_every_eval_yaml_parses` is the single
    canonical owner of YAML-parse-error reporting; the other tests defer to
    it so a malformed file produces one clean failure message, not three
    different tracebacks pointing at the same root cause.
    """
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None


def _l1l2_exempt_reasons(eval_doc):
    """Return ``{stim_name: reason}`` for stims that opt out of the L1+L2
    deterministic-grader requirement via a non-empty ``l1l2_exempt`` reason
    string.

    Use this ONLY for stims that build nothing in Fabric to verify -- offline
    or pure-codegen / advice stims (e.g. "write this SQL", "review this query")
    where there is no Fabric artefact for a Layer-2 ``program`` verifier to
    inspect and no Fabric tool call for a Layer-1 ``tool-calls`` matcher to
    assert. The reason is mandatory: it is surfaced on every run by
    ``test_warn_when_l1l2_exempt_used`` so the gap stays auditable, and a
    present-but-empty value is hard-failed by ``test_l1l2_exempt_requires_reason``.

    Factored out as a module helper so it can be unit-tested with synthetic
    docs (see L1L2ExemptHelperTests).
    """
    out = {}
    if not isinstance(eval_doc, dict):
        return out
    stims = eval_doc.get("stimuli") or []
    if not isinstance(stims, list):
        return out
    for s in stims:
        if not isinstance(s, dict) or "l1l2_exempt" not in s:
            continue
        reason = s.get("l1l2_exempt")
        if isinstance(reason, str) and reason.strip():
            out[s.get("name") or "<unnamed>"] = reason.strip()
    return out


def _l1l2_exempt_problems(eval_doc):
    """Return ``[(stim_name, value_repr), ...]`` for stims whose ``l1l2_exempt``
    field is PRESENT but is not a non-empty string.

    A reason is mandatory, so an empty string, whitespace, ``true``, a list,
    etc. is a hard error -- otherwise an author could silently dodge the L1+L2
    requirement with a contentless opt-out. Factored out as a module helper so
    it can be unit-tested with synthetic docs (see L1L2ExemptHelperTests).
    """
    out = []
    if not isinstance(eval_doc, dict):
        return out
    stims = eval_doc.get("stimuli") or []
    if not isinstance(stims, list):
        return out
    for s in stims:
        if not isinstance(s, dict) or "l1l2_exempt" not in s:
            continue
        reason = s.get("l1l2_exempt")
        if not (isinstance(reason, str) and reason.strip()):
            out.append((s.get("name") or "<unnamed>", repr(reason)))
    return out


def _required_l1l2_violations(eval_dir_name, eval_doc):
    """Return ``[(stim_name, [missing_grader_types]), ...]`` for the stims that
    are REQUIRED to carry the Layer-1 ``tool-calls`` and Layer-2 ``program``
    deterministic graders but are missing one or both.

    The grandfather baseline is keyed per STIM, not per dir: a stim is exempt
    (warn-only, no violation) only if its eval dir is in ``L1L2_GRANDFATHERED``
    AND its exact name is in that dir's frozen set. Every other stim must carry
    at least one ``tool-calls`` grader AND at least one ``program`` grader; this
    covers both stims in brand-new (non-grandfathered) eval dirs and brand-new
    stims added to a grandfathered eval. A stim may also opt out via a non-empty
    ``l1l2_exempt`` reason (see ``_l1l2_exempt_reasons``) -- for offline /
    codegen stims that build nothing in Fabric to verify. Factored out as a
    module helper so it can be unit-tested with synthetic docs (see
    L1L2RequirementHelperTests).
    """
    exempt_stims = L1L2_GRANDFATHERED.get(eval_dir_name, frozenset())
    l1l2_exempt = _l1l2_exempt_reasons(eval_doc)
    out = []
    for stim_name, grader_types, _exempt in _grader_types_per_stim(eval_doc):
        if stim_name in exempt_stims:
            # Named legacy stim: allowed to remain L0-only, surfaced as a
            # stderr WARN by test_warn_when_l1_or_l2_missing instead.
            continue
        if stim_name in l1l2_exempt:
            # Opted out via `l1l2_exempt` (offline / codegen stim that builds
            # nothing in Fabric to verify); surfaced as a stderr WARN by
            # test_warn_when_l1l2_exempt_used instead.
            continue
        missing = []
        if L1_SUGGESTED not in grader_types:
            missing.append(L1_SUGGESTED)
        if L2_SUGGESTED not in grader_types:
            missing.append(L2_SUGGESTED)
        if missing:
            out.append((stim_name, missing))
    return out


def _grandfather_stale_problems(grandfathered, present_dirs, on_disk):
    """Return problem strings for stale/graduated entries in a per-stim L1+L2
    grandfather baseline.

    - ``grandfathered``: the baseline mapping (dir -> set of stim names).
    - ``present_dirs``: dirs that have an eval.yaml on disk (parsed OR not).
    - ``on_disk``: dir -> {stim name: grader_types} for dirs that PARSED.

    A dir that is present but absent from ``on_disk`` failed to parse; that is
    owned by ``test_every_eval_yaml_parses``, so it is skipped here rather than
    misreported as a missing dir. Factored out so the edge cases can be
    unit-tested with synthetic inputs (see GrandfatherStaleHelperTests).
    """
    problems = []
    for d, names in sorted(grandfathered.items()):
        if d not in present_dirs:
            problems.append(
                f"  dir {d!r}: not found under {EVALS_DIR.relative_to(REPO_ROOT)}"
            )
            continue
        dir_stims = on_disk.get(d)
        if dir_stims is None:
            # eval.yaml exists but failed to parse: owned by
            # test_every_eval_yaml_parses; cannot introspect stims here.
            continue
        for name in sorted(names):
            if name not in dir_stims:
                problems.append(
                    f"  {d} :: {name!r}: stim no longer exists (renamed/removed)"
                )
            elif L1_SUGGESTED in dir_stims[name] and L2_SUGGESTED in dir_stims[name]:
                problems.append(
                    f"  {d} :: {name!r}: stim now carries L1+L2 -- it has graduated"
                )
    return problems


def _unknown_l0_exempt_names(eval_doc):
    """Return ``[(stim_name, [unknown_names]), ...]`` for stims whose
    ``l0_exempt`` list contains a name that is not in ``L0_EXEMPTABLE``.

    Factored out as a module helper so it can be unit-tested with synthetic
    docs (see L0ExemptValidationHelperTests).
    """
    out = []
    for stim_name, _grader_types, exempt in _grader_types_per_stim(eval_doc):
        unknown = sorted(exempt - L0_EXEMPTABLE)
        if unknown:
            out.append((stim_name, unknown))
    return out


class EvalYamlStructureTests(unittest.TestCase):
    """Walk every tests/evals/<skill>/eval.yaml and enforce L0 grader minimum."""

    @classmethod
    def setUpClass(cls):
        cls.eval_paths = _discover_eval_yamls()

    def test_at_least_one_eval_yaml_exists(self):
        self.assertGreater(
            len(self.eval_paths),
            0,
            f"No eval.yaml files found under {EVALS_DIR}. "
            "Repo is not in a state this lint can guard.",
        )

    def test_every_eval_yaml_parses(self):
        for p in self.eval_paths:
            with self.subTest(eval=str(p.relative_to(REPO_ROOT))):
                try:
                    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
                except yaml.YAMLError as e:
                    self.fail(f"{p.relative_to(REPO_ROOT)}: YAML parse error: {e}")
                self.assertIsInstance(
                    doc, dict, f"{p.relative_to(REPO_ROOT)}: top-level must be a mapping",
                )

    def test_stimuli_and_graders_are_lists(self):
        """Hard-fail per eval.yaml when `stimuli` is not a list of mappings,
        or when any stim's `graders` is not a list of mappings.

        Catches structural drift (e.g. `stimuli: {}` instead of `stimuli: []`,
        or a stim that uses `graders: <mapping>`) with one clear failure
        message per offender, BEFORE `_grader_types_per_stim` silently skips
        the malformed substructure. Files that fail to YAML-parse are owned
        by `test_every_eval_yaml_parses`.
        """
        violations = []
        for p in self.eval_paths:
            doc = _load_eval_yaml_or_none(p)
            if doc is None:
                continue
            stims = doc.get("stimuli")
            if stims is not None and not isinstance(stims, list):
                violations.append(
                    f"  {p.relative_to(REPO_ROOT)}: `stimuli` is "
                    f"{type(stims).__name__}, expected list"
                )
                continue
            for i, s in enumerate(stims or []):
                if not isinstance(s, dict):
                    violations.append(
                        f"  {p.relative_to(REPO_ROOT)}: stimuli[{i}] is "
                        f"{type(s).__name__}, expected mapping"
                    )
                    continue
                g = s.get("graders")
                if g is not None and not isinstance(g, list):
                    violations.append(
                        f"  {p.relative_to(REPO_ROOT)}: stimuli[{i}].graders "
                        f"is {type(g).__name__}, expected list"
                    )
                    continue
                for j, grader in enumerate(g or []):
                    if not isinstance(grader, dict):
                        violations.append(
                            f"  {p.relative_to(REPO_ROOT)}: "
                            f"stimuli[{i}].graders[{j}] is "
                            f"{type(grader).__name__}, expected mapping"
                        )
        if violations:
            self.fail(
                f"Structural drift in {len(violations)} location(s):\n" +
                "\n".join(violations) +
                "\n\nFix the eval.yaml shape; see tests/evals/README.md for "
                "the canonical template."
            )

    def test_every_stim_has_required_l0_graders(self):
        """Hard-fail per stim if any L0 grader is missing.

        Stims may opt out of a specific L0 grader via the top-level
        `l0_exempt: [grader-name, ...]` field when the grader doesn't apply
        (e.g., multi-skill agent composition cannot assert one required
        skill). The exemption is per-stim, not per-eval.

        Files that fail to YAML-parse are skipped here -- they will be
        surfaced as a clear failure by `test_every_eval_yaml_parses`.
        """
        violations = []
        for p in self.eval_paths:
            doc = _load_eval_yaml_or_none(p)
            if doc is None:
                continue
            for stim_name, grader_types, exempt in _grader_types_per_stim(doc):
                required_here = L0_REQUIRED - exempt
                missing = sorted(required_here - set(grader_types))
                if missing:
                    violations.append(
                        f"  {p.relative_to(REPO_ROOT)} :: stim={stim_name!r}\n"
                        f"      missing L0 graders: {missing}"
                    )
        if violations:
            self.fail(
                "L0 grader minimum violated in "
                f"{len(violations)} stim(s):\n" + "\n".join(violations) +
                "\n\nAdd the missing graders. See tests/evals/README.md for "
                "the Layer 0 template and the eventhouse-authoring-cli pilot "
                "for the worked example. If a grader genuinely does not "
                "apply (e.g., `skill-invocation` for multi-skill agent "
                "composition), opt out via `l0_exempt: [<grader>]` on the "
                "stim with a comment explaining why."
            )

    def test_every_stim_has_positive_output_assertion(self):
        """Hard-fail per stim if neither `output-matches` nor `output-contains`
        is present.

        Without a positive output assertion, an L0 stim can pass on routing,
        completion, no-crash, and budgets without ever asserting that the
        expected behaviour produced expected output. A negative-only stim is
        effectively a no-op grade.

        Opt out per-stim with `l0_exempt: [positive-output-assertion]` when
        the assertion legitimately lives elsewhere (L1 tool-calls, L2 program
        verifier) or there is no testable positive output (routing-negative
        stims). Carry a TODO comment on the exempt entry so the gap is
        visible.

        Files that fail to YAML-parse are skipped here -- the parse failure
        is owned by `test_every_eval_yaml_parses`.
        """
        violations = []
        for p in self.eval_paths:
            doc = _load_eval_yaml_or_none(p)
            if doc is None:
                continue
            for stim_name, grader_types, exempt in _grader_types_per_stim(doc):
                if POSITIVE_OUTPUT_ASSERTION_KEY in exempt:
                    continue
                if not (POSITIVE_OUTPUT_ASSERTION_GRADERS & set(grader_types)):
                    violations.append(
                        f"  {p.relative_to(REPO_ROOT)} :: stim={stim_name!r}\n"
                        f"      stim has no positive output assertion "
                        f"(output-matches or output-contains)"
                    )
        if violations:
            self.fail(
                "Positive output assertion missing in "
                f"{len(violations)} stim(s):\n" + "\n".join(violations) +
                "\n\nAdd an `output-matches` or `output-contains` grader, "
                "or (when the assertion lives in L1/L2 or the stim is "
                "routing-negative) opt out via "
                "`l0_exempt: [positive-output-assertion]` on the stim with "
                "a comment explaining why."
            )

    def test_new_stims_require_l1_and_l2(self):
        """Hard-fail when a stim that must carry the deterministic layers is
        missing a Layer-1 ``tool-calls`` grader or a Layer-2 ``program``
        grader.

        A stim is required to carry both layers unless it is a named legacy
        stim in ``L1L2_GRANDFATHERED`` (its dir AND its exact name). So the
        requirement applies to every stim in a brand-new eval dir (the
        ``eventhouse-authoring-cli`` pilot is the worked example) AND to every
        brand-new stim added to a grandfathered eval -- a new test case cannot
        skip the layers just because its eval dir predates the rule. Named
        legacy stims keep the stderr WARN (``test_warn_when_l1_or_l2_missing``)
        until a team adds the layers and removes them from the baseline.

        Files that fail to YAML-parse are skipped here; the parse failure is
        owned by `test_every_eval_yaml_parses`.
        """
        violations = []
        for p in self.eval_paths:
            doc = _load_eval_yaml_or_none(p)
            if doc is None:
                continue
            for stim_name, missing in _required_l1l2_violations(p.parent.name, doc):
                violations.append(
                    f"  {p.relative_to(REPO_ROOT)} :: stim={stim_name!r}\n"
                    f"      missing deterministic grader(s): {missing}"
                )
        if violations:
            self.fail(
                "L1+L2 deterministic grader requirement violated in "
                f"{len(violations)} stim(s):\n" + "\n".join(violations) +
                "\n\nEvery stim must carry at least one `tool-calls` (Layer 1) "
                "grader AND at least one `program` (Layer 2) verifier, unless "
                "it is an existing stim named in L1L2_GRANDFATHERED. See "
                "tests/evals/README.md#how-to-write-a-verifier-for-your-skill "
                "and the eventhouse-authoring-cli pilot for the worked example. "
                "A new stim added to a grandfathered eval must still ship both "
                "layers -- do NOT add it to the grandfather baseline (that "
                "baseline is meant to shrink, not grow). If a stim builds "
                "nothing in Fabric to verify (offline / codegen / pure-advice), "
                "opt out with `l1l2_exempt: \"<reason>\"` on the "
                "stim instead -- the reason is mandatory and surfaces as a WARN."
            )

    def test_stim_names_unique_within_eval(self):
        """Stim names must be unique within each eval.yaml. The per-stim L1+L2
        grandfather baseline keys exemptions by (dir, stim name); a duplicate
        name would let a new L0-only stim ride on an existing baseline name and
        skip the deterministic layers (and could also confuse the stale guard,
        which records grader types by name last-wins). Uniqueness closes that
        and is good hygiene regardless.

        Files that fail to YAML-parse are skipped here; the parse failure is
        owned by `test_every_eval_yaml_parses`.
        """
        dupes = []
        for p in self.eval_paths:
            doc = _load_eval_yaml_or_none(p)
            if doc is None:
                continue
            seen = set()
            local_dupes = set()
            for stim_name, _types, _exempt in _grader_types_per_stim(doc):
                if stim_name in seen:
                    local_dupes.add(stim_name)
                seen.add(stim_name)
            for name in sorted(local_dupes):
                dupes.append(f"  {p.relative_to(REPO_ROOT)} :: {name!r}")
        self.assertEqual(
            dupes,
            [],
            "Duplicate stim name(s) within an eval.yaml -- names must be unique "
            "so the per-stim L1+L2 grandfather baseline cannot be bypassed by "
            "reusing an existing name:\n" + "\n".join(dupes),
        )

    def test_grandfather_list_has_no_stale_entries(self):
        """The L1L2_GRANDFATHERED baseline must only name (dir, stim) pairs
        that still exist AND are still L0-only. A dir or stim that was deleted
        or renamed, or a stim that has since gained both deterministic layers,
        must be removed so the baseline keeps shrinking and cannot silently
        shelter a real gap (or pin a stim that already graduated)."""
        # dir name -> {stim name: grader_types} for parsed grandfathered evals.
        on_disk = {}
        # Grandfathered dirs that have an eval.yaml present on disk (even if it
        # fails to parse), so a parse failure is NOT misreported as a missing
        # dir below -- parse failures are owned by test_every_eval_yaml_parses.
        present_dirs = set()
        for p in self.eval_paths:
            d = p.parent.name
            if d not in L1L2_GRANDFATHERED:
                continue
            present_dirs.add(d)
            doc = _load_eval_yaml_or_none(p)
            if doc is None:
                continue
            stims = on_disk.setdefault(d, {})
            for stim_name, grader_types, _exempt in _grader_types_per_stim(doc):
                stims[stim_name] = grader_types
        problems = _grandfather_stale_problems(
            L1L2_GRANDFATHERED, present_dirs, on_disk
        )
        self.assertEqual(
            problems,
            [],
            "L1L2_GRANDFATHERED has stale or graduated baseline entries. Remove "
            "each one so the baseline stays honest and shrinking:\n"
            + "\n".join(problems),
        )

    def test_warn_when_l1_or_l2_missing(self):
        """Print to stderr when a named legacy (baseline) stim is L0-only;
        never fail. New stims -- in a non-grandfathered dir or added to a
        grandfathered eval -- are hard-gated by
        ``test_new_stims_require_l1_and_l2``, so they are skipped here to avoid
        a duplicate signal.

        Files that fail to YAML-parse are skipped here; the parse failure is
        owned by `test_every_eval_yaml_parses`.
        """
        gaps_l1 = []
        gaps_l2 = []
        for p in self.eval_paths:
            exempt_stims = L1L2_GRANDFATHERED.get(p.parent.name)
            if not exempt_stims:
                continue
            doc = _load_eval_yaml_or_none(p)
            if doc is None:
                continue
            for stim_name, grader_types, _exempt in _grader_types_per_stim(doc):
                if stim_name not in exempt_stims:
                    # New (non-baseline) stim -> hard-gated by
                    # test_new_stims_require_l1_and_l2, not a warn.
                    continue
                rel = p.relative_to(REPO_ROOT)
                if L1_SUGGESTED not in grader_types:
                    gaps_l1.append(f"    {rel} :: {stim_name!r}")
                if L2_SUGGESTED not in grader_types:
                    gaps_l2.append(f"    {rel} :: {stim_name!r}")
        if gaps_l1 or gaps_l2:
            print(
                "\n[WARN] eval.yaml structure -- "
                "the following GRANDFATHERED stims are missing a Layer-1 "
                "(`tool-calls`) and/or Layer-2 (`program`) deterministic "
                "grader. L0-only graders judge prose; Layers 1 and 2 judge "
                "actual Fabric behaviour. These stims are named in "
                "L1L2_GRANDFATHERED; add the missing layer(s) and remove the "
                "stim from the baseline to graduate it. See "
                "tests/evals/README.md#how-to-write-a-verifier-for-your-skill "
                "and the eventhouse-authoring-cli pilot.",
                file=sys.stderr,
            )
            if gaps_l1:
                print(
                    f"\n  Missing `tool-calls` grader ({len(gaps_l1)} stim(s)):",
                    file=sys.stderr,
                )
                for line in gaps_l1:
                    print(line, file=sys.stderr)
            if gaps_l2:
                print(
                    f"\n  Missing `program` grader ({len(gaps_l2)} stim(s)):",
                    file=sys.stderr,
                )
                for line in gaps_l2:
                    print(line, file=sys.stderr)

    def test_l0_exempt_values_are_known_grader_names(self):
        """Hard-fail when a stim's ``l0_exempt`` list contains a name that is
        not a known exemptable grader type.

        ``l0_exempt`` lists GRADER-TYPE names (e.g. ``skill-invocation``,
        ``positive-output-assertion``) that legitimately do not apply to a
        stim -- it does NOT list skill names. A typo would silently grant no
        exemption and could mask a real L0 gap, so any value outside
        ``L0_EXEMPTABLE`` is rejected.

        Files that fail to YAML-parse are skipped here; the parse failure is
        owned by `test_every_eval_yaml_parses`.
        """
        violations = []
        for p in self.eval_paths:
            doc = _load_eval_yaml_or_none(p)
            if doc is None:
                continue
            for stim_name, unknown in _unknown_l0_exempt_names(doc):
                violations.append(
                    f"  {p.relative_to(REPO_ROOT)} :: stim={stim_name!r}\n"
                    f"      unknown l0_exempt name(s): {unknown}"
                )
        if violations:
            self.fail(
                f"Unknown l0_exempt grader name(s) in {len(violations)} "
                "stim(s):\n" + "\n".join(violations) +
                "\n\n`l0_exempt` must list known grader-type names (one of "
                f"{sorted(L0_EXEMPTABLE)}), NOT skill names. Fix the typo or "
                "remove the entry. See the `l0_exempt` reference in "
                "tests/evals/README.md."
            )

    def test_warn_when_l0_exempt_used(self):
        """Print to stderr every stim that opts out of an L0 grader via
        ``l0_exempt``; never fail. Each exemption removes real coverage, so
        usage should be VISIBLE on every run (not silent-when-valid) -- a
        reviewer/maintainer can scan the list and challenge any exemption that
        shouldn't be there, and watch the count over time. Mirrors the
        grandfather WARN in ``test_warn_when_l1_or_l2_missing``; the hard typo
        guard lives in ``test_l0_exempt_values_are_known_grader_names``.

        Files that fail to YAML-parse are skipped here; the parse failure is
        owned by `test_every_eval_yaml_parses`.
        """
        usages = []
        for p in self.eval_paths:
            doc = _load_eval_yaml_or_none(p)
            if doc is None:
                continue
            for stim_name, _grader_types, exempt in _grader_types_per_stim(doc):
                if exempt:
                    rel = p.relative_to(REPO_ROOT)
                    usages.append(
                        f"    {rel} :: {stim_name!r} -- "
                        f"l0_exempt: {sorted(exempt)}"
                    )
        if usages:
            print(
                f"\n[WARN] eval.yaml structure -- {len(usages)} stim(s) opt out "
                "of an L0 grader via `l0_exempt`. Each exemption removes real "
                "coverage; confirm every one is justified (routing-negative or "
                "agent-composition stims) and keep the list tight. See the "
                "`l0_exempt` reference in tests/evals/README.md.",
                file=sys.stderr,
            )
            for line in usages:
                print(line, file=sys.stderr)

    def test_l1l2_exempt_requires_reason(self):
        """Hard-fail when a stim's ``l1l2_exempt`` field is present but is not a
        non-empty string.

        ``l1l2_exempt`` opts a stim out of the L1+L2 deterministic-grader
        requirement (for offline / codegen stims that build nothing in Fabric to
        verify). Because it removes the strongest coverage layers, the reason is
        mandatory -- an empty string, ``true``, a list, etc. is rejected so an
        author cannot silently dodge the requirement with a contentless opt-out.

        Files that fail to YAML-parse are skipped here; the parse failure is
        owned by `test_every_eval_yaml_parses`.
        """
        violations = []
        for p in self.eval_paths:
            doc = _load_eval_yaml_or_none(p)
            if doc is None:
                continue
            for stim_name, value_repr in _l1l2_exempt_problems(doc):
                violations.append(
                    f"  {p.relative_to(REPO_ROOT)} :: stim={stim_name!r}\n"
                    f"      l1l2_exempt must be a non-empty reason string, got: {value_repr}"
                )
        if violations:
            self.fail(
                f"Malformed l1l2_exempt in {len(violations)} stim(s):\n"
                + "\n".join(violations) +
                "\n\n`l1l2_exempt` must be a non-empty string explaining WHY the "
                "stim builds nothing in Fabric to verify (e.g. \"offline JSON "
                "translation; no Fabric artefact or tool call to assert\"). See "
                "the `l1l2_exempt` reference in tests/evals/README.md."
            )

    def test_warn_when_l1l2_exempt_used(self):
        """Print to stderr every stim that opts out of L1+L2 via ``l1l2_exempt``;
        never fail. Opting out removes the deterministic behaviour layers, so
        usage should be VISIBLE on every run -- a reviewer/maintainer can scan
        the list and challenge any opt-out that should instead carry real
        Layer-1/Layer-2 graders. Mirrors ``test_warn_when_l0_exempt_used``; the
        hard guard lives in ``test_l1l2_exempt_requires_reason``.

        Files that fail to YAML-parse are skipped here; the parse failure is
        owned by `test_every_eval_yaml_parses`.
        """
        usages = []
        for p in self.eval_paths:
            doc = _load_eval_yaml_or_none(p)
            if doc is None:
                continue
            for stim_name, reason in sorted(_l1l2_exempt_reasons(doc).items()):
                rel = p.relative_to(REPO_ROOT)
                usages.append(f"    {rel} :: {stim_name!r} -- {reason}")
        if usages:
            print(
                f"\n[WARN] eval.yaml structure -- {len(usages)} stim(s) opt out "
                "of the L1+L2 deterministic graders via `l1l2_exempt`. Each "
                "opt-out removes Fabric-behaviour coverage; confirm every one is "
                "an offline / codegen stim that truly builds nothing to verify, "
                "and keep the list tight. See the `l1l2_exempt` reference in "
                "tests/evals/README.md.",
                file=sys.stderr,
            )
            for line in usages:
                print(line, file=sys.stderr)


class L1L2RequirementHelperTests(unittest.TestCase):
    """Unit tests for ``_required_l1l2_violations`` using synthetic docs, so
    the gate logic is verified independently of the on-disk evals."""

    @staticmethod
    def _doc(grader_types, name="synthetic-stim"):
        """Build a minimal eval doc with a single named stim carrying the given
        grader types."""
        return {
            "stimuli": [
                {
                    "name": name,
                    "graders": [{"type": t} for t in grader_types],
                }
            ]
        }

    def test_non_grandfathered_missing_l2_is_violation(self):
        doc = self._doc(["skill-invocation", "tool-calls"])
        violations = _required_l1l2_violations("brand-new-eval", doc)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0][0], "synthetic-stim")
        self.assertIn(L2_SUGGESTED, violations[0][1])
        self.assertNotIn(L1_SUGGESTED, violations[0][1])

    def test_non_grandfathered_missing_l1_is_violation(self):
        doc = self._doc(["skill-invocation", "program"])
        violations = _required_l1l2_violations("brand-new-eval", doc)
        self.assertEqual(len(violations), 1)
        self.assertIn(L1_SUGGESTED, violations[0][1])
        self.assertNotIn(L2_SUGGESTED, violations[0][1])

    def test_non_grandfathered_missing_both_is_violation(self):
        doc = self._doc(["skill-invocation"])
        violations = _required_l1l2_violations("brand-new-eval", doc)
        self.assertEqual(len(violations), 1)
        self.assertEqual(set(violations[0][1]), {L1_SUGGESTED, L2_SUGGESTED})

    def test_non_grandfathered_with_l1_and_l2_passes(self):
        doc = self._doc(["skill-invocation", "tool-calls", "program"])
        self.assertEqual(_required_l1l2_violations("brand-new-eval", doc), [])

    @mock.patch.dict(
        L1L2_GRANDFATHERED,
        {"synthetic-grandfathered-dir": frozenset({"legacy-stim"})},
        clear=True,
    )
    def test_grandfathered_baseline_stim_never_violates(self):
        # A named legacy stim (in the dir's baseline) may stay L0-only: it only
        # WARNs, never violates. Uses a synthetic baseline via patch.dict so the
        # test does not depend on the real baseline being non-empty -- it is
        # meant to shrink to {} as stims graduate, at which point indexing the
        # real dict would raise.
        doc = self._doc(["skill-invocation"], name="legacy-stim")
        self.assertEqual(
            _required_l1l2_violations("synthetic-grandfathered-dir", doc), []
        )

    @mock.patch.dict(
        L1L2_GRANDFATHERED,
        {"synthetic-grandfathered-dir": frozenset({"legacy-stim"})},
        clear=True,
    )
    def test_new_stim_in_grandfathered_dir_is_violation(self):
        # A brand-new stim (name NOT in the dir's baseline) added to a
        # grandfathered eval must still ship L1+L2. This is the gap the per-stim
        # baseline closes: dir-level grandfathering used to let new test cases
        # skip the deterministic layers entirely.
        doc = self._doc(["skill-invocation"], name="brand-new-stim-not-in-baseline")
        violations = _required_l1l2_violations("synthetic-grandfathered-dir", doc)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0][0], "brand-new-stim-not-in-baseline")
        self.assertEqual(set(violations[0][1]), {L1_SUGGESTED, L2_SUGGESTED})

    @mock.patch.dict(
        L1L2_GRANDFATHERED,
        {"synthetic-grandfathered-dir": frozenset({"legacy-stim"})},
        clear=True,
    )
    def test_new_stim_in_grandfathered_dir_with_l1l2_passes(self):
        # The same brand-new stim passes once it carries both layers.
        doc = self._doc(
            ["skill-invocation", "tool-calls", "program"],
            name="brand-new-compliant-stim",
        )
        self.assertEqual(
            _required_l1l2_violations("synthetic-grandfathered-dir", doc), []
        )

    def test_eventhouse_pilot_is_not_grandfathered_and_passes(self):
        # The pilot is the worked example: it is NOT in the grandfather set,
        # and its real eval.yaml carries both tool-calls and program graders,
        # so the hard rule passes for it.
        self.assertNotIn("eventhouse-authoring-cli", L1L2_GRANDFATHERED)
        pilot = EVALS_DIR / "eventhouse-authoring-cli" / "eval.yaml"
        self.assertTrue(
            pilot.is_file(),
            f"expected pilot eval at {pilot.relative_to(REPO_ROOT)}",
        )
        doc = _load_eval_yaml_or_none(pilot)
        self.assertIsNotNone(doc, "pilot eval.yaml must parse")
        self.assertEqual(
            _required_l1l2_violations("eventhouse-authoring-cli", doc),
            [],
            "eventhouse-authoring-cli pilot must satisfy the L1+L2 hard rule",
        )


class GrandfatherStaleHelperTests(unittest.TestCase):
    """Unit tests for ``_grandfather_stale_problems`` using synthetic inputs,
    so the stale/graduated/parse-failure edge cases are verified independently
    of the on-disk evals."""

    def test_clean_baseline_has_no_problems(self):
        gf = {"d1": frozenset({"s1"})}
        on_disk = {"d1": {"s1": {"skill-invocation"}}}
        self.assertEqual(_grandfather_stale_problems(gf, {"d1"}, on_disk), [])

    def test_missing_dir_is_reported(self):
        gf = {"gone": frozenset({"s1"})}
        problems = _grandfather_stale_problems(gf, set(), {})
        self.assertEqual(len(problems), 1)
        self.assertIn("not found", problems[0])

    def test_parse_failure_dir_is_not_reported_as_missing(self):
        # eval.yaml present but unparsed: in present_dirs, absent from on_disk.
        # Must NOT be flagged "not found" -- the parse failure is owned by
        # test_every_eval_yaml_parses (the Copilot review edge case).
        gf = {"d1": frozenset({"s1"})}
        self.assertEqual(_grandfather_stale_problems(gf, {"d1"}, {}), [])

    def test_renamed_or_removed_stim_is_reported(self):
        gf = {"d1": frozenset({"old-stim"})}
        on_disk = {"d1": {"different-stim": {"skill-invocation"}}}
        problems = _grandfather_stale_problems(gf, {"d1"}, on_disk)
        self.assertEqual(len(problems), 1)
        self.assertIn("no longer exists", problems[0])

    def test_graduated_stim_is_reported(self):
        gf = {"d1": frozenset({"s1"})}
        on_disk = {"d1": {"s1": {"skill-invocation", L1_SUGGESTED, L2_SUGGESTED}}}
        problems = _grandfather_stale_problems(gf, {"d1"}, on_disk)
        self.assertEqual(len(problems), 1)
        self.assertIn("graduated", problems[0])

    def test_stim_with_only_one_layer_is_not_graduated(self):
        # A baseline stim with L1 but not L2 (or vice versa) is still legacy
        # debt -- it has NOT graduated and must stay in the baseline.
        gf = {"d1": frozenset({"s1"})}
        on_disk = {"d1": {"s1": {"skill-invocation", L1_SUGGESTED}}}
        self.assertEqual(_grandfather_stale_problems(gf, {"d1"}, on_disk), [])


class L0ExemptValidationHelperTests(unittest.TestCase):
    """Unit tests for ``_unknown_l0_exempt_names`` using synthetic docs."""

    @staticmethod
    def _doc(l0_exempt):
        return {
            "stimuli": [
                {
                    "name": "synthetic-stim",
                    "graders": [{"type": "skill-invocation"}],
                    "l0_exempt": l0_exempt,
                }
            ]
        }

    def test_known_names_pass(self):
        doc = self._doc(["skill-invocation", "positive-output-assertion"])
        self.assertEqual(_unknown_l0_exempt_names(doc), [])

    def test_unknown_name_is_reported(self):
        doc = self._doc(["skill-invokation"])  # typo of skill-invocation
        result = _unknown_l0_exempt_names(doc)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "synthetic-stim")
        self.assertEqual(result[0][1], ["skill-invokation"])

    def test_skill_name_is_rejected(self):
        # A skill name (not a grader-type name) must be flagged.
        doc = self._doc(["eventhouse-authoring-cli"])
        result = _unknown_l0_exempt_names(doc)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], ["eventhouse-authoring-cli"])

    def test_missing_l0_exempt_is_clean(self):
        doc = {
            "stimuli": [
                {"name": "s", "graders": [{"type": "skill-invocation"}]}
            ]
        }
        self.assertEqual(_unknown_l0_exempt_names(doc), [])


class L1L2ExemptHelperTests(unittest.TestCase):
    """Unit tests for ``_l1l2_exempt_reasons`` and ``_l1l2_exempt_problems``
    using synthetic docs."""

    @staticmethod
    def _doc(l1l2_exempt, include=True):
        stim = {
            "name": "synthetic-stim",
            "graders": [{"type": "skill-invocation"}],
        }
        if include:
            stim["l1l2_exempt"] = l1l2_exempt
        return {"stimuli": [stim]}

    def test_valid_reason_is_collected(self):
        doc = self._doc("offline JSON translation; nothing built in Fabric")
        self.assertEqual(
            _l1l2_exempt_reasons(doc),
            {"synthetic-stim": "offline JSON translation; nothing built in Fabric"},
        )
        self.assertEqual(_l1l2_exempt_problems(doc), [])

    def test_reason_is_stripped(self):
        doc = self._doc("  padded reason  ")
        self.assertEqual(_l1l2_exempt_reasons(doc), {"synthetic-stim": "padded reason"})

    def test_missing_field_is_clean(self):
        doc = self._doc(None, include=False)
        self.assertEqual(_l1l2_exempt_reasons(doc), {})
        self.assertEqual(_l1l2_exempt_problems(doc), [])

    def test_empty_string_is_problem_not_exemption(self):
        doc = self._doc("   ")
        self.assertEqual(_l1l2_exempt_reasons(doc), {})
        problems = _l1l2_exempt_problems(doc)
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0][0], "synthetic-stim")

    def test_non_string_is_problem(self):
        doc = self._doc(True)
        self.assertEqual(_l1l2_exempt_reasons(doc), {})
        self.assertEqual(len(_l1l2_exempt_problems(doc)), 1)

    def test_exempt_stim_is_not_an_l1l2_violation(self):
        # A non-grandfathered eval dir whose only stim is l1l2_exempt (and has
        # no tool-calls/program graders) must NOT produce an L1+L2 violation.
        doc = self._doc("offline; nothing to verify")
        self.assertEqual(
            _required_l1l2_violations("brand-new-offline-eval", doc), []
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
