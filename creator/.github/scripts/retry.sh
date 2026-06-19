#!/usr/bin/env bash
# Shared bounded-retry helper for CI steps that wrap transient network ops
# (pip / npm / choco install, az login, az keyvault secret show, ...).
#
# Usage:
#   set -euo pipefail
#   source "${GITHUB_WORKSPACE}/.github/scripts/retry.sh"
#   retry pip install foo
#   TOKEN=$(retry az keyvault secret show --vault-name "$KV" --name FOO --query value -o tsv)
#
# Behaviour:
#   3 attempts total with 5s then 10s sleep between failures (no sleep
#   after the final failure -- the wrapped command's exit code is returned
#   immediately). Returns 0 on first success; on exhaustion returns the
#   wrapped command's last non-zero exit code so callers can branch on the
#   actual failure mode (e.g. distinguish a 401 from a network timeout).
#   Emits ::warning:: per failed attempt on stderr so the step log shows
#   retry progression without polluting stdout-captured output.
#
# Output-capture caveat:
#   When wrapping a command whose stdout is captured (`X=$(retry cmd ...)`)
#   or redirected to a file (`retry cmd ... > file`), the wrapped command
#   must write its output atomically -- i.e. produce nothing on failure, OR
#   produce the full payload only on the successful attempt. In practice
#   `az keyvault secret show --query value -o tsv` and `az ... --output tsv`
#   satisfy this (they emit value bytes only after the API call resolves),
#   which is why the call sites in this repo use them safely. Future
#   contributors wrapping a streaming command (e.g. `curl` without
#   `--output-dir` semantics) should write to a temp file per attempt
#   instead, then rename on success.
#
# Single shared retry helper sourced by every CI step that wraps a transient
# network operation. Keeping one definition avoids drift between call sites
# (any future tweak -- jitter, longer backoff, structured logging, max-attempts
# -- only edits this file).

retry() {
  local max=3 delay=5 attempt=1 rc=0
  while true; do
    if "$@"; then return 0; fi
    rc=$?
    if [ "$attempt" -ge "$max" ]; then return "$rc"; fi
    echo "::warning::Command failed (attempt ${attempt}/${max}, rc=${rc}); retrying in ${delay}s: $*" >&2
    sleep "$delay"
    delay=$((delay * 2))
    attempt=$((attempt + 1))
  done
}
