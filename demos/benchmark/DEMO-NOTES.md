# Pre-index demo — narrative + numbers

The story behind the combined benchmark and the latency decomposition. Audience
lens: a network-infrastructure partner (e.g. Megaport). Everything here is
measured, not simulated.

## The one-line thesis

**Deterministic governance before embedding — NOL8 (Themis, FPGA) matches a real
RE2 incumbent (Aergia) byte-for-byte, and the engine is sub-millisecond, so nearly
all latency is the network path.** That reframes "how fast is your engine?" into
"how good is the path?", which is a networking conversation, not a compute one.

## The three beats

1. **NOL8 matches the incumbent, exactly.** Same governance policy on NOL8
   (Themis, :443) and the RE2 incumbent (Aergia, :444). Over 1,000 chunks: **535
   governed, 0 errors, byte-identical output between NOL8 and RE2** (verified
   1000/1000). Example: `Westbridge Merchant Services` → `[CUSTOMER]`,
   `Redwood Identity` → `[PROJECT]`. NOL8 is a drop-in for the incumbent on
   correctness.

2. **The engine is effectively free.** Decomposing a per-call round-trip
   (N = 100, medians, from the client box):

   | engine | network RTT | warm (pooled) | cold (TLS/call) | TLS tax | engine |
   |---|---|---|---|---|---|
   | NOL8 (Themis, FPGA) | 2.14 ms | 2.38 ms | 7.17 ms | 4.80 ms | **< 0.3 ms** |
   | RE2 (Aergia) | 2.01 ms | 1.73 ms | 6.18 ms | 4.45 ms | **< 0.3 ms** |

   The 7 ms benchmark number is **~97% transport** (TLS handshake + one network
   round-trip). Engine processing is below the network noise floor on both — an
   upper bound, because no server-side timing hook is exposed. The small
   NOL8-vs-RE2 gap is network-path variance, not engine speed.

3. **The wins are on the path.** Connection pooling alone is 3× (7.17 → 2.38 ms).
   Beyond that, shorter/warmer/more-direct network paths translate almost 1:1 into
   end-to-end latency. The engine keeps up with the wire, so inline deterministic
   control has no meaningful compute latency budget. The FPGA-vs-software edge
   shows at **throughput/scale** — the next measurement, not this one.

## Honesty guardrails (say these, don't let anyone over-read the numbers)

- The 7 ms is **not** a NOL8 throughput number — it's single-threaded,
  new-connection-per-call, network-dominated. Do NOT quote 138 chunks/sec as an
  engine rate.
- Engine processing is an **upper bound** (warm − network RTT); it sits in the
  jitter, so "< 0.3 ms / sub-millisecond" for both, not a precise figure. Don't
  claim NOL8 beats RE2 on per-call latency — the gap is network jitter.
- The demo shows **listMatch** (literal governance) — that's what the NOL8 product
  (Themis) does today; regex isn't a NOL8 capability yet. RE2 (Aergia) is a regex
  engine, but here it runs the same literal task as the incumbent reference.
- Not a concurrency/saturation test. A real throughput/latency-under-load number
  needs parallel clients + server-side timing (next step if the perf angle matters).

## The report: three approaches, not four modes

The report is framed as three strategies for a chunk, because that is how a buyer
reads it:

**Engine identity (do not confuse):** **Themis == NOL8** (the FPGA product).
**Aergia == RE2** (a real RE2 engine stood up and named Aergia, as the known
incumbent to benchmark against). There is NO "Themis + Aergia" pair - it is
**NOL8 vs RE2**. The two data-plane ports map that way: :443 = NOL8 (Themis),
:444 = RE2 (Aergia). The kit's local Go `re2` mode is irrelevant (Aergia is the
real RE2).

- **Do nothing** (nofilter) - forward everything. 0 governed.
- **RE2 (Aergia)** - the known incumbent regex engine (:444). Given the same
  governance policy it flags the same chunks: 535 governed.
- **NOL8 (Themis, FPGA)** - deterministic known-value governance (:443). 535
  governed, **byte-identical to the RE2 incumbent**, sub-ms per call. Parity on
  correctness; the FPGA edge is throughput at scale (next test).

Dropped from the view: `nol8sim` (a placeholder - we have real results now) and
`listmatch` (the kit's LOCAL Go list-matcher - confusing next to the real NOL8
engines that do the same job for real). RE2 and NOL8 target different content, so
do NOT stage it as a token-reduction race - NOL8's story is deterministic
governance at hardware speed.

## The report (on-brand, Design-approved template)

**One data contract, one renderer.** `demos/benchmark/run.json` holds the run's
data; `make-report.py` renders it into a self-contained, on-brand HTML using the
NOL8 design system (charcoal + green, Space Grotesk / Google Sans). Fonts, logos,
and the hero pattern are inlined, so the file opens anywhere.

```bash
python demos/benchmark/make-report.py         # -> demos/benchmark/pre-index-report.html
```

- **Web (default):** open `pre-index-report.html` in a browser. Dark theme, sticky
  nav, engine-compare tabs, scroll-reveal. Interactivity degrades to fully-visible.
- **Deck / leave-behind:** the same file. Browser Export -> PDF triggers the
  `@media print` block, which forces the light (cream) palette and hides nav/tabs.
  That is the whole web/deck story - no separate build.
- The rendered HTML is **gitignored** (regenerate with the command above). Tracked:
  `run.json`, `make-report.py`, `brand/` (subset woff2 fonts, logos, pattern).
- Design source: `/private/tmp/HTML Report redesign/` (the handoff bundle -
  `Pre-Index Web Report.dc.html` + `_ds/` + README). We reimplemented from its
  `run.json` contract (Option B) rather than carry its `support.js` runtime.

**Brand voice (enforced in report copy):** no em dashes, no exclamation marks, no
emoji. Aergia is always "Aergia (RE2 baseline)" / "Google RE2", never a NOL8
product. Themis is "Themis (NOL8 · FPGA)".

- **Kit's original report** (`datapoint1/report/report.html`, from run-live.sh) is
  the raw detailed backup only (hardcoded to old kit modes) - not for showing.
- **Reproduce the latency numbers:** `python3 demos/benchmark/latency-decompose.py`
  on EC2 (`set -a; source .env; set +a` first).
