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

Two rules and one record, straight curl against your own tenant. Nothing to
install.

> Loading a policy replaces the active policy, so use a tenant where that is
> acceptable.

```bash
POLICY_ENDPOINT="https://<control-plane-host>:8444/policy"
PROCESS_ENDPOINT="https://<tenant-host>/v1/process"
TOKEN="<bearer-token>"
```

**Step 1 — load a policy with two rules whose matches overlap:**

```bash
printf '"ABCD" -> "[P]";\n"DEFG" -> "[Q]";\n' | curl -sS \
  -X POST "$POLICY_ENDPOINT" \
  -H "Authorization: Bearer $TOKEN" \
  --data-binary @-
```

**Step 2 — send one record containing `ABCDEFG`:**

```bash
curl -sS -X POST "$PROCESS_ENDPOINT" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message":"x ABCDEFG y"}'
```

Correct output is `x [P]EFG y`. Observed output is `x [P[Q] y`.

**Step 3 — the control.** Load either rule on its own and repeat step 2:

```bash
printf '"ABCD" -> "[P]";\n' | curl -sS \
  -X POST "$POLICY_ENDPOINT" \
  -H "Authorization: Bearer $TOKEN" \
  --data-binary @-
```

That returns `x [P]EFG y` correctly, isolating the fault to the combination
rather than to either rule.

**A larger overlap destroys more.** With `"ABCDEF" -> "[P]"` and
`"DEFGHI" -> "[Q]"` against `x ABCDEFGHI y`, the output is `x [Q] y` — the `AB`
is gone.

> If the control-plane endpoint presents a self-signed certificate you may need
> `-k`. We mention it only because we hit it; it is not part of the defect.

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
