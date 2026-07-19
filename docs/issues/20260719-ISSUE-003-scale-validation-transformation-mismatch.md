# Issue #003 - Scale Validation Transformation Mismatch

Date: 2026-07-19  
Status: Investigating  
Category: Validation / Engine Behavior  
Owner: Engineering  
Discovered by: Scale Validation Qualification  

## Summary

The 10,000 record / 5,000 rule validation qualification completed successfully from an execution perspective, but 272 records failed content validation due to differences between expected transformations and actual Themis output.

The framework generated deterministic expected results, Themis processed all requests successfully, but the returned transformations did not match the expected replacement behavior.

A known Themis runtime limitation has been confirmed as a contributing factor:

- Replacement strings longer than 15 characters are truncated during runtime transformation processing.
- This behavior is documented in KNOWN_BEHAVIORS.md as KB-001.

Further investigation is required to determine whether any additional scale-specific transformation issues remain after accounting for the known replacement length limitation.

---

## Context

This issue was discovered during the first large-scale validation qualification intended to determine whether the validation framework could support realistic customer proof-of-concept workloads.

Qualification parameters:

- Rules requested: 5,000
- Records requested: 10,000
- Target: Themis
- Run ID: 20260719T161514709224Z

---

## Observed Behavior

Functional execution completed successfully.

Results:

- Records processed: 10,000
- Requests succeeded: 10,000
- Requests failed: 0

Latency:

- Average latency: 12.576 ms
- p50: 12.498 ms
- p95: 14.207 ms
- p99: 16.462 ms

Validation results:

- Records evaluated: 10,000
- Records passed: 9,728
- Records failed: 272
- Pass rate: 97.280%

Failure classification:

- CONTENT_MISMATCH: 272
- EXECUTION_FAILURE: 0

---

## Expected Behavior

For every dirty record, Themis should replace each detected policy literal with the configured replacement token.

Example:

Input:

```
Elena Chen 2527
```

Expected:

```
[PII:PERSON_NAME]
```

---

## Actual Behavior

Observed output contains malformed replacement results including:

Truncated replacement tokens:

```
[PII:PERSON_NAM
[PII:EMAIL_ADDR
[PII:STREET_ADD
```

Nested replacements:

```
[PII:[PII:PERSON_NAM
```

The framework-generated expected output does not contain these patterns.

---

## Evidence Collected

Confirmed:

- Rule catalog generation produced 5,000 unique detection literals.
- Policy generation completed successfully.
- Generated policy artifacts contain complete replacement strings.
- Themis accepted and loaded all 5,000 rules.
- Execution returned HTTP 200 for all 10,000 records.
- Framework expected transformations are deterministic.

A minimal reproduction confirmed the known replacement length limitation:

Run:

```
20260719T174421134465Z
```

Configuration:

```
Rules: 1
Records: 1
```

Generated policy:

```
"4111-1111-0001-0007" -> "[FINANCIAL:CREDIT_CARD_NUMBER]";
```

Themis returned a truncated replacement.

Comparison behavior:

```
--replacement-max-length 15
```

passes validation.

```
--replacement-max-length 16
```

fails validation.

Related behavior:

```
KB-001 - Replacement strings truncated to 15 characters
```

---

## Root Cause Analysis

### Confirmed

Themis runtime truncates replacement literals longer than 15 characters.

This behavior occurs after policy generation and during runtime transformation processing.

No framework-side policy generation or serialization issue has been identified.

---

### Confirmed - Source Cursor Misalignment (2026-07-19)

The 272 failures are NOT explained by KB-001.

Re-running comparison with `--replacement-max-length 15` against the existing
run output produced an identical result: 272 CONTENT_MISMATCH. The manifest
confirms normalization was applied (`replacement_max_length: 15`). The failures
survive replacement-length normalization entirely.

All 272 failing records are `dirty` and all involve `[PII:PERSON_NAM`.

Observed corruption is a positional shift of the replacement token, not a
malformed replacement value. Two directions occur:

Characters left behind before the token (positive delta):

```
expected: CUST-516774,[PII:PERSON_NAM
actual:   CUST-516774,[PII:[PII:PERSON_NAM
```

Characters consumed before the token (negative delta):

```
expected: CUST-647637,[PII:PERSON_NAM
actual:   CUST-647637[PII:PERSON_NAM
```

The earlier reading of the nested case as "replacement rescanning" was
incorrect. Rescanning would produce a well-formed nested token. The observed
fragments are variable-length partial prefixes, and the negative cases consume
unrelated preceding characters (commas, spaces). Both are consistent with the
replacement being written at a misaligned source offset.

#### Empirical law

Let `L` = length of the matched `person_name` literal and
`delta` = `len(actual) - len(expected)`:

```
delta = 20 - L
```

| L    | 15  | 16  | 17  | 18  | 19  | 20 | 21  |
|------|-----|-----|-----|-----|-----|----|-----|
| delta| +5  | +4  | +3  | +2  | +1  | 0  | -1  |
| count| 38  | 53  | 59  | 45  | 35  | -  | 8   |

Equivalently, the runtime consumes `2L - 20` source bytes where it should
consume `L`. The error is zero at `L = 20`; no length-20 literal appears in the
failure set.

This is the signature of a double-advance: the source cursor is advanced by the
matched literal length and then corrected a second time against a fixed 20-byte
reference.

#### Gating factor still unknown

Literal length determines the magnitude of corruption but does not determine
whether it occurs. Passing records span the same length range as failures:

```
L=17 -> 63 failed, 320 passed
L=15 -> 38 failed, 102 passed
L=19 -> 38 failed, 145 passed
```

1453 of 9728 passing records contain a `person_name` match and are unaffected.

Leading hypothesis: a rule-table collision in which the correct literal is
matched but a different catalog entry's length is used to advance the cursor.
This would explain both the fixed 20-byte reference and the partial firing rate.

Evidence: run `20260719T161514709224Z`, artifact `generated/comparison.jsonl`.

---

### Remaining Investigation

- Identify the gating factor that determines whether the misalignment fires.
- Determine whether the 20-byte reference corresponds to a specific catalog
  entry length.
- Determine whether the defect is specific to `person_name` or to any
  multi-token literal.
- Determine whether catalog size (5,000 rules) is required to reproduce.

---

## Impact

This prevents using the current large-scale qualification as customer-facing proof-of-concept evidence until deterministic transformation behavior is confirmed.

The execution path is stable, but transformation correctness must reach 100% before presenting validation results externally.

---

## Recommendation

Continue isolated runtime qualification using minimal deterministic tests.

Validate:

- replacement length handling
- overlapping literal behavior
- replacement rescanning behavior
- rule ordering behavior

After engine behavior is confirmed, update either:

- framework policy generation rules
- validation expectations
- Themis configuration/runtime behavior

---

## Resolution

Pending.

---

## Regression Test

The final validation suite should prove:

- 5,000 rules load successfully.
- 10,000 records process successfully.
- Expected transformations equal actual transformations.
- CONTENT_MISMATCH count is zero after known runtime limitations are accounted for.
- Results remain deterministic across repeated runs.