# Themis Product Limitations

Date: 2026-07-19  
Audience: Product, engineering, and anyone scoping a customer deployment  
Source: Findings surfaced by the Nol8 Validation Framework

These are characteristics of the Themis product, not defects in the validation
framework. They were found while building a repeatable validation capability,
and they affect what can be sold and supported rather than only what can be
tested.

Framework issues are tracked separately in `docs/issues/`.

---

## Summary

| # | Limitation | Severity | Customer impact |
|---|---|---|---|
| 1 | A deployed policy has no identity | High | Cannot answer "what is enforcing right now?" |
| 2 | Deployment replaces the entire ruleset | High | No multi-tenant, staged rollout, or partial update |
| 3 | Deployment is fire and forget | Medium | Traffic may be evaluated against the previous policy |
| 4 | Overlapping matches corrupt output | High | Silent data destruction (ISSUE-003) |
| 5 | Replacements truncate at 15 characters | Medium | Constrains redaction token design (KB-001) |

Items 1 to 3 concern the policy lifecycle and share one root cause: **a policy
is not a first-class object.** It has no identity, no version, and no
addressable existence after it is posted.

---

## 1. A deployed policy has no identity

### Observed

The policy endpoint accepts a policy body and returns:

```json
{
  "ok": true,
  "command_id": "cmd-453",
  "stage": "apollo",
  "message": "loaded 5000 rule(s) into native apollo via reload_rules (persisted, REPLACE)",
  "rules": 5000
}
```

There is no endpoint to ask what policy is currently loaded. `command_id`
identifies the dispatch, not the policy, and nothing can be looked up with it
afterwards. There is no policy identifier, no version, no content hash, no
deployed-at timestamp, and no way to retrieve the policy body.

### Why it matters

An operator cannot answer basic questions:

- What policy is enforcing right now?
- When did it change, and to what?
- Is the policy in this environment the same as the one in that one?
- What was in effect while this data passed through?

The last question is the serious one. During an incident - a leak, an audit, a
customer dispute - the first thing anyone asks is what rules were active. Today
that is unanswerable from the product. It can only be inferred from whatever
records the operator kept outside it.

Backup and recovery are also impossible from the product alone. A policy that
cannot be read back cannot be exported, diffed, or restored. If the only copy
of the source file is lost, the deployed ruleset cannot be recovered even
though it is actively enforcing.

### What is needed

In rough order of value:

1. A stable policy identifier returned on deployment **and** queryable
   afterwards.
2. A read endpoint returning at least a summary: identifier, rule count,
   content hash, deployed-at, and deploying principal.
3. Full policy retrieval, so a deployed policy can be exported and restored.
4. Deployment history, so "what changed and when" is answerable.

Item 2 alone would resolve most of the operational pain.

### Framework mitigation, and its limits

`validate policy --status` records every deployment made through the CLI -
timestamp, target, source, rule count, and SHA-256 - and reports them.

This is a substitute, not a solution. It only knows about deployments made from
that checkout. A deployment from another machine, another tool, or by hand is
invisible to it. The output says so explicitly, because a record that looks
authoritative but is not would be worse than having none.

---

## 2. Deployment replaces the entire ruleset

### Observed

Posting a policy replaces everything. The response says so plainly:
`(persisted, REPLACE)`. There is no namespace, no partial update, no rollback,
and no dry run.

### Why it matters

- **Multi-tenancy is unsafe.** The endpoint is global per credential. Two teams
  sharing credentials silently overwrite each other with no error and no way to
  detect it afterwards, because of limitation 1.
- **Every change is a full redeploy.** Adding one rule means re-uploading the
  entire ruleset. That is also precisely the operation most likely to introduce
  an overlapping literal pair and therefore trigger ISSUE-003.
- **No rollback.** A bad policy is either a DLP outage or, worse, silent
  under-redaction until someone notices.
- **No dry run.** A syntactically valid but semantically wrong policy goes
  straight into enforcement.

### What is needed

Namespaced or versioned policies, partial update, an explicit activation step
separate from upload, and rollback to a previous version.

---

## 3. Deployment is fire and forget

### Observed

The deploy call returns as soon as the service accepts it. The response fields
`command_id` and `stage: apollo` suggest an asynchronous distribution pipeline,
but nothing reports convergence and nothing can be polled.

### Why it matters

Records sent immediately after deployment may be evaluated against the previous
policy. If the previous policy was more permissive, data passes unredacted. If
it was similar, the results look correct but were produced by the wrong rules -
the more dangerous case, because nothing indicates it.

For validation this means a run started immediately after deployment can
produce evidence that does not correspond to the policy it claims to test.

### What is needed

A readiness or convergence signal: either a synchronous deploy that returns
once active, or a status endpoint that can be polled against `command_id`.

---

## 4. Overlapping matches corrupt output

Full detail in
`docs/issues/20260719-ISSUE-003-scale-validation-transformation-mismatch.md`.

When two rules match overlapping regions of the input, the runtime computes the
wrong match start offset and destroys content preceding the match. Silent -
HTTP 200 every time.

```
rules   "ABCD" -> "[P]"  and  "DEFG" -> "[Q]"
input    x ABCDEFG y
correct  x [P]EFG y
actual   x [P[Q] y
```

Customer impact: this is ordinary policy authoring, not an exotic edge case.
Redacting both `"Acme Corp"` and `"Acme Corporation"` triggers it. So does
`"ACCT-1234"` alongside `"1234-5678"`, where neither literal contains the other.

Until it is fixed, customers must be told: no two literals in a policy may
produce overlapping matches. That constraint is awkward to satisfy and
impossible to verify without tooling.

Reproduce with `scripts/repro-issue-003-curl.sh`, which uses plain curl and
needs no part of this repository.

---

## 5. Replacements truncate at 15 characters

Full detail in `docs/issues/KNOWN_BEHAVIORS.md` (KB-001).

Replacement strings longer than 15 characters are truncated at runtime.
`[FINANCIAL:CREDIT_CARD_NUMBER]` is emitted as `[FINANCIAL:CRED`.

Customer impact: redaction tokens must be designed within a 15-character
budget, and tokens sharing a 15-character prefix become indistinguishable in
output - so a reader cannot tell which rule fired. That is a real constraint on
token vocabulary, and it silently degrades the auditability of redacted
documents.

Whether the limit is configurable has not been established.

---

## Note on how these were found

All five were surfaced by building a validation capability against a live
Themis instance, and all are reproducible outside this repository. Items 4 and
5 are reproducible with curl alone.

Items 1 to 3 were not found by testing Themis. They were found by trying to
operate it safely and repeatedly - which is what a customer will do.
