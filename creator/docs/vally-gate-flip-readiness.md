# Vally gate-flip readiness runbook

This runbook is the pre-flight checklist for turning the Vally merge gate from
comment-only into a hard blocking gate. Run it BEFORE flipping the toggle, not
after, so a known-flaky stim does not red-fail every PR the day enforcement
turns on.

## Why this exists

The Vally merge gate (Gate A in `.github/workflows/fabric-smoke-vally.yml`) is
controlled by `VALLY_GATE_ON_STIM_FAIL`, default `false` (comment-only during
calibration). The per-trial gate (Gate B) is controlled by
`VALLY_FAIL_ON_REGRESSION`, also default `false`. While both are off, a stim
that fails intermittently shows up only as a PR comment and never red-fails a
run, so flakiness stays invisible.

The scoring math makes this sharp. Each eval declares `scoring.threshold`
(default `1.0`) and `runs` (today `5` across every eval). A stim passes only
when its trial-averaged score reaches the threshold, so `threshold: 1.0` with
`runs: 5` means every one of the 5 trials must score perfectly on every grader.
A stim with even a 10% per-trial flake then fails the 5-trial gate roughly
40% of the time. Flip `VALLY_GATE_ON_STIM_FAIL=true` with a dozen such stims and
the first PR after the flip is red through no fault of its author.

This runbook surfaces those stims first.

## Pre-flip checklist

Do not set `VALLY_GATE_ON_STIM_FAIL=true` until every box is checked.

1. **Gather a per-stim pass-rate window.** Collect the last 10+ nightly Vally
   runs on `main`. The per-stim pass/fail history is in the
   `smoke-results-schema-*` artifacts each run uploads; `.github/scripts/weekly-flake-report.py`
   already parses these into per-test outcome strings. Run it (or read its
   output) over the window to get a pass rate per stim.

2. **Build the stabilize list.** Any stim that is not at 100% pass over the
   window goes on the list, tagged with its observed pass rate and the most
   common root-cause class (the `RootCause` column from
   `tests/vally-ci/Classify-VallyFailure.ps1`, already surfaced in the job
   summary and the PR comment). Track the list wherever the team tracks
   release blockers; issue #372 is the starting point.

3. **Resolve each entry one of two ways:**
   - **Fix the flake (preferred).** Most flakes are a too-tight budget
     (`max_turns` / `wall-time` / `max_tokens`), a non-deterministic output
     assertion, or a genuine skill bug. Fix it and confirm the stim is green
     across a fresh window.
   - **Lower that eval's threshold, with justification.** If the flake is
     irreducible (a legitimately probabilistic step), set `scoring.threshold`
     below `1.0` on that eval (Vally reads it per-eval, so this affects every
     stim in the file -- prefer splitting the flaky stim into its own eval if
     the rest should stay strict). Record the value, the reason, and a
     revisit date next to the eval. This is the `threshold` lever Vally already
     exposes; no Vally change is needed.

4. **Confirm the list is empty or fully justified.** Every entry is either
   green across the latest window or carries a documented threshold override.

5. **Flip, watch, and be ready to revert.** Set `VALLY_GATE_ON_STIM_FAIL=true`.
   Watch the first day of PRs. If a stim red-fails that the window said was
   clean, flip back to `false` (it is a single workflow input, not a code
   change) and add the stim to the stabilize list.

## What NOT to do

- Do not flip the gate and triage flakes post-merge. The whole point of this
  runbook is that the flip-day surprise is foreseeable from the window data.
- Do not lower the repo-wide default threshold to mask flakiness. Lower it only
  per-eval, only with a recorded reason and revisit date, so the override is
  visible and temporary rather than a silent permanent relaxation.
- Do not raise `runs` to paper over a flake; more trials make a flaky stim more
  likely to fail the strict gate, not less.

## Related

- `.github/workflows/fabric-smoke-vally.yml` -- `VALLY_GATE_ON_STIM_FAIL`,
  `VALLY_FAIL_ON_REGRESSION` toggles.
- `.github/scripts/weekly-flake-report.py` -- per-stim flake history source.
- `tests/vally-ci/Classify-VallyFailure.ps1` -- root-cause classification.
- `tests/evals/README.md` -- eval authoring, the L1/L2 layers, and the
  grandfather list.
