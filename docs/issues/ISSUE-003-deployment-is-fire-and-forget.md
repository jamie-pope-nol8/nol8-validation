# ISSUE-003 — Deployment is fire-and-forget

**Component:** Themis policy control plane
**Type:** Product limitation (policy lifecycle)
**Severity:** Medium
**Status:** Open

## Summary

The deploy call returns as soon as the service accepts the policy, not once the
policy is active. The response suggests an asynchronous distribution pipeline,
but nothing reports convergence and nothing can be polled. There is no way to
know when the new policy is actually enforcing.

## Observed

The deploy response returns immediately and includes `command_id` and
`stage: apollo`, which imply an asynchronous pipeline behind the call. There is
no readiness signal and no endpoint to poll for convergence against
`command_id`.

## Why it matters

Records sent immediately after a deployment may be evaluated against the
**previous** policy:

- If the previous policy was more permissive, data passes unredacted.
- If it was similar, the results look correct but were produced by the wrong
  rules — the more dangerous case, because nothing indicates it.

There is no window guarantee and no way to confirm the new policy is live before
sending traffic, so an operator cannot know whether a given request was handled
by the policy they intended.

## What would resolve it

A readiness or convergence signal, either of:

- a synchronous deploy that returns once the policy is active, or
- a status endpoint that can be polled against `command_id` until it reports
  converged.

## Related

Shares a root cause with ISSUE-001, ISSUE-002, and ISSUE-007: the runtime cannot
be asked about its own state — here, whether a deployment has taken effect.
