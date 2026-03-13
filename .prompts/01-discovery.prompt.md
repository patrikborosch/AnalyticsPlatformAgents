---
description: Kick off a new analytics architecture design session
---

# Architecture Discovery

Start a new architecture engagement by gathering requirements.

## Instructions

Walk the user through the following discovery questions, one domain at a time.
Summarise answers as you go and confirm before proceeding.

### Business Context
1. What business questions must this architecture answer?
2. Who are the primary consumers? (Analysts, Data Scientists, Applications, Executives)
3. What are the latency requirements? (Batch daily, hourly, near-real-time, real-time)

### Source Landscape
4. What source systems exist? (List name, type, estimated volume, change frequency)
5. Are there CDC (Change Data Capture) capabilities available, or only full extracts?
6. Are there streaming sources (event hubs, Kafka topics, IoT)?

### Target Architecture Preferences
7. Preferred target schema style? (Star Join / Snowflake / Data Vault / Hybrid)
8. Which entities need history tracking, and what SCD types are appropriate?
9. Are there existing naming conventions or standards?

### Technology Context (for Modeler Agent handoff)
10. What is the target technology stack? (e.g., Fabric, Snowflake, Databricks, Azure Synapse)
11. What ETL/ELT tooling is available or preferred?
12. Any security, compliance, or data residency constraints?

After discovery, compile findings into a **Requirements Summary** with a Mermaid context diagram showing the end-to-end landscape.
