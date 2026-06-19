# skills-for-fabric Tests

This folder contains tests for validating skills-for-fabric. There are **three distinct testing layers** here, often confused:

1. **Pytest layer (semantic + integration)** -- described in this README. Lightweight unit/integration tests run via `npm test`, `pytest`, or the `quality_checker.py` workflow. Auth: standard `az login` against any Fabric workspace you have access to, configured via `FABRIC_TEST_*` env vars. This is the layer the PR validation workflow runs automatically.
2. **Vally layer (primary PR + nightly harness)** -- `tests/evals/<skill>/eval.yaml`, run through `tests/run-vally-eval.ps1` and `.github/workflows/fabric-smoke-vally.yml`. Add new skill behavior coverage here; see [`evals/README.md`](evals/README.md).
3. **Legacy manual-only smoke + full-eval layer (PowerShell runners)** -- `tests/run-smoke-tests.ps1` and `tests/run-full-tests.ps1`. These provision a fresh workspace, run live Copilot CLI sessions against legacy `tests/tests.json` / `tests/full-eval-tests/`, and grade results. Use legacy smoke only as break-glass; see [`../docs/legacy-smoke-break-glass.md`](../docs/legacy-smoke-break-glass.md) and [`../docs/testing-guide.md`](../docs/testing-guide.md).

## Test Categories

| Marker | Description | External Deps |
|--------|-------------|---------------|
| `semantic` | Validates skill semantics (triggers, descriptions, naming) | None |
| `integration` | Tests against real Fabric endpoints | Azure + Fabric |
| `sqlcmd` | Tests requiring sqlcmd CLI | sqlcmd (Go) |

## Setup

### Install Dependencies

```bash
pip install -r tests/requirements-dev.txt
```

### For Integration Tests

1. **Authenticate to Azure:**
   ```bash
   az login
   ```

2. **Install sqlcmd (Go version):**
   - Windows: `winget install sqlcmd`
   - macOS: `brew install sqlcmd`
   - Linux: `apt-get install sqlcmd`

3. **Set environment variables:**
   ```bash
   # Required for all integration tests
   export FABRIC_TEST_WORKSPACE_ID="<your-workspace-guid>"
   
   # For SQL endpoint tests
   export FABRIC_TEST_WAREHOUSE_ID="<your-warehouse-guid>"
   export FABRIC_TEST_ENDPOINT="<endpoint>.datawarehouse.fabric.microsoft.com"
   export FABRIC_TEST_DATABASE="<WarehouseName>"
   
   # For Spark/Livy tests
   export FABRIC_TEST_LAKEHOUSE_ID="<your-lakehouse-guid>"
   ```

   **PowerShell:**
   ```powershell
   $env:FABRIC_TEST_WORKSPACE_ID = "<your-workspace-guid>"
   $env:FABRIC_TEST_WAREHOUSE_ID = "<your-warehouse-guid>"
   $env:FABRIC_TEST_ENDPOINT = "<endpoint>.datawarehouse.fabric.microsoft.com"
   $env:FABRIC_TEST_DATABASE = "<WarehouseName>"
   $env:FABRIC_TEST_LAKEHOUSE_ID = "<your-lakehouse-guid>"
   ```

## Running Tests

### All Tests
```bash
npm test
# or
python -m pytest
```

### Semantic Tests Only (No External Deps)
```bash
npm run test:semantic
# or
python -m pytest -m semantic
```

### Integration Tests Only
```bash
npm run test:integration
# or
python -m pytest -m integration
```

### Full Eval Runner

```powershell
# All plans (nightly equivalent)
cd tests
.\run-full-tests.ps1

# One skill only (workload-owner shortcut)
.\run-full-tests.ps1 -PlanFilter "eval-<skill>" -skipLogin -SkipWarehouse -SkipLakehouse -SkipCleanup -capacityId "<cap>" -tenant "<tenant>"
```

`-PlanFilter` accepts a comma-separated list. Unknown plan names hard-fail BEFORE provisioning. CI auto-applies the filter on PRs that touch a skill with eval coverage. See [`full-eval-tests/README.md`](full-eval-tests/README.md) for the catalog and [`../docs/testing-guide.md`](../docs/testing-guide.md#pr-touched-gates-ci-auto-runs) for the gate.

Each full run also writes `tests\full-eval-tests\result\eval-run-telemetry.json`.
That JSON captures per-phase duration, exact Copilot session IDs, skills used,
assistant turns, tool calls, token usage from session logs, and best-effort
retry signals parsed from the generated result markdown files.

### Coverage Gap Report
```bash
python tests/coverage_gap_report.py
```

- Prints a markdown summary of smoke gaps, individual-eval gaps, and current combined-eval participation
- Writes `coverage-gap-report.json` at the repo root
- Advisory only for now; it does **not** fail on existing gaps
- After merge, `.github/workflows/daily-coverage-gap-report.yml` runs it daily and uploads `coverage-gap-report.json` as a workflow artifact

### Specific Test File
```bash
python -m pytest tests/test_sqldw_consumption.py -v
```

### Skip Slow Tests
```bash
python -m pytest -m "not integration"
```

## Test Structure

```
tests/
├── copilot-session-telemetry.ps1 # Shared Copilot session log parsing for eval telemetry
├── coverage_gap_report.py       # Advisory smoke/eval coverage audit
├── copilot-session-telemetry.ps1 # Shared Copilot session log parsing for eval telemetry
├── conftest.py                  # Shared fixtures, helpers
├── requirements-dev.txt         # Test dependencies
├── test_coverage_gap_report.py  # Coverage report unit tests
├── test_semantic.py             # Skill semantic validation
├── run-full-tests.ps1           # Full eval runner
├── test_sqldw_consumption.py    # SQL endpoint read tests
├── test_sqldw_authoring.py      # SQL endpoint write tests
├── test_spark_consumption.py    # Livy session tests
├── test_spark_authoring.py      # Lakehouse/notebook tests
└── full-eval-tests/             # Full eval plans, fixtures, and results
```

## Writing New Tests

### Semantic Test Example
```python
@pytest.mark.semantic
def test_my_semantic_check(all_skills):
    for skill_name, skill_data in all_skills.items():
        assert "something" in skill_data["description"]
```

### Integration Test Example
```python
@pytest.mark.integration
@pytest.mark.sqlcmd
def test_my_sql_query(fabric_config, sqlcmd_available, az_authenticated):
    if not sqlcmd_available:
        pytest.skip("sqlcmd not available")
    
    endpoint = fabric_config.get("endpoint")
    database = fabric_config.get("database")
    
    returncode, stdout, stderr = run_sqlcmd(endpoint, database, "SELECT 1")
    assert returncode == 0
```

## Notes

- Semantic tests run without any external dependencies
- Integration tests require Azure authentication and Fabric access
- Integration tests that create resources (tables, lakehouses) clean up after themselves
- Use a **dedicated test workspace** for integration tests
- Tests are idempotent and can be run multiple times

