# ISSUE-004 — Silent output corruption when two rules match overlapping text

**Component:** Themis runtime (processing / `/v1/process`)
**Type:** Defect — data correctness
**Severity:** High
**Status:** Open

## Summary

When two rules in a policy match overlapping regions of the same input, the
runtime writes the replacement at the wrong start offset and destroys the
characters preceding it. Every affected request returns HTTP 200 with no error;
nothing indicates the output was corrupted. It destroys legitimate input that
neither rule matched, and it is reachable through ordinary policy authoring.

## What happens

```
rules:   "ABCD" -> "[P]"   and   "DEFG" -> "[Q]"
input:   x ABCDEFG y
correct: x [P]EFG y
actual:  x [P[Q] y
```

The two matches share the `D`. The runtime computes the wrong start offset for
the second replacement and overwrites content ahead of it. With this
three-character overlap, two characters of legitimate input that neither rule
matched were destroyed.

## Why it is serious

1. **It is silent.** Every affected request returns HTTP 200 with no error field
   and no signal. A caller has no way to detect it.
2. **It destroys data rather than mis-redacting it.** In one observed case
   `name: ` came back as `na`. The amount destroyed varies with the configured
   replacement lengths, and **shorter replacements destroy more** surrounding
   content, not less.
3. **Ordinary policy authoring triggers it.** A customer redacting both
   `"Acme Corp"` and `"Acme Corporation"` hits it. So does one redacting
   `"ACCT-1234"` alongside `"1234-5678"`, where neither literal contains the
   other.

Until it is fixed, the only safe guidance to a customer is "no two literals in
your policy may produce overlapping matches" — a constraint that is awkward to
satisfy and impossible to verify by eye.

## What we established

- Either rule alone produces correct output. Only their coexistence triggers it.
- Rule order in the policy makes no difference.
- Adjacent matches that do not share bytes are handled correctly, as are
  fully disjoint matches. Only shared bytes corrupt.
- Containment is not required: `"ABCD"` with `"DEFG"` corrupts, and neither
  contains the other.
- Replacement length is not the cause, and this is unrelated to the known
  15-character replacement truncation.
- Replacement output is not re-scanned; matching is single pass.
- The match **end** offset is correct in every case observed. Only the **start**
  is displaced — which may help narrow where to look.

## Reproduction

Two rules and one record, straight curl. Nothing to install. The commands below
were run end to end against the evaluation tenant; the responses shown are the
actual output.

```bash
POLICY_ENDPOINT="https://<control-plane-host>:8444/policy"   # self-signed cert
PROCESS_ENDPOINT="https://<tenant-host>/v1/process"          # valid cert
TOKEN="<bearer-token>"
```

> **TLS:** the policy control plane presents a **self-signed certificate** whose
> subject is an internal address, so the policy calls use `--insecure`. The
> processing endpoint has a valid certificate and does not need it. Adjust to
> your own environment if the control plane verifies normally there.
>
> **Note:** loading a policy replaces the entire active ruleset, so use a tenant
> where that is acceptable.

**Step 1 — load a policy with two rules whose matches overlap:**

```bash
printf '"ABCD" -> "[P]";\n"DEFG" -> "[Q]";\n' | curl -sS --insecure \
  -X POST "$POLICY_ENDPOINT" \
  -H "Authorization: Bearer $TOKEN" \
  --data-binary @-
```

Response confirms the load:

```json
{"ok": true, "command_id": "cmd-480", "stage": "apollo",
 "message": "loaded 2 rule(s) into native apollo via reload_rules (persisted, REPLACE)",
 "rules": 2}
```

**Step 2 — send one record containing `ABCDEFG`:**

```bash
curl -sS -X POST "$PROCESS_ENDPOINT" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message":"x ABCDEFG y"}'
```

Correct output would be `x [P]EFG y`. **Observed:**

```json
{"jid":1978103430208103584,"frameId":1,"last":true,"result":{"message":"x [P[Q] y"}}
```

The corrupted value is in `result.message`: `x [P[Q] y`.

**Step 3 — the control.** Load either rule on its own and repeat step 2:

```bash
printf '"ABCD" -> "[P]";\n' | curl -sS --insecure \
  -X POST "$POLICY_ENDPOINT" \
  -H "Authorization: Bearer $TOKEN" \
  --data-binary @-
```

With only that rule loaded, step 2 returns `"result":{"message":"x [P]EFG y"}` —
correct — isolating the fault to the combination rather than to either rule.

**A larger overlap destroys more.** With `"ABCDEF" -> "[P]"` and
`"DEFGHI" -> "[Q]"` loaded, processing `x ABCDEFGHI y` returns
`"result":{"message":"x [Q] y"}` — the `AB` is gone.

## Scale of impact

While exercising the evaluation environment with generated workloads, a
10,000-record run against a 5,000-rule policy returned 272 corrupted records at
a 100% HTTP success rate — nothing in any response indicated a problem. Removing
the overlapping rule pairs and re-running produced 10,000 correct results and
zero mismatches, so overlapping matches accounted for every failure observed.
Everything above reproduces with two rules and one record; the volume run is
only how it was found.

## What would resolve it

Correct the start-offset computation so that overlapping matches either resolve
deterministically (e.g. first/longest match wins, remainder re-based) or are
rejected at policy-load time with a clear error, rather than silently corrupting
output at runtime.
