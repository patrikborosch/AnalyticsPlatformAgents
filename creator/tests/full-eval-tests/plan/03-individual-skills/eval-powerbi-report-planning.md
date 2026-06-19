---
plugin: powerbi-authoring
---

# Eval Plan: powerbi-report-planning

## Skill Overview
- **Skill:** `powerbi-report-planning`
- **Category:** Power BI Report Planning
- **Purpose:** Turn open-ended Power BI report requests into approved requirements, scope, page plans, design direction, dependencies, and implementation handoffs before PBIR files are edited.

## Pre-requisites
- Fabric workspace available as `{{WORKSPACE}}`
- At least one semantic model or local PBIP project available for report planning context
- Authentication configured if the plan needs to inspect Fabric workspace items

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### PBRP-01: Guided Requirements Intake
- **Prompt:** "Plan a new executive sales dashboard from the semantic model `nyctaxi_yellow_directlake` in workspace `{{WORKSPACE}}`. Do not build anything until I approve."
- **Expected:** Skill asks or resolves audience, goals, key metrics, report scope, dependencies, delivery target, and approval gate.
- **Pass criteria:** Output includes a structured requirements summary, explicit assumptions or clarifying questions, page plan, and a stop-before-build approval step.

### PBRP-02: Approved Implementation Handoff
- **Prompt:** "Turn the approved sales dashboard requirements into an implementation-ready report spec for authoring."
- **Expected:** Skill produces a locked report spec suitable for downstream design and authoring.
- **Pass criteria:** Output includes pages, visuals, measures/data dependencies, filters/slicers, design direction, validation expectations, and handoff instructions to report design/authoring.

### PBRP-03: Scope Control for Ambiguous Request
- **Prompt:** "Build me a Power BI report for customer churn."
- **Expected:** Skill does not start authoring immediately; it narrows scope first.
- **Pass criteria:** Output asks for missing business context or presents bounded options, including target audience, churn definition, model availability, delivery target, and approval workflow.

### PBRP-04: Spec from Sufficient Inputs
- **Prompt:** "For my sales report: audience VP of Sales, weekly review. Model tables Sales(SalesID, OrderDate, ProductName, Quantity, UnitPrice), measures `Total Revenue` and `Total Quantity`. Two pages — Overview (KPIs + monthly trend) and Products (top 10 by revenue). Generate the locked spec."
- **Expected:** Skill produces a locked report spec from the supplied inputs without re-asking for known answers.
- **Pass criteria:** Output is (or clearly describes) a `_brief/report-spec.md` artifact with audience, page plan, and per-page visuals bound only to the supplied measures/columns; includes an explicit approval/sign-off gate; does not start authoring or edit PBIR files.

### PBRP-05: Approval Gate on Build+Publish Ask
- **Prompt:** "Build me a Power BI dashboard for customer churn and publish it to my workspace."
- **Expected:** Skill enforces the planning → spec → approval flow even when publish is requested in the same breath.
- **Pass criteria:** Output does not publish, does not invoke `powerbi-report-management`, and does not edit PBIR; routes through clarification → spec → approval; explicitly notes that approval is required before any implementation or publish step.

## Expected Token Range
- 1000–2500 tokens per invocation
