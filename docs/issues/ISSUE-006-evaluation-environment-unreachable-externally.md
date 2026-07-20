# ISSUE-006 — The evaluation environment cannot be reached by the integrations we most need to demonstrate

**Component:** Evaluation environment (network posture)
**Type:** Environment configuration — not a defect
**Severity:** High (to evaluation and sales)
**Status:** Open

## Summary

The evaluation environment is reachable only from inside the VPC — VPN plus, in
practice, an SSH session to a host on the network. The processing and policy
endpoints are not reachable from outside. That is a reasonable posture for
production, but it blocks the one category of integration most likely to close a
sale: an external agent or service calling the API directly.

## Observed

Access to the processing and policy endpoints requires a VPN connection and an
SSH session to a host inside the network. Neither endpoint is reachable from the
public internet.

## Why it matters

An agent — or any external service, customer sandbox, CI pipeline, or partner
integration — cannot establish a VPN connection or drive an SSH session. It needs
a reachable HTTPS endpoint and a credential. Without one, agent-mediated
integrations cannot be demonstrated at all, and that is the fastest-growing
category of buyer interest for a data-protection product sitting in front of
models.

The practical cost: **the product cannot be demonstrated to the audience most
likely to buy it**, because the demonstration itself cannot reach the service.

It also invites a question a prospect will ask directly: if evaluating the
product requires network-level access to the vendor's VPC, what does integrating
it require? The access model shapes the perceived integration cost whether or
not that perception is accurate.

## What would resolve it

A reachable evaluation endpoint — not an open one:

- public HTTPS endpoint for the processing and policy APIs
- scoped, revocable tokens per evaluator or per demonstration
- rate limiting and request-size caps
- synthetic data only, stated as a condition of use
- separate from any environment holding customer data

That is a normal shape for a vendor evaluation environment and gives up little.

## Note

This is not an argument for weakening production security. It is that an
evaluation environment has a different job from a production one, and is
currently configured for the latter.
