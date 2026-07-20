# ISSUE-003 Handover Message

Drafts for sending ISSUE-003 to Themis engineering. Adjust names and links
before sending.

## IMPORTANT - what engineering has and has not seen

Engineering did **not** write this validation framework, did not commission it,
and has never seen it. They handed over the v1.0 sandbox with documentation and
an invitation to use the system. This repository is ours.

Therefore, in anything sent to them:

- **Never reference a path in this repository.** `scripts/repro-issue-003-curl.sh`
  means nothing to someone who does not have the repository, and asking them to
  clone unfamiliar tooling to reproduce a defect in their own product is a
  reason to deprioritise it.
- **Inline the reproduction as literal curl commands** against their own
  endpoints with their own token. It must be copy-pasteable into a terminal
  with nothing installed.
- Mention the framework only as provenance for how the defect was found at
  scale, never as a dependency.

Guidance behind the wording:

- Lead with the defect, not the project that found it.
- Three points have to land before anyone stops reading: it is **silent**, it
  **destroys data**, and it is triggered by **ordinary policy authoring**.
- Keep the product limitations separate. Mixing "please fix this bug" with
  "these shape what we can sell" risks the defect being triaged as feedback.

---

## Slack version

> **Themis: silent output corruption when two rules match overlapping text**
>
> We found a data-correctness bug in the Themis runtime while building
> validation tooling. Short version: if two rules in a policy match overlapping
> regions of the input, the runtime writes the replacement at the wrong offset
> and destroys the characters before it. Every request returns HTTP 200 and
> nothing indicates anything went wrong.
>
> ```
> rules:   "ABCD" -> "[P]"   and   "DEFG" -> "[Q]"
> input:   x ABCDEFG y
> correct: x [P]EFG y
> actual:  x [P[Q] y
> ```
>
> With a 3-character overlap it destroyed two characters of input that neither
> rule matched.
>
> Three things worth knowing:
>
> 1. It is silent - HTTP 200 every time, no error, no signal.
> 2. It destroys data rather than mis-redacting it. In one case `name: ` came
>    back as `na`.
> 3. Ordinary policy authoring triggers it. Redacting both "Acme Corp" and
>    "Acme Corporation" is enough. So is "ACCT-1234" alongside "1234-5678",
>    where neither literal contains the other.
>
> Either rule alone is fine. Only having both in the same policy triggers it,
> and rule order does not matter. Adjacent matches that do not share bytes are
> correct.
>
> Reproduces with two rules and one record, straight curl against your own
> tenant - full commands in the thread. Note the policy load replaces the
> active policy, so use a tenant where that is fine.
>
> Happy to walk through it or run it live.
>
> Happy to walk through it or run it live against any tenant.

---

## Email version

**Subject:** Themis: silent output corruption when two rules match overlapping
text

Hi <name>,

While building validation tooling for Themis we found a data-correctness defect
in the runtime that I think needs your attention.

**What happens**

When two rules in a policy match overlapping regions of the input, the runtime
computes the wrong start offset for the replacement and overwrites the
characters preceding it.

```
rules:   "ABCD" -> "[P]"   and   "DEFG" -> "[Q]"
input:   x ABCDEFG y
correct: x [P]EFG y
actual:  x [P[Q] y
```

With a three-character overlap, two characters of legitimate input that neither
rule matched were destroyed.

**Why we think it is serious**

It is silent. Every affected request returned HTTP 200 with no error field and
no indication the output was wrong. A caller has no way to detect it.

It destroys data rather than merely mis-redacting. In one case `name: ` was
reduced to `na`. The amount destroyed varies with the configured replacement
lengths, and shorter replacements destroy more surrounding content, not less.

It is reachable through ordinary policy authoring. A customer redacting both
"Acme Corp" and "Acme Corporation" hits it. So does one redacting "ACCT-1234"
alongside "1234-5678", where neither literal contains the other.

**What we established**

- Either rule alone produces correct output. Only their coexistence triggers it.
- Rule order in the policy makes no difference.
- Adjacent matches that do not share bytes are handled correctly, as are
  disjoint matches.
- Replacement length is not a factor, and this is unrelated to the known
  15-character replacement truncation.
- Replacement output is not re-scanned; matching is single pass.
- The match end offset is correct in every case we observed. Only the start is
  displaced, which may help narrow where to look.

**Reproducing it**

Two rules and one record, straight curl against your own tenant. Nothing to
install.

Note the policy load replaces the active policy, so please use a tenant where
that is acceptable.

```bash
POLICY_ENDPOINT="https://<host>:8444/policy"
PROCESS_ENDPOINT="https://<tenant>/v1/process"
TOKEN="<token>"
```

Step 1 - load a policy with two rules whose matches overlap:

```bash
printf '"ABCD" -> "[P]";\n"DEFG" -> "[Q]";\n' | curl -sS \
  -X POST "$POLICY_ENDPOINT" \
  -H "Authorization: Bearer $TOKEN" \
  --data-binary @-
```

Step 2 - send one record containing `ABCDEFG`:

```bash
curl -sS -X POST "$PROCESS_ENDPOINT" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"message":"x ABCDEFG y"}'
```

Correct output is `x [P]EFG y`. Observed output is `x [P[Q] y`.

Step 3 - the control. Load either rule on its own and repeat step 2:

```bash
printf '"ABCD" -> "[P]";\n' | curl -sS \
  -X POST "$POLICY_ENDPOINT" \
  -H "Authorization: Bearer $TOKEN" \
  --data-binary @-
```

That returns `x [P]EFG y` correctly, which is what isolates the fault to the
combination rather than either rule.

A larger overlap destroys more. With `"ABCDEF" -> "[P]"` and
`"DEFGHI" -> "[Q]"` against `x ABCDEFGHI y`, the output is `x [Q] y` - the `AB`
is gone.

If your endpoint presents a self-signed certificate you may need `-k`. We
mention it only because we hit it; it is not required by the reproduction.

**Scale of impact**

We built internal tooling to exercise the sandbox with generated workloads. A
10,000-record run against a 5,000-rule policy returned 272 corrupted records
with a 100% HTTP success rate - nothing in any response indicated a problem.
Removing the overlapping rule pairs and re-running produced 10,000 passes and
zero mismatches, so this accounted for every failure we saw.

The tooling is only how we found it at volume. Everything above reproduces
without it.

Separately, we have a short list of product observations about the policy
lifecycle - identity, versioning, and deployment readiness. I will send those
on their own so they do not compete with this.

Happy to walk through any of it or run the reproduction live.

<name>

---

## Question to raise alongside, not in the same message

The process response includes `jid`, `frameId`, and `last: true`, which suggests
a framed or streaming protocol rather than simple request/response.

Today we POST a payload and the transformed payload returns to the caller, who
must then forward it onward. For a production data path the caller handles
unredacted content on both sides of the call, which partly defeats the purpose.

Worth asking: **is there an inline, proxy, or streaming mode, and what is the
intended integration pattern for a real deployment?** This is a question rather
than a finding - we may simply be using the wrong endpoint.
