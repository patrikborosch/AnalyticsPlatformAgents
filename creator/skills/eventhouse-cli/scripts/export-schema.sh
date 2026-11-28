#!/bin/bash
set -euo pipefail

CLUSTER_URI="${1:?Usage: $0 <cluster_uri> <database> [output_file]}"
DB="${2:?Usage: $0 <cluster_uri> <database> [output_file]}"
OUTPUT="${3:-schema_export_$(date +%Y%m%d).kql}"

BODY_FILE="$(mktemp)"
trap 'rm -f "${BODY_FILE}"' EXIT

echo "=== Exporting schema for ${DB} ==="
jq -n --arg db "${DB}" --arg csl ".show database ${DB} schema as csl script" \
  '{db: $db, csl: $csl}' > "${BODY_FILE}"
az rest --method POST \
  --url "${CLUSTER_URI}/v1/rest/mgmt" \
  --resource "https://kusto.kusto.windows.net" \
  --headers "Content-Type=application/json" \
  --body "@${BODY_FILE}" \
  | jq -r '.Tables[0].Rows[][0]' > "${OUTPUT}"
echo "Schema exported to ${OUTPUT}"
