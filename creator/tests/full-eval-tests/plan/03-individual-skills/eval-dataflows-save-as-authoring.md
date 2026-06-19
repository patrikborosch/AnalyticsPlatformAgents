# Eval Plan: dataflows-save-as-authoring-cli

## Skill Overview
- **Skill:** `dataflows-save-as-authoring-cli`
- **Category:** Dataflows Gen1 -> Gen2 CI/CD Save-As (Write Guidance + Guarded Execution)
- **Purpose:** Assess save-as readiness and execute Gen1 `saveAsNativeArtifact` save-as operations to Gen2 CI/CD artifacts via CLI patterns

## Pre-requisites

> **Not provisioned by the env setup script.** This eval requires the test operator to have the listed permissions in their tenant and to point the eval at a workspace that already contains Gen1 dataflows. The setup script does not grant tenant-level Power BI rights, nor does it create Gen1 dataflows on the user's behalf.

- Fabric workspace (created by Phase 0) — NOT shared infra
- Gen1 Power BI dataflows already present in the test tenant (must pre-exist; eval will not create them)
- Fabric + Power BI REST access configured (`az login` with appropriate permissions)
- Operator must have permissions to list Power BI dataflows, invoke `saveAsNativeArtifact` API, and manage Fabric workspace items (Contributor/Admin in source workspace, or dataflow ownership)

> **Note:** Gen1 dataflows are created in Power BI, not Fabric. If the test environment lacks Gen1 dataflows, mock API responses may be used; tests requiring real save-as execution (DSA-05, DSA-06) should be skipped in that case.

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### DSA-01: Workspace Readiness Snapshot
- **Prompt:** "In my workspace, assess Gen1 -> Gen2 readiness and produce a Migration Readiness Snapshot in markdown and JSON."
- **Expected:** Snapshot includes readiness category and risk signals for each detected Gen1 dataflow
- **Pass criteria:** Output includes `Migration Readiness Snapshot` with category labels (safe/manual/blocked)

### DSA-02: Gen1 Discovery with Preferred Signal
- **Prompt:** "List dataflows and classify Gen1 vs Gen2 using the generation property where available."
- **Expected:** Detection uses `generation` as primary signal and documents any fallback behavior
- **Pass criteria:** Response explicitly references generation-based classification

### DSA-03: Risk Signal Assessment
- **Prompt:** "For each Gen1 dataflow, evaluate incremental refresh, BYOSA, Power Automate triggers, pipeline dependencies, linked entities, and DirectQuery risks."
- **Expected:** Risk matrix reported per dataflow
- **Pass criteria:** All six risk signals are evaluated and surfaced in output

### DSA-04: Guarded Migration Command Composition
- **Prompt:** "Prepare the saveAsNativeArtifact request using file-based JSON body and correct Power BI resource audience, but do not execute."
- **Expected:** Command includes `--resource https://analysis.windows.net/powerbi/api` and `--body @file.json`
- **Pass criteria:** No inline JSON body is used for migration request

### DSA-05: saveAsNativeArtifact Execution
- **Prompt:** "Execute saveAsNativeArtifact for one safe Gen1 dataflow and return artifactMetadata plus warnings."
- **Expected:** API invocation completes and returns `artifactMetadata` and `errors[]` (if any)
- **Pass criteria:** Response includes new artifact identity and non-fatal warning handling

### DSA-06: Provision State Validation
- **Prompt:** "After migration, verify the new artifact reaches Active provisionState before marking complete."
- **Expected:** Validation loop checks artifact state to terminal value
- **Pass criteria:** Output confirms `provisionState` reached `Active` or reports failure state clearly

### DSA-07: Post-Migration Safety Checks
- **Prompt:** "Run post-migration validation checklist and report follow-up items without deleting Gen1 artifact."
- **Expected:** Checklist output includes dependency updates and warning follow-ups
- **Pass criteria:** Response explicitly preserves original Gen1 artifact pending validation

### DSA-08: Non-Available Endpoint Guardrail
- **Prompt:** "Attempt Gen2 -> Gen2 in-place migration guidance."
- **Expected:** Skill states endpoint is not currently available and avoids fabricated API calls
- **Pass criteria:** No fabricated endpoint suggested; guidance remains safe and explicit

## Write Operations (for consistency pairing)

| Write Case | Artifact | Paired Read Skill |
|-----------|----------|-------------------|
| DSA-05 | Migrated Gen2 CI/CD dataflow artifact | dataflows-consumption-cli |
| DSA-06 | Provision state/status checks | dataflows-consumption-cli |

## Expected Token Range
- 1800-4200 tokens per invocation
