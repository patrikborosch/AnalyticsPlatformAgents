"""
Example: Dependency Mapping and Analysis
"""

from dependency_mapper import DependencyMapper

# Initialize mapper
mapper = DependencyMapper()

# Add nodes (from a tenant scan)
print("📍 Adding artifacts to dependency graph...\n")

# Semantic Models
mapper.add_semantic_model("model-001", "Sales Model", "ws-analytics", "Analytics Workspace")
mapper.add_semantic_model("model-002", "Customers Model", "ws-analytics", "Analytics Workspace")
mapper.add_semantic_model("model-003", "Finance Model", "ws-finance", "Finance Workspace")

# Reports
mapper.add_report("report-001", "Sales Dashboard", "ws-analytics", "Analytics Workspace")
mapper.add_report("report-002", "Customer Insights", "ws-analytics", "Analytics Workspace")
mapper.add_report("report-003", "Budget vs Actual", "ws-finance", "Finance Workspace")

# Data Sources
mapper.add_data_source("source-001", "SQL Server: SalesDB", "ws-analytics", "Analytics Workspace")
mapper.add_data_source("source-002", "SQL Server: FinanceDB", "ws-finance", "Finance Workspace")
mapper.add_data_source("source-003", "Excel: Budget", "ws-finance", "Finance Workspace")

# Build relationships
print("🔗 Building dependency relationships...\n")

# Model to Source
mapper.link_model_to_source("model-001", "source-001")  # Sales Model uses SalesDB
mapper.link_model_to_source("model-003", "source-002")  # Finance Model uses FinanceDB
mapper.link_model_to_source("model-003", "source-003")  # Finance Model uses Budget Excel

# Report to Model
mapper.link_report_to_model("report-001", "model-001")  # Sales Dashboard uses Sales Model
mapper.link_report_to_model("report-002", "model-002")  # Customer Insights uses Customers Model
mapper.link_report_to_model("report-003", "model-003")  # Budget vs Actual uses Finance Model

# Model to Model (cross-model references)
mapper.link_model_to_model("model-002", "model-001", "uses")  # Customers Model references Sales Model

# Generate report
print("📊 Generating dependency analysis...\n")
report = mapper.generate_dependency_report()

print("Dependency Report Summary:")
print(f"  - Total Nodes: {report['summary']['total_nodes']}")
print(f"  - Total Dependencies: {report['summary']['total_edges']}")
print(f"  - Node Types: {report['summary']['node_types']}")
print(f"  - Circular Dependencies: {report['summary']['cycles_detected']}")

print("\n🎯 High-Impact Nodes (change radius > 1):")
for node in report['high_impact_nodes']:
    print(f"  - {node['name']} ({node['type']})")
    print(f"    • Impact Radius: {node['impact_radius']} artifacts")
    print(f"    • Direct Consumers: {node['direct_consumers']}")

print("\n🏚️ Orphaned Nodes (no connections):")
if report['orphaned_nodes']:
    for node in report['orphaned_nodes']:
        print(f"  - {node['name']} ({node['type']}) in {node['workspace']}")
else:
    print("  None found ✓")

print("\n📈 Isolated Components:")
if report['isolated_components']:
    for i, component in enumerate(report['isolated_components'], 1):
        print(f"  Component {i}: {len(component)} nodes")
else:
    print("  All artifacts are connected ✓")

# Export to multiple formats
print("\n💾 Exporting dependency graphs...\n")
mapper.graph.export_to_json("./output/dependencies.json")
mapper.graph.export_to_mermaid("./output/dependencies.mermaid")
mapper.export_to_csv("./output/dependencies.csv")

print("✅ Dependency analysis complete!")
