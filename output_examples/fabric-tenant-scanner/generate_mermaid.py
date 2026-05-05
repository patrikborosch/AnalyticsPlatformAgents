import json
import sys
from pathlib import Path
from collections import defaultdict

def generate_mermaid_diagram(inventory_file, output_file):
    """Generate Mermaid dependency diagram from inventory"""
    
    # Load inventory
    with open(inventory_file) as f:
        inventory = json.load(f)
    
    # Group by workspace
    workspace_map = {ws['id']: ws['name'] for ws in inventory['workspaces']}
    model_workspace = {m['id']: m['workspace_id'] for m in inventory['semantic_models']}
    report_workspace = {r['id']: r['workspace_id'] for r in inventory['reports']}
    
    # Build diagram
    lines = [
        "graph TD",
        "    classDef Workspace fill:#9013FE,stroke:#5D0CA3,stroke-width:3px,color:#fff",
        "    classDef SemanticModel fill:#4A90E2,stroke:#2E5C8A,stroke-width:2px,color:#fff",
        "    classDef Report fill:#50E3C2,stroke:#2D8B7A,stroke-width:2px,color:#fff",
        "    classDef DataSource fill:#F5A623,stroke:#8B6914,stroke-width:2px,color:#fff",
        "    classDef Empty fill:#E8E8E8,stroke:#999999,stroke-width:1px,color:#333",
        ""
    ]
    
    # Add workspace nodes
    for workspace in inventory['workspaces']:
        ws_id = f"ws_{workspace['id'].replace('-', '_')[:8]}"
        ws_name = workspace['name']
        model_count = len([m for m in inventory['semantic_models'] if m['workspace_id'] == workspace['id']])
        report_count = len([r for r in inventory['reports'] if r['workspace_id'] == workspace['id']])
        
        # Format node name with model and report counts
        display_name = f"{ws_name}<br/>({model_count} models, {report_count} reports)"
        
        if model_count == 0 and report_count == 0:
            lines.append(f'    {ws_id}["{display_name}"]:::Empty')
        else:
            lines.append(f'    {ws_id}["{display_name}"]:::Workspace')
    
    lines.append("")
    
    # Add semantic model nodes
    for model in inventory['semantic_models']:
        model_id = f"m_{model['id'].replace('-', '_')[:8]}"
        model_name = model['name']
        ws_id = f"ws_{model['workspace_id'].replace('-', '_')[:8]}"
        
        display_name = f"{model_name}<br/><sub>(Model)</sub>"
        lines.append(f'    {model_id}["{display_name}"]:::SemanticModel')
        
        # Link model to workspace
        lines.append(f'    {ws_id} --> {model_id}')
    
    lines.append("")
    
    # Add report nodes
    for report in inventory['reports']:
        report_id = f"r_{report['id'].replace('-', '_')[:8]}"
        report_name = report['name']
        ws_id = f"ws_{report['workspace_id'].replace('-', '_')[:8]}"
        
        display_name = f"{report_name}<br/><sub>(Report)</sub>"
        lines.append(f'    {report_id}["{display_name}"]:::Report')
        
        # Link report to workspace
        lines.append(f'    {ws_id} --> {report_id}')
    
    lines.append("")
    
    # Add dependencies
    for dep in inventory['dependencies']:
        source_id = f"m_{dep['source_id'].replace('-', '_')[:8]}" if 'model' in dep['source_type'].lower() else f"r_{dep['source_id'].replace('-', '_')[:8]}"
        target_id = f"r_{dep['target_id'].replace('-', '_')[:8]}" if 'report' in dep['target_type'].lower() else f"m_{dep['target_id'].replace('-', '_')[:8]}"
        
        relation_type = dep.get('dependency_type', 'uses')
        lines.append(f'    {source_id} -->|{relation_type}| {target_id}')
    
    # Write diagram
    with open(output_file, 'w') as f:
        f.write('\n'.join(lines))
    
    return len(lines)

if __name__ == '__main__':
    inventory_file = r'output\tenant-inventory.json'
    output_file = r'output\dependency-graph.mermaid'
    
    try:
        line_count = generate_mermaid_diagram(inventory_file, output_file)
        print(f"✓ Mermaid diagram generated: {output_file}")
        print(f"  Lines: {line_count}")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
