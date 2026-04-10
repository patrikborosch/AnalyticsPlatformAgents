# SaaS Sales Dashboard Analysis

## Overview

The **SaaS Sales Dashboard** (`assets/sample-reports-and-content/saas-sales-dashboard/SaaS Sales dashboard.pbix`) is a real-world example of professional financial dashboarding using **IBCS standards** and **ZebraBI custom visuals**.

This analysis documents the dashboard structure, visuals used, and data patterns observed when extracting and analyzing the PBIX file.

## Dashboard Composition

### Custom Visuals Used

The dashboard leverages three ZebraBI custom visuals:

1. **ZebraBI Cards** (zebraBiCards8085D508EB994C8081CA47C85ABD7C26)
   - Version: 7.4.0.14906484778
   - Purpose: Key metric display with trend indicators and mini-charts
   - Usage: KPI overview section (top of dashboard)

2. **ZebraBI Charts** (Waterfall/Variance)
   - Visual: waterfall0221D8FBE40445C1A4E598AA8EF8B506
   - Version: 7.8.1.22097493993
   - Chart types: Hichert diagrams, waterfall analysis, variance charts
   - Usage: Mid-section analysis charts

3. **ZebraBI Tables** (IBCS Tables)
   - Visual: ZebraBITables98F88148E5424E949E69864664EE1860
   - Version: 7.8.0.22130630320
   - Purpose: Detailed financial data with variance indicators
   - Usage: Detailed breakdown tables

### Visual Resource Structure

The PBIX contains:
- **Resource Packages**: Three custom visual packages registered in the report
- **Static Resources**: 
  - Custom themes (CY23SU08.json - likely a Microsoft theme)
  - ZebraBI branding assets (zebra-bi-sign-frame17148782451773203.png)
- **Theme Configuration**: Base theme from SharedResources

## Data Model Insights

The dashboard likely contains the following semantic model elements:

### Probable Tables
- **Sales** — Transactional sales data with measures
- **Forecasts** — Planned/budgeted sales values
- **Time/Calendar** — Date dimension with period hierarchy
- **Geography** — Region, territory dimensions
- **Product** — Product category hierarchy

### Probable Measures
- Revenue (Actual)
- Revenue (Plan/Forecast)
- Revenue Variance (Actual - Plan)
- Variance % ((Actual - Plan) / Plan)
- Prior Year Revenue (for comparison)
- Growth metrics

### Probable Dimensions Used
- Month/Quarter/Year
- Product Category
- Sales Region
- Customer Segment

## IBCS Implementation

### Color Scheme Applied
- **Black (#000000)** — Actual/current period values
- **Dark Gray (#646464)** — Plan/budget/forecast values
- **Light Gray (#C8C8C8)** — Prior year baseline
- **Green (#00B050)** — Favorable variance
- **Red (#FF0000)** — Unfavorable variance

### Chart Hierarchy Pattern

Typical SaaS dashboard structure follows:
```
┌─────────────────────────────────────────┐
│        Summary KPI Tier                 │
│  (ZebraBI Cards - 4-6 main metrics)    │
├─────────────────────────────────────────┤
│     Analysis Tier                       │
│  (ZebraBI Charts - Hichert/Waterfall)  │
│  Plan vs Actual vs Prior Year          │
├─────────────────────────────────────────┤
│     Detail Tier                         │
│  (ZebraBI Tables - by product/region)  │
│  Variance breakdowns and variance %     │
└─────────────────────────────────────────┘
```

## Key Observations

### 1. Custom Visual Registration
- Custom visuals are embedded in the PBIX as package resources
- Each visual has a unique GUID for identification
- Versions are specific and should be matched when replicating

### 2. Report Structure
- Report uses PBIX binary format (not PBIR text format)
- Layout stored in Report/Layout file as compressed JSON
- Visual definitions include positioning (x, y, z, height, width)

### 3. Theme Integration
- Uses Microsoft's CY23SU08 base theme (likely Fabric design system)
- Custom branding assets included (ZebraBI logo)
- Colors follow IBCS standard conventions

## What Makes This Dashboard Effective

1. **Progressive Disclosure**: 
   - Executives see KPI cards first (high-level overview)
   - Then variance analysis (what changed)
   - Finally detail tables (why it changed)

2. **IBCS Compliance**:
   - Consistent color usage (red/green for variance)
   - Standard chart types (Hichert, waterfall)
   - Professional typography and layout

3. **Interactivity**:
   - ZebraBI Cards with trend indicators enable quick pattern recognition
   - Variance charts highlight deviations from plan
   - Detail tables support drill-down and analysis

4. **Performance**:
   - ZebraBI visuals are optimized for large datasets
   - Multiple visuals on one page with independent filtering
   - Sparklines in cards and tables provide micro-trends

## Replicating This Dashboard

To create a similar SaaS sales dashboard:

1. **Create semantic model** with Sales, Plan, Prior Year measures
2. **Design pages** following the hierarchy above
3. **Add ZebraBI Cards** for KPI overview
4. **Add ZebraBI Charts** for variance analysis
5. **Add ZebraBI Tables** for detail and drill-down
6. **Configure IBCS colors** (green/red, black/gray)
7. **Test performance** with typical data volumes
8. **Deploy to Fabric workspace** for sharing

See the **Quick Start Guide** in `references/quick-start.md` for step-by-step instructions.

## Integration with Copilot

When using the `powerbi-ibcs` skill with GitHub Copilot:

1. **Design phase**: Describe your requirements to Copilot
   - "Create a SaaS dashboard with ZebraBI visuals showing revenue vs plan"
   - Copilot will suggest data model structure and visual layout

2. **Development phase**: Copilot can generate JSON for visuals
   - "Generate a ZebraBI Card visual for total revenue with variance"
   - Copilot will output complete visual.json with proper field bindings

3. **Validation phase**: Copilot can validate compliance
   - "Check this dashboard for IBCS compliance"
   - Copilot will review colors, symbols, and data accuracy

## References

- **Dashboard Location**: `assets/sample-reports-and-content/saas-sales-dashboard/SaaS Sales dashboard.pbix`
- **Data File**: `assets/sample-reports-and-content/saas-sales-dashboard/Data.xlsx`
- **Main Skill**: `../SKILL.md`
- **Quick Start**: `./quick-start.md`
- **IBCS Reference**: `./ibcs-standard.md`
- **ZebraBI Config**: `./zebrabi-configuration.md`

## Next Steps

1. Open the SaaS Sales dashboard in Power BI Desktop to see it in action
2. Explore how each ZebraBI visual is configured
3. Use the JSON examples in this skill to build your own dashboards
4. Deploy to Fabric workspace for team collaboration
5. Customize for your specific business metrics and data
