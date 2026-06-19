# Skill test result schema

> **Status**: ACCEPTED. The schema is the **contract** between producers of
> skill-test results (Vally evals today; legacy manual-only smoke and future MSBench
> benchmarks) and consumers that aggregate or display them (lightweight
> static HTML dashboard today; potentially other consumers later). The
> schema is intentionally decoupled from any specific dashboard
> implementation.

## Why this exists

We run multiple test pipelines:

- **Vally evals** (today) -- primary PR and nightly harness from `tests/evals/<skill>/eval.yaml`, with Vally graders and per-suite filtering.
- **Full-eval** (today) -- runs on every PR that touches a skill with an eval plan (auto-narrowed to matching plans) plus nightly cron (all plans), with per-test PASS/FAIL grading (`tests/full-eval-tests/`).
- **Legacy manual-only smoke** -- frozen break-glass path with Y/N per test (`tests/run-smoke-tests.ps1`, `tests/testFabricSkills.ps1`).
- **MSBench benchmarks** (future) — cross-model nightly runs in Harbor
  format.

Each pipeline produces its own raw output. A consistent **on-disk shape**
makes it possible to:

1. Build a single team-internal dashboard that aggregates across pipelines.
2. Add new pipelines (or replace existing ones) without rewriting the
   dashboard.
3. Adopt third-party consumers (Power BI, Grafana, etc.) by pointing them
   at the same files.

This schema is the on-disk shape.

## Where this schema came from

The schema is adapted from the data layout used by the Azure Skills team in
[`microsoft/GitHub-Copilot-for-Azure`](https://github.com/microsoft/GitHub-Copilot-for-Azure)
(specifically their `dashboard/api/src/functions/getData.ts` and
`getTestResults.ts`). Their dashboard is a fork-able Static Web App we
briefly copied as foundation work; we adopted the **schema only**, not the
dashboard itself.

Reasoning:

- The schema is the genuinely valuable, portable artifact.
- Their dashboard is ~15k LoC of inherited code we don't need at our scale
  (1 FTE + 30 skills + `workflow_dispatch` cadence).
- The Azure Skills team's lead confirmed "use your own dashboard" — no
  alignment value in adopting their UI stack.

Both repositories are Microsoft-owned, so the schema is reused as internal
IP; no third-party OSS license is implied.

## Storage shape

Results are organized as a directory tree (or equivalently, a blob-storage
hierarchy when published to Azure Blob Storage in a future Power BI Phase
2):

```
${DATE-yyyy-mm-dd}/                                 # one entry per calendar day (UTC)
└── ${RUN_ID}/                                      # one entry per pipeline run
    └── ${SKILL_NAME}/                              # one entry per skill grouping
        ├── test-run-{datetime}-{skill}-SKILL-REPORT.md   # per-skill summary
        ├── testResults.json                              # per-test results
        ├── token-summary.jsonl                           # per-test token usage (optional)
        └── ${TEST_CASE}/                                 # one entry per test
            ├── test-consolidated-report.md               # per-test summary
            ├── agent-metadata-{datetime}.md              # agent trajectory (markdown)
            ├── agent-metadata.json                       # agent trajectory (machine-readable, hidden by default)
            └── token-usage.json                          # per-test token data (machine-readable, hidden by default)
```

Notes:

- `${DATE-yyyy-mm-dd}` is the UTC calendar date of the run.
- `${RUN_ID}` is opaque — pick anything that uniquely identifies a single
  pipeline invocation. The legacy manual-only smoke pipeline uses
  `${github.run_id}-${github.run_attempt}` from the GitHub Actions context.
- `${SKILL_NAME}` is a producer-chosen grouping key. Legacy manual-only smoke uses the `area`
  field from legacy `tests/tests.json` (e.g., `sqldw`, `eventhouse`, `powerbi`).
  Other producers (Vally) may use finer-grained skill names
  (e.g., `eventhouse-consumption-cli`); the schema is naming-agnostic and
  treats this string as an opaque key.
- `${TEST_CASE}` is the test-case directory name; the legacy manual-only smoke pipeline uses
  a sanitised version of the test name from legacy `tests/tests.json`.

## File-by-file shape

### `testResults.json`

Per-skill summary of all test cases. Each `testResults.json` lives at the
**single skill area level** (`${SKILL_NAME}/testResults.json`) and contains
only test cases that share that skill grouping. Example (here all keys are
in the `sqldw` skill area):

```json
{
    "sqldw-consumption-basic-query": {
        "isPass": true,
        "message": "Smoke status: Y",
        "rawStatus": "Y",
        "durationSeconds": 102.6,
        "foundSkills": ["sqldw-consumption-cli"],
        "foundResults": ["10,000"]
    },
    "sqldw-consumption-advanced-query": {
        "isPass": false,
        "message": "Smoke status: N",
        "rawStatus": "N",
        "durationSeconds": 300.1,
        "missingResults": ["2.86"]
    },
    "sqldw-consumption-list-and-inspect": {
        "isPass": true,
        "message": "Smoke status: F (flaky issue: https://github.com/gim-home/skills-for-fabric/issues/131)",
        "rawStatus": "F",
        "flakyIssue": "https://github.com/gim-home/skills-for-fabric/issues/131",
        "durationSeconds": 88.4,
        "missingSkills": ["sqldw-authoring-cli"]
    }
}
```

A sibling `${SKILL_NAME}/testResults.json` exists per skill area (`sqldw`,
`spark`, `powerbi`, `eventhouse`, ...); consumers walk the schema tree and
aggregate across them.

Fields:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `isPass` | `boolean` | yes | `true` if the test passed grading (including flaky-passes for the smoke producer), `false` otherwise. |
| `message` | `string` | no | Human-readable detail (failure reason, useful context, raw smoke status, etc.). Free-form. |
| `rawStatus` | `string` (`"Y"`, `"F"`, `"N"`) | no | The raw smoke runner status (Y = pass, F = flaky-pass, N = fail/timeout). When the producer is the smoke pipeline, this is always present. |
| `durationSeconds` | `number` | no | Wall-clock seconds the test took. Populated by the smoke translator from `smoke-run.log`. |
| `foundSkills` | `array<string>` | no | Skills detected in the agent's output (matched against `expectedSkills` in legacy `tests/tests.json`). |
| `foundResults` | `array<string>` | no | Expected result substrings detected in the agent's output. |
| `missingSkills` | `array<string>` | no | Expected skills NOT detected. Non-empty implies a routing miss. |
| `missingResults` | `array<string>` | no | Expected results NOT detected. Non-empty implies the agent ran the right skill but produced the wrong content. |
| `warnings` | `array<string>` | no | Free-text warnings emitted by the runner (e.g., timeouts, Copilot CLI errors). |
| `flakyIssue` | `string` (URL) | no | GitHub issue URL for tests known to be flaky. Producers set this when downgrading a fail to `F`. |
| `skillInvocationRate` | `number` (0-1) | no | Fraction of agent runs (when `runs > 1`) that invoked the expected skill. `1.0` if all runs invoked it. Only meaningful for producers that run each test multiple times (smoke runs once today). |
| `expectsScreenshot` | `boolean` | no | Internal flag for tests that capture a screenshot (UI tests). Defaults to `false`. |

Multiple test cases per skill share the same `testResults.json`; the
test-case name (used as a directory below) is the object key.

#### Top-level field: `schemaVersion`

Each `testResults.json` object carries a reserved top-level `schemaVersion`
integer (currently `1`) alongside the per-test-case entries:

```json
{
    "schemaVersion": 1,
    "sqldw-consumption-basic-query": { "isPass": true, "message": "..." }
}
```

`schemaVersion` is the **on-disk contract version** -- the agreed shape of
this file (and its sibling artifacts). It is bumped only on a **breaking
shape change** (for example, renaming a required field or restructuring the
per-test entries) so a consumer can detect and reject an incompatible
producer instead of silently mis-parsing it. Additive, backward-compatible
changes (new OPTIONAL fields such as `rootCause`) do **not** bump it.

Because the field sits at the same level as the test-case keys, consumers
that iterate test cases MUST skip reserved non-object top-level values
(`schemaVersion` is an integer, not a test-case object). The static
dashboard (`.github/scripts/build-dashboard.py`) does this by dropping any
top-level value that is not a JSON object before counting pass/fail.

The vally producer (`tests/vally-ci/Export-VallySchemaArtifact.ps1`) emits
`schemaVersion: 1`. Producers that predate the field (e.g. the legacy smoke
translator) may omit it; consumers MUST treat its absence as `1` for
backward compatibility.

#### Optional field: `rootCause`

When the producer can attribute a failure to a stable cause class, it
MAY add a `rootCause` field at the per-test entry level (or on each
per-grader sub-entry in a richer producer-specific shape). Consumers
MUST treat this string as opaque -- the canonical taxonomy lives in
the producer (today: `tests/vally-ci/Classify-VallyFailure.ps1`,
eleven-class taxonomy `Routing` / `WallTimeBudget` / `TokenBudget` /
`TurnBudget` / `SessionIdle` / `AuthOrSetup` / `ToolError` /
`ContentMismatch` / `HarnessCrash` / `EvalThreshold` / `Other`). The
field is OPTIONAL so consumers MUST tolerate its absence (legacy
in-window artifacts have no `rootCause` and continue to render).

### `deepLinks.json` (optional, sibling)

Per-skill sibling file `${date}/${run_id}/${skill}/deepLinks.json`
emitted by producers that want to surface per-failure deep links on
the consumer side (today: the vally producer via
`tests/vally-ci/Export-VallySchemaArtifact.ps1`; tomorrow potentially
the smoke producer if useful). Shape:

```json
{
  "runId": "12345678-1",
  "workflowRunId": 12345678,
  "jobs": {"shard0": 999111, "shard1": 999112, "summarise": 999200},
  "artifacts": {"smoke-results-schema-vally-12345678-1": 555},
  "stimGraders": [
    {"stim": "Ingest 100MB", "shard": "shard0", "grader": "wall-time-budget",
     "passed": false, "rootCause": "WallTimeBudget",
     "evidence": "Exceeded wall-time budget: 612s (limit 300s). Workspace [REDACTED] was responsive."},
    {"stim": "Ingest 100MB", "shard": "shard0", "grader": "tool-routing",
     "passed": true},
    {"stim": "Ingest 100MB", "shard": "shard0", "grader": "expected-output",
     "passed": true}
  ]
}
```

Fields:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `runId` | `string` | yes | The producer's run identifier (matches the on-disk `${date}/${run_id}/${skill}/` directory name). For the vally producer this is the attempt-suffixed form `<github.run_id>-<github.run_attempt>` (e.g. `12345678-1`) so re-runs land in distinct subtrees. NOT for URL composition -- use `workflowRunId` instead. |
| `workflowRunId` | `int` | yes | The bare GitHub Actions workflow run id (no attempt suffix). Consumers compose `/actions/runs/{workflowRunId}/job/{job_id}` and `/actions/runs/{workflowRunId}/artifacts/{artifact_id}` URLs from this. Distinct from `runId` because the attempt-suffixed form 404s on GitHub Actions URLs. |
| `jobs` | `object` | yes | Map of shard label (or job name) -> GitHub Actions `job_id` (int). Compose URLs with `workflowRunId`, not `runId`. |
| `artifacts` | `object` | yes | Map of artifact name -> `artifact_id` (int). Compose URLs with `workflowRunId`, not `runId`. |
| `stimGraders` | `array<object>` | yes | One entry per (stim, shard, grader) for stims that had at least one grader failure. Carries `stim`, `shard`, `grader`, `passed` (bool). Failing entries also carry `rootCause` and redacted `evidence`; passing entries omit those fields. Consumers use this to render the full triage context ("X of Y graders failed" rather than just "X failed"). |
| `stimFailures` | `array<object>` | no (legacy) | The pre-`stimGraders` shape carrying failing-only entries. Renderers still accept it as a fallback; new producers SHOULD emit `stimGraders` instead. |

The `logLineOffset` field on stim entries is **(future, not currently emitted)** by the vally producer -- per-stim line offsets are deferred to a follow-up when the log parser tracks stim context.

`deepLinks.json` is producer-and-consumer-agnostic on purpose: the
field names are stable so a future Power BI ingester can read it
identically to the static-dashboard renderer that exists today, with
no producer-side changes required. The field is OPTIONAL -- when
absent the consumer falls back to a top-level run-page link only.

### `token-summary.jsonl`

Per-skill JSONL (one JSON object per line). One record per **agent run** (so
multiple records per test when `runs > 1`):

```json
{"testName":"sqldw-consumption-basic-query","inputTokens":4210,"outputTokens":612,"cacheReadTokens":0,"cacheWriteTokens":0}
```

Fields: `testName` (matches the key in `testResults.json`), `inputTokens`,
`outputTokens`, `cacheReadTokens`, `cacheWriteTokens` (all `number`).

A consumer aggregates these per test by summing across lines with the same
`testName`.

For the smoke pipeline, the producer captures these from Copilot CLI's per-test
session telemetry (`~/.copilot/session-state/<session-id>/events.jsonl`, read via
`tests/copilot-session-telemetry.ps1::Get-CopilotSessionTelemetry`). The values
map as follows:

| Schema field      | Source                                                                                                     |
|-------------------|------------------------------------------------------------------------------------------------------------|
| `inputTokens`     | sum of `systemTokens` + `conversationTokens` + `toolDefinitionsTokens` from the Copilot session-shutdown event |
| `outputTokens`    | `currentTokens` minus the input-token sum above (Copilot CLI does not report completion tokens separately) |
| `cacheReadTokens` | `0` today (Copilot CLI does not currently surface prompt-cache counters at session shutdown)               |
| `cacheWriteTokens`| `0` today (same)                                                                                           |

The `cacheRead`/`cacheWrite` counters are reserved in the schema for when
Copilot CLI starts emitting them; consumers should not assume they're populated.

### `test-run-{datetime}-{skill}-SKILL-REPORT.md`

Per-skill markdown summary. Free-form, except that **an optional
`Confidence: N` line is parsed** by future consumers (where `N` is an
integer 0-100). Otherwise rendered as-is.

The `{datetime}` portion is the run start time in `yyyy-MM-ddTHHmmssZ`
form; multiple SKILL-REPORTs may coexist for a single date when multiple
runs share a day (rare).

### `test-consolidated-report.md` (per test case)

Per-test markdown summary. Free-form; rendered as-is by any consumer that
supports markdown. Typical content: outcome, brief trajectory, follow-ups.

### `agent-metadata-{datetime}.md` (per test case)

Per-test agent trajectory in markdown. One file per agent run when
`runs > 1`. Free-form; intended for human reading.

### `agent-metadata.json` (per test case, hidden by default)

Machine-readable agent trajectory. Same content as the `.md` companion but
structured. By convention this file is **not enumerated** by consumers (so
it doesn't appear in tab listings); it remains downloadable on demand.
Producers should not put secrets in it.

### `token-usage.json` (per test case, hidden by default)

Machine-readable per-test token data. Same hidden-by-default convention as
`agent-metadata.json`.

## Producer: legacy manual-only smoke pipeline

Legacy manual-only `tests/testFabricSkills.ps1` emits a flat `testsResults.json` (array of
`{name, passed}` records, where `passed` is `'Y'`, `'F'`, or `'N'`). The
GitHub Actions workflow `fabric-smoke-ephemeral.yml` then runs
`.github/scripts/smoke-results-to-schema.ps1` to translate that into this
schema, grouping tests by `area` from legacy `tests/tests.json`. The translator
emits the tree under `${runner.temp}/smoke-results-schema/` and uploads it
as the `smoke-results-schema-{run_id}-{run_attempt}` artifact (90-day
retention).

The translator also writes a per-skill rollup markdown table that the
workflow appends to `$GITHUB_STEP_SUMMARY` so a leadership-readable status
shows at the top of every legacy smoke run page.

## Consumer: lightweight static dashboard

`.github/workflows/dashboard-build.yml` runs on legacy manual-only smoke completion +
daily + manual dispatch. It uses the GitHub CLI to download recent
`smoke-results-schema-*` artifacts, then invokes
`.github/scripts/build-dashboard.py` to aggregate per-skill pass/fail across
a configurable window (default 30 days). The aggregator emits one
self-contained `index.html` with per-skill rows, inline-SVG sparklines, and
light/dark mode via `prefers-color-scheme`. The workflow uploads the HTML
as the `smoke-dashboard-html` artifact.

The dashboard is delivered as a **workflow artifact**, not a stable
public URL. `gim-home/skills-for-fabric` is internal; GitHub Pages on
internal repos publishes content at a publicly-discoverable URL, and the
rendered HTML includes test names and agent error messages that may leak
workspace IDs or internal-tenant details. The audience-vs-surface decision
is deferred to a follow-up PR (alternatives include GitHub Pages with
explicit access controls, an internal Static Web App, or a Power BI report
on top of the same schema).

## Future consumers

| Consumer | Status | Reads |
|---|---|---|
| GitHub Actions Job Summary (built into smoke + vally workflows) | Shipping | Per-skill rollup table at the top of every smoke-run / vally-run page; vally additionally renders a Root-cause breakdown mini-table. |
| Lightweight static dashboard (workflow + artifact) | Shipping | All `testResults.json` from the last N days (from BOTH `smoke-results-schema-*` and `smoke-results-schema-vally-*` artifacts -- the consumer matches both via `startswith("smoke-results-schema-")`); per-skill pass/fail trends; per-failure `details` disclosure with RootCause chip and deep links when the sibling `deepLinks.json` is present. |
| Power BI report | Future, conditional | Same files, via Azure Blob / Lakehouse / SharePoint connector. Prerequisites: workspace ownership, storage layer decision, cross-tenant identity. The `deepLinks.json` field names are stable so a PBI ingester can consume them identically to the static dashboard. |
| Future: Vally outer-loop report integration | n/a -- vally is now a first-class producer | The vally workflow emits this schema directly via `tests/vally-ci/Export-VallySchemaArtifact.ps1`; no translator from `eval-results.md` / `results.jsonl` is needed. |

## Naming caveat

This fixture uses Fabric skill names (`eventhouse-consumption-cli`) and Fabric
test cases (`list-databases`, `query-weather`). When extracted from the
upstream sister-team dashboard, the upstream sample data referred to Azure
skills (`azure-deploy`, `azure-prepare`, etc.). The schema itself is
naming-agnostic — `${SKILL_NAME}` is just a string the consumer treats as a
key. Translation from a smoke runner's output to this on-disk shape lives in
the producer (`fabric-smoke-ephemeral.yml` + a small translator script).
