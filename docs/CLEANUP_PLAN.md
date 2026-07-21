# Repository Cleanup

Date: 2026-07-19  
Status: Executed

Validation runs wrote into a tracked directory, so routine execution produced
git churn and the development and execution hosts drifted apart. EC2 had
accumulated 1.4 GB of run output and 27 pending git changes, all deletions of
tracked artifacts.

---

## What changed

**`artifacts/runs/` is no longer tracked.** Runs are reproducible from
configuration and seed, are large, and tracking them made the two hosts fight.
Added to `.gitignore` and removed from the index with `git rm --cached`, so
existing files stayed on disk.

**`artifacts/test-documents/` removed.** Ten generated sample documents, one
per format, dating from the initial commit. Content was `_synthetic_padding`;
one `.eml` was 938 KB of filler. Nothing in the repository referenced them.
Recoverable from history at `99dac01` if ever needed.

**`artifacts/initial-functional-baseline/` retained.** 16 KB, three files, and
referenced by `scripts/restructure-framework.sh`.

**`artifacts/evidence/` created and tracked.** Holds the small number of
artifacts that must survive run cleanup. See its README for provenance.

---

## The dependency that nearly bit

`scripts/load-policy.sh` replaces the entire active Themis policy, and Themis
provides no way to read back what is deployed. Tenant recovery therefore
depends on retaining a copy of the deployed policy file.

That file lived only inside `artifacts/runs/20260719T161514709224Z/` on EC2 -
untracked, and about to be deleted by this cleanup. Removing run artifacts
without preserving it first would have made the demo tenant's policy
unrecoverable.

It is now tracked at `artifacts/evidence/tenant-restore-policy.nol`, and the
restore command in `docs/continue-conversation.md` points there.

**Rule going forward:** never make tenant recovery depend on anything under
`artifacts/runs/`.

---

## Retention

Keep on EC2:

- the current passing qualification, for reference
- the most recent run, for debugging

Delete everything else. Anything cited as evidence belongs in
`artifacts/evidence/` on the Mac, not in a run directory.

Regenerate rather than retain:

```bash
validate generate --config config/workloads/customer-record-csv.yaml \
  --rules 5000 --records 10000
```

---

## Removed 2026-07-21 (Tier 2 review, FW-10)

`scripts/restructure-framework.sh`, `scripts/process-message.sh`, and
`framework/execution/run_functional_test.py` (with its empty package
`__init__.py`) were removed. Verified unreferenced by any live code or test.
`process-message.sh` and `run_functional_test.py` carried the unauthenticated
processing paths (T2-5) and the plaintext writer (T2-4); deleting them resolved
those findings outright rather than hardening dead code. See FINDINGS FW-10.

`docs/continue-conversation.md` contains working conventions that would serve
better as `CLAUDE.md` at the repository root, where tooling and contributors
will find them.
