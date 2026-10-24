#!/bin/bash
set -euo pipefail

CLUSTER_URI="${1:?Usage: $0 <cluster_uri> <database> [blob_uri]}"
DB="${2:?Usage: $0 <cluster_uri> <database> [blob_uri]}"
BLOB_URI="${3:-}"

# mktemp, not a fixed path: two concurrent runs would otherwise overwrite each
# other's request body.
BODY_FILE="$(mktemp)"
trap 'rm -f "${BODY_FILE}"' EXIT

# jq builds the body. KQL commands carry embedded double quotes (ingestion mappings,
# policy JSON), so interpolating one into a JSON string emits invalid JSON.
kusto() {
  local endpoint="$1" command="$2"
  jq -n --arg db "${DB}" --arg csl "${command}" '{db: $db, csl: $csl}' > "${BODY_FILE}"
  az rest --method POST \
    --url "${CLUSTER_URI}/v1/rest/${endpoint}" \
    --resource "https://kusto.kusto.windows.net" \
    --headers "Content-Type=application/json" \
    --body "@${BODY_FILE}" \
    | jq '.Tables[0].Rows'
}

echo "=== Creating table ==="
kusto mgmt ".create-merge table Events (Timestamp: datetime, EventType: string, UserId: string, Properties: dynamic, Duration: real)"

echo "=== Creating CSV mapping ==="
kusto mgmt ".create-or-alter table Events ingestion csv mapping 'EventsCsvMapping' '[{\"column\":\"Timestamp\",\"datatype\":\"datetime\",\"ordinal\":0},{\"column\":\"EventType\",\"datatype\":\"string\",\"ordinal\":1},{\"column\":\"UserId\",\"datatype\":\"string\",\"ordinal\":2},{\"column\":\"Properties\",\"datatype\":\"dynamic\",\"ordinal\":3},{\"column\":\"Duration\",\"datatype\":\"real\",\"ordinal\":4}]'"

if [ -n "${BLOB_URI}" ]; then
  echo "=== Ingesting data ==="
  kusto mgmt ".ingest into table Events (h'${BLOB_URI};impersonate') with (format='csv', ingestionMappingReference='EventsCsvMapping', ignoreFirstRecord=true)"
  echo "Ingestion command submitted."
else
  echo "No blob URI provided - skipping ingestion."
fi

echo "=== Verifying ==="
kusto query "Events | count"
echo "Done."
