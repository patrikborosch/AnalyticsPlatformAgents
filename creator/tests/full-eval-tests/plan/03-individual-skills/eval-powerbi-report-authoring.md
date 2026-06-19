---
plugin: powerbi-authoring
---

# Eval Plan: powerbi-report-authoring

## Skill Overview
- **Skill:** `powerbi-report-authoring`
- **Category:** Power BI Report Authoring
- **Purpose:** Create and modify local Power BI PBIR/PBIP report files, including pages, visuals, filters, slicers, bookmarks, themes, formatting, validation, and Power BI Desktop verification loops.

## Pre-requisites
- Local PBIP fixture at `./evalsets/fixtures/sales-pbip/` (a writable copy is provisioned per case before the prompt is sent so each case starts from the same baseline)
- The `powerbi-report-author` and `powerbi-desktop` CLIs are **not assumed to be installed**; the skill should fall back to its reference files (degraded mode) when the CLIs are unavailable

> **Execution Rules:** See [00-overview.md](../00-overview.md#execution-rules-mandatory) — all rules apply to every test below.

## Test Cases

### PBRA-01: Add a Page
- **Prompt:** "In the PBIP at `./evalsets/fixtures/sales-pbip/`, add a page that summarizes products by revenue. Keep the layout simple."
- **Expected:** Skill edits the local PBIR files to add a new page with at least one visual, following the PBIR file layout from its reference files.
- **Pass criteria (verified by inspecting the PBIP after the run):**
  - `sales.Report/definition/pages/pages.json` has exactly one additional entry in `pageOrder` matching a new page directory under `definition/pages/`.
  - The new `pages/<id>/page.json` exists with a `$schema` URL, a non-empty `displayName` clearly tied to products, and `height`/`width` at least 720/1280 (larger custom canvases are also valid).
  - At least one `pages/<id>/visuals/<visualId>/visual.json` exists with a `$schema` URL, a valid `visualType`, and at least one role projection in `visual.query.queryState` bound to a real `Sales` table column or measure (no fictional fields).
  - All touched JSON files parse cleanly; no existing pages, visuals, or `definition.pbir`/`version.json` content is corrupted.

### PBRA-02: Add a Card Visual
- **Prompt:** "Add a headline KPI for total quantity to the Overview page of `./evalsets/fixtures/sales-pbip/`."
- **Expected:** Skill adds a single Card visual on the existing Overview page bound to the appropriate measure.
- **Pass criteria:**
  - A new `visual.json` exists under `sales.Report/definition/pages/<Overview-id>/visuals/<visualId>/` and is the only net-new visual on that page.
  - `visualType` is `"cardVisual"` (not legacy `"card"`).
  - The `Data` role has at least one projection bound to the `Sales.Total Quantity` measure with correct `field.Measure`, `queryRef`, and `nativeQueryRef` shape.
  - `position` lies fully within the 1280×720 canvas and does not overlap any pre-existing visual on the Overview page.
  - File parses cleanly; `$schema` URL is set; no other visuals modified.

### PBRA-03: Make a Visual Stand Out
- **Prompt:** "Make the headline KPI on the Overview page stand out more."
- **Expected:** Skill applies visual-formatting or theming changes to the target card without re-authoring it.
- **Pass criteria:**
  - A real, intentional formatting change shows up vs. the pre-run state in at least one of: the card's `visual.json` (e.g. larger font size, set color, callout enabled, accent), the page's `page.json` formatting (e.g. background, wallpaper), or the theme JSON under `sales.Report/StaticResources/RegisteredResources/<theme>.json` (e.g. updated `dataColors`, callout/card style block) — with the `report.json` `themeCollection` and `resourcePackages` entries updated consistently if the theme file is renamed.
  - Any added formatting in PBIR uses correct Literal-expression encoding — colors as `{"solid":{"color":{"expr":{"Literal":{"Value":"'#hex'"}}}}}`, numeric properties as `{"expr":{"Literal":{"Value":"<n>D"}}}`, booleans as `"true"`/`"false"` Literals. Theme-JSON edits use plain theme-schema shapes (not Literal expressions).
  - All touched files still parse; no other visuals on the page are mutated; existing data bindings on the card are preserved.

### PBRA-04: Ambiguous Edit Request
- **Prompt:** "Make this report better."
- **Expected:** Skill asks for or derives concrete authoring requirements before editing.
- **Pass criteria:** Output does not make arbitrary PBIR changes; it asks for goals or proposes bounded options for pages, visuals, formatting, or validation.

### PBRA-05: Re-theming Cleanup Sweep
- **Prompt:** "I just switched my report's theme from light to dark, but several visuals still show the old accent color. Walk me through the systematic check to find and fix every visual that hardcodes the old theme colors."
- **Expected:** Skill explains the re-theming sweep workflow without requiring the CLI to be installed.
- **Pass criteria:** Output describes the systematic process (map old → new colors, scan `definition/` for hardcoded `Literal` hex values across visuals, shapes, and nav buttons), pairs the sweep with the theme JSON change, and explains how to verify after sweeping.

## Expected Token Range
- 1500–4000 tokens per invocation
