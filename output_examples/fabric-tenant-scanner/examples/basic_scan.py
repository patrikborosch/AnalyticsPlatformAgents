"""
Example: Basic Tenant Scan
"""

from scanner import FabricTenantScanner, TenantConfig

# Configuration
config = TenantConfig(
    tenant_id="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    environment="production",
    exclude_workspaces=["Archive", "Sandbox"]
)

# Initialize scanner
scanner = FabricTenantScanner(config)

# Run full scan
print("\n🚀 Starting Fabric Tenant Scan...\n")
summary = scanner.run_full_scan()

print("\n📊 Scan Summary:")
print(f"  - Workspaces: {summary['workspace_count']}")
print(f"  - Semantic Models: {summary['semantic_model_count']}")
print(f"  - Reports: {summary['report_count']}")
print(f"  - Dependencies: {summary['dependency_count']}")

# Export results
print("\n💾 Exporting results...")
scanner.export_to_json("./output/tenant-inventory.json")
scanner.export_to_markdown("./output/tenant-report.md")

print("\n✅ Scan complete!")
