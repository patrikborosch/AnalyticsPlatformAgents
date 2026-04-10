---
name: powerbi-ibcs
description: Guide to develop Power BI Reports using IBCS (International Business Communication Standards) and ZebraBI visuals for professional financial dashboards. Use this skill for creating Hichert diagrams, variance charts, IBCS-compliant tables, and KPI cards in PBIR format. Covers ZebraBI Cards, ZebraBI Charts (waterfall/variance), and ZebraBI Tables for financial and business reporting.
---

# Power BI IBCS & ZebraBI Visuals Skill

This skill provides guidance on how to develop professional financial and business dashboards using **IBCS (International Business Communication Standards)** with **ZebraBI custom visuals** in Power BI PBIR format.

## What is IBCS?

**IBCS** is an international standard for business communication that ensures consistency, clarity, and professionalism in business graphics and tables. It provides rules for:

- **Color coding**: Red for negative variance/unfavorable, green for positive/favorable, black for neutral
- **Chart types**: Specific visualization types for different data relationships (Hichert diagrams, waterfalls, variances)
- **Symbol usage**: Standardized symbols and notation for financial metrics
- **Typography & layout**: Professional presentation standards

IBCS is particularly suited for:
- Executive dashboards
- Financial reporting (P&L, variance analysis, forecasts)
- Performance dashboards (KPI monitoring)
- Sales and cost variance reporting
- Budget vs. actuals analysis

## ZebraBI Custom Visuals

The SaaS Sales Dashboard example uses three ZebraBI custom visuals that implement IBCS standards:

### 1. **ZebraBI Cards** (zebraBiCards)
**Purpose**: Showcase key metrics with trend indicators and mini-charts.

**Use cases**:
- KPI cards with actual vs target
- Trend indicators (↑ favorable, ↓ unfavorable)
- Contextual sparklines within cards
- Sales quota achievement, revenue targets

**Typical configuration**:
- Main metric value (large, bold)
- Secondary metric (trend, period-over-period)
- Mini chart (sparkline showing trend over time)
- Color-coded status (IBCS-compliant green/red/gray)
- Variance percentage or absolute value

### 2. **ZebraBI Charts** (Waterfall/Variance)
**Purpose**: Show composition and variance analysis using Hichert diagrams and waterfall charts.

**Chart types supported**:
- **Waterfall charts**: Show how initial value changes through intermediate steps to reach final value (e.g., forecast to actual sales)
- **Variance charts**: Compare budget vs actual with variance highlights
- **Hichert diagrams**: Multi-dimensional Hichert boxes showing actual (solid), plan (outline), and previous year (gray) simultaneously
- **Combo charts**: Mix of column, area, line, and variance in small multiples

**Use cases**:
- Revenue bridge (budget → actuals)
- Variance analysis (plan vs actual)
- Actuals + Plan + Prior Year comparison
- Waterfall cost breakdown
- Sales funnel variance

**IBCS colors**:
- Solid black/dark: Actual values
- Outline/hollow: Plan/budget values
- Gray: Prior year/baseline
- Red fills: Unfavorable variance
- Green fills: Favorable variance

### 3. **ZebraBI Tables** (IBCS Tables)
**Purpose**: Display structured financial data with embedded mini-charts and variance indicators.

**Use cases**:
- Income statements with YoY comparison
- Sales variance reports (by product, region, salesperson)
- Cost variance reporting
- Budget vs actuals tables
- Detailed financial schedules

**Features**:
- Row-level mini charts (sparklines, bars, variance indicators)
- IBCS-compliant color coding by row
- Conditional formatting based on variance thresholds
- Hierarchy support (parent-child financial statements)
- Sortable and filterable columns

## Critical Concepts

### PBIR Integration with Custom Visuals

Unlike native visuals, custom visuals (like ZebraBI) in PBIP projects require:

1. **Visual GUIDs** — Each custom visual has a unique GUID (e.g., `zebraBiCards8085D508EB994C8081CA47C85ABD7C26`) that references its package
2. **Resource packages** — Custom visual resources must be registered in the PBIP structure
3. **Field bindings** — Data fields are mapped using consistent `Entity` and `Property` references (same as native visuals)
4. **Custom properties** — ZebraBI visuals expose additional configuration options beyond native visuals (chart type, variance settings, IBCS color schemes)

### Data Model Requirements for IBCS Dashboards

To leverage IBCS reporting effectively, your semantic model should include:

- **Actual/Actuals table** — Current period realized values
- **Plan/Budget table** — Planned or budgeted values
- **Prior Year table** — Previous period baseline for comparison
- **Variance calculations** — Measures for (Actual - Plan), % Variance, Favorable/Unfavorable flag
- **Hierarchy dimensions** — If using tables (e.g., GL account hierarchies, product categories)
- **Time dimension** — Calendar with periods for trend analysis in mini-charts
- **Status dimensions** — Traffic light indicators (Green/Yellow/Red for KPI status)

## Pre-development: Understand IBCS Report Requirements

Before creating an IBCS dashboard, gather:

1. **Business requirements**
   - What financial metrics or KPIs need monitoring?
   - What comparisons are critical (actual vs plan, YoY, forecast vs actual)?
   - Who is the audience (executive, manager, analyst)?

2. **Data structure**
   - Do you have Actual, Plan, and Prior Year data separated?
   - What hierarchies exist (GL accounts, cost centers, business units)?
   - What time granularity is needed (monthly, quarterly, daily)?

3. **IBCS compliance rules** (customize for your organization)
   - Color scheme: Standard IBCS (red/green) or company-specific?
   - Symbols: Use Hichert boxes, waterfalls, or variance charts?
   - Thresholds: When to flag variance as unfavorable (e.g., >5% variance)?

## Task: Create a KPI Dashboard with ZebraBI Cards

### Step 1: Prepare the Semantic Model

Ensure your model includes:
- **Measures**: Total Sales, Sales Target, Sales Actual, YoY Growth %
- **Dimensions**: Month, Quarter, Year, Product Category, Salesperson
- **Calculated columns** (optional): Variance Amount, Variance %, Status (Green/Red/Gray)

Example DAX for variance:
```dax
Sales Variance = [Sales Actual] - [Sales Plan]
Variance % = DIVIDE([Sales Variance], [Sales Plan], 0)
Variance Status = IF([Sales Variance] >= 0, "Favorable", "Unfavorable")
```

### Step 2: Create PBIR Report Structure

Follow the standard PBIP structure:
```
Project.Report/
├── definition/
│   ├── report.json
│   ├── version.json
│   ├── pages/
│   │   ├── pages.json
│   │   └── kpiPage/
│   │       ├── page.json
│   │       └── visuals/
│   │           ├── kpi-revenue-card/
│   │           ├── kpi-growth-card/
│   │           └── kpi-target-card/
│   └── bookmarks/
│       └── bookmarks.json
├── StaticResources/
└── definition.pbir
```

### Step 3: Add ZebraBI Cards Visual

Each ZebraBI Card visual requires a `visual.json` configured with:

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.1.0/schema.json",
  "name": "kpi_revenue_card",
  "position": {
    "x": 0,
    "y": 0,
    "z": 1000,
    "height": 180,
    "width": 250,
    "tabOrder": 0
  },
  "visual": {
    "visualType": "zebraBiCards",
    "query": {
      "queryState": {
        "Values": {
          "projections": [
            {
              "field": {
                "Measure": {
                  "Expression": {
                    "SourceRef": {
                      "Entity": "[Sales]"
                    }
                  },
                  "Property": "[Total Sales]"
                }
              },
              "queryRef": "[Sales].[Total Sales]",
              "nativeQueryRef": "[Total Sales]",
              "active": true,
              "inUse": true
            }
          ]
        },
        "Breakout": {
          "projections": []
        }
      }
    },
    "objects": {
      "card": [
        {
          "properties": {
            "cardType": 1,
            "showTrendIndicator": true,
            "showMiniChart": true,
            "ibcsCompliant": true
          }
        }
      ]
    }
  }
}
```

### Step 4: Configure ZebraBI Properties

ZebraBI Cards support these configuration properties:

- **cardType**: 0=Single metric, 1=Actual vs Target, 2=Trend card
- **showTrendIndicator**: Display ↑/↓ based on variance
- **showMiniChart**: Embed sparkline showing metric trend
- **ibcsCompliant**: Apply IBCS color scheme (red/green)
- **colorForFavorable**: RGB color for positive variance (default: green)
- **colorForUnfavorable**: RGB color for negative variance (default: red)
- **decimalPlaces**: Number format
- **suffix**: e.g., "%", "K", "M"

## Task: Create Variance Analysis with ZebraBI Charts (Hichert/Waterfall)

### Step 1: Design the Chart

Determine which chart type fits your analysis:

| Chart Type | Best For | Example |
|-----------|----------|---------|
| **Waterfall** | Showing how initial value changes step-by-step | Forecast → Actuals (Bridge analysis) |
| **Hichert/Variance** | Comparing Actual, Plan, Prior Year side-by-side | Budget vs Actual + Prior Year |
| **Combo** | Multiple measures or time periods in small multiples | Multiple regions' variance charts |

### Step 2: Add ZebraBI Charts Visual

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.1.0/schema.json",
  "name": "variance_analysis_chart",
  "position": {
    "x": 250,
    "y": 0,
    "z": 1000,
    "height": 400,
    "width": 600,
    "tabOrder": 1
  },
  "visual": {
    "visualType": "waterfall0221D8FBE40445C1A4E598AA8EF8B506",
    "query": {
      "queryState": {
        "Category": {
          "projections": [
            {
              "field": {
                "Column": {
                  "Expression": {
                    "SourceRef": {
                      "Entity": "[Time]"
                    }
                  },
                  "Property": "[Month]"
                }
              },
              "queryRef": "[Time].[Month]",
              "nativeQueryRef": "[Month]",
              "active": true
            }
          ]
        },
        "Y": {
          "projections": [
            {
              "field": {
                "Measure": {
                  "Expression": {
                    "SourceRef": {
                      "Entity": "[Sales]"
                    }
                  },
                  "Property": "[Sales Actual]"
                }
              },
              "queryRef": "[Sales].[Sales Actual]",
              "nativeQueryRef": "[Sales Actual]"
            },
            {
              "field": {
                "Measure": {
                  "Expression": {
                    "SourceRef": {
                      "Entity": "[Sales]"
                    }
                  },
                  "Property": "[Sales Plan]"
                }
              },
              "queryRef": "[Sales].[Sales Plan]",
              "nativeQueryRef": "[Sales Plan]"
            }
          ]
        }
      }
    },
    "objects": {
      "chart": [
        {
          "properties": {
            "chartType": "hichert",
            "ibcsCompliant": true,
            "showVariance": true,
            "showPriorYear": true,
            "colorActual": "#000000",
            "colorPlan": "#999999",
            "colorPriorYear": "#CCCCCC",
            "colorFavorable": "#00B050",
            "colorUnfavorable": "#FF0000"
          }
        }
      ]
    }
  }
}
```

### Step 3: Configure Hichert/Variance Properties

ZebraBI Charts support:

- **chartType**: "waterfall", "hichert", "variance", "combo"
- **ibcsCompliant**: Enable IBCS color scheme
- **showVariance**: Display variance calculations
- **showPriorYear**: Include prior year line (gray, outline)
- **colorActual**: IBCS solid color for actuals (typically black)
- **colorPlan**: IBCS outline color for plan (typically gray)
- **colorFavorable/Unfavorable**: Variance colors
- **dataLabels**: Show/hide values on bars
- **legendPosition**: "top", "bottom", "left", "right", "none"

## Task: Create Financial Tables with ZebraBI Tables

### Step 1: Structure Financial Data

ZebraBI Tables work best with hierarchical financial data:

```
GL Account Hierarchy:
├── Revenue (Total)
│   ├── Product Sales
│   │   ├── Product A
│   │   └── Product B
│   └── Service Revenue
├── Cost of Goods Sold
│   ├── Materials
│   └── Labor
└── Net Income
```

### Step 2: Add ZebraBI Table Visual

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.1.0/schema.json",
  "name": "financial_variance_table",
  "position": {
    "x": 0,
    "y": 400,
    "z": 1000,
    "height": 300,
    "width": 850,
    "tabOrder": 2
  },
  "visual": {
    "visualType": "ZebraBITables98F88148E5424E949E69864664EE1860",
    "query": {
      "queryState": {
        "Rows": {
          "projections": [
            {
              "field": {
                "Column": {
                  "Expression": {
                    "SourceRef": {
                      "Entity": "[GL_Account]"
                    }
                  },
                  "Property": "[Account Name]"
                }
              },
              "queryRef": "[GL_Account].[Account Name]",
              "nativeQueryRef": "[Account Name]",
              "active": true
            }
          ]
        },
        "Values": {
          "projections": [
            {
              "field": {
                "Measure": {
                  "Expression": {
                    "SourceRef": {
                      "Entity": "[Finance]"
                    }
                  },
                  "Property": "[Actual]"
                }
              },
              "queryRef": "[Finance].[Actual]",
              "nativeQueryRef": "[Actual]"
            },
            {
              "field": {
                "Measure": {
                  "Expression": {
                    "SourceRef": {
                      "Entity": "[Finance]"
                    }
                  },
                  "Property": "[Plan]"
                }
              },
              "queryRef": "[Finance].[Plan]",
              "nativeQueryRef": "[Plan]"
            },
            {
              "field": {
                "Measure": {
                  "Expression": {
                    "SourceRef": {
                      "Entity": "[Finance]"
                    }
                  },
                  "Property": "[Variance]"
                }
              },
              "queryRef": "[Finance].[Variance]",
              "nativeQueryRef": "[Variance]"
            }
          ]
        }
      }
    },
    "objects": {
      "table": [
        {
          "properties": {
            "ibcsCompliant": true,
            "showVarianceIndicators": true,
            "colorFavorable": "#00B050",
            "colorUnfavorable": "#FF0000",
            "columnWidth": "auto",
            "fontSize": 11,
            "rowHeight": 24,
            "alternateRowColor": true,
            "frozenColumns": 1
          }
        }
      ]
    }
  }
}
```

### Step 3: Configure Table Properties

ZebraBI Tables support:

- **ibcsCompliant**: Apply IBCS styling
- **showVarianceIndicators**: Display variance symbols (↑/↓/→)
- **colorFavorable/Unfavorable**: IBCS variance colors
- **showMiniCharts**: Include sparklines in cells
- **columnWidth**: "auto", "fixed", or pixel values
- **frozenColumns**: Number of columns to freeze (for row headers)
- **alternateRowColor**: Zebra striping for readability
- **fontSize**, **rowHeight**: Typography settings
- **hierarchyIndentation**: Indent child rows in hierarchies

## Relationship to Other Skills

- **powerbi-semantic-model**: Use for DAX measure calculations, calendar tables, and hierarchy design required by IBCS dashboards.
- **powerbi-report**: Use for standard native visuals (if needed alongside IBCS visuals).
- **fabric-cli**: Use for deploying IBCS dashboards to Fabric workspaces.

## Post-development: Validate IBCS Compliance

After creating an IBCS dashboard, verify:

1. **Color consistency** — All variance indicators follow IBCS scheme (red=unfavorable, green=favorable)
2. **Symbol standardization** — Hichert boxes, waterfall charts, and variance symbols are consistent
3. **Data accuracy** — Measures and calculations match expected business logic
4. **Performance** — Charts render smoothly with typical data volumes
5. **Accessibility** — Sufficient contrast ratios, readable fonts, alt text for visuals
6. **Drill-through capability** — Links to detailed pages or external reports if needed

## Error Handling

- **Custom visual not found**: Ensure ZebraBI visuals are installed in the workspace and their GUIDs match in `visual.json`.
- **Field mapping errors**: Verify `Entity` (table name) and `Property` (column/measure name) match exactly (case-sensitive).
- **IBCS color not applied**: Check that `ibcsCompliant: true` is set and colors are in hex format (e.g., `#FF0000`).
- **Performance issues**: Reduce data volume in visuals using report-level or visual-level filters; consider aggregating data in the semantic model.
- **Export/print issues**: Ensure page size and visual positions allow for proper printing; test export to PDF.

## Examples & Best Practices

### Best Practice 1: Combine Multiple Visualization Types

Use different IBCS visuals together on one dashboard:
- **Top row**: KPI Cards showing main metrics (ZebraBI Cards)
- **Middle**: Variance/Hichert chart showing plan vs actual (ZebraBI Charts)
- **Bottom**: Detailed variance table by product/region (ZebraBI Tables)

This layering supports both executive overview and detail exploration.

### Best Practice 2: Progressive Disclosure

Use **bookmarks** in Power BI to toggle between:
- Summary view (high-level KPIs with ZebraBI Cards)
- Detail view (variance analysis with ZebraBI Charts and Tables)

### Best Practice 3: Drillable Hierarchies

Combine ZebraBI Tables with hierarchy dimensions to enable:
- Expand/collapse account hierarchies
- Drill from summary accounts to detail transactions
- Context-sensitive variance analysis

### Best Practice 4: Mobile Responsiveness

- Use smaller card sizes for mobile (ZebraBI Cards adapt well)
- Reduce table columns for mobile view (hide low-priority metrics)
- Test visual layout on multiple screen sizes

## References

**External resources**:
- [IBCS Official Standard](https://www.ibcs.com/) — International Business Communication Standards body
- [ZebraBI Documentation](https://zebrabi.com/pbi-help) — ZebraBI visuals documentation
- [Microsoft PBIR Format](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report) — PBIR/PBIP documentation
- [Power BI Custom Visuals](https://learn.microsoft.com/en-us/power-bi/developer/custom-visual-development-process) — Custom visual development guide

**Sample dashboard reference**: `assets/sample-reports-and-content/saas-sales-dashboard/` — Example SaaS sales dashboard using ZebraBI Cards, Charts, and Tables
