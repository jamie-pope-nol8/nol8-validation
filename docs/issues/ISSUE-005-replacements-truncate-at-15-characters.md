# ISSUE-005 — Replacements truncate at 15 characters

**Component:** Themis runtime (processing / `/v1/process`)
**Type:** Runtime behavior / constraint
**Severity:** Medium
**Status:** Open

## Summary

Replacement strings longer than 15 characters are truncated at runtime.
`[FINANCIAL:CREDIT_CARD_NUMBER]` is emitted as `[FINANCIAL:CRED`. Whether the
limit is configurable has not been established.

## Observed

A rule whose replacement token exceeds 15 characters produces truncated output.
The truncation is silent — HTTP 200, no error.

## Reproduction

Run end to end against the evaluation tenant; the responses shown are the actual
output.

```bash
POLICY_ENDPOINT="https://<control-plane-host>:8444/policy"   # self-signed cert
PROCESS_ENDPOINT="https://<tenant-host>/v1/process"          # valid cert
TOKEN="<bearer-token>"
```

> The policy control plane presents a self-signed certificate, so the policy
> call uses `--insecure`; the processing endpoint has a valid certificate and
> does not. Loading a policy replaces the entire active ruleset.

Load a rule with a replacement longer than 15 characters, then process a record
that matches it:

```bash
printf '"4111111111111111" -> "[FINANCIAL:CREDIT_CARD_NUMBER]";\n' | curl -sS --insecure \
  -X POST "$POLICY_ENDPOINT" -H "Authorization: Bearer $TOKEN" --data-binary @-

curl -sS -X POST "$PROCESS_ENDPOINT" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $TOKEN" \
  -d '{"message":"card 4111111111111111 on file"}'
```

**Observed** — the replacement is truncated to its first 15 characters:

```json
{"jid":114118497663452371,"frameId":1,"last":true,"result":{"message":"card [FINANCIAL:CRED on file"}}
```

`[FINANCIAL:CREDIT_CARD_NUMBER]` (29 chars) is emitted as `[FINANCIAL:CRED`.

## Why it matters

- Redaction tokens must be designed within a 15-character budget.
- Two tokens that share a 15-character prefix become **indistinguishable** in
  output, so a reader cannot tell which rule fired. For example
  `[FINANCIAL:CREDIT_CARD_NUMBER]` and `[FINANCIAL:CREDIT_ROUTING]` both emit
  `[FINANCIAL:CRED`.

That is a real constraint on token vocabulary, and it silently degrades the
auditability of redacted documents: the output no longer records unambiguously
what was redacted or by which rule.

## What would resolve it

- Document the limit and whether it is configurable.
- If it is fixed, either raise it or surface an error at policy-load time when a
  replacement exceeds it, rather than truncating silently at runtime.
- Ideally, guarantee that distinct replacement tokens remain distinct in output.
