import sys
import os
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from scanner import FabricTenantScanner, TenantConfig

def main():
    print("\n" + "="*80)
    print("🚀 FABRIC TENANT SCAN")
    print("="*80 + "\n")
    
    # Configuration
    config = TenantConfig(
        tenant_id="00000000-0000-4000-8000-000000000040",
        environment="production",
        exclude_workspaces=["Archive", "Sandbox"]
    )
    
    # Initialize scanner
    try:
        scanner = FabricTenantScanner(config)
        print("✅ Scanner initialized\n")
    except Exception as e:
        print(f"❌ Failed to initialize scanner: {e}")
        print("\n💡 Make sure you're authenticated with: az login")
        return
    
    # Run full scan
    print("📊 Starting discovery...\n")
    try:
        summary = scanner.run_full_scan()
        
        print("\n" + "="*80)
        print("📈 SCAN RESULTS")
        print("="*80)
        print(f"\n✓ Scan Status:        {summary['status']}")
        print(f"✓ Workspaces Found:   {summary['workspace_count']}")
        print(f"✓ Semantic Models:    {summary['semantic_model_count']}")
        print(f"✓ Reports:            {summary['report_count']}")
        print(f"✓ Dependencies:       {summary['dependency_count']}")
        
        # Export results
        print("\n💾 Exporting results...\n")
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        
        scanner.export_to_json(str(output_dir / "tenant-inventory.json"))
        scanner.export_to_markdown(str(output_dir / "tenant-report.md"))
        
        print("\n✅ Scan Complete!\n")
        print("📂 Output Files:")
        print(f"   • {output_dir}/tenant-inventory.json")
        print(f"   • {output_dir}/tenant-report.md")
        
        # Show summary
        if scanner.workspaces:
            print("\n📋 Workspaces Discovered:")
            for ws in scanner.workspaces[:5]:
                model_count = len([m for m in scanner.semantic_models if m.workspace_id == ws.id])
                report_count = len([r for r in scanner.reports if r.workspace_id == ws.id])
                print(f"   • {ws.name}: {model_count} models, {report_count} reports")
            if len(scanner.workspaces) > 5:
                print(f"   ... and {len(scanner.workspaces) - 5} more workspaces")
        
        print("\n" + "="*80 + "\n")
        
    except Exception as e:
        print(f"\n❌ Scan failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
