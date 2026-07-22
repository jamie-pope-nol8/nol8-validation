# Data Point 2 demo, pre/post-inference control, narrative + numbers

The story behind the pre/post-inference benchmark. Audience lens: a team putting an
LLM into production that has to govern a model boundary. Everything here is measured
on the live engines, not simulated. Companion to the DP1 notes; same honesty rules.

## The one-line thesis

**A model boundary has two edges. NOL8 (Themis, FPGA) governs both deterministically,
inline, with the same literal policy, and produces byte-identical output to a real
RE2 incumbent (Aergia).** Block and route stop a third of prompts before the model is
ever called; masking and tagging happen at both edges; unsafe generated output is
caught on the way out.

## The three beats

1. **Two edges, one policy.** `demos/policies/boundary.nol` (19 literal rules) deploys
   to both engines. Each engine is called twice per prompt: once on the prompt
   (pre-inference), once on the model-stub output (post-inference). The action
   (block, route, mask, tag, allow) is derived from which sentinel the engine emitted
   (`[BLOCK]`, `[ROUTE]`, `[MASK_CARD]`, `[MASK_ACCT]`, `[TAG_INT]`, `[BLOCK_OUT]`,
   `[TAG_PRIV]`).

2. **NOL8 matches the incumbent, and is provably correct.** Over 52 prompts, Themis
   and Aergia produced **0 field-diffs** (byte-for-byte identical at both edges), and
   **both matched an independent oracle 52 of 52** (`verify-oracle.py`, the framework's
   Aho-Corasick matcher applied to the boundary policy). So the parity is not two
   engines agreeing on a mistake; both are correct. No corruption here, because the
   boundary policy redacts to sentinels rather than stripping to empty (contrast DP1,
   where strip-to-empty exposed an Aergia defect).

3. **A third of prompts never reach the model.** Block (5) and route (12) stopped 17
   of 52 prompts before inference. That is model spend avoided and policy enforced
   *before* the call. At the output edge, 4 unsafe responses were blocked and 11 were
   tagged privileged.

## The measured result (single clean run, 52 prompts, both live engines)

| edge | action | count |
|---|---|---|
| pre | blocked (never sent) | 5 |
| pre | routed (controlled path) | 12 |
| pre | tagged internal | 4 |
| pre | allowed through | 31 |
| post | blocked unsafe output | 4 |
| post | tagged privileged | 11 |
| post | allowed out | 20 |

- **Parity:** Themis vs Aergia, 0 diffs / 52. Both vs oracle, 52/52.
- **Tokens:** 379 forwarded to the model, 350 released from it (vs 599 in / 563 out
  for Do nothing).

## Honesty guardrails (say these; do not let anyone over-read the numbers)

- **listMatch scope, the important one.** NOL8 governs KNOWN literal values, not
  arbitrary patterns. On this set the literal engines (Themis, Aergia, listguard)
  masked **0** payment cards, because the prompts' card numbers are not exact list
  literals (e.g. `card 5555 6666 7777 8888`). A regex baseline (re2_guard) masked 12,
  and the oracle-sim expected 9. This is not a bug; it is the scope. Say: "NOL8
  governs the values you give it, exactly. Arbitrary-pattern masking, any card
  number, is regex, which NOL8 does not do yet." Do NOT imply NOL8 masks unknown
  patterns.
- **Exact, case-sensitive matching.** Literal matching is case-sensitive, so a block
  phrase only fires on the exact casing in the list. In the set, `Send raw notes to
  reseller leadership...` was ALLOWED pre-inference (the list has `send raw notes to
  reseller`, lower case) and was instead caught by the OUTPUT control post-inference.
  That is a legitimate defence-in-depth story (the second edge caught it), but be
  honest about the cause: a production policy should carry the casings the customer
  uses, or the customer should supply their own list. Both engines behave identically
  here (parity holds).
- **Tag is redact-to-marker, not metadata.** A literal engine can only replace, so a
  "tag" replaces the governed value with a sentinel (`Project Maple Vault` ->
  `[TAG_INT]`) rather than attaching metadata while preserving the text. Both engines
  do this identically. If a customer needs the original value preserved-and-flagged,
  that is a different control than literal redaction.
- **The model is a deterministic stub.** This measures the CONTROLS, not model
  quality, latency, or throughput. Do not present it as an LLM benchmark.
- **Same policy, same data, both engines.** No per-engine tuning. The result is the
  result.

## Reproduce (SA-runnable, on EC2, the box that reaches the engines)

```bash
# 1. build the boundary policy from the reference lists (only if lists changed)
python demos/policies/build_boundary_policy.py        # -> demos/policies/boundary.nol

# 2. deploy to both engines and run all modes (nocontrol re2_guard listguard
#    nol8sim_infer themis_api_infer aergia_api_infer), combine the CSV
bash demos/benchmark/datapoint2/run-live.sh

# 3. adjudicate each engine against the independent oracle
python demos/benchmark/datapoint2/verify-oracle.py \
  --results demos/benchmark/datapoint2/results themis_api_infer aergia_api_infer
```

The `themis_api_infer` / `aergia_api_infer` modes call the engine directly (no
adapter); they read `THEMIS_ENDPOINT` / `AERGIA_ENDPOINT` and the tokens, which
`run-live.sh` exports from `config/demo.env` + `.env`.

## The report

`demos/benchmark/datapoint2/run.json` (a `kind: dp2` data contract) is rendered by the
shared `demos/benchmark/make-report.py`:

```bash
python demos/benchmark/make-report.py \
  demos/benchmark/datapoint2/run.json \
  demos/benchmark/datapoint2/pre-post-report.html
```

Web (dark, open the file) / deck (Export -> PDF, light). The renderer is shared with
DP1; DP2 adds the `boundary`, `flows`, and appendix sections and drives the hero
CTAs, nav, and footer from `run.json`. The rendered HTML is gitignored.

**Open item:** the user flagged that the DP2 stat band / numbers need a conversation
before the copy is locked. Framing TBD.
