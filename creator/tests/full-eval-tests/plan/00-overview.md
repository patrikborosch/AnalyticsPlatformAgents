# Master Evaluation Plan

## Objective

Evaluate all skills-for-fabric for correctness, efficiency, and data consistency. Each skill is tested individually, then in combination with other skills to verify end-to-end workflows.

## Skills Under Test

| ID | Skill | Category | R/W | Has Eval Plan |
|----|-------|----------|-----|---------------|
| S2 | `spark-authoring-cli` | Spark Authoring | Write | Yes |
| S3 | `spark-consumption-cli` | Spark Consumption | Read | Yes |
| S4 | `sqldw-authoring-cli` | SQL DW Authoring | Write | Yes |
| S5 | `sqldw-consumption-cli` | SQL DW Consumption | Read | Yes |
| S6 | `e2e-medallion-architecture` | Pipeline | Write+Read | Yes |
| S7 | `eventhouse-authoring-cli` | KQL / Eventhouse Authoring | Write | Yes |
| S8 | `eventhouse-consumption-cli` | KQL / Eventhouse Consumption | Read | Yes |
| S9 | `semantic-model-authoring` | Power BI Semantic Model Authoring | Write | Yes |
| S10 | `semantic-model-consumption` | Power BI Semantic Model Consumption | Read | Yes 
| S11 | `synapse-migration` | Migration Guidance | Description | Yes |
| S12 | `hdinsight-migration` | Migration Guidance | Description | Yes |
| S13 | `databricks-migration` | Migration Guidance | Description | Yes |
| S14 | `eventstream-authoring-cli` | Eventstream / Real-Time Intelligence Authoring | Write | Yes |
| S15 | `eventstream-consumption-cli` | Eventstream / Real-Time Intelligence Consumption | Read | Yes |
| S16 | `activator-authoring-cli` | Activator / Real-Time Intelligence Authoring | Write | Yes |
| S17 | `activator-consumption-cli` | Activator / Real-Time Intelligence Consumption | Read | Yes |
| A1 | `FabricMigrationEngineer` (agent) | Migration Orchestration | Description | No |

## Evaluation Phases

### Phase 0: Workspace Provisioning (Runner-Managed)

The eval runner (`run-full-tests.ps1`) creates a fresh, timestamped workspace before any tests run and passes its name and ID in every prompt.

#### What the runner does (before invoking any eval plan):
1. Logs in via service principal
2. Discovers an active Fabric capacity
3. Creates a workspace named `FullEval-YYYYMMDD-HHmmss` with the capacity assigned
4. Replaces `{{WORKSPACE}}` and `{{WORKSPACE_ID}}` placeholders in all eval plan `.md` files with the actual values
5. Passes the workspace name and ID in every Copilot prompt

#### What the agent must do:
- Use the workspace name and ID provided in the prompt — do NOT ask the user or use a default.
- The workspace is empty and ready to use. No cleanup is needed.
- Store the workspace name as `EVAL_WORKSPACE` and use it for all subsequent eval phases.
- All prompts that reference "my workspace" resolve to `EVAL_WORKSPACE`.

**Phase 0 is run-once per session.** If Phase 0 has already completed (workspace ID resolved), subsequent eval plans in the same session MUST skip Phase 0 and reuse the previously resolved `EVAL_WORKSPACE` and workspace ID.

### Phase 0b: Shared Infrastructure Provisioning (Runner-Managed)

After creating the workspace, the runner provisions shared infrastructure items that are expensive to create (2-5 min each). Individual eval plans reuse this infrastructure but **set up and tear down their own data independently**.

The runner creates the following shared items via Copilot:
1. **Data Warehouse** — `{{WAREHOUSE}}`
2. **Lakehouse** — `{{LAKEHOUSE}}` (with schema support enabled)
3. **Eventhouse** — `{{EVENTHOUSE}}` with KQL Database `{{KQLDB}}`

These items are provisioned once and shared across all plans. Individual plans MUST NOT drop or recreate these items.

### Data Isolation Principle (MANDATORY)

> **Each eval plan is self-contained for data.** No plan may depend on data created by a previous plan.

Rules:
1. **Each plan sets up its own data** in a "Data Setup" step at the beginning (create schemas, tables, insert rows).
2. **Each plan tears down its data** in a "Data Teardown" step at the end (drop tables, schemas, views — NOT the shared infrastructure).
3. **Plans may run in any order** — consumption plans do NOT depend on authoring plans having run first.
4. **Shared infra is read-only** — plans use the pre-provisioned warehouse/lakehouse/eventhouse but never drop them.
5. **Table names should be unique per plan** where possible, or explicitly dropped and recreated at the start.

### Phase 1: Data Preparation
- Use checked-in deterministic datasets from `evalsets/data-generation/`
- Use checked-in golden results from `evalsets/expected-results/`
- Regenerate data only when intentionally refreshing fixtures or when generation rules change
- See `01-data-generation.md`

### Phase 2: Individual Skill Evaluation
- Run each skill through a set of test prompts
- Measure success rate and token usage per prompt
- See `03-individual-skills/eval-*.md`

**Execution order:** Plans may run in any order. Each plan provisions its own data in a Data Setup step and cleans up in a Data Teardown step.


### Phase 3: Combined Skill Evaluation
- Chain write skills → read skills and verify consistency
- Run multi-step pipeline scenarios
- See `04-combined-skills/eval-*.md`


### Phase 4: Metrics Collection & Reporting
- Aggregate success rates, token counts, consistency scores
- See `02-metrics.md`

### Phase 4a: Runner Execution Summary

After all eval plans run, the runner should print a concise execution summary table to the console/log with one row per plan:

| Column | Meaning |
|--------|---------|
| Plan | Eval plan name (for example, `eval-spark-authoring`) |
| Duration | Runtime in seconds |
| Error | Captured execution error (if any) |

The summary must also include:

1. Total number of plans executed
2. Destination path where result files were copied

This summary is operational logging only. It does not replace the required markdown result files.

### Phase 4b: Runner Telemetry Artifact

In addition to the console summary, the runner must emit
`result/eval-run-telemetry.json`.

The JSON artifact should include:

1. Cleanup, per-plan, and post-processing phase records
2. Duration, status, error, bailout code, log path, and copied result path
3. Exact Copilot session IDs for each invocation
4. Skills used, tool-call count, and assistant-turn count from the session log
5. Token usage from the Copilot session shutdown metrics when available
6. Best-effort retry signals parsed from generated result markdown files

This file is operational telemetry for analysis and automation. It does not
replace the required markdown result files.

## Execution Rules (MANDATORY)

> **These rules are non-negotiable. The eval runner MUST follow them exactly for every eval plan.**

1. **EXECUTE every test case** — Send the prompt to the agent AND verify the actual Fabric API response or output. Every test MUST produce a real API call or command execution.
2. **No shortcuts** — Do NOT mark any test as "documented", "validated", "deferred", or "skipped". Do NOT invent a "tiered execution strategy" or any approach that avoids running tests.
3. **Record actual output** — For each test, capture the real HTTP status code, row counts, data returned, or error message. Synthetic or assumed results are not acceptable.
4. **Continue on failure** — If a test fails, record the failure with the actual error and proceed to the next test. Do not stop the eval.
5. **Sequential dependencies** — Tests that depend on prior write operations MUST be run in order.
6. **100% execution rate required** — The eval is only valid if every test case was actually executed against the Fabric workspace.
7. **No extra files** — Do NOT create any files other than the one result file specified per eval plan. No API reference docs, no execution summaries, no technical documentation — ONLY the results file.
8. **Use skills** — Execute ALL test cases and use skills. The whole purpose of this suite is to test skills
## Bailout Conditions (MANDATORY)

To prevent the evaluator from getting stuck on one test, apply these bailout rules for every case:

1. **No clear rules / insufficient instructions**
   - If the test cannot be executed because required rules or inputs are missing/contradictory, record an error and move on.
   - Use error code: **`EVAL-BAIL-001`**.

2. **Max retry attempts reached**
   - For any single test case, do not retry more than **3 attempts** total (initial attempt + up to 2 retries).
   - for any task which is part of your plan for executing a test case, do not retry more than **3 attempts** total (initial attempt + up to 2 retries).
   - After the 3rd failed attempt, record an error and move to the next test.
   - Use error code: **`EVAL-BAIL-003`**.

3. **Never block plan progress**
   - Bailout on the current test only.
   - Continue with the next test case in the same eval plan.
   - Do not abort the entire plan unless the runner process itself crashes.

4. **Suite-level bailout on skip**
   - If any plan result marks a test as `SKIP`/`SKIPPED`, the runner must abort the full suite immediately.
   - Use error code: **`EVAL-SUITE-010`**.
   - Rationale: skipped tests can invalidate dependency assumptions for subsequent plans.
   - Under parallel execution, the runner signals the bailout via a shared event;
     in-flight chains complete their current plan and then skip any remaining
     plans. SKIP semantics therefore still abort the suite, just with up to
     `ThrottleLimit` plans worth of latency before the abort lands.


## Parallel-Safety Contract (informational; runner-enforced)

The full-eval runner can dispatch multiple eval plans concurrently. Plans MUST
NOT assume serial ordering across the suite. Specifically:

1. **Plan-prefixed shared item names (default).** Any Delta table or other
   shared-name object written into the lakehouse / warehouse / semantic model
   from a plan MUST be prefixed with the plan's domain (for example
   `eval_spark_sales_transactions`). The runner provisions one shared workspace
   per run; concurrent plans share the lakehouse and warehouse and collide on
   un-prefixed generic names like `sales_transactions` or `products`.

   **Exception -- chain-serialized siblings MAY share un-prefixed names.** When
   every plan that touches a shared object is placed in the *same chain*
   (rule #3 below), those plans never execute concurrently, so collision is
   impossible by construction. In that case the object MAY use a domain-bare
   schema name (for example `eval.sales_transactions` in the warehouse,
   shared by `eval-sqldw-authoring`, `eval-sqldw-consumption`, and
   `eval-sqldw-authoring-plus-consumption`). Plans relying on this exception
   MUST document it explicitly in their **Data Setup** section and cite the
   chain that serializes them. Any object touched by plans from *different*
   chains still requires the plan-prefix per the default rule above.

2. **No cross-plan ordering assumptions.** A plan must not rely on a different
   plan having created or seeded any item. If two plans need the same data,
   each MUST seed its own copy (typically from the read-only fixtures under
   `evalsets/data-generation/`).

3. **Pair semantics preserved via "chains".** Plans named
   `eval-<workload>-authoring` and `eval-<workload>-consumption` run sequentially
   within a single chain (authoring first, then consumption) so consumption
   plans can rely on artifacts the authoring plan created. Combined plans
   (`eval-<workload>-authoring-plus-consumption`) join the same chain.

4. **Per-plan working directory + read-only fixture junctions.** The runner
   places each plan's cwd at `<TestFolder>/<plan-name>/`, with `evalsets/` and
   `plan/` exposed inside it as Windows junctions back to the shared roots.
   Relative paths like `evalsets/data-generation/<csv>` therefore resolve
   identically under serial and parallel execution.

5. **`result/` is per-plan, then staged.** Each plan writes its
   `<plan-name>-results.md` into its own `<plan-name>/result/` directory; the
   runner stages all per-plan results into `<TestFolder>/result/` before the
   merged summary step runs.

6. **Lakehouse `Files/` staging paths.** When plans upload fixtures to the
   shared `{{LAKEHOUSE}}`, identical content overwriting itself is benign
   (e.g. multiple plans uploading the same `sales_transactions_100.csv`), but
   distinct content under the same path would last-write-wins under parallel
   execution. New plans that upload non-fixture data into `{{LAKEHOUSE}}/Files/`
   SHOULD nest it under a plan-prefixed subdirectory (for example
   `Files/eval_spark/<artifact>`).


## Result File Format

Each eval plan produces **exactly one** result file. The file MUST be named `{plan-name}-results.md` where `{plan-name}` matches the eval plan filename without extension (e.g., `eval-spark-authoring.md` → `eval-spark-authoring-results.md`).

### Required structure

```markdown
# Eval Results: {skill or combined name}

**Workspace:** {workspace name} ({workspace ID})
**Run Date:** {YYYY-MM-DD}

## Summary Table

| Test ID | Status | Details |
|---------|--------|---------|
| XX-01   | PASS   | {brief} |
| XX-02   | FAIL   | {brief} |
...

If `Status = ERROR`, include the bailout code in `Details` (for example: `EVAL-BAIL-003: failed after 3 attempts`).

## Detailed Test Results

### XX-01: {Title}
- Prompt sent
- Actual API/command output
- Pass/fail determination
- If errored, include `Error Code` and `Attempt Count`

(repeat for each test case)

## Totals

| Status | Count |
|--------|-------|
| PASS   | N     |
| FAIL   | N     |
| ERROR  | N     |
| Total  | N     |
```

## Merged Summary

After all individual result files are produced, a single merged summary MUST be generated at `result/eval-results.md` containing:

1. A per-skill summary table (Skill | Total | Pass | Fail | Skip | Pass Rate)
2. An Overall row with aggregate counts
3. Detailed results per skill (extracted from individual result files)
4. A Failures Analysis table (only for FAIL cases: Case | Skill | Issue | Root Cause)

> **Important:** The merged summary is generated by *reading* the individual result files — it does NOT re-run any tests.

## Regression Analysis

After the merged summary is produced, compare results against the checked-in baseline at:

```
https://github.com/gim-home/skills-for-fabric/blob/main/tests/full-eval-tests/result/eval-results.md
```

Write the comparison to `result/regression_analysis.md` with:

1. **Overall pass rate** — baseline vs current, delta
2. **Per-skill comparison** — highlight improvements and regressions
3. **Persistent failures** — tests that failed in both runs (same root cause?)
4. **New coverage** — tests that exist in current but not in baseline
5. **Verdict** — one of: `BETTER` (no regressions, pass rate same or higher), `REGRESSION` (any test that was passing is now failing), `SAME` (identical results)

If no baseline exists (first run), skip the comparison.

## Eval Execution Model

Each eval is a **prompt → skill invocation → result verification** loop:

> **Note:** All prompts that reference "my workspace" refer to the `EVAL_WORKSPACE` provided by the runner in the prompt.

```
For each eval case:
  1. Record start state (token counter, workspace state)
  2. Send the eval prompt to the agent
  3. Agent invokes the skill
  4. Capture: success/failure, token usage, output
  5. For write+read pairs: verify read output == expected data
  6. Log results to eval tracker
```

## Pass/Fail Criteria

| Metric | Pass Threshold |
|--------|---------------|
| Success Rate | ≥ 90% per skill |
| Token Usage | Within 2x of baseline (established in first run) |
| Read/Write Consistency | 100% exact match for all write→read pairs |

## Dependencies

- Active Microsoft Fabric workspace with capacity
- At least one Lakehouse provisioned
- At least one Data Warehouse provisioned
- At least one Eventhouse with a KQL Database provisioned
- At least one Power BI Semantic Model provisioned (for powerbi-authoring/consumption evals)
- Fabric API authentication configured (Azure CLI or token)
