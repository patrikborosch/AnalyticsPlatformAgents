#!/bin/bash
set -euo pipefail

CLUSTER_URI="${1:?Usage: $0 <cluster_uri> <database> <table> <retention_days> <cache_days>}"
DB="${2:?Usage: $0 <cluster_uri> <database> <table> <retention_days> <cache_days>}"
TABLE="${3:?Usage: $0 <cluster_uri> <database> <table> <retention_days> <cache_days>}"
RETENTION_DAYS="${4:?Usage: $0 <cluster_uri> <database> <table> <retention_days> <cache_days>}"
CACHE_DAYS="${5:?Usage: $0 <cluster_uri> <database> <table> <retention_days> <cache_days>}"

BODY_FILE="$(mktemp)"
trap 'rm -f "${BODY_FILE}"' EXIT

# jq builds the body. The retention policy is itself a JSON document, so interpolating
# it into a JSON string emits invalid JSON.
#
# `.show` is a management command even with a trailing `| project`, so every call here
# goes to /v1/rest/mgmt. /v1/rest/query is only for expressions such as `Events | count`.
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

echo "=== Setting retention to ${RETENTION_DAYS}d for ${TABLE} ==="
kusto ".alter table ${TABLE} policy retention '{\"SoftDeletePeriod\":\"${RETENTION_DAYS}.00:00:00\",\"Recoverability\":\"Enabled\"}'"

echo "=== Setting hot cache to ${CACHE_DAYS}d for ${TABLE} ==="
kusto ".alter table ${TABLE} policy caching hot = ${CACHE_DAYS}d"

echo "=== Verifying ==="
kusto ".show table ${TABLE} policy retention"
kusto ".show table ${TABLE} policy caching"

echo "Done."
