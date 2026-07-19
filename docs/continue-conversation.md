# Continue Conversation

Last Updated: 2026-07-19

Durable memory of the project, so a new session can continue without
reconstructing context from chat history.

## Maintaining this file

When the user says **"update the project"**, rewrite this file to reflect
current state. Also refresh it at the end of meaningful work sessions.

Rewrite it wholesale. Do not append, and do not preserve stale sections because
they are already here - a previous revision claimed `compare` and `report` were
NOT STARTED long after both had shipped, which would have sent a new session to
redo finished work. Accuracy over history.

---

# The Short Version

Two separate problems. Do not conflate them.

**1. Themis has real product defects.** The headline is ISSUE-003: two rules
matching overlapping text cause the runtime to write the replacement at the
wrong offset and destroy adjacent data, silently, HTTP 200 every time. Proven
with plain curl, no framework code involved. Full product findings in
`docs/product/themis-product-limitations.md`.

**2. The framework had its own defects**, now fixed. It generated data that
tripped the Themis bug, computed expected output from a false invariant (and so
blamed Themis for correct behaviour), and had ordinary bugs. All corrected and
verified at scale.

Current status: **the framework produces trustworthy evidence.** A clean
5,000 rule / 10,000 record qualification passes 100%.

---

# Session Operating Rules

- Work one action at a time. End responses with a clear next action.
- `validate` is the product surface. Do NOT call `scripts/*.sh` directly -
  every operation, including policy restore, runs through `validate`.
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
works non-interactively, so read-only analysis can be run directly.

Always activate first:

```bash
cd /opt/nol8/nol8-validation && source .venv/bin/activate
```

Long-running commands over SSH must be detached (`nohup setsid ... &`), or an
SSH drop kills them. When polling for completion, grep a log for a completion
marker - `pgrep -f "validate run"` matches its own command line and hangs.

The EC2 environment is a **test and demo environment**, not production.
Overwriting a policy is not an emergency.

---

# CLI

```bash
validate generate --config <yaml> [--rules N] [--records M]
validate policy   --run <RUN_ID> | --file <path.nol> | --status
validate run      --run <RUN_ID> [--limit N]
validate compare  --run <RUN_ID> [--replacement-max-length 15]
validate report   --run <RUN_ID>
```

`--run` accepts a bare run ID or a path. Fully documented in `README.md`.

End-to-end smoke test, about a minute:

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

`--replacement-max-length 15` is required because of KB-001. Without it every
record with a longer replacement reports as a mismatch. That is expected.

---

# Current State - 2026-07-19

## Clean qualification - 20260719T230452981053Z (AUTHORITATIVE)

```
5,000 rules / 10,000 records / customer-record-csv
overlapping_match_documents: 0
replacement tokens distinct under 15-character truncation

Requests succeeded: 10,000    Requests failed: 0
PASS: 10,000                  CONTENT_MISMATCH: 0
Latency p50/p95/p99: 12.492 / 14.214 / 16.686 ms
Report: PASS, 100.00%
```

Like-for-like with the original failing run: same workload, clean/dirty split
and payload size within 1%.

**This proves ISSUE-003 was the sole cause of the original 272 failures**, and
that it is not a marginal edge case.

An earlier clean run (`20260719T204836698102Z`) reported the same 100% but
predates the replacement token fix, so a wrong-rule application within
business_terms would have scored PASS. Superseded - do not cite it.

The original failing run (`20260719T161514709224Z`, 272 mismatches) is retained
only as a sample in `artifacts/evidence/`.

## ISSUE-003 - ready for handover

**Overlapping matches corrupt Themis output.** Two rules matching overlapping
regions cause the runtime to compute the wrong match start offset and destroy
content preceding the match. Silent; HTTP 200.

Empirically established:

- Either rule alone renders correctly. Only coexistence triggers it.
- Rule order does not matter.
- Adjacent and disjoint matches are correct. Only shared bytes corrupt.
- Replacement length is irrelevant; shorter replacements destroy MORE.
- Replacement output is NOT re-scanned (single pass).
- Unrelated to KB-001.

Static condition: two literals can overlap when either contains the other, OR
when a non-empty proper suffix of one equals a proper prefix of the other.

**Lead the handover with `scripts/repro-issue-003-curl.sh`** - plain curl, runs
with no part of this repository present. Engineering has never seen this
codebase, so a framework-dependent repro is dismissible.
`scripts/repro-issue-003.py` covers 11 cases including controls; 5 corrupt.

## Themis product limitations

`docs/product/themis-product-limitations.md` - five findings. The three
policy-lifecycle ones share a root cause: **a policy is not a first-class
object.** No identity, no version, no read-back. An operator cannot answer
"what is enforcing right now?", which is unacceptable during an incident.

`validate policy --status` is a partial mitigation: a local ledger of
deployments made through the CLI. It states its own limitation in the output,
because a record that looks authoritative but is not would be worse than none.

## Code review

`docs/CODE_REVIEW_PLAN.md` - full review of ~7,800 lines, tiered by risk.

- **Tier 0 COMPLETE** - the framework could report success it had not verified.
- **Tier 1 COMPLETE** except T1-6 - generator false positives.
- **Tier 2 NOT STARTED** - security.
- **Tier 3** - product limitations, now written up.
- **Tier 4 NOT STARTED** - evidence quality and report usability.
- **Tier 5 NOT STARTED** - structure and tests.

## Generator guarantees

Generation now REFUSES to produce a catalog that would make results
meaningless:

- **No nested literals.** Five generators used a variable-width index allowing
  containment; all now fixed-width. The guard caught a fifth
  (`internal_product_name`) that a manual sweep missed.
- **Replacement tokens stay distinct under 15-character truncation.** Three
  `[BUSINESS_TERMS:*]` tokens previously collapsed to one string, so wrong-rule
  application scored PASS across 4,755 transformations. Categories and two
  pattern names are now abbreviated - `[BIZ:CONTRACT_NUMBER]` etc.

Expected output is computed by scanning the **full catalog** via Aho-Corasick
(`framework/policy/matching.py`), not only injected rules. The old assumption
was false: 415 of 10,000 documents carried literals it missed.

Check `overlapping_match_documents` in the generation manifest before treating
any run as a qualification.

---

# Immediate Next Actions

1. **Hand ISSUE-003 to Themis engineering.** Ready, self-contained, highest
   external value. Lead with the curl repro.

2. **Tier 2 security.** `scripts/load-policy.sh` uses `curl -k`, disabling TLS
   verification on the one call carrying both the bearer token and the complete
   ruleset. First establish empirically whether `-k` is necessary -
   `run-validation.sh` does not use it, suggesting a certificate problem on the
   control plane, which would itself be a product finding. Also: both
   transports `source config/demo.env`, which is committed, so anyone who can
   land a change to it gets code execution plus the tokens sourced next.

3. **Tier 4 report usability.** Passing reports are fine. Failing reports are
   2.6 MB of undifferentiated blocks with no diff, grouping, or root-cause
   classification. Highest-value addition: warn when the deployed policy
   contains overlapping literals, converting "272 records failed" into "your
   policy has overlapping literals, here they are".

4. **T1-6: generation depends on YAML key order**, not only the seed.
   `_weighted_item` builds a list from `dict.keys()` and passes it to
   `random.choices`. Latent because the snapshot uses `sort_keys=False`.

---

# Decisions Made - Do Not Reopen

- Five-stage lifecycle; do not collapse stages.
- `validate` is the only supported interface. Scripts are transport.
- Artifacts are first class; the run directory is the source of truth.
- Manifest-driven state, written atomically.
- Do NOT adjust validation expectations to make ISSUE-003 pass.
- A run where every request fails is deliberately NOT raised as a stage
  failure - that would block compare and report, leaving an exception instead
  of evidence.
- `artifacts/runs/` is not tracked in git. Anything that must survive cleanup
  goes in `artifacts/evidence/`.

---

# Repository Hygiene

`artifacts/runs/` is gitignored; runs are reproducible from config and seed.
Tracked evidence lives in `artifacts/evidence/` with a README explaining
provenance:

- `tenant-restore-policy.nol` - the deployed 5,000 rule policy. Themis cannot
  read back what is deployed, so this is the only copy.
- `issue-003-failure-sample.jsonl` - 12 representative failures.
- `qualification-passing-report.html` - reference for a clean result.

`docs/CLEANUP_PLAN.md` records what was removed and what still needs a decision
(`scripts/restructure-framework.sh` and `scripts/process-message.sh` both look
dead but were not removed unilaterally).

Note: `docs/product/validation-framework-overview.md` is a 0-byte placeholder.

Tests: 189, all passing. Run with:

```bash
source .venv/bin/activate && python -m unittest discover -s tests -q
```
