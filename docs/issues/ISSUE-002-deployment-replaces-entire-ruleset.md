# ISSUE-002 — Deployment replaces the entire ruleset

**Component:** Themis policy control plane
**Type:** Product limitation (policy lifecycle)
**Severity:** High
**Status:** Open

## Summary

Posting a policy replaces everything currently loaded. There is no namespace, no
partial update, no explicit activation step, no dry run, and no rollback. The
deploy response states it plainly: `(persisted, REPLACE)`.

## Observed

Every deployment is a full replace of the active ruleset. The response message
reads, for example:

```
loaded 5000 rule(s) into native apollo via reload_rules (persisted, REPLACE)
```

## Why it matters

- **Multi-tenancy is unsafe.** The endpoint is global per credential. Two teams
  sharing a credential silently overwrite each other, with no error and — because
  a deployed policy has no identity (ISSUE-001) — no way to detect it afterwards.
- **Every change is a full redeploy.** Adding a single rule means re-uploading
  the entire ruleset. That is also the operation most likely to introduce an
  overlapping literal pair and so trigger the corruption defect (ISSUE-004).
- **No rollback.** A bad policy is either a DLP outage or, worse, silent
  under-redaction until someone notices.
- **No dry run.** A syntactically valid but semantically wrong policy goes
  straight into enforcement.

## What would resolve it

- Namespaced or versioned policies rather than one global active set.
- Partial update, so a change does not require re-uploading everything.
- An explicit activation step separate from upload.
- Rollback to a previous version.

## Related

Part of the policy-lifecycle gap shared with ISSUE-001 and ISSUE-003: a policy
is not a first-class, addressable object.
