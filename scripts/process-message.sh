#!/usr/bin/env bash

set -euo pipefail

CONFIG_FILE="$HOME/jamie/config/demo.env"
INPUT_FILE="${1:-}"
OUTPUT_DIR="$HOME/jamie/output"
ENDPOINT_DEFAULT="https://tenant001-v1demo.nol8.net/v1/process"

if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
fi

ENDPOINT="${ARGUS_PROCESS_ENDPOINT:-$ENDPOINT_DEFAULT}"

if [[ -z "$INPUT_FILE" ]]; then
  echo "Usage: $0 <input-file>"
  exit 1
fi

if [[ ! -f "$INPUT_FILE" ]]; then
  echo "Input file not found: $INPUT_FILE"
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

INPUT_NAME="$(basename "$INPUT_FILE")"
INPUT_STEM="${INPUT_NAME%.*}"
INPUT_EXTENSION="${INPUT_NAME##*.}"

if [[ "$INPUT_NAME" == "$INPUT_EXTENSION" ]]; then
  OUTPUT_FILE="$OUTPUT_DIR/${INPUT_NAME}.processed"
else
  OUTPUT_FILE="$OUTPUT_DIR/${INPUT_STEM}.processed.${INPUT_EXTENSION}"
fi

REQUEST_FILE="$(mktemp)"
RESPONSE_FILE="$(mktemp)"
CURL_METADATA_FILE="$(mktemp)"

cleanup() {
  rm -f "$REQUEST_FILE" "$RESPONSE_FILE" "$CURL_METADATA_FILE"
}
trap cleanup EXIT

jq -Rs '{message: .}' "$INPUT_FILE" > "$REQUEST_FILE"

HTTP_CODE="$(
  curl -sS \
    -o "$RESPONSE_FILE" \
    -w '%{http_code} %{time_total}' \
    -H 'Content-Type: application/json' \
    --data-binary "@$REQUEST_FILE" \
    "$ENDPOINT" \
    > "$CURL_METADATA_FILE"

  awk '{print $1}' "$CURL_METADATA_FILE"
)"

ELAPSED_SECONDS="$(awk '{print $2}' "$CURL_METADATA_FILE")"
ELAPSED_MS="$(awk -v seconds="$ELAPSED_SECONDS" 'BEGIN {printf "%.0f", seconds * 1000}')"

if [[ "$HTTP_CODE" -lt 200 || "$HTTP_CODE" -ge 300 ]]; then
  echo "Request failed with HTTP $HTTP_CODE"
  jq . "$RESPONSE_FILE" 2>/dev/null || cat "$RESPONSE_FILE"
  exit 1
fi

if ! jq -e '.result.message | type == "string"' "$RESPONSE_FILE" >/dev/null; then
  echo "Response did not contain result.message:"
  jq . "$RESPONSE_FILE"
  exit 1
fi

jq -r '.result.message' "$RESPONSE_FILE" > "$OUTPUT_FILE"

JOB_ID="$(jq -r '.jid // "not returned"' "$RESPONSE_FILE")"

if cmp -s "$INPUT_FILE" "$OUTPUT_FILE"; then
  CHANGED="No"
else
  CHANGED="Yes"
fi

echo
echo "Nol8 Processing Demo"
echo
printf "%-13s %s\n" "Endpoint:" "$ENDPOINT"
printf "%-13s %s\n" "Input:" "$INPUT_FILE"
printf "%-13s %s\n" "Output:" "$OUTPUT_FILE"
printf "%-13s %s\n" "Job ID:" "$JOB_ID"
printf "%-13s %s ms\n" "Elapsed:" "$ELAPSED_MS"
printf "%-13s %s\n" "Changed:" "$CHANGED"

echo
echo "Original"
echo "--------"
cat "$INPUT_FILE"

echo
echo
echo "Processed"
echo "---------"
cat "$OUTPUT_FILE"
echo
