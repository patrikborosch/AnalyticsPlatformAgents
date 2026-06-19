// Unit tests for .github/scripts/vally-pr-comment.js -- run with the built-in
// Node test runner: `node --test tests/test_vally_pr_comment.js`.
//
// No additional dependencies. Verifies the pure render helpers used by the
// fabric-smoke-vally.yml post-comment job (one comment is posted per run):
//   - normaliseFailures sorts by (skill, stim) and defaults rootCause
//   - classBreakdown counts per root cause, worst-first
//   - resolveHeadline picks clean / comment-only / gating / did-not-complete
//   - a hard Gate A failure (results present) renders the gating failure set,
//     NOT a did-not-complete headline (the summarise job exits 1 after emitting
//     results, so its job result is 'failure' even though results exist)
//   - buildBody renders marker + headline + breakdown table + failing-stim list

'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const mod = require(path.resolve(__dirname, '..', '.github', 'scripts', 'vally-pr-comment.js'));

const {
  MARKER,
  normaliseFailures,
  classBreakdown,
  hasResults,
  resolveHeadline,
  buildBody,
} = mod;

const F = (skill, stim, rootCause) => ({ skill, stim, rootCause });

test('normaliseFailures sorts by (skill, stim) and defaults rootCause', () => {
  const out = normaliseFailures([F('b', '2'), F('a', '2', 'X'), F('a', '1')]);
  assert.deepEqual(out.map((f) => `${f.skill}/${f.stim}`), ['a/1', 'a/2', 'b/2']);
  assert.equal(out[0].rootCause, 'Other'); // default applied
  assert.equal(out[1].rootCause, 'X');
});

test('normaliseFailures drops malformed entries', () => {
  const out = normaliseFailures([null, 5, {}, { skill: '', stim: '' }, F('a', '1', 'Y')]);
  assert.equal(out.length, 1);
  assert.equal(out[0].skill, 'a');
});

test('classBreakdown counts per class, worst-first', () => {
  const b = classBreakdown([F('a', '1', 'X'), F('b', '2', 'Y'), F('c', '3', 'X')]);
  assert.deepEqual(b, [{ rootCause: 'X', count: 2 }, { rootCause: 'Y', count: 1 }]);
});

test('resolveHeadline: clean run is a check', () => {
  const { icon } = resolveHeadline({ gatingStimTotal: 56, gatingStimFailed: 0, gateMode: 'comment-only' });
  assert.equal(icon, '\u2705');
});

test('resolveHeadline: comment-only with failures is a warning (not blocking)', () => {
  const { icon, headline } = resolveHeadline({ gatingStimTotal: 56, gatingStimFailed: 22, gateMode: 'comment-only' });
  assert.equal(icon, '\u26a0\ufe0f');
  assert.match(headline, /comment-only/);
});

test('resolveHeadline: gating with failures is an X', () => {
  const { icon, headline } = resolveHeadline({ gatingStimTotal: 56, gatingStimFailed: 3, gateMode: 'gating' });
  assert.equal(icon, '\u274c');
  assert.match(headline, /FAILED \(gating\)/);
});

test('resolveHeadline: a crash with no results is a did-not-complete warning', () => {
  const { icon, headline } = resolveHeadline({
    gatingStimTotal: 0, stimTotal: 0, gatingStimFailed: 0, gateMode: 'comment-only',
    summariseResult: 'failure', failures: [],
  });
  assert.equal(icon, '\u26a0\ufe0f');
  assert.match(headline, /did not complete/);
  assert.doesNotMatch(headline, /passed/);
});

test('resolveHeadline: a 0/0 with summariseResult=success is a warning, never a green pass', () => {
  // Defense-in-depth invariant: end-to-end the summarise job exits 1 on a
  // zero-trial total, but the pure function must not green a 0/0 even when
  // summariseResult is reported as success.
  const { icon, headline } = resolveHeadline({
    gatingStimTotal: 0, stimTotal: 0, gatingStimFailed: 0, gateMode: 'comment-only',
    summariseResult: 'success', failures: [],
  });
  assert.equal(icon, '\u26a0\ufe0f');
  assert.doesNotMatch(headline, /passed/);
  assert.match(headline, /no stims/i);
});

test('resolveHeadline: log-only fallback (gatingTotal 0 but stimTotal > 0) warns WITHOUT claiming "no stims"', () => {
  // results.jsonl missing -> Aggregate-VallyResults populates no per-stim
  // gating keys (gatingStimTotal stays 0), but pass (b) counts real stims from
  // vally-run.log (stimTotal > 0). Stims DID run, so the headline must not say
  // "no stims (0/0)"; it must stay a warning (a 0 gating total never greens)
  // and name the executed stim count + the unavailable gating data.
  const { icon, headline } = resolveHeadline({
    gatingStimTotal: 0, stimTotal: 45, gatingStimFailed: 0, gateMode: 'comment-only',
    summariseResult: 'success', failures: [],
  });
  assert.equal(icon, '\u26a0\ufe0f');
  assert.doesNotMatch(headline, /passed/);
  assert.doesNotMatch(headline, /no stims/i);
  assert.match(headline, /45 stim/);
  assert.match(headline, /log-only fallback/i);
});

test('resolveHeadline: a 0/0 with a summarise failure stays a did-not-complete crash (crash branch precedes the 0/0 guard)', () => {
  const { headline } = resolveHeadline({
    gatingStimTotal: 0, stimTotal: 0, gatingStimFailed: 0, gateMode: 'comment-only',
    summariseResult: 'failure', failures: [],
  });
  assert.match(headline, /did not complete/);
  assert.doesNotMatch(headline, /no stims/i);
});

test('resolveHeadline: a normal full pass (56/56, summarise success) still greens', () => {
  const { icon, headline } = resolveHeadline({
    gatingStimTotal: 56, gatingStimFailed: 0, gateMode: 'comment-only', summariseResult: 'success',
  });
  assert.equal(icon, '\u2705');
  assert.match(headline, /passed: 56\/56/);
});

test('resolveHeadline: a hard Gate A failure (results present) shows gating, not did-not-complete', () => {
  // VALLY_GATE_ON_STIM_FAIL=true -> summarise emits outputs then exit 1 -> job
  // result 'failure', but results EXIST. Must render the gating headline.
  const { icon, headline } = resolveHeadline({
    gatingStimTotal: 5, stimTotal: 5, gatingStimFailed: 2, gateMode: 'gating',
    summariseResult: 'failure', failures: [F('a', '1', 'X'), F('b', '2', 'Y')],
  });
  assert.equal(icon, '\u274c');
  assert.match(headline, /FAILED \(gating\)/);
  assert.doesNotMatch(headline, /did not complete/);
});

test('hasResults: true when counts or failures present, false on an empty crash', () => {
  assert.equal(hasResults({ gatingStimTotal: 5 }), true);
  assert.equal(hasResults({ stimTotal: 3 }), true);
  assert.equal(hasResults({ failures: [F('a', '1', 'X')] }), true);
  assert.equal(hasResults({ gatingStimTotal: 0, stimTotal: 0, failures: [] }), false);
  assert.equal(hasResults({}), false);
});

test('buildBody renders marker, headline, breakdown table and failing list', () => {
  const body = buildBody({
    runUrl: 'https://x/run/1', stimTotal: 5, gatingStimTotal: 5, gatingStimFailed: 2, gateMode: 'comment-only',
    failures: [F('spark-authoring-cli', 'read parquet', 'WallTimeBudget'), F('sqldw-consumption-cli', 'row count', 'SkillRouting')],
  });
  assert.ok(body.startsWith(MARKER), 'body leads with the marker');
  assert.match(body, /calibration window/);
  assert.match(body, /Failures by root cause/);
  assert.match(body, /\| SkillRouting \| 1 \|/);
  assert.match(body, /\| WallTimeBudget \| 1 \|/);
  assert.match(body, /Failing stims \(2\)/);
  assert.match(body, /`spark-authoring-cli` \/ read parquet -- _WallTimeBudget_/);
});

test('buildBody: hard Gate A failure renders the failure set (not did-not-complete)', () => {
  const body = buildBody({
    runUrl: 'https://x/run/9', stimTotal: 5, gatingStimTotal: 5, gatingStimFailed: 2, gateMode: 'gating',
    summariseResult: 'failure', failures: [F('a', '1', 'X'), F('b', '2', 'Y')],
  });
  assert.match(body, /FAILED \(gating\)/);
  assert.match(body, /Failing stims \(2\)/);
  assert.doesNotMatch(body, /did not complete/);
});

test('buildBody: genuine crash (no results) renders headline + link only', () => {
  const body = buildBody({
    runUrl: 'https://x/run/2', stimTotal: 0, gatingStimTotal: 0, gatingStimFailed: 0, gateMode: 'comment-only',
    summariseResult: 'failure', failures: [],
  });
  assert.match(body, /did not complete/);
  assert.match(body, /No grader results were produced/);
  assert.doesNotMatch(body, /Failures by root cause/);
});

test('renderFailureList (via buildBody) strips backticks/newlines so a stray char cannot break markdown', () => {
  const body = buildBody({
    gatingStimTotal: 1, gatingStimFailed: 1, gateMode: 'comment-only',
    failures: [F('x', 'a`b\nc', 'OutputMatch')],
  });
  const line = body.split('\n').find((l) => l.startsWith('- `x`'));
  assert.ok(line, 'failing-stim bullet is present');
  assert.doesNotMatch(line, /`.*`.*`/); // only the skill stays in backticks; stim backtick stripped
  assert.match(line, /a b c/); // backtick + newline collapsed to spaces
});

test('buildBody escapes a pipe in a root-cause table cell so the column cannot shift', () => {
  // rootCause is a closed enum today, but defend against a future taxonomy
  // value: a raw | in a table cell would silently break column alignment.
  const body = buildBody({
    gatingStimTotal: 1, gatingStimFailed: 1, gateMode: 'comment-only',
    failures: [F('x', '1', 'Weird|Class')],
  });
  const row = body.split('\n').find((l) => l.startsWith('| Weird'));
  assert.ok(row, 'root-cause table row is present');
  assert.match(row, /\| Weird\\\|Class \| 1 \|/); // pipe escaped as \|
});
