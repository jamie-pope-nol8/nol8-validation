#!/usr/bin/env bash
# Preflight: "are the engines where they need to be?"
#
# For each engine (NOL8/Themis :443, RE2/Aergia :444), checks the two planes
# independently so a failure points at the right place:
#   1. control plane  - deploy a harmless 1-rule probe policy ("ping" -> "[PONG]")
#   2. data plane     - send one message and confirm the round-trip transform
#
# Run on EC2 (the box that reaches the engines). Deploys a probe policy, so the
# tenant is disposable - redeploy your benchmark policy afterward. Exits non-zero
# if any check fails, so it can gate a run.
#
#   bash demos/check-engines.sh              # both engines
#   ENGINES=themis bash demos/check-engines.sh
#   CHECK_TIMEOUT=20 bash demos/check-engines.sh
set -uo pipefail   # deliberately NOT -e: run every check and report

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
set -a; source config/demo.env; source .env; set +a

TIMEOUT="${CHECK_TIMEOUT:-10}"
ENGINES="${ENGINES:-themis aergia}"
PROBE_RULE='"ping" -> "[PONG]";'
PROBE_MSG='ping test'
EXPECT='[PONG] test'

pass=0
fail=0
ok()   { printf '  [OK]   %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf '  [FAIL] %s\n' "$1"; fail=$((fail+1)); }

check_engine() {
  local name="$1" policy_ep="$2" process_ep="$3" token="$4"
  local host; host="$(printf '%s' "$process_ep" | sed -E 's#https?://([^:/]+).*#\1#')"
  printf '\n===== %s =====\n' "$name"

  # 0. DNS for the data-plane host
  local ip; ip="$(getent hosts "$host" 2>/dev/null | awk '{print $1; exit}')"
  if [ -n "$ip" ]; then ok "DNS: $host -> $ip"; else bad "DNS: $host did not resolve"; fi

  # 1. control plane: deploy the probe policy
  local code
  code="$(printf '%s' "$PROBE_RULE" | curl -skS -m "$TIMEOUT" -X POST "$policy_ep" \
    -H "Authorization: Bearer $token" --data-binary @- -o /dev/null -w '%{http_code}' 2>/dev/null)"
  if [ "$code" = "200" ]; then ok "control plane: policy deploy HTTP 200 ($policy_ep)"
  else bad "control plane: policy deploy HTTP ${code:-000} ($policy_ep)"; fi

  # 2. data plane: round-trip one message
  local body rc
  body="$(printf '{"message":"%s"}' "$PROBE_MSG" | curl -skS -m "$TIMEOUT" -X POST "$process_ep" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer $token" --data-binary @- 2>/dev/null)"
  rc=$?
  if [ $rc -ne 0 ] || [ -z "$body" ]; then
    bad "data plane: UNREACHABLE (curl exit $rc, connection timed out) - $process_ep"
    printf '         control plane was reachable, so this is the data-plane path/host.\n'
  elif printf '%s' "$body" | grep -qF "$EXPECT"; then
    ok "data plane: round-trip transform correct ('$PROBE_MSG' -> contains '$EXPECT')"
  else
    bad "data plane: reachable but unexpected response"
    printf '         body: %s\n' "$body"
  fi
}

printf 'NOL8 engine preflight  (probe policy: %s)\n' "$PROBE_RULE"
for e in $ENGINES; do
  case "$e" in
    themis) check_engine "NOL8 (Themis, :443)" "$THEMIS_POLICY_ENDPOINT" "$THEMIS_PROCESS_ENDPOINT" "$THEMIS_TOKEN" ;;
    aergia) check_engine "RE2 (Aergia, :444)"  "$AERGIA_POLICY_ENDPOINT" "$AERGIA_PROCESS_ENDPOINT" "$AERGIA_TOKEN" ;;
    *) printf '\nunknown engine: %s\n' "$e" ;;
  esac
done

printf '\n----- summary: %d ok, %d failed -----\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || { printf 'Not ready. Fix the failed checks above before running a benchmark.\n'; exit 1; }
printf 'All checks passed. Engines are reachable and round-tripping.\n'
