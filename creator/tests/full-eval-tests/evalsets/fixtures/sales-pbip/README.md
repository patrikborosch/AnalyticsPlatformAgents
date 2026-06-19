# sales-pbip — Minimal PBIP Fixture for Power BI Report Evals

Self-contained PBIP project consumed by the Power BI report eval plans
(`eval-powerbi-report-authoring.md`, `eval-powerbi-report-management.md`).

## What this fixture is

- A **minimal but valid** Power BI Project (PBIP) with one semantic model
  (`sales.SemanticModel`) and one bound report (`sales.Report`).
- Designed to be **uploaded as-is** to a Fabric workspace via the Fabric REST
  API (used by `powerbi-report-management` skill), AND to be **read/modified as
  local files** (used by `powerbi-report-authoring` skill).

## Contents

| Item | Detail |
|---|---|
| Semantic model | `sales.SemanticModel` — Import mode, one table `Sales` with 5 inline rows, 2 measures (`Total Revenue`, `Total Quantity`) |
| Report | `sales.Report` — one page `Overview` with one card visual bound to `[Total Revenue]` |
| Storage mode | **Import** with `#table()` inline rows — zero external data dependencies, fully parallel-safe |

## Why Import (not Direct Lake)?

The eval plans here test report **authoring** and **report-item CRUD** — they do
not test Direct Lake binding semantics. Import mode keeps the fixture
self-contained: no `{{LAKEHOUSE}}` Delta tables to provision, no OneLake paths
to substitute, no cross-plan data isolation risk. If a future eval plan needs
Direct Lake specifically, it should create its own fixture or extend this one.

## Why `byPath` in `definition.pbir`?

The local file uses `"byPath": { "path": "../sales.SemanticModel" }` so it
matches what a real on-disk PBIP looks like and is usable by Power BI Desktop /
the PBIR authoring CLI.

When uploading to Fabric, the Fabric REST API requires `byConnection` instead
(see `common/ITEM-DEFINITIONS-CORE.md` — *"Fabric REST API only supports
`byConnection` references (not `byPath`)"*). The `powerbi-report-management`
skill is responsible for rewriting `definition.pbir` to a `byConnection` form
that points at the deployed semantic model item ID before POSTing the report
definition.

## How plans reach this fixture

The eval runner exposes `tests/full-eval-tests/evalsets/` as a Windows junction
inside each per-plan working directory, so plans reference it as a relative
path:

```
./evalsets/fixtures/sales-pbip/
```

## Layout

```
sales-pbip/
├── README.md                          (this file)
├── sales.pbip                         (PBIP root project file)
├── sales.SemanticModel/
│   ├── definition.pbism
│   └── definition/
│       ├── database.tmdl
│       ├── model.tmdl
│       └── tables/
│           └── Sales.tmdl
└── sales.Report/
    ├── definition.pbir                (byPath — rewrite to byConnection on upload)
    └── definition/
        ├── report.json
        ├── version.json
        └── pages/
            ├── pages.json
            └── overview/
                ├── page.json
                └── visuals/
                    └── total-revenue/
                        └── visual.json
```
