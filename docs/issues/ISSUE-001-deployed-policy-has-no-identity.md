# ISSUE-001 — A deployed policy has no identity

**Component:** Themis policy control plane
**Type:** Product limitation (policy lifecycle)
**Severity:** High
**Status:** Open

## Summary

Once a policy is deployed there is no way to ask the product what policy is
currently enforcing. The deploy response identifies the dispatch, not the
policy, and nothing can be looked up afterwards — no identifier, no version, no
content hash, no deployed-at time, and no way to read the policy body back.

## Observed

Posting a policy returns:

```json
{
  "ok": true,
  "command_id": "cmd-453",
  "stage": "apollo",
  "message": "loaded 5000 rule(s) into native apollo via reload_rules (persisted, REPLACE)",
  "rules": 5000
}
```

`command_id` identifies the dispatch, not the policy, and nothing can be
retrieved with it afterwards. There is no endpoint to ask what is currently
loaded, and no way to retrieve the deployed policy body.

## Why it matters

An operator cannot answer basic questions:

- What policy is enforcing right now?
- When did it change, and to what?
- Is the policy in this environment the same as the one in that one?
- What rules were in effect while this data passed through?

The last is the serious one. During an incident — a leak, an audit, a customer
dispute — the first question is what rules were active. Today that is
unanswerable from the product; it can only be inferred from records kept outside
it.

Backup and recovery are also impossible from the product alone. A policy that
cannot be read back cannot be exported, diffed, or restored. If the only copy of
the source is lost, the deployed ruleset is unrecoverable even though it is
actively enforcing.

## What would resolve it

In rough order of value:

1. A stable policy identifier returned on deployment **and** queryable
   afterwards.
2. A read endpoint returning at least a summary: identifier, rule count, content
   hash, deployed-at, and deploying principal.
3. Full policy retrieval, so a deployed policy can be exported and restored.
4. Deployment history, so "what changed and when" is answerable.

Item 2 alone would resolve most of the operational pain.

## Related

This is one facet of a broader gap — the runtime cannot be asked about its own
state — shared with ISSUE-002, ISSUE-003, and ISSUE-007.
