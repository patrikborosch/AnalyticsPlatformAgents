// Pure functions for building the PR-touched smoke comment and computing
// signal-change transitions. No GitHub API dependency -- the workflow wraps
// these with octokit calls.
//
// Two comment kinds:
//   1. Sticky:     one per PR, updated in place on every push, marker
//                  <!-- fabric-smoke-pr-touched -->
//   2. Transition: append-only audit trail, posted at the bottom ONLY when
//                  the failed-test set changes or the auth gate flips,
//                  marker <!-- fabric-smoke-pr-touched-transition -->.
//                  Touched-skill set changes alone do NOT trigger a
//                  transition (they're noted in the body if other signals
//                  also changed).
//
// State is embedded in the sticky as an HTML-commented JSON blob so the
// next run can reliably diff. Old-format sticky bodies (without the JSON)
// are parsed via a regex fallback so existing PRs migrate cleanly with no
// spurious transition comment on the first new-format run.

'use strict';

// -----------------------------------------------------------------------------
// Naming glossary (three layers, similar names, different semantics)
// -----------------------------------------------------------------------------
//   Layer            | Composite display       | Clean CSV / state
//   -----------------+-------------------------+----------------------
//   Workflow output  | `touched-skills`        | `touched-skill-names`
//   Workflow env     | `TOUCHED_SKILLS`        | `TOUCHED_SKILL_NAMES`
//   Helper state     | `selectionReason`       | `touchedSkills`
//
// The right column is what gets persisted/diffed; the left column is
// display-only and may contain commas inside parens (e.g.
// "(plugins: a,b) + (tests.json: c,d)"). Crossing the two -- e.g. feeding
// `selectionReason` into `state.touchedSkills` -- is the root cause of
// every diff-vs-render bug we've seen so far.
// -----------------------------------------------------------------------------

const STICKY_MARKER = '<!-- fabric-smoke-pr-touched -->';
const TRANSITION_MARKER = '<!-- fabric-smoke-pr-touched-transition -->';
const STATE_PREFIX = '<!-- state:';
const STATE_SUFFIX = ' -->';

// Coerce any input to a non-negative integer; treat NaN / null / undefined as 0.
// Centralises the parseInt(_, 10) || 0 pattern that appears across encode,
// build, normalize, and parse paths.
const toInt = (v) => parseInt(v, 10) || 0;

// Frozen default for the "no prior sticky" branch of diffStates so we don't
// reallocate an identical literal on every call and don't visually split
// the function body with a 6-line constant.
const EMPTY_PREV = Object.freeze({
  authReady: false,
  smokeResult: null,
  pass: 0, fail: 0, flaky: 0, total: 0,
  touchedSkills: [], failedTests: [],
});

// Build the sticky body from a fully-resolved state object.
// state shape:
//   { authReady, authMode, smokeResult, total, pass, flaky, fail,
//     touchedSkills: string[], selectionReason?: string,
//     matchedTests: string[], matchedCount?: string|number,
//     failedTests: string[],
//     headSha, runUrl }
//
// touchedSkills is the clean kebab-case folder list (used for diff/persistence).
// selectionReason is the human-readable composite from the detect step
// (e.g. "(infrastructure: ...)" or "skill-a + (tests.json: t1,t2)").
// It is displayed verbatim when there is no clean folder list to show; it is
// NEVER fed into state.touchedSkills.
// matchedCount is the upstream-authoritative count string from detect
// (the 'matched-test-count' output). May be the sentinel 'all' for the
// full-catalog fallback paths; otherwise a numeric string. When omitted
// the display falls back to matchedTests.length (legacy behavior). The
// upstream value is the source of truth because matchedTests is the
// concrete test-name list and is empty for full-catalog runs (the
// 'all' sentinel is NOT a test name -- inserting it as one rendered as
// "Matched tests (1): `all`" which misled reviewers about catalog
// breadth).
// Classify the headline (icon + headline text) from a resolved state.
// Pure function of `state`, extracted so the classification table can be
// unit-tested directly without round-tripping through buildStickyBody.
function resolveHeadline(state) {
  const { authReady, authMode, smokeResult, total, pass, flaky, fail } = state;
  const failNum = toInt(fail);
  if (authReady === 'false' || authReady === false) {
    return {
      icon: '\u23ed\ufe0f', // skip
      headline: `PR-touched smoke skipped -- auth gate not configured (mode: ${authMode || 'skip'}). Configure either Phase A (SP_APP_ID + SP_CERT_BASE64 + SP_OBJECT_ID + TENANT_DOMAIN) or Phase B (AZURE_CLIENT_ID + KV) secrets.`,
    };
  }
  if (smokeResult === 'success' && failNum === 0) {
    return {
      icon: '\u2705', // check
      headline: `PR-touched smoke passed: ${pass}/${total} (flaky: ${flaky}, fail: ${fail})`,
    };
  }
  if (smokeResult === 'success' && failNum > 0) {
    return {
      icon: '\u26a0\ufe0f', // warning
      headline: `PR-touched smoke: ${pass}/${total} passed (flaky: ${flaky}, fail: ${fail}) -- ${fail} non-flaky failure(s). Check stays green (observation-grade); review failures below.`,
    };
  }
  if (smokeResult === 'failure') {
    return {
      icon: '\u274c', // X
      headline: `PR-touched smoke FAILED: ${pass}/${total} (flaky: ${flaky}, fail: ${fail})`,
    };
  }
  if (smokeResult === 'skipped') {
    return {
      icon: '\u23ed\ufe0f',
      headline: `PR-touched smoke skipped at orchestrator level.`,
    };
  }
  return {
    icon: '\u26a0\ufe0f',
    headline: `PR-touched smoke result: ${smokeResult}`,
  };
}

// Build the sticky body from a fully-resolved state object.
// state shape:
//   { authReady, authMode, smokeResult, total, pass, flaky, fail,
//     touchedSkills: string[], selectionReason?: string,
//     matchedTests: string[], matchedCount?: string|number,
//     failedTests: string[],
//     headSha, runUrl }
//
// touchedSkills is the clean kebab-case folder list (used for diff/persistence).
// selectionReason is the human-readable composite from the detect step
// (e.g. "(infrastructure: ...)" or "skill-a + (tests.json: t1,t2)").
// It is displayed verbatim when there is no clean folder list to show; it is
// NEVER fed into state.touchedSkills.
// matchedCount is the upstream-authoritative count string from detect
// (the 'matched-test-count' output). May be the sentinel 'all' for the
// full-catalog fallback paths; otherwise a numeric string. When omitted
// the display falls back to matchedTests.length (legacy behavior). The
// upstream value is the source of truth because matchedTests is the
// concrete test-name list and is empty for full-catalog runs (the
// 'all' sentinel is NOT a test name -- inserting it as one rendered as
// "Matched tests (1): `all`" which misled reviewers about catalog
// breadth).
function buildStickyBody(state) {
  const {
    touchedSkills,
    selectionReason,
    matchedTests,
    matchedCount,
    failedTests,
    runUrl,
  } = state;

  const { icon, headline } = resolveHeadline(state);

  // Display priority: clean folder list > selectionReason composite > "(none)".
  // The clean list shows what code paths the smoke actually exercised; the
  // composite reason explains why those (and possibly extra) tests were picked.
  let touchedDisplay;
  if (touchedSkills && touchedSkills.length > 0) {
    touchedDisplay = touchedSkills.join(', ');
  } else if (selectionReason) {
    touchedDisplay = selectionReason;
  } else {
    touchedDisplay = '(none)';
  }
  // Matched-tests rendering. Three cases:
  //   1. matchedCount === 'all' (or numeric 'all'-equivalent string): the
  //      detect job hit a full-catalog fallback (infrastructure touch,
  //      tests.json diff failure, etc.). matchedTests is empty in this
  //      mode -- the workflow strips the 'all' sentinel before passing
  //      the list in. Display "(all) entire catalog" so the reviewer
  //      understands the breadth without seeing a misleading "(1): `all`".
  //   2. matchedCount is a numeric string (or number): use it verbatim
  //      for the count prefix. Trust the upstream value over the array
  //      length so any divergence (e.g. sentinel handling) is visible.
  //   3. matchedCount is undefined (legacy callers / older tests): fall
  //      back to matchedTests.length, preserving the old behavior.
  const matchedListLength = (matchedTests || []).length;
  const matchedDisplay = matchedListLength > 0
    ? matchedTests.join(', ')
    : '(none)';
  const isAllSentinel = matchedCount === 'all' || matchedCount === 'ALL';
  let matchedLine;
  if (isAllSentinel) {
    matchedLine = `**Matched tests (all):** _entire catalog_`;
  } else {
    const displayedCount = matchedCount !== undefined && matchedCount !== null
      ? String(matchedCount)
      : String(matchedListLength);
    matchedLine = `**Matched tests (${displayedCount}):** \`${matchedDisplay}\``;
  }

  const lines = [
    STICKY_MARKER,
    encodeState(state),
    `### ${icon} ${headline}`,
    ``,
    `**Touched skills (${touchedSkills.length}):** \`${touchedDisplay}\``,
    matchedLine,
    ``,
  ];
  if (failedTests.length > 0) {
    lines.push(`**Failed tests (${failedTests.length} non-flaky):**`);
    for (const name of failedTests) {
      lines.push(`- \`${name}\``);
    }
    lines.push(``);
    lines.push(`> If any of these tests cover the skills you modified in this PR, please investigate and fix before merging. Failures in unrelated tests are likely pipeline-side issues -- safe to merge if your touched-skill tests pass.`);
    lines.push(``);
  }
  lines.push(`[View workflow run](${runUrl}) for per-test detail.`);
  lines.push(``);
  lines.push(`<sub>This comment is automatically updated on each push. Signal changes (new failures, recoveries) post as a separate comment below. Nightly smoke at 06:00 UTC runs the full catalog.</sub>`);
  return lines.join('\n');
}

// Serialize the diff-relevant subset of state as an HTML-commented JSON blob.
// Kept minimal so updates to comment text don't drift the parser.
function encodeState(state) {
  const minimal = {
    v: 1,
    authReady: state.authReady === true || state.authReady === 'true',
    smokeResult: state.smokeResult,
    pass: toInt(state.pass),
    fail: toInt(state.fail),
    flaky: toInt(state.flaky),
    total: toInt(state.total),
    touchedSkills: (state.touchedSkills || []).slice().sort(),
    failedTests: (state.failedTests || []).slice().sort(),
  };
  // Escape any '-->' that could prematurely close the HTML comment.
  // Test/skill names are kebab-case so this is defensive, not load-bearing.
  const json = JSON.stringify(minimal).replace(/-->/g, '--\\u003E');
  return `${STATE_PREFIX}${json}${STATE_SUFFIX}`;
}

// Parse the prior sticky body and return its embedded state, or null if
// the body has no sticky marker. Returns a best-effort state object when
// the embedded JSON is missing (old format) so PR sticky comments authored
// before this change migrate cleanly without firing a spurious transition.
function parseStickyState(body) {
  if (!body || !body.includes(STICKY_MARKER)) return null;

  // Prefer embedded JSON.
  const startIdx = body.indexOf(STATE_PREFIX);
  if (startIdx !== -1) {
    const endIdx = body.indexOf(STATE_SUFFIX, startIdx);
    if (endIdx !== -1) {
      const json = body.slice(startIdx + STATE_PREFIX.length, endIdx);
      try {
        const parsed = JSON.parse(json);
        return normalizeState(parsed);
      } catch (e) {
        // fall through to regex parse
      }
    }
  }

  // Fallback for old-format bodies (no embedded JSON).
  return parseLegacyStickyBody(body);
}

function parseLegacyStickyBody(body) {
  const state = {
    v: 0, // legacy
    authReady: !body.includes('PR-touched smoke skipped -- auth gate'),
    smokeResult: inferLegacyResult(body),
    pass: 0,
    fail: 0,
    flaky: 0,
    total: 0,
    touchedSkills: [],
    failedTests: [],
  };

  // Counts line. Three legacy body shapes share a 4-capture suffix
  // (flaky/fail), so one alternation covers all three:
  //   - "passed: X/Y (flaky: F, fail: G)"          (success, no failures)
  //   - ": X/Y passed (flaky: F, fail: G)"          (success with non-flaky failures)
  //   - "FAILED: X/Y (flaky: F, fail: G)"           (failure)
  const counts = body.match(/(?:passed:|FAILED:)? ?(\d+)\/(\d+)(?: passed)? \(flaky: (\d+), fail: (\d+)\)/);
  if (counts) {
    state.pass = toInt(counts[1]);
    state.total = toInt(counts[2]);
    state.flaky = toInt(counts[3]);
    state.fail = toInt(counts[4]);
  }

  // Touched skills line: "**Touched skills (N):** `a, b, c`"
  const touchedLine = body.match(/\*\*Touched skills \(\d+\):\*\* `([^`]*)`/);
  if (touchedLine && touchedLine[1] && touchedLine[1] !== '(none)') {
    state.touchedSkills = touchedLine[1].split(',').map((s) => s.trim()).filter(Boolean).sort();
  }

  // Failed-tests bulleted block.
  const failedMatch = body.match(/\*\*Failed tests \((\d+) non-flaky\):\*\*\n([\s\S]*?)(?:\n\n|\n>)/);
  if (failedMatch) {
    const block = failedMatch[2];
    const names = [];
    const lineRegex = /- `([^`]+)`/g;
    let m;
    while ((m = lineRegex.exec(block)) !== null) {
      names.push(m[1]);
    }
    state.failedTests = names.sort();
  }

  return state;
}

function inferLegacyResult(body) {
  if (body.includes('PR-touched smoke FAILED')) return 'failure';
  if (body.includes('PR-touched smoke passed')) return 'success';
  if (body.includes('non-flaky failure(s)')) return 'success';
  if (body.includes('skipped')) return 'skipped';
  return 'unknown';
}

function normalizeState(s) {
  return {
    v: s.v ?? 1,
    authReady: s.authReady === true || s.authReady === 'true',
    smokeResult: s.smokeResult || 'unknown',
    pass: toInt(s.pass),
    fail: toInt(s.fail),
    flaky: toInt(s.flaky),
    total: toInt(s.total),
    touchedSkills: Array.isArray(s.touchedSkills) ? s.touchedSkills.slice().sort() : [],
    failedTests: Array.isArray(s.failedTests) ? s.failedTests.slice().sort() : [],
  };
}

// Compute diff between two state objects. Either side may be null
// (first run, no sticky yet).
function diffStates(prior, current) {
  const cur = normalizeState(current);
  const isFirstRun = prior === null;
  const prev = prior ? normalizeState(prior) : EMPTY_PREV;

  const prevFailed = new Set(prev.failedTests);
  const curFailed = new Set(cur.failedTests);

  const touchedChanged = !sameSet(prev.touchedSkills, cur.touchedSkills);
  const authChanged = prev.smokeResult !== null && prev.authReady !== cur.authReady;

  // When either side is auth-skipped, tests didn't actually run on that side,
  // so failed-set diffs are meaningless (and worse: a skip after red would
  // look like every test "recovered"). Zero the failed-set diffs in that case;
  // the authChanged flag is the only signal worth surfacing.
  const authSkippedEitherSide = prev.authReady === false || cur.authReady === false;
  const newlyFailing = authSkippedEitherSide
    ? []
    : cur.failedTests.filter((t) => !prevFailed.has(t));
  const recovered = authSkippedEitherSide
    ? []
    : prev.failedTests.filter((t) => !curFailed.has(t));
  const stillFailing = authSkippedEitherSide
    ? []
    : cur.failedTests.filter((t) => prevFailed.has(t));

  return {
    isFirstRun,
    isLegacyMigration: !isFirstRun && (prior.v === 0),
    newlyFailing,
    recovered,
    stillFailing,
    touchedChanged,
    authChanged,
    prev,
    cur,
  };
}

function sameSet(a, b) {
  // normalizeState sorts both inputs; this can assume index-aligned comparison.
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

// Decide whether to post a transition comment.
//
// Rules:
//   - First run on a PR with no prior sticky: post initial state.
//   - Legacy-format prior sticky (migration): do NOT post -- the diff is
//     a one-time artifact of the upgrade.
//   - Otherwise: post when the failed-test set CHANGED (newlyFailing OR
//     recovered is non-empty). Flaky-only deltas, total-count changes
//     with same failed set, and pure no-ops stay silent.
//   - Auth state flip (skip <-> run) is also worth a ping.
function shouldPostTransition(diff) {
  if (diff.isLegacyMigration) return false;
  if (diff.isFirstRun) return true;
  if (diff.newlyFailing.length > 0 || diff.recovered.length > 0) return true;
  if (diff.authChanged) return true;
  return false;
}

// Classify the verb (icon + verb text) for a transition comment from a diff
// and the current state. Pure function, extracted so the classification table
// can be unit-tested directly without round-tripping through
// buildTransitionBody. The order of branches matters: auth flips come before
// failure-set verbs so a skip-after-red never reports "recovered".
function resolveVerb(diff, cur) {
  if (diff.isFirstRun) {
    if (cur.authReady === false) return { icon: '\u23ed\ufe0f', verb: 'skipped (auth gate)' };
    if (cur.fail > 0) return { icon: '\u274c', verb: `started red (${cur.fail} failure${cur.fail === 1 ? '' : 's'})` };
    if (cur.smokeResult === 'failure') return { icon: '\u274c', verb: 'started red' };
    return { icon: '\u2705', verb: 'started green' };
  }
  if (diff.authChanged) {
    return {
      icon: '\u23ed\ufe0f',
      verb: cur.authReady ? 'auth gate cleared' : 'auth gate engaged',
    };
  }
  if (diff.newlyFailing.length > 0 && diff.recovered.length === 0 && diff.stillFailing.length === 0) {
    return { icon: '\u274c', verb: 'went red' };
  }
  if (diff.recovered.length > 0 && diff.newlyFailing.length === 0 && cur.fail === 0) {
    return { icon: '\u2705', verb: 'recovered' };
  }
  if (diff.newlyFailing.length > 0 || diff.recovered.length > 0) {
    return { icon: '\ud83d\udfe1', verb: 'changed (failure set updated)' };
  }
  return { icon: '\u2139\ufe0f', verb: 'updated' };
}

// Build the transition comment body.
//
// Format:
//   <!-- fabric-smoke-pr-touched-transition -->
//   <emoji> **Smoke <verb> on <short-sha>**
//   - Newly failing: `a`, `b`
//   - Recovered: `c`
//   - Still failing: `d`
//   [Sticky details](#issuecomment-<id>) | [Workflow run](<url>)
function buildTransitionBody({ diff, current, runUrl, shortSha, stickyCommentUrl }) {
  const cur = normalizeState(current);
  const { icon, verb } = resolveVerb(diff, cur);

  const lines = [
    TRANSITION_MARKER,
    `${icon} **Smoke ${verb}** on \`${shortSha || 'HEAD'}\` -- ${cur.pass}/${cur.total} passing (flaky: ${cur.flaky}, fail: ${cur.fail}).`,
    ``,
  ];
  if (diff.newlyFailing.length > 0) {
    lines.push(`- \ud83d\udd34 Newly failing: ${formatList(diff.newlyFailing)}`);
  }
  if (diff.recovered.length > 0) {
    lines.push(`- \ud83d\udfe2 Recovered: ${formatList(diff.recovered)}`);
  }
  if (diff.stillFailing.length > 0 && (diff.newlyFailing.length > 0 || diff.recovered.length > 0)) {
    lines.push(`- \ud83d\udfe1 Still failing: ${formatList(diff.stillFailing)}`);
  }
  if (diff.touchedChanged && !diff.isFirstRun) {
    lines.push(`- \ud83d\udcdd Touched-skill set changed.`);
  }
  if (lines[lines.length - 1] !== ``) lines.push(``);
  const links = [];
  if (stickyCommentUrl) links.push(`[Sticky details](${stickyCommentUrl})`);
  links.push(`[Workflow run](${runUrl})`);
  lines.push(links.join(' | '));
  return lines.join('\n');
}

function formatList(arr) {
  return arr.map((n) => `\`${n}\``).join(', ');
}

module.exports = {
  STICKY_MARKER,
  TRANSITION_MARKER,
  buildStickyBody,
  encodeState,
  parseStickyState,
  parseLegacyStickyBody,
  normalizeState,
  diffStates,
  resolveHeadline,
  resolveVerb,
  shouldPostTransition,
  buildTransitionBody,
};
