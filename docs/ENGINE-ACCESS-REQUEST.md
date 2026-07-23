# Engine access — two requests for engineering

_Prepared 2026-07-23. Self-contained: hostnames, IPs, and commands only — paste any
section straight into Slack/a ticket. Two independent asks; they can be actioned
separately._

---

## Ask 1 — Aergia data plane on :444 is down (Themis :443 on the same host is fine)

**What we see (run from the in-VPC EC2 box, which reaches the engines):**

```
NOL8 (Themis, :443)
  DNS: tenant001-v1demo.nol8.net -> 10.8.11.254        OK
  control plane (themis.sales.nol8.cloud:8444/policy)  HTTP 200
  data plane   (tenant001-v1demo.nol8.net:443)         round-trip OK  ("ping test" -> "[PONG] test")

RE2 (Aergia, :444)
  DNS: tenant001-v1demo.nol8.net -> 10.8.11.254        OK
  control plane (aergia.sales.nol8.cloud:8444/policy)  HTTP 200
  data plane   (tenant001-v1demo.nol8.net:444)         TCP CONNECT TIMES OUT (packets dropped)
```

**Diagnosis — this is port-444-specific, not a host outage.** :443 and :444 are the
**same host** (`10.8.11.254`). :443 completes a full TLS + HTTP round-trip, so the host
is up and reachable. Only :444 never completes a TCP connect. So either the **Aergia
listener on :444 is down**, or a **security-group / firewall rule allows :443 but not
:444**. (ICMP is dropped to this host even for the working :443, so ping is not a useful
signal here — the discriminator is 443-connects vs 444-times-out on one host.)

**Reproduce (any host that can reach 10.8.11.254):**

```bash
# 443 connects, 444 does not:
nc -vz -w 5 tenant001-v1demo.nol8.net 443    # -> succeeded
nc -vz -w 5 tenant001-v1demo.nol8.net 444    # -> timed out
# or with curl connect timing (0.000000 = never connected):
curl -sS -o /dev/null -w 'connect=%{time_connect}s\n' -m 8 https://tenant001-v1demo.nol8.net:443/v1/process
curl -sS -o /dev/null -w 'connect=%{time_connect}s\n' -m 8 https://tenant001-v1demo.nol8.net:444/v1/process
```

**Request:** restart / bring up the Aergia listener on :444, or add the missing :444
ingress rule on the data-plane host's security group. Control plane is healthy — no
policy/creds action needed.

---

## Ask 2 — Open direct access to the engines from a VPN client (drop the EC2 hop)

Today all benchmark execution must run on the in-VPC EC2 box because a VPN-connected
laptop cannot reach the engines. There are **two independent walls** — both must be
removed; fixing either alone does nothing.

**Evidence — `getaddrinfo` (what curl/ssh actually resolve), same three names from each host:**

| hostname | from VPN laptop (100.83.x) | from in-VPC EC2 |
|---|---|---|
| `tenant001-v1demo.nol8.net` (data plane :443/:444) | **NO RESOLUTION** | `10.8.11.254` |
| `themis.sales.nol8.cloud` (control :8444) | `10.10.1.254` | `10.10.1.254` |
| `aergia.sales.nol8.cloud` (control :8444) | `10.10.1.127` | `10.10.1.127` |

**Wall 1 — DNS split-horizon.** `tenant001-v1demo.nol8.net` resolves **only** inside
the VPC. The VPN resolver was never given that record, so a laptop cannot even resolve
the data plane.
→ **Publish `tenant001-v1demo.nol8.net` (→ 10.8.11.254) to the VPN/Tailscale resolver.**

**Wall 2 — no route to the subnets.** Even the control-plane names that *do* resolve for
the laptop (`10.10.1.254` / `10.10.1.127`) **time out on :8444** — the VPN isn't
advertising the engine subnets to peers:

```bash
# from the VPN laptop — resolves, but no route:
nc -vz -w 6 themis.sales.nol8.cloud 8444    # -> timed out
nc -vz -w 6 aergia.sales.nol8.cloud 8444    # -> timed out
```

→ **Advertise `10.10.1.0/24` (control plane) and `10.8.11.0/24` (data plane) to VPN
peers (`100.83.0.0/8`), and allow ingress on :443, :444, :8444 from that range.**

**Net:** DNS alone isn't enough (you'd resolve `10.8.11.254` and still have no route);
routing alone isn't enough (the data-plane name still won't resolve). Both, please.

---

_Until Ask 1 lands, the RE2/Aergia baseline is unavailable, so any benchmark that
compares NOL8 against the incumbent is blocked on the compare column. Until Ask 2 lands,
all execution stays on the EC2 box._
