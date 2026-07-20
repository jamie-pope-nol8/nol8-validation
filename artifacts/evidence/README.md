# Preserved Evidence

Validation runs are no longer tracked in git - they are reproducible, large,
and caused the development and execution hosts to diverge. This directory holds
the small number of artifacts that must survive run cleanup.

Everything here is tracked deliberately. Do not add whole run directories.

---

## tenant-restore-policy.nol

The 5,000 rule policy currently deployed on the `tenant001-v1demo` Themis
tenant, from the authoritative qualification run `20260720T193444152733Z`.

```
SHA256  c3b763aa38b33e270557a7ec2921978bfc4765ba3b64e1f1adc5b5ffc8b72ca2
```

**This is the only copy.** Themis provides no way to read back the deployed
policy (THM-1), so if this file is lost the tenant's policy is unrecoverable.

Deploying any policy replaces the entire active ruleset (THM-2), so restore
after any deployment:

```bash
validate policy --file artifacts/evidence/tenant-restore-policy.nol --target themis
```

This catalog contains **no overlapping literals**, so it does not trigger
ISSUE-003, and its replacement tokens remain distinct after the runtime's
15-character truncation (THM-5), so a comparison can tell which rule fired.

Both properties are now enforced at generation time - a catalog lacking either
is refused rather than emitted.

> Superseded `20260719T161514709224Z`, whose catalog contained 31 overlapping
> literal pairs and three `[BUSINESS_TERMS:*]` tokens that collapsed under
> truncation. Kept in history only; do not deploy it.

## issue-003-failure-sample.jsonl

Twelve representative failures from the original qualification
(`20260719T161514709224Z`, 272 CONTENT_MISMATCH of 10,000).

Each row carries the record id, the byte offset where output diverged, the
byte delta, and trimmed excerpts of expected versus actual. The full 61 MB
comparison artifact is not retained - ISSUE-003 is reproducible from
`scripts/repro-issue-003-curl.sh` with no corpus at all, so this sample is
corroborating evidence rather than the primary proof.

## qualification-passing-report.html

The passing report from run `20260720T193444152733Z`:

```
5,000 rules / 10,000 records / customer-record-csv / seed 42
10,000 PASS · 0 CONTENT_MISMATCH · 0 EXECUTION_FAILURE · 0 INCONCLUSIVE
p50 12.618 ms · p95 14.383 ms · p99 17.032 ms
```

Retained as the reference for what a clean qualification looks like.

This supersedes the report from `20260719T230452981053Z`. That run also showed
10,000 PASS, but it predated collision detection and its catalog contained
three `[BUSINESS_TERMS:*]` tokens that became identical under truncation -
covering 4,755 transformations that could not, strictly, be confirmed. Under
current logic those records would be reported INCONCLUSIVE rather than PASS.

---

## Reproducing rather than retaining

Any run can be regenerated deterministically from its configuration and seed.
Verified: two generations from seed 42 produced byte-identical policy, input,
and expected artifacts. Prefer regenerating over keeping artifacts:

```bash
validate generate --config config/workloads/customer-record-csv.yaml \
  --rules 5000 --records 10000
```
