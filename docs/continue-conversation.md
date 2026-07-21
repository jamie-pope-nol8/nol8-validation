# Continue Conversation

Last Updated: 2026-07-20

Durable memory of the project, so a new session can continue without
reconstructing context from chat history.

> **Handoff at 2026-07-20 (end of day, third handoff).** Clean tree, all pushed
> (latest commit `1d2a70e` or later), both hosts synced, 228 tests passing.
> Endpoint healthy; the 5,000-rule qualification policy is deployed (SHA
> `27fe47db`). Nothing mid-edit. User stopped for family time; resumes tomorrow
> with **Tier 2 then Tier 5**.
>
> **Done this session (all committed + pushed):**
> - **FW-6** report usability - grouped, compact failure details (`4cc2185`).
> - **FW-7** generation independent of YAML key order (`53ea077`).
> - **Re-qualification** under the post-FW-7 generator - new authoritative run
>   `20260720T221534714262Z`, deployed and verified airtight (10,000 PASS, 0
>   inconclusive). The FW-7 reproducibility gap is CLOSED; the deployed policy
>   again regenerates from seed 42. Evidence promoted; prior qualifications are
>   superseded history.
> - **Engineering-facing issue register** in `docs/issues/` (`ISSUE-001..007`,
>   aligned 1:1 to THM-1..7; the corruption defect renumbered ISSUE-003 ->
>   ISSUE-004). Each doc self-contained and emailable. Internal material moved to
>   `docs/issues/internal/`.
> - **Reproductions verified against the live tenant** and corrected: control-
>   plane curl calls need `--insecure` (self-signed cert); the docs now show the
>   real response envelopes and actual observed output (ISSUE-004 `x [P[Q] y`,
>   ISSUE-005 `[FINANCIAL:CRED`).
> - **Outbound Slack comms** drafted: `docs/issues/internal/outbound-slack-comms.md`.
>
> **Next work items (in order):**
> 1. **Tier 2 - security. DONE 2026-07-21.** T2-3 fixed (FW-9, token off argv,
>    live-verified); dead insecure scripts removed (FW-10, resolves T2-4/T2-5);
>    T2-1/T2-2 already handled by FW-4/5; T2-4 residual recorded as OBS-3. See
>    the Tier 2 status block in `docs/CODE_REVIEW_PLAN.md`.
> 2. **Tier 5 - structure and tests. START HERE.** NOT STARTED.
> 3. **Then: demo environment.** Likely a NEW repo, reusing the reviewed
>    `preindex-benchmark-kit` (three use cases, datasets, Go harness, reports -
>    ~80% built) and a second **agentic insurance-claims** repo that is **not on
>    this machine yet** (clone + review first). See "Next horizon - demonstrations".
>
> Still open but not blocking: send ISSUE-004 to engineering (register + comms
> are ready; the user handles the actual send).

This file is project *state*: where things stand and what to do next. Three
companions carry the rest, and they are the ones to reach for first:

| question | document |
|---|---|
| Something is broken right now | `docs/TROUBLESHOOTING.md` |
| What have we found? | `docs/FINDINGS.md` - every finding, stable IDs (THM-n Themis, OPS-n their tooling, FW-n ours, OBS-n deliberately-not-findings) |
| Where is any other document? | `docs/README.md` |

**Keep them in step.** When a finding's status changes, update FINDINGS.md.
When a new failure mode is diagnosed, add it to TROUBLESHOOTING.md. Both are
indexes, not archives - they must not be allowed to drift.

## Maintaining this file

When the user says **"update the project"**, rewrite this file to reflect
current state. Also refresh it at the end of meaningful work sessions and
before compaction.

Rewrite it wholesale. Do not append, and do not preserve stale sections because
they are already here - a previous revision claimed `compare` and `report` were
NOT STARTED long after both had shipped. Accuracy over history.

---

# The Short Version

Two separate problems. Do not conflate them.

**1. Themis has real product defects.** The headline is ISSUE-004: two rules
matching overlapping text cause the runtime to write the replacement at the
wrong offset and destroy adjacent data, silently, HTTP 200 every time.
**Still open. Not yet reported to engineering.** Full product findings in
`docs/product/themis-product-limitations.md`.

**2. The framework had its own defects**, now fixed. It generated data that
tripped the Themis bug, computed expected output from a false invariant (and so
blamed Themis for correct behaviour), and had ordinary bugs. All corrected and
verified at scale.

Current status: **the framework produces trustworthy evidence.** A clean
5,000 rule / 10,000 record qualification passes 100%.

The 2026-07-20 outage is **RESOLVED**. Root cause and the lesson from it are
under "Runtime outage" below - worth reading before touching the environment.

---

# CRITICAL CONTEXT - who wrote what

**Engineering did not write this repository.** They handed over the v1.0
sandbox (originally called alpha; that name was dropped) with documentation and
an invitation to use the system. This validation framework is ours - built by
the user and coding agents.

Consequences for anything sent to engineering:

- Never reference a path in this repository. Asking them to clone unfamiliar
  tooling to reproduce a defect in their own product is a reason to
  deprioritise it.
- Inline reproductions as literal curl against their endpoints and token.
- Mention the framework only as provenance for finding the defect at scale.

The engineering-facing issue docs in `docs/issues/` already follow this. Keep it
that way.

---

# Session Operating Rules

- Work one action at a time. End responses with a clear next action.
- `validate` is the product surface. Do NOT call `scripts/*.sh` directly.
- Do not restart resolved architecture discussions or replace working tooling.
- Verify whether an issue is real before proposing changes.

---

# Environments

| | Mac | EC2 |
|---|---|---|
| purpose | development, commits | execution against Themis |
| path | `~/Code/nol8/nol8-validation` | `/opt/nol8/nol8-validation` |
| python | 3.12 | 3.14.4 |
| host | - | `nol8-demo` (in `~/.ssh/config`) |

Edit and commit on Mac, push, `git pull` on EC2, execute there. SSH from Mac
works non-interactively.

```bash
cd /opt/nol8/nol8-validation && source .venv/bin/activate
```

Long-running commands over SSH must be detached (`nohup setsid ... &`). When
polling, grep a log for a completion marker - `pgrep -f "validate run"` matches
its own command line and hangs.

Progress output adapts to its destination: in-place bar on a terminal, roughly
one line per ten percent with no escapes when redirected.

EC2 is a **test and demo environment**, not production. Overwriting a policy is
not an emergency.

## Permissions - previously the top quality-of-life issue

Bash prompts had been relentless across earlier sessions and the user could not
walk away during long runs. The full history of what was tried is below. The
last step before this session was a **VS Code / extension update, then restart**.

**This (post-restart) session ran the entire FW-6 and FW-7 work cycle - many
Bash commands, edits, commits - without the user reporting interruptions.** That
is a tentative signal the update+restart cured it. If prompts recur, the state
and remaining options are preserved here:

**Committed baseline (`.claude/settings.json`, safe, shareable):** allows all
Bash (bare `Bash`) with a deny list (sudo, `rm -rf /`, force push,
curl-pipe-to-shell, reading `.env` and private keys).

**Local override (`.claude/settings.local.json`, gitignored, this machine):**
`permissions.defaultMode: "bypassPermissions"`. Delete this file to return to
the safe allow+deny baseline.

**Tried across earlier sessions, in order, none reliably worked at the time:**
1. Per-command allow list - failed: real commands are compound/piped.
2. Bare `Bash` allow-all in project settings - still prompted.
3. Reopening the folder for the VS Code workspace-trust dialog - still prompted.
4. `bypassPermissions` in local settings reloaded via `/config` - reportedly did
   NOT fix it (a mid-session-created settings file is not picked up by the
   watcher until a full restart; the update+restart should have cured that).

If prompts return: confirm the running extension actually loaded
`settings.local.json`; check the VS Code setting
`claudeCode.initialPermissionMode` is not forcing an ask mode; as a last resort
launch the CLI with `--dangerously-skip-permissions` (sandbox only). Revisit the
whole scheme if this stops being a personal sandbox.

---

# CLI

```bash
validate generate --config <yaml> [--rules N] [--records M]
validate policy   --run <RUN_ID> | --file <path.nol> | --status
validate run      --run <RUN_ID> [--limit N] [--skip-preflight]
validate compare  --run <RUN_ID> [--replacement-max-length 15]
validate report   --run <RUN_ID>
```

Fully documented in `README.md`. End-to-end smoke test, about a minute:

```bash
validate generate --config config/workloads/customer-record-csv.yaml \
  --rules 100 --records 50
export RID=<run-id>
validate policy  --run $RID --target themis
validate run     --run $RID --target themis
validate compare --run $RID --replacement-max-length 15
validate report  --run $RID
validate policy  --file artifacts/evidence/tenant-restore-policy.nol
```

Expect 50/50 succeeded, `PASS: 50`, `CONTENT_MISMATCH: 0`, banner `PASS`.

---

# Current State - 2026-07-20

## Runtime outage 2026-07-20 - RESOLVED

Every request 503'd for about an hour. **Root cause: apollo boots with its data
plane PAUSED and un-pauses only when a policy commits.** None had been deployed
since the last restart. Not a crash - documented-in-source startup behaviour.
Deploying a single-rule policy restored it; the 5,000-rule policy is live again
and verified (SHA256 `0902f0e1...`).

**Full runbook: `docs/TROUBLESHOOTING.md`.** Not repeated here - it must not
drift. Two things to carry in your head:

- **Do not restart services for a 503.** Deploy a policy first. The journal
  shows apollo was restarted three times that hour, each returning to the same
  paused state. Restarting is the loop, not the exit.
- **Every convenient signal lied** - `systemctl` said active, `nolctl doctor`
  reported a false FAIL on kernel params, and the status string still read
  PAUSED after recovery. Only `grep -c "Rules committed" apollo.log` was
  accurate. Recorded as OPS-1 to OPS-3.

Mitigated our side: `validate run` now pre-flights the endpoint and aborts with
the remedy rather than generating a full run of failures.

### Where the services actually live

`nol8-demo` (hostname `data-streamer`, 10.8.10.40) runs **none** of it - no
containers, no Themis processes. Pure client box, holds our checkout.

| | address |
|---|---|
| themis host (`themis-demo`, ssh) | 10.10.1.254, runs iris + apollo + policyd |
| data plane endpoint | 10.8.11.254, publishes port 443 only |
| aergia control plane | 10.10.1.127 |

**Treat `themis-demo` with care** - the user asked for no harm there. Policy
deploys via the API are fine and are the recovery path; service restarts and
system changes are not ours to make.

## Clean qualification - 20260720T221534714262Z (AUTHORITATIVE)

```
5,000 rules / 10,000 records / customer-record-csv / seed 42
overlapping_match_documents: 0    intended_clean_with_literals: 0

PASS: 10,000        CONTENT_MISMATCH: 0
EXECUTION_FAILURE: 0    INCONCLUSIVE: 0
Pre-flight: healthy    Pass rate: 100.000%
Latency p50/p95/p99: 12.643 / 14.358 / 16.814 ms
policy SHA256: 27fe47db...
```

This is the **airtight** qualification: 0 inconclusive, 0 replacement
collisions, report banner PASS. Generated under the **current (post-FW-7)**
generator, so it regenerates byte-identically from seed 42. Its policy and
report are promoted into `artifacts/evidence/`, and the policy is the one
deployed on the tenant (deployed 2026-07-20 as `cmd-479`, apollo confirmed
`loaded 5000 rule(s) ... REPLACE`). 7,504 dirty / 2,496 clean records.

## Reproducibility after FW-7 - resolved this session

FW-7 canonicalised the order in which weighted selections are drawn (previously
they depended on YAML key order), which **changed what seed 42 produces**. That
briefly left the deployed policy and the then-authoritative qualification
(`20260720T193444152733Z`) unreproducible from seed 42. **Resolved by
re-qualifying:** generated a fresh 5,000/10,000 seed-42 bundle under the current
generator (`overlapping_match_documents: 0` verified), deployed it to Themis,
ran/compared/reported to 10,000 PASS / 0 inconclusive, and promoted it as the
new authoritative run `20260720T221534714262Z`.

State now:

- The deployed policy again **regenerates from seed 42** under the current
  generator. Reproducible-from-seed is restored.
- Determinism is guaranteed and tested
  (`tests/test_generation_determinism.py`): same config + seed -> identical
  output, now regardless of key order.
- The prior authoritative policy `c3b763aa...` and its run are superseded but
  kept as valid frozen evidence in history.

If you ever re-qualify again: regenerate at 5,000/10,000, confirm
`overlapping_match_documents: 0`, run/compare/report to 100% PASS with 0
inconclusive, promote the new policy+report into `artifacts/evidence/`, deploy,
and update this section, the qualification block, and the evidence README with
the new run ID and SHA.

Supersedes three earlier runs, kept only as history:

- `20260720T193444152733Z` - the prior authoritative run. Equally airtight
  (10,000 PASS, 0 inconclusive), but generated under the pre-FW-7 generator, so
  it no longer matches what seed 42 yields. Policy SHA `c3b763aa...`.
- `20260719T230452981053Z` - also 10,000 PASS, but predated collision detection
  and had three `[BUSINESS_TERMS:*]` tokens collapsing under truncation across
  4,755 transformations. Under current logic those would be INCONCLUSIVE. This
  is exactly the blind spot FW-3 closed, now proven closed end to end.
- `20260719T161514709224Z` - the original 272-failure run whose catalog had 31
  overlapping pairs; the source of `issue-004-failure-sample.jsonl`.

The last two together **prove ISSUE-004 was the sole cause of the original 272
failures**, and that it is not a marginal edge case.

## ISSUE-004 - OPEN, engineering doc ready but NOT SENT

**Do not record this as resolved.** A draft once described it as "resolved
through policy quality validation". Wrong. The Themis defect is untouched; our
*generator* stopped producing catalogs that trip it.

Note the renumber: the overlapping-corruption defect is **ISSUE-004** (aligned
to THM-4). It was formerly labelled ISSUE-003 - a Codex numbering that started at
003 with no 001/002. The whole `issue-003` token was renamed to `issue-004`
across docs, code comments, tests, scripts, and the evidence sample file.

- **Themis defect** - open, unfixed, not yet reported.
- **Framework workaround** - our catalogs no longer contain overlapping
  literals, so our runs no longer trigger it.

A customer redacting `"Acme Corp"` alongside `"Acme Corporation"` is still
silently corrupted.

Empirically established:

- Either rule alone renders correctly. Only coexistence triggers it.
- Rule order does not matter.
- Adjacent and disjoint matches are correct. Only shared bytes corrupt.
- Containment is NOT required - `"ABCD"` with `"DEFG"` corrupts.
- Within containment, only strict prefix corrupts; suffix and middle are fine.
- Replacement length is irrelevant; shorter replacements destroy MORE.
- Replacement output is NOT re-scanned (single pass).
- Match END offset is correct; only the START is displaced.

**Engineering-facing report:** `docs/issues/ISSUE-004-overlapping-matches-corrupt-output.md`
- self-contained, inline curl, no repository needed, safe to attach to an email.
The full internal investigation is `docs/issues/internal/ISSUE-004-corruption-investigation.md`.
The old ready-to-send handover-message draft was removed; its curl reproduction
is folded into the ISSUE-004 report.

## Themis product limitations - seven findings

`docs/product/themis-product-limitations.md`.

1. A deployed policy has no identity (no read-back, version, or identifier)
2. Deployment replaces the entire ruleset
3. Deployment is fire and forget
4. Overlapping matches corrupt output (ISSUE-004)
5. Replacements truncate at 15 characters (KB-001)
6. Evaluation environment unreachable externally - VPN and SSH only, so agent
   integrations cannot be demonstrated
7. No way to check whether the runtime is healthy (added 2026-07-20 from the
   outage above)

1 to 3 and 7 share a root cause: **the runtime cannot be asked about its own
state** - not what policy is loaded, not whether it converged, not whether the
engine is running.

Item 6 was added because agent-mediated demos are the fastest-growing buyer
interest and currently cannot be shown at all. Framed as demonstrability, not
as criticism of the security posture.

### TLS - investigated and deliberately NOT a limitation

The policy control plane presents a self-signed certificate
(`CN=ip-172-31-40-100`) while the processing endpoint has a valid
Amazon-issued one, so `--insecure` is required to deploy.

This was briefly written up as a high-severity limitation. **That was wrong**
and it was withdrawn. The sandbox is provisioned for one team and reachable
only from inside the VPC. A certificate proves server identity; anyone able to
exploit its absence is already inside that network. No customer traffic passes
through it. Self-signed is a reasonable choice here.

Do not re-promote it. The only open question is why the two endpoints were
provisioned differently, which is a question about production intent.

`load-policy.sh` still verifies by default and requires
`THEMIS_ALLOW_INSECURE_TLS=1` (set in `config/demo.env`), kept so the exception
stays visible rather than propagating silently into an environment where it
would matter.

## Open question for engineering - the data path

Today: POST to `/v1/process`, the transformed payload returns to the **caller**,
who must forward it onward. For production that is backwards - the caller
handles unredacted data on both sides.

But the response carries `jid`, `frameId`, and `last: true`, which suggests a
framed or streaming protocol. There may be an inline or proxy mode we are not
using.

Raise as a **question, not a finding**: is there an inline/streaming mode, and
what is the intended integration pattern? Send it as its own short note, not
stapled to any issue doc.

## Conceptual clarification - the oracle is ours, not the product

`expected.jsonl` is a **test oracle**, not a product artifact. It exists so we
can prove the engine does what it claims. A customer streaming terabytes has no
oracle and never will - they write a policy, stream data, and trust
enforcement.

Of the generated bundle, only the **policy** is a product artifact.

Two things DO translate to product capability, and are worth building
eventually:

- **Invariants instead of expectations** - "no unredacted SSN pattern appears
  in output" is checkable on real data with no oracle.
- **Synthetic canaries in a live stream** - inject known values into real
  traffic and verify they come back redacted. Continuous assurance in
  production.

Have this ready: a customer watching a demo will ask "how do I do this with my
data?" and "you don't, this proves the engine works" is a weak answer alone.

## Code review

`docs/CODE_REVIEW_PLAN.md` - full review of ~7,800 lines, tiered by risk.

- **Tier 0 COMPLETE** - the framework could report success it had not verified.
- **Tier 1 COMPLETE** - T1-6 (YAML key order) closed this session as FW-7. The
  only remaining Tier 1 item historically deferred was T1-6; confirm nothing
  else is outstanding when you next open the plan.
- **Tier 2 COMPLETE (2026-07-21)** - security. T2-3 fixed (FW-9: token off the
  curl argv into a 0600 `-H @file`, live-verified). Dead insecure scripts removed
  (FW-10: `process-message.sh`, `framework/execution/run_functional_test.py`,
  `restructure-framework.sh`) - this resolves T2-5 (unauthenticated paths) and the
  T2-4 plaintext writer. T2-1 (TLS) and T2-2 (env sourcing) were already handled
  by FW-4/FW-5. T2-4 residual on live artifacts recorded as OBS-3 (synthetic data
  only; real-data guardrail). Full status block in the plan.
- **Tier 3** - product limitations, written up.
- **Tier 4** - evidence quality and report usability. **FW-6 (report usability)
  done.** Re-scan the plan for any remaining Tier 4 items.
- **Tier 5 NOT STARTED** - structure and tests. **Next.**

## Generator guarantees

Generation REFUSES to produce a catalog that would make results meaningless:

- **No nested literals.** Five generators used a variable-width index; all now
  fixed-width. The guard caught a fifth (`internal_product_name`) a manual
  sweep missed.
- **Replacement tokens stay distinct under 15-character truncation.**
- **Selection is independent of YAML key order** (FW-7). Weighted draws sort
  their keys, so a catalog depends on the seed and the map contents alone.

Expected output is computed by scanning the **full catalog** via Aho-Corasick
(`framework/policy/matching.py`), not only injected rules.

Check `overlapping_match_documents` in the generation manifest before treating
any run as a qualification.

## Replacement token budget

Tokens exceed the 15-character runtime limit (`[PII:PERSON_NAME]` is 17), so
Themis truncates them all. Running `compare` without
`--replacement-max-length 15` reports mismatches - correctly, by design.

**Do NOT simply fail generation on tokens over 15 characters.** Almost every
token in use exceeds it, including the catalog behind the passing
qualification. That would make both shipped workloads ungeneratable.

Three modes are wanted deliberately:

| mode | purpose |
|---|---|
| long tokens, no compare flag | **the demo** - show the truncation limitation |
| long tokens, compare flag | today's qualification - works, but normalized |
| short tokens, no flag needed | **cleanest evidence** - exact byte comparison |

`compare` detects replacements that become identical under truncation and
reports affected would-be passes as `INCONCLUSIVE` rather than `PASS` (commit
`ca5c377`). See the INCONCLUSIVE section.

Still to do:

1. A generation-side option constraining tokens to the runtime budget, so a
   qualification needs no normalization. Opt-in - emitting oversized tokens
   deliberately is how the demo works.
2. A generation-time warning naming oversized tokens, as a backstop.

`--replacement-max-length` stays. It is the demo switch and remains useful for
modelling documented runtime behaviour even after Themis is fixed.

## INCONCLUSIVE verdict

The blind spot: `[FINANCIAL:CREDIT_CARD_NUMBER]` and
`[FINANCIAL:CREDIT_ROUTING]` both truncate to `[FINANCIAL:CRED`. A record where
the wrong rule fired was byte-identical to one where the right rule fired, and
`compare` scored it PASS.

Now:

- `compare` builds a collision map of replacements sharing a prefix within the
  limit, and downgrades affected would-be passes to `INCONCLUSIVE`.
- **Mismatches are deliberately left alone.** Truncation can only make two
  messages look more alike, never less, so an inequality is still genuine
  evidence of a product failure.
- The manifest records `records_inconclusive` and `replacement_collisions`
  (count plus up to 20 examples, with a `truncated` flag).
- The report counts inconclusive records as **neither passes nor failures** -
  withholds an overall PASS while any exist, styles the pass rate amber, and
  names the responsible tokens.

## Report failure details (FW-6) - done this session

Failing reports were one full-document `<article>` per failing row - at scale,
~2.6 MB of undifferentiated blocks with no diff, grouping, or classification.
Now `framework/reporting/generate_report.py`:

- `classify_failure` labels each failure by an explainable *diff-shape*
  signature (prefix-of-expected/truncation, actual longer, content lost,
  same-length-differs, `Execution failure (HTTP 503)`, ...). Shape, not cause.
- `group_failures` groups by signature, ordered by count then name.
- `render_failure_section` renders a summary table (signature | count | first
  example) then <=3 compact representatives per group. Each shows a windowed
  diff anchored on the first divergence byte; full messages stay in a collapsed
  `<details>`. Drops are stated ("Showing 3 of 187") with every remaining
  record ID listed - never silent.

Divergence offset is **computed** from the live `expected_message` /
`actual_message`; live comparison rows do NOT carry `divergence_offset` /
`byte_delta` (only the curated `issue-004-failure-sample.jsonl` does). On a
252-failure / 3-signature render the failure section is ~15 KB with 9 examples,
versus 252 full dumps before. INCONCLUSIVE rows never appear here. Tests:
`tests/test_report_failure_grouping.py`, proven non-vacuous against the old
full-dump renderer.

## Idea under discussion - pre-generated demo datasets

Generation is dead air in a demo: ~45s for 2,000 records, ~4 min for 10,000 on
the larger workload. Proposal is pre-built datasets in t-shirt sizes per
workload.

Design constraints:

- A dataset is a **bundle** - input, expected, and the matching policy. Only
  valid together.
- **Collides with limitation 2.** Themis holds one policy, so multiple demo
  datasets cannot be live simultaneously; switching demos costs a policy
  deploy.
- Keep them **out of git** - `artifacts/` was deliberately untracked. EC2 disk
  or S3, with configs and seeds in git so any bundle is reproducible.
- Define sizes by what they demonstrate, not round numbers.

## Deferred - emailable HTML render of docs, with copy buttons

**Not started; do when there is slack, not urgent.** Markdown has no copy button
on code blocks - that is a renderer feature (GitHub and VS Code preview give it
free; raw `.md` and PDF exports do not). For docs we hand off - the `docs/issues/`
register especially, where engineers copy-paste curl reproductions - render the
markdown to **self-contained HTML with a small inline copy button** on each code
block. No dependencies, opens offline in any browser, emailable.

Design:
- One HTML per issue (preserves "forward issues individually") is the default
  shape; a combined single-page variant is a nice-to-have.
- Markdown stays the source of truth; HTML is a generated, throwaway render.
- Output to a gitignored `handoff/` dir (same place the PDF export already goes),
  as a repeatable build step so re-running regenerates after any doc edit.
- Reuse it going forward for anything we hand off, not just the current issues.

## Next horizon - demonstrations and demonstration stories

**After Tier 2 and Tier 5.** The user wants to build a demo environment and demo
stories - how to show Themis (FPGA) and Aergia (RE2) to a buyer compellingly.
There is a big head start: an existing benchmark repo reviewed 2026-07-20 that
is most of the narrative and tooling already built. **Likely plan: create a NEW
repo for the demo environment and move over what we need from that kit.**

### Asset 1 - `preindex-benchmark-kit` (REVIEWED, reusable)

Path (this machine): `~/Code/nol8/preindex-benchmark-kit`. A "benchmark
workbench" with three use cases that map exactly to the demo horizon:

- **datapoint1 - Pre-Index Optimization:** govern what gets embedded before RAG
  indexing.
- **datapoint2 - Pre/Post-Inference Control:** govern what reaches the model and
  what leaves it (the model-boundary / prompt-injection filter angle).
- **datapoint3 - Agent-to-Agent Control:** govern messages/handoffs/tool-calls
  across an agent mesh (the ISSUE-006 agent-integration story).

Each pack ships synthetic datasets, reference lists (compromised accounts, bad
IPs, denied entities, payment cards...), a Go benchmark harness, Python analysis,
a polished data-driven HTML report, an AI-summary generator, and extensive
sales/talking-point docs. The datapoint-1 report is excellent (branded,
metric-driven: token reduction, prevented-from-embedding, governed share,
"listmatch CPU vs re2").

**~80% built; the one real gap is a contract mismatch.** `go/nol8_client.go`
already has a pluggable `nol8_api` mode that POSTs to `NOL8_ENDPOINT` with a
bearer token - the "live Nol8 validation pending" gap is exactly what our live
endpoints now close. But:
- Benchmark expects `{"text":...}` -> `{"action":"keep|mask|drop|route","text":...}`.
- Themis speaks `{"message":...}` -> `{"result":{"message":...}}` (redaction only,
  no action classification).
- Needs a thin adapter (~30-50 lines) mapping the fields and *deriving* the
  action (unchanged->keep, changed->mask; drop/route via policy sentinel tokens).
  That derivation - governance decisions as policy - is where our nol8-validation
  policy work applies directly. Check whether **Aergia (RE2)** is a closer fit;
  the report already benchmarks "vs re2".

**Terraform can be retired.** `aws_benchmark_harness` provisions one EC2 box to
*run the benchmark* (not to stand up Nol8). We already have the live endpoints
and the `data-streamer` EC2 with a checkout, so point `NOL8_ENDPOINT` at
Themis/Aergia and run the harness locally or on that box - no Terraform. Dropping
it also sheds 648 MB of cached provider binaries (the actual code/data is ~1 MB).

**Honesty caveat:** current reports show a simulated `nol8sim` placeholder, not
real measured results (the README is honest about this). A credible demo must
replace the placeholder with real measured `nol8_api` numbers and never present
simulated figures as real - same discipline as our validation work.

**Complementary to nol8-validation:** validation proves "the engine redacts
correctly" (correctness evidence); the kit proves "here is the value and the
performance story" (positioning). Together: correctness -> value -> narrative.

### Asset 2 - agentic (agent-to-agent) insurance-claims demo (NOT YET REVIEWED)

A second repo the user built: a **multi-agent (agent-to-agent) demo for insurance
claims**. Believed to have good work in it. **It is NOT on this MacBook Air yet** -
must be cloned/pulled down before it can be reviewed. Do that at the start of the
demo work, review it the same way, and see what to reuse (it likely overlaps
datapoint3's agent-mesh story).

### Conceptual threads that still feed the demo

- **"How do I do this with my data?"** - the honest answer ("the oracle is ours")
  is weak alone. Build toward **invariants** ("no unredacted SSN pattern appears
  in output", checkable with no oracle) and **synthetic canaries in a live
  stream**. See "Conceptual clarification - the oracle is ours".
- **Agent-mediated integration** is the fastest-growing buyer interest (ISSUE-006)
  and currently undemonstrable because the eval env is VPC-only; a reachable
  endpoint is the unlock.
- **The data-path question** (OBS-2): the intended production integration mode
  (inline/proxy/streaming?) shapes what a realistic demo looks like - worth
  engineering's answer before building the integration demo.
- **Pre-generated demo datasets** (the "Idea under discussion" section) remove
  generation dead-air during a live demo.

**Suggested first spike:** wire datapoint-1 (or datapoint-2) to the live Themis
endpoint through the adapter and produce one real report. Treat this whole
section as the seed; the plan gets built when we start.

---

# Immediate Next Actions

**In order:**

1. **Tier 5 - structure and tests. START HERE.** NOT STARTED. Re-read the Tier 5
   section of `docs/CODE_REVIEW_PLAN.md` against current code first (as with Tier
   2, some items may already be resolved). Work one item at a time, verify each
   issue is real before proposing changes, add a test per fix.

2. **Tier 2 - security. DONE 2026-07-21.** T2-3 fixed (FW-9); dead insecure
   scripts removed (FW-10); T2-1/T2-2 via FW-4/5; T2-4 residual = OBS-3. See the
   plan's Tier 2 status block.

3. **Then: build the demo environment.** Likely a new repo. Start by (a) cloning
   the **agentic insurance-claims** repo (not on this machine yet) and reviewing
   it, and (b) reusing `~/Code/nol8/preindex-benchmark-kit` - move over what we
   need, wire datapoint-1/2 to the live Themis/Aergia endpoints via an adapter,
   retire its Terraform. See "Next horizon - demonstrations" for the full review.

**In the background (user handles the send):** ISSUE-004 and the rest of the
issue register are ready in `docs/issues/`, with Slack comms drafted in
`docs/issues/internal/outbound-slack-comms.md`. Send ISSUE-004 first and alone;
the data-path question goes as its own note.

Done since last update:
- **FW-6** report usability (commit `4cc2185`) - grouped, compact failure
  details. See the FW-6 section.
- **FW-7** generation independent of YAML key order (commit `53ea077`).
- **Re-qualification** of the tenant under the post-FW-7 generator - new
  authoritative run `20260720T221534714262Z`, deployed and verified airtight,
  evidence promoted. The FW-7 reproducibility gap is closed (see above).

---

# Decisions Made - Do Not Reopen

- Five-stage lifecycle; do not collapse stages.
- `validate` is the only supported interface. Scripts are transport.
- Manifest-driven state, written atomically.
- Do NOT adjust validation expectations to make ISSUE-004 pass.
- A run where every request fails is deliberately NOT raised as a stage
  failure - that would block compare and report, leaving an exception instead
  of evidence. **The 2026-07-20 outage is exactly this case working as intended.**
- An unconfirmable record is INCONCLUSIVE, never PASS and never FAIL.
- `artifacts/runs/` is not tracked. Anything that must survive cleanup goes in
  `artifacts/evidence/`.
- **Generation is canonicalised** (FW-7): weighted selection sorts its keys, so
  output depends on the seed and config semantics, not serialization order.
  Accepting that this changed seed-42 output was a deliberate choice.

---

# Repository Hygiene

Tracked evidence in `artifacts/evidence/` with a README explaining provenance:

- `tenant-restore-policy.nol` - the deployed 5,000 rule policy (run
  `20260720T221534714262Z`, SHA `27fe47db...`). Themis cannot read back what is
  deployed, so this is the only copy. Generated under the current post-FW-7
  generator; reproducible from seed 42.
- `issue-004-failure-sample.jsonl` - 12 representative failures.
- `qualification-passing-report.html` - reference for a clean result.

`docs/CLEANUP_PLAN.md` records what was removed and what still needs a decision
(`scripts/restructure-framework.sh` and `scripts/process-message.sh` both look
dead but were not removed unilaterally).

`docs/product/validation-framework-overview.md` is a 0-byte placeholder.

**PDFs are not tracked.** The user generates PDF renders of the docs (via the
`yzane.markdown-pdf` VS Code extension) on demand to hand to engineering, then
removes them while work continues. `*.pdf` and `handoff/` are gitignored; the
extension is configured in `.vscode/settings.json` (itself gitignored) to export
to `handoff/`. Three PDFs were once committed by accident via `git add -A` -
**do not use `git add -A`; stage specific files** so generated artifacts never
ride along again.

Tests: 228, all passing.

```bash
source .venv/bin/activate && python -m unittest discover -s tests -q
```
