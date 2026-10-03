#!/bin/bash
set -euo pipefail

CLUSTER_URI="${1:?Usage: $0 <cluster_uri> <database> <schema_file>}"
DB="${2:?Usage: $0 <cluster_uri> <database> <schema_file>}"
SCHEMA_FILE="${3:?Usage: $0 <cluster_uri> <database> <schema_file>}"

[ -f "${SCHEMA_FILE}" ] && [ -r "${SCHEMA_FILE}" ] || {
  echo "Cannot read schema file: ${SCHEMA_FILE}" >&2
  exit 1
}

BODY_FILE="$(mktemp)"
trap 'rm -f "${BODY_FILE}"' EXIT

# jq builds the body. A schema file holds real KQL -- ingestion mappings, retention
# policies, docstrings -- which carry double quotes and backslashes, so interpolating
# it into a JSON string emits invalid JSON.
kusto() {
  local command="$1"
  jq -n --arg db "${DB}" --arg csl "${command}" '{db: $db, csl: $csl}' > "${BODY_FILE}"
  az rest --method POST \
    --url "${CLUSTER_URI}/v1/rest/mgmt" \
    --resource "https://kusto.kusto.windows.net" \
    --headers "Content-Type=application/json" \
    --body "@${BODY_FILE}" \
    | jq '.Tables[0].Rows'
}

# The whole file goes in one `.execute database script`, not line by line. A script
# produced by `.show database schema as csl script` contains multiline function bodies
# and policies, so splitting on newlines would cut valid commands in half.
# ThrowOnErrors stops at the first bad command instead of reporting partial success.
echo "=== Deploying schema from ${SCHEMA_FILE} ==="
jq -n --arg db "${DB}" --rawfile script "${SCHEMA_FILE}" \
  '{db: $db, csl: (".execute database script with (ThrowOnErrors=true) <|\n" + $script)}' \
  > "${BODY_FILE}"
az rest --method POST \
  --url "${CLUSTER_URI}/v1/rest/mgmt" \
  --resource "https://kusto.kusto.windows.net" \
  --headers "Content-Type=application/json" \
  --body "@${BODY_FILE}" \
  | jq '.Tables[0].Rows'

# `.show` is a management command even with a trailing `| project`, so these go to
# /v1/rest/mgmt. /v1/rest/query is for expressions such as `Events | count`.
echo "=== Verifying deployment ==="
kusto ".show tables details | project TableName, TotalRowCount"
kusto ".show functions | project Name, Folder"
kusto ".show materialized-views | project Name, IsEnabled, IsHealthy"

echo "Schema deployment complete."
