"""
Fabric Tenant Scanner - Core Module
Orchestrates tenant discovery and artifact analysis
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import json
import logging
from pathlib import Path
from enum import Enum

from azure.identity import DefaultAzureCredential
import requests


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScanStatus(Enum):
    """Scan execution status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TenantConfig:
    """Tenant configuration"""
    tenant_id: str
    environment: str = "production"
    include_workspaces: Optional[List[str]] = None
    exclude_workspaces: Optional[List[str]] = None
    parse_dax: bool = True
    parse_power_query: bool = True
    trace_lineage: bool = True
    anonymize_connections: bool = True


@dataclass
class WorkspaceInfo:
    """Workspace metadata"""
    id: str
    name: str
    capacity_id: Optional[str] = None
    description: Optional[str] = None
    artifact_count: int = 0


@dataclass
class SemanticModelInfo:
    """Semantic Model metadata"""
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
    
    def __post_init__(self):
        if self.data_sources is None:
            self.data_sources = []


@dataclass
class ReportInfo:
    """Report metadata"""
    id: str
    name: str
    workspace_id: str
    workspace_name: str
    semantic_model_id: Optional[str] = None
    semantic_model_name: Optional[str] = None
    created_by: Optional[str] = None
    modified_date: Optional[str] = None
    page_count: int = 0


@dataclass
class Dependency:
    """Artifact dependency"""
    source_id: str
    source_name: str
    source_type: str  # SemanticModel, DataSource, Report, etc.
    target_id: str
    target_name: str
    target_type: str
    dependency_type: str  # consumer, feeder, cross_ref
    description: Optional[str] = None


class FabricTenantScanner:
    """
    Main Fabric Tenant Scanner
    
    Orchestrates:
    - Tenant discovery (workspaces, items)
    - Artifact enumeration (semantic models, reports, data sources)
    - Metadata extraction (TMDL, DAX, Power Query)
    - Dependency mapping
    - Output generation
    """
    
    def __init__(self, config: TenantConfig):
        """
        Initialize scanner with configuration
        
        Args:
            config: TenantConfig with tenant_id and discovery parameters
        """
        self.config = config
        self.credential = DefaultAzureCredential()
        self.token = None
        self.api_version = "2023-11-01"
        self.base_url = "https://api.fabric.microsoft.com/v1"
        
        self.workspaces: List[WorkspaceInfo] = []
        self.semantic_models: List[SemanticModelInfo] = []
        self.reports: List[ReportInfo] = []
        self.dependencies: List[Dependency] = []
        
        self.scan_status = ScanStatus.PENDING
        self.scan_start_time: Optional[datetime] = None
        self.scan_end_time: Optional[datetime] = None
        
        logger.info(f"FabricTenantScanner initialized for tenant: {config.tenant_id}")
    
    def _get_token(self) -> str:
        """Get Azure token for Fabric API"""
        if not self.token:
            token_obj = self.credential.get_token("https://api.fabric.microsoft.com/.default")
            self.token = token_obj.token
        return self.token
    
    def _api_call(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """
        Make REST API call to Fabric API
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (relative to base_url)
            **kwargs: Additional request parameters
            
        Returns:
            Response JSON
        """
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API call failed: {e}")
            raise
    
    def discover_workspaces(self) -> List[WorkspaceInfo]:
        """
        Discover all workspaces in tenant
        
        Returns:
            List of WorkspaceInfo objects
        """
        logger.info("Discovering workspaces...")
        
        try:
            response = self._api_call("GET", "/workspaces")
            items = response.get("value", [])
            
            self.workspaces = []
            for item in items:
                workspace_name = item.get("displayName", "Unknown")
                
                # Apply filters
                if self.config.include_workspaces and workspace_name not in self.config.include_workspaces:
                    continue
                if self.config.exclude_workspaces and workspace_name in self.config.exclude_workspaces:
                    continue
                
                workspace = WorkspaceInfo(
                    id=item.get("id"),
                    name=workspace_name,
                    capacity_id=item.get("capacityId"),
                    description=item.get("description")
                )
                self.workspaces.append(workspace)
            
            logger.info(f"✓ Discovered {len(self.workspaces)} workspaces")
            return self.workspaces
            
        except Exception as e:
            logger.error(f"Failed to discover workspaces: {e}")
            raise
    
    def enumerate_semantic_models(self, workspace_id: str) -> List[SemanticModelInfo]:
        """
        Enumerate all semantic models in workspace
        
        Args:
            workspace_id: Workspace ID
            
        Returns:
            List of SemanticModelInfo objects
        """
        logger.info(f"Enumerating semantic models in workspace {workspace_id}...")
        
        try:
            response = self._api_call("GET", f"/workspaces/{workspace_id}/items")
            items = response.get("value", [])
            
            workspace = next((w for w in self.workspaces if w.id == workspace_id), None)
            workspace_name = workspace.name if workspace else "Unknown"
            
            models = []
            for item in items:
                # Filter for semantic models only
                if item.get("type") != "SemanticModel":
                    continue
                
                model = SemanticModelInfo(
                    id=item.get("id"),
                    name=item.get("displayName", "Unknown"),
                    workspace_id=workspace_id,
                    workspace_name=workspace_name,
                    created_by=item.get("createdBy", {}).get("userPrincipalName"),
                    modified_date=item.get("lastModifiedTime")
                )
                models.append(model)
            
            self.semantic_models.extend(models)
            logger.info(f"✓ Found {len(models)} semantic models in workspace")
            return models
            
        except Exception as e:
            logger.error(f"Failed to enumerate semantic models: {e}")
            raise
    
    def enumerate_reports(self, workspace_id: str) -> List[ReportInfo]:
        """
        Enumerate all reports in workspace
        
        Args:
            workspace_id: Workspace ID
            
        Returns:
            List of ReportInfo objects
        """
        logger.info(f"Enumerating reports in workspace {workspace_id}...")
        
        try:
            response = self._api_call("GET", f"/workspaces/{workspace_id}/items")
            items = response.get("value", [])
            
            workspace = next((w for w in self.workspaces if w.id == workspace_id), None)
            workspace_name = workspace.name if workspace else "Unknown"
            
            reports = []
            for item in items:
                # Filter for reports only
                if item.get("type") != "Report":
                    continue
                
                report = ReportInfo(
                    id=item.get("id"),
                    name=item.get("displayName", "Unknown"),
                    workspace_id=workspace_id,
                    workspace_name=workspace_name,
                    created_by=item.get("createdBy", {}).get("userPrincipalName"),
                    modified_date=item.get("lastModifiedTime")
                )
                reports.append(report)
            
            self.reports.extend(reports)
            logger.info(f"✓ Found {len(reports)} reports in workspace")
            return reports
            
        except Exception as e:
            logger.error(f"Failed to enumerate reports: {e}")
            raise
    
    def run_full_scan(self) -> Dict[str, Any]:
        """
        Run complete tenant scan
        
        Returns:
            Scan results summary
        """
        self.scan_status = ScanStatus.IN_PROGRESS
        self.scan_start_time = datetime.now()
        
        try:
            # Step 1: Discover workspaces
            self.discover_workspaces()
            
            # Step 2: Enumerate items per workspace
            for workspace in self.workspaces:
                logger.info(f"\nScanning workspace: {workspace.name}")
                self.enumerate_semantic_models(workspace.id)
                self.enumerate_reports(workspace.id)
            
            # Step 3: Build dependency map (placeholder)
            self._build_basic_dependencies()
            
            self.scan_status = ScanStatus.COMPLETED
            self.scan_end_time = datetime.now()
            
            summary = {
                "status": self.scan_status.value,
                "scan_start": self.scan_start_time.isoformat(),
                "scan_end": self.scan_end_time.isoformat(),
                "workspace_count": len(self.workspaces),
                "semantic_model_count": len(self.semantic_models),
                "report_count": len(self.reports),
                "dependency_count": len(self.dependencies)
            }
            
            logger.info(f"\n✓ Scan completed: {summary}")
            return summary
            
        except Exception as e:
            self.scan_status = ScanStatus.FAILED
            logger.error(f"Scan failed: {e}")
            raise
    
    def _build_basic_dependencies(self):
        """Build basic dependency map (placeholder for full implementation)"""
        logger.info("Building dependency map...")
        
        # For now, link reports to semantic models
        # In full implementation, would parse TMDL and Power Query
        for report in self.reports:
            # Placeholder: assume first model in workspace
            for model in self.semantic_models:
                if model.workspace_id == report.workspace_id:
                    dep = Dependency(
                        source_id=model.id,
                        source_name=model.name,
                        source_type="SemanticModel",
                        target_id=report.id,
                        target_name=report.name,
                        target_type="Report",
                        dependency_type="consumer"
                    )
                    self.dependencies.append(dep)
                    break
    
    def export_to_json(self, output_path: str):
        """Export inventory to JSON"""
        output = {
            "tenant_id": self.config.tenant_id,
            "scan_timestamp": self.scan_start_time.isoformat() if self.scan_start_time else None,
            "scan_status": self.scan_status.value,
            "workspaces": [asdict(w) for w in self.workspaces],
            "semantic_models": [asdict(m) for m in self.semantic_models],
            "reports": [asdict(r) for r in self.reports],
            "dependencies": [asdict(d) for d in self.dependencies]
        }
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2, default=str)
        
        logger.info(f"✓ Exported JSON to {output_path}")
    
    def export_to_markdown(self, output_path: str):
        """Export inventory to Markdown report"""
        lines = [
            "# Fabric Tenant Scan Report\n",
            f"**Scan Timestamp:** {self.scan_start_time.isoformat() if self.scan_start_time else 'N/A'}\n",
            f"**Status:** {self.scan_status.value}\n",
            f"**Tenant ID:** {self.config.tenant_id}\n",
            "\n## Summary\n",
            f"- Workspaces: {len(self.workspaces)}\n",
            f"- Semantic Models: {len(self.semantic_models)}\n",
            f"- Reports: {len(self.reports)}\n",
            f"- Dependencies: {len(self.dependencies)}\n",
            "\n## Workspaces\n",
        ]
        
        for ws in self.workspaces:
            lines.append(f"\n### {ws.name}\n")
            lines.append(f"- **ID:** {ws.id}\n")
            lines.append(f"- **Capacity:** {ws.capacity_id or 'N/A'}\n")
            
            ws_models = [m for m in self.semantic_models if m.workspace_id == ws.id]
            ws_reports = [r for r in self.reports if r.workspace_id == ws.id]
            
            lines.append(f"- **Semantic Models:** {len(ws_models)}\n")
            for model in ws_models:
                lines.append(f"  - {model.name} (ID: {model.id})\n")
            
            lines.append(f"- **Reports:** {len(ws_reports)}\n")
            for report in ws_reports:
                lines.append(f"  - {report.name} (ID: {report.id})\n")
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.writelines(lines)
        
        logger.info(f"✓ Exported Markdown to {output_path}")


def main():
    """CLI entry point (example)"""
    config = TenantConfig(
        tenant_id="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        environment="production",
        exclude_workspaces=["Archive"]
    )
    
    scanner = FabricTenantScanner(config)
    scanner.run_full_scan()
    
    scanner.export_to_json("./output/tenant-inventory.json")
    scanner.export_to_markdown("./output/tenant-report.md")


if __name__ == "__main__":
    main()
