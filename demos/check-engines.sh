#!/usr/bin/env bash
# Preflight: "are the engines where they need to be?"
#
# For each engine (NOL8/Themis :443, RE2/Aergia :444), checks the two planes
# independently so a failure points at the right place:
#   1. control plane  - deploy a harmless 1-rule probe policy ("ping" -> "[PONG]")
#   2. data plane     - send one message and confirm the round-trip transform
#
# On a data-plane failure (or with --diagnose) it drops into a deeper probe
# (TCP-connect timing + ICMP ping + raw nc) and interprets the result:
#   - packets DROPPED (no ICMP, TCP timeout) -> host down or firewalled (infra side)
#   - TCP RST "refused"                      -> host up, service down on that port
#   - HTTP 503 with a body                   -> paused awaiting policy (deploy one)
# Cross-reference docs/TROUBLESHOOTING.md ("Health check by hand").
#
# Run on EC2 (the box that reaches the engines). Deploys a probe policy, so the
# tenant is disposable - redeploy your benchmark policy afterward. Exits non-zero
# if any check fails, so it can gate a run.
#
#   bash demos/check-engines.sh                 # both engines
#   bash demos/check-engines.sh --diagnose      # + deep probe every engine
#   ENGINES=themis bash demos/check-engines.sh
#   CHECK_TIMEOUT=20 bash demos/check-engines.sh
set -uo pipefail   # deliberately NOT -e: run every check and report

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
set -a; source config/demo.env; source .env; set +a

TIMEOUT="${CHECK_TIMEOUT:-10}"
ENGINES="${ENGINES:-themis aergia}"
DIAGNOSE=0
[ "${1:-}" = "--diagnose" ] && DIAGNOSE=1
[ "${DIAGNOSE_ALL:-0}" = "1" ] && DIAGNOSE=1
PROBE_RULE='"ping" -> "[PONG]";'
PROBE_MSG='ping test'
EXPECT='[PONG] test'

pass=0
fail=0
ok()  { printf '  [OK]   %s\n' "$1"; pass=$((pass+1)); }
bad() { printf '  [FAIL] %s\n' "$1"; fail=$((fail+1)); }

# Deep probe of one data-plane endpoint: is it down, refused, or filtered?
diagnose_dataplane() {
  local ep="$1" host port ct ploss ncout
  host="$(printf '%s' "$ep" | sed -E 's#https?://([^:/]+).*#\1#')"
  port="$(printf '%s' "$ep" | sed -E 's#https?://[^:/]+:([0-9]+).*#\1#')"
  [ "$port" = "$ep" ] && port=443
  printf '  -- diagnose %s:%s --\n' "$host" "$port"

  ct="$(curl -sS --connect-timeout 6 -m 8 -o /dev/null -w '%{time_connect}' "$ep" 2>/dev/null)"
  ploss="$(ping -c 2 -W 2 "$host" 2>/dev/null | sed -n 's/.* \([0-9]\{1,3\}\)% packet loss.*/\1/p')"
  ploss="${ploss:-100}"
  if command -v nc >/dev/null; then ncout="$(nc -vz -w 5 "$host" "$port" 2>&1 | tail -1)"; else ncout="(nc not installed)"; fi

  printf '     tcp connect: %ss (0.000000 = never connected)\n' "${ct:-n/a}"
  printf '     icmp loss  : %s%% (note: ICMP is often blocked even when the port works; TCP is authoritative)\n' "$ploss"
  printf '     nc %s:%s : %s\n' "$host" "$port" "$ncout"

  # TCP is authoritative. A successful connect (nc succeeded, or a non-zero connect time)
  # means the host is UP and the port is reachable, regardless of ICMP loss.
  local tcp_ok=0
  printf '%s' "$ncout" | grep -qi 'succeeded' && tcp_ok=1
  [ -n "$ct" ] && [ "$ct" != "0.000000" ] && [ "$ct" != "n/a" ] && tcp_ok=1

  if [ "$tcp_ok" = "1" ]; then
    printf '     => TCP connects: the host is UP and port %s is reachable. This is NOT a\n' "$port"
    printf '        connectivity problem. If the round-trip was wrong, it is policy or\n'
    printf '        propagation: the probe policy may not have reloaded yet (raise RELOAD_WAIT),\n'
    printf '        or HTTP 503 = paused awaiting a policy (deploy one).\n'
  elif printf '%s' "$ncout" | grep -qi 'refused'; then
    printf '     => TCP reset (refused): the host is UP but nothing is listening on %s.\n' "$port"
    printf '        The service is down on that port. (Not policy or creds.)\n'
  else
    printf '     => TCP never connects (timeout, not refused): packets are DROPPED. The\n'
    printf '        data-plane host (%s, argus edge) is DOWN or a firewall / security\n' "$host"
    printf '        group / route is blocking %s. Network/infra side, not our code.\n' "$port"
  fi
  printf '     See docs/TROUBLESHOOTING.md, "Health check by hand".\n'
}

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

  # 2. data plane: round-trip one message. Retry, because a just-deployed policy takes a
  #    few seconds to propagate (Aergia especially); a reachable-but-untransformed response
  #    means the probe has not reloaded yet, not that the engine is down.
  local body rc failed=0 attempt=1 tries="${ROUNDTRIP_TRIES:-4}" wait="${RELOAD_WAIT:-3}"
  while : ; do
    body="$(printf '{"message":"%s"}' "$PROBE_MSG" | curl -skS -m "$TIMEOUT" -X POST "$process_ep" \
      -H 'Content-Type: application/json' -H "Authorization: Bearer $token" --data-binary @- 2>/dev/null)"
    rc=$?
    if [ $rc -eq 0 ] && printf '%s' "$body" | grep -qF "$EXPECT"; then
      ok "data plane: round-trip transform correct ('$PROBE_MSG' -> contains '$EXPECT')"
      break
    fi
    if [ "$attempt" -ge "$tries" ]; then
      if [ $rc -ne 0 ] || [ -z "$body" ]; then
        bad "data plane: UNREACHABLE (curl exit $rc) - $process_ep"
      else
        bad "data plane: reachable but probe not applied after $tries tries - $process_ep"
        printf '         body: %s\n' "$body"
        printf '         (Reachable + valid response but UNtransformed usually means the probe policy\n'
        printf '          has not propagated yet - raise RELOAD_WAIT. HTTP 503 = paused awaiting policy;\n'
        printf '          401/403 = creds; 404 = wrong path.)\n'
      fi
      failed=1
      break
    fi
    attempt=$((attempt+1))
    sleep "$wait"
  done

  # deep probe on failure, or when --diagnose is set
  if [ "$failed" = "1" ] || [ "$DIAGNOSE" = "1" ]; then diagnose_dataplane "$process_ep"; fi
}

printf 'NOL8 engine preflight  (probe policy: %s)%s\n' "$PROBE_RULE" \
  "$([ "$DIAGNOSE" = "1" ] && printf '  [--diagnose]')"
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
