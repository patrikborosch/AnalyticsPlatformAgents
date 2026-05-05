"""
Example: TMDL/BIM Parsing and Analysis
"""

from tmdl_parser import TmdlParser, BimParser, ModelAnalyzer

# Example 1: Parse a TMDL file
print("📄 Parsing TMDL file...\n")
tmdl_model = TmdlParser.parse_tmdl_file("./examples/sample_model.tmdl")

# Example 2: Parse a BIM file (JSON)
print("📄 Parsing BIM file...\n")
bim_model = BimParser.parse_bim_file("./examples/sample_model.bim")

# Example 3: Analyze the model
print("🔍 Analyzing model structure...\n")
analysis = ModelAnalyzer.analyze_model(bim_model)

print("Model Analysis:")
print(f"  - Name: {analysis['model_name']}")
print(f"  - Tables: {analysis['table_count']}")
print(f"  - Relationships: {analysis['relationship_count']}")
print(f"  - Data Sources: {analysis['data_source_count']}")
print(f"  - Total Measures: {analysis['total_measures']}")
print(f"  - Total Columns: {analysis['total_columns']}")

print("\n📋 Tables Summary:")
for table in analysis['tables_summary']:
    print(f"  - {table['name']}")
    print(f"    • Type: {table['source_type']}")
    print(f"    • Columns: {table['column_count']}")
    print(f"    • Measures: {table['measure_count']}")
    print(f"    • Hidden: {table['hidden_columns']}")

print("\n💡 Insights:")
for insight in analysis['insights']:
    print(f"  {insight}")

print("\n✅ Analysis complete!")
