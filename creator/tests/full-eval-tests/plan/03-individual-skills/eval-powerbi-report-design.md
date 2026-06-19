---
plugin: powerbi-authoring
---

# Eval Plan: powerbi-report-design

## Skill Overview
- **Skill:** `powerbi-report-design`
- **Category:** Power BI Report Design
- **Purpose:** Produce visual design guidance, page archetypes, chart choices, layout, color, accessibility direction, and design briefs before PBIR report files are authored.

## Pre-requisites
- Report requirements, semantic model summary, or existing PBIP report context available to the agent
- No live Fabric workspace is required for static design-brief tests

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### PBRD-01: Create Design Brief
- **Prompt:** "Create a visual design brief for an executive sales report with revenue KPIs, monthly trend, regional performance, and product category breakdowns. Do not edit PBIR files."
- **Expected:** Skill produces a report design brief rather than implementation changes.
- **Pass criteria:** Output includes page layout, visual choices, hierarchy, color/theming direction, typography/accessibility notes, and guidance that can be handed to report authoring.

### PBRD-02: Chart Selection Rationale
- **Prompt:** "For a Power BI report comparing revenue trend, region, category mix, and top customers, choose the right visuals and explain why."
- **Expected:** Skill recommends appropriate chart types and explains tradeoffs.
- **Pass criteria:** Output avoids unsuitable chart choices, explains when to use cards, line charts, bars, tables, and decomposition/drill visuals, and ties choices back to report goals.

### PBRD-03: Critique Existing Layout
- **Prompt:** "Review this existing Power BI report layout: one page has 12 visuals, low contrast colors, duplicated legends, and three disconnected slicer panels. What should improve before authoring changes?"
- **Expected:** Skill provides design critique and remediation guidance.
- **Pass criteria:** Output identifies hierarchy, density, contrast, slicer, alignment, and accessibility issues without editing files directly.

### PBRD-04: Brand Theme Application
- **Prompt:** "Apply our brand palette (primary `#0F4C81`, accent `#F4A300`, neutral `#5A6770`) to a sales report with a 'calm professional' voice. Describe the theme direction and any concerns."
- **Expected:** Skill maps brand colors to report theme roles and provides supporting design direction.
- **Pass criteria:** Output assigns brand colors to data/accent/neutral roles, recommends typography and tone direction consistent with the requested voice, flags any accessibility or contrast concerns, and stays in design-direction lane (no PBIR file edits, no theme JSON writes).

### PBRD-05: Accessibility Audit
- **Prompt:** "Score these foreground/background pairs for WCAG AA contrast: white on `#F4A300`, white on `#5A6770`, `#0F4C81` on white, `#888888` on white. Recommend fixes for any failures."
- **Expected:** Skill evaluates color contrast against WCAG AA and proposes remediations.
- **Pass criteria:** Output reports contrast ratios per pair, identifies which fail WCAG AA (4.5:1 for normal text, 3:1 for large text), proposes compliant alternative colors, and does not write any files.

## Expected Token Range
- 1000–2500 tokens per invocation
