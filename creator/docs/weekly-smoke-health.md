# Weekly Legacy Smoke Health Review

> **Purpose:** sustainable cadence for triaging flaky/failing legacy manual-only smoke tests by routing each finding to the right team owner, with paper-trail evidence and a clear pushback channel.

## Quick reference

| Field | Value |
|---|---|
| **Cadence** | Weekly (Monday morning) |
| **Window** | Last 5 completed legacy manual-only smoke runs on `main` |
| **Source data** | `smoke-results-schema-*` artifacts from manual-only `fabric-smoke-ephemeral.yml` break-glass runs |
| **Owner map** | `.github/skill-ownership.yml` (single source of truth; CI-enforced) |
| **Script** | `.github/scripts/weekly-flake-report.py` |
| **Report** | `reports/weekly-YYYY-MM-DD.md` (location + commit decision TBD after 2-3 manual cycles; for now the report is written wherever `--output` points and review is desk-side) |

## How it works

1. **Aggregate** the last 5 legacy manual-only smoke runs on `main` (using `smoke-results-schema-*` artifacts).
2. **Compute** a per-test "outcomes string" like `YFYYN` (oldest -> newest, one character per run).
3. **Resolve** each test's owning team via legacy `tests/tests.json::expectedSkills[i]` -> `skill-ownership.yml::skills[<skill>].owningTeam` -> `teams[<team>].contact`.
4. **Classify** each test with a coarse "likely cause" hint (stable / flake / known-issue / consistently-broken).

### Outcome character legend

The per-test outcome string (e.g. `YFYYN`, oldest -> newest) uses the same `rawStatus` characters as the legacy smoke schema (see [docs/skill-test-result-schema.md](skill-test-result-schema.md#testresults-array)):

| Char | Meaning | Notes |
|---|---|---|
| `Y` | Pass | test ran and met expectedSkills + expectedResults |
| `F` | Flaky-pass (downgraded fail) | test failed but is carrying a `flaky.githubIssue` flag; legacy smoke harness downgrades to F + sets `isPass=true` so dashboards stay green |
| `N` | Unexpected fail / timeout | test failed and has NO `flaky.githubIssue` flag -- a real regression |
| `-` | Absent from that run | run produced no schema artifact for this test (cancelled, startup-failed, or the test was added after the run) |
5. **Draft** for each team:
    - a GitHub issue comment body (intended for the team's central tracker issue)
    - an email body to the team owner contact
6. **Emit** a single markdown report.

**The script does NOT post comments, open issues, or send email.** The eval team owner reviews the report and decides which actions to take, **one at a time**.

## Run the script

```bash
python .github/scripts/weekly-flake-report.py --runs 5 --output reports/weekly-2026-05-20.md
```

Requirements: `gh` CLI authenticated with read access to the repo, Python 3.10+, PyYAML, run from repo root.

## Per-item permission flow (no batch approvals)

Per the eval-team protocol:

| Phase | Who | Permission needed |
|---|---|---|
| Generate weekly report markdown | Eval team owner (manual run) | None -- just produces a file |
| Review the report + each drafted action | Eval team owner | None -- desk review |
| Per item: "Should we open issue / update comment / tag X?" | Eval team owner decides | Explicit per-item approval -- **never batch** |
| Execute approved action | Eval team owner (via `gh` CLI) | Acts on the one approved item |
| Send email to team owner | Eval team owner (NOT automation) | Owner sends from their own inbox |

Why this discipline:

- Issue comments are public, auditable, easy to retract -- automation OK with per-item approval.
- Emails are private, less retractable, and the team owner's relationship matters more than automation efficiency. Sent by humans, not scripts.

## Central-issue-per-team pattern

We use **one open issue per team** as the conversation thread (e.g., `[smoke-health] dataflows`). Each weekly comment refreshes the F/N table on that issue. Why this shape:

- Stable conversation thread per team (instead of N short-lived issues per test)
- Team owners see the full state of their area in one place
- "Likely cause" column invites pushback -- if the finding sits in our infra (test prompt, fixture, harness), the team can push back and we'll fix it in the infra rather than nag them

Cross-cutting issues (e.g., `expectedSkills` check semantics affecting multiple teams) stay as their own meta-issues and are **linked** from per-team issues rather than restated.

## Flag-removal candidates

A test carrying a `flaky.githubIssue` reference that has passed 3+ consecutive runs in the window is flagged as a removal candidate. These are NOT automatically de-flagged; a separate small PR removes the flag once the underlying issue is verified closed.

## Routing data (where it comes from)

| Question | Answered by |
|---|---|
| Which team owns this skill? | `skill-ownership.yml::skills[<skill>].owningTeam` |
| Who do I contact for this team? | `skill-ownership.yml::teams[<team>].contact` (name + email + github) |
| Which test exercises which skill? | legacy `tests/tests.json::expectedSkills[]` |
| Which tests are known-flaky? | legacy `tests/tests.json::<test>.flaky.githubIssue` |

When a new skill is added, the existing CI gate (`tests/coverage_enforcement.py`) requires it to be registered in `skill-ownership.yml` -- which means the weekly report automatically picks up the right owner. No second tracker to maintain.

## Limitations + future improvements

- **No central-issue automation yet.** Comments are drafted, not posted. Once we've used this for 2-3 weeks and trust the drafts, we can add a `--apply` mode that posts comments after explicit per-item approval.
- **Unmapped tests** (today: `document-workspace-agent` with empty `expectedSkills`) render in a dedicated section with TBD owner. Either add `expectedSkills` to the test entry or route to the `platform` team to clear this bucket.
- **`flaky.githubIssue`** is currently the only source of "is this test known-flaky". A future improvement would compute it from the dashboard pass-rate trend directly (>= 30 days, < 80%), making the field a pointer rather than ground truth.

## Related docs

- `.github/skill-ownership.yml` -- the canonical team + contact source
- `docs/contributor-kit.md` -- how to add a new skill (and register it)
- `.github/workflows/fabric-smoke-ephemeral.yml` -- the legacy manual-only smoke break-glass workflow that produces schema artifacts
- `.github/scripts/build-dashboard.py` -- the dashboard generator (different concern; complementary)
