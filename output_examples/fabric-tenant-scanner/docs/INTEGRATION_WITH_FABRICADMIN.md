# Fabric Tenant Scanner — Integration Guide

## For FabricAdmin Agent

The Fabric Tenant Scanner produces structured output that the **FabricAdmin** agent can consume for workspace documentation, governance analysis, and compliance reporting.

---

## Integration Points

### 1. Output Artifacts

The scanner produces these artifacts that FabricAdmin can use:

```
output/
├── tenant-inventory.json          # Machine-readable artifact inventory
├── tenant-report.md               # Executive summary
├── dependencies.json              # Dependency graph
├── dependencies.csv               # Dependency table
├── dependencies.mermaid           # Lineage diagram
└── lineage.mermaid               # Data flow visualization
```

### 2. Input to FabricAdmin Workflow

**Current Workflow (Manual):**
```
User → FabricAdmin → Workspace exploration → Manual documentation
```

**Enhanced Workflow (with Scanner):**
```
User → Scanner (automated discovery)
    ↓
    → tenant-inventory.json
    ↓
    → FabricAdmin (consumes inventory)
    ↓
    → Dependency analysis
    ↓
    → Executive report + governance insights
```

---

## Usage with FabricAdmin

### Step 1: Run Scanner
```bash
# From fabric-tenant-scanner/
python -m examples.basic_scan
```

### Step 2: FabricAdmin Processes Results
```python
from fabric_scanner import FabricTenantScanner
from dependency_mapper import DependencyMapper
import json

# Load scanner results
with open("./output/tenant-inventory.json") as f:
    inventory = json.load(f)

# Generate governance report
report = {
    "inventory_summary": {
        "workspaces": len(inventory['workspaces']),
        "semantic_models": len(inventory['semantic_models']),
        "reports": len(inventory['reports'])
    },
    "high_risk_findings": [
        # Orphaned models with no reports
        # Data sources with multiple dependencies
        # Cross-workspace references
    ]
}
```

---

## Output Formats

### 1. JSON Inventory
**File:** `tenant-inventory.json`

Used for programmatic access, API integration, database import.

```json
{
  "tenant_id": "...",
  "scan_timestamp": "2026-04-01T07:35:33Z",
  "workspaces": [
    {
      "id": "ws-001",
      "name": "Analytics",
      "capacity_id": "...",
      "artifact_count": 24
    }
  ],
  "semantic_models": [
    {
      "id": "model-001",
      "name": "Sales Model",
      "workspace_id": "ws-001",
      "table_count": 12,
      "measure_count": 45,
      "data_sources": [
        {"name": "SQL Server", "type": "SQL"}
      ]
    }
  ],
  "dependencies": [...]
}
```

### 2. Markdown Report
**File:** `tenant-report.md`

Human-readable executive summary with actionable insights.

```markdown
# Fabric Tenant Scan Report

**Scan Timestamp:** 2026-04-01T07:35:33Z
**Status:** completed
**Tenant ID:** 12345678-...

## Summary
- Workspaces: 5
- Semantic Models: 42
- Reports: 128
- Dependencies: 256

## Workspaces

### Analytics Workspace
- **ID:** ws-001
- **Capacity:** Premium P2
- **Semantic Models:** 12
  - Sales Model (45 measures, 12 tables)
  - Customers Model (18 measures, 8 tables)
  - ...
- **Reports:** 28
  - Sales Dashboard
  - Customer Insights
  - ...
```

### 3. Dependency Graph (Mermaid)
**File:** `dependencies.mermaid`

Visual representation for architecture documents and presentations.

```mermaid
graph LR
  source1["SQL Server: SalesDB"]:::DataSource
  model1["Sales Model"]:::SemanticModel
  report1["Sales Dashboard"]:::Report
  
  source1 -->|feeds| model1
  model1 -->|consumed_by| report1
  
  classDef SemanticModel fill:#4A90E2,stroke:#2E5C8A,color:#fff
  classDef Report fill:#50E3C2,stroke:#2D8B7A,color:#fff
  classDef DataSource fill:#F5A623,stroke:#8B6914,color:#fff
```

### 4. CSV Dependencies
**File:** `dependencies.csv`

For import into Excel, Power BI, or analytics tools.

```csv
source_id,source_name,source_type,target_id,target_name,target_type,relationship_type
model-001,Sales Model,SemanticModel,report-001,Sales Dashboard,Report,consumed_by
source-001,SQL Server: SalesDB,DataSource,model-001,Sales Model,SemanticModel,feeds
```

---

## Key Insights FabricAdmin Can Extract

### 1. Workspace Health
```python
findings = {
    "orphaned_models": [],      # Models with no consuming reports
    "unused_data_sources": [],  # Data sources not powering any models
    "isolated_components": []   # Disconnected artifact groups
}
```

### 2. Governance Risks
- **Cross-workspace dependencies** → Requires coordination for changes
- **Complex lineage** → Risk of cascading failures
- **Many-to-many relationships** → Data quality concerns
- **Stale models** → Not modified in X days

### 3. Capacity Optimization
- **Most-used models** → Priority for performance tuning
- **Underutilized artifacts** → Candidates for consolidation
- **Refresh dependencies** → Optimization opportunities

---

## Integration Checklist

- [ ] Scanner discovers all workspaces in tenant
- [ ] Inventory includes all semantic models and reports
- [ ] Dependency graph identifies all relationships
- [ ] Output formats validated (JSON schema, CSV columns)
- [ ] FabricAdmin can parse and consume JSON
- [ ] Governance rules implemented on scanner insights
- [ ] Automated reporting scheduled (daily/weekly)

---

## Roadmap

### Phase 1: Discovery (✅ Current)
- Enumerate workspaces, models, reports
- Export structured inventory

### Phase 2: Metadata Extraction (🚧 Next)
- Parse TMDL/BIM for table/measure details
- Extract Power Query source queries
- Parse DAX formula dependencies

### Phase 3: Lineage Tracing (📋 Future)
- Map column-level lineage
- Identify data quality dependencies
- Build impact radius calculations

### Phase 4: Governance Integration (📋 Future)
- Real-time compliance scanning
- Automated policy enforcement
- Change impact predictions

---

## Example: FabricAdmin Workflow

```python
# Load scanner results
inventory = json.load(open("./output/tenant-inventory.json"))
dependency_report = json.load(open("./output/dependencies.json"))

# Generate FabricAdmin report
report = {
    "timestamp": datetime.now().isoformat(),
    "workspace_governance": {
        "total_workspaces": len(inventory['workspaces']),
        "workspaces_with_models": sum(1 for w in inventory['workspaces'] if w['model_count'] > 0),
        "workspaces_without_reports": sum(1 for w in inventory['workspaces'] if w['report_count'] == 0),
    },
    "model_health": {
        "total_models": len(inventory['semantic_models']),
        "models_in_use": sum(1 for m in inventory['semantic_models'] if m['consumer_count'] > 0),
        "orphaned_models": dependency_report['orphaned_nodes'],
        "high_impact_models": dependency_report['high_impact_nodes'],
    },
    "data_lineage": {
        "total_dependencies": dependency_report['summary']['total_edges'],
        "circular_dependencies": len(dependency_report['summary']['cycles_detected']),
        "isolated_components": len(dependency_report['isolated_components']),
    },
    "recommendations": [
        "Archive 3 orphaned semantic models to reduce maintenance",
        "Consolidate 5 overlapping customer models",
        "Document cross-workspace dependencies for Sales-Finance integration",
    ]
}

# Export governance report
with open("./FabricAdmin-Governance-Report.json", "w") as f:
    json.dump(report, f, indent=2)
```

---

## API Contract

### Scanner Output → FabricAdmin Input

**Contract:**
1. Scanner produces `tenant-inventory.json` with canonical structure
2. FabricAdmin consumes via standardized JSON schema
3. FabricAdmin enriches with governance rules and policies
4. FabricAdmin exports governance report for compliance/audit

**Schema Version:** 1.0  
**Last Updated:** 2026-04-01

---

## Next Steps

1. **Run the scanner** on your Fabric tenant
2. **Review the output** (especially `tenant-report.md`)
3. **Check for governance risks** in `dependencies.json`
4. **Feed to FabricAdmin** for deeper analysis and policy enforcement
5. **Schedule regular scans** for continuous compliance monitoring

See `README.md` for setup instructions.
