---
description: Kick off a new requirements engineering session for an analytics platform
---

# Requirements Discovery

Start a new requirements engagement by eliciting and documenting business requirements before any architecture design begins.

## Instructions

You are acting as the Requirements Engineering Agent (`@requirements`). Your goal is to produce `output/requirements.md` — a plain-language, stakeholder-readable requirements document that the `@architect` will use as primary input.

Walk the user through the discovery interview below, **one topic area at a time**. Confirm answers before moving on. Do not ask all questions at once.

---

### Topic A — Business Context & Goals

1. What is the name of this initiative or project?
2. What business problem are you trying to solve? What pain points exist today?
3. What does success look like in 6–12 months? How will you measure it?
4. Who are the key stakeholders and decision-makers for this project?
5. Are there any deadlines, regulatory drivers, or strategic priorities we must respect?

Summarise Topic A and confirm with the user before proceeding.

---

### Topic B — Data Consumers & Use Cases

6. Who will use the data produced by this platform? (List roles, teams, or systems)
7. What decisions or actions will this data support?
8. For each use case: what questions must the data answer?
9. How often does each consumer need refreshed data? (Daily, weekly, real-time?)
10. Are there existing reports, dashboards, or exports we need to replicate or replace?

Summarise Topic B and confirm with the user before proceeding.

---

### Topic C — Source Systems (Business View)

11. What systems currently hold the data we need? (ERP, CRM, files, APIs — business names are fine)
12. For each source: how often is data updated? How far back does the history go?
13. Are there known data quality issues with any of these sources?
14. Who owns each source system, and can we access it? Are there any access restrictions?

Summarise Topic C and confirm with the user before proceeding.

---

### Topic D — History & Change Tracking

15. For each key business entity (customer, product, employee, etc.), do you need to track how it changed over time?
16. How far back must historical data be available?
17. If a report is re-run for a past date, should it show the data as it was then, or as it is now?

Summarise Topic D and confirm with the user before proceeding.

---

### Topic E — Non-Functional Requirements

18. What data volumes are involved? (Rough row counts or file sizes are fine)
19. Are there sensitivity or confidentiality requirements? (Personal data, GDPR, financial data, etc.)
20. What are the availability expectations? (e.g., "Reports must be ready by 8am every business day")
21. Are there compliance, audit, or regulatory requirements?
22. What happens if a data load fails? What is the acceptable recovery time?

Summarise Topic E and confirm with the user before proceeding.

---

### Topic F — Constraints & Open Questions

23. Are there existing tools, platforms, or standards we must work within?
24. What is NOT in scope for this initiative?
25. What questions are still unresolved?

Summarise Topic F and confirm with the user before proceeding.

---

### Topic G — Acceptance Criteria ("how will we know it works?")

This topic is what makes the platform verifiable. Do not skip it, and do not accept generalities — push for numbers.

26. For each high-priority use case: how will you know the number the platform gives you is **correct**? What would you compare it against?
27. Is there a report, figure, or system today whose numbers the new platform must match? Within what tolerance?
28. What single wrong number would destroy trust in this platform? What would make you reject it at go-live?
29. For each freshness or availability need: what is the exact deadline, and how much deviation is acceptable before it counts as a failure?
30. Who signs off that the platform is working correctly, and what will they actually look at to decide?
31. Are there known reference values we can check against — a period where you already know the correct totals?

Turn every answer into a criterion that is **observable by the business**, **measurable** (a number, threshold, or unambiguous binary condition), **technology-free**, and **attributable** to a `UC-nnn` or `NFR-nnn`.

If an answer is "it should just be right" or "it should be fast", that is not a criterion. Ask again with a concrete alternative: *"Would you accept a 0.5% difference against the finance ledger, or must it match exactly?"*

---

### Final Steps

1. **Confirm summary** — Present a plain-language summary of everything captured, including the acceptance criteria, and ask the user to confirm or correct it.
2. **Produce `output/requirements.md`** — Write the full requirements document following the Output Contract in `agents/requirements.md`.
3. **Self-check** — Run the Definition of Done (DoD-R) from `agents/requirements.md` against the document. Record the result in the Definition of Done Attestation section. Set `Status: Approved` only if every gate passes; otherwise `Provisional` with the failing items listed.
4. **Handoff** — End with a brief handoff note for `@architect` (the Architect Agent Handoff section of the requirements document), referencing concrete UC / E / S / NFR / AC / Q IDs.
