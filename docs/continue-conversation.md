# Continue Conversation

Last Updated: 2026-07-19

This document is the durable memory of the project. It exists so a new session
can continue without reconstructing context from chat history.

## Maintaining this file

When the user says **"update the project"**, rewrite this file to reflect
current state. Also refresh it at the end of meaningful work sessions and
before any risk of context loss.

Rewrite it. Do not append to it and do not preserve stale sections because
they are already here - a previous revision claimed `compare` and `report` were
NOT STARTED long after both had shipped, which would have sent a new session
to redo finished work. Accuracy matters more than history.

---

# The Short Version

There are TWO separate problems. Do not conflate them.

**1. Themis has a real defect (ISSUE-003).** Two rules matching overlapping
text cause the runtime to write the replacement at the wrong offset and destroy
adjacent data. Silent - HTTP 200 every time. Proven with plain curl, no
framework code involved, so the finding does not depend on this repository.
This is the escalation-worthy finding.

**2. The framework had its own defects**, now largely fixed. It generated test
data that happens to trip the Themis bug; it computed expected output from an
invariant that was false, so it blamed Themis for correct behaviour; and it had
ordinary bugs (non-reproducible generation, an outright crash at realistic rule
counts).

The 272 qualification failures are genuine Themis corruption - independently
confirmed. But the framework's own measurement bugs would have added false
failures on top, which is why they had to be fixed before any claim is made
using its output.

---

# Session Operating Rules

## Execution Style

- Work one action at a time.
- Do not provide batches of commands unless they are inseparable.
- End responses with a clear next action.

## Context Preservation

This is a continuation of an existing engineering effort.

Do not:
- ask the user to re-explain the project
- restart architectural discussions already resolved
- suggest replacing working tooling
- introduce unnecessary frameworks
- assume only one development environment exists

## Decision Discipline

Before proposing changes:
- understand why the current design exists
- verify whether the issue is real
- prefer incremental fixes over redesign

---

# Environments

Two environments, both required.

| | Mac | EC2 |
|---|---|---|
| purpose | development, commits | execution against Themis |
| path | `~/Code/nol8/nol8-validation` | `/opt/nol8/nol8-validation` |
| python | 3.12 | 3.14.4 |
| host alias | - | `nol8-demo` (in `~/.ssh/config`) |

Workflow: edit and commit on Mac, push, `git pull` on EC2, execute there.

SSH from Mac to EC2 works non-interactively. Assistants can run read-only
analysis directly rather than round-tripping commands through the user.

On EC2 the `validate` console script requires the venv:

```bash
cd /opt/nol8/nol8-validation && source .venv/bin/activate
```

---

# CLI

```
validate generate --config <yaml> [--rules N] [--records M]
validate policy   --run <RUN_ID> --target themis
validate run      --run <RUN_ID> --target themis [--limit N]
validate compare  --run <RUN_ID> [--replacement-max-length 15]
validate report   --run <RUN_ID>
```

`--run` accepts a bare run ID or a path. All five stages are implemented.

`config/workloads/enterprise-dlp.yaml` defaults to 5,000 rules and 10,000
records - roughly a 7 minute run. Pass `--rules`/`--records` for a smoke test.

---

# CRITICAL OPERATIONAL WARNING

`validate policy` and `scripts/load-policy.sh` **replace the entire active
policy** on the target tenant. There is no namespacing, no versioning, and no
way to read back what is currently deployed.

The target is a shared sales demo tenant (`tenant001-v1demo`).

Always restore afterwards:

```bash
./scripts/load-policy.sh themis \
  artifacts/runs/20260719T161514709224Z/generated/scale-policy.nol
```

That file is the only copy of the qualification policy. If it is lost, the
tenant's policy is unrecoverable.

---

# Current State - 2026-07-19

## ISSUE-003: confirmed Themis defect, ready for handover

**Overlapping matches corrupt Themis output.** When two rules match overlapping
regions of the input, the runtime computes the wrong match start offset and
destroys content preceding the match. Silent - every request returns HTTP 200.

Proven with plain curl against Themis's own response payload. No framework code
in the path, so the finding does not depend on this repository.

```
rules   "ABCD" -> "[P]"  and  "DEFG" -> "[Q]"
input    x ABCDEFG y
correct  x [P]EFG y
actual   x [P[Q] y
```

Key facts, all empirically established:

- Either rule alone renders correctly. Only coexistence triggers it.
- Rule order in the policy does not matter.
- Adjacent, non-overlapping matches are correct. Disjoint matches are correct.
- Replacement length is irrelevant. Shorter replacements destroy MORE
  preceding content.
- Replacement output is NOT re-scanned (single pass, confirmed).
- Unrelated to KB-001 replacement truncation.

Static condition: two literals can produce overlapping matches when either
contains the other, OR when a non-empty proper suffix of one equals a proper
prefix of the other.

Reproductions:
- `scripts/repro-issue-003-curl.sh` - plain curl, no framework. **Lead with
  this for engineering, who have never seen this repository.**
- `scripts/repro-issue-003.py` - 11 cases including controls, 5 corrupt.

Documented in:
- `docs/issues/20260719-ISSUE-003-scale-validation-transformation-mismatch.md`
- `docs/issues/KNOWN_BEHAVIORS.md` (KB-001 is separate and unrelated)
- `docs/architecture/validation-boundaries.md`

## Qualification runs

### Clean qualification - 20260719T230452981053Z (CURRENT, PASSING)

Generated after both the non-overlapping generator fix AND the replacement
token distinctness fix. This is the authoritative result: no known blind spot.

```
5,000 rules / 10,000 records / customer-record-csv
overlapping_match_documents: 0
replacement tokens distinct under 15-character truncation

Requests succeeded: 10,000    Requests failed: 0
PASS: 10,000                  CONTENT_MISMATCH: 0
Latency p50/p95/p99: 12.492 / 14.214 / 16.686 ms
Report: PASS, 100.00%
```

Requires `--replacement-max-length 15` for KB-001. Without it, all 7,479 dirty
records fail on replacement truncation alone and only the 2,521 clean records
pass. That is expected and documented behaviour, not a defect in this run.

Like-for-like with the original: same workload, clean/dirty split and payload
size within 1%.

**This proves ISSUE-003 was the SOLE cause of the original 272 failures.** It
also means ISSUE-003 is not a marginal edge case - it accounted for every
failure in the original qualification.

### Earlier clean qualification - 20260719T204836698102Z (superseded)

Same result (10,000 PASS) but produced while three `[BUSINESS_TERMS:*]` tokens
still collapsed to one string under truncation, so a wrong-rule application in
that family would have scored PASS. Superseded by the run above; do not cite
it.

### Original qualification - 20260719T161514709224Z (FAILING, retained as evidence)

```
5,000 rules / 10,000 records
9,728 passed, 272 CONTENT_MISMATCH (97.28%)
```

Caused by ISSUE-003. Cited throughout the issue documentation; preserve it.

## Replacement token distinctness - RESOLVED

`--replacement-max-length 15` truncates expected replacements, and truncation
is not injective. Three tokens previously collapsed to one string:

```
[BUSINESS_TERMS:CONTRACT_NUMBER]  ->  [BUSINESS_TERMS
[BUSINESS_TERMS:CUSTOMER_ID]      ->  [BUSINESS_TERMS
[BUSINESS_TERMS:SUPPORT_CASE_ID]  ->  [BUSINESS_TERMS
```

A wrong-rule application within that family scored PASS, covering 4,755
transformations in the first clean qualification.

Category and pattern names are now abbreviated so every token stays distinct
within the 15-character budget - `[BIZ:CONTRACT_NUMBER]`, `[BIZ:CUSTOMER_ID]`,
`[BIZ:SUPPORT_CASE_ID]`. Generation refuses a catalog whose tokens collide when
truncated.

The exhaustive test over every category and pattern combination also caught
`internal_url` and `internal_product_name`, which both reduce to `INTERNAL_`.
The shipped configurations avoid it by placing them in different families, so
testing only shipped configurations would have missed it.

## Code review

Full review of ~7,800 lines recorded in `docs/CODE_REVIEW_PLAN.md`, tiered by
risk. Central finding: the framework can report a result that is not true in
both directions.

- **Tier 0 - COMPLETE.** The framework could report success it had not
  verified. Fixed: a 2xx no longer implies success without a processed
  message; every failed request carries an error category; an empty comparison
  renders INCONCLUSIVE not a green PASS; pass rate cannot round to 100.00%
  with failures present.
- **Tier 1 - MOSTLY COMPLETE.** Generator false positives - the framework
  blamed Themis for its own bugs.
  - T1-1 expected output from full catalog - **DONE, verified at scale**
  - T1-2 clean records containing literals - **SURFACED** in the generation
    manifest, not prevented
  - T1-3 expected-value algorithm - **RESOLVED**, see below
  - T1-4 support ticket abort - **DONE**
  - T1-5 generation determinism - **DONE**
  - T1-6 YAML key order dependence - **NOT STARTED**

T1-3 resolution: Themis was tested directly. Where matches do not overlap it
behaves as leftmost-longest, which `resolve_non_overlapping` implements. Where
matches DO overlap Themis corrupts the output, so no expected value is correct
and the framework records the exposure instead of guessing.

### Non-overlapping generation - RESOLVED

The generator previously emitted literals nested inside one another, so every
catalog contained overlapping pairs, every scale run reproduced ISSUE-003, and
no scale run could establish transformation correctness.

Five generators used a variable-width index in a position allowing
containment - `person_name`, `street_address`, `ipv4_address`, `ipv6_address`,
`internal_product_name`. All now use fixed-width components.

Generation now REFUSES to proceed if the catalog contains a nested literal
pair, rather than producing a corpus that cannot answer the question it was
generated for. That guard is what caught `internal_product_name`, which the
manual sweep missed.

Verified at 5,000 rules / 2,000 records:

```
overlapping_match_documents      0
intended_clean_with_literals     0
```

Containment is checked, not the wider suffix/prefix class. Containment is
unavoidable - wherever the outer literal appears the inner one necessarily
matches inside it. The suffix/prefix class needs the literals to abut in the
input, never occurs on generated corpora, and reporting it produced 1.28
million pairs on the 5,000 rule catalog.

Still check `overlapping_match_documents` in the generation manifest before
treating any run as a qualification.

### Tier 1 foundation (done)

`framework/policy/matching.py` - Aho-Corasick over the catalog.
`LiteralMatcher.find_all` returns every occurrence of every literal in one pass
per document. `overlapping_matches` finds matches sharing bytes;
`resolve_non_overlapping` does leftmost-longest selection.

`framework/policy/overlap.py` - static literal-pair analysis. **Use with
care:** run against the 5,000 rule catalog the suffix/prefix rule reports
1,277,627 pairs in 26 seconds, nearly all one-character joins. It is not
actionable on its own. Document-level detection via `matching.py` is the
precise signal.

### Corpus audit (measured on run 20260719T161514709224Z)

```
10,000 documents scanned in 1.66 s against 5,000 rules
documents containing OVERLAPPING matches: 415 (4.15%)
documents with UNACCOUNTED literals:      415 (4.15%)  - same documents
CLEAN documents containing literals:      0
```

The unaccounted literals in this corpus are the overlap partners themselves
(`Elena Chen` alongside `Elena Chen 2527`), so T1-1 exposure and ISSUE-003
exposure are the same population here.

**415 documents are exposed but only 272 failed**, so overlap presence is
necessary but not sufficient - roughly a third render correctly. Do not assume
every overlapping document corrupts.

The suffix class appears in real data: `document-000061` carries
`'3560 Cedar Avenue, Charlotte NC'` and `'560 Cedar Avenue, Charlotte NC'`.

Clean-record contamination measured 0 here, but a reviewer measured 1.5% on a
`healthcare_claim`/`text` configuration, so that path remains a real risk.
- Tiers 2-5 not started: security, product limitations, evidence quality,
  structure and tests.

---

# Immediate Next Actions

1. **Tier 2 security** (`docs/CODE_REVIEW_PLAN.md`): `curl -k` on the policy
   control plane, and both transports sourcing a git-tracked `config/demo.env`.

2. **Tier 4 report usability**: a failing report renders every failure as a
   full expected/actual pair with no diff, grouping, or root-cause
   classification - 2.6 MB for 272 failures. Passing reports are fine (12 KB).

3. **T1-6: generation depends on YAML key order**, not only the seed.
   `generate_workload.py` `_weighted_item` builds a list from `dict.keys()` and
   passes it to `random.choices`. Latent today because the config snapshot uses
   `sort_keys=False`, but any re-serialization silently invalidates
   reproducibility.

---

# Decisions Made - Do Not Reopen

- Five-stage lifecycle. Do not collapse stages.
- Artifacts are first class; the run directory is the source of truth.
- Manifest-driven state, written atomically.
- Transport boundary: Python owns orchestration, shell owns curl and
  authentication. Python does not handle tokens.
- Do NOT adjust validation expectations to make ISSUE-003 pass. The framework
  output is correct; masking corruption would hide a customer-facing defect.
- A run where every request fails is deliberately NOT raised as a stage
  failure. Failing the stage blocks compare and report, leaving the operator
  with an exception instead of evidence.

---

# Product Limitations Surfaced

These are Themis characteristics, not framework bugs. They affect what can be
sold, not just what can be tested.

- **Wholesale policy replacement.** No namespace, version, partial update,
  rollback, or read-back. Two teams sharing a credential silently clobber each
  other. Recovery depends on a human retaining the previous file.
- **Fire-and-forget deployment.** The response carries `command_id` and
  `stage: apollo`, suggesting async distribution, but nothing polls for
  convergence. Records sent immediately after deployment may be evaluated
  against the previous policy.
- **Reported latency is not a product measurement.** Every request opens a
  fresh TCP+TLS connection; failed requests contribute 0.0 ms to the average.

---

# Open Cleanup

`docs/CLEANUP_PLAN.md` - phased, not executed. Key structural issue:
`artifacts/` is tracked in git, so validation runs dirty the tree and the two
hosts diverge. EC2 holds ~169 MB. Preserve cited evidence before untracking.
