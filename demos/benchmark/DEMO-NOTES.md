# Pre-index demo — narrative + numbers

The story behind the combined benchmark and the latency decomposition. Audience
lens: a network-infrastructure partner (e.g. Megaport). Everything here is
measured, not simulated.

## The one-line thesis

**Deterministic governance before embedding, on real Themis (FPGA) and Aergia —
the engine is sub-millisecond, so nearly all latency is the network path.** That
reframes "how fast is your engine?" into "how good is the path?", which is a
networking conversation, not a compute one.

## The three beats

1. **It works, and it's identical on both engines.** Same literal policy deployed
   to Themis (:443) and Aergia (:444). Over 1,000 chunks: **535 governed, 0
   errors, byte-identical output on both engines** (verified 1000/1000). Example:
   `Westbridge Merchant Services` → `[CUSTOMER]`, `Redwood Identity` → `[PROJECT]`.
   Governance is deterministic and portable across engines.

2. **The engine is effectively free.** Decomposing a per-call round-trip
   (N = 100, medians, from the client box):

   | engine | network RTT | warm (pooled) | cold (TLS/call) | TLS tax | engine proc |
   |---|---|---|---|---|---|
   | Themis (FPGA) | 2.14 ms | 2.38 ms | 7.17 ms | 4.80 ms | **≤ 0.23 ms** |
   | Aergia | 2.01 ms | 1.73 ms | 6.18 ms | 4.45 ms | **≤ 0.00 ms** |

   The 7 ms benchmark number is **~97% transport** (TLS handshake + one network
   round-trip). Engine processing is below the network noise floor — an upper
   bound, because no server-side timing hook is exposed.

3. **The wins are on the path.** Connection pooling alone is 3× (7.17 → 2.38 ms).
   Beyond that, shorter/warmer/more-direct network paths translate almost 1:1 into
   end-to-end latency. The engine keeps up with the wire, so inline deterministic
   control has no meaningful compute latency budget.

## Honesty guardrails (say these, don't let anyone over-read the numbers)

- The 7 ms is **not** a Themis throughput number — it's single-threaded,
  new-connection-per-call, network-dominated. Do NOT quote 138 chunks/sec as an
  engine rate.
- Engine processing is an **upper bound** (warm − network RTT); it sits in the
  jitter, so "≤ 0.23 ms / sub-millisecond", not a precise figure.
- listMatch only — literal governance. No regex (Aergia can't do regex yet).
- Not a concurrency/saturation test. A real throughput/latency-under-load number
  needs parallel clients + server-side timing (next step if the perf angle matters).

## The report: three approaches, not four modes

The report is framed as three strategies for a chunk, because that is how a buyer
reads it:

- **Do nothing** (nofilter) - forward everything. 0 governed.
- **Traditional regex (software)** - a local Go RE2 baseline on a CPU, the
  incumbent way, for context. Catches pattern shapes + strips boilerplate; 395
  chunks touched. NOT a NOL8 engine - it's the thing we compare against. (Labelled
  "Traditional regex", never "RE2", to avoid colliding with Aergia, which the team
  calls "the RE2 engine".)
- **NOL8** (Themis + Aergia) - deterministic known-value governance. 535 governed,
  identical on both engines, sub-ms per call.

Dropped from the view: `nol8sim` (a placeholder - we have real results now) and
`listmatch` (the kit's LOCAL Go list-matcher - confusing next to the real NOL8
engines that do the same job for real). RE2 and NOL8 target different content, so
do NOT stage it as a token-reduction race - NOL8's story is deterministic
governance at hardware speed.

## Artifacts to show

- **THE report (open locally):** `demos/benchmark/pre-index-report.html` - the
  three-approach benchmark + the raw-FPGA latency decomposition, self-contained.
  Double-click / open in a browser. Committed, so it travels with the repo.
- **Same page, shareable link:** https://claude.ai/code/artifact/e07bb1c5-fdf9-461c-9059-31279d055230
  (private; share from the page's share menu. If the link won't open, use the
  local file above.)
- **Kit's original report** (`datapoint1/report/report.html`, from run-live.sh) is
  the raw detailed backup, but its template is hardcoded to the kit's old modes
  (shows `nol8sim`/`listmatch`) - use `pre-index-report.html` for showing.
- **Reproduce the latency numbers:** `python3 demos/benchmark/latency-decompose.py`
  on EC2 (`set -a; source .env; set +a` first).
