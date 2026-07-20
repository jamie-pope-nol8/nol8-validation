# Outbound Slack comms — Themis engineering

Drafts to accompany the issue handoff. Engineering-facing; no repo references.
Adjust names/greeting before sending.

---

## Comm 1 — issue handoff (attach the zip of `docs/issues/` + README)

> **Themis findings from our validation work — one defect, plus a set of product observations**
>
> While building validation tooling against the eval environment we turned up a
> handful of things worth your eyes. I've zipped them up — each file is
> self-contained (reproductions are inline curl against our own endpoints,
> nothing to install), and `README.md` is the index.
>
> **Please look at ISSUE-004 first — it's a data-correctness defect, not
> feedback.** When two rules in a policy match overlapping text, the runtime
> writes the replacement at the wrong offset and silently destroys the input
> next to it. HTTP 200 every time, no error. It's triggered by ordinary policy
> authoring — redacting both "Acme Corp" and "Acme Corporation" is enough — and
> it reproduces with two rules and one record.
>
> The rest (ISSUE-001–003, 005–007) are product-lifecycle and environment
> observations: a deployed policy has no identity or version, deploys replace the
> whole ruleset and are fire-and-forget, replacements truncate at 15 characters,
> the eval environment isn't reachable from outside the VPC, and there's no
> health/readiness signal. Lower urgency than 004, but they shape what we can
> demo and sell.
>
> Happy to walk through any of them or run the repros live.

---

## Comm 2 — the data-path / integration-mode question (send on its own)

> **Question on the intended data-path / integration mode**
>
> Quick one on how `/v1/process` is meant to be used in production. Today we POST
> a payload and the *transformed* payload comes back to us — so the caller ends
> up handling the content on both sides of the redaction, which seems backwards
> for a data-protection service.
>
> But the response carries `jid`, `frameId`, and `last: true`, which look like a
> framed or streaming protocol rather than simple request/response. That makes us
> think there's probably an inline / proxy / streaming mode we're just not using.
>
> Is there one? And what's the intended integration pattern for a real
> deployment — does Themis sit in the data path and forward redacted content on
> itself, rather than returning it to the caller? Entirely possible we're just
> pointed at the wrong endpoint.

---

*Note: ISSUE-004 is deliberately elevated inside Comm 1 and labelled a defect so
it is triaged as the priority rather than as product feedback, even though it
ships in the same bundle as the lifecycle observations. Comm 2 stays separate —
it is a question about intended usage, not a finding.*
