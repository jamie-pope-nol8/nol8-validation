# Known Behaviors

Scope

This file documents accepted runtime behavior boundaries that policy authors
and validation operators must design around.

It does NOT document defects. A behavior belongs here only when it is
understood, bounded, and safe to work within. Confirmed defects are tracked as
issues in this directory.

Current defects affecting validation:

- ISSUE-004 - Overlapping matches corrupt Themis output. When two rules match
  overlapping regions of the input, the runtime computes the wrong match start
  offset and destroys content preceding the match. Silent; no error signal.
  Not prevented by KB-001's 15-character guidance.

  Authoring constraint until resolved: no two literals in a policy may produce
  overlapping matches. Statically, that means neither literal may contain the
  other, and no non-empty proper suffix of one may equal a proper prefix of the
  other. Adjacent, non-overlapping matches are safe.

---

### KB-001 - Replacement strings truncated to 15 characters

Status: Confirmed runtime limitation  
Disposition: Documented Themis behavior boundary  
Owner: Engineering  
Discovered: 2026-07-16  
Discovered by: Functional validation suite  

Description

Themis runtime truncates replacement strings longer than 15 characters during transformation processing.

The validation framework generates complete replacement values correctly and policy deployment succeeds. The truncation occurs during runtime transformation execution.

Example:

Configured replacement:

```
[FINANCIAL:CREDIT_CARD_NUMBER]
```

Observed runtime output:

```
[FINANCIAL:CRED
```

Impact

Policy authors must currently keep replacement strings ≤15 characters when targeting Themis runtime behavior.

Longer replacement strings result in functional validation failures classified as:

```
CONTENT_MISMATCH
```

Resolution

The validation framework supports comparison normalization using:

```
--replacement-max-length 15
```

Further engineering work is required to determine whether the runtime limitation is configurable or can be removed.

IMPORTANT - normalization is not a general workaround

Keeping replacement strings ≤15 characters does NOT guarantee correct Themis
output. A separate and unrelated defect (ISSUE-004) corrupts output when a
policy contains overlapping literals, at any replacement length.

In run `20260719T161514709224Z`, 272 records failed with normalization applied
at 15 characters. This behavior boundary covers replacement truncation only.

Regression Test

The functional validation suite should verify:

- Replacement strings ≤15 characters pass validation.
- Replacement strings >15 characters are identified as runtime limitations.
- Validation reports clearly identify replacement length limitations.

Related Investigation:

- 20260719-ISSUE-004-scale-validation-transformation-mismatch.md