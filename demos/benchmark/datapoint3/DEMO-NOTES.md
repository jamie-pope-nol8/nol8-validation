# Data Point 3 - agent-to-agent mesh control: demo notes

What DP3 proves, how to run it, and the honest scope. DP3 is DP2 generalized from two
control points to many: governance at every hop of an agent workflow.

## The claim

An agent workflow hands a task from one model to the next (Triage -> Research ->
Decision -> Action -> Final), calls tools, and returns an answer. NOL8 governs **every
hop** with one deterministic literal policy (`demos/policies/mesh.nol`), inline:

- **at each handoff** - route, block-handoff, or mask the agent-to-agent message;
- **at the tool call** - block a tool invocation before it executes;
- **at the final output** - block or tag what leaves the mesh for the user.

Two headline results from one clean run of the 12-task set on the **live Themis engine**:

1. **Governance survives the whole chain, verifiably.** `themis_api_mesh` reproduces an
   independent oracle **12 / 12 tasks, event for event** (`verify-oracle.py`), and equals
   the in-process RE2 / literal baselines on every governance action.
2. **Reduction before delivery.** The mesh forwards **52.6% less content downstream**
   than no control (797 -> 378 downstream tokens): blocked and routed tasks deliver
   nothing further, masked values travel redacted, so each agent receives only what it
   needs.

## How the oracle works (the integrity check pointed at us)

DP3's flow is stateful (a message is governed at every hop and redactions carry forward),
so a per-event check is not enough. `verify-oracle.py` **re-simulates the entire mesh
flow** with the same orchestration as the engine mode, but performs every literal
transformation with the framework's Aho-Corasick matcher (leftmost-longest,
non-overlapping) over `mesh.nol` instead of the engine, then compares the engine's events
to the oracle's one for one. The orchestration is shared harness logic; the thing being
independently verified is the engine's literal matching and replacement at each hop,
exactly where an ISSUE-004-style corruption would show up. Themis == oracle, 12/12.

## Honest scope (say this out loud in the demo)

- **listMatch only. Literal, case-insensitive.** No regex, no patterns. NOL8 governs the
  exact known values you declare. Regex is on the NOL8 roadmap; it is not in this demo.
- **Literal matching is substring-exact, so it can over-trigger.** One task in the set is
  a deliberate near-miss: "Contoso Advisory **Board**" is a different entity, but it
  contains the flagged literal "Contoso Advisory", so the mesh routes it. That is the
  honest boundary of listMatch. (The other near-miss, "Project Maple **Syrup**" vs the
  protected "Project Maple Vault", correctly does not match - different words.)
  Word-boundary regex and classification are the complementary layer, on the roadmap.
- **Precedence is deterministic and can differ from a task's headline intent.** A task
  that names a flagged customer routes at the first handoff before its tool-block phrase
  is ever evaluated (route wins over block_tool). This is defensible ordering, not an
  error; it is why contract-alignment with the labels is 10/12, not 12/12.
- **Mask is a governance action once.** A value masked at the first handoff stays a
  sentinel downstream; the engine and oracle count the mask at the hop where it is first
  redacted, not again at every later hop. (Earlier drafts double-counted; fixed.)
- **The RE2 baseline here is in-process (Go regexp), not the networked Aergia.** Go's
  `regexp` is a real RE2 implementation, run on the identical literal lists. It prevents
  the same exposures and takes the same actions. It reports slightly more delivered
  downstream (410 vs 378) only because the detect-only baseline substitutes a value on a
  mask, while the engine redacts every matched literal at every hop. The **networked RE2
  baseline (Aergia, :444) parity column is pending an engine-side outage**; add
  `aergia_api_mesh` to MODES once `check-engines.sh` is green.
- **The action counts describe the test-set composition, not a NOL8 metric.** What is
  NOL8's is oracle-correctness (12/12) and the reduction before delivery. Do not headline
  the raw counts.
- **The agents are deterministic stubs**, not real models. This isolates the mesh
  controls, exactly like DP1/DP2. Not a model-quality or throughput test.

## Reproduce (SA-runnable, on EC2)

```bash
# 0. preflight - engines reachable? (Themis :443 must be green; Aergia :444 optional)
bash demos/check-engines.sh

# 1. regenerate the mesh policy from the reference lists (safe: ISSUE-004/005 guards)
python demos/policies/build_mesh_policy.py     # -> demos/policies/mesh.nol

# 2. deploy + run every mode against the live Themis engine, combine, oracle-verify
bash demos/benchmark/datapoint3/run-live.sh
#   add Aergia once :444 is back:
#   MODES="nocontrol re2_mesh listmesh nol8sim_agent themis_api_mesh aergia_api_mesh" \
#     bash demos/benchmark/datapoint3/run-live.sh

# 3. (verify only) adjudicate the engine output against the oracle
python demos/benchmark/datapoint3/verify-oracle.py \
  --policy demos/policies/mesh.nol \
  --results demos/benchmark/datapoint3/results \
  themis_api_mesh
```

## The report

```bash
python demos/benchmark/make-report.py \
  demos/benchmark/datapoint3/run.json \
  demos/benchmark/datapoint3/agent-mesh-report.html
```

Self-contained HTML (fonts/logos inlined), web (dark) / deck (Export to PDF, light).
`run.json` (`kind: dp3`) carries the numbers above; regenerate the HTML after any edit.
The rendered HTML is gitignored.

## Next

- **Networked RE2 parity:** rerun with `aergia_api_mesh` once :444 returns, to add the
  byte-parity column (Themis == Aergia == oracle) like DP1/DP2.
- **Representative insurer mesh:** a DP3 representative dataset mirroring DP2's
  `representative/` set, the near-term bridge to the agentic insurance story. The full
  experience lives in Track B (agentic-mesh-lab), which consumes DP3's wiring and numbers.
