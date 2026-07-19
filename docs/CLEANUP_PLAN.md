# Repository Cleanup Plan

Date: 2026-07-19  
Status: Proposed - not yet executed  
Scope: Repository hygiene and artifact retention, Mac and EC2

This plan exists because validation runs write into a tracked directory, so
routine execution produces git churn and the development and execution hosts
drift apart.

Nothing here is urgent. None of it blocks the ISSUE-003 handover. Execute when
there is a natural pause.

---

## Current state

Mac (development):

```
artifacts/          3.5 MB      37 files tracked in git
docs/                56 KB
framework/          412 KB
tests/              304 KB
```

EC2 (execution):

```
artifacts/          169 MB      11 validation runs
git status          21 pending changes, all artifact deletions
```

The EC2 pending changes are deletions of artifacts that are tracked in git.
Neither host is wrong; the directory should not have been tracked.

---

## Phase 1 - Stop tracking run output

The structural fix. Everything else is tidying.

Validation runs are reproducible from configuration and are large. They are
evidence, not source.

Actions:

- Add `artifacts/runs/` to `.gitignore`.
- `git rm -r --cached artifacts/runs/` to untrack without deleting on disk.
- Keep `artifacts/initial-functional-baseline/` tracked. It is a small,
  deliberate reference baseline (16 KB).
- Decide on `artifacts/test-documents/` (1.5 MB). If these are fixed inputs
  rather than run output, they are source and should stay tracked.

Effect: validation runs stop dirtying the tree, and the two hosts stop
diverging.

Caution: run artifacts referenced as evidence in issue documentation must
survive this change. `20260719T161514709224Z` is cited throughout ISSUE-003.
Preserve it before untracking - see Phase 2.

---

## Phase 2 - Preserve evidence deliberately

Issue documentation cites run artifacts as evidence. Once `artifacts/runs/` is
untracked, that evidence is only as durable as one host's disk.

Actions:

- Create `artifacts/evidence/` and track it.
- Copy the specific files cited by open issues into it, not whole runs:
  - `20260719T161514709224Z/generated/comparison.jsonl` (ISSUE-003, 272
    failures)
  - `20260719T161514709224Z/generated/scale-policy.nol` (the catalog containing
    the 31 prefix literals)
- Update ISSUE-003 evidence paths to point at the preserved copies.

Rationale: the qualification run is the primary evidence for a customer-facing
defect. It should not be deletable by a routine cleanup.

---

## Phase 3 - EC2 retention

169 MB across 11 runs, growing with each execution.

Actions:

- Keep `20260719T161514709224Z` indefinitely. It is cited evidence.
- Keep the most recent run for debugging.
- Delete the remainder after confirming nothing references them.
- Adopt a retention rule: keep the newest N runs plus anything explicitly
  referenced by documentation.

Do not automate deletion until the rule is agreed. Silent deletion of evidence
is the failure mode to avoid.

---

## Phase 4 - Dead and misplaced files

Verify each before acting. None are confirmed dead.

`scripts/restructure-framework.sh`  
A one-time migration script. The only references to it are inside itself. If
the migration is complete, remove it. Confirm with the team first - it may be
retained deliberately as a record of the layout change.

`scripts/process-message.sh`  
No references found in the repository. May be a manual convenience tool. Ask
before removing.

`docs/continue-conversation.md`  
Contains session operating rules and workflow conventions. This is agent and
contributor guidance, not project documentation. Consider moving to
`CLAUDE.md` at the repository root, where tooling and contributors will
actually find it.

`.DS_Store`  
Present on disk under `docs/architecture/`, not tracked. Add `.DS_Store` to
`.gitignore` - the current entry only covers the repository root.

---

## Phase 5 - Follow-up work surfaced by ISSUE-003

Not cleanup, but recorded here so it is not lost. Add to
`docs/issues/technical_debt.md`:

- Detect literals that are a strict prefix of another literal during policy
  generation and report them before execution. The framework currently
  produces overlapping literals by construction and cannot warn about it.
- Offer a generation mode that produces no overlapping literals, so future
  qualification runs can isolate behavior other than ISSUE-003.

---

## Execution order

Phase 2 before Phase 1. Preserve the evidence before untracking the directory
that holds it.

Phases 3, 4, and 5 are independent and can be done in any order.
