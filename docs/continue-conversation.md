# Continue Conversation

Last Updated: 2026-07-21

Durable memory of the project, so a new session (or a post-compaction session)
can continue without reconstructing context from chat history.

> **Handoff at 2026-07-21.** Two tracks: (1) product validation (Themis/NOL8
> defects) is stable, **236 framework tests passing**; (2) the **demo environment**
> is the active work.
>
> **Data Point 1 (pre-index) is DONE and shipped.** It runs end-to-end against the
> live engines and produces an on-brand report that now **leads with the
> optimization use case** (clean the data before it becomes embeddings): Themis
> forwards **64.3% fewer tokens** and is **oracle-verified correct 1000/1000**,
> while the RE2 baseline (Aergia) **corrupts 876/1000** on the strip. Every number
> comes from a **single fresh clean run** (2026-07-21) and the report's appendix is
> a full "show your work" receipts block. See "Demo environment / DP1" below.
>
> **Current focus: Data Point 2 (pre/post-inference control).** The kit pack is
> **copied out** into `demos/benchmark/datapoint2/`. Scoped and ready to build; the
> real-engine wiring is the main task (see "DP2" below).
>
> **Template tweak applied (2026-07-21):** the user's small change was the stat band
> background - it was on the full-width `<section>` (`background:var(--card)`), so the
> card surface bled edge-to-edge past the outer cards. Moved it onto the stat GRID so
> it stops at the first card's left border, with page background beyond. Full-width
> top/bottom rules kept. Both themes. NOTE our report has intentionally diverged from
> the Design template (optimization vs the template's governance copy); our renderer
> is our own `make-report.py`.

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

# CRITICAL: engine identity (kept getting this wrong)

- **Themis == NOL8** - the FPGA product we sell. Data plane `:443`.
- **Aergia == RE2** - a *real RE2 (regex) engine* the team stood up and named
  Aergia, used as the **known incumbent** to benchmark NOL8 against. Data plane
  `:444`.
- There is **NO "Themis + Aergia" pair of NOL8 engines.** It is **NOL8 vs RE2**.
- **Demo scope: listMatch (literal) only** - that's what NOL8 does today; regex is
  NOT a NOL8 capability yet. RE2/Aergia *is* a regex engine, but we run it on the
  same literal policy as the incumbent reference. See [[demo-scope-listmatch-only]].
- **Benchmark integrity:** same policy + same dataset flow to every engine. If they
  behave differently, we report it honestly; we do NOT tune the test to force parity
  or hide divergence. Verifying our own engine against an independent oracle is the
  integrity check pointed at us, not rigging. See [[benchmark-integrity-no-rigging]].

---

# The Short Version

Two separate tracks.

**1. Product validation (Themis/NOL8 defects).** Headline: ISSUE-004 - two rules
matching overlapping text make the runtime write the replacement at the wrong
offset and destroy adjacent data, silently, HTTP 200. **Open, not yet reported to
engineering** (the send is the user's; docs are ready). Full issue register in
`docs/issues/`. The framework itself had defects (all fixed); a clean 5,000-rule /
10,000-record qualification passes 100%.

**2. Demo environment (the current work).** DP1 (pre-index) done and shipped. DP2
(pre/post-inference) kicked off. DP3 (agent-mesh) scoped for last.

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

- **Announce before ANY git command (local or remote)** and run it plainly, so the
  user can see it. Do NOT rsync around a blocked push. [[announce-before-git]]
  (Push works this session; keep announcing anyway.)
- **Every demo must be SA-runnable** - documented runbooks, copy-paste commands, the
  two-host workflow, so the user and other SAs can run it live. [[demos-must-be-sa-runnable]]
- The Themis tenant is the user's disposable sandbox - overwrite policy freely; do
  not reflexively restore it. [[sandbox-policy-overwrite]]
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

Normal flow: edit/commit on Mac, `git push`, `git pull` on EC2, execute there. The
Go demo benchmark runs on EC2 only (the box that can reach the engines). Git push
and pull both work this session; EC2 is reconciled and current with origin/main.

**SSH note:** `nol8-demo` depends on the VPN tunnel; if `data-streamer.sales.nol8.cloud`
stops resolving, the VPN dropped - reconnect it. Long-running SSH commands must be
detached (`setsid nohup ... </dev/null >log 2>&1 &`) and polled via a log marker;
adapters/servers started in one ssh session die when it closes, so run adapter +
harness inside ONE ssh command (run-live.sh does).

---

# Services & ports (confirmed 2026-07-21)

| | address | notes |
|---|---|---|
| **NOL8 (Themis, FPGA)** data plane | `tenant001-v1demo.nol8.net:443/v1/process` | valid Amazon cert |
| **RE2 (Aergia)** data plane | `tenant001-v1demo.nol8.net:444/v1/process` | valid cert, SAME contract |
| Themis policy control plane | `themis.sales.nol8.cloud:8444/policy` | self-signed - needs `--insecure` |
| Aergia policy control plane | `aergia.sales.nol8.cloud:8444/policy` | self-signed - needs `--insecure` |
| themis host (`themis-demo`, ssh) | 10.10.1.254 | runs iris+apollo+policyd; treat with care |

Contract (both engines): `POST {"message": text}` -> `{"jid":.., "frameId":1,
"last":true, "result":{"message": processed}}`. Config in `config/demo.env`
(`THEMIS_PROCESS_ENDPOINT`=:443, `AERGIA_PROCESS_ENDPOINT`=:444, `*_POLICY_ENDPOINT`,
`THEMIS_ALLOW_INSECURE_TLS=1`); tokens in `.env` (`THEMIS_TOKEN`, `AERGIA_TOKEN`).
Aergia's :444 data plane has a **few-second reload propagation delay** after deploy.

**Tenant state:** `demos/policies/optimization.nol` is deployed to BOTH engines
(from the last fresh DP1 run). Not the 5,000-rule qualification.

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

## Authoritative qualification - 20260720T221534714262Z
5,000 rules / 10,000 records / customer-record-csv / seed 42. 10,000 PASS, 0
inconclusive, 0 collisions, report banner PASS. Regenerates byte-identically from
seed 42 (post-FW-7). Policy + report in `artifacts/evidence/`; policy SHA `27fe47db`.

## ISSUE-004 - OPEN, engineering docs ready but NOT SENT
Overlapping/containing literals corrupt output (wrong start offset), silently, 200.
Our generator stopped producing overlapping catalogs so our runs don't trip it, but
the Themis defect is untouched. Report: `docs/issues/ISSUE-004-overlapping-matches-
corrupt-output.md` (self-contained, inline curl, verified live).

## Issue register + code review
`docs/issues/` = `ISSUE-001..007`, one emailable self-contained report each, aligned
1:1 to THM-1..7. Internal material in `docs/issues/internal/`. All code-review tiers
(0-4 + pragmatic 5) DONE - `docs/CODE_REVIEW_PLAN.md`. Runtime-outage runbook (apollo
boots data-plane PAUSED until a policy commits) in `docs/TROUBLESHOOTING.md` (OPS-1..3);
`validate run` pre-flights.

---

# Demo environment - THE CURRENT WORK (in `demos/`)

Self-contained, isolated from `framework/`. Reuses live endpoints/config; does not
import from `framework/` (except `verify-oracle.py`, which deliberately reuses the
framework's tested matcher as the independent oracle).

## Shared pieces (built + live-verified)

- **`demos/themis-adapter/adapter.py`** - bridges the benchmark contract
  `{"text"}->{"action","text"}` to the engine contract `{"message"}->{result.message}`.
  Derives keep/mask; drop/route via optional sentinel tokens (`THEMIS_DROP_TOKEN`/
  `THEMIS_ROUTE_TOKEN`). Reads generic `PROCESS_ENDPOINT`/`PROCESS_TOKEN` (falls back
  to `THEMIS_*`) so one adapter serves either engine. 9 network-free tests.
- **`demos/policies/`** - `build_policy.py` -> `starter-known-values.nol` (42 govern
  rules, safe: tokens <=15 chars, no contained literals). `build_optimization_policy.py`
  -> `optimization.nol` (42 govern + 10 filler-strip rules). Parser note: trailing
  inline comments after a rule are rejected; comments must be own-line.
- **On-brand report pipeline:** `run.json` (data contract) + `make-report.py` ->
  self-contained HTML (fonts/logos/pattern inlined). Web (dark, open the file) /
  deck (Export -> PDF, `@media print` forces light cream). Content is visible by
  default (no fade-gating; renamed away from "reveal" - a reveal.js preso wrapper was
  injecting a spurious left hamburger; serve the report STANDALONE). Tracked:
  `run.json`, `make-report.py`, `brand/`. Rendered HTML is gitignored.

## Data Point 1 - pre-index - DONE (in `demos/benchmark/`, corpus in `datapoint1/`)

- **Story: leads with the OPTIMIZATION use case** (clean the data before it becomes
  embeddings). Headline "Clean the data before it becomes embeddings, at hardware
  speed"; "One policy. Two engines. Only one stays correct." Governance byte-identical
  redaction is the trust anchor. Latency decomposition (engine is free, latency is the
  network) is a supporting beat. Copy lives in `run.json`.
- **The measured result (single fresh clean run, 2026-07-21, optimization.nol on both
  live engines, oracle-adjudicated):**
  | approach | bytes fwd | tokens fwd | vs do-nothing | oracle |
  |---|---|---|---|---|
  | Do nothing | 322 KB | 43,005 | baseline | n/a |
  | Aergia (RE2) | 131 KB | 17,512 | -59.3% | 124/1000 |
  | Themis (NOL8) | 117 KB | 15,343 | **-64.3%** | **1000/1000** |
  Both kept 27 / masked 973. Latency (N=100 medians): engine <0.3 ms both (upper
  bound, below the network floor); ~97% of a cold call is TLS + RTT; pooling is 3x
  (cold 7.17 -> warm 2.38 ms).
- **BIG FINDING - Aergia corrupts on strip:** every one of Aergia's 876 divergences
  is a strip rule (zero on redaction). It leaves the tail of a stripped literal
  (`default.`->`ault.`). Themis strips cleanly. Logged:
  `demos/benchmark/findings/aergia-strip-corruption.md` (careful framing: Aergia is
  our RE2 baseline; RE2-inherent vs Aergia-harness is an open follow-up).
- **The oracle verifier:** `demos/benchmark/verify-oracle.py` adjudicates each
  engine's recorded output against the framework's Aho-Corasick matcher. This is the
  integrity check pointed at us. Reproduce (EC2):
  ```
  POLICY=demos/policies/optimization.nol MODES="nofilter re2 themis_api aergia_api" \
    bash demos/benchmark/run-live.sh
  python demos/benchmark/verify-oracle.py --results demos/benchmark/datapoint1/results \
    themis_api aergia_api
  ```
- **The report appendix is a full "Show your work" receipts block:** the 64.3%
  breakdown + oracle-verified stamp, the 10 strip rules with corpus repeat counts, 3
  real before/after chunks (green token chips on Themis; RE2 corruption fragments
  boxed in a semantic red), and the forwarded-payload aggregate.
- **Runner:** `demos/benchmark/run-live.sh` (one command on EC2: deploy policy to
  both, start one adapter per engine 8799->:443 / 8800->:444, run harness, build the
  kit's raw report, clean up). Harness modes `themis_api`/`aergia_api` added to our
  copy. Latency: `demos/benchmark/latency-decompose.py`.
- **Narrative + honesty guardrails:** `demos/benchmark/DEMO-NOTES.md`.
- Kit's own `datapoint1/report/report.html` is the raw backup only, not for showing.

## Data Point 2 - pre/post-inference control - KICKED OFF (in `demos/benchmark/datapoint2/`)

- **Copied OUT of the kit** (`~/Code/nol8/preindex-benchmark-kit/
  datapoint2_pre_post_inference_pack_v1`, non-destructive) into
  `demos/benchmark/datapoint2/`. Baseline commit is the clean copy.
- **Flow:** `Prompt -> Pre-Inference Control -> Model Stub -> Post-Inference Control
  -> Output`. Govern what reaches the model AND what leaves it.
- **Actions:** allow / mask / block / route / tag, at BOTH control points.
- **Dataset:** `data/prompts/sample_prompts.jsonl` (each row: prompt_text,
  expected_pre_action, expected_pre_tags, model_stub_profile). Reference lists in
  `data/reference_lists/` (block_phrases, route_phrases, flagged_customers,
  denied_entities, internal_projects, payment_cards, account_ids,
  output_block_phrases, output_tag_phrases) - ALL literal, so listMatch-compatible.
- **Harness** (`go/main.go`): modes `nocontrol`, `re2_guard` (regex), `listguard`
  (literal, uses the reference lists - our closest analog), `nol8sim_infer` (uses the
  expected actions, an oracle sim). Per-mode `applyPreInference*` / `applyPostInference*`
  functions. The kit's `nol8_api_infer` mode calls a placeholder `/infer-control` API
  that our engines do NOT have.
- **>>> THE BUILD:**
  1. **DONE - Boundary policy:** `demos/policies/build_boundary_policy.py` reads the
     DP2 reference lists and emits `demos/policies/boundary.nol` (19 rules, 9 lists).
     Sentinels: block_phrases->`[BLOCK]`, route/flagged/denied->`[ROUTE]`, payment->
     `[MASK_CARD]`, account->`[MASK_ACCT]`, internal->`[TAG_INT]`, output_block->
     `[BLOCK_OUT]`, output_tag->`[TAG_PRIV]` (all <=15 chars). Reuses build_policy's
     ISSUE-005/004 guards; the real lists passed the containment check. Tracked.
  2. **NEXT - Real-engine modes** `themis_api_infer` / `aergia_api_infer`: call the engine at
     BOTH control points (govern the prompt, then govern the model-stub output) via
     the sentinel-extended adapter, deriving block/mask/route/tag from which sentinel
     appears. This is the DP1 drop-sentinel pattern generalized. (The adapter already
     supports drop/route sentinels; extend for block/tag as needed.)
  3. `run.json` + reuse `make-report.py` (or a DP2 copy) for the on-brand report;
     modes map onto the DP1 story: `nocontrol`=Do nothing, `aergia`=RE2 baseline,
     `themis`=NOL8. Oracle-verify each engine (same integrity discipline as DP1).
  4. SA runbook + DEMO-NOTES for DP2.
- **Reuse:** adapter (extend sentinels), policy-generator pattern, report pipeline,
  the oracle-verify discipline. **New:** the pack's prompt corpus + reference lists
  (ship), the two-control-point wiring, a boundary policy, DP2 report copy.

---

# Next horizon

1. **DP2 build** (above) - the active task.
2. **Apply the user's small template tweak** to `make-report.py` once they say what it
   was (open loop in the header).
3. **Throughput / scale benchmark** - concurrency + server-side timing, the test that
   would let NOL8 (FPGA) visibly pull ahead of RE2. The honest "next measurement".
4. **Agentic-mesh-lab review** - user's repo `~/Code/nol8/agentic-mesh-lab` (small,
   in GitHub). Review non-destructively; it overlaps DP3, so it informs DP3's shape.
5. **Data Point 3 - agent-to-agent control** - kit pack `datapoint3_agent_mesh_pack_v1`.
   Flow: `Triage -> Research -> Decision -> Action`; govern each inter-agent hop
   (ISSUE-006). More design; shape after the agentic-mesh-lab review.
6. **EC2 general tidy** (checkout is reconciled and current; just housekeeping).

---

# Deferred / backlog

- Full `main.py` layer-split (Tier 5 remainder) - structural, skip until it matters.
- Emailable HTML render of `docs/issues/` with copy buttons into gitignored `handoff/`.
- Pre-generated demo datasets in t-shirt sizes.
- Isolate whether Aergia's strip corruption is RE2-inherent or Aergia-harness (a
  single-rule direct `:444` curl repro would help; needs RE2-the-library to fully
  settle).

---

# Immediate Next Actions

1. **Build DP2** - start with the boundary policy generator (from the reference
   lists), then the `themis_api_infer`/`aergia_api_infer` two-control-point modes.
2. Await the user's answer on the small template change; apply to `make-report.py`.
3. Announce before every git command ([[announce-before-git]]).

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
  honestly; never rig for parity. [[benchmark-integrity-no-rigging]]
- DP1 leads with the optimization use case (not governance); governance parity is the
  trust anchor. (User's call, 2026-07-21.)

---

# Repository Hygiene

`validate generate` writes to `artifacts/runs/<RUN_ID>/` (gitignored). Survivors go
in `artifacts/evidence/`. Gitignored: `.env`, `keys/`, `.venv/`, `artifacts/runs/`,
`*.pdf`, `handoff/`, and under `demos/benchmark/`: `**/results/*`, `**/report/
report.html`, `**/report/report_data.json`, `**/go/benchmark_runner`, `**/.gocache/`,
and `pre-index-report.html`. **Do not `git add -A`; stage specific files.**

Tests: **236**, all passing.
```bash
source .venv/bin/activate && python -m unittest discover -s tests -q
```
