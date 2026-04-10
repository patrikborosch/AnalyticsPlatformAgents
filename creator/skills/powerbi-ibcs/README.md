# powerbi-ibcs Skill Documentation Index

## 📚 Complete Documentation Structure

This skill enables Copilot to help you create professional IBCS-compliant financial dashboards using ZebraBI visuals in Power BI.

### Main Skill Document
- **[SKILL.md](./SKILL.md)** — Complete skill guide
  - What is IBCS and why it matters
  - ZebraBI custom visuals (Cards, Charts, Tables)
  - Complete tasks with step-by-step instructions
  - Data model requirements
  - JSON configuration examples
  - Error handling and best practices
  - **Start here for comprehensive guidance**

### Reference Documents

#### 1. [IBCS Standard Reference](./references/ibcs-standard.md)
Quick reference for IBCS principles and standards.
- IBCS color scheme with hex codes
- Chart types (Hichert, Waterfall, Variance)
- Symbol conventions (↑ ↓ →)
- Typography rules
- Layout principles
- Variance calculation methods
- Compliance checklist
- **Use when**: You need to understand IBCS standards

#### 2. [ZebraBI Configuration Reference](./references/zebrabi-configuration.md)
Detailed configuration guide for each ZebraBI visual.
- Visual GUIDs and versions
- Field binding specifications
- Complete property documentation
- Configuration examples
- Troubleshooting guide
- **Use when**: You're configuring a specific visual

#### 3. [Quick Start Guide](./references/quick-start.md)
Step-by-step guide to create your first IBCS dashboard.
- 5-minute setup prerequisites
- Create semantic model with DAX
- Export as PBIP format
- Add ZebraBI Cards
- Add Hichert Charts
- Add Detail Tables
- Validation checklist
- **Use when**: You want to get started immediately

#### 4. [SaaS Dashboard Analysis](./references/saas-dashboard-analysis.md)
Analysis of the sample SaaS Sales Dashboard example.
- Dashboard composition and structure
- Custom visuals used (versions and GUIDs)
- Data model insights
- IBCS implementation details
- What makes it effective
- How to replicate it
- **Use when**: You want to understand the example dashboard

## 🎯 How to Use This Skill

### With GitHub Copilot CLI

Use this skill to get expert guidance on IBCS dashboarding:

```bash
# Ask Copilot about IBCS dashboards
copilot "Create a ZebraBI dashboard showing revenue vs plan with IBCS compliance"

# Get help with specific visuals
copilot "Configure a ZebraBI Cards visual showing KPI variance"

# Validate your work
copilot "Check this dashboard for IBCS standards compliance"
```

### Reading Path by Use Case

**I want to understand IBCS fundamentals**
1. Read: [SKILL.md - "What is IBCS?"](./SKILL.md#what-is-ibcs)
2. Reference: [ibcs-standard.md](./references/ibcs-standard.md)
3. Example: [SaaS Dashboard Analysis](./references/saas-dashboard-analysis.md)

**I want to create my first dashboard**
1. Follow: [Quick Start Guide](./references/quick-start.md)
2. Reference: [SKILL.md - Task sections](./SKILL.md#task-create-a-kpi-dashboard-with-zebrabi-cards)
3. Config: [ZebraBI Configuration Reference](./references/zebrabi-configuration.md)

**I need detailed configuration**
1. Reference: [zebrabi-configuration.md](./references/zebrabi-configuration.md)
2. Examples: [SKILL.md JSON examples](./SKILL.md#step-3-add-zebrabi-cards-visual)
3. Validate: Troubleshooting section

**I want to understand the example**
1. Read: [saas-dashboard-analysis.md](./references/saas-dashboard-analysis.md)
2. Open: `assets/sample-reports-and-content/saas-sales-dashboard/SaaS Sales dashboard.pbix`
3. Learn: Copy JSON patterns from the analysis

## 📊 Key Topics Covered

### Visual Types
- ✅ **ZebraBI Cards** — KPI visualization with trends
- ✅ **ZebraBI Charts** — Hichert, Waterfall, Variance analysis
- ✅ **ZebraBI Tables** — IBCS-compliant financial tables

### Technical Aspects
- ✅ PBIR JSON format and visual structure
- ✅ Data field bindings and entity/property references
- ✅ Custom visual GUIDs and resource packages
- ✅ Configuration properties and options
- ✅ Semantic model design for IBCS dashboards
- ✅ DAX measure examples

### Standards & Best Practices
- ✅ IBCS color scheme and compliance
- ✅ Chart type selection
- ✅ Symbol conventions
- ✅ Typography and layout rules
- ✅ Variance calculation methods
- ✅ Progressive disclosure pattern
- ✅ Mobile responsiveness

### Practical Guidance
- ✅ Step-by-step task workflows
- ✅ Complete JSON examples
- ✅ Error handling and troubleshooting
- ✅ Performance optimization
- ✅ Validation checklist
- ✅ Real-world examples

## 🔗 Related Skills

This skill complements other Power BI skills:

- **[powerbi-semantic-model](../../powerbi-semantic-model/)** — Create DAX measures and dimensions needed for IBCS dashboards
- **[powerbi-report](../../powerbi-report/)** — General report editing (standard visuals)
- **[fabric-cli](../../../fabric/skills/fabric-cli/)** — Deploy dashboards to Fabric workspaces

## 📖 Reading Recommendations

### For Business Users
1. [IBCS Standard Reference](./references/ibcs-standard.md) — Understand the standards
2. [SaaS Dashboard Analysis](./references/saas-dashboard-analysis.md) — See example
3. [Quick Start Guide](./references/quick-start.md) — Get started

### For Power BI Developers
1. [SKILL.md - Complete Guide](./SKILL.md) — Full technical documentation
2. [ZebraBI Configuration Reference](./references/zebrabi-configuration.md) — API reference
3. [Quick Start Guide](./references/quick-start.md) — Hands-on tutorial

### For Data Analysts
1. [SKILL.md - Data Model Requirements](./SKILL.md#data-model-requirements-for-ibcs-dashboards) — Design your data
2. [Quick Start Guide](./references/quick-start.md) — Build dashboards
3. [SaaS Dashboard Analysis](./references/saas-dashboard-analysis.md) — Analyze examples

## 💡 Quick Tips

- **Always use hex colors** (#RRGGBB format) for IBCS compliance
- **Enable ibcsCompliant: true** in your visual properties
- **Test on mobile** before deploying dashboard
- **Use frozen columns** in tables for better UX
- **Embed sparklines** in cards for trend context
- **Combine all three visuals** for complete dashboards
- **Validate field references** exactly (case-sensitive)

## 🆘 Troubleshooting

Common issues and solutions are documented in:
- **[SKILL.md - Error Handling](./SKILL.md#error-handling)**
- **[zebrabi-configuration.md - Troubleshooting](./references/zebrabi-configuration.md#troubleshooting)**
- **[quick-start.md - Common Issues](./references/quick-start.md#common-issues--solutions)**

## 📞 Support Resources

- [ZebraBI Official Help](https://zebrabi.com/pbi-help)
- [IBCS Official Standard](https://www.ibcs.com/)
- [Microsoft Power BI Documentation](https://learn.microsoft.com/en-us/power-bi/)
- [Power BI Custom Visuals Guide](https://learn.microsoft.com/en-us/power-bi/developer/custom-visual-development-process)

## 📝 Version History

- **v1.0** (2026-04-03) — Initial skill created
  - IBCS fundamentals
  - ZebraBI Cards, Charts, Tables
  - Complete JSON examples
  - Quick start guide
  - SaaS dashboard analysis

## ✅ Validation Checklist

Before using this skill for production dashboards:

- [ ] Reviewed IBCS Standard Reference
- [ ] Completed Quick Start Guide
- [ ] Studied ZebraBI Configuration Reference
- [ ] Analyzed SaaS Dashboard example
- [ ] Tested with sample data
- [ ] Validated IBCS compliance
- [ ] Tested mobile responsiveness
- [ ] Reviewed error handling section

---

**Last Updated**: 2026-04-03  
**Created By**: GitHub Copilot  
**Status**: Ready for use  
**Next Iteration**: Collect feedback from users and enhance with additional use cases
