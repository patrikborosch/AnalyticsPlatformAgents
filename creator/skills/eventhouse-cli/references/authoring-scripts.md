# Eventhouse Authoring Scripts

Runnable Bash and PowerShell scripts for common Eventhouse authoring operations via
`az rest`. **Execute these; do not read them into context.** Only their output costs
tokens, and a pre-written script is more reliable than regenerating one per run.

Every script authenticates through `az`, targets the Kusto endpoints
(`<cluster_uri>/v1/rest/mgmt` and `/v1/rest/query`), and prints the rows it gets back.
All of them stop at the first failed call and print a usage line when a required argument
is missing. Management commands -- anything starting with `.`, including `.show ... |
project` -- go to `/mgmt`; `/query` is only for expressions such as `Events | count`.

**Bash scripts require `jq`** (`apt-get install jq`, `brew install jq`, or
`winget install jqlang.jq`). They use it for two things: reading `.Tables[0].Rows` out of
the response, and building the request body with `jq -n --arg`, which JSON-escapes the KQL
command. That escaping is not optional -- ingestion mappings and policy documents contain
double quotes, and interpolating one into a JSON string produces a body `az rest` rejects.
The PowerShell scripts get the same guarantee from `ConvertTo-Json`.

## Contents

- [Bash](#bash)
- [PowerShell](#powershell)
- [Adapting a script](#adapting-a-script)

## Bash

**`create-table-and-ingest.sh`** — create the `Events` table with a CSV mapping, then
optionally ingest a blob and report the row count.

```bash
bash scripts/create-table-and-ingest.sh <cluster_uri> <database> [blob_uri]
```

**`deploy-schema.sh`** — submit a `.kql` file as a single
`.execute database script with (ThrowOnErrors=true)`, then list tables, functions and
materialized views. The whole file goes in one command rather than line by line, because a
script exported by `export-schema.sh` contains multiline function bodies and policies that
per-line execution would cut in half. `ThrowOnErrors` stops at the first bad command
instead of reporting partial success. Use `.create-merge` commands so a re-run is
idempotent.

```bash
bash scripts/deploy-schema.sh <cluster_uri> <database> <schema_file>
```

**`export-schema.sh`** — write the whole database schema out as a CSL script. Its output is
exactly what `deploy-schema.sh` takes, so export and redeploy round-trip.

```bash
bash scripts/export-schema.sh <cluster_uri> <database> [output_file]
```

**`set-policies.sh`** — set retention and hot-cache policies on one table, then read both
policies back.

```bash
bash scripts/set-policies.sh <cluster_uri> <database> <table> <retention_days> <cache_days>
```

## PowerShell

**`create-table-and-ingest.ps1`** — the Bash script above, for pwsh.

```powershell
pwsh scripts/create-table-and-ingest.ps1 -ClusterUri <uri> -Database <db> [-BlobUri <uri>]
```

**`deploy-schema.ps1`** — the schema deployment above, for pwsh.

```powershell
pwsh scripts/deploy-schema.ps1 -ClusterUri <uri> -Database <db> -SchemaFile <path>
```

## Adapting a script

The table name, column set and mapping in the create-and-ingest scripts are worked
examples. When the request names a different table or schema, copy the script, edit the
`.create-merge` and mapping commands, and run the copy. The `kusto` helper (Bash) and
`Invoke-KustoMgmt` (PowerShell) inside each one is the pattern to reuse for any other
management command.
