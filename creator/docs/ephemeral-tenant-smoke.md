# Ephemeral Tenant Smoke (legacy manual-only break-glass)

> **LEGACY BREAK-GLASS ONLY:** Vally is the primary PR and nightly harness. Start with [`tests/evals/README.md`](../tests/evals/README.md). Use this legacy smoke path only to cross-check a suspected Vally false negative or during a Vally outage.

The shared ephemeral tenant setup still matters for manual validation because both Vally and the legacy smoke runner need a Fabric workspace. Microsoft contributors should use the tenant rotation details from `aka.ms/fabrictenants` and the current service-principal or certificate flow documented in the tenant runbook.

The legacy smoke flow used `apitestadmin@E2EAPIMSIT2.onmicrosoft.com` with a certificate downloaded from the `E2EAPIMSIT2-GA` Key Vault. Two problems:

1. **Access was gated** -- every developer + CI principal needed the `pbitestusera-3iqq` entitlement to download the cert.
2. **Not shared with the rest of the Fabric platform** -- other teams use the ephemeral Shared Test Tenant pattern at `aka.ms/fabrictenants`.

This document describes the flow that nightly CI historically used and that contributors may still need as a manual break-glass: the ephemeral pattern + a service principal we register ourselves, so the smoke can run unattended in GitHub Actions without per-developer entitlements. Day-to-day skill validation should go through Vally instead -- see [`tests/evals/README.md`](../tests/evals/README.md).

## Architecture

```
GitHub Actions runner (or developer laptop)
        |
        |  1. az login --service-principal --tenant <ephemeral-tenant>
        |     --username <our-SP-appId> --certificate <PEM>
        v
ephemeral Shared Test Tenant (msitprimary03192026.onmicrosoft.com or current rotation)
        |
        |  2. Acquire Fabric token (aud: https://api.fabric.microsoft.com, idtyp: app)
        v
Fabric REST API
        |  3. setup_test_env.py creates a fresh workspace + lakehouse + eventhouse + dataflow
        |     and grants our SP Contributor on the workspace (via --sp-object-id)
        v
testFabricSkills.ps1
        |  4. Reinstalls the local fabric-skills plugin
        |  5. Runs each test in tests/tests.json against the workspace
        |  6. Grades pass/fail via substring match
        v
Results (testsResults.json + per-test *_output.txt)
```

## What this is NOT

- **Not the primary harness.** Vally is the primary PR and nightly harness -- start with [`tests/evals/README.md`](../tests/evals/README.md).
- **Not Phase B yet.** Nightly + `workflow_dispatch` runs use Phase A (direct GH Actions secrets). Phase B (OIDC + central Key Vault) is the planned follow-up.
- **Not a substitute for manual checks the PR description should mention.** CI captures Vally + full-eval results in the sticky comment; contributors still note any manual evidence CI cannot produce (Jaccard, baseline comparison, tenant-specific repro).
- **Full-eval local run.** For workload-owner one-skill validation, use `tests/run-full-tests.ps1 -PlanFilter "eval-<skill>"` (see [`../tests/full-eval-tests/README.md`](../tests/full-eval-tests/README.md)). For the PR-touched gate, see [testing-guide.md](testing-guide.md#pr-touched-gates-ci-auto-runs).

## What was validated (2026-05-11 PoC)

| Step | Result |
|---|---|
| Cert from `aka.ms/fabrictenants` (AdminUser01 PFX) | PASS Valid for the current rotation (expiry varies per rotation cycle -- see runbook for current date) |
| `az login --tenant msitprimary03192026.onmicrosoft.com` as AdminUser01 (browser CBA) | PASS |
| `az ad app create` + `az ad sp create` for a new SP named `fabric-skills-smoke-test` | PASS (AdminUser01 has Application Administrator role) |
| Self-signed cert uploaded to the new SP | PASS |
| SP added as Contributor on the test workspace | PASS |
| `az login --service-principal --certificate` as the new SP | PASS |
| Fabric REST API as SP returns only workspaces SP has explicit access to | PASS |
| `testFabricSkills.ps1 -testName dataflows-consumption-list-and-inspect` as SP | PASS Y, 1/1, 280s |

The end-to-end flow works without any human in the loop after the SP cert is installed.

## How to run locally (break-glass)

### One-time setup (per developer)

1. Join `PBI-Test-UserAcc-Access` AAD security group (auto-approved for Azure Data Org).
2. Wait 24-48 hours for propagation.
3. Open `aka.ms/fabrictenants`, download `AdminCert01.pfx` for the current `MsitPrimary` tenant.
4. Install in `Cert:\CurrentUser\My` (`Import-PfxCertificate -FilePath <pfx> -CertStoreLocation Cert:\CurrentUser\My`).
5. `az login --tenant <current-tenant>.onmicrosoft.com` (browser will offer the installed cert).
6. *Optional, one-time*: provision your own SP in the test tenant by following Steps 3-4 of [the tenant rotation runbook](tenant-rotation-runbook.md). AdminUser01 has Application Administrator role, so you can do this yourself.

### Each manual legacy smoke invocation

```powershell
gh workflow run fabric-smoke-ephemeral.yml --repo gim-home/skills-for-fabric --ref <branch> --field test-names=<legacy-smoke-name> # legacy manual-only break-glass
```

Local legacy smoke invocation:

```powershell
./tests/run-smoke-tests.ps1 -tenant "<current-tenant>.onmicrosoft.com" -skipLogin -testName "<legacy-smoke-name>" # legacy manual-only break-glass
```

Do not add new coverage here. Add or update `tests/evals/<skill>/eval.yaml` and follow the canonical Vally guide.
