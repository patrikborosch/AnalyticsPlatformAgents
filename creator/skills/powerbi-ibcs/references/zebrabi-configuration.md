# ZebraBI Visuals Configuration Reference

This document provides detailed configuration options for ZebraBI custom visuals used in Power BI PBIR format.

## ZebraBI Custom Visual GUIDs

When creating reports in PBIR format, use these GUIDs to reference ZebraBI visuals:

| Visual Name | GUID | Version (from sample) |
|---|---|---|
| ZebraBI Cards | `zebraBiCards8085D508EB994C8081CA47C85ABD7C26` | 7.4.0.14906484778 |
| ZebraBI Charts | `waterfall0221D8FBE40445C1A4E598AA8EF8B506` | 7.8.1.22097493993 |
| ZebraBI Tables | `ZebraBITables98F88148E5424E949E69864664EE1860` | 7.8.0.22130630320 |

**Note**: These GUIDs may change with ZebraBI updates. Always verify against your installed versions.

## ZebraBI Cards Configuration

### Visual Type Identifier
```json
"visualType": "zebraBiCards"
```

### Data Field Bindings

ZebraBI Cards accepts the following field projections in the query:

#### Values Projection (Required)
Main metric value to display on the card.

```json
{
  "field": {
    "Measure": {
      "Expression": {
        "SourceRef": {
          "Entity": "[TableName]"
        }
      },
      "Property": "[MeasureName]"
    }
  },
  "queryRef": "[TableName].[MeasureName]",
  "nativeQueryRef": "[MeasureName]",
  "active": true,
  "inUse": true
}
```

#### Breakout Projection (Optional)
Dimension to break down the metric (creates multiple cards).

```json
{
  "field": {
    "Column": {
      "Expression": {
        "SourceRef": {
          "Entity": "[DimensionTable]"
        }
      },
      "Property": "[DimensionColumn]"
    }
  },
  "queryRef": "[DimensionTable].[DimensionColumn]",
  "nativeQueryRef": "[DimensionColumn]",
  "active": true
}
```

### Configuration Properties

ZebraBI Cards support these properties in the `objects` section:

```json
"objects": {
  "card": [
    {
      "properties": {
        "cardType": 1,
        "showTrendIndicator": true,
        "showMiniChart": true,
        "showVarianceAmount": true,
        "showVariancePercent": true,
        "ibcsCompliant": true,
        "colorForFavorable": "#00B050",
        "colorForUnfavorable": "#FF0000",
        "colorForNeutral": "#000000",
        "decimalPlaces": 2,
        "suffix": "$",
        "prefix": "",
        "fontSize": 24,
        "title": "Total Revenue",
        "showTitle": true
      }
    }
  ]
}
```

#### Property Descriptions

| Property | Type | Values | Default | Notes |
|----------|------|--------|---------|-------|
| `cardType` | int | 0=Single Metric, 1=Actual vs Target, 2=Trend | 1 | Determines card layout |
| `showTrendIndicator` | bool | true/false | true | Displays ↑/↓/→ arrow |
| `showMiniChart` | bool | true/false | true | Embeds sparkline chart |
| `showVarianceAmount` | bool | true/false | true | Shows variance value |
| `showVariancePercent` | bool | true/false | true | Shows variance % |
| `ibcsCompliant` | bool | true/false | false | Applies IBCS color scheme |
| `colorForFavorable` | hex | #RRGGBB | #00B050 | Green for positive variance |
| `colorForUnfavorable` | hex | #RRGGBB | #FF0000 | Red for negative variance |
| `colorForNeutral` | hex | #RRGGBB | #000000 | Black for no variance |
| `decimalPlaces` | int | 0-4 | 2 | Number format precision |
| `suffix` | string | Any | "$" | E.g., "%", "K", "M" |
| `prefix` | string | Any | "" | E.g., "$", "€" |
| `fontSize` | int | 8-48 | 24 | Card value font size |
| `title` | string | Any | "" | Custom card title |
| `showTitle` | bool | true/false | true | Display card title |

## ZebraBI Charts Configuration

### Visual Type Identifier
```json
"visualType": "waterfall0221D8FBE40445C1A4E598AA8EF8B506"
```

### Data Field Bindings

ZebraBI Charts accepts:

#### Category Projection
X-axis dimension (required for axis-based charts).

```json
{
  "field": {
    "Column": {
      "Expression": {
        "SourceRef": {
          "Entity": "[TimeDimension]"
        }
      },
      "Property": "[Month]"
    }
  },
  "queryRef": "[TimeDimension].[Month]",
  "nativeQueryRef": "[Month]",
  "active": true
}
```

#### Y Projections
One or more measures (values to chart).

```json
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
```

#### Play Axis (Optional)
Dimension for animation over time.

```json
{
  "field": {
    "Column": {
      "Expression": {
        "SourceRef": {
          "Entity": "[TimeDimension]"
        }
      },
      "Property": "[Year]"
    }
  },
  "queryRef": "[TimeDimension].[Year]",
  "nativeQueryRef": "[Year]",
  "active": true
}
```

### Configuration Properties

```json
"objects": {
  "chart": [
    {
      "properties": {
        "chartType": "hichert",
        "ibcsCompliant": true,
        "showVariance": true,
        "showPriorYear": true,
        "showDataLabels": true,
        "legendPosition": "top",
        "colorActual": "#000000",
        "colorPlan": "#646464",
        "colorPriorYear": "#C8C8C8",
        "colorFavorable": "#00B050",
        "colorUnfavorable": "#FF0000",
        "useThousandsSeparator": true,
        "decimalPlaces": 0
      }
    }
  ]
}
```

#### Property Descriptions

| Property | Type | Values | Default | Notes |
|----------|------|--------|---------|-------|
| `chartType` | string | "waterfall", "hichert", "variance", "combo" | "column" | Chart visualization style |
| `ibcsCompliant` | bool | true/false | false | Apply IBCS standards |
| `showVariance` | bool | true/false | true | Display variance indicators |
| `showPriorYear` | bool | true/false | false | Include prior year comparison |
| `showDataLabels` | bool | true/false | true | Show values on bars |
| `legendPosition` | string | "top", "bottom", "left", "right", "none" | "top" | Legend placement |
| `colorActual` | hex | #RRGGBB | #000000 | Actual value color (black) |
| `colorPlan` | hex | #RRGGBB | #646464 | Plan value color (dark gray) |
| `colorPriorYear` | hex | #RRGGBB | #C8C8C8 | Prior year color (light gray) |
| `colorFavorable` | hex | #RRGGBB | #00B050 | Favorable variance (green) |
| `colorUnfavorable` | hex | #RRGGBB | #FF0000 | Unfavorable variance (red) |
| `useThousandsSeparator` | bool | true/false | true | Format numbers (1,000 vs 1000) |
| `decimalPlaces` | int | 0-4 | 0 | Number format precision |

### Chart Type Details

#### Waterfall Chart
Shows composition with bridges between values.
- **Best for**: Budget → Actuals, revenue breakdowns, cumulative flows
- **Requires**: One category, one or more measures
- **Colors**: Different segment for each measure or step

#### Hichert Chart
Compares three data series (actual, plan, prior year) in boxes.
- **Best for**: Multi-dimensional variance analysis
- **Requires**: One category, three measures (actual, plan, prior year)
- **Colors**: Solid (actual), outline (plan), gray (prior year)

#### Variance Chart
Highlights differences between two measures.
- **Best for**: Plan vs Actual with variance focus
- **Requires**: One category, two or more measures
- **Colors**: Green (favorable), Red (unfavorable), Gray (neutral)

#### Combo Chart
Combination of chart types (bars, lines, areas).
- **Best for**: Multiple measures with different scales
- **Requires**: One or more categories, multiple measures
- **Colors**: Different color per measure

## ZebraBI Tables Configuration

### Visual Type Identifier
```json
"visualType": "ZebraBITables98F88148E5424E949E69864664EE1860"
```

### Data Field Bindings

ZebraBI Tables accepts:

#### Rows Projection
Dimension for rows (required).

```json
{
  "field": {
    "Column": {
      "Expression": {
        "SourceRef": {
          "Entity": "[GLAccount]"
        }
      },
      "Property": "[Account Name]"
    }
  },
  "queryRef": "[GLAccount].[Account Name]",
  "nativeQueryRef": "[Account Name]",
  "active": true
}
```

#### Values Projections
Multiple measures for table columns.

```json
[
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
```

### Configuration Properties

```json
"objects": {
  "table": [
    {
      "properties": {
        "ibcsCompliant": true,
        "showVarianceIndicators": true,
        "colorFavorable": "#00B050",
        "colorUnfavorable": "#FF0000",
        "showMiniCharts": true,
        "columnWidth": "auto",
        "fontSize": 11,
        "rowHeight": 24,
        "alternateRowColor": true,
        "alternateRowColorValue": "#F5F5F5",
        "frozenColumns": 1,
        "headerFontSize": 12,
        "headerBackgroundColor": "#D9D9D9",
        "enableSorting": true,
        "enableFiltering": true,
        "maxRows": 1000
      }
    }
  ]
}
```

#### Property Descriptions

| Property | Type | Values | Default | Notes |
|----------|------|--------|---------|-------|
| `ibcsCompliant` | bool | true/false | false | Apply IBCS styling |
| `showVarianceIndicators` | bool | true/false | true | Display ↑/↓/→ symbols |
| `colorFavorable` | hex | #RRGGBB | #00B050 | Green for favorable |
| `colorUnfavorable` | hex | #RRGGBB | #FF0000 | Red for unfavorable |
| `showMiniCharts` | bool | true/false | true | Embed sparklines in cells |
| `columnWidth` | string | "auto", "fixed", pixels | "auto" | Column sizing |
| `fontSize` | int | 8-16 | 11 | Data cell font size |
| `rowHeight` | int | 16-40 | 24 | Row height in pixels |
| `alternateRowColor` | bool | true/false | true | Zebra striping |
| `alternateRowColorValue` | hex | #RRGGBB | #F5F5F5 | Stripe background color |
| `frozenColumns` | int | 0-3 | 1 | Frozen header columns |
| `headerFontSize` | int | 8-16 | 12 | Header font size |
| `headerBackgroundColor` | hex | #RRGGBB | #D9D9D9 | Header background |
| `enableSorting` | bool | true/false | true | Allow column sorting |
| `enableFiltering` | bool | true/false | true | Show filter icons |
| `maxRows` | int | 100-10000 | 1000 | Maximum rows to display |

## Common Configuration Examples

### Example 1: KPI Card with Variance Percentage

```json
{
  "name": "kpi_card_variance",
  "visual": {
    "visualType": "zebraBiCards",
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
            "decimalPlaces": 1,
            "suffix": "%",
            "fontSize": 28,
            "title": "Revenue vs Target"
          }
        }
      ]
    }
  }
}
```

### Example 2: Hichert Chart (Actual vs Plan vs Prior Year)

```json
{
  "name": "hichert_variance_chart",
  "visual": {
    "visualType": "waterfall0221D8FBE40445C1A4E598AA8EF8B506",
    "objects": {
      "chart": [
        {
          "properties": {
            "chartType": "hichert",
            "ibcsCompliant": true,
            "showVariance": true,
            "showPriorYear": true,
            "showDataLabels": true,
            "legendPosition": "bottom",
            "colorActual": "#000000",
            "colorPlan": "#646464",
            "colorPriorYear": "#C8C8C8",
            "colorFavorable": "#00B050",
            "colorUnfavorable": "#FF0000",
            "useThousandsSeparator": true,
            "decimalPlaces": 0
          }
        }
      ]
    }
  }
}
```

### Example 3: IBCS Financial Table

```json
{
  "name": "financial_table",
  "visual": {
    "visualType": "ZebraBITables98F88148E5424E949E69864664EE1860",
    "objects": {
      "table": [
        {
          "properties": {
            "ibcsCompliant": true,
            "showVarianceIndicators": true,
            "colorFavorable": "#00B050",
            "colorUnfavorable": "#FF0000",
            "showMiniCharts": true,
            "fontSize": 10,
            "rowHeight": 22,
            "alternateRowColor": true,
            "frozenColumns": 1,
            "headerFontSize": 11,
            "headerBackgroundColor": "#E7E6E6",
            "enableSorting": false,
            "enableFiltering": false,
            "maxRows": 500
          }
        }
      ]
    }
  }
}
```

## Troubleshooting

### Custom Visual Not Found Error
- **Cause**: GUID mismatch or visual not installed in workspace
- **Solution**: Verify GUID matches your ZebraBI version; ensure visual is installed

### Field References Invalid
- **Cause**: Table or measure name doesn't match semantic model exactly
- **Solution**: Check Entity and Property are case-sensitive and match exact names

### Colors Not Applying
- **Cause**: `ibcsCompliant` set to false or hex format incorrect
- **Solution**: Set `ibcsCompliant: true` and use valid hex (e.g., `#FF0000`)

### Performance Issues
- **Cause**: Too many rows or complex calculations
- **Solution**: Reduce data volume with filters, pre-aggregate in model, reduce `maxRows`

## References

- [ZebraBI Official Documentation](https://zebrabi.com/pbi-help)
- [Power BI Custom Visuals API](https://learn.microsoft.com/en-us/power-bi/developer/custom-visual-development-process)
- [SaaS Sales Dashboard Example](../../../assets/sample-reports-and-content/saas-sales-dashboard)
