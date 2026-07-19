# Preserved Evidence

Validation runs are no longer tracked in git - they are reproducible, large,
and caused the development and execution hosts to diverge. This directory holds
the small number of artifacts that must survive run cleanup.

Everything here is tracked deliberately. Do not add whole run directories.

---

## tenant-restore-policy.nol

The 5,000 rule policy currently deployed on the `tenant001-v1demo` Themis
tenant, from run `20260719T161514709224Z`.

**This is the only copy.** Themis provides no way to read back the deployed
policy, so if this file is lost the tenant's policy is unrecoverable.

`validate policy` and `scripts/load-policy.sh` replace the entire active policy,
so restore after any deployment:

```bash
./scripts/load-policy.sh themis artifacts/evidence/tenant-restore-policy.nol
```

Note this catalog contains 31 overlapping literal pairs and therefore triggers
ISSUE-003. It is retained because it is what is deployed, not because it is a
good catalog.

## issue-003-failure-sample.jsonl

Twelve representative failures from the original qualification
(`20260719T161514709224Z`, 272 CONTENT_MISMATCH of 10,000).

Each row carries the record id, the byte offset where output diverged, the
byte delta, and trimmed excerpts of expected versus actual. The full 61 MB
comparison artifact is not retained - ISSUE-003 is reproducible from
`scripts/repro-issue-003-curl.sh` with no corpus at all, so this sample is
corroborating evidence rather than the primary proof.

## qualification-passing-report.html

The passing report from run `20260719T230452981053Z`: 5,000 rules, 10,000
records, 10,000 PASS, zero content mismatches, generated after both the
non-overlapping catalog fix and the replacement token distinctness fix.

Retained as the reference for what a clean qualification looks like.

---

## Reproducing rather than retaining

Any run can be regenerated deterministically from its configuration and seed.
Prefer regenerating over keeping artifacts:

```bash
validate generate --config config/workloads/customer-record-csv.yaml \
  --rules 5000 --records 10000
```
