# Fabric Tenant Scanner — API Reference

**Version:** 0.1 (Prototype)

---

## Core Classes

### 1. FabricTenantScanner

Main orchestrator class for tenant discovery and artifact analysis.

#### Constructor
```python
FabricTenantScanner(config: TenantConfig)
```

**Parameters:**
- `config` (TenantConfig): Configuration object with tenant ID and discovery parameters

**Example:**
```python
from scanner import FabricTenantScanner, TenantConfig

config = TenantConfig(
    tenant_id="12345678-1234-1234-1234-123456789abc",
    environment="production",
    exclude_workspaces=["Archive"]
)

scanner = FabricTenantScanner(config)
```

#### Methods

##### discover_workspaces()
Discover all workspaces in tenant.

```python
workspaces: List[WorkspaceInfo] = scanner.discover_workspaces()
```

**Returns:** List of `WorkspaceInfo` objects

**Example:**
```python
workspaces = scanner.discover_workspaces()
for ws in workspaces:
    print(f"Workspace: {ws.name} (ID: {ws.id})")
```

---

##### enumerate_semantic_models(workspace_id: str)
List all semantic models in a workspace.

```python
models: List[SemanticModelInfo] = scanner.enumerate_semantic_models(workspace_id)
```

**Parameters:**
- `workspace_id` (str): Workspace ID

**Returns:** List of `SemanticModelInfo` objects

**Example:**
```python
models = scanner.enumerate_semantic_models("ws-analytics")
for model in models:
    print(f"Model: {model.name}")
    print(f"  Tables: {model.table_count}")
    print(f"  Measures: {model.measure_count}")
```

---

##### enumerate_reports(workspace_id: str)
List all reports in a workspace.

```python
reports: List[ReportInfo] = scanner.enumerate_reports(workspace_id)
```

**Parameters:**
- `workspace_id` (str): Workspace ID

**Returns:** List of `ReportInfo` objects

---

##### run_full_scan()
Execute complete tenant scan (discovery + enumeration + dependency building).

```python
summary: Dict[str, Any] = scanner.run_full_scan()
```

**Returns:** Summary dict with counts and status

**Example:**
```python
summary = scanner.run_full_scan()
print(f"Scan Status: {summary['status']}")
print(f"Workspaces: {summary['workspace_count']}")
print(f"Models: {summary['semantic_model_count']}")
```

---

##### export_to_json(output_path: str)
Export inventory to JSON file.

```python
scanner.export_to_json("./output/tenant-inventory.json")
```

**Output Format:**
```json
{
  "tenant_id": "...",
  "scan_timestamp": "2026-04-01T...",
  "workspaces": [...],
  "semantic_models": [...],
  "reports": [...],
  "dependencies": [...]
}
```

---

##### export_to_markdown(output_path: str)
Export inventory to Markdown report.

```python
scanner.export_to_markdown("./output/tenant-report.md")
```

---

### 2. TmdlParser

Parse TMDL (Tabular Model Definition Language) files.

#### Static Methods

##### parse_tmdl_file(file_path: str)
Parse a TMDL file.

```python
from tmdl_parser import TmdlParser

model = TmdlParser.parse_tmdl_file("./models/Sales.tmdl")
```

**Parameters:**
- `file_path` (str): Path to TMDL file

**Returns:** Parsed model structure (Dict)

**Raises:**
- `FileNotFoundError`: If file doesn't exist
- `yaml.YAMLError`: If TMDL is invalid

---

### 3. BimParser

Parse BIM (Power BI model file) in JSON format.

#### Static Methods

##### parse_bim_file(file_path: str)
Parse a BIM file.

```python
from tmdl_parser import BimParser

model = BimParser.parse_bim_file("./models/Sales.bim")
```

**Parameters:**
- `file_path` (str): Path to BIM file

**Returns:** Parsed model structure (Dict)

---

### 4. ModelAnalyzer

Analyze parsed model structures for insights.

#### Static Methods

##### analyze_model(parsed_model: Dict[str, Any])
Generate insights about model structure.

```python
from tmdl_parser import ModelAnalyzer

analysis = ModelAnalyzer.analyze_model(parsed_model)
```

**Returns:** Analysis dict with:
- `model_name`: Model name
- `table_count`: Number of tables
- `relationship_count`: Number of relationships
- `total_measures`: Total measure count
- `insights`: List of insights (strings)
- `tables_summary`: Summary of each table

**Example:**
```python
analysis = ModelAnalyzer.analyze_model(model)
print("Insights:")
for insight in analysis['insights']:
    print(f"  {insight}")

print("\nTables:")
for table in analysis['tables_summary']:
    print(f"  - {table['name']} ({table['column_count']} columns, {table['measure_count']} measures)")
```

---

### 5. DependencyMapper

Build and analyze dependency graphs.

#### Constructor
```python
from dependency_mapper import DependencyMapper

mapper = DependencyMapper()
```

#### Methods

##### add_semantic_model(model_id, model_name, workspace_id, workspace_name)
Add semantic model node.

```python
mapper.add_semantic_model(
    "model-001",
    "Sales Model",
    "ws-analytics",
    "Analytics Workspace"
)
```

---

##### add_report(report_id, report_name, workspace_id, workspace_name)
Add report node.

```python
mapper.add_report(
    "report-001",
    "Sales Dashboard",
    "ws-analytics",
    "Analytics Workspace"
)
```

---

##### add_data_source(source_id, source_name, workspace_id, workspace_name)
Add data source node.

```python
mapper.add_data_source(
    "source-001",
    "SQL Server: SalesDB",
    "ws-analytics",
    "Analytics Workspace"
)
```

---

##### link_report_to_model(report_id, model_id)
Create dependency: report consumes model.

```python
mapper.link_report_to_model("report-001", "model-001")
```

---

##### link_model_to_source(model_id, source_id)
Create dependency: model depends on source.

```python
mapper.link_model_to_source("model-001", "source-001")
```

---

##### link_model_to_model(source_model_id, target_model_id, reference_type="cross_ref")
Create dependency: model references another model.

```python
mapper.link_model_to_model("model-002", "model-001", "uses")
```

---

##### generate_dependency_report()
Generate comprehensive dependency analysis.

```python
report = mapper.generate_dependency_report()
```

**Returns:** Dict with:
- `summary`: Overall statistics
- `high_impact_nodes`: High-impact artifacts
- `orphaned_nodes`: Unused artifacts
- `isolated_components`: Disconnected groups

**Example:**
```python
report = mapper.generate_dependency_report()

print(f"Total Nodes: {report['summary']['total_nodes']}")
print(f"Total Dependencies: {report['summary']['total_edges']}")

for node in report['high_impact_nodes']:
    print(f"{node['name']}: {node['impact_radius']} downstream artifacts")

if report['orphaned_nodes']:
    print("Unused artifacts:")
    for node in report['orphaned_nodes']:
        print(f"  - {node['name']}")
```

---

##### export_to_csv(file_path)
Export dependencies as CSV.

```python
mapper.export_to_csv("./dependencies.csv")
```

**Output Format:**
```
source_id,source_name,source_type,target_id,target_name,target_type,relationship_type
model-001,Sales Model,SemanticModel,report-001,Sales Dashboard,Report,consumed_by
source-001,SQL Server: SalesDB,DataSource,model-001,Sales Model,SemanticModel,feeds
```

---

### 6. DependencyGraph

Low-level dependency graph management.

#### Constructor
```python
from dependency_mapper import DependencyGraph

graph = DependencyGraph()
```

#### Methods

##### add_node(node: DependencyNode)
Add node to graph.

```python
from dependency_mapper import DependencyNode

node = DependencyNode(
    id="model-001",
    name="Sales Model",
    node_type="SemanticModel",
    workspace_id="ws-1",
    workspace_name="Analytics"
)
graph.add_node(node)
```

---

##### add_edge(source_id, target_id, relationship_type)
Add directed edge.

```python
graph.add_edge("model-001", "report-001", "consumed_by")
```

---

##### get_consumers(node_id)
Get all nodes that consume this node.

```python
consumers = graph.get_consumers("model-001")
for node in consumers:
    print(f"Consumed by: {node.name}")
```

---

##### get_dependencies(node_id)
Get all nodes that this node depends on.

```python
dependencies = graph.get_dependencies("report-001")
for node in dependencies:
    print(f"Depends on: {node.name}")
```

---

##### calculate_impact_radius(node_id)
Calculate change impact radius.

```python
impact = graph.calculate_impact_radius("model-001")
print(f"Changing this model affects {impact} artifacts")
```

---

##### find_cycles()
Detect circular dependencies.

```python
cycles = graph.find_cycles()
if cycles:
    print("⚠️ Circular dependencies detected:")
    for cycle in cycles:
        print(f"  {' -> '.join(cycle)}")
```

---

##### export_to_json(file_path)
Export graph as JSON.

```python
graph.export_to_json("./graph.json")
```

---

##### export_to_mermaid(file_path)
Export graph as Mermaid diagram.

```python
graph.export_to_mermaid("./lineage.mermaid")
```

**Output:** Mermaid flowchart with colored nodes by type

---

## Data Classes

### TenantConfig
```python
@dataclass
class TenantConfig:
    tenant_id: str
    environment: str = "production"
    include_workspaces: Optional[List[str]] = None
    exclude_workspaces: Optional[List[str]] = None
    parse_dax: bool = True
    parse_power_query: bool = True
    trace_lineage: bool = True
    anonymize_connections: bool = True
```

### WorkspaceInfo
```python
@dataclass
class WorkspaceInfo:
    id: str
    name: str
    capacity_id: Optional[str] = None
    description: Optional[str] = None
    artifact_count: int = 0
```

### SemanticModelInfo
```python
@dataclass
class SemanticModelInfo:
    id: str
    name: str
    workspace_id: str
    workspace_name: str
    created_by: Optional[str] = None
    modified_date: Optional[str] = None
    data_sources: List[Dict[str, str]] = None
    table_count: int = 0
    relationship_count: int = 0
    measure_count: int = 0
```

### ReportInfo
```python
@dataclass
class ReportInfo:
    id: str
    name: str
    workspace_id: str
    workspace_name: str
    semantic_model_id: Optional[str] = None
    semantic_model_name: Optional[str] = None
    created_by: Optional[str] = None
    modified_date: Optional[str] = None
    page_count: int = 0
```

---

## Error Handling

### Common Exceptions

| Exception | When | Handling |
|---|---|---|
| `FileNotFoundError` | File path doesn't exist | Check file path, verify permissions |
| `RequestException` | Fabric API call fails | Check authentication, network connectivity |
| `yaml.YAMLError` | Invalid TMDL syntax | Validate TMDL file format |
| `json.JSONDecodeError` | Invalid BIM JSON | Validate BIM file format |

### Example Error Handling
```python
from requests.exceptions import RequestException

try:
    scanner.run_full_scan()
except RequestException as e:
    print(f"API Error: {e}")
    # Check authentication with: az account show
except FileNotFoundError as e:
    print(f"File Error: {e}")
except Exception as e:
    print(f"Unexpected Error: {e}")
```

---

## Configuration

See `src/config.py` for detailed configuration options.

### Load Configuration from YAML
```python
from config import TenantConfig

config = TenantConfig.from_yaml("./scanner-config.yaml")
scanner = FabricTenantScanner(config)
```

---

## Logging

The scanner uses Python's standard logging module.

### Configure Logging Level
```python
import logging

# Set to DEBUG for verbose output
logging.basicConfig(level=logging.DEBUG)

# Or configure specific logger
logger = logging.getLogger("fabric_scanner")
logger.setLevel(logging.DEBUG)
```

### Log Output
```
INFO - FabricTenantScanner initialized for tenant: 12345678-...
INFO - Discovering workspaces...
INFO - ✓ Discovered 5 workspaces
INFO - Enumerating semantic models in workspace ws-001...
INFO - ✓ Found 12 semantic models in workspace
```

---

## Performance Notes

- **API Rate Limits:** Respect Fabric API rate limits (typically 300 requests/minute)
- **Large Tenants:** For tenants with >100 workspaces, consider filtering with `include_workspaces`
- **TMDL Parsing:** Large models (>1000 tables) may take several seconds to parse
- **Dependency Analysis:** Graph analysis is O(n) for impact radius; use for targeted nodes

---

## Next Steps

See examples in `examples/` directory for complete working code samples.
