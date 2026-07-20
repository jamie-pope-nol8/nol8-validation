# Documentation Map

Every document, what it is for, and when to read it.

## Start here

| Document | Read it when |
|---|---|
| [FINDINGS.md](FINDINGS.md) | **You want to know what we have found.** Every finding, stable IDs, one paragraph each, links to detail. |
| [continue-conversation.md](continue-conversation.md) | You are resuming work. Project state, environments, what to do next. |

Those two answer almost every question. The rest is detail they point to.

## Product findings - things Themis does

| Document | Contains |
|---|---|
| [product/themis-product-limitations.md](product/themis-product-limitations.md) | THM-1 to THM-7 and OPS-1 to OPS-3, in full, with evidence |
| [issues/KNOWN_BEHAVIORS.md](issues/KNOWN_BEHAVIORS.md) | Accepted runtime behaviour to design around (KB-001), and the ISSUE-003 authoring constraint |

## Issues

| Document | Contains |
|---|---|
| [issues/20260719-ISSUE-003-scale-validation-transformation-mismatch.md](issues/20260719-ISSUE-003-scale-validation-transformation-mismatch.md) | THM-4 in full: overlapping matches corrupt output. Evidence, reproduction, what was ruled out |
| [issues/ISSUE-003-handover-message.md](issues/ISSUE-003-handover-message.md) | Ready-to-send Slack and email drafts, plus the reasoning behind each choice |
| [issues/technical_debt.md](issues/technical_debt.md) | Minor framework debt, no customer impact |

## Our framework

| Document | Contains |
|---|---|
| [CODE_REVIEW_PLAN.md](CODE_REVIEW_PLAN.md) | Full review of the codebase, tiered by risk. FW-1 to FW-7 |
| [architecture/validation-boundaries.md](architecture/validation-boundaries.md) | What the framework proves and, importantly, what it does not |
| [USE_CASES.md](USE_CASES.md) | Scenarios the framework is built to cover |
| [CLEANUP_PLAN.md](CLEANUP_PLAN.md) | What was removed from the repo and what still needs a decision |

## Evidence

`artifacts/evidence/` holds what must survive cleanup - the deployed policy
(the only copy, see THM-1), failure samples, and a reference passing report.
Its README explains provenance.

`artifacts/runs/` is **not** tracked. Anything that matters goes to
`artifacts/evidence/`.

## Placeholders - empty, do not cite

`ARCHITECTURE.md`, `REPORTS.md`, and `product/validation-framework-overview.md`
are 0-byte stubs. They are listed here so nobody hunts for content that was
never written.
