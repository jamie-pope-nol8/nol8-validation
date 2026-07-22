# Continue Conversation

Last Updated: 2026-07-22

Durable memory of the project, so a new session (or a post-compaction session) can
continue without reconstructing context from chat history.

> **Handoff at 2026-07-22.** Two tracks: (1) product validation (Themis/NOL8 defects)
> is stable, **236 framework tests passing**; (2) the **demo environment** is the
> active work, and it now has THREE data points at different stages.
>
> - **Data Point 1 (pre-index) - DONE, shipped.** On-brand report leads with the
>   optimization use case: Themis forwards **64.3% fewer tokens**, oracle-verified
>   **1000/1000**; the RE2 baseline (Aergia) **corrupts 876/1000** on strip. Single
>   fresh clean run; full "show your work" receipts appendix.
> - **Data Point 2 (pre/post-inference) - DONE (stats reframed).** Real-engine modes
>   govern a model boundary at both edges. **Themis == Aergia == oracle, 52/52**. The
>   stats were reframed to the **"deterministic guardrail for known policy"** story
>   (no test-set counts up top) and a **representative-policy dataset** was built
>   (`datapoint2/representative/`, insurer scenario). Report/DEMO-NOTES/oracle-verify
>   built. Only gap: the LIVE run of the representative set (blocked by the outage
>   below). See the DP2 section + [[demo-positioning-and-data-strategy]].
> - **Data Point 3 (agent-to-agent) - PLANNED only.** Full build spec in
>   `demos/benchmark/DP3-PLAN.md`. DP2 generalized to many control points. Not built.
>
> **>>> CURRENT OPERATIONAL BLOCKER (2026-07-22 end of session): the engine DATA
> planes (:443/:444) are UNREACHABLE from EC2.** Control planes (:8444) are healthy
> (policy deploys return 200); DNS resolves (`tenant001-v1demo.nol8.net` ->
> 10.8.11.254); but the data-plane ports time out at the TCP level (curl exit 28).
> Diagnose/confirm with **`bash demos/check-engines.sh`** on EC2 (built this session).
> Likely a data-plane service/firewall/VPN-route issue on the engine side - NOT our
> code. Any live benchmark is blocked until this clears; the framework code is fine.
>
> **Current focus / NEXT:** (a) clear the data-plane outage, then the pending live
> representative run; (b) final DP2 copy look; (c) build DP3 per the plan; (d) Track B
> (`agentic-mesh-lab`) is separate and larger.

This file is project *state*. Three companions carry the rest:

| question | document |
|---|---|
| Something is broken right now | `docs/TROUBLESHOOTING.md` |
| What have we found? | `docs/FINDINGS.md` (THM-n product, OPS-n their tooling, FW-n ours, OBS-n non-findings) |
| Where is any other document? | `docs/README.md` |

## Maintaining this file

- **On "update the project":** rewrite this file wholesale to current state. Do not
  append or preserve stale sections - accuracy over history.
- **Every turn:** keep it current as work happens, so `/compact` is safe anytime.

---

# CRITICAL: engine identity + integrity

- **Themis == NOL8** - the FPGA product we sell. Data plane `:443`.
- **Aergia == RE2** - a *real RE2 (regex) engine* the team stood up and named Aergia,
  used as the **known incumbent** to benchmark NOL8 against. Data plane `:444`.
- There is **NO "Themis + Aergia" pair of NOL8 engines.** It is **NOL8 vs RE2**.
- **Demo scope: listMatch (literal) only** - that's what NOL8 does today; regex is not
  a NOL8 capability yet. RE2/Aergia is a regex engine but runs the same literal policy
  as the incumbent reference. [[demo-scope-listmatch-only]]
- **Benchmark integrity:** same policy + same dataset to every engine. Report
  divergence honestly; never tune for parity. Verifying our own engine against an
  independent oracle is the integrity check pointed at us, not rigging.
  [[benchmark-integrity-no-rigging]]

---

# The Short Version

**1. Product validation (Themis/NOL8 defects).** Headline: ISSUE-004 - overlapping
literals make the runtime write the replacement at the wrong offset and destroy
adjacent data, silently, HTTP 200. **Open, not yet reported to engineering** (the send
is the user's; docs ready). Register in `docs/issues/`. A clean 5,000-rule /
10,000-record qualification passes 100%.

**2. Demo environment (the current work).** DP1 done, DP2 done (pending stats talk),
DP3 planned. Plus Track B (agentic-mesh-lab), a separate larger visual demo.

---

# CRITICAL CONTEXT - who wrote what

**Engineering did not write this repository.** They handed over the v1.0 sandbox with
docs and an invitation to use it. This validation framework is ours. For anything sent
to engineering (the `docs/issues/` register already follows this): never reference a
repo path; inline reproductions as literal curl against their endpoints and token;
mention the framework only as provenance for finding the defect at scale.

---

# Session Operating Rules

- **Announce before ANY git command (local or remote)** and run it plainly. Do NOT
  rsync around a blocked push. Push works this session; keep announcing.
  [[announce-before-git]]
- **Every demo must be SA-runnable** - runbooks, copy-paste commands, the two-host
  workflow. [[demos-must-be-sa-runnable]]
- The Themis tenant is the user's disposable sandbox - overwrite policy freely; do not
  reflexively restore it. [[sandbox-policy-overwrite]]
- Reuse the external demo asset repos non-destructively - copy OUT of the kit, never
  edit it in place. [[preindex-kit-non-destructive]] [[demo-asset-repos]]
- `validate` is the product surface. Do NOT call `scripts/*.sh` directly.
- Work one action at a time; end responses with a clear next action.
- Repro/command docs aren't "done" until run as written.

---

# Environments

| | Mac | EC2 |
|---|---|---|
| purpose | development, commits | execution against the engines |
| path | `~/Code/nol8/nol8-validation` | `/opt/nol8/nol8-validation` |
| python | 3.12 | 3.14.4 |
| go | (none) | 1.22.5 at `$HOME/.local/go` (on `.bashrc` PATH) |
| host | - | `nol8-demo` (in `~/.ssh/config`; hostname `data-streamer`, 10.8.10.40) |

Edit/commit on Mac, `git push`, `git pull` on EC2, execute there. The Go demo
benchmarks run on EC2 only (the box that reaches the engines). Git push/pull both work;
EC2 is reconciled and current with origin.

**SSH note:** `nol8-demo` depends on the VPN; if `data-streamer.sales.nol8.cloud`
stops resolving, the VPN dropped - reconnect it. Long-running SSH commands must be
detached (`setsid nohup ... </dev/null >log 2>&1 &`) and polled via a log marker; run
adapter/engine calls + harness inside ONE ssh command (the run-live.sh scripts do).

---

# Services & ports (confirmed 2026-07-22)

| | address | notes |
|---|---|---|
| **NOL8 (Themis, FPGA)** data plane | `tenant001-v1demo.nol8.net:443/v1/process` | valid Amazon cert |
| **RE2 (Aergia)** data plane | `tenant001-v1demo.nol8.net:444/v1/process` | valid cert, SAME contract |
| Themis policy control plane | `themis.sales.nol8.cloud:8444/policy` | self-signed - needs `--insecure` |
| Aergia policy control plane | `aergia.sales.nol8.cloud:8444/policy` | self-signed - needs `--insecure` |
| themis host (`themis-demo`, ssh) | 10.10.1.254 | runs iris+apollo+policyd; treat with care |

Contract (both engines): `POST {"message": text}` -> `{"jid":.., "result":{"message":
processed}}`. Config in `config/demo.env` (`THEMIS_PROCESS_ENDPOINT`=:443,
`AERGIA_PROCESS_ENDPOINT`=:444, `*_POLICY_ENDPOINT`, `THEMIS_ALLOW_INSECURE_TLS=1`);
tokens in `.env`. Aergia's :444 has a **few-second reload propagation delay** after a
deploy.

**Tenant state:** `demos/policies/boundary-representative.nol` was last deployed to BOTH
engines (the representative-run attempt). Redeploy the relevant policy before a
different benchmark. NOTE (2026-07-22): both engine DATA planes (:443/:444) were
unreachable from EC2 at end of session (transient); control plane deploys still worked.

---

# CLI

```bash
validate generate --config <yaml> [--rules N] [--records M]
validate policy   --run <RUN_ID> | --file <path.nol> | --status  [--target {themis,aergia}]
validate run      --run <RUN_ID> [--limit N] [--skip-preflight]
validate compare  --run <RUN_ID> [--replacement-max-length 15]
validate report   --run <RUN_ID>
```

Fully documented in `README.md`. Transports read `NOL8_CONFIG_FILE`/`NOL8_SECRETS_FILE`
(default `config/demo.env`, `.env`); the token is written to a `0600` temp file and
passed with `-H @file` (never on argv - FW-9).

---

# Product-validation state

- **Authoritative qualification** 20260720T221534714262Z: 5,000 rules / 10,000 records
  / seed 42. 10,000 PASS, 0 collisions. Regenerates byte-identically. Policy + report
  in `artifacts/evidence/`; policy SHA `27fe47db`.
- **ISSUE-004** (overlapping literals corrupt output, silently, 200) - OPEN, eng doc
  ready but NOT SENT. Report: `docs/issues/ISSUE-004-overlapping-matches-corrupt-
  output.md`. Our generator stopped producing overlapping catalogs; the defect is
  untouched.
- **Register + code review:** `docs/issues/` = ISSUE-001..007 (1:1 to THM-1..7), one
  emailable report each; internal material in `docs/issues/internal/`. All code-review
  tiers DONE. Runtime-outage runbook (apollo boots data-plane PAUSED until a policy
  commits) in `docs/TROUBLESHOOTING.md` (OPS-1..3); `validate run` pre-flights.

---

# Demo environment - THE CURRENT WORK (in `demos/`)

Self-contained, isolated from `framework/` (except the `verify-oracle.py` scripts,
which deliberately reuse the framework's tested matcher as the independent oracle).

## Shared pieces

- **`demos/check-engines.sh`** - preflight ("are things where they need to be?"). Per
  engine, checks DNS + control-plane policy deploy + data-plane round-trip transform
  independently, so a failure points at the right plane. On a data-plane failure (or
  with `--diagnose`) it deep-probes (TCP-connect timing + ICMP ping + raw nc) and
  interprets: packets DROPPED (host down/firewalled) vs TCP RST (service down) vs HTTP
  503 (paused, deploy a policy); cross-refs `docs/TROUBLESHOOTING.md`. Deploys a
  harmless probe policy; exits non-zero if anything fails. Run on EC2 before any
  benchmark. **Confirmed the 2026-07-22 outage: argus edge (10.8.11.254) drops all
  ICMP+TCP - host down or firewalled, infra-side.**
- **`demos/themis-adapter/adapter.py`** - bridges `{"text"}->{"action","text"}` to the
  engine contract; keep/mask, drop/route via sentinel tokens. Used by DP1. (DP2/DP3
  call the engine directly in Go instead - simpler for a Go harness we own.)
- **`demos/policies/`** - `build_policy.py` -> `starter-known-values.nol` (42 govern
  rules); `build_optimization_policy.py` -> `optimization.nol` (DP1: govern + strip);
  `build_boundary_policy.py` -> `boundary.nol` (DP2: 19 rules, literals -> sentinels).
  All reuse ISSUE-005 (<=15 char tokens) / ISSUE-004 (no contained literals) guards.
  Parser note: trailing inline comments after a rule are rejected; own-line only.
- **On-brand report pipeline:** `demos/benchmark/run.json` (DP1) and
  `demos/benchmark/datapoint2/run.json` (DP2), rendered by the SHARED
  `demos/benchmark/make-report.py`. It dispatches on `run.get("kind")`: default (DP1)
  and `dp2`. Hero CTAs, nav, and footer readout are run.json-driven. Self-contained
  HTML (fonts/logos inlined); web (dark) / deck (Export->PDF, light). Content visible
  by default (no fade-gating; serve standalone, not in a reveal.js/preso wrapper).
  Rendered HTML is gitignored.

## Data Point 1 - pre-index - DONE (`demos/benchmark/`, corpus in `datapoint1/`)

- **Leads with the OPTIMIZATION use case** (clean data before embeddings). Headline
  "Clean the data before it becomes embeddings, at hardware speed." Governance
  byte-identical redaction is the trust anchor; latency decomposition (engine is free,
  latency is the network) supports.
- **Result (single fresh clean run, optimization.nol on both engines, oracle-adjudicated):**
  Themis 15,343 tokens / 117 KB / **1000-1000 oracle**, -64.3%; Aergia 17,512 / 131 KB
  / **124-1000** (876 diverge), -59.3%; both kept 27 / masked 973. Latency: engine
  <0.3 ms both (upper bound); ~97% of a cold call is TLS+RTT; pooling is 3x.
- **Aergia corrupts on strip** - every one of the 876 divergences is a strip rule,
  zero on redaction; leaves the tail of a stripped literal (`default.`->`ault.`).
  Finding: `demos/benchmark/findings/aergia-strip-corruption.md`.
- **Verifier:** `demos/benchmark/verify-oracle.py`. **Report appendix** is a full
  "Show your work" receipts block (breakdown + oracle stamp, strip rules with counts,
  before/after chunks with highlighted corruption, aggregate). Notes:
  `demos/benchmark/DEMO-NOTES.md`. Runner: `demos/benchmark/run-live.sh`.

## Data Point 2 - pre/post-inference control - DONE, pending stats talk (`demos/benchmark/datapoint2/`)

- Copied out of the kit. Flow: `Prompt -> Pre-control -> Model stub -> Post-control ->
  Output`; actions block/route/mask/tag at BOTH edges.
- **Real-engine modes** `themis_api_infer` / `aergia_api_infer` (`go/engine_infer.go`):
  call the engine directly at both control points, derive the action from the
  `boundary.nol` sentinels. Runner: `datapoint2/run-live.sh`. Direct engine calls, no
  adapter (DP2 owns its Go harness).
- **Result (52 prompts, both live engines):** **Themis == Aergia == oracle, 52/52.**
  0 field-diffs (byte-parity) AND both match the framework oracle at both edges
  (`datapoint2/verify-oracle.py`). No corruption (boundary redacts to sentinels, not
  strip-to-empty). Pre: 31 allow / 5 block / 12 route / 4 tag; post (of 35 inference):
  20 allow / 4 block / 11 tag. 17/52 stopped before inference. 379 prompt tokens fwd,
  350 output tokens out.
- **Honest listMatch scope:** literal engines mask 0 arbitrary cards (only known
  literals); re2 masks 12, nol8sim 9. Also exact/case-sensitive: `Send raw notes...`
  (capital S) was allowed pre / caught post. tag = redact-to-marker (not metadata).
  All in `datapoint2/DEMO-NOTES.md`.
- **Report:** `datapoint2/run.json` (`kind: dp2`) via the shared make-report.py; adds
  `boundary()`, `flows()` (agent-action cards with colored badges), `dp2_appendix()`.
  Regenerate: `python demos/benchmark/make-report.py demos/benchmark/datapoint2/run.json
  demos/benchmark/datapoint2/pre-post-report.html`.
- **Flow cards fixed (2026-07-22):** the block/route flow cards used to render fake
  MODEL/POST rows (incl. a misleading "POST ALLOW"); now stopped flows show one clear
  outcome line and full-journey cards lead. That WAS the user's specific screenshot
  complaint.
- **>>> STATS - strategic direction set (2026-07-22), reframe still TO DO.** The user
  steered the stats concern into positioning. Decisions ([[demo-positioning-and-data-
  strategy]]): (1) Position NOL8 as **"the deterministic guardrail for known policy"** -
  100% precision/recall on the KNOWN set, wire speed, deterministic; complementary to
  (not competing with) classifiers. Frame listMatch as a differentiator, not an
  apology. (2) **Do NOT headline test-set counts** ("34/52 governed", "17/52 stopped")
  - they describe the harness, not NOL8. Lead with what NOL8 EARNED: parity vs the
  incumbent (52/52 identical), oracle-correctness (52/52), payload + calls avoided.
  (3) **Every use case needs >1 dataset:** the functional-test set we have (keep) PLUS
  a **representative-policy** dataset (realistic customer policy/traffic) - user said
  yes to drafting these. (4) **Classification is a separate concern** (partner/roadmap/
  own data point); **regex IS on the NOL8 roadmap** ("soon") but not today, so keep all
  copy listMatch-honest and do NOT overrotate to the future.
  **DONE (2026-07-22):** (a) **Stat band + copy reframed** to the deterministic-
  guardrail story - stats are now 52/52 oracle-verified, 100% incumbent match, 0 false
  pos/neg, 2 edges (NO test-set counts up top; moved to the appendix, labeled as
  test-data composition). Headline "The deterministic guardrail for the model
  boundary"; takeaways carry the deterministic-vs-probabilistic (complementary to
  classifiers) framing. (b) **Representative-policy dataset built + committed:**
  `demos/benchmark/datapoint2/representative/` (insurer claims-support scenario, 9
  curated lists + 24 real-shaped prompts incl. false-pressure rows); generator takes
  `--list-dir/--output`; `run-live.sh` takes `DP2_INPUT/LISTS/RESULTS`; policy
  `demos/policies/boundary-representative.nol` generated + safety-checked. Local modes
  validated it (masking FIRES now: listguard masked 3 / blocked 2 / routed 3 / tagged 2
  - the gap the functional-test set had). See representative/README.md.
  **PENDING: the LIVE engine run of the representative set** - blocked 2026-07-22
  because both data planes (:443/:444) went unreachable from EC2 (curl times out,
  http_code 000; transient infra/network - they worked earlier today). Retry when
  connectivity returns (command in representative/README.md; policy already deployed).

## Data Point 3 - agent-to-agent control - PLANNED (`demos/benchmark/DP3-PLAN.md`)

- **Not built.** Full build spec in `demos/benchmark/DP3-PLAN.md`. DP3 is DP2
  generalized: governance at every agent hop (handoff), tool call, and final output
  across `Triage -> Research -> Decision -> Action -> Final`. Kit pack:
  `~/Code/nol8/preindex-benchmark-kit/datapoint3_agent_mesh_pack_v1` (same structure as
  DP1/DP2; literal policy lists; modes nocontrol/re2_mesh/listmesh/nol8sim_agent).
- **Build mirrors DP2:** mesh policy generator (-> `mesh.nol`), real-engine modes
  `themis_api_mesh`/`aergia_api_mesh` (`engine_mesh.go`, engine at each stage, derive
  per-stage action from sentinel), run.json + report (`kind: dp3`, a mesh-flow
  section), oracle-verify (framework matcher per stage), DEMO-NOTES + runbook.
- **agentic-mesh-lab (Track B)** = a SEPARATE, larger visual demo
  (`~/Code/nol8/agentic-mesh-lab`, PRD-stage): side-by-side traditional-vs-Nol8
  insurance-claim workflow with a UI. Its framing ("AI Data Plane governing agent
  communication"; "reduction before delivery, downstream agents receive only what they
  need") should shape DP3 - push DP3 to measure **payload reduction across hops**, not
  just action counts. The lab consumes DP3's wiring/numbers; building it is out of the
  benchmark line's scope. See DP3-PLAN.md "Open decisions for the user".

---

# Next horizon

1. **DP2 stats conversation** with the user (open item), then DP2 is fully done.
2. **Build DP3** per `demos/benchmark/DP3-PLAN.md` (reuses everything from DP2).
3. **Throughput / scale benchmark** - concurrency + server-side timing, the test that
   would let NOL8 (FPGA) visibly pull ahead of RE2. The honest "next measurement".
4. **agentic-mesh-lab (Track B)** - the richer visual demo; larger, user-driven; decide
   timing once DP1-3 are complete.
5. **EC2 general tidy** (checkout reconciled; just housekeeping).

---

# Immediate Next Actions

1. **Clear the data-plane outage, then verify** with `bash demos/check-engines.sh` on
   EC2 (want all checks OK). Then run the pending LIVE representative run (command in
   `datapoint2/representative/README.md`) and DP2 is fully done.
2. **DP2 stats/copy reframe + representative dataset are DONE** (this session). Apply
   the same positioning + multi-dataset principle to DP1/DP3.
   [[demo-positioning-and-data-strategy]]
3. **Build DP3** (copy pack out, mesh policy generator, engine modes - follow
   DP3-PLAN.md).
4. Announce before every git command ([[announce-before-git]]).

**Not blocking (user handles):** send ISSUE-004 to engineering (report in
`docs/issues/`, Slack drafts in `docs/issues/internal/outbound-slack-comms.md`).

---

# Decisions Made - Do Not Reopen

- Five-stage lifecycle; `validate` is the only supported interface; scripts are
  transport; manifest-driven state written atomically.
- Do NOT adjust validation expectations to make ISSUE-004 pass.
- Generation is canonicalised (FW-7): output depends on seed + config semantics.
- `artifacts/runs/` is not tracked; survivors go in `artifacts/evidence/`.
- Control-plane TLS self-signed is OBS-1, deliberately not a finding; `--insecure` required.
- Demo scope is listMatch only; the report is NOL8 vs RE2, never "two NOL8 engines".
- Benchmark integrity: same policy + dataset to every engine; report divergence
  honestly. [[benchmark-integrity-no-rigging]]
- DP1 leads with the optimization use case; governance parity is the trust anchor.
- DP2/DP3 real-engine modes call the engine directly in Go (no Python adapter).
- The report renderer is SHARED (`make-report.py`, `kind`-dispatched); do not fork it
  per data point.

---

# Repository Hygiene

`validate generate` writes to `artifacts/runs/<RUN_ID>/` (gitignored). Survivors ->
`artifacts/evidence/`. Gitignored: `.env`, `keys/`, `.venv/`, `artifacts/runs/`,
`*.pdf`, `handoff/`, and under `demos/benchmark/`: `**/results/*`, `**/report/
report.html`, `**/report/report_data.json`, `**/go/benchmark_runner`, `**/.gocache/`,
`pre-index-report.html`, `datapoint2/pre-post-report.html`. **Do not `git add -A`;
stage specific files.**

Tests: **236**, all passing.
```bash
source .venv/bin/activate && python -m unittest discover -s tests -q
```
