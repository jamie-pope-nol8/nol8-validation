#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$PROJECT_ROOT/config/demo.env"
SECRETS_FILE="$PROJECT_ROOT/.env"

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Config file not found: $CONFIG_FILE" >&2
  exit 2
fi

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "Secrets file not found: $SECRETS_FILE" >&2
  exit 2
fi

# shellcheck disable=SC1090
source "$CONFIG_FILE"

# shellcheck disable=SC1090
source "$SECRETS_FILE"

if [[ "${1:-}" == "--check" ]]; then
  CHECK_ONLY=true
  TARGET="${2:-}"
else
  CHECK_ONLY=false
  TARGET="${1:-}"
fi

case "$TARGET" in
  themis)
    ENDPOINT="${THEMIS_PROCESS_ENDPOINT:-}"
    TOKEN="${THEMIS_TOKEN:-}"
    ;;
  *)
    echo "Usage: $0 [--check] <themis>" >&2
    exit 2
    ;;
esac

if [[ -z "$ENDPOINT" ]]; then
  echo "Processing endpoint is not configured for target: $TARGET" >&2
  exit 2
fi

if [[ -z "$TOKEN" ]]; then
  echo "Token is not configured for target: $TARGET" >&2
  exit 2
fi

if [[ "$CHECK_ONLY" == true ]]; then
  exit 0
fi

REQUEST_FILE="$(mktemp)"
RESPONSE_FILE="$(mktemp)"

cleanup() {
  rm -f "$REQUEST_FILE" "$RESPONSE_FILE"
}
trap cleanup EXIT

cat > "$REQUEST_FILE"

if ! jq -e '.message | type == "string"' "$REQUEST_FILE" >/dev/null; then
  echo "Request must be JSON containing a string message." >&2
  exit 3
fi

set +e
CURL_METADATA="$(curl -sS \
  --connect-timeout 5 \
  --max-time 30 \
  -o "$RESPONSE_FILE" \
  -w '%{http_code} %{time_total}' \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  --data-binary "@$REQUEST_FILE" \
  "$ENDPOINT")"
CURL_STATUS=$?
set -e

if [[ "$CURL_STATUS" -ne 0 ]]; then
  echo "Processing endpoint request failed." >&2
  exit 5
fi

HTTP_CODE="${CURL_METADATA%% *}"
ELAPSED_SECONDS="${CURL_METADATA#* }"

if ! jq --arg http_status "$HTTP_CODE" \
  --arg elapsed_seconds "$ELAPSED_SECONDS" \
  '
  def remove_sensitive_fields:
    if type == "object" then
      with_entries(
        select(
          (.key | ascii_downcase | test("token|authorization|header|environment|secret"))
          | not
        )
        | .value |= remove_sensitive_fields
      )
    elif type == "array" then
      map(remove_sensitive_fields)
    else
      .
    end;

  ($http_status | tonumber) as $status
  | {
      http_status: $status,
      latency_ms: (($elapsed_seconds | tonumber) * 1000),
      response: (
        if $status >= 200 and $status < 300 then
          (.result // null)
        elif type == "object" then
          {
            error: .error,
            message: .message,
            status: .status,
            detail: .detail
          }
          | with_entries(select(.value != null))
          | remove_sensitive_fields
        else
          {detail: .}
        end
      )
    }
  ' "$RESPONSE_FILE"; then
  echo "Processing endpoint returned invalid JSON." >&2
  exit 6
fi

if [[ "$HTTP_CODE" -lt 200 || "$HTTP_CODE" -ge 300 ]]; then
  exit 6
fi
