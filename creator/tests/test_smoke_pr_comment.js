// Unit tests for .github/scripts/smoke-pr-comment.js -- run with the
// built-in Node test runner: `node --test tests/test_smoke_pr_comment.js`.
//
// No additional dependencies. Verifies the pure-function helpers used by
// the PR-touched smoke workflow's post-comment step:
//   - sticky body builds with an embedded state JSON
//   - the state JSON round-trips through parseStickyState
//   - legacy-format bodies parse correctly (failed-tests, touched skills)
//   - diffStates detects newly-failing, recovered, no-op, first-run
//   - shouldPostTransition suppresses legacy migration + flaky-only diffs
//   - transition body picks the right verb/icon for common scenarios

'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const mod = require(path.resolve(__dirname, '..', '.github', 'scripts', 'smoke-pr-comment.js'));

const {
  buildStickyBody,
  parseStickyState,
  diffStates,
  shouldPostTransition,
  buildTransitionBody,
  STICKY_MARKER,
  TRANSITION_MARKER,
} = mod;

function baseState(over = {}) {
  return Object.assign({
    authReady: 'true',
    authMode: 'phaseA',
    smokeResult: 'success',
    total: 5,
    pass: 5,
    flaky: 0,
    fail: 0,
    touchedSkills: ['sqldw-consumption-cli'],
    matchedTests: ['sqldw-consumption-cli-basic-query'],
    failedTests: [],
    runUrl: 'https://github.com/o/r/actions/runs/1',
  }, over);
}

test('buildStickyBody embeds state JSON and round-trips', () => {
  const state = baseState({
    fail: 1,
    pass: 4,
    failedTests: ['sqldw-consumption-cli-basic-query'],
  });
  const body = buildStickyBody(state);
  assert.ok(body.includes(STICKY_MARKER), 'must include sticky marker');
  assert.ok(body.includes('<!-- state:'), 'must embed state JSON');

  const parsed = parseStickyState(body);
  assert.ok(parsed, 'parser returns non-null for sticky body');
  assert.equal(parsed.fail, 1);
  assert.equal(parsed.pass, 4);
  assert.deepEqual(parsed.failedTests, ['sqldw-consumption-cli-basic-query']);
  assert.deepEqual(parsed.touchedSkills, ['sqldw-consumption-cli']);
});

test('parseStickyState returns null for unrelated comments', () => {
  assert.equal(parseStickyState('just a normal comment'), null);
  assert.equal(parseStickyState(''), null);
  assert.equal(parseStickyState(null), null);
});

test('parseStickyState falls back to legacy regex parser', () => {
  const legacyBody = [
    STICKY_MARKER,
    '### \u26a0\ufe0f PR-touched smoke: 3/5 passed (flaky: 1, fail: 1) -- 1 non-flaky failure(s). Check stays green',
    '',
    '**Touched skills (2):** `sqldw-consumption-cli, dataflows-consumption-cli`',
    '**Matched tests (2):** `sqldw-consumption-cli-basic-query, dataflows-consumption-cli-list`',
    '',
    '**Failed tests (1 non-flaky):**',
    '- `sqldw-consumption-cli-basic-query`',
    '',
    '> If any of these tests cover the skills you modified',
    '',
    '[View workflow run](https://github.com/o/r/actions/runs/1)',
  ].join('\n');

  const parsed = parseStickyState(legacyBody);
  assert.ok(parsed, 'legacy body parses');
  assert.equal(parsed.v, 0, 'legacy marker');
  assert.equal(parsed.pass, 3);
  assert.equal(parsed.total, 5);
  assert.equal(parsed.flaky, 1);
  assert.equal(parsed.fail, 1);
  assert.deepEqual(parsed.touchedSkills.sort(), ['dataflows-consumption-cli', 'sqldw-consumption-cli']);
  assert.deepEqual(parsed.failedTests, ['sqldw-consumption-cli-basic-query']);
});

test('diffStates flags first-run when no prior sticky', () => {
  const diff = diffStates(null, baseState());
  assert.equal(diff.isFirstRun, true);
  assert.equal(diff.isLegacyMigration, false);
  assert.deepEqual(diff.newlyFailing, []);
  assert.deepEqual(diff.recovered, []);
});

test('diffStates detects newly-failing test', () => {
  const prior = parseStickyState(buildStickyBody(baseState()));
  const cur = baseState({
    fail: 1,
    pass: 4,
    smokeResult: 'success',
    failedTests: ['sqldw-consumption-cli-basic-query'],
  });
  const diff = diffStates(prior, cur);
  assert.equal(diff.isFirstRun, false);
  assert.deepEqual(diff.newlyFailing, ['sqldw-consumption-cli-basic-query']);
  assert.deepEqual(diff.recovered, []);
  assert.deepEqual(diff.stillFailing, []);
});

test('diffStates detects recovery', () => {
  const priorState = baseState({
    fail: 1, pass: 4,
    failedTests: ['sqldw-consumption-cli-basic-query'],
  });
  const prior = parseStickyState(buildStickyBody(priorState));
  const cur = baseState(); // all green
  const diff = diffStates(prior, cur);
  assert.deepEqual(diff.recovered, ['sqldw-consumption-cli-basic-query']);
  assert.deepEqual(diff.newlyFailing, []);
});

test('diffStates detects partial change (one recovered, one new)', () => {
  const priorState = baseState({
    fail: 1, pass: 4,
    failedTests: ['test-a'],
  });
  const prior = parseStickyState(buildStickyBody(priorState));
  const cur = baseState({
    fail: 1, pass: 4,
    failedTests: ['test-b'],
  });
  const diff = diffStates(prior, cur);
  assert.deepEqual(diff.newlyFailing, ['test-b']);
  assert.deepEqual(diff.recovered, ['test-a']);
  assert.deepEqual(diff.stillFailing, []);
});

test('diffStates with same failure set finds no change (flaky-only delta is silent)', () => {
  const priorState = baseState({
    fail: 1, pass: 3, flaky: 1, total: 5,
    failedTests: ['test-x'],
  });
  const prior = parseStickyState(buildStickyBody(priorState));
  // Same failure, but flaky count changed
  const cur = baseState({
    fail: 1, pass: 3, flaky: 0, total: 5,
    failedTests: ['test-x'],
  });
  const diff = diffStates(prior, cur);
  assert.deepEqual(diff.newlyFailing, []);
  assert.deepEqual(diff.recovered, []);
  assert.equal(shouldPostTransition(diff), false, 'flaky-only delta stays silent');
});

test('diffStates flags touched-skill set change', () => {
  const prior = parseStickyState(buildStickyBody(baseState({ touchedSkills: ['skill-a'] })));
  const cur = baseState({ touchedSkills: ['skill-a', 'skill-b'] });
  const diff = diffStates(prior, cur);
  assert.equal(diff.touchedChanged, true);
});

test('shouldPostTransition: first run posts', () => {
  const diff = diffStates(null, baseState());
  assert.equal(shouldPostTransition(diff), true);
});

test('shouldPostTransition: legacy migration does NOT post', () => {
  const legacyBody = [
    STICKY_MARKER,
    '### \u2705 PR-touched smoke passed: 5/5 (flaky: 0, fail: 0)',
    '',
    '**Touched skills (1):** `skill-a`',
    '**Matched tests (1):** `skill-a-test`',
    '',
    '[View workflow run](https://github.com/o/r/actions/runs/1)',
  ].join('\n');
  const prior = parseStickyState(legacyBody);
  assert.equal(prior.v, 0, 'parser flagged as legacy');
  const cur = baseState();
  const diff = diffStates(prior, cur);
  assert.equal(diff.isLegacyMigration, true);
  assert.equal(shouldPostTransition(diff), false, 'migration is silent');
});

test('shouldPostTransition: same state no-op stays silent', () => {
  const s = baseState({ fail: 1, pass: 4, failedTests: ['t1'] });
  const prior = parseStickyState(buildStickyBody(s));
  const diff = diffStates(prior, s);
  assert.equal(shouldPostTransition(diff), false);
});

test('shouldPostTransition: auth flip from skip to ready posts', () => {
  const prior = parseStickyState(buildStickyBody(baseState({
    authReady: 'false', smokeResult: 'success', pass: 0, total: 0,
  })));
  const cur = baseState();
  const diff = diffStates(prior, cur);
  assert.equal(diff.authChanged, true);
  assert.equal(shouldPostTransition(diff), true);
});

test('buildTransitionBody: first-run green', () => {
  const cur = baseState();
  const diff = diffStates(null, cur);
  const body = buildTransitionBody({
    diff, current: cur,
    runUrl: cur.runUrl, shortSha: 'abc1234',
    stickyCommentUrl: 'https://github.com/o/r/pull/1#issuecomment-99',
  });
  assert.ok(body.includes(TRANSITION_MARKER));
  assert.ok(body.includes('started green'));
  assert.ok(body.includes('abc1234'));
  assert.ok(body.includes('Sticky details'));
});

test('buildTransitionBody: went red lists newly-failing', () => {
  const prior = parseStickyState(buildStickyBody(baseState()));
  const cur = baseState({ fail: 1, pass: 4, failedTests: ['skill-x-test'] });
  const diff = diffStates(prior, cur);
  const body = buildTransitionBody({
    diff, current: cur,
    runUrl: cur.runUrl, shortSha: 'def5678',
  });
  assert.ok(body.includes('went red'));
  assert.ok(body.includes('skill-x-test'));
  assert.ok(body.includes('Newly failing'));
  assert.ok(!body.includes('Recovered'));
});

test('buildTransitionBody: recovered lists recovered tests', () => {
  const prior = parseStickyState(buildStickyBody(baseState({
    fail: 1, pass: 4, failedTests: ['skill-x-test'],
  })));
  const cur = baseState();
  const diff = diffStates(prior, cur);
  const body = buildTransitionBody({
    diff, current: cur, runUrl: cur.runUrl, shortSha: 'aaa',
  });
  assert.ok(body.includes('recovered'));
  assert.ok(body.includes('skill-x-test'));
  assert.ok(body.includes('Recovered'));
  assert.ok(!body.includes('Newly failing'));
});

test('buildTransitionBody: mixed change shows newly + recovered + still', () => {
  const prior = parseStickyState(buildStickyBody(baseState({
    fail: 2, pass: 3, failedTests: ['a', 'b'],
  })));
  const cur = baseState({
    fail: 2, pass: 3, failedTests: ['b', 'c'],
  });
  const diff = diffStates(prior, cur);
  const body = buildTransitionBody({
    diff, current: cur, runUrl: cur.runUrl, shortSha: 'mix',
  });
  assert.ok(body.includes('changed'));
  assert.ok(body.includes('`c`'));   // newly
  assert.ok(body.includes('`a`'));   // recovered
  assert.ok(body.includes('`b`'));   // still
  assert.ok(body.includes('Still failing'));
});

test('auth gate engagement after red does NOT say recovered', () => {
  // Prior: red with 2 failures. Current: auth gate engaged (skip).
  // We must NOT report the 2 prior failures as "recovered" -- tests
  // didn't run; auth simply became unavailable.
  const prior = parseStickyState(buildStickyBody(baseState({
    authReady: 'true',
    fail: 2, pass: 3, total: 5,
    failedTests: ['skill-x-test', 'skill-y-test'],
  })));
  const cur = baseState({
    authReady: 'false',
    authMode: 'skip',
    smokeResult: 'success',
    fail: 0, pass: 0, flaky: 0, total: 0,
    failedTests: [],
  });
  const diff = diffStates(prior, cur);
  assert.equal(diff.authChanged, true);
  assert.deepEqual(diff.recovered, [], 'auth-skip side must not populate recovered');
  assert.deepEqual(diff.newlyFailing, []);
  assert.equal(shouldPostTransition(diff), true);
  const body = buildTransitionBody({
    diff, current: cur, runUrl: cur.runUrl, shortSha: 'auth1',
  });
  assert.ok(body.includes('auth gate engaged'), 'verb must be auth gate engaged');
  assert.ok(!body.includes('recovered'), 'must not mention recovery');
  assert.ok(!body.includes('Recovered:'), 'must not list recovered tests');
});

test('auth gate clearance after skip does NOT say went red', () => {
  // Prior: auth-skipped. Current: auth available, some real failures.
  // Auth flip should be the headline, not "went red" (those failures
  // are the first observation, not a regression).
  const prior = parseStickyState(buildStickyBody(baseState({
    authReady: 'false',
    authMode: 'skip',
    smokeResult: 'success',
    fail: 0, pass: 0, total: 0,
    failedTests: [],
  })));
  const cur = baseState({
    authReady: 'true',
    fail: 1, pass: 4, total: 5,
    failedTests: ['skill-z-test'],
  });
  const diff = diffStates(prior, cur);
  assert.equal(diff.authChanged, true);
  assert.deepEqual(diff.newlyFailing, [], 'auth-skip side must not populate newlyFailing');
  const body = buildTransitionBody({
    diff, current: cur, runUrl: cur.runUrl, shortSha: 'auth2',
  });
  assert.ok(body.includes('auth gate cleared'), 'verb must be auth gate cleared');
  assert.ok(!body.includes('went red'), 'must not say went red on first observation');
});

test('buildStickyBody shows selectionReason composite when touchedSkills is empty', () => {
  // tests.json-only PR: detect step emits clean touched-skill-names as empty
  // and TOUCHED_SKILLS as "(tests.json: t1,t2)". Display falls back to the
  // composite so reviewers see WHY tests were selected.
  const state = baseState({
    touchedSkills: [],
    selectionReason: '(tests.json: sqldw-consumption-list,sqldw-authoring-create)',
  });
  const body = buildStickyBody(state);
  assert.ok(
    body.includes('`(tests.json: sqldw-consumption-list,sqldw-authoring-create)`'),
    'sticky body must display the composite selection reason verbatim when no clean folders'
  );
  assert.ok(!body.includes('`(none)`'), 'must not fall through to (none) when reason present');
});

test('buildStickyBody shows clean folder list (not selectionReason) when both present', () => {
  // Skill + tests.json combo: clean list is non-empty, composite also present.
  // Display priority is clean list; composite is suppressed to keep sticky
  // focused on actual code paths exercised.
  const state = baseState({
    touchedSkills: ['sqldw-consumption-cli'],
    selectionReason: 'sqldw-consumption-cli + (tests.json: t1,t2)',
  });
  const body = buildStickyBody(state);
  assert.ok(body.includes('`sqldw-consumption-cli`'), 'must show clean folder list');
  assert.ok(
    !body.includes('+ (tests.json: t1,t2)'),
    'must NOT display composite when clean list is non-empty (clean is the source of truth)'
  );
});

test('selectionReason never leaks into encoded state.touchedSkills', () => {
  // Regression test for the post-comment script bug where the composite
  // "(tests.json: a,b)" was naively split on commas and inserted into
  // state.touchedSkills. The new contract: clean kebab-case folder list is
  // the only thing persisted; selectionReason is purely a display string.
  const state = baseState({
    touchedSkills: ['sqldw-consumption-cli'],
    selectionReason: 'sqldw-consumption-cli + (tests.json: t1,t2)',
  });
  const body = buildStickyBody(state);
  const parsed = parseStickyState(body);
  assert.ok(parsed, 'parser returns non-null');
  assert.deepEqual(
    parsed.touchedSkills,
    ['sqldw-consumption-cli'],
    'encoded state must contain ONLY the clean folder list, never the composite'
  );
});

test('selectionReason-only state (tests.json-only PR) encodes empty touchedSkills', () => {
  // tests.json-only PR: nothing under skills/ touched, so state.touchedSkills
  // is []. The composite display is the only signal of WHY tests ran. The
  // encoded state must reflect the empty array so a follow-up push that
  // touches a skill folder produces a real touched-set diff (not spurious).
  const state = baseState({
    touchedSkills: [],
    selectionReason: '(tests.json: sqldw-consumption-list)',
  });
  const body = buildStickyBody(state);
  const parsed = parseStickyState(body);
  assert.ok(parsed, 'parser returns non-null');
  assert.deepEqual(parsed.touchedSkills, [], 'encoded touchedSkills stays empty');
});

test('matchedCount=all renders "Matched tests (all): entire catalog" (no misleading (1) count)', () => {
  // Regression for the post-comment bug where the detect job's 'all'
  // sentinel for full-catalog runs (infra touch, tests.json parse
  // failure) was naively split into ['all'] and rendered as
  // "Matched tests (1): `all`" -- misleading reviewers about catalog
  // breadth. The workflow now strips the sentinel from matchedTests and
  // passes matchedCount='all' so buildStickyBody renders the explicit
  // "entire catalog" label.
  const state = baseState({
    touchedSkills: [],
    selectionReason: '(infrastructure: common/lakehouse.md)',
    matchedTests: [],
    matchedCount: 'all',
  });
  const body = buildStickyBody(state);
  assert.ok(
    body.includes('**Matched tests (all):** _entire catalog_'),
    `expected "(all): _entire catalog_" line, got: ${body}`
  );
  assert.ok(
    !body.includes('Matched tests (1)') && !body.includes('Matched tests (0)'),
    'must not show a numeric count when full-catalog mode'
  );
  assert.ok(!body.includes('`all`'), 'must not render the literal "all" sentinel as a test name');
});

test('matchedCount as numeric string overrides matchedTests.length for the display count', () => {
  // Defensive: when detect emits a numeric matched-test-count (e.g. "3"),
  // the sticky should trust the upstream count rather than re-deriving
  // from array length. This catches any future divergence (e.g. if a
  // test name is filtered post-detect).
  const state = baseState({
    touchedSkills: ['skill-a'],
    matchedTests: ['skill-a-t1', 'skill-a-t2', 'skill-a-t3'],
    matchedCount: '3',
  });
  const body = buildStickyBody(state);
  assert.ok(body.includes('**Matched tests (3):**'), `expected (3) prefix, got: ${body}`);
  assert.ok(body.includes('`skill-a-t1, skill-a-t2, skill-a-t3`'));
});

test('matchedCount undefined preserves legacy length-based count (back-compat)', () => {
  // Existing callers / tests that build state without matchedCount must
  // keep getting the old behavior so we don't have to rewrite the
  // baseline test surface.
  const state = baseState({
    touchedSkills: ['skill-a'],
    matchedTests: ['skill-a-t1', 'skill-a-t2'],
  });
  const body = buildStickyBody(state);
  assert.ok(body.includes('**Matched tests (2):**'), `expected length-derived (2), got: ${body}`);
  assert.ok(body.includes('`skill-a-t1, skill-a-t2`'));
});

test('matchedCount=all with non-empty matchedTests still renders entire-catalog (defensive)', () => {
  // The workflow normally clears matchedTests when matchedCount='all'.
  // If a future caller forgets that step, the script should still
  // produce the right header (not "Matched tests (all): `t1, t2`"
  // which would mix sentinel semantics with a real test list).
  const state = baseState({
    matchedTests: ['t1', 't2'],
    matchedCount: 'all',
  });
  const body = buildStickyBody(state);
  assert.ok(body.includes('**Matched tests (all):** _entire catalog_'));
  assert.ok(!body.includes('`t1, t2`'), 'must suppress test list under all-sentinel');
});

// --- Regression: legacy body counts parse all 3 shapes ----------------------
// The collapsed `(?:passed:|FAILED:)? ?(\d+)\/(\d+)(?: passed)? \(flaky: ..., fail: ...\)`
// alternation MUST keep accepting every shape the helper has ever emitted, or
// PRs upgraded mid-flight will lose their counts and look like a regression.
test('parseLegacyStickyBody: success-no-failure body counts', () => {
  const body = [
    STICKY_MARKER,
    '### ✅ PR-touched smoke passed: 5/5 (flaky: 0, fail: 0)',
    '',
    '**Touched skills (1):** `a`',
  ].join('\n');
  const state = mod.parseLegacyStickyBody(body);
  assert.equal(state.pass, 5);
  assert.equal(state.total, 5);
  assert.equal(state.flaky, 0);
  assert.equal(state.fail, 0);
});

test('parseLegacyStickyBody: success-with-failures body counts', () => {
  const body = [
    STICKY_MARKER,
    '### ⚠️ PR-touched smoke: 4/5 passed (flaky: 0, fail: 1) -- 1 non-flaky failure.',
    '',
    '**Touched skills (1):** `a`',
  ].join('\n');
  const state = mod.parseLegacyStickyBody(body);
  assert.equal(state.pass, 4);
  assert.equal(state.total, 5);
  assert.equal(state.flaky, 0);
  assert.equal(state.fail, 1);
});

test('parseLegacyStickyBody: failure body counts', () => {
  const body = [
    STICKY_MARKER,
    '### ❌ PR-touched smoke FAILED: 3/5 (flaky: 1, fail: 1)',
    '',
    '**Touched skills (1):** `a`',
  ].join('\n');
  const state = mod.parseLegacyStickyBody(body);
  assert.equal(state.pass, 3);
  assert.equal(state.total, 5);
  assert.equal(state.flaky, 1);
  assert.equal(state.fail, 1);
});

// --- resolveHeadline classification (extracted helper) ----------------------
test('resolveHeadline: auth not ready (string false)', () => {
  const { icon, headline } = mod.resolveHeadline({ authReady: 'false', authMode: 'skip' });
  assert.equal(icon, '\u23ed\ufe0f');
  assert.match(headline, /auth gate not configured/);
});

test('resolveHeadline: auth not ready (boolean false)', () => {
  const { icon, headline } = mod.resolveHeadline({ authReady: false, authMode: 'skip' });
  assert.equal(icon, '\u23ed\ufe0f');
  assert.match(headline, /auth gate not configured/);
});

test('resolveHeadline: success, zero failures', () => {
  const { icon, headline } = mod.resolveHeadline({
    authReady: true, smokeResult: 'success', pass: 5, total: 5, flaky: 0, fail: 0,
  });
  assert.equal(icon, '\u2705');
  assert.match(headline, /smoke passed: 5\/5/);
});

test('resolveHeadline: success with non-flaky failures (warning)', () => {
  const { icon, headline } = mod.resolveHeadline({
    authReady: true, smokeResult: 'success', pass: 4, total: 5, flaky: 0, fail: 1,
  });
  assert.equal(icon, '\u26a0\ufe0f');
  assert.match(headline, /non-flaky failure/);
});

test('resolveHeadline: failure', () => {
  const { icon, headline } = mod.resolveHeadline({
    authReady: true, smokeResult: 'failure', pass: 3, total: 5, flaky: 0, fail: 2,
  });
  assert.equal(icon, '\u274c');
  assert.match(headline, /smoke FAILED/);
});

test('resolveHeadline: orchestrator-level skip', () => {
  const { icon, headline } = mod.resolveHeadline({ authReady: true, smokeResult: 'skipped' });
  assert.equal(icon, '\u23ed\ufe0f');
  assert.match(headline, /skipped at orchestrator level/);
});

test('resolveHeadline: unknown result falls through', () => {
  const { icon, headline } = mod.resolveHeadline({ authReady: true, smokeResult: 'cancelled' });
  assert.equal(icon, '\u26a0\ufe0f');
  assert.match(headline, /smoke result: cancelled/);
});

// --- resolveVerb classification (extracted helper) --------------------------
test('resolveVerb: first run, auth not ready -> skipped', () => {
  const { icon, verb } = mod.resolveVerb({ isFirstRun: true }, { authReady: false, fail: 0 });
  assert.equal(icon, '\u23ed\ufe0f');
  assert.equal(verb, 'skipped (auth gate)');
});

test('resolveVerb: first run, single failure (singular)', () => {
  const { icon, verb } = mod.resolveVerb(
    { isFirstRun: true },
    { authReady: true, fail: 1, smokeResult: 'success' },
  );
  assert.equal(icon, '\u274c');
  assert.equal(verb, 'started red (1 failure)');
});

test('resolveVerb: first run, multiple failures (plural)', () => {
  const { icon, verb } = mod.resolveVerb(
    { isFirstRun: true },
    { authReady: true, fail: 3, smokeResult: 'success' },
  );
  assert.equal(verb, 'started red (3 failures)');
});

test('resolveVerb: first run, smoke failure with zero fail (engine error)', () => {
  const { icon, verb } = mod.resolveVerb(
    { isFirstRun: true },
    { authReady: true, fail: 0, smokeResult: 'failure' },
  );
  assert.equal(icon, '\u274c');
  assert.equal(verb, 'started red');
});

test('resolveVerb: first run, success', () => {
  const { icon, verb } = mod.resolveVerb(
    { isFirstRun: true },
    { authReady: true, fail: 0, smokeResult: 'success' },
  );
  assert.equal(icon, '\u2705');
  assert.equal(verb, 'started green');
});

test('resolveVerb: auth flipped to ready', () => {
  const { icon, verb } = mod.resolveVerb(
    { isFirstRun: false, authChanged: true, newlyFailing: [], recovered: [], stillFailing: [] },
    { authReady: true, fail: 0 },
  );
  assert.equal(icon, '\u23ed\ufe0f');
  assert.equal(verb, 'auth gate cleared');
});

test('resolveVerb: auth flipped to engaged', () => {
  const { icon, verb } = mod.resolveVerb(
    { isFirstRun: false, authChanged: true, newlyFailing: [], recovered: [], stillFailing: [] },
    { authReady: false, fail: 0 },
  );
  assert.equal(icon, '\u23ed\ufe0f');
  assert.equal(verb, 'auth gate engaged');
});

test('resolveVerb: pure new failures (no recovered, no still-failing) -> went red', () => {
  const { icon, verb } = mod.resolveVerb(
    { isFirstRun: false, authChanged: false, newlyFailing: ['a'], recovered: [], stillFailing: [] },
    { authReady: true, fail: 1 },
  );
  assert.equal(icon, '\u274c');
  assert.equal(verb, 'went red');
});

test('resolveVerb: clean recovery -> recovered', () => {
  const { icon, verb } = mod.resolveVerb(
    { isFirstRun: false, authChanged: false, newlyFailing: [], recovered: ['a'], stillFailing: [] },
    { authReady: true, fail: 0 },
  );
  assert.equal(icon, '\u2705');
  assert.equal(verb, 'recovered');
});

test('resolveVerb: mixed change -> failure set updated (yellow)', () => {
  const { icon, verb } = mod.resolveVerb(
    { isFirstRun: false, authChanged: false, newlyFailing: ['a'], recovered: ['b'], stillFailing: [] },
    { authReady: true, fail: 1 },
  );
  assert.equal(icon, '\ud83d\udfe1');
  assert.equal(verb, 'changed (failure set updated)');
});

test('resolveVerb: no failure-set change -> updated (informational)', () => {
  const { icon, verb } = mod.resolveVerb(
    { isFirstRun: false, authChanged: false, newlyFailing: [], recovered: [], stillFailing: [] },
    { authReady: true, fail: 0 },
  );
  assert.equal(icon, '\u2139\ufe0f');
  assert.equal(verb, 'updated');
});
