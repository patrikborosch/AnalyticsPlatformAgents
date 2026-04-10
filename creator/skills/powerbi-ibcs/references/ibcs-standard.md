# IBCS Standard Overview

This document provides a quick reference to the **International Business Communication Standards (IBCS)** as applied to Power BI and ZebraBI visuals.

## IBCS Principles

IBCS defines standardized rules for business communication graphics. The key principles are:

1. **Consistency** — All similar information is presented the same way
2. **Clarity** — Information is presented in the clearest, simplest way possible
3. **Comprehension** — The audience understands the message quickly and correctly

## IBCS Color Scheme

### Standard Colors

| Color | Meaning | RGB | Hex |
|-------|---------|-----|-----|
| Black | Actual/Current values | (0, 0, 0) | #000000 |
| Dark Gray | Plan/Budget/Forecast | (100, 100, 100) | #646464 |
| Light Gray | Prior Year/Baseline | (200, 200, 200) | #C8C8C8 |
| Green | Favorable variance | (0, 176, 80) | #00B050 |
| Red | Unfavorable variance | (255, 0, 0) | #FF0000 |
| Yellow | Warning/Attention | (255, 192, 0) | #FFC000 |
| White | Neutral/Not applicable | (255, 255, 255) | #FFFFFF |

### Variance Color Rules

- **Favorable outcomes** (profit ↑, cost ↓): Green
- **Unfavorable outcomes** (profit ↓, cost ↑): Red
- **Neutral or no variance**: Black, Gray, or White
- **Threshold-based**: Yellow when variance approaches limit

## IBCS Chart Types (Hichert Diagrams)

### Hichert Box (H-Chart)

**Use**: Comparing actual, plan, and prior year values simultaneously

**Structure**:
```
  ┌─────────────────────┐
  │  ACTUAL (solid)     │  ← Black solid box
  │  PLAN (outline)     │  ← Gray outline
  │  PRIOR YR (gray)    │  ← Light gray background
  └─────────────────────┘
```

**Data requirements**:
- Actual value
- Plan/Budget value
- Prior year value

### Waterfall Chart

**Use**: Showing how an initial value bridges to a final value through intermediate steps

**Example**: Revenue bridge from forecast to actuals
- Forecast: $1M (starting point)
- Product A sales: +$200K
- Product B sales: -$50K
- Actual: $1.15M (ending point)

**IBCS waterfall rules**:
- Positive changes: Bars pointing up
- Negative changes: Bars pointing down
- Connecting line shows cumulative flow

### Variance Chart

**Use**: Highlighting differences between two measures

**Structure**:
- Base bar: One measure (e.g., Plan)
- Variance bar: Difference (e.g., Actual - Plan)
- Color: Green if favorable, Red if unfavorable

## IBCS Symbol Conventions

### Symbols in Cards and Tables

| Symbol | Meaning | Usage |
|--------|---------|-------|
| ↑ | Increasing, favorable direction | KPI trending up, variance favorable |
| ↓ | Decreasing, unfavorable direction | KPI trending down, variance unfavorable |
| → | Neutral, no change | No variance, flat trend |
| ◆ | Alert/Attention needed | Threshold exceeded |
| ■ | Actual (solid box) | Hichert actual value |
| □ | Plan (outline box) | Hichert plan value |

## IBCS Typography Rules

1. **Font**: Sans-serif (Arial, Calibri, Segoe UI)
2. **Font sizes**:
   - Headers: 12-14pt
   - Data: 10-11pt
   - Legends: 9-10pt
3. **Weight**:
   - Headlines: Bold
   - Actual values: Regular or bold
   - Plan/baseline: Regular
4. **Emphasis**: Use bold sparingly for key metrics only

## IBCS Layout Principles

1. **Simplification**: Remove all non-essential elements (gridlines, decorations)
2. **Organization**: Group related information together
3. **Hierarchy**: Most important information in top-left (reading direction)
4. **Alignment**: Use consistent spacing and alignment
5. **White space**: Use generous white space for clarity

### Layout Template (Dashboard Page)

```
┌─────────────────────────────────────────────────┐
│  Dashboard Title                                │
├─────────────────────────────────────────────────┤
│  KPI Card 1  │  KPI Card 2  │  KPI Card 3      │  ← Summary tier
├─────────────────────────────────────────────────┤
│                                                 │
│         Hichert Chart / Variance Analysis       │  ← Analysis tier
│                                                 │
├─────────────────────────────────────────────────┤
│                                                 │
│    Detailed Table (by Product, Region, etc.)   │  ← Detail tier
│                                                 │
└─────────────────────────────────────────────────┘
```

## Variance Calculation & Interpretation

### Types of Variance

1. **Absolute Variance** = Actual - Plan
   - Example: Revenue $1.1M - Plan $1.0M = +$100K
   - Direction: Positive = Favorable (for revenue), Negative = Unfavorable

2. **Percentage Variance** = (Actual - Plan) / Plan × 100%
   - Example: +$100K / $1.0M × 100% = +10%
   - Magnitude: Threshold-based (e.g., >5% is "high variance")

3. **Favorable/Unfavorable**:
   - **Revenue/Sales**: Actual > Plan = Favorable (green), Actual < Plan = Unfavorable (red)
   - **Costs/Expenses**: Actual > Plan = Unfavorable (red), Actual < Plan = Favorable (green)

### IBCS Variance Thresholds

Define organizational thresholds for variance interpretation:

| Variance Range | Classification | Action |
|---|---|---|
| ±0-2% | Within tolerance | No action, gray |
| ±2-5% | Minor variance | Monitor, neutral color |
| ±5-10% | Significant variance | Alert, yellow |
| >±10% | Major variance | Critical alert, red |

## IBCS Compliance Checklist

- [ ] Color scheme matches IBCS standard (black/gray/green/red)
- [ ] Chart types use appropriate Hichert, waterfall, or variance format
- [ ] Symbols are consistent (↑/↓/→) and meaningful
- [ ] Font is sans-serif, size is readable (10-14pt)
- [ ] Title clearly describes the metric/analysis
- [ ] Legend identifies all measures (Actual, Plan, Prior Year)
- [ ] No unnecessary gridlines, decorations, or 3D effects
- [ ] Variance calculation is clearly defined
- [ ] Mobile-responsive layout is tested
- [ ] Accessibility features (contrast, alt text) are included

## Examples by Use Case

### Sales Performance Dashboard

**KPI Cards** (ZebraBI Cards):
- Total Sales (Actual vs Target)
- Sales Growth % (YoY)
- Sales by Region

**Analysis** (ZebraBI Charts):
- Revenue bridge: Forecast → Actuals
- Region variance: Plan vs Actual

**Detail** (ZebraBI Tables):
- Sales by Product and Region with variance indicators

### Financial Statement

**KPI Cards**:
- Revenue, COGS, Operating Income, Net Income

**Analysis**:
- Revenue bridge (Plan vs Actual)
- COGS variance (favorable/unfavorable)

**Detail**:
- Income statement with GL account hierarchy
- Variance column highlighting significant items

### Cost Variance Report

**KPI Cards**:
- Total Costs, Variance %, Variance Amount

**Analysis**:
- Hichert diagram: Actual vs Budget vs Prior Year
- Waterfall: How budget variances accumulate

**Detail**:
- Cost center variance table
- Cost category breakdown with sparklines

## References

- [IBCS Official Website](https://www.ibcs.com/)
- [IBCS Standard Document](https://www.ibcs.com/standard)
- [ZebraBI IBCS Implementation](https://zebrabi.com/ibcs)
