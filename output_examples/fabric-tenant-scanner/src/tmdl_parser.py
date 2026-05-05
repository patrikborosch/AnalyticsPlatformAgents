"""
TMDL / BIM Parser
Extracts semantic model metadata from TMDL or BIM (JSON) files
"""

import json
import yaml
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class Column:
    """Column definition"""
    name: str
    data_type: str  # int64, string, datetime, etc.
    is_hidden: bool = False
    description: Optional[str] = None
    is_key: bool = False
    sort_by_column: Optional[str] = None


@dataclass
class Measure:
    """Measure definition"""
    name: str
    dax_expression: str
    description: Optional[str] = None
    format_string: Optional[str] = None
    is_hidden: bool = False


@dataclass
class Table:
    """Table definition"""
    name: str
    source_type: str  # DirectQuery, Import, Calculated
    columns: List[Column] = None
    measures: List[Measure] = None
    description: Optional[str] = None
    refresh_policy: Optional[Dict[str, Any]] = None
    data_source: Optional[str] = None
    source_query: Optional[str] = None
    
    def __post_init__(self):
        if self.columns is None:
            self.columns = []
        if self.measures is None:
            self.measures = []


@dataclass
class Relationship:
    """Table relationship"""
    name: str
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    cardinality: str  # One, Many
    cross_filter_direction: str  # OneDirection, BothDirections


@dataclass
class DataSource:
    """Data source definition"""
    name: str
    source_type: str  # SQL, Excel, Web, etc.
    connection_string: Optional[str] = None
    provider: Optional[str] = None
    anonymous_masked: bool = False


class TmdlParser:
    """Parse TMDL (Tabular Model Definition Language) files"""
    
    @staticmethod
    def parse_tmdl_file(file_path: str) -> Dict[str, Any]:
        """
        Parse TMDL files (YAML-based)
        
        Args:
            file_path: Path to TMDL file
            
        Returns:
            Parsed model structure
        """
        logger.info(f"Parsing TMDL file: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tmdl_data = yaml.safe_load(f)
            
            return TmdlParser._parse_tmdl_structure(tmdl_data)
            
        except Exception as e:
            logger.error(f"Failed to parse TMDL file: {e}")
            raise
    
    @staticmethod
    def _parse_tmdl_structure(tmdl_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse TMDL structure"""
        model = {
            "name": tmdl_data.get("name", "Unknown"),
            "tables": [],
            "relationships": [],
            "data_sources": [],
            "measures_total": 0,
            "columns_total": 0
        }
        
        # Parse tables
        if "tables" in tmdl_data:
            for table_def in tmdl_data["tables"]:
                table = TmdlParser._parse_table(table_def)
                model["tables"].append(table)
                model["columns_total"] += len(table.get("columns", []))
                model["measures_total"] += len(table.get("measures", []))
        
        # Parse relationships
        if "relationships" in tmdl_data:
            for rel_def in tmdl_data["relationships"]:
                rel = TmdlParser._parse_relationship(rel_def)
                model["relationships"].append(rel)
        
        # Parse data sources
        if "dataSources" in tmdl_data:
            for ds_def in tmdl_data["dataSources"]:
                ds = TmdlParser._parse_data_source(ds_def)
                model["data_sources"].append(ds)
        
        return model
    
    @staticmethod
    def _parse_table(table_def: Dict[str, Any]) -> Dict[str, Any]:
        """Parse table definition"""
        table = {
            "name": table_def.get("name", "Unknown"),
            "description": table_def.get("description"),
            "source_type": table_def.get("sourceType", "Import"),
            "columns": [],
            "measures": [],
            "calculated_table": bool(table_def.get("querySource"))
        }
        
        # Parse columns
        if "columns" in table_def:
            for col_def in table_def["columns"]:
                col = TmdlParser._parse_column(col_def)
                table["columns"].append(col)
        
        # Parse measures
        if "measures" in table_def:
            for meas_def in table_def["measures"]:
                meas = TmdlParser._parse_measure(meas_def)
                table["measures"].append(meas)
        
        return table
    
    @staticmethod
    def _parse_column(col_def: Dict[str, Any]) -> Dict[str, Any]:
        """Parse column definition"""
        return {
            "name": col_def.get("name", "Unknown"),
            "data_type": col_def.get("dataType", "string"),
            "is_hidden": col_def.get("isHidden", False),
            "description": col_def.get("description"),
            "is_key": col_def.get("isKey", False),
            "sort_by_column": col_def.get("sortByColumn")
        }
    
    @staticmethod
    def _parse_measure(meas_def: Dict[str, Any]) -> Dict[str, Any]:
        """Parse measure definition"""
        return {
            "name": meas_def.get("name", "Unknown"),
            "description": meas_def.get("description"),
            "expression": meas_def.get("expression", "")[:200] + "...",  # Truncate for preview
            "format_string": meas_def.get("formatString"),
            "is_hidden": meas_def.get("isHidden", False)
        }
    
    @staticmethod
    def _parse_relationship(rel_def: Dict[str, Any]) -> Dict[str, Any]:
        """Parse relationship definition"""
        return {
            "name": rel_def.get("name", "Unknown"),
            "from_table": rel_def.get("fromTable"),
            "from_column": rel_def.get("fromColumn"),
            "to_table": rel_def.get("toTable"),
            "to_column": rel_def.get("toColumn"),
            "cardinality": rel_def.get("cardinality", "One"),
            "cross_filter_direction": rel_def.get("crossFilterDirection", "OneDirection")
        }
    
    @staticmethod
    def _parse_data_source(ds_def: Dict[str, Any]) -> Dict[str, Any]:
        """Parse data source definition"""
        return {
            "name": ds_def.get("name", "Unknown"),
            "type": ds_def.get("type", "Unknown"),
            "connection_details": ds_def.get("connectionDetails", {})
        }


class BimParser:
    """Parse BIM (JSON-based model file)"""
    
    @staticmethod
    def parse_bim_file(file_path: str) -> Dict[str, Any]:
        """
        Parse BIM files (JSON format)
        
        Args:
            file_path: Path to BIM file
            
        Returns:
            Parsed model structure
        """
        logger.info(f"Parsing BIM file: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                bim_data = json.load(f)
            
            return BimParser._parse_bim_structure(bim_data)
            
        except Exception as e:
            logger.error(f"Failed to parse BIM file: {e}")
            raise
    
    @staticmethod
    def _parse_bim_structure(bim_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse BIM structure"""
        model = bim_data.get("model", {})
        
        parsed = {
            "name": model.get("name", "Unknown"),
            "compatibility_level": model.get("compatibilityLevel"),
            "tables": [],
            "relationships": [],
            "data_sources": [],
            "measures_total": 0,
            "columns_total": 0
        }
        
        # Parse tables
        if "tables" in model:
            for table_def in model["tables"]:
                table = BimParser._parse_table_bim(table_def)
                parsed["tables"].append(table)
                parsed["columns_total"] += len(table.get("columns", []))
                parsed["measures_total"] += len(table.get("measures", []))
        
        # Parse relationships
        if "relationships" in model:
            for rel_def in model["relationships"]:
                rel = BimParser._parse_relationship_bim(rel_def)
                parsed["relationships"].append(rel)
        
        # Parse data sources
        if "dataSources" in model:
            for ds_def in model["dataSources"]:
                ds = BimParser._parse_data_source_bim(ds_def)
                parsed["data_sources"].append(ds)
        
        return parsed
    
    @staticmethod
    def _parse_table_bim(table_def: Dict[str, Any]) -> Dict[str, Any]:
        """Parse table from BIM"""
        table = {
            "name": table_def.get("name", "Unknown"),
            "description": table_def.get("description"),
            "source_type": table_def.get("sourceType", "Import"),
            "columns": [],
            "measures": [],
        }
        
        # Parse columns
        if "columns" in table_def:
            for col_def in table_def["columns"]:
                col = {
                    "name": col_def.get("name", "Unknown"),
                    "data_type": col_def.get("dataType", "string"),
                    "is_hidden": col_def.get("isHidden", False),
                    "description": col_def.get("description"),
                    "is_key": col_def.get("isKey", False)
                }
                table["columns"].append(col)
        
        # Parse measures
        if "measures" in table_def:
            for meas_def in table_def["measures"]:
                meas = {
                    "name": meas_def.get("name", "Unknown"),
                    "description": meas_def.get("description"),
                    "format_string": meas_def.get("formatString"),
                    "is_hidden": meas_def.get("isHidden", False)
                }
                table["measures"].append(meas)
        
        return table
    
    @staticmethod
    def _parse_relationship_bim(rel_def: Dict[str, Any]) -> Dict[str, Any]:
        """Parse relationship from BIM"""
        return {
            "name": rel_def.get("name", "Unknown"),
            "from_table": rel_def.get("fromTable"),
            "from_column": rel_def.get("fromColumn"),
            "to_table": rel_def.get("toTable"),
            "to_column": rel_def.get("toColumn"),
            "cardinality": rel_def.get("cardinality", "One"),
            "cross_filter_direction": rel_def.get("crossFilterDirection", "OneDirection")
        }
    
    @staticmethod
    def _parse_data_source_bim(ds_def: Dict[str, Any]) -> Dict[str, Any]:
        """Parse data source from BIM"""
        return {
            "name": ds_def.get("name", "Unknown"),
            "type": ds_def.get("type", "Unknown"),
            "provider": ds_def.get("provider")
        }


class ModelAnalyzer:
    """Analyze parsed model for insights and dependencies"""
    
    @staticmethod
    def analyze_model(parsed_model: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze model structure for insights
        
        Args:
            parsed_model: Parsed model from TMDL or BIM
            
        Returns:
            Analysis results
        """
        analysis = {
            "model_name": parsed_model.get("name"),
            "table_count": len(parsed_model.get("tables", [])),
            "relationship_count": len(parsed_model.get("relationships", [])),
            "data_source_count": len(parsed_model.get("data_sources", [])),
            "total_measures": parsed_model.get("measures_total", 0),
            "total_columns": parsed_model.get("columns_total", 0),
            "insights": ModelAnalyzer._generate_insights(parsed_model),
            "data_sources": parsed_model.get("data_sources", []),
            "tables_summary": []
        }
        
        # Summarize tables
        for table in parsed_model.get("tables", []):
            summary = {
                "name": table.get("name"),
                "source_type": table.get("source_type"),
                "column_count": len(table.get("columns", [])),
                "measure_count": len(table.get("measures", [])),
                "key_columns": [c for c in table.get("columns", []) if c.get("is_key")],
                "hidden_columns": len([c for c in table.get("columns", []) if c.get("is_hidden")])
            }
            analysis["tables_summary"].append(summary)
        
        return analysis
    
    @staticmethod
    def _generate_insights(parsed_model: Dict[str, Any]) -> List[str]:
        """Generate insights about model"""
        insights = []
        
        # Check for orphaned tables (no relationships)
        table_names = {t.get("name") for t in parsed_model.get("tables", [])}
        related_tables = set()
        for rel in parsed_model.get("relationships", []):
            related_tables.add(rel.get("from_table"))
            related_tables.add(rel.get("to_table"))
        
        orphaned = table_names - related_tables
        if orphaned:
            insights.append(f"⚠️ Orphaned tables (no relationships): {', '.join(orphaned)}")
        
        # Check for many-to-many relationships
        many_to_many = [r for r in parsed_model.get("relationships", []) 
                       if r.get("cardinality") == "Many"]
        if many_to_many:
            insights.append(f"⚠️ Many-to-Many relationships detected ({len(many_to_many)})")
        
        # Check for complex models
        if len(parsed_model.get("tables", [])) > 50:
            insights.append(f"ℹ️ Large model with {len(parsed_model.get('tables', []))} tables")
        
        if parsed_model.get("measures_total", 0) > 100:
            insights.append(f"ℹ️ High measure count ({parsed_model.get('measures_total')})")
        
        return insights if insights else ["✓ Model structure appears healthy"]
