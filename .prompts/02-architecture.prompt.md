---
description: Generate a complete architecture handoff document for the Modeler Agent
---

# Generate Handoff Document

Compile all architecture decisions from this session into a structured handoff for the Modeler Agent.

## Instructions

Produce a single document containing ALL of the following sections.
Every section must be complete — do not leave placeholders.

1. **Architecture Decision Records (ADRs):** All decisions made, with context and trade-offs
2. **Object Catalogue:** Every table/entity with layer, type, grain, load pattern, SCD type, key columns
3. **Column Specifications:** Per object — column, logical data type, nullable, source mapping, transformation, business rule
4. **Pipeline Specifications:** Per pipeline — schedule, steps, source→target, load pattern, dependencies, error handling
5. **Transformation Rule Library:** All reusable transformation rules with code/expressions
6. **Quality Rules:** Per target object — rule type, expression, severity
7. **Mermaid Diagram Collection:** All diagrams labeled and cross-referenced
8. **Modeler Instructions:** Technology stack, naming conventions, physical optimization hints, security requirements, refresh schedule

Format as a clean Markdown document ready for handoff.
