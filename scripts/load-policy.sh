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

# shellcheck source=scripts/lib/env-config.sh
source "$SCRIPT_DIR/lib/env-config.sh"

# Parse rather than execute (FW-4), and let the caller's environment win over
# the files (FW-5). The committed config is restricted to its known keys; the
# local secrets file is the operator's own.
load_env_file "$CONFIG_FILE" \
  THEMIS_POLICY_ENDPOINT AERGIA_POLICY_ENDPOINT \
  THEMIS_PROCESS_ENDPOINT THEMIS_ALLOW_INSECURE_TLS
load_env_file "$SECRETS_FILE"

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

HEADER_FILE="$(mktemp)"

cleanup() {
  rm -f "$RESPONSE_FILE" "$HEADER_FILE"
}
trap cleanup EXIT

# Keep the bearer token out of the process argument list (T2-3). Passed as
# `-H "Authorization: Bearer $TOKEN"` it is visible to any local user via `ps`
# for the lifetime of the request. A 0600 temp file read with `-H @file` is
# owner-only and removed on exit - the token is never an argv element.
chmod 600 "$HEADER_FILE"
printf 'Authorization: Bearer %s\n' "$TOKEN" > "$HEADER_FILE"

# TLS verification is ON by default. The policy control plane currently
# presents a self-signed certificate named after an internal address
# (CN=ip-172-31-40-100), so verification fails against its DNS name and
# THEMIS_ALLOW_INSECURE_TLS must be set to reach it.
#
# This call carries both the bearer token and the complete ruleset, so
# disabling verification is a deliberate, visible choice rather than a
# hardcoded default. See "Control plane TLS is self-signed" under Observations
# in docs/product/themis-product-limitations.md - an observation, not a
# limitation, but kept explicit so the exception does not silently propagate
# into an environment where it would matter.
# A single optional flag, held as a string rather than an array: an empty array
# expanded under `set -u` is an "unbound variable" error on bash 3.2 (the macOS
# system bash). The ${VAR:+"$VAR"} form expands to nothing when unset and is
# safe everywhere. Now that the caller can set THEMIS_ALLOW_INSECURE_TLS=0
# (FW-5), the empty case is actually reachable.
INSECURE_FLAG=""
if [[ "${THEMIS_ALLOW_INSECURE_TLS:-0}" == "1" ]]; then
  INSECURE_FLAG="--insecure"
fi

set +e
HTTP_CODE="$(curl -sS ${INSECURE_FLAG:+"$INSECURE_FLAG"} \
  --connect-timeout 5 \
  --max-time 30 \
  -o "$RESPONSE_FILE" \
  -w '%{http_code}' \
  -X POST "$ENDPOINT" \
  -H "@$HEADER_FILE" \
  --data-binary "@$POLICY_FILE")"
CURL_STATUS=$?
set -e

if [[ "$CURL_STATUS" -eq 60 ]]; then
  echo "Policy deployment failed TLS verification against $ENDPOINT." >&2
  echo "The control plane certificate does not match its hostname." >&2
  echo "To proceed anyway, set THEMIS_ALLOW_INSECURE_TLS=1 - note this sends" >&2
  echo "the bearer token and the full ruleset over an unverified connection." >&2
  exit 5
fi

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

if ! jq --arg http_status "$HTTP_CODE" \
  '{http_status: ($http_status | tonumber), response: .}' \
  "$RESPONSE_FILE"; then
  echo "Policy deployment returned an invalid JSON response." >&2
  exit 6
fi
