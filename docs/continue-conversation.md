# Continue Conversation

Last Updated: 2026-07-21

Durable memory of the project, so a new session (or a post-compaction session)
can continue without reconstructing context from chat history.

> **Handoff at 2026-07-21 (fourth handoff).** Clean tree, all pushed, both hosts
> synced, **236 tests passing**. Endpoint healthy; the 5,000-rule qualification
> policy is deployed (SHA `27fe47db`). Nothing mid-edit.
>
> **All code-review tiers are done** (0-4 and pragmatic 5). **Next work is the
> demo environment** - see "Next horizon" and Immediate Next Actions.
>
> **Latest session (2026-07-21):** Tier 2 security (T2-3 token off the curl argv
> = FW-9, live-verified; dead insecure scripts removed = FW-10; artifact residual
> = OBS-3) and pragmatic Tier 5 (atomic-write + JSONL-reader consolidation, an
> end-to-end pipeline test, hermetic transport tests = FW-11; full `main.py`
> layer-split deferred). Then a repo cleanup (see Repository Hygiene).
>
> **Sandbox note:** the Themis tenant is the user's disposable sandbox. Overwrite
> its policy freely; do NOT reflexively restore. Only restore the 5,000-rule
> qualification policy when a known state is needed.

This file is project *state*. Three companions carry the rest, reached for first:

| question | document |
|---|---|
| Something is broken right now | `docs/TROUBLESHOOTING.md` |
| What have we found? | `docs/FINDINGS.md` - every finding, stable IDs (THM-n Themis, OPS-n their tooling, FW-n ours, OBS-n deliberately-not-findings) |
| Where is any other document? | `docs/README.md` |

**Keep them in step.** When a finding's status changes, update FINDINGS.md. When
a failure mode is diagnosed, add it to TROUBLESHOOTING.md.

## Maintaining this file

- **On "update the project":** rewrite this file wholesale to current state. Do
  not append, and do not preserve stale sections - accuracy over history.
- **Every turn:** keep this file current as work happens (status, next actions,
  what's done), so `/compact` is safe to run at any point without losing state.
  Treat the handoff as always-shippable.

---

# The Short Version

Two separate problems. Do not conflate them.

**1. Themis has real product defects.** Headline: ISSUE-004 - two rules matching
overlapping text make the runtime write the replacement at the wrong offset and
destroy adjacent data, silently, HTTP 200 every time. **Open, not yet reported to
engineering** (the send is the user's to make; the docs are ready).

**2. The framework had its own defects, now fixed.** It generated data that
tripped the Themis bug, computed expected output from a false invariant, and had
ordinary bugs. All corrected and verified at scale. The framework now produces
trustworthy evidence: a clean 5,000-rule / 10,000-record qualification passes
100%.

The 2026-07-20 outage is **RESOLVED** (see Runtime outage below).

---

# CRITICAL CONTEXT - who wrote what

**Engineering did not write this repository.** They handed over the v1.0 sandbox
with documentation and an invitation to use the system. This validation framework
is ours. Consequences for anything sent to engineering:

- Never reference a path in this repository.
- Inline reproductions as literal curl against their endpoints and token.
- Mention the framework only as provenance for finding the defect at scale.

The `docs/issues/` register already follows this. Keep it that way.

---

# Session Operating Rules

- Work one action at a time. End responses with a clear next action.
- `validate` is the product surface. Do NOT call `scripts/*.sh` directly.
- Do not restart resolved architecture discussions or replace working tooling.
- Verify whether an issue is real before proposing changes.
- **Repro/command docs are not "done" until run as written.** (Learned the hard
  way: the ISSUE-004 curl needed `--insecure` and that was found only by running
  it against the tenant.)

---

# Environments

| | Mac | EC2 |
|---|---|---|
| purpose | development, commits | execution against Themis |
| path | `~/Code/nol8/nol8-validation` | `/opt/nol8/nol8-validation` |
| python | 3.12 | 3.14.4 |
| host | - | `nol8-demo` (in `~/.ssh/config`) |

Edit and commit on Mac, `git push`, `git pull` on EC2, execute there. SSH from
Mac is non-interactive.

```bash
cd /opt/nol8/nol8-validation && source .venv/bin/activate
```

Long-running SSH commands must be detached (`nohup setsid ... > log 2>&1 &`) and
polled by grepping the log for a completion marker - `pgrep -f "validate run"`
matches its own command line and hangs. Progress output adapts: in-place bar on a
terminal, ~one line per 10% when redirected. EC2 is a **test/demo** environment,
not production; overwriting a policy is not an emergency.

### Where the services actually live

`nol8-demo` (hostname `data-streamer`, 10.8.10.40) is a pure client box - holds
our checkout, runs none of Themis.

| | address |
|---|---|
| themis host (`themis-demo`, ssh) | 10.10.1.254, runs iris + apollo + policyd |
| data plane endpoint (`tenant001-v1demo.nol8.net`) | valid Amazon cert, port 443 |
| policy control plane (`themis.sales.nol8.cloud:8444`) | **self-signed cert** (CN=ip-172-31-40-100 - matches neither the DNS name nor the host 10.10.1.254), so `--insecure`/`-k` is required |
| aergia control plane | 10.10.1.127 |

**Treat `themis-demo` with care** - policy deploys via the API are fine (the
recovery path); service restarts and system changes are not ours to make.

## Permissions

Bash prompts were a recurring pain in earlier sessions. Baseline in
`.claude/settings.json` allows all Bash with a deny list; local override
`.claude/settings.local.json` (gitignored) sets `bypassPermissions`. Recent
sessions have run cleanly. If prompts recur, confirm the extension loaded
`settings.local.json`, check `claudeCode.initialPermissionMode`, and as a last
resort launch with `--dangerously-skip-permissions` (sandbox only).

---

# CLI

```bash
validate generate --config <yaml> [--rules N] [--records M]
validate policy   --run <RUN_ID> | --file <path.nol> | --status
validate run      --run <RUN_ID> [--limit N] [--skip-preflight]
validate compare  --run <RUN_ID> [--replacement-max-length 15]
validate report   --run <RUN_ID>
```

Fully documented in `README.md`. Smoke test (~1 min): generate 100/50 on
customer-record-csv, then policy/run/compare/report against themis; expect 50/50
succeeded, `PASS: 50`, `CONTENT_MISMATCH: 0`, banner `PASS`.

Transport note: both scripts read `NOL8_CONFIG_FILE`/`NOL8_SECRETS_FILE`
(defaulting to `config/demo.env` and `.env`); the token is written to a `0600`
temp file and passed with `-H @file` (never on the command line - FW-9).

---

# Current State - 2026-07-21

## Runtime outage 2026-07-20 - RESOLVED

Every request 503'd for ~an hour. **Root cause: apollo boots with its data plane
PAUSED and un-pauses only when a policy commits.** None had been deployed since
restart. Not a crash - documented startup behaviour. Deploying any policy
restores it. Full runbook: `docs/TROUBLESHOOTING.md`. Carry two things:

- **Do not restart services for a 503.** Deploy a policy first (apollo was
  restarted three times that hour, each returning to paused).
- **Every convenient signal lied** - `systemctl` said active, `nolctl doctor`
  false-FAILed on kernel params, the status string still read PAUSED after
  recovery. Only `grep -c "Rules committed" apollo.log` was accurate. Recorded as
  OPS-1..3. `validate run` now pre-flights and aborts with the remedy.

## Authoritative qualification - 20260720T221534714262Z

```
5,000 rules / 10,000 records / customer-record-csv / seed 42
overlapping_match_documents: 0   intended_clean_with_literals: 0
PASS: 10,000   CONTENT_MISMATCH: 0   EXECUTION_FAILURE: 0   INCONCLUSIVE: 0
Latency p50/p95/p99: 12.643 / 14.358 / 16.814 ms   policy SHA256: 27fe47db...
```

Airtight (0 inconclusive, 0 collisions, report banner PASS). Generated under the
**current post-FW-7 generator**, so it regenerates byte-identically from seed 42.
Its policy and report are promoted into `artifacts/evidence/` and the policy is
deployed on the tenant. Supersedes three earlier runs kept only as history
(`20260720T193444152733Z` pre-FW-7; `20260719T230452981053Z` pre-collision-
detection; `20260719T161514709224Z` the original 272-failure run and source of
`issue-004-failure-sample.jsonl`).

### Reproducibility after FW-7 (resolved)

FW-7 canonicalised weighted-selection order (was YAML-key-order dependent),
changing what seed 42 produces. Rather than leave the deployed policy
unreproducible, the tenant was re-qualified under the current generator (the run
above). Reproducible-from-seed is restored; determinism is tested
(`tests/test_generation_determinism.py`), now independent of key order.

## ISSUE-004 - OPEN, engineering docs ready but NOT SENT

**Do not record as resolved.** The Themis defect is untouched; our *generator*
stopped producing overlapping-literal catalogs, so our runs no longer trip it. A
customer redacting `"Acme Corp"` alongside `"Acme Corporation"` is still silently
corrupted. Empirically: either rule alone is correct; only coexistence triggers
it; order-independent; only shared bytes corrupt; only the match START is
displaced (END correct); shorter replacements destroy MORE.

- **Engineering-facing report:** `docs/issues/ISSUE-004-overlapping-matches-corrupt-output.md`
  (self-contained, inline curl, verified against the tenant).
- **Full internal investigation:** `docs/issues/internal/ISSUE-004-corruption-investigation.md`.

## Issue register - engineering-facing, sendable

`docs/issues/` holds `ISSUE-001..007`, one self-contained emailable report each,
aligned 1:1 to the internal THM-1..7 (ISSUE-N = THM-N). ISSUE-004 is the
corruption defect (the priority; send alone). Others: policy has no identity
(001), deploy replaces ruleset (002), fire-and-forget (003), 15-char truncation
(005), eval env unreachable externally (006), no health signal (007). Register
index: `docs/issues/README.md`. Internal/repo-referencing material lives in
`docs/issues/internal/` (investigation, KNOWN_BEHAVIORS, technical_debt).

**Outbound Slack comms drafted:** `docs/issues/internal/outbound-slack-comms.md`
(Comm 1 = issue-bundle handoff with ISSUE-004 elevated; Comm 2 = the data-path /
inline-streaming question, OBS-2, sent separately).

## Code review - ALL TIERS DONE

`docs/CODE_REVIEW_PLAN.md` (full review of ~7,800 lines). Status blocks in the
plan record what was verified against current code.

- **Tier 0** COMPLETE - framework could certify unverified success.
- **Tier 1** COMPLETE - blamed the product for generator bugs; T1-6 = FW-7.
- **Tier 2** COMPLETE (2026-07-21) - T2-1/T2-2 via FW-4/5; T2-3 token off argv =
  FW-9 (live-verified); dead insecure scripts removed = FW-10 (resolves
  T2-4/T2-5); live-artifact plaintext residual = OBS-3 (synthetic-only guardrail).
- **Tier 3** - product limitations, written up (the issue register).
- **Tier 4** - evidence quality + report usability; FW-6 (grouped/compact failure
  details).
- **Tier 5** PRAGMATIC COMPLETE (2026-07-21, FW-11) - atomic-write + JSONL-reader
  consolidation, end-to-end pipeline test, hermetic transport tests. **Deferred
  by choice:** the full `main.py` layer-split (high churn on a working core,
  pre-release value not needed pre-demo).

## Framework guarantees, briefly

- Generation refuses catalogs that would make results meaningless: no nested
  literals; replacement tokens stay distinct under 15-char truncation; selection
  is independent of YAML key order (FW-7). Check `overlapping_match_documents` in
  the generation manifest before trusting any run as a qualification.
- Expected output is computed by scanning the full catalog via Aho-Corasick
  (`framework/policy/matching.py`).
- **INCONCLUSIVE verdict:** where two replacements collapse to the same 15-char
  string, a would-be PASS is downgraded to INCONCLUSIVE (neither pass nor product
  failure). Mismatches are left alone (truncation only makes messages look more
  alike). `--replacement-max-length 15` models the runtime truncation; it is the
  demo switch and stays.
- **Report failure details (FW-6):** failures are classified by diff-shape
  signature, grouped, and shown as a summary table plus <=3 compact windowed
  diffs per group; full messages behind `<details>`, drops stated explicitly.

---

# Next horizon - DEMONSTRATIONS (the current work)

Goal: a demo environment + demo stories showing Themis (FPGA) and Aergia (RE2) to
buyers. **Likely a NEW repo** that reuses assets from two external repos.

### Asset 1 - `preindex-benchmark-kit` (REVIEWED, reusable) - DO NOT MODIFY IN PLACE

Path: `~/Code/nol8/preindex-benchmark-kit`. **The user does not want this repo
changed or destroyed - work OUTSIDE it: copy/reference what we need into the new
demo repo, never edit in place.** A benchmark workbench, three use cases mapping
to the demo horizon:
- datapoint1 Pre-Index Optimization (govern what gets embedded before RAG).
- datapoint2 Pre/Post-Inference Control (model-boundary / prompt-injection filter).
- datapoint3 Agent-to-Agent Control (agent-mesh; the ISSUE-006 agent story).

Each ships datasets, reference lists, a Go harness, Python analysis, a polished
HTML report, an AI-summary generator, and sales docs. ~80% built. **Gap:** a
contract mismatch - the benchmark wants `{"text"}->{"action","text"}`
(keep/mask/drop/route), Themis speaks `{"message"}->{"result":{"message"}}`
(redaction only). Needs a thin adapter (~30-50 lines) mapping fields and deriving
the action (unchanged->keep, changed->mask; drop/route via policy sentinel
tokens) - where our policy work applies. Its `go/nol8_client.go` already has a
pluggable `nol8_api` mode hitting `NOL8_ENDPOINT`. Terraform (`aws_benchmark_
harness`) can be retired (we have live endpoints + the EC2 box). Reports currently
show a simulated `nol8sim` placeholder - a credible demo must replace it with real
measured numbers and never present simulated figures as real.

### Asset 2 - agentic insurance-claims demo (NOT YET ON THIS MACHINE)

A multi-agent (agent-to-agent) insurance-claims demo the user built, on their
MacBook Pro. **Plan:** the user pushes it to a new GH repo, we clone it here, and
I review it the same way (likely overlaps datapoint3). Not startable until cloned.

### Conceptual threads that feed the demo

- **"How do I do this with my data?"** - the honest answer ("the oracle is ours")
  is weak alone. Build toward **invariants** ("no unredacted SSN pattern in
  output", checkable with no oracle) and **synthetic canaries in a live stream**.
- **Agent-mediated integration** is the fastest-growing buyer interest (ISSUE-006)
  and currently undemonstrable (eval env is VPC-only); a reachable endpoint is the
  unlock.
- **Data-path question (OBS-2):** the intended production integration mode
  (inline/proxy/streaming - `jid`/`frameId`/`last:true` hint at it) shapes a
  realistic demo. Worth engineering's answer (Comm 2).

### Progress (2026-07-21) - demo environment started IN THIS REPO

Decision: the demo work lives in `demos/` inside nol8-validation (its own
directory, self-contained, isolated from `framework/` and the validation
`tests/` - can graduate to its own repo later by lifting the dir out). It reuses
the live endpoints/config but does not import from `framework/`.

**Done:** `demos/themis-adapter/adapter.py` - the bridge that lets the benchmark
harness run against real Themis. Accepts the benchmark's `{"text"}`, calls
Themis, returns `{"action","text"}` (keep if unchanged, mask if changed; opt-in
drop/route via `THEMIS_DROP_TOKEN`/`THEMIS_ROUTE_TOKEN` policy sentinels).
9 network-free tests. **Live-verified against Themis** (mask + keep both correct;
the 15-char truncation showed through, confirming real behaviour). Run tests:
`python -m unittest discover -s demos/themis-adapter -p 'test_*.py'`.

**Next demo steps:** (1) copy ONE datapoint's harness+datasets OUT of
`preindex-benchmark-kit` into `demos/` (never edit the kit), point its
`NOL8_ENDPOINT` at the adapter, and produce one real report replacing the
`nol8sim` placeholder. (2) Extend the adapter's drop/route via a policy that maps
governed values to sentinel tokens. (3) Clone + review the agentic repo when
pushed.

---

# Deferred / backlog (not now)

- **Full `main.py` layer-split** (Tier 5 T5-1 remainder) - structural, high churn,
  pre-release value; skip until it matters.
- **Emailable HTML render of docs with copy buttons** - render `docs/issues/` to
  self-contained HTML (inline copy buttons) into a gitignored `handoff/` dir, as a
  repeatable build step. Reusable for anything we hand off. Markdown has no native
  copy button; GitHub/VS-Code preview do, PDF/raw do not.
- **Pre-generated demo datasets** in t-shirt sizes (bundles of input+expected+
  policy) to remove generation dead-air in a live demo; collides with THM-2 (one
  policy at a time).

---

# Immediate Next Actions

**In order:**

1. **Build the demo environment (STARTED, in `demos/`).** The Themis adapter is
   done and live-verified. Next: copy ONE datapoint (harness+datasets) OUT of
   `preindex-benchmark-kit` into `demos/`, point its `NOL8_ENDPOINT` at the
   adapter, and produce one real report. Then extend drop/route via sentinel
   policy. Clone + review the agentic repo when the user pushes it. See "Next
   horizon - Progress".

**Not blocking (user handles):** send ISSUE-004 to engineering - report in
`docs/issues/`, Slack comms in `docs/issues/internal/outbound-slack-comms.md`.
Send ISSUE-004 first and alone.

---

# Decisions Made - Do Not Reopen

- Five-stage lifecycle; do not collapse stages. `validate` is the only supported
  interface; scripts are transport. Manifest-driven state, written atomically.
- Do NOT adjust validation expectations to make ISSUE-004 pass.
- A run where every request fails is deliberately NOT a stage failure - it would
  block compare/report, leaving an exception instead of evidence. (The outage is
  this working as intended.)
- An unconfirmable record is INCONCLUSIVE, never PASS/FAIL.
- Generation is canonicalised (FW-7): output depends on seed + config semantics,
  not serialization order. Accepting the seed-42 output change was deliberate.
- `artifacts/runs/` is not tracked; anything that must survive cleanup goes in
  `artifacts/evidence/`.
- TLS: the control plane's self-signed cert is OBS-1, deliberately NOT a finding
  for this sandbox. Do not re-promote it. `--insecure` is required to reach it.

---

# Repository Hygiene

Tracked evidence in `artifacts/evidence/` (with a README on provenance):
`tenant-restore-policy.nol` (deployed 5,000-rule policy, SHA `27fe47db`, the only
copy - Themis can't read back what's deployed), `issue-004-failure-sample.jsonl`,
`qualification-passing-report.html`.

**Where generated data goes.** `validate generate` writes to
`artifacts/runs/<RUN_ID>/` (RUN_ID = UTC stamp, e.g. `20260721T120130336787Z`),
which is **gitignored** - generated corpora stay local, never committed:

```
artifacts/runs/<RUN_ID>/
  manifest.json                  run state
  config/<workload>.yaml         snapshot of the config used
  generated/input.jsonl          the generated corpus (sent to Themis)
  generated/expected.jsonl       the oracle (expected redacted output)
  generated/scale-policy.nol     the generated policy
  generated/generation-manifest.json   seed, counts, overlapping_match_documents
  generated/output.jsonl         actual Themis responses (after `run`)
  generated/comparison.jsonl     per-record verdicts (after `compare`)
  reports/validation-report.html the report (after `report`)
```

Anything that must survive cleanup is copied into the tracked
`artifacts/evidence/`. Default runs root is `artifacts/runs` (`DEFAULT_RUNS_DIRECTORY`).

**Cleanup done 2026-07-21:** removed the stray `dotenv` file, the 0-byte doc
stubs (`docs/ARCHITECTURE.md`, `docs/REPORTS.md`, `docs/product/validation-
framework-overview.md`) and their placeholder note, `samples/` (15 MB legacy
data), and `artifacts/initial-functional-baseline/` (superseded by evidence/).
Earlier (Tier 2) removed dead scripts (`process-message.sh`,
`restructure-framework.sh`, `run_functional_test.py`).

**PDFs are not tracked.** The user generates PDF renders via the
`yzane.markdown-pdf` VS Code extension (exports to gitignored `handoff/`), then
removes them. `*.pdf`, `handoff/`, `.env`, `keys/`, `.venv/`, `artifacts/runs/`
are gitignored. **Do not `git add -A`; stage specific files** so generated
artifacts never ride along.

Tests: **236**, all passing.

```bash
source .venv/bin/activate && python -m unittest discover -s tests -q
```
