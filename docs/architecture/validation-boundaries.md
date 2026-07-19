Purpose:
Document validation framework capability boundaries discovered through engineering experiments.

Include:

# Validation Boundaries

## Purpose
Explain that this document records tested capability limits, discoveries, and required evolution before customer-facing proof-of-concept use.

## Completed Validation Points

### Functional baseline
- Workload
- Records
- Rules
- Result
- Evidence produced

### First scale validation
- customer_record + CSV
- 1000 records
- 500 rules
- Result
- Performance observations

## Boundary Discovery

### 5000-rule experiment
Document:
- Attempted configuration
- Failure
- Root cause
- Why the validation guardrail correctly failed
- Required remediation

## Current Product Readiness

Separate:
- Customer-ready capabilities
- Engineering validation capabilities
- Remaining work before POC

---
## 5000 Rule / 10000 Record Qualification - Clean Record Collision

Scope:
Rule uniqueness and clean-record collision avoidance only. This section does
not assert transformation correctness; see the scale qualification below.

Status:
Passed

Initial failure:
Clean-record collision caused by overlapping synthetic data domains.

Resolution:
- Unique policy literal generation.
- Deterministic collision avoidance in realistic customer data generation.
- Preserved clean-record collision invariant.

Qualification:
- 5000 unique rules.
- 10000 deterministic records.
- Zero clean collisions.

---
## Execution Model Boundary

### Sequential Validation Driver

Status:
Known limitation / planned evolution

Observed:
- 1,000 records / 500 rules sustained ~24 req/sec
- 10,000 records / 5,000 rules sustained ~24 req/sec

Conclusion:
The current validation driver scales in workload size but does not model a production streaming data path.

Current behavior:
- Sequential request execution
- One request in flight
- Harness throughput includes client-side overhead

Impact:
Reported throughput represents validation harness capacity, not Nol8 data-plane capacity.

Future evolution:
Introduce streaming execution mode:
- concurrent workers
- producer/consumer model
- configurable concurrency
- records/sec and bytes/sec measurement
- latency distribution under load

---
## 10,000 Record / 5,000 Rule Scale Qualification

Status:
Execution passed. Content validation FAILED.

Configuration:
- Workload: customer_record + CSV
- Records: 10,000
- Rules: 5,000

Execution results:
- Records processed: 10,000
- Requests succeeded: 10,000
- Requests failed: 0

Content validation results:
- Records evaluated: 10,000
- Records passed: 9,728
- Records failed: 272
- Pass rate: 97.280%
- Failure classification: CONTENT_MISMATCH

The 272 failures are caused by a confirmed Themis runtime defect: policies
containing overlapping literals, where one rule's literal is a strict prefix of
another's, cause the runtime to compute the wrong match start offset and
destroy content preceding the match. The corruption is silent; every request
returned HTTP 200.

The qualification catalog contained 31 such prefix literals. Removing only
those rules eliminates the corruption entirely.

See ISSUE-003 for the root cause, evidence, and handover.

Execution:
- Total duration: 416.045 seconds
- Sustained harness throughput: ~24 req/sec

Observed service latency:
- Average: 12.576 ms
- p50: 12.498 ms
- p95: 14.207 ms
- p99: 16.462 ms

Conclusion:
The validation driver executes large workloads reliably and correctly detected
a runtime data-correctness defect at scale. Harness throughput is limited by
the sequential execution model rather than workload size, policy size, or
execution stability.

This qualification does NOT establish transformation correctness at scale, and
must not be presented as customer-facing evidence of correct redaction until
ISSUE-003 is resolved.

Future evolution:
Introduce streaming/concurrent validation execution to measure sustained data-path throughput.

----
## Replacement Interaction Boundary

Status:
Not established. Blocked by ISSUE-003.

Two runtime behaviors currently affect replacement output. Both are
length-accounting errors in the Themis replacement writer and they are
independent of each other.

### Replacement value truncation (KB-001)

Replacement strings longer than 15 characters are truncated at runtime.

Bounded and predictable. Policy authors can design around it by keeping
replacement strings at or below 15 characters. The validation framework can
normalize for it using `--replacement-max-length 15`.

### Overlapping match corruption (ISSUE-003)

When two rules match overlapping regions of the input, the runtime computes the
wrong match start offset and destroys content preceding the match.

Root cause confirmed. Reproducible with two rules and one record.

- It is silent. Every affected request returned HTTP 200.
- Data loss is unbounded and not limited to delimiters. An overlap of three
  characters destroyed two characters of input that neither rule matched.
- It is not prevented by the KB-001 15-character guidance, and is unrelated to
  replacement truncation.
- Either rule alone renders correctly. Only their coexistence triggers it, and
  rule order does not matter.
- Adjacent, non-overlapping matches are correct.

Authoring constraint until resolved:

```
No two literals in a policy may produce overlapping matches.

Statically: neither literal may contain the other, and no non-empty proper
suffix of one may equal a proper prefix of the other.
```

This is a genuine and awkward restriction, not a synthetic-data artifact. A
customer redacting both "Acme Corp" and "Acme Corporation" hits the containment
case. A customer redacting "ACCT-1234" and "1234-5678" hits the suffix/prefix
case without either literal containing the other.

### Implication for validation

Transformation correctness cannot be asserted for any catalog containing
overlapping literals.

The scale workload generator currently produces them by construction - bare
`"First Last"` for indices <= 400 and `"First Last {index}"` above - so the
5,000-rule qualification catalog contained 31 prefix literals.

Execution stability, latency, policy capacity, and catalog scale are
independently established and remain valid. Catalog size is not itself a
boundary: it correlated with failures only because a larger generated catalog
is more likely to contain an overlapping pair.