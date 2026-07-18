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
  echo "Create it from $PROJECT_ROOT/.env.example and add the required tokens." >&2
  exit 3
fi

# shellcheck disable=SC1090
source "$CONFIG_FILE"

# shellcheck disable=SC1090
source "$SECRETS_FILE"

TARGET="${1:-}"
POLICY_FILE="${2:-}"

case "$TARGET" in
  themis)
    TOKEN="${THEMIS_TOKEN:-}"
    ENDPOINT="${THEMIS_POLICY_ENDPOINT:-}"
    ;;
  aergia)
    TOKEN="${AERGIA_TOKEN:-}"
    ENDPOINT="${AERGIA_POLICY_ENDPOINT:-}"
    ;;
  *)
    echo "Usage: $0 <themis|aergia> <policy-file>" >&2
    exit 2
    ;;
esac

if [[ -z "$TOKEN" ]]; then
  echo "Token is not configured for target: $TARGET" >&2
  exit 3
fi

if [[ -z "$ENDPOINT" ]]; then
  echo "Policy endpoint is not configured for target: $TARGET" >&2
  exit 2
fi

if [[ -z "$POLICY_FILE" ]]; then
  echo "Usage: $0 <themis|aergia> <policy-file>" >&2
  exit 2
fi

if [[ ! -f "$POLICY_FILE" ]]; then
  echo "Policy file not found: $POLICY_FILE" >&2
  exit 2
fi

RESPONSE_FILE="$(mktemp)"

cleanup() {
  rm -f "$RESPONSE_FILE"
}
trap cleanup EXIT

set +e
HTTP_CODE="$(curl -skS \
  -o "$RESPONSE_FILE" \
  -w '%{http_code}' \
  -X POST "$ENDPOINT" \
  -H "Authorization: Bearer $TOKEN" \
  --data-binary "@$POLICY_FILE")"
CURL_STATUS=$?
set -e

if [[ "$CURL_STATUS" -ne 0 ]]; then
  echo "Policy deployment network request failed." >&2
  exit 5
fi

if [[ "$HTTP_CODE" == "401" || "$HTTP_CODE" == "403" ]]; then
  echo "Policy deployment authentication was rejected (HTTP $HTTP_CODE)." >&2
  exit 4
fi

if [[ "$HTTP_CODE" -lt 200 || "$HTTP_CODE" -ge 300 ]]; then
  echo "Policy deployment failed (HTTP $HTTP_CODE)." >&2
  exit 6
fi

if ! jq . "$RESPONSE_FILE"; then
  echo "Policy deployment returned an invalid JSON response." >&2
  exit 6
fi
