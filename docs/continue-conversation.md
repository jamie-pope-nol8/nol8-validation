# Continue Conversation

Last Updated: 2026-07-21

Durable memory of the project, so a new session (or a post-compaction session)
can continue without reconstructing context from chat history.

> **Handoff at 2026-07-21 (sixth handoff).** All code-review tiers done. The
> pre-index demo runs end-to-end against live engines and produces a clean report.
> **236 framework tests passing.**
>
> **Current focus: the demo environment.** Data Point 1 (pre-index) is built,
> benchmarked, and has an **on-brand report pipeline** (`run.json` +
> `make-report.py`, Design template, web + PDF, collapsible raw-data appendix).
> **#3 DONE (2026-07-21):** the optimization policy cut Themis's forwarded payload
> 64.3% (15,343/43,005 tokens) and this is now **oracle-verified** — Themis matches
> an independent oracle **1000/1000 byte-for-byte**; the RE2 baseline (Aergia)
> **corrupts 876/1000** on the strip rules (leaves match tails, `default.`→`ault.`),
> every divergence a strip, zero on redaction. Verifier: `demos/benchmark/
> verify-oracle.py`. Finding logged: `demos/benchmark/findings/aergia-strip-
> corruption.md`. Story is honest and earned ([[benchmark-integrity-no-rigging]]).
> **NEXT:** (a) sync the updated Design template in `/private/tmp/HTML Report
> redesign/`; decide whether DP1's report leads with governance (current) or
> optimization (stronger, needs the divergence told carefully). Then: Datapoint 2
> (scoped), agentic-mesh-lab review, Datapoint 3.
>
> **Tenant state:** the 42-rule **starter policy** is deployed to BOTH engines
> (NOL8/Themis :443 and RE2/Aergia :444). Not the 5,000-rule qualification.
>
> **BLOCKERS / operational debt:**
> - **`git push` is blocked by the auto-mode classifier this session.** Announce
>   before every git command (see Operating Rules + [[announce-before-git]]); do
>   NOT rsync around it (that caused the EC2 divergence below). The user wants to
>   fix the push permission.
> - **EC2 checkout is diverged** from a earlier rsync workaround: benchmark files
>   are untracked there and a few tracked files are locally modified, so `git pull`
>   aborts. Reconciliation procedure is in Environments below.

This file is project *state*. Three companions carry the rest:

| question | document |
|---|---|
| Something is broken right now | `docs/TROUBLESHOOTING.md` |
| What have we found? | `docs/FINDINGS.md` (THM-n product, OPS-n their tooling, FW-n ours, OBS-n non-findings) |
| Where is any other document? | `docs/README.md` |

## Maintaining this file

- **On "update the project":** rewrite this file wholesale to current state. Do
  not append or preserve stale sections - accuracy over history.
- **Every turn:** keep it current as work happens, so `/compact` is safe anytime.

---

# CRITICAL: engine identity (I kept getting this wrong)

- **Themis == NOL8** - the FPGA product we sell. Data plane `:443`.
- **Aergia == RE2** - a *real RE2 (regex) engine* the team stood up and named
  Aergia, used as the **known incumbent** to benchmark NOL8 against. Data plane
  `:444`.
- There is **NO "Themis + Aergia" pair of NOL8 engines.** It is **NOL8 vs RE2**.
- **Demo scope: listMatch (literal) only** - that's what NOL8 does today; regex is
  NOT a NOL8 capability yet. RE2/Aergia *is* a regex engine, but we run it on the
  same literal policy as the incumbent reference. See [[demo-scope-listmatch-only]].

---

# The Short Version

Two separate tracks.

**1. Product validation (Themis/NOL8 defects).** Headline: ISSUE-004 - two rules
matching overlapping text make the runtime write the replacement at the wrong
offset and destroy adjacent data, silently, HTTP 200. **Open, not yet reported to
engineering** (the send is the user's; docs are ready). Full issue register in
`docs/issues/`. The framework itself had defects (all fixed); a clean 5,000-rule /
10,000-record qualification passes 100%.

**2. Demo environment (the current work).** A pre-index governance demo that runs
NOL8 (Themis) against the RE2 incumbent (Aergia) on real endpoints, plus a latency
decomposition proving the engine is sub-millisecond and latency is the network.

---

# CRITICAL CONTEXT - who wrote what

**Engineering did not write this repository.** They handed over the v1.0 sandbox
with docs and an invitation to use it. This validation framework is ours.
Consequences for anything sent to engineering (the `docs/issues/` register already
follows this):
- Never reference a path in this repository.
- Inline reproductions as literal curl against their endpoints and token.
- Mention the framework only as provenance for finding the defect at scale.

---

# Session Operating Rules

- **Announce before ANY git command (local or remote)** and run it plainly (not
  buried in a compound command), so the user can see why it's blocked and fix it.
  Do NOT rsync around a blocked push. [[announce-before-git]]
- Work one action at a time. End responses with a clear next action.
- `validate` is the product surface. Do NOT call `scripts/*.sh` directly.
- Don't restart resolved architecture discussions or replace working tooling.
- **Repro/command docs aren't "done" until run as written.**

---

# Environments

| | Mac | EC2 |
|---|---|---|
| purpose | development, commits | execution against the engines |
| path | `~/Code/nol8/nol8-validation` | `/opt/nol8/nol8-validation` |
| python | 3.12 | 3.14.4 |
| go | (none) | 1.22.5 at `$HOME/.local/go` (on `.bashrc` PATH) |
| host | - | `nol8-demo` (in `~/.ssh/config`; hostname `data-streamer`, 10.8.10.40) |

Normal flow: edit/commit on Mac, `git push`, `git pull` on EC2, execute there.
The Go demo benchmark runs on EC2 only (the box that can reach the engines).

**Git push is blocked this session** (auto-mode classifier). Until fixed, the Mac
has unpushed commits and EC2 cannot pull cleanly.

**EC2 reconciliation (run once push works, or to clean up now).** EC2 has untracked
benchmark files + locally-modified tracked files from the earlier rsync workaround,
so `git pull` aborts. Since EC2 has no unique work (only stale rsync copies), align
it to the remote (gitignored `results/`, `report.html`, `.env` survive - no `-x`):
```
cd /opt/nol8/nol8-validation
git fetch origin
git clean -fd demos/benchmark      # remove untracked rsynced source
git reset --hard origin/main       # discard local tracked mods, match remote
git status                         # expect clean
```

Long-running SSH commands must be detached (`setsid nohup ... </dev/null >log 2>&1 &`)
and polled via a log marker. Detached adapters/servers started in one ssh session
die when it closes - run adapter+harness inside ONE ssh command (run-live.sh does).

---

# Services & ports (confirmed 2026-07-21)

| | address | notes |
|---|---|---|
| **NOL8 (Themis, FPGA)** data plane | `tenant001-v1demo.nol8.net:443/v1/process` | valid Amazon cert |
| **RE2 (Aergia)** data plane | `tenant001-v1demo.nol8.net:444/v1/process` | valid cert, SAME contract |
| Themis policy control plane | `themis.sales.nol8.cloud:8444/policy` | self-signed (CN ip-172-31-40-100) - needs `--insecure` |
| Aergia policy control plane | `aergia.sales.nol8.cloud:8444/policy` | self-signed (CN ip-172-31-42-162) - needs `--insecure` |
| themis host (`themis-demo`, ssh) | 10.10.1.254 | runs iris+apollo+policyd; treat with care |

Contract (both engines): `POST {"message": text}` -> `{"jid":.., "frameId":1,
"last":true, "result":{"message": processed}}`. Config in `config/demo.env`
(`THEMIS_PROCESS_ENDPOINT`=:443, `AERGIA_PROCESS_ENDPOINT`=:444,
`*_POLICY_ENDPOINT`, `THEMIS_ALLOW_INSECURE_TLS=1`); tokens in `.env`
(`THEMIS_TOKEN`, `AERGIA_TOKEN`). Aergia's :444 data plane has a **few-second
reload propagation delay** after a policy deploy.

---

# CLI

```bash
validate generate --config <yaml> [--rules N] [--records M]
validate policy   --run <RUN_ID> | --file <path.nol> | --status  [--target {themis,aergia}]
validate run      --run <RUN_ID> [--limit N] [--skip-preflight]
validate compare  --run <RUN_ID> [--replacement-max-length 15]
validate report   --run <RUN_ID>
```

Fully documented in `README.md`. Transport scripts read `NOL8_CONFIG_FILE`/
`NOL8_SECRETS_FILE` (default `config/demo.env`, `.env`); the token is written to a
`0600` temp file and passed with `-H @file` (never on argv - FW-9).

---

# Product-validation state

## Runtime outage 2026-07-20 - RESOLVED
apollo boots with its data plane PAUSED and un-pauses only when a policy commits.
Deploy any policy to restore. Do NOT restart services for a 503. Runbook in
`docs/TROUBLESHOOTING.md` (OPS-1..3); `validate run` now pre-flights.

## Authoritative qualification - 20260720T221534714262Z
5,000 rules / 10,000 records / customer-record-csv / seed 42. 10,000 PASS, 0
inconclusive, 0 collisions, report banner PASS. Regenerates byte-identically from
seed 42 (post-FW-7). Policy + report promoted to `artifacts/evidence/`; policy SHA
`27fe47db`. NOTE: the tenant currently has the 42-rule demo starter deployed, not
this - restore only if the framework needs a known state.

## ISSUE-004 - OPEN, engineering docs ready but NOT SENT
Overlapping/containing literals corrupt output (wrong start offset), silently, 200.
Our generator stopped producing overlapping catalogs so our runs don't trip it, but
the Themis defect is untouched. Engineering-facing report:
`docs/issues/ISSUE-004-overlapping-matches-corrupt-output.md` (self-contained, inline
curl with `--insecure` on the control plane, verified live). Investigation:
`docs/issues/internal/ISSUE-004-corruption-investigation.md`.

## Issue register + code review
`docs/issues/` = `ISSUE-001..007`, one emailable self-contained report each,
aligned 1:1 to THM-1..7. Internal/repo-referencing material in `docs/issues/
internal/` (incl. `outbound-slack-comms.md`). All code-review tiers (0-4 + pragmatic
5) DONE - see `docs/CODE_REVIEW_PLAN.md`. FW-9 (token off argv), FW-10 (dead scripts
removed), FW-11 (atomic-write/JSONL consolidation + e2e test), FW-6 (grouped report
failures), FW-7 (key-order-independent generation).

---

# Demo environment - THE CURRENT WORK (in `demos/`)

Self-contained, isolated from `framework/`; can graduate to its own repo. Reuses
live endpoints/config, does not import from `framework/`.

## Pieces (all built + live-verified)

- **`demos/themis-adapter/adapter.py`** - bridges the benchmark contract
  `{"text"}->{"action","text"}` to the engine contract `{"message"}->{result.
  message}`. Derives keep/mask (drop/route via optional sentinel tokens). Reads
  `PROCESS_ENDPOINT`/`PROCESS_TOKEN` (generic; falls back to `THEMIS_*`) so one
  adapter can serve either engine. 9 network-free tests.
- **`demos/policies/`** - `build_policy.py` turns `values/*.txt` (7 categories, 42
  known values, copied from the kit) into a SAFE literal `.nol` policy. Guards:
  tokens <=15 chars/distinct (ISSUE-005), no contained literals (ISSUE-004).
  Output `starter-known-values.nol` = 42 rules. Engine-agnostic (same file loads to
  NOL8 and RE2). 7 tests.
- **`demos/benchmark/datapoint1/`** - the pre-index benchmark, copied OUT of
  `~/Code/nol8/preindex-benchmark-kit` (never edit the kit). Go harness with
  per-engine modes `themis_api`/`aergia_api` (added to our copy of `benchmark.go` +
  `nol8_client.go`), corpus (1,000 chunks), report generator.
- **`demos/benchmark/run-live.sh`** - ONE command on EC2: deploys the starter
  policy to both engines, starts one adapter per engine (8799->NOL8:443,
  8800->RE2:444), runs the harness, builds the kit report, cleans up. Modes default
  `nofilter re2 themis_api aergia_api`.
- **`demos/benchmark/latency-decompose.py`** - isolates raw engine time by measuring
  network-RTT / warm-pooled / cold-per-call and subtracting transport.
- **On-brand report pipeline (Design-approved).** `run.json` (data contract) +
  `make-report.py` -> `pre-index-report.html`, a self-contained on-brand report
  (NOL8 design system: charcoal + green, Space Grotesk / Google Sans; fonts, logos,
  hero pattern inlined). Reimplemented from the Design handoff `/private/tmp/HTML
  Report redesign/` (Option B - from its `run.json` contract, not its `support.js`
  runtime). **Web (default)** = open the HTML (dark, sticky nav, engine tabs);
  **deck/leave-behind** = browser Export -> PDF (the `@media print` block forces
  the light cream palette). Regenerate: `python demos/benchmark/make-report.py`.
  Tracked: `run.json`, `make-report.py`, `brand/` (subset woff2 + logos + pattern);
  the rendered HTML is gitignored. Brand voice enforced (no em dashes/exclamations/
  emoji; Aergia = "RE2 baseline", never a NOL8 product). Verified in dark + light +
  PDF via headless Chrome. Artifact:
  https://claude.ai/code/artifact/2feb6e5a-b3d6-466b-b4db-cc3daa6a735c (local file
  is authoritative). Copy content lives in `run.json` (three approaches: Do nothing
  / Aergia RE2 baseline / NOL8 Themis FPGA + latency decomposition). Includes a
  **collapsed "Full benchmark data" appendix** (raw per-approach table, Show
  toggle, auto-expanded in print). Report tracks the Design template in `/private/
  tmp/HTML Report redesign/` (re-check it for updates - last synced its 13:28
  change: takeaways are a fixed 2-column grid). The appendix measures **data
  forwarded** (payload that becomes embeddings), NOT test-harness CPU/RSS (those
  only differ because of the client+adapter we add to test, so they mislead -
  dropped 2026-07-21). **Open story question:** DP1 is "Pre-Index OPTIMIZATION"
  (ship less to embeddings = fewer vectors = lower cost), but our demo policy
  REDACTS known values (governance, length-neutral, ~2.5% volume cut). The strong
  "clean it up, ship much less" story needs the policy to DROP low-value content
  (filler/boilerplate): kit `re2` stripping boilerplate hit 7.2%, `listmatch`
  drop/route hit 52%. Themis is literal (can drop KNOWN boilerplate via a drop
  sentinel); broad filler-dropping is pattern-based (RE2/Aergia). Decide whether DP1
  leads with governance (current) or optimization (add drop rules).
  **DROP verified live 2026-07-21:** policy `"password" -> "[DROP]"` on Themis; a
  message with "password" came back `here is your [DROP]: 1324343` on direct curl,
  and `{"action":"drop","text":""}` through the adapter with `THEMIS_DROP_TOKEN=
  "[DROP]"` (dropped chunk = 0 forwarded). So chunk-level drop works. NOTE: Themis
  is literal, so it can map a specific literal to `[DROP]` (drop the whole chunk) or
  to `""` (strip that text inline, keep the rest - not yet tested). Tenant currently
  has the 1-rule drop-test policy, NOT the 42-rule starter - redeploy the starter or
  the new optimization policy before the next benchmark run.
  **OPTIMIZATION POLICY BUILT + BIG FINDING (2026-07-21):**
  `demos/policies/build_optimization_policy.py` -> `optimization.nol` = 42
  governance redact rules + 10 strip rules (top repeated filler sentences -> "").
  Run with `POLICY=demos/policies/optimization.nol bash demos/benchmark/run-live.sh`.
  Result: **Themis forwards 15,343 tokens (64.3% reduction)**, huge "ship less"
  win. BUT **Themis and Aergia DIVERGE** (Aergia 17,512 / 59.3%): **Aergia (RE2)
  CORRUPTS output on multi-strip** - leaves match tails ("ault." from "default.",
  "ssed early." from "suppressed early."); Themis strips cleanly to "\n\n".
  Reproducible live post-propagation (direct :443 vs :444). This is a NEW finding
  distinct from ISSUE-004 (Themis-on-overlapping-redaction). Parser note: trailing
  inline comments after a rule are rejected (comments must be own-line).

  **USER DECISION (2026-07-21): do NOT rig the test to force parity.** Same policy,
  same dataset, both engines (listMatch only). If Themis is clean and Aergia
  corrupts on the same input, that is a legitimate result - report it honestly. Do
  not pick a "safe" policy to hide the divergence. See [[benchmark-integrity-no-
  rigging]]. Chosen path = #3.

  **>>> #3 DONE (2026-07-21) - verified, honest, logged:**
  `demos/benchmark/verify-oracle.py` adjudicates each engine's recorded output
  against the framework's Aho-Corasick oracle (`framework/policy/matching.py`,
  leftmost-longest non-overlapping literal replacement, `""` for strip). Run on EC2
  against the optimization outputs: **Themis 1000/1000 match oracle** (its 15,343-
  token / 64.3% result is provably correct); **Aergia 876/1000 diverge, every one a
  strip rule, zero redact-only** - Aergia keeps the tail of a stripped literal
  (`default.`→`ault.`, `suppressed early.`→`ssed early.`) and forwards garbage into
  the vectors. Finding: `demos/benchmark/findings/aergia-strip-corruption.md`
  (self-contained, careful framing: Aergia is our RE2 baseline; RE2-inherent vs
  Aergia-harness is an open follow-up). DEMO-NOTES has the "optimization variant"
  section. Reproduce: `POLICY=demos/policies/optimization.nol
  MODES="nofilter re2 themis_api aergia_api" bash demos/benchmark/run-live.sh` then
  `python demos/benchmark/verify-oracle.py --results demos/benchmark/datapoint1/
  results themis_api aergia_api` (EC2). Tenant has `optimization.nol` on both engines.
  **Open story decision:** does DP1's report lead with governance (current headline,
  drop-in parity) or optimization (64% ship-less + the correctness gap)? User's call.
- **`demos/benchmark/DEMO-NOTES.md`** - the narrative + numbers + honesty guardrails.
- The kit's own `datapoint1/report/report.html` template is hardcoded to old kit
  modes (`nol8sim`/`listmatch`) - NOT for showing; superseded by
  `pre-index-report.html`. Fixing that template is deferred.

## The result (measured, 2026-07-21, 1,000 chunks)

Same literal policy on both engines -> **NOL8 and RE2 produced BYTE-IDENTICAL
output (1000/1000)**, 535 chunks governed, 0 errors. Latency decomposed (N=100,
medians): engine processing **< 0.3 ms on both** (below the network floor); ~97% of
a cold call is TLS handshake (~4.7 ms) + network RTT (~2.1 ms). Connection pooling
alone is 3x (cold 7.17 -> warm 2.38 ms). **The story: NOL8 matches the incumbent
byte-for-byte; the engine is free; latency is a network problem** (the Megaport
hook). Honest gaps: do NOT quote 138 chunks/sec as an engine rate; the per-call
NOL8-vs-RE2 latency gap is network jitter, not engine speed; the FPGA's real edge
(throughput under concurrent load) is NOT YET measured.

---

# Next horizon

1. **New report template (incoming from user)** - Claude-designed, on-brand. When it
   arrives: reskin `pre-index-report.html` to it, then add a **web (default) / deck**
   output toggle. Keep it simple - "deck" can be the same page saved as PDF for a
   leave-behind POC readout. Don't overthink the toggle.
2. **Throughput / scale benchmark** - the concurrency + server-side-timing test that
   would let NOL8 (FPGA) visibly pull ahead of RE2. The honest "next measurement".
3. **Datapoint 2 - Pre/Post-Inference Control (SCOPED, build next).** Kit pack:
   `~/Code/nol8/preindex-benchmark-kit/datapoint2_pre_post_inference_pack_v1`. Flow:
   `Input -> Pre-Inference Control -> Model Stub -> Post-Inference Control -> Output`
   (govern what reaches the model AND what leaves; prompt-injection in, egress out).
   Modes map onto our story 1:1: `nocontrol`=Do nothing, `re2_guard`=RE2 (Aergia),
   `nol8_api_infer`=NOL8 (Themis) via the SAME adapter. **Reuse:** adapter unchanged,
   policy generator (+injection/egress phrase lists), report pipeline (new run.json).
   **New:** the pack's corpus (ships), a boundary-tuned policy, pre/post report copy.
   Highest reuse, closest to DP1 - do this first.
4. **Agentic-mesh-lab review** - user's repo at `/Users/jamiepope/Code/nol8/
   agentic-mesh-lab` (small, checked into GitHub). Review non-destructively; it
   overlaps DP3, so it should inform DP3's shape. Do after DP2.
5. **Datapoint 3 - Agent-to-Agent Control (SCOPED, build last).** Kit pack:
   `datapoint3_agent_mesh_pack_v1`. Flow: `Triage -> Research -> Decision -> Action`
   agents; govern what moves between agents/tools (agent-mesh, ISSUE-006). Same
   harness pattern but an earlier first pass (fewer scripts, no live runtime).
   Governance at each inter-agent hop via the adapter. More design; shape it after
   the agentic-mesh-lab review.
5. **EC2 cleanup** - reconcile the git divergence (procedure in Environments), then a
   general tidy of the checkout.

Conceptual threads: "how do I do this with my data?" -> build toward invariants
("no unredacted SSN pattern in output") + synthetic canaries; agent-mediated
integration is the fastest-growing buyer interest (ISSUE-006); the data-path
question (OBS-2, Comm 2) shapes a realistic demo.

---

# Deferred / backlog

- Full `main.py` layer-split (Tier 5 remainder) - structural, skip until it matters.
- Emailable HTML render of `docs/issues/` with copy buttons into gitignored
  `handoff/`.
- Pre-generated demo datasets in t-shirt sizes.
- drop/route via sentinel-token policy rules (adapter already supports the tokens).

---

# Immediate Next Actions

1. **Build Datapoint 2 (pre/post-inference)** - scoped in Next horizon item 3. Copy
   the pack OUT of the kit into `demos/benchmark/datapoint2/`, point `nol8_api_infer`
   at the adapter, author a boundary policy + run.json, render the report.
2. **Review agentic-mesh-lab** (`/Users/jamiepope/Code/nol8/agentic-mesh-lab`),
   then build Datapoint 3.
3. Git push works now (was flaky); announce before every git command
   ([[announce-before-git]]). EC2 reconciled; normal `git pull` there works.

**Not blocking (user handles):** send ISSUE-004 to engineering (report in
`docs/issues/`, Slack drafts in `docs/issues/internal/outbound-slack-comms.md`).

---

# Decisions Made - Do Not Reopen

- Five-stage lifecycle; `validate` is the only supported interface; scripts are
  transport; manifest-driven state written atomically.
- Do NOT adjust validation expectations to make ISSUE-004 pass.
- A run where every request fails is deliberately NOT a stage failure.
- An unconfirmable record is INCONCLUSIVE, never PASS/FAIL.
- Generation is canonicalised (FW-7): output depends on seed + config semantics.
- `artifacts/runs/` is not tracked; survivors go in `artifacts/evidence/`.
- TLS self-signed control planes are OBS-1, deliberately NOT a finding for this
  sandbox; `--insecure` required to reach them.
- Demo scope is listMatch only; the report is NOL8 vs RE2, never "two NOL8 engines".

---

# Repository Hygiene

`validate generate` writes to `artifacts/runs/<RUN_ID>/` (gitignored). Survivors go
in `artifacts/evidence/`. Gitignored: `.env`, `keys/`, `.venv/`, `artifacts/runs/`,
`*.pdf`, `handoff/`, and under `demos/benchmark/`: `**/results/*`, `**/report/
report.html`, `**/go/benchmark_runner`, `**/.gocache/`. **Do not `git add -A`;
stage specific files** so generated artifacts never ride along.

Tests: **236**, all passing.
```bash
source .venv/bin/activate && python -m unittest discover -s tests -q
```
