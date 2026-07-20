# ISSUE-007 — There is no way to check whether the runtime is healthy

**Component:** Themis runtime + operator tooling (`nolctl`, status string)
**Type:** Diagnosability limitation
**Severity:** Medium
**Status:** Open

## Summary

There is no health, readiness, or status endpoint. The only way to learn that
the engine is not serving is to send real traffic and have it fail. When the
processing endpoint returned HTTP 503 to every request for about an hour, the
true cause was benign — the engine was up but had no policy loaded — yet every
available signal pointed elsewhere, and the documented remedy made it worse.

## Observed

The data-plane host publishes exactly one TCP port (443), and on it
`/v1/process` is the only route. Every one of `/health`, `/healthz`, `/ready`,
`/readyz`, `/live`, `/livez`, `/status`, `/metrics`, `/version`, their `/v1/`
variants, and `/` returns 404. `GET /v1/process` returns 405, confirming the
route exists and the 404s are genuine absence rather than a routing quirk.

Those 404s and the 405 are served promptly **while the engine is not serving**.
The edge is healthy and answering, so nothing short of real traffic
distinguishes a working system from a broken one.

### The incident

Apollo boots with its data plane paused and un-pauses only when a policy
commits. No policy had been deployed since the last restart, so it sat paused
and returned 503 to all traffic. Posting a single-rule policy restored service
immediately. **The system was one API call from working, and every signal
pointed somewhere else:**

| signal | what it said | true? |
|---|---|---|
| Error message | `ARGUS_UPSTREAM_UNAVAILABLE … no apollo response` | misleading — apollo was up and healthy |
| Troubleshooting guide | "most probably Apollo encountered a severe bug"; restart services | wrong; restarting returns to the same paused state |
| `systemctl` | `service=active` | true but useless — active and paused are indistinguishable |
| `nolctl doctor` | `FAIL preflight: missing hugepages/isolcpus/…` | **false positive** (see below) |
| Status string | `data plane PAUSED` | correct while broken, **still says PAUSED after recovery** |

The 503 body, for the record:

```json
{"error": {"code": "ARGUS_UPSTREAM_UNAVAILABLE",
 "message": "stream submit: ARGUS_UPSTREAM_UNAVAILABLE: backend send failed:
  dispatcher: iris send: ARGUS_UPSTREAM_TIMEOUT: iris quic: upstream error:
  RESPONSE_WAIT: request timed out (no apollo response in >2s)"}}
```

The edge accepted, authenticated, and routed the request; apollo did not answer
within the 2-second budget because it was paused, not unhealthy. The control
plane stayed responsive throughout (under 10 ms). So the product was partly
alive — reachable, authenticating, routing — and unable to do the one thing it
exists to do, while reporting every component as active.

### Two tooling defects made it worse

1. **`nolctl doctor` reports a false `FAIL` on kernel parameters.** It expects
   the literal strings `hugepages=4, isolcpus=0-11, nohz_full=0-11,
   rcu_nocbs=0-11`, while the host is correctly configured as `hugepages=16,
   isolcpus=2-13, nohz_full=2-13, rcu_nocbs=2-13`. It string-matches one topology
   instead of checking the parameters are present and sane, so it fails on a
   correct machine and points the operator at GRUB and a reboot.
2. **The service status string is set once at startup and never updated.** It
   still read `data plane PAUSED` after the data plane was verified working. An
   operator trusting it would restart a healthy service.

## Why it matters

- **Work is started against a dead backend.** A long run begins normally and
  produces nothing but failures; nothing can be checked beforehand.
- **Outage duration is unknowable.** With no health signal and no timestamped
  status, there is no way to establish when the engine stopped responding or
  whether it has recovered, other than by probing it.
- **Causes cannot be distinguished.** A 503 could be the engine, the transport,
  the tenant, the credential — or, as here, a healthy engine awaiting a policy.
  Only the error string separates them, and only because it happens to name
  internal components. That is incidental detail, not a contract; a less chatty
  or redacted error would leave an operator with an unexplained 503 and nothing
  to act on.

**"Paused awaiting policy" deserves its own signal.** It is a normal,
recoverable, expected state currently indistinguishable from a crashed backend,
and the documented remedy for what it looks like — restart everything — does not
fix it and returns the system to the same state. That combination turned a
one-call fix into an hour.

## Reproduction / recovery

Any policy un-pauses the data plane. This is also the recovery for the incident
above:

```bash
POLICY_ENDPOINT="https://<control-plane-host>:8444/policy"   # self-signed cert
TOKEN="<bearer-token>"

printf '"SSN" -> "[REDACTED]";\n' | curl -sS --insecure \
  -X POST "$POLICY_ENDPOINT" -H "Authorization: Bearer $TOKEN" --data-binary @-
```

The `--insecure` is required because the policy control plane presents a
self-signed certificate whose subject is an internal address. A successful load
returns `{"ok": true, …, "message": "loaded 1 rule(s) … REPLACE", "rules": 1}`
and un-pauses the data plane immediately.

## What would resolve it

- A health endpoint reporting engine reachability **and policy-load state**,
  unauthenticated or cheaply authenticated, so it can be polled before starting
  work and by any monitoring the customer already runs. Here it would have said
  "up, no policy loaded" and the fix would have been immediate.
- An error code distinguishing "awaiting policy" from "engine unavailable".
- A status string that reflects live state rather than startup state.
- `nolctl doctor` to check kernel parameters are present and sane rather than
  string-matching one expected topology.
- The troubleshooting guide to cover this case — the one an evaluator hits most:
  a fresh or restarted host has no policy yet.
