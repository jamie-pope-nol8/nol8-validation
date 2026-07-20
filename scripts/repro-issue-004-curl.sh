#!/usr/bin/env bash
#
# ISSUE-004 reproduction using curl only.
#
# This script deliberately uses NO code from the validation framework. It sends
# a policy and a message to Themis with plain curl and prints the complete,
# unprocessed response body. Nothing between curl and the terminal transforms
# the output.
#
# Purpose: demonstrate that the corruption originates in the Themis runtime and
# not in any tooling that produced it.
#
# Requires three values, taken from the environment or from config/demo.env
# and .env if present:
#
#   THEMIS_POLICY_ENDPOINT
#   THEMIS_PROCESS_ENDPOINT
#   THEMIS_TOKEN
#
# Usage:
#
#   ./scripts/repro-issue-004-curl.sh
#
# WARNING: deploying a policy REPLACES the active policy on the target tenant.
# Restore the previous policy afterwards.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

# Convenience only: load endpoints/token if the operator has them on disk.
# Engineering can instead export the three variables and run this anywhere.
[[ -f "$PROJECT_ROOT/config/demo.env" ]] && source "$PROJECT_ROOT/config/demo.env"
[[ -f "$PROJECT_ROOT/.env" ]] && source "$PROJECT_ROOT/.env"

: "${THEMIS_POLICY_ENDPOINT:?set THEMIS_POLICY_ENDPOINT}"
: "${THEMIS_PROCESS_ENDPOINT:?set THEMIS_PROCESS_ENDPOINT}"
: "${THEMIS_TOKEN:?set THEMIS_TOKEN}"

MESSAGE='name: Elena Chen 1327, done'

deploy_policy() {
  local policy="$1"
  printf '%s' "$policy" | curl -skS \
    -X POST "$THEMIS_POLICY_ENDPOINT" \
    -H "Authorization: Bearer $THEMIS_TOKEN" \
    --data-binary @- \
    -o /dev/null \
    -w '  policy deploy HTTP %{http_code}\n'
}

send_message() {
  # Body is built with printf so the exact bytes on the wire are visible.
  printf '{"message":"%s"}' "$MESSAGE" | curl -skS \
    -X POST "$THEMIS_PROCESS_ENDPOINT" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer $THEMIS_TOKEN" \
    --data-binary @-
  printf '\n'
}

case_run() {
  local label="$1" policy="$2"
  printf '\n--- %s ---\n' "$label"
  printf '  policy sent:\n'
  printf '%s' "$policy" | sed 's/^/    /'
  deploy_policy "$policy"
  printf '  raw response body:\n    '
  send_message
}

printf 'ISSUE-004 reproduction via curl only\n'
printf 'no validation-framework code is involved\n\n'
printf 'request body sent to the processing endpoint:\n'
printf '  {"message":"%s"}\n' "$MESSAGE"

case_run "full literal rule only" \
'"Elena Chen 1327" -> "[PII:PERSON_NAME]";
'

case_run "prefix literal rule only" \
'"Elena Chen" -> "[PII:PERSON_NAME]";
'

case_run "both rules (overlapping literals)" \
'"Elena Chen 1327" -> "[PII:PERSON_NAME]";
"Elena Chen" -> "[PII:PERSON_NAME]";
'

case_run "both rules, short replacement" \
'"Elena Chen 1327" -> "[NAME]";
"Elena Chen" -> "[NAME]";
'

cat <<'EOF'

Expected reading of the results above:

  Either rule deployed alone returns correct output.
  Both rules deployed together corrupt the output, destroying content that
  precedes the match.

Restore the previous policy before leaving the tenant in this state.
EOF
