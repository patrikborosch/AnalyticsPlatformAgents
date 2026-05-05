"""
Dependency Mapper
Build and analyze artifact dependencies across tenant
"""

from typing import Dict, List, Set, Tuple, Any
from dataclasses import dataclass, asdict
import json
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class DependencyNode:
    """Node in dependency graph"""
    id: str
    name: str
    node_type: str  # SemanticModel, Report, DataSource, Workspace
    workspace_id: str
    workspace_name: str
    metadata: Dict[str, Any] = None


class DependencyGraph:
    """Build and analyze dependency relationships"""
    
    def __init__(self):
        self.nodes: Dict[str, DependencyNode] = {}
        self.edges: List[Tuple[str, str, str]] = []  # (source_id, target_id, relationship_type)
        self.adjacency: Dict[str, List[str]] = defaultdict(list)  # source -> [targets]
        self.reverse_adjacency: Dict[str, List[str]] = defaultdict(list)  # target -> [sources]
    
    def add_node(self, node: DependencyNode):
        """Add node to graph"""
        self.nodes[node.id] = node
        logger.debug(f"Added node: {node.name} ({node.node_type})")
    
    def add_edge(self, source_id: str, target_id: str, relationship_type: str):
        """Add directed edge (source -> target)"""
        if source_id not in self.nodes or target_id not in self.nodes:
            logger.warning(f"Edge references missing nodes: {source_id} -> {target_id}")
            return
        
        self.edges.append((source_id, target_id, relationship_type))
        self.adjacency[source_id].append(target_id)
        self.reverse_adjacency[target_id].append(source_id)
        logger.debug(f"Added edge: {source_id} -> {target_id} ({relationship_type})")
    
    def get_consumers(self, node_id: str) -> List[DependencyNode]:
        """Get all nodes that consume this node"""
        consumer_ids = self.adjacency.get(node_id, [])
        return [self.nodes[cid] for cid in consumer_ids if cid in self.nodes]
    
    def get_dependencies(self, node_id: str) -> List[DependencyNode]:
        """Get all nodes that this node depends on"""
        dep_ids = self.reverse_adjacency.get(node_id, [])
        return [self.nodes[did] for did in dep_ids if did in self.nodes]
    
    def calculate_impact_radius(self, node_id: str) -> int:
        """Calculate how many nodes are affected by changes to this node"""
        visited = set()
        queue = [node_id]
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            queue.extend(self.adjacency.get(current, []))
        
        return len(visited) - 1  # Exclude the source node
    
    def find_cycles(self) -> List[List[str]]:
        """Detect circular dependencies"""
        cycles = []
        visited = set()
        rec_stack = set()
        
        def dfs(node_id: str, path: List[str]):
            visited.add(node_id)
            rec_stack.add(node_id)
            path.append(node_id)
            
            for neighbor in self.adjacency.get(node_id, []):
                if neighbor not in visited:
                    dfs(neighbor, path.copy())
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])
            
            rec_stack.remove(node_id)
        
        for node_id in self.nodes:
            if node_id not in visited:
                dfs(node_id, [])
        
        return cycles
    
    def export_to_json(self, file_path: str):
        """Export graph to JSON"""
        export = {
            "nodes": [
                {
                    "id": node.id,
                    "name": node.name,
                    "type": node.node_type,
                    "workspace": node.workspace_name,
                    "impact_radius": self.calculate_impact_radius(node.id)
                }
                for node in self.nodes.values()
            ],
            "edges": [
                {"source": src, "target": tgt, "type": rel_type}
                for src, tgt, rel_type in self.edges
            ],
            "cycles": self.find_cycles()
        }
        
        with open(file_path, 'w') as f:
            json.dump(export, f, indent=2, default=str)
        
        logger.info(f"✓ Exported graph to {file_path}")
    
    def export_to_mermaid(self, file_path: str):
        """Export graph as Mermaid diagram"""
        lines = [
            "graph LR",
            "    classDef SemanticModel fill:#4A90E2,stroke:#2E5C8A,stroke-width:2px,color:#fff",
            "    classDef Report fill:#50E3C2,stroke:#2D8B7A,stroke-width:2px,color:#fff",
            "    classDef DataSource fill:#F5A623,stroke:#8B6914,stroke-width:2px,color:#fff",
            "    classDef Workspace fill:#9013FE,stroke:#5D0CA3,stroke-width:2px,color:#fff",
            ""
        ]
        
        # Add nodes
        for node in self.nodes.values():
            safe_name = node.name.replace(" ", "_").replace("-", "_")
            class_name = node.node_type
            lines.append(f'    {node.id}["{node.name}"]:::' + class_name)
        
        # Add edges
        for src, tgt, rel_type in self.edges:
            lines.append(f"    {src} -->|{rel_type}| {tgt}")
        
        with open(file_path, 'w') as f:
            f.write("\n".join(lines))
        
        logger.info(f"✓ Exported Mermaid diagram to {file_path}")


class DependencyMapper:
    """Map dependencies across Fabric artifacts"""
    
    def __init__(self):
        self.graph = DependencyGraph()
    
    def add_semantic_model(self, model_id: str, model_name: str, workspace_id: str, workspace_name: str):
        """Add semantic model node"""
        node = DependencyNode(
            id=model_id,
            name=model_name,
            node_type="SemanticModel",
            workspace_id=workspace_id,
            workspace_name=workspace_name
        )
        self.graph.add_node(node)
    
    def add_report(self, report_id: str, report_name: str, workspace_id: str, workspace_name: str):
        """Add report node"""
        node = DependencyNode(
            id=report_id,
            name=report_name,
            node_type="Report",
            workspace_id=workspace_id,
            workspace_name=workspace_name
        )
        self.graph.add_node(node)
    
    def add_data_source(self, source_id: str, source_name: str, workspace_id: str, workspace_name: str):
        """Add data source node"""
        node = DependencyNode(
            id=source_id,
            name=source_name,
            node_type="DataSource",
            workspace_id=workspace_id,
            workspace_name=workspace_name
        )
        self.graph.add_node(node)
    
    def link_report_to_model(self, report_id: str, model_id: str):
        """Report consumes semantic model"""
        self.graph.add_edge(model_id, report_id, "consumed_by")
    
    def link_model_to_source(self, model_id: str, source_id: str):
        """Model depends on data source"""
        self.graph.add_edge(source_id, model_id, "feeds")
    
    def link_model_to_model(self, source_model_id: str, target_model_id: str, reference_type: str = "cross_ref"):
        """Model references another model"""
        self.graph.add_edge(source_model_id, target_model_id, reference_type)
    
    def generate_dependency_report(self) -> Dict[str, Any]:
        """Generate comprehensive dependency report"""
        report = {
            "summary": {
                "total_nodes": len(self.graph.nodes),
                "total_edges": len(self.graph.edges),
                "node_types": self._count_by_type(),
                "cycles_detected": len(self.graph.find_cycles())
            },
            "high_impact_nodes": self._identify_high_impact(),
            "orphaned_nodes": self._identify_orphaned(),
            "isolated_components": self._identify_components()
        }
        return report
    
    def _count_by_type(self) -> Dict[str, int]:
        """Count nodes by type"""
        counts = defaultdict(int)
        for node in self.graph.nodes.values():
            counts[node.node_type] += 1
        return dict(counts)
    
    def _identify_high_impact(self, threshold: int = 5) -> List[Dict[str, Any]]:
        """Identify high-impact nodes (many dependents)"""
        high_impact = []
        for node_id, node in self.graph.nodes.items():
            impact = self.graph.calculate_impact_radius(node_id)
            if impact >= threshold:
                high_impact.append({
                    "node_id": node_id,
                    "name": node.name,
                    "type": node.node_type,
                    "impact_radius": impact,
                    "direct_consumers": len(self.graph.adjacency.get(node_id, []))
                })
        
        return sorted(high_impact, key=lambda x: x["impact_radius"], reverse=True)
    
    def _identify_orphaned(self) -> List[Dict[str, Any]]:
        """Identify nodes with no connections"""
        orphaned = []
        for node_id, node in self.graph.nodes.items():
            if not self.graph.adjacency.get(node_id) and not self.graph.reverse_adjacency.get(node_id):
                orphaned.append({
                    "node_id": node_id,
                    "name": node.name,
                    "type": node.node_type,
                    "workspace": node.workspace_name
                })
        return orphaned
    
    def _identify_components(self) -> List[List[str]]:
        """Identify isolated connected components"""
        visited = set()
        components = []
        
        def dfs(node_id: str, component: List[str]):
            visited.add(node_id)
            component.append(node_id)
            
            # Follow both directions
            for neighbor in self.graph.adjacency.get(node_id, []):
                if neighbor not in visited:
                    dfs(neighbor, component)
            
            for neighbor in self.graph.reverse_adjacency.get(node_id, []):
                if neighbor not in visited:
                    dfs(neighbor, component)
        
        for node_id in self.graph.nodes:
            if node_id not in visited:
                component = []
                dfs(node_id, component)
                if len(component) > 1:
                    components.append(component)
        
        return components
    
    def export_to_csv(self, file_path: str):
        """Export dependencies as CSV"""
        lines = ["source_id,source_name,source_type,target_id,target_name,target_type,relationship_type"]
        
        for src_id, tgt_id, rel_type in self.graph.edges:
            src_node = self.graph.nodes[src_id]
            tgt_node = self.graph.nodes[tgt_id]
            lines.append(
                f'"{src_id}","{src_node.name}","{src_node.node_type}",'
                f'"{tgt_id}","{tgt_node.name}","{tgt_node.node_type}","{rel_type}"'
            )
        
        with open(file_path, 'w') as f:
            f.write("\n".join(lines))
        
        logger.info(f"✓ Exported dependencies to {file_path}")


def main():
    """Example usage"""
    mapper = DependencyMapper()
    
    # Add nodes
    mapper.add_semantic_model("model-1", "Sales Model", "ws-1", "Analytics")
    mapper.add_semantic_model("model-2", "Customers Model", "ws-1", "Analytics")
    mapper.add_report("report-1", "Sales Dashboard", "ws-1", "Analytics")
    mapper.add_data_source("source-1", "SQL Server: SalesDB", "ws-1", "Analytics")
    
    # Add edges
    mapper.link_model_to_source("model-1", "source-1")
    mapper.link_report_to_model("report-1", "model-1")
    mapper.link_model_to_model("model-2", "model-1")
    
    # Generate reports
    report = mapper.generate_dependency_report()
    print(json.dumps(report, indent=2))
    
    # Export
    mapper.graph.export_to_json("./dependencies.json")
    mapper.graph.export_to_mermaid("./dependencies.mermaid")
    mapper.export_to_csv("./dependencies.csv")


if __name__ == "__main__":
    main()
