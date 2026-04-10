# Quick Start: Creating IBCS Dashboards with ZebraBI

This guide walks you through creating your first IBCS dashboard using ZebraBI visuals in Power BI.

## Prerequisites

- Power BI Desktop (latest version)
- [ZebraBI visuals installed](https://zebrabi.com/pbi-help) in your Power BI instance
- Basic understanding of Power BI data modeling (measures, dimensions)
- Familiarity with PBIR (Power BI Report) format

## 5-Minute Setup

### Step 1: Prepare Your Data Model

Ensure your semantic model includes:

```dax
-- In your semantic model, create these measures:

Total Sales = SUM(Sales[Amount])

Sales vs Plan = [Total Sales] - [Sales Plan]

Sales Variance % = DIVIDE([Sales vs Plan], [Sales Plan], 0)

Sales Status = IF([Sales vs Plan] >= 0, "Favorable", "Unfavorable")
```

And these dimensions:
- `Time[Month]`, `Time[Year]` — For time-based analysis
- `Product[Category]`, `Product[Name]` — For breakdowns
- A `Calendar` table with date hierarchy

### Step 2: Export Semantic Model as PBIP

```bash
# In Power BI Desktop, save as PBIP project:
File > Save As > Choose "Power BI Project" format
```

This creates a folder structure like:
```
MyProject/
├── MyProject.SemanticModel/
│   ├── definition/
│   └── tables/
└── MyProject.Report/
    ├── definition/
    └── StaticResources/
```

### Step 3: Create Report Pages and Visuals

Navigate to the `MyProject.Report/definition/pages/` folder and create page structure:

```
mainPage/
├── page.json
└── visuals/
    ├── kpi-revenue/
    │   └── visual.json
    ├── variance-chart/
    │   └── visual.json
    └── detail-table/
        └── visual.json
```

### Step 4: Add Your First ZebraBI Visual (KPI Card)

Create `kpi-revenue/visual.json`:

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.1.0/schema.json",
  "name": "kpi_revenue",
  "position": {
    "x": 0,
    "y": 0,
    "z": 1000,
    "height": 180,
    "width": 250,
    "tabOrder": 0
  },
  "visual": {
    "visualType": "zebraBiCards8085D508EB994C8081CA47C85ABD7C26",
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
            },
            {
              "field": {
                "Measure": {
                  "Expression": {
                    "SourceRef": {
                      "Entity": "[Sales]"
                    }
                  },
                  "Property": "[Sales vs Plan]"
                }
              },
              "queryRef": "[Sales].[Sales vs Plan]",
              "nativeQueryRef": "[Sales vs Plan]",
              "active": true
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
            "showVariancePercent": true,
            "ibcsCompliant": true,
            "colorForFavorable": "#00B050",
            "colorForUnfavorable": "#FF0000",
            "decimalPlaces": 0,
            "suffix": "$",
            "fontSize": 28,
            "title": "Total Sales"
          }
        }
      ]
    }
  }
}
```

### Step 5: Add a Hichert Chart for Variance Analysis

Create `variance-chart/visual.json`:

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.1.0/schema.json",
  "name": "hichert_variance",
  "position": {
    "x": 250,
    "y": 0,
    "z": 1000,
    "height": 400,
    "width": 500,
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
                      "Entity": "[Product]"
                    }
                  },
                  "Property": "[Category]"
                }
              },
              "queryRef": "[Product].[Category]",
              "nativeQueryRef": "[Category]",
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
                  "Property": "[Total Sales]"
                }
              },
              "queryRef": "[Sales].[Total Sales]",
              "nativeQueryRef": "[Total Sales]"
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
            "showDataLabels": true,
            "colorActual": "#000000",
            "colorPlan": "#646464",
            "colorFavorable": "#00B050",
            "colorUnfavorable": "#FF0000",
            "legendPosition": "bottom"
          }
        }
      ]
    }
  }
}
```

### Step 6: Add a Detail Table

Create `detail-table/visual.json`:

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.1.0/schema.json",
  "name": "detail_table",
  "position": {
    "x": 0,
    "y": 400,
    "z": 1000,
    "height": 300,
    "width": 750,
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
                      "Entity": "[Product]"
                    }
                  },
                  "Property": "[Name]"
                }
              },
              "queryRef": "[Product].[Name]",
              "nativeQueryRef": "[Name]",
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
                      "Entity": "[Sales]"
                    }
                  },
                  "Property": "[Total Sales]"
                }
              },
              "queryRef": "[Sales].[Total Sales]",
              "nativeQueryRef": "[Total Sales]"
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
            },
            {
              "field": {
                "Measure": {
                  "Expression": {
                    "SourceRef": {
                      "Entity": "[Sales]"
                    }
                  },
                  "Property": "[Sales vs Plan]"
                }
              },
              "queryRef": "[Sales].[Sales vs Plan]",
              "nativeQueryRef": "[Sales vs Plan]"
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
            "fontSize": 10,
            "rowHeight": 22,
            "alternateRowColor": true,
            "frozenColumns": 1,
            "headerFontSize": 11
          }
        }
      ]
    }
  }
}
```

### Step 7: Update Pages Index

Edit or create `mainPage/page.json` to include your visuals. Ensure `pages/pages.json` lists your page.

### Step 8: Open in Power BI Desktop

Open your PBIP folder in Power BI Desktop. The report should now display:
1. **KPI Card** showing Total Sales with variance
2. **Hichert Chart** showing Product Category variance
3. **Detail Table** showing line-by-line sales vs plan

## Validation Checklist

Before deploying your dashboard:

- [ ] All visuals load without errors
- [ ] KPI card displays trend indicator (↑/↓) correctly
- [ ] Hichert chart shows actual (black) and plan (gray) bars
- [ ] Table rows are color-coded (green/red for variance)
- [ ] Mobile preview looks acceptable
- [ ] Export to PDF works correctly
- [ ] Performance is acceptable (visuals render in <2 seconds)

## Common Issues & Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| "Custom visual not found" | GUID mismatch | Verify GUIDs match your ZebraBI installation |
| Visuals blank/no data | Field reference error | Check `Entity` and `Property` names (case-sensitive) |
| Cards showing wrong colors | `ibcsCompliant` false | Set `ibcsCompliant: true` in properties |
| Table not sorting | `enableSorting` disabled | Set `enableSorting: true` in table properties |
| Performance slow | Too much data | Add filters, reduce rows, pre-aggregate in model |

## Next Steps

1. **Customize colors** — Update hex colors in `colorFavorable`/`colorUnfavorable` to match your brand
2. **Add more pages** — Create additional pages for different departments or metrics
3. **Deploy to Fabric** — Use `fabric-cli` skill to deploy to workspace
4. **Add bookmarks** — Create bookmarks for different views (summary vs detail)
5. **Configure drills** — Set up drill-through to related pages for deeper analysis

## Resources

- [Full IBCS & ZebraBI Skill](../SKILL.md)
- [IBCS Standard Reference](./ibcs-standard.md)
- [ZebraBI Configuration Reference](./zebrabi-configuration.md)
- [SaaS Sales Dashboard Example](../../../assets/sample-reports-and-content/saas-sales-dashboard)
- [ZebraBI Help](https://zebrabi.com/pbi-help)
- [Microsoft PBIR Documentation](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-report)
