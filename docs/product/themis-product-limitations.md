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
| 6 | Evaluation environment is unreachable externally | High | Agent integrations cannot be demonstrated |
| 7 | No way to check whether the runtime is healthy | Medium | Work is started against a dead backend |

Items 1 to 3 concern the policy lifecycle and share one root cause: **a policy
is not a first-class object.** It has no identity, no version, and no
addressable existence after it is posted.

Items 1 to 3 and 7 are all facets of the same gap: **the runtime cannot be
asked about its own state.** Not what policy is loaded, not whether the policy
has converged, not whether the engine is running.

Item 6 is not a defect but an environment configuration choice. It is included
because it currently prevents demonstrating the product to the audience most
likely to buy it.

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

Reproduces with curl alone against any tenant - two rules and one record, no
tooling required. Commands are in the ISSUE-003 write-up.

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

## 6. The evaluation environment cannot be reached by the integrations we most need to demonstrate

### Observed

The evaluation environment is reachable only from inside the VPC. Access
requires a VPN connection and, in practice, an SSH session to a host inside the
network. The processing and policy endpoints are not reachable from outside.

### Why it matters

This is an appropriate posture for production. It is a poor fit for an
environment whose purpose is evaluation and demonstration, and it rules out a
category of integration entirely.

An agent - or any external service, customer sandbox, CI pipeline, or partner
integration - cannot establish a VPN connection or drive an SSH session. It
needs a reachable HTTPS endpoint and a credential. Without one, agent-mediated
integrations cannot be demonstrated at all, and that is the fastest-growing
category of buyer interest for a data-protection product sitting in front of
models.

The practical cost is straightforward: **we cannot demonstrate the product to
the audience most likely to buy it**, because the demonstration itself cannot
reach the service.

It also raises a question a prospect will ask directly. If evaluating the
product requires network-level access to the vendor's VPC, what does
integrating it require? The access model shapes the perceived integration cost
whether or not that perception is accurate.

### What is needed

A reachable evaluation endpoint. Not an open one:

- public HTTPS endpoint for the processing and policy APIs
- scoped, revocable tokens per evaluator or per demonstration
- rate limiting and request size caps
- synthetic data only, with that stated as a condition of use
- separate from any environment holding customer data

That is a normal shape for a vendor evaluation environment and gives up little.
The current model gives up the ability to demonstrate the product's most
strategically relevant use case.

### Note

This is not an argument for weakening production security. It is an argument
that an evaluation environment has a different job from a production one, and
is currently configured for the latter.

---

## 7. There is no way to check whether the runtime is healthy

### Observed

On 2026-07-20 the processing endpoint began returning HTTP 503 to every
request:

```json
{"error": {"code": "ARGUS_UPSTREAM_UNAVAILABLE",
 "message": "stream submit: ARGUS_UPSTREAM_UNAVAILABLE: backend send failed:
  dispatcher: iris send: ARGUS_UPSTREAM_TIMEOUT: iris quic: upstream error:
  RESPONSE_WAIT: request timed out (no apollo response in >2s)"}}
```

The edge accepted the request, authenticated it, and routed it. The rules
engine behind it - `apollo`, the same component named in the policy-load
response - did not answer within the 2-second budget. The control plane
remained responsive throughout, answering in under 10 ms.

So the product was partly alive: reachable, authenticating, routing, and
unable to do the one thing it exists to do.

### Why it matters

There is no health, readiness, or status endpoint. The only way to discover
that the engine is down is to send real traffic and have it fail. That has
three consequences:

- **Work is started against a dead backend.** A long validation run begins
  normally and produces nothing but execution failures. Nothing can be checked
  beforehand.
- **Outage duration is unknowable.** With no health signal and no timestamped
  status, there is no way to establish when the engine stopped responding or
  whether it has recovered, other than by probing it.
- **An operator cannot distinguish causes.** A 503 could be the engine, the
  transport, the tenant, or the credential. Only the error string separates
  them, and only because it happens to name its internal components. That is
  incidental detail, not a contract, and it should not be what operators rely
  on.

The diagnosis above was possible only because the error message exposed the
internal call chain. A less chatty error - or a future release that redacts it,
which would be a reasonable thing to do - would leave an operator with an
unexplained 503 and nothing to act on.

### What is needed

A health endpoint reporting engine reachability and policy-load state,
unauthenticated or cheaply authenticated, so it can be polled before starting
work and used by any monitoring the customer already runs. A distinguishable
error taxonomy for "engine unavailable" versus "request rejected" would close
most of the remainder.

### Framework handling

The framework treats a 503 with no processed message as `EXECUTION_FAILURE`,
not as a pass, so an outage produces honest evidence of an outage rather than a
green report. It does not yet pre-flight the endpoint before a run; that is
worth adding, and is the only mitigation available without a health endpoint.

---

## Observations to confirm - not limitations

### Control plane TLS is self-signed, the data plane is not

The policy endpoint presents a self-signed certificate named after an internal
address:

```
subject = CN=ip-172-31-40-100
issuer  = CN=ip-172-31-40-100
```

so verification fails against `themis.sales.nol8.cloud` and clients must pass
`--insecure`. The processing endpoint presents a valid Amazon-issued
certificate for `*.nol8.net` and verifies normally.

**This is not a finding.** The environment is a sandbox provisioned for one
team, reachable only from inside the VPC over VPN. A certificate proves server
identity; an attacker able to exploit its absence is already inside that
network, at which point the certificate is not the problem. Self-signed is a
reasonable choice here and no customer traffic passes through it.

The only thing worth asking is why the two endpoints differ. A deliberate
"sandbox, self-sign everything" decision would have applied to both. That it
applies to one suggests the control plane and data plane were provisioned
through different paths, which may or may not carry into production.

Worth one question - does the production control plane present a
publicly-verifiable certificate? - rather than tracking as a limitation.

### Framework handling

`scripts/load-policy.sh` verifies TLS by default and requires
`THEMIS_ALLOW_INSECURE_TLS=1`, set in `config/demo.env` with a comment. Kept not
because the sandbox needs it, but so the exception is visible and does not
silently propagate into an environment where it would matter.

---

## Note on how these were found

All seven were surfaced by building a validation capability against a live
Themis instance. Items 1 to 5 and 7 are reproducible outside this repository,
and items 4, 5, and 7 with curl alone.

Items 1 to 3, 6, and 7 were not found by testing Themis. They were found by
trying to operate and demonstrate it repeatedly - which is what a customer and
a sales engineer will do.
