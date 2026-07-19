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

## Qualification run

```
Run ID: 20260719T161514709224Z
5,000 rules / 10,000 records
10,000/10,000 requests succeeded
9,728 passed, 272 CONTENT_MISMATCH (97.28%)
```

The 272 are caused by ISSUE-003. **272 is a floor, not an exact count** -
`--replacement-max-length 15` collapses three `[BUSINESS_TERMS:*]` tokens to
one string, so wrong-rule application within that family scores as PASS.

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

1. **T1-6: generation depends on YAML key order**, not only the seed.
   `generate_workload.py` `_weighted_item` builds a list from `dict.keys()` and
   passes it to `random.choices`. Latent today because the config snapshot uses
   `sort_keys=False`, but any re-serialization silently invalidates
   reproducibility. Fix by sorting names before weighting, then assert a
   round-tripped config produces an identical corpus.

2. **A clean qualification run.** The generator still emits overlapping
   literals by construction (`"First Last"` for index <= 400 and
   `"First Last {index}"` above; `street_address` produces suffix pairs). Until
   a non-overlapping generation mode exists, every scale run reproduces
   ISSUE-003 and cannot establish transformation correctness.

   Check `overlapping_match_documents` in the generation manifest before
   treating any run as a qualification.

3. **Tier 2 security** (`docs/CODE_REVIEW_PLAN.md`): `curl -k` on the policy
   control plane, and both transports sourcing a git-tracked `config/demo.env`.

4. **Tier 4 report usability**: 272 failures render as 272 near-identical
   blocks with no diff, grouping, or root-cause classification. The report is
   honest now but not usable as customer evidence at 2.6 MB.

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
