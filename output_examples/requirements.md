# Requirements Document — Swiss Railway Visitors Analytics Platform

> **Version:** 1.0  
> **Date:** 2026-03-13  
> **Status:** Approved  
> **Author:** Requirements Engineering Agent  
> **Stakeholders:** Head of Business Intelligence (interview lead), Data Product Owner, IT Operations Manager, Finance Controller  

---

## Table of Contents

1. [Business Context](#1-business-context)
2. [Use Case Backlog](#2-use-case-backlog)
3. [Functional Requirements](#3-functional-requirements)
4. [Non-Functional Requirements](#4-non-functional-requirements)
5. [Source System Inventory](#5-source-system-inventory)
6. [Key Business Entities](#6-key-business-entities)
7. [Acceptance Criteria](#7-acceptance-criteria)
8. [Stakeholder Register](#8-stakeholder-register)
9. [Assumptions & Risks](#9-assumptions--risks)
10. [Open Questions](#10-open-questions)
11. [Rework Intake](#11-rework-intake)
12. [Architect Agent Handoff](#12-architect-agent-handoff)
13. [Definition of Done Attestation](#13-definition-of-done-attestation)

---

## 1. Business Context

| Field | Value |
|---|---|
| Project Name | Swiss Railway Visitors Analytics Platform |
| Business Problem | Visitor and revenue data is spread across multiple disconnected systems (ticketing, retail, hospitality). Reporting is manual, inconsistent, and always at least a day behind. Business managers cannot reliably answer basic questions like "How many visitors used station X last month?" or "Which retail categories performed best during peak hours?" |
| Strategic Driver | The railway operator wants to become data-driven in its commercial and operational decisions. A unified analytics platform is the foundation for future AI/ML use cases (demand forecasting, pricing optimisation). |
| Success Criteria | 1. All key visitor and revenue KPIs available in a single dashboard by go-live. 2. Reports are refreshed automatically every night — no manual exports. 3. Users can compare current performance against the same period last year. 4. Any new data source can be connected within 2 weeks without a development project. |
| Key Stakeholders | Head of BI, Data Product Owner, Finance Controller, IT Operations Manager, Station Managers (consumers) |
| Target Go-Live | Q3 2026 (phased: core visitor data first, retail and hospitality in phase 2) |
| In Scope | Visitor counts by station and time, ticket sales and revenue, retail sales at station shops, hospitality revenue (cafés, restaurants), operational metadata (train arrivals/departures as context) |
| Out of Scope | Predictive/ML models (future phase), real-time streaming dashboards (future phase), HR and staffing data, external benchmark data |

---

## 2. Use Case Backlog

```
UC-001: Daily Visitor Summary by Station
As a Station Manager,
I want to see how many visitors passed through my station yesterday, this week, and this month,
So that I can assess whether traffic matches expectations and plan staffing accordingly.
Refresh: Daily by 7am
Priority: High
```

```
UC-002: Visitor Trend Over Time
As a Head of BI,
I want to compare visitor numbers for any station over any time period (day, week, month, year),
So that I can identify seasonal trends and year-on-year growth or decline.
Refresh: Daily
Priority: High
```

```
UC-003: Revenue by Category and Station
As a Finance Controller,
I want to see total revenue broken down by category (tickets, retail, hospitality) per station per month,
So that I can produce monthly financial reports without manual data collection.
Refresh: Daily by 7am
Priority: High
```

```
UC-004: Top and Bottom Performing Retail Products
As a Head of BI,
I want to see which retail product categories and individual products generated the most and least revenue at each station,
So that I can identify assortment optimisation opportunities.
Refresh: Daily
Priority: Medium
```

```
UC-005: Peak Hour Analysis
As a Station Manager,
I want to understand visitor traffic by hour of day for any station and any date range,
So that I can plan staffing and service availability around peak periods.
Refresh: Daily
Priority: Medium
```

```
UC-006: Year-on-Year Comparison Report
As a Finance Controller,
I want to compare this month's revenue and visitor numbers against the same month last year,
So that I can produce accurate variance analysis for the board report.
Refresh: Monthly (automated, triggered by month-end)
Priority: High
```

```
UC-007: Station Data Completeness Monitor
As a Data Product Owner,
I want to see which stations have not reported data today and flag missing feeds,
So that I can proactively fix data gaps before business users notice them.
Refresh: Daily by 6am
Priority: Medium
```

```
UC-008: Hospitality Revenue Drill-Through
As a Head of BI,
I want to drill from a station's total hospitality revenue down to individual outlet performance (café, restaurant, kiosk),
So that I can identify which outlets are driving or dragging performance.
Refresh: Daily
Priority: Low (Phase 2)
```

---

## 3. Functional Requirements

| # | Requirement | Source UC | Priority | Notes |
|---|---|---|---|---|
| FR-001 | The platform must consolidate visitor data from all station ticketing systems into a single reporting area | UC-001, UC-002, UC-005 | High | Multiple ticketing systems with different file formats |
| FR-002 | The platform must consolidate revenue data from ticketing, retail, and hospitality source systems | UC-003, UC-004, UC-008 | High | |
| FR-003 | Reports must be available with data as of the previous business day by 7am | UC-001, UC-003, UC-006 | High | Nightly batch load required |
| FR-004 | The platform must support historical comparisons — users must be able to query data as it was on any past date | UC-002, UC-006 | High | History must be preserved; retroactive changes must not silently overwrite history |
| FR-005 | Adding a new station or new data source must not require a development project — only configuration | All | High | Metadata-driven ingestion is required |
| FR-006 | The platform must detect and flag missing or late-arriving data feeds | UC-007 | Medium | Automated data quality monitoring |
| FR-007 | The platform must support drill-through from summary figures to transaction-level detail | UC-004, UC-008 | Medium | |
| FR-008 | The platform must support both structured database sources and flat-file sources (CSV, Excel) | FR-001, FR-002 | High | Legacy station systems use flat-file exports |
| FR-009 | All data loads must be auditable — who loaded what, when, with what row count and status | All | High | Regulatory and operational requirement |
| FR-010 | The platform must support rollback to the state before a failed or erroneous load | All | High | |

---

## 4. Non-Functional Requirements

| # | Category | Requirement | Acceptance Criteria (ref) |
|---|---|---|---|
| NFR-001 | Freshness | Core visitor and revenue data must be available by 7am every business day | AC-001 |
| NFR-002 | Volume | Approximately 50 station sources, each producing 10,000–500,000 rows per day across all source types | AC-002 |
| NFR-003 | Retention | All raw data must be retained for a minimum of 7 years (regulatory) | AC-003 |
| NFR-004 | Availability | Analytics dashboards must be available during business hours (7am–8pm CET) | AC-004 |
| NFR-005 | Compliance | Station visitor count data may include proximity/device signals — must not store personally identifiable information at the individual level | AC-005 |
| NFR-006 | Security | Data access must be role-based — station managers see only their own station's data; head office sees all | AC-006 |
| NFR-007 | Recovery | In the event of a failed nightly load, the platform must recover without manual intervention or raise an alert | AC-007 |
| NFR-008 | Auditability | Every data change must be traceable to the source load event | AC-008 |

---

## 5. Source System Inventory

| # | System Name | Business Owner | Data Domain | Approx. Volume | Update Frequency | History Available | Access Confirmed | Known Issues |
|---|---|---|---|---|---|---|---|---|
| S-001 | Station Ticketing System (STS) | IT Operations | Visitor counts, ticket sales, revenue by ticket type | ~200K rows/day across 50 stations | Daily file export (CSV) at 01:00 | 3 years in archive | Yes — SFTP drop available | File format differs slightly between older and newer station versions |
| S-002 | Retail POS System (RPOS) | Head of Retail | Retail product sales, revenue by outlet and product | ~50K transactions/day | Daily DB extract | 2 years | Yes — read-only DB connection confirmed | Product catalogue changes frequently; product codes are occasionally recycled |
| S-003 | Hospitality Management System (HMS) | Head of Hospitality | Café/restaurant/kiosk revenue, covers, average spend | ~5K records/day | Daily file export (Excel) | 1 year | Partial — 3 of 12 outlets not yet confirmed | Excel format; some outlets submit manually and may be late |
| S-004 | Train Operations System (TOS) | IT Operations | Train arrivals/departures, platform assignments, delays | ~10K events/day | Daily DB extract | 5 years | Yes — API available | Context/dimension only; not a primary revenue source |
| S-005 | Finance Master Data (FMD) | Finance Controller | Cost centre hierarchy, account codes, station master | ~500 records (mostly static) | Weekly full extract | N/A (reference data) | Yes | Infrequent changes; important for revenue categorisation |

---

## 6. Key Business Entities

| # | Entity Name | Description | Changes Over Time? | Which Attributes Change? | Change Frequency | History Required |
|---|---|---|---|---|---|---|
| E-001 | Station | A railway station — has a name, region, and category (large/medium/small hub) | Yes | Category can be reclassified; name can change (rare) | Very low (a few times per year at most) | Yes — reclassification must not change historical reports |
| E-002 | Product | A retail item sold at station shops — has a name, category, sub-category, and price | Yes | Price changes regularly; category reassignments happen; products are discontinued and recycled | Medium (weekly price changes expected) | Yes — historical revenue reports must reflect the price at time of sale |
| E-003 | Outlet | A specific hospitality or retail point of sale within a station | Yes | Outlet type (café/restaurant/kiosk) can change; outlet can close or open | Low | Yes — outlet history needed for trend analysis |
| E-004 | Ticket Type | A ticket category (day pass, annual pass, group, etc.) — defines pricing and counting rules | Rarely | Name or pricing tier may change; types are occasionally retired | Very low | Yes — for accurate YoY comparison |
| E-005 | Visitor Count | A daily aggregated visitor count per station per time band | No (it's a measurement) | N/A | N/A — append only | N/A — facts are immutable once loaded |
| E-006 | Sales Transaction | An individual point-of-sale transaction (retail or hospitality) | No (it's a measurement) | N/A | N/A | N/A — append only |
| E-007 | Cost Centre | A finance reporting hierarchy node — maps stations to business units | Yes | Hierarchy can be restructured; station-to-cost-centre assignments can change | Low (annual budget cycle) | Yes — financial reporting must reflect structure as it was in the period |

---

## 7. Acceptance Criteria

These criteria define what "working" means for this platform. They are technology-free by design — `@modeler` translates each one into an executable assertion, and `@validator` enforces it. `Must` criteria block go-live; `Should` criteria are tracked as warnings.

| # | Derives From | Acceptance Statement (business-observable) | Measure / Threshold | Evidence the Business Accepts | Severity |
|---|---|---|---|---|---|
| AC-001 | NFR-001 | Yesterday's visitor and revenue data is available to station managers each business morning before the working day starts | Load completed successfully before 07:00 CET on at least 95% of business days, measured monthly | Monthly load punctuality summary reviewed by the Data Product Owner | Must |
| AC-002 | NFR-002 | A peak-volume night completes within the loading window without failure or truncation | 25 million rows processed in a single nightly cycle, finishing before the 07:00 deadline, with output row counts matching input row counts | Volume test run signed off by the Data Product Owner before go-live | Must |
| AC-003 | NFR-003 | Raw data from any point in the last 7 years can still be retrieved in its original form | Zero raw records deleted within the 7-year window; a record loaded on the earliest available date is still retrievable | Retention spot-check performed at go-live and annually | Must |
| AC-004 | NFR-004 | Dashboards are usable throughout the working day | Available at least 99.5% of the 07:00–20:00 CET window, measured monthly | Monthly availability report | Must |
| AC-005 | NFR-005 | No individual person can be identified from any data the platform holds or produces | Zero individual-level identifiers present in any layer or output; visitor data is aggregated counts only | Data protection review of every table, signed off by the Data Product Owner before go-live | Must |
| AC-006 | NFR-006 | A station manager can see their own station's data and nothing else | A station manager account returns rows for their own station only and exactly zero rows for every other station | Access test executed for at least three station manager accounts before go-live | Must |
| AC-007 | NFR-007 | A failed nightly load never results in silent data loss or an unnoticed gap | Failure raises an alert to the Data Product Owner within 30 minutes, and the affected day is either recovered automatically or explicitly flagged as incomplete | Documented failure drill executed before go-live | Must |
| AC-008 | NFR-008 | Any figure in any report can be traced back to the load event that produced it | Every load event records timestamp, source, row count, and outcome; a sampled figure can be traced to its load event in under 5 minutes | Traceability walkthrough with the Finance Controller | Must |
| AC-009 | UC-001 | Daily visitor counts per station match the source ticketing system | Exact match — zero row difference — for a chosen reference date across all stations | Side-by-side comparison against the ticketing system's own daily report | Must |
| AC-010 | UC-002 | Re-running a past report gives the same answer it gave at the time | Zero change to any previously published figure for a prior period after a station is reclassified or renamed | Before-and-after comparison using a deliberately reclassified station | Must |
| AC-011 | UC-003 | Monthly revenue by station and category reconciles to the finance ledger | Within 0.1% per station per category per month; any larger deviation is explained and documented | Monthly reconciliation reviewed and signed by the Finance Controller | Must |
| AC-012 | UC-006 | Year-on-year comparisons reproduce figures already published to the board | Prior-year figures for a known reference month match the archived board report exactly | Comparison against the archived board report for that month | Must |
| AC-013 | UC-004, R-001 | Revenue is never attributed to the wrong product when a product code is reused | Revenue from a discontinued product and revenue from a later product reusing the same code are reported separately, never merged | Test using a known recycled product code, verified by the Head of BI | Must |
| AC-014 | UC-007 | Missing station feeds are detected before business users notice them | Every station that has not delivered data is listed by 06:00 CET on the same morning | Data completeness monitor reviewed daily by the Data Product Owner | Should |
| AC-015 | UC-005 | Hourly visitor patterns are complete across the full day | Hourly counts for any station and date sum exactly to that station's daily total for the same date | Spot-check across five stations and five dates | Should |

---

## 8. Stakeholder Register

| Name | Role | Interest | Influence | Sign-Off Required |
|---|---|---|---|---|
| Head of BI | Requirements lead; primary platform champion | High — will use platform daily | High | Yes — requirements and go-live |
| Data Product Owner | Owns data quality and platform governance | High — accountable for data accuracy | Medium | Yes — requirements |
| Finance Controller | Key consumer; drives year-on-year reporting | High — monthly board reporting depends on this | High | Yes — financial data accuracy |
| IT Operations Manager | Owns source systems and access | Medium — needs to provide connectivity | Medium | No — consulted only |
| Station Managers (×50) | End consumers via dashboards | Medium — daily operational use | Low | No — user acceptance testing |

---

## 9. Assumptions & Risks

| # | Type | Description | Impact | Mitigation |
|---|---|---|---|---|
| A-001 | Assumption | All 50 station ticketing systems can deliver their daily CSV file to the SFTP drop by 01:00 CET | High — late files will cause incomplete morning reports | Implement monitoring and alerting for missing files (UC-007); load partial data where possible |
| A-002 | Assumption | The Finance Master Data extract is sufficiently stable to use as a weekly-refreshed reference; no intra-week changes need to be reflected same-day | Medium | If intra-week changes are needed, increase refresh frequency |
| A-003 | Assumption | Hospitality outlet data quality will improve over time; initial phase may have gaps for the 3 unconfirmed outlets | Medium | Design ingestion to handle missing outlet data gracefully; flag gaps in monitoring |
| A-004 | Assumption | Visitor count data is already aggregated at source (no individual-level tracking) — GDPR compliance is inherited | High — if individual data exists, redesign needed | Confirm with IT Operations before go-live |
| R-001 | Risk | Product codes are recycled in the retail POS system — a product discontinued in 2023 may reuse the same code for a new product in 2025 | High — historical revenue will be misattributed if not handled | Architect must design a surrogate key strategy that decouples the platform's product identity from the source system's reused natural key |
| R-002 | Risk | 3 of 12 hospitality outlets have not confirmed data access | Medium — Phase 2 hospitality use cases will be incomplete | Escalate to Head of Hospitality; defer those outlets to a later phase if access is not confirmed by architecture review |
| R-003 | Risk | Excel files from hospitality outlets may arrive in inconsistent formats if submitted manually | Medium — load failures or data errors | Implement schema validation at the landing layer; quarantine malformed files |
| R-004 | Risk | Row-level security by station requires the BI/reporting layer to enforce access correctly — a misconfiguration could expose all-station data to a station manager | High — data privacy and trust | Architecture must include explicit access control design; security review required before go-live |

---

## 10. Open Questions

| # | Question | Owner | Due Date | Status |
|---|---|---|---|---|
| Q-001 | Can the Station Ticketing System (S-001) provide incremental exports (only changes since last extract) rather than full daily dumps? This would significantly reduce load volume. | IT Operations Manager | 2026-03-20 | Open |
| Q-002 | What is the exact format variation between old and new STS station versions? A schema mapping must be agreed before ingestion is designed. | IT Operations Manager + Data Product Owner | 2026-03-27 | Open |
| Q-003 | Are the 3 unconfirmed hospitality outlets (from HMS, S-003) in scope for Phase 1 or only Phase 2? | Head of Hospitality + Data Product Owner | 2026-03-20 | Open |
| Q-004 | Does the Finance Controller need revenue data broken down by individual transaction, or is a daily/monthly aggregate sufficient for board reporting? | Finance Controller | 2026-03-20 | Open |
| Q-005 | What is the expected growth in station count over the next 3 years? This affects platform capacity planning. | Head of BI | 2026-04-01 | Open |

---

## 11. Rework Intake

No rework recorded. This section is populated when `@validator` or a downstream agent routes a failure back to Phase 0.

| # | Date | Raised By | Gate | Finding | Affected IDs | Diagnosis | Resolution | Doc Version |
|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | — |

---

## 12. Architect Agent Handoff

### Summary for `@architect`

This project builds a **nightly-batch analytics platform** for a Swiss railway operator, consolidating visitor and revenue data from 5 source systems across 50 stations.

**Confirmed Scope**
- Visitor counts, ticket sales, retail sales, and hospitality revenue — all per station
- 50 stations, phased go-live: ticketing first, retail and hospitality in Phase 2
- Nightly refresh, data available by 7am

**Out of Scope**
- Real-time streaming, ML/AI models, HR data, external benchmarks

**Use Cases Driving the Architecture** *(see Section 2)*
- UC-001, UC-002: Daily visitor counts by station, with trend over time — drives need for time dimension and station dimension
- UC-003, UC-006: Revenue by category and YoY comparison — drives need for a conformed revenue fact and date dimension supporting period comparison
- UC-005: Peak hour analysis — drives need for hour-of-day granularity in the time dimension
- UC-007: Data completeness monitoring — drives need for a metadata/audit layer visible to the data product owner

**Entities Requiring Historical Tracking** *(see Section 6)*
- **E-001 Station** — reclassification must not change historical reports. History needed.
- **E-002 Product** — price and category change frequently; historical revenue must reflect price at time of sale. History needed.
- **E-003 Outlet** — type and status changes; needed for trend analysis. History needed.
- **E-004 Ticket Type** — rarely changes but YoY comparison requires stability. History needed.
- **E-007 Cost Centre** — hierarchy restructures must not retroactively change historical financial reports. History needed.
- **E-005 Visitor Count** and **E-006 Sales Transaction** are measurements (facts) — append-only, no history tracking needed.

**Data Freshness SLAs**
- Core data (visitor counts, revenue): available by 7am every business day
- Reference/master data (finance hierarchy, product catalogue): weekly refresh is acceptable

**Compliance & Security Constraints**
- NFR-005: No personally identifiable information at individual level — visitor data is aggregated at source; architecture must ensure no individual identifiers flow through any layer
- NFR-006: Row-level security by station required at the consumption layer — station managers see only their station's data
- NFR-003: 7-year retention required for raw data
- NFR-008: Full audit trail of all load events required

**Source System Landscape** *(see Section 5)*
- S-001 STS: 50 stations, daily CSV via SFTP — file format variations between station versions (Q-002 open)
- S-002 RPOS: Daily DB extract — recycled product codes (R-001 critical risk for architect)
- S-003 HMS: Daily Excel files — 3 outlets unconfirmed (Q-003 open); potential for malformed files (R-003)
- S-004 TOS: Daily DB extract — operational context/dimension only
- S-005 FMD: Weekly DB extract — reference/master data

**Acceptance Criteria the Architecture Must Satisfy** *(see Section 7)*
- **AC-009, AC-011, AC-012** demand an auditable lineage from source to published figure, with control totals captured at every layer boundary — reconciliation to the finance ledger within 0.1% and exact reproduction of archived board figures cannot be demonstrated without it
- **AC-010** demands point-in-time correctness: a reclassified station must not alter previously published figures. This is the architectural driver for entity historisation
- **AC-013** demands that product identity survive source-system code reuse — this is R-001 expressed as a testable criterion, and it constrains the key strategy
- **AC-005, AC-006** demand that access control and data-minimisation be designed into the layers, not added at the reporting surface
- **AC-007, AC-008** demand load-event logging, restartability, and alerting as first-class architectural components
- **AC-001, AC-002** constrain scheduling and load-window design

**Open Questions Requiring Architectural Decisions** *(see Section 10)*
- Q-001: If STS can provide incremental exports, the ingestion pattern changes from full-load to watermark-based — architect should design for both and confirm with IT
- Q-002: Schema variations across station versions require a mapping strategy at the landing or cleansing layer
- R-001: Recycled product codes in RPOS require the architect to design a surrogate key strategy that survives product code reuse — this is a critical design decision, and AC-013 is the criterion it will be judged against

---

## 13. Definition of Done Attestation

| Gate | Description | Result | Notes |
|---|---|---|---|
| A | Structure | Pass | All 13 sections present; IDs unique and well-formed; no bare placeholders |
| B | Content completeness | Pass | 8 use cases, 10 FRs all traced to UCs, 5 sources with owners and access status, 7 entities with explicit history decisions, all NFR categories covered |
| C | Loop readiness | Pass | 15 acceptance criteria; every NFR and every High-priority UC covered; all criteria measurable and technology-free; Rework Intake section present |
| D | Stakeholder & scope | Pass | In and out of scope defined; three sign-off owners identified; all 5 open questions owned and dated; user confirmation recorded in changelog |
| E | Handoff | Pass | Handoff references concrete UC / E / S / NFR / AC / Q IDs; history needs stated without prescribing SCD types; open architectural questions listed |

**Overall:** `Approved`

Three open questions (Q-001, Q-002, Q-003) remain unresolved at sign-off. Each has a named owner and a due date, and each is surfaced to `@architect` as a design input rather than a blocker — consistent with the DoD escalation rule that explicit, documented unknowns are acceptable but silence is not.

---

## Changelog

| Version | Date | Change | Trigger |
|---|---|---|---|
| 1.0 | 2026-03-13 | Initial requirements captured. Summary and acceptance criteria confirmed by Head of BI, Data Product Owner, and Finance Controller before the document was written. | Discovery interview |
