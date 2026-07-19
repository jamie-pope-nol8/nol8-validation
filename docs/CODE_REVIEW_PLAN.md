# Code Review and Correction Plan

Date: 2026-07-19  
Status: Proposed - nothing executed  
Scope: Full review of framework/, scripts/, tests/ (~7,800 lines)

Four parallel reviews covered the CLI orchestrator, workload generation,
execution and transport, and reporting and tests. Findings are consolidated
here and ordered by risk to the product claim.

---

## The central theme

The framework can report a result that is not true, in both directions.

It can report success when nothing was validated, and it can report the product
as broken when the framework is wrong. For a tool whose entire purpose is
detecting silent corruption in someone else's product, silent corruption in
this tool is the defining risk.

Nothing here invalidates ISSUE-003. That defect was proven with raw curl
against Themis's own response payload, with no framework code in the path.

---

## Tier 0 - The framework can certify a broken product

These allow a passing result that means nothing. Fix before anyone external
sees a report.

**T0-1. A 2xx with no result field records success.**  
`scripts/run-validation.sh:117-119` extracts `(.result // null)`; nothing checks
`result.message` exists. `framework/cli/main.py:495-499` sets success from HTTP
status alone. Themis returning `200 {"error":"policy not loaded"}` yields
`{"success": true, "response": null}` for every record. A 10,000-record run
reports 100% success while the product processed nothing.

**T0-2. An empty comparison file renders a green PASS banner.**  
`framework/reporting/generate_report.py:223` sets overall PASS when
`failed == 0`. Zero rows means zero failures. A truncated or empty
`comparison.jsonl` produces customer-facing evidence stating the product
passed. `report_run` accepts an empty file without complaint.

**T0-3. Pass rate rounds up to 100.00% with failures present.**  
`generate_report.py:259` formats `{pass_rate:.2f}%`. 99,999/100,000 displays
"100.00% Pass rate" styled green, beside a "1 Failed" tile.

**T0-4. Transport failures other than network are recorded without an error.**  
`framework/cli/main.py:467-507` special-cases only exit code 5. Exits 2, 3, and
6 fall through to a row with no error key, and the run stage is still written
`completed`. The operator cannot distinguish a network drop from a bad response
body from a 500.

---

## Tier 1 - The framework blames the product for its own bugs

These produce false positives. They directly threaten the credibility of any
finding this framework reports.

**T1-1. Expected output is computed from selected rules only, and that
invariant is false.**  
`framework/workload/generate_scale_artifacts.py:574-579` assumes only selected
rules can appear in a document. Measured on `enterprise-dlp.yaml`: 34 of 300
documents contained catalog literals absent from `expected_matches`, 5 of 4,000
fully independent of any selected rule. Two sources: `date_of_birth` values
collide with catalog literals at ~1.3%, and `support_ticket` emits
`DEMO-CASE-{index}` which contains the `CASE-{index}` literal.

Effect: Themis correctly redacts a value the expected file says should survive,
and is scored as a failure.

**T1-2. Clean records can contain policy literals.**  
`generate_scale_artifacts.py:190-236` performs no catalog-collision check.
Only the customer-record and support-ticket paths check; every other
scenario/format/size combination is unguarded. Measured: 12 of 800 clean
`healthcare_claim` records carried literals. These are written with
`expected_match_count: 0`, so correct redaction is scored as a failure.

**T1-3. Expected values are produced by a reimplementation of the product's
matcher.**  
`framework/policy/generate_functional_test.py:159-180` applies sequential
`str.replace` longest-first over already-transformed text. This is cascading
multi-pass substitution. If Themis performs single-pass leftmost-longest
matching, the two diverge whenever a replacement's output contains another
rule's variant.

The framework is judging the product against an independent, differently
specified algorithm. This needs to be either verified against documented Themis
semantics or reframed as an explicit modelling assumption.

**T1-4. Support ticket generation aborts at realistic rule counts.**  
`framework/scenarios/support_ticket.py:130-133` raises rather than repairs, and
trips on the generator's own `DEMO-CASE-` value. Reproduced with
`rule_count: 400` - immediate `ValueError`, no artifacts. Passes today only
because the test fixture uses 12 rules.

**T1-5. Generation is not deterministic for log-formatted documents.**  
`framework/workload/generate_workload.py:607` falls back to
`datetime.now(UTC)`. Around 9% of `enterprise-dlp.yaml` documents are affected.
Two runs one second apart differ. This breaks the reproducibility guarantee the
manifest implies.

**T1-6. Generation depends on YAML key order, not only the seed.**  
`generate_workload.py:209-213` builds a list from `dict.keys()` and passes it
to `random.choices`. Reordering semantically identical config produces a
different catalog. Currently latent because the snapshot uses
`sort_keys=False`, but any re-serialization silently invalidates
reproducibility.

---

## Tier 2 - Security

**T2-1. TLS verification disabled on the policy control plane.**  
`scripts/load-policy.sh:74` uses `curl -skS`, unconditionally, on the one call
carrying both the bearer token and the complete DLP ruleset. A MITM can steal
the token, read the customer's full definition of what they consider sensitive,
and substitute a permissive policy - after which validation reports clean
passes against attacker-supplied rules. `run-validation.sh` does not use `-k`,
which suggests this papers over a certificate problem on the control plane.
That is itself a product finding.

**T2-2. Both transports source a git-tracked file.**  
`run-validation.sh:21` and `load-policy.sh:23` source `config/demo.env`, which
is committed. Anyone who can land a change to that file gets code execution on
every machine that runs validation, plus exfiltration of the tokens sourced
immediately afterward.

**T2-3. Bearer token passed on the command line.**  
`load-policy.sh:80`, `run-validation.sh:81`. Readable via `ps` by any local
user, once per record in the execution path.

**T2-4. Plaintext content and error bodies written to artifacts.**  
`framework/execution/run_functional_test.py:263` embeds full HTTP error bodies
into results files; `:373-374` writes full expected and actual messages. No
restrictive file permissions anywhere. Pointed at real data this writes
plaintext sensitive content to disk.

**T2-5. The processing endpoint is called without authentication in two of
three paths.**  
`scripts/process-message.sh:51-57` and `run_functional_test.py:229-237` send no
Authorization header. Either the tenant accepts unauthenticated submissions,
which is a product security problem, or these paths have been failing silently.

---

## Tier 3 - Product limitations to document

These are not framework bugs. They are Themis characteristics this work
surfaced, and they belong in product documentation.

**T3-1. Policy deployment replaces the entire ruleset.**  
No namespace, no version, no partial update, no rollback, no dry run, and no
way to read back what is currently deployed. Implications:

- Two teams sharing a credential silently clobber each other, with no error.
- Recovery depends on a human having retained the previous policy file. There
  is no server-side history.
- Adding one rule requires re-uploading the entire ruleset, which is exactly
  the operation that introduces prefix-overlapping literals and therefore
  ISSUE-003.
- A bad policy is either a DLP outage or silent under-redaction.

**T3-2. Policy deployment is fire-and-forget with no readiness signal.**  
The response carries `command_id` and `stage: apollo`, which suggests an
asynchronous distribution pipeline, but nothing polls for convergence. Records
sent immediately after deployment may be evaluated against the previous policy,
and if the previous policy was similar they will pass against stale rules.

**T3-3. Reported latency is not a product measurement.**  
Every request opens a fresh TCP and TLS connection - the CLI path forks a new
curl per record. Reported latency includes full handshake cost and is not
comparable to any keep-alive client. Failed requests contribute 0.0 ms to the
average, deflating results exactly when a run goes badly. Throughput appears in
the report beside "Nol8 FPGA-accelerated data path" but is dominated by process
spawn and per-request manifest writes.

---

## Tier 4 - Evidence quality and correctness

**T4-1. `--replacement-max-length` can mask wrong-rule application.**  
`framework/cli/main.py:799-824` truncates expected replacements, and truncation
is not injective. Verified against the qualification catalog: three distinct
tokens collapse to `[BUSINESS_TERMS` at 15 characters. If Themis applied
`CUSTOMER_ID` where `CONTRACT_NUMBER` was expected, comparison scores PASS. The
qualification contained 4,715 business_terms transformations, so its 272
failures are a floor, not an exact count.

**T4-2. No chain of custody between input and evidence.**  
Output rows carry only `request_index` - no record_id, no message hash, no
policy sha256. Correlation to `input.jsonl` is by line order alone, and nothing
binds a result to the policy that produced it.

**T4-3. JSONL readers split on Unicode line separators.**  
`main.py:620`, `:776`, `:1412` use `.splitlines()`, which splits on U+2028,
U+2029, and U+0085. Writers use `ensure_ascii=False`, so those characters are
emitted raw. One record containing U+2028 becomes two invalid lines, shifting
every subsequent `request_index` and silently pairing outputs against the wrong
inputs.

**T4-4. `--limit` produces a run that can never be compared.**  
`main.py:621` writes N rows; `compare_run` requires the full corpus and raises
an alignment error. The documented smoke-test path is a dead end, and the limit
is not recorded in the manifest.

**T4-5. Re-running a stage does not invalidate downstream stages.**  
Re-running `run` truncates `output.jsonl` while `stages.comparison` still reads
completed. `report` then renders from comparison rows describing output that no
longer exists. Artifact sha256 values are recorded but never verified except
for the policy.

**T4-6. Report does not explain causes.**  
272 failures render as 272 near-identical blocks of full expected and actual
text, with no diff, no grouping, and no root-cause classification - despite
both causes being known and having detectable signatures. The report never
warns that the deployed policy contains prefix-overlapping literals, which is
the highest-value single addition.

---

## Tier 5 - Structure and tests

**T5-1. `framework/cli/main.py` is 1,651 lines** containing four interleaved
layers. Natural seams: manifest handling, JSONL IO, transport, per-stage
orchestration, argument parsing, progress rendering, summary formatting.
`main()` is 235 lines and roughly 85% output formatting.

Load-bearing duplication, worth collapsing before the correctness fixes:
- Manifest load-and-validate preamble, 4 near-verbatim copies.
- Stage-failure epilogue, 7 copies.
- Atomic write, 4 hand-rolled copies - consolidating is the single-point fix
  for missing fsync and fixed temp-file names.
- Three JSONL readers with three different failure semantics - the direct cause
  of T4-3 and several crash paths.

**T5-2. Test gaps, highest value first.**
- No test for prefix-overlapping literals, which the generator produces by
  construction and which triggers ISSUE-003.
- The expected-output equivalence test runs against a 12-rule fixture whose
  patterns cannot produce overlap, so it can never fail.
- No end-to-end pipeline test; each stage is tested against hand-written
  fixtures, so schema drift between stages is undetectable.
- Report-side malformed-artifact paths have zero coverage.
- `--limit` has a test whose name asserts a property the test does not check
  and which is false.

**T5-3. Tests are not hermetic.** `tests/test_transport_scripts.py` requires a
real `.env`, and the scripts source it after the test sets its own value, so
assertions run against the developer's production token.

---

## Recommended order

1. **Tier 0** - stop the framework certifying a broken product.
2. **T1-1, T1-2, T1-4, T1-5** - stop blaming the product for generator bugs.
   These are the prerequisite for any credible qualification run.
3. **T2-1, T2-2** - the two security issues with realistic blast radius.
4. **T3-1, T3-2** - document the product limitations, since they affect what
   can be sold rather than what can be tested.
5. **T1-3** - resolve whether the expected-value algorithm matches Themis
   semantics. This is the correctness core of the entire validation claim.
6. **T4** - evidence quality, before customers see reports.
7. **T5** - structure and tests, before external release.

Tiers 0, 1, and 2 are each small and independent. Tier 5 is the only item
requiring sustained work.

---

## Verified during review

Two claims were checked empirically rather than assumed.

**Replacement collisions under normalization** - confirmed. Three
`[BUSINESS_TERMS:*]` tokens collapse to a single 15-character string in the
qualification catalog.

**ISSUE-003 containment class** - tested prefix, suffix, and middle containment
against Themis with curl. Only prefix containment corrupts output; suffix and
middle render correctly, as does a disjoint control. The "strict prefix"
framing in ISSUE-003 is correct and precise.
