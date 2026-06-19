# Eval Plan: spark-operations-cli

## Skill Overview
- **Skill:** `spark-operations-cli`
- **Category:** Spark / Operations (Read)
- **Purpose:** Diagnose failed Spark jobs, unhealthy Livy sessions, and performance bottlenecks using Fabric REST APIs, Spark Monitoring APIs, Spark Advisor, Resource Usage, and logs.

## Pre-requisites
- Shared `{{WORKSPACE}}` workspace provisioned by runner.
- Shared `{{LAKEHOUSE}}` lakehouse provisioned by runner.
- Spark capacity available.
- Fabric API authentication configured.
- Spark Monitoring APIs available for the workspace.

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) - all rules apply to every test below.

## Data Setup (run FIRST - before any test cases)

This diagnostic plan needs at least one completed Spark application and one intentionally failed notebook run.

1. Create or reuse a notebook named `spark_operations_failing_notebook` in `{{WORKSPACE}}` attached to `{{LAKEHOUSE}}`.
2. The notebook should execute a small Spark statement and then raise a deterministic error: `RuntimeError("spark operations eval failure")`.
3. Trigger the notebook and wait until the job instance reaches a failed terminal state.
4. Capture the notebook item ID and failed job instance ID for verification.
5. If the runner supports session setup, leave one idle Livy session available for session-health diagnostics.

## Test Cases

### SO-01: Failed Notebook Job Diagnosis *(infrastructure)*
- **Prompt:** "In workspace {{WORKSPACE}}, diagnose the latest failed run for notebook spark_operations_failing_notebook. Retrieve the job instance details and explain the failure reason."
- **Expected:** The skill uses workspace/item discovery, retrieves recent job instances, selects the failed run, and reports the deterministic failure.
- **Pass criteria:** Response includes the notebook name, failed job status, job instance ID or equivalent run identifier, and `spark operations eval failure`.
- **Metrics:** Success rate, token usage, time to diagnosis.

### SO-02: Session Health Triage *(infrastructure or description)*
- **Prompt:** "In workspace {{WORKSPACE}}, check Spark Livy session health and identify idle, stuck, or unhealthy sessions without killing active work."
- **Expected:** The skill lists sessions or describes the exact read-only session-health checks when no session exists.
- **Pass criteria:** Response classifies session states, distinguishes active from idle sessions, and avoids destructive cleanup without checking active statements.
- **Metrics:** Correct state classification, safety of remediation guidance.

### SO-03: Performance Diagnostics With Monitoring APIs *(infrastructure)*
- **Prompt:** "In workspace {{WORKSPACE}}, diagnose Spark performance for the most recent Spark application using Spark Advisor and Resource Usage metrics."
- **Expected:** The skill checks Spark Monitoring APIs before raw log parsing and summarizes advisor findings, skew signals, task errors, or core efficiency.
- **Pass criteria:** Response references Spark Advisor or Resource Usage results and provides a prioritized diagnosis rather than generic Spark tuning advice.
- **Metrics:** Correct API selection, specificity of recommendations.

### SO-04: Negative - Authoring Request Boundary *(description)*
- **Prompt:** "Create a new notebook and run a Spark job that loads sales data into a Delta table."
- **Expected:** The skill should not take over authoring work; it should route or recommend `spark-authoring-cli`.
- **Pass criteria:** Response clearly identifies this as authoring, not diagnostics.
- **Verification:** Text response only - do NOT create resources.

### SO-05: Workspace-wide Spark Activity Health *(infrastructure)*
- **Prompt:** "In workspace {{WORKSPACE}}, review the health of all Spark activities and summarize any failures or anomalies."
- **Expected:** The skill lists recent Spark job instances across the workspace, groups by state, and highlights failures.
- **Pass criteria:** Response provides a health overview covering multiple items, identifies failed runs, and distinguishes item types (Notebook, SJD, Lakehouse).
- **Metrics:** Coverage breadth, correct state classification.

### SO-06: Notebook Past Runs Diagnosis *(infrastructure)*
- **Prompt:** "In workspace {{WORKSPACE}}, review the health and diagnose failures across the past runs of notebook spark_operations_failing_notebook."
- **Expected:** The skill retrieves job instance history for the notebook, identifies failure patterns, and provides root cause analysis.
- **Pass criteria:** Response includes multiple run statuses, identifies the failure pattern, and provides actionable diagnosis.
- **Metrics:** Correct history retrieval, pattern detection accuracy.

### SO-07: Pipeline-Run Diagnosis *(infrastructure)*
- **Prompt:** "In workspace {{WORKSPACE}}, diagnose the most recent failed pipeline run and identify which Spark activity caused the failure."
- **Expected:** The skill uses `queryActivityRuns` to correlate pipeline activities with Spark sessions, identifies the failed activity, and extracts error details.
- **Pass criteria:** Response identifies the failed pipeline activity, correlates to a Spark session, and presents error details from `output.result.error`.
- **Metrics:** Correct cross-activity correlation, error extraction completeness.
- **Missing infra note:** If no `DataPipeline` item exists in the eval workspace (Phase 0b does not provision one today), record status as `ERROR` with detail `EVAL-BAIL-001: no DataPipeline item available in eval workspace`. Do NOT use SKIP — SKIP triggers a suite-level abort per `00-overview.md`. This deterministic failure mode prevents the silent error class observed in run #25988928060.

### SO-08: Lakehouse Past Runs Diagnosis *(infrastructure)*
- **Prompt:** "In workspace {{WORKSPACE}}, review the health and diagnose failures across the past operation runs for lakehouse {{LAKEHOUSE}}."
- **Expected:** The skill retrieves job instance history for the lakehouse item and identifies any failed operations.
- **Pass criteria:** Response includes operation run history, state classification, and failure diagnosis if any runs failed.
- **Metrics:** Correct item type handling, operation history retrieval.

### SO-09: SJD Past Runs Diagnosis *(infrastructure)*
- **Prompt:** "In workspace {{WORKSPACE}}, review the health and diagnose failures across the past runs of Spark Job Definition 'DailyETL'."
- **Expected:** The skill retrieves SJD job instance history and diagnoses any failures.
- **Pass criteria:** Response includes SJD run history, identifies failures, and provides root cause analysis.
- **Metrics:** Correct SJD item discovery, job instance retrieval.
- **Missing infra note:** If no `SparkJobDefinition` item exists in the eval workspace (Phase 0b does not provision one today), record status as `ERROR` with detail `EVAL-BAIL-001: no SparkJobDefinition item available in eval workspace`. Do NOT use SKIP — SKIP triggers a suite-level abort per `00-overview.md`. This deterministic failure mode prevents the silent error class observed in run #25988928060.

### SO-10: Retention-Expired Fallback *(infrastructure)*
- **Prompt:** "In workspace {{WORKSPACE}}, diagnose the failed Spark job for notebook spark_operations_failing_notebook — the job ran several days ago and Spark Monitoring API data may have expired."
- **Expected:** The skill attempts Spark Monitoring APIs, handles 404/empty responses gracefully, falls back to Job Instance API and queryActivityRuns, and always presents the Notebook Snapshot URL.
- **Pass criteria:** Response acknowledges data expiration, uses fallback APIs, presents Notebook Snapshot URL for manual inspection, and recommends diagnosing within retention window for future failures.
- **Metrics:** Graceful degradation, snapshot URL presence, retention guidance.

## Data Teardown (run LAST - after all test cases)

1. Delete `spark_operations_failing_notebook` if it was created by this eval.
2. Stop any Livy sessions created by the eval after confirming no active statements remain.
3. Leave the shared `{{LAKEHOUSE}}` lakehouse in place.

## Expected Token Range
- 1500-3500 tokens per invocation