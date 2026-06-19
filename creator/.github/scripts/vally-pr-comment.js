// Pure functions for rendering the Vally PR comment body. No GitHub API
// dependency -- the workflow (fabric-smoke-vally.yml post-comment job) wraps
// buildBody with a single octokit createComment call.
//
// Posting model: ONE NEW COMMENT PER RUN (not a sticky). While the suite is
// still being stabilised, a fresh comment per run gives a chronological history
// on the PR conversation tab. Because each comment is self-contained, this
// helper carries NO state between runs and renders no run-over-run diff -- just
// this run's failure set grouped by the root-cause class
// Classify-VallyFailure.ps1 computes.
//
// Why a comment at all during the calibration window: the merge gate (Gate A)
// is comment-only until VALLY_GATE_ON_STIM_FAIL flips to 'true'. While
// comment-only, the failure signal must still reach the reviewer; this comment
// surfaces the per-stim failure set without the reviewer opening the job
// summary.

'use strict';

const MARKER = '<!-- fabric-smoke-vally -->';

// Coerce any input to a non-negative integer; NaN / null / undefined -> 0.
const toInt = (v) => {
  const n = parseInt(v, 10);
  return Number.isFinite(n) && n >= 0 ? n : 0;
};

// Escape a value for a markdown TABLE cell: a pipe breaks the column and a
// newline breaks the row. rootCause is a closed classifier enum today, but
// escape defensively so a future taxonomy value cannot corrupt the table.
const mdCell = (s) => String(s).replace(/[\r\n]+/g, ' ').replace(/\|/g, '\\|').trim();

// Normalise a raw failures array (any shape) into the canonical
// [{skill, stim, rootCause}] list, dropping malformed entries. Sorted by
// (skill, stim) so the rendered list is deterministic.
function normaliseFailures(failures) {
  if (!Array.isArray(failures)) return [];
  const out = [];
  for (const f of failures) {
    if (!f || typeof f !== 'object') continue;
    const skill = String(f.skill ?? '').trim();
    const stim = String(f.stim ?? '').trim();
    if (!skill && !stim) continue;
    out.push({
      skill: skill || '(unknown-skill)',
      stim: stim || '(unknown-stim)',
      rootCause: String(f.rootCause ?? 'Other').trim() || 'Other',
    });
  }
  out.sort((a, b) =>
    a.skill === b.skill ? a.stim.localeCompare(b.stim) : a.skill.localeCompare(b.skill),
  );
  return out;
}

// Count failures per root-cause class, returned as an array of {rootCause,
// count} sorted by descending count then class name (worst-offender-first).
function classBreakdown(failures) {
  const counts = new Map();
  for (const f of normaliseFailures(failures)) {
    counts.set(f.rootCause, (counts.get(f.rootCause) || 0) + 1);
  }
  return [...counts.entries()]
    .map(([rootCause, count]) => ({ rootCause, count }))
    .sort((a, b) => (b.count - a.count) || a.rootCause.localeCompare(b.rootCause));
}

// True when the summarise step produced grader results, regardless of whether
// the job then exited non-zero. A hard Gate A failure (VALLY_GATE_ON_STIM_FAIL
// =true) emits the counts + failure set and THEN exit 1, so summariseResult is
// 'failure' even though results exist -- this flag keeps that case from being
// mistaken for a crash that produced nothing.
function hasResults(state) {
  const failureCount = Array.isArray(state.failures) ? state.failures.length : 0;
  return toInt(state.gatingStimTotal) > 0 || toInt(state.stimTotal) > 0 || failureCount > 0;
}

// Headline icon + text from a resolved state.
function resolveHeadline(state) {
  // Only treat the run as "did not complete" when summarise did NOT finish
  // successfully AND produced no results (a genuine crash / auth / parser
  // death). A non-success result WITH results present is a hard Gate A failure,
  // which must render its failure breakdown, not a crash headline.
  const runStatus = state.summariseResult || 'success';
  if (runStatus !== 'success' && !hasResults(state)) {
    return {
      icon: '\u26a0\ufe0f', // warning
      headline: `Vally run did not complete (summarise: ${runStatus}). No grader results were produced; open the workflow run for the failure.`,
    };
  }
  const gatingFailed = toInt(state.gatingStimFailed);
  const gatingTotal = toInt(state.gatingStimTotal);
  const stimTotal = toInt(state.stimTotal);
  // Defense-in-depth: a 0 gating total must NEVER render as a green pass. The
  // summarise job already exits 1 when the trial total is 0 (an empty run is
  // a harness/selection failure, not a clean pass), which routes through the
  // "did not complete" branch above. But this pure function must not green a
  // 0 gating total on its own: warn REGARDLESS of summariseResult instead of
  // falling through to the gatingFailed === 0 green branch below.
  if (gatingTotal === 0) {
    // A 0 gating total has two distinct causes; both stay a warning, but the
    // message must not claim "no stims" when stims demonstrably executed:
    //  (a) Genuine empty run -- nothing executed at all (harness/selection
    //      failure): both gating and log-derived stim totals are 0.
    //  (b) Log-only fallback -- results.jsonl was missing, so per-stim gating
    //      keys were never populated, yet pass (b) of Aggregate-VallyResults
    //      still counted real stims from vally-run.log (stimTotal > 0). Here
    //      stims DID run; only the per-stim gating breakdown is unavailable,
    //      so "no stims (0/0)" would misreport a run that actually executed.
    if (stimTotal > 0) {
      return {
        icon: '\u26a0\ufe0f', // warning
        headline: `Vally executed ${stimTotal} stim(s) but per-stim gating data was unavailable (log-only fallback) -- see the workflow run.`,
      };
    }
    return {
      icon: '\u26a0\ufe0f', // warning
      headline: 'Vally executed no stims (0/0) -- see the workflow run.',
    };
  }
  const passed = Math.max(0, gatingTotal - gatingFailed);
  const gating = state.gateMode === 'gating';
  if (gatingFailed === 0) {
    return {
      icon: '\u2705', // check
      headline: `Vally passed: ${passed}/${gatingTotal} stims clean (all graders).`,
    };
  }
  if (gating) {
    return {
      icon: '\u274c', // X
      headline: `Vally FAILED (gating): ${passed}/${gatingTotal} stims clean, ${gatingFailed} with >=1 grader fail.`,
    };
  }
  return {
    icon: '\u26a0\ufe0f', // warning
    headline: `Vally calibration window: ${passed}/${gatingTotal} stims clean, ${gatingFailed} with >=1 grader fail. Gate is comment-only (not blocking); review the failure set below.`,
  };
}

// Render a failure list as a compact markdown bullet list. skill is a folder
// name and stim is an eval scalar, so backticks/newlines are not expected, but
// they are stripped defensively so a stray character cannot break the markdown.
function renderFailureList(failures) {
  const list = normaliseFailures(failures);
  if (list.length === 0) return '_(none)_';
  const clean = (s) => String(s).replace(/[\r\n`]+/g, ' ').trim();
  return list
    .map((f) => `- \`${clean(f.skill)}\` / ${clean(f.stim)} -- _${clean(f.rootCause)}_`)
    .join('\n');
}

// Build the comment body for a single run. No previous-run state and no diff --
// one fresh comment is posted per run by the workflow.
function buildBody(state) {
  const { icon, headline } = resolveHeadline(state);
  const lines = [];
  lines.push(MARKER);
  lines.push(`### ${icon} ${headline}`);
  lines.push('');
  if (state.runUrl) {
    lines.push(`[Workflow run](${state.runUrl}) -- full per-grader rows + evidence are in the run's job summary.`);
    lines.push('');
  }

  // Genuine crash (no results): headline + run link only.
  if ((state.summariseResult || 'success') !== 'success' && !hasResults(state)) {
    lines.push('_No grader results were produced this run; open the workflow run for the failure._');
    return lines.join('\n');
  }

  const failures = normaliseFailures(state.failures);
  const breakdown = classBreakdown(failures);
  if (breakdown.length > 0) {
    lines.push('**Failures by root cause:**');
    lines.push('');
    lines.push('| Root cause | Count |');
    lines.push('|---|---:|');
    for (const b of breakdown) {
      lines.push(`| ${mdCell(b.rootCause)} | ${b.count} |`);
    }
    lines.push('');
  }

  lines.push(`**Failing stims (${failures.length}):**`);
  lines.push(renderFailureList(failures));
  lines.push('');
  return lines.join('\n');
}

module.exports = {
  MARKER,
  normaliseFailures,
  classBreakdown,
  hasResults,
  resolveHeadline,
  buildBody,
};
