"""
Configuration for Fabric Tenant Scanner
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import yaml
import os


@dataclass
class TenantConfig:
    """Main configuration class"""
    
    # Tenant settings
    tenant_id: str
    environment: str = "production"
    
    # Discovery settings
    include_workspaces: Optional[List[str]] = None
    exclude_workspaces: Optional[List[str]] = field(default_factory=list)
    
    # Analysis settings
    parse_dax: bool = True
    parse_power_query: bool = True
    trace_lineage: bool = True
    
    # Output settings
    output_formats: List[str] = field(default_factory=lambda: ["json", "markdown", "mermaid"])
    output_directory: str = "./output"
    include_metadata: bool = True
    
    # Security settings
    anonymize_connections: bool = True
    exclude_credentials: bool = True
    
    @classmethod
    def from_yaml(cls, yaml_file: str) -> "TenantConfig":
        """Load configuration from YAML file"""
        if not os.path.exists(yaml_file):
            raise FileNotFoundError(f"Configuration file not found: {yaml_file}")
        
        with open(yaml_file, 'r') as f:
            data = yaml.safe_load(f)
        
        # Flatten nested structure
        config_dict = {
            'tenant_id': data.get('tenant', {}).get('tenant_id'),
            'environment': data.get('tenant', {}).get('environment', 'production'),
            'include_workspaces': data.get('discovery', {}).get('include_workspaces'),
            'exclude_workspaces': data.get('discovery', {}).get('exclude_workspaces', []),
            'parse_dax': data.get('analysis', {}).get('parse_dax', True),
            'parse_power_query': data.get('analysis', {}).get('parse_power_query', True),
            'trace_lineage': data.get('analysis', {}).get('trace_lineage', True),
            'output_formats': data.get('output', {}).get('formats', ['json', 'markdown', 'mermaid']),
            'output_directory': data.get('output', {}).get('directory', './output'),
            'include_metadata': data.get('output', {}).get('include_metadata', True),
            'anonymize_connections': data.get('security', {}).get('anonymize_connections', True),
            'exclude_credentials': data.get('security', {}).get('exclude_credentials', True),
        }
        
        return cls(**config_dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'tenant': {
                'tenant_id': self.tenant_id,
                'environment': self.environment
            },
            'discovery': {
                'include_workspaces': self.include_workspaces,
                'exclude_workspaces': self.exclude_workspaces
            },
            'analysis': {
                'parse_dax': self.parse_dax,
                'parse_power_query': self.parse_power_query,
                'trace_lineage': self.trace_lineage
            },
            'output': {
                'formats': self.output_formats,
                'directory': self.output_directory,
                'include_metadata': self.include_metadata
            },
            'security': {
                'anonymize_connections': self.anonymize_connections,
                'exclude_credentials': self.exclude_credentials
            }
        }


def create_default_config() -> str:
    """Create a default configuration YAML file"""
    default_config = """
tenant:
  tenant_id: "REPLACE_WITH_YOUR_TENANT_ID"
  environment: "production"  # or "test", "dev"

discovery:
  include_workspaces: []  # Leave empty = all; specify names to filter
  exclude_workspaces: 
    - "Archive"
    - "Sandbox"
  
analysis:
  parse_dax: true
  parse_power_query: true
  trace_lineage: true
  
output:
  formats: 
    - "json"
    - "markdown"
    - "mermaid"
  directory: "./output"
  include_metadata: true

security:
  anonymize_connections: true
  exclude_credentials: true
"""
    return default_config.strip()
