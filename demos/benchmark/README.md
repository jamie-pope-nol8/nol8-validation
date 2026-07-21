# Benchmark harness (demo)

The pre-index benchmark from `~/Code/nol8/preindex-benchmark-kit`, copied here
(never edited in place) so it can run against **real Themis** instead of the
kit's local simulation. See `datapoint1/` for the datapoint being measured.

## What it measures

`datapoint1` = **Pre-Index Optimization**: govern sensitive text *before* it lands
in embeddings. The Go harness (`datapoint1/go/benchmark.go`) streams a 1,000-chunk
corpus through one or more *modes* and records, per mode, how much was
kept/masked/dropped/routed, how many tokens were forwarded downstream (the embed
cost saved), and throughput (chunks/sec, wall time via `/usr/bin/time`).

Modes:

| mode | what it is | measured? |
|---|---|---|
| `nofilter` | passthrough baseline (everything forwarded) | yes |
| `re2` | traditional RE2 **regex** masking, in local Go (email/SSN/phone/ACC-ID + boilerplate) | yes |
| `listmatch` | **literal** reference-list matching, in local Go (software equivalent of Themis' approach) | yes |
| `nol8sim` | hard-coded placeholder — **not** real, excluded from our runs | no |
| `nol8_api` | **real Themis**, via the adapter below | yes |

The honest comparison axes: `re2` (pattern approach) vs `listmatch`/`nol8_api`
(literal approach), and `listmatch` (literal matching in software) vs `nol8_api`
(the same literal matching on Themis' FPGA path).

## How `nol8_api` reaches Themis

The harness speaks the benchmark contract `{"text"} -> {"action","text"}`
(keep/mask/drop/route). Themis speaks `{"message"} -> {"result":{"message"}}`
(redaction only). Our adapter bridges them:

```
benchmark.go (nol8_api)  --{"text"}-->  themis-adapter (127.0.0.1:8799)  --{"message"}-->  Themis
                         <--{action,text}--                              <--{result.message}--
```

The adapter (`demos/themis-adapter/adapter.py`) derives the action: unchanged ->
`keep`, changed -> `mask`, sentinel tokens -> `drop`/`route`. Themis is a *literal*
matcher, so `nol8_api` masks the corpus's **known governed values** (entities,
accounts, cards, projects — the ones in the starter policy) and leaves
**regex-class PII** (arbitrary emails/SSNs/phones) untouched. That gap is real and
intended: pattern classes are Aergia's (RE2) job — see the combined-report plan in
`docs/continue-conversation.md`.

## Run it (on EC2 — the box that can reach Themis)

```bash
cd /opt/nol8/nol8-validation && source .venv/bin/activate
export PATH=$HOME/.local/go/bin:$PATH            # Go 1.22 installed here

# 1. Deploy the starter policy (governs the corpus's known values)
validate policy --file demos/policies/starter-known-values.nol --target themis

# 2. Start the adapter (reads THEMIS_PROCESS_ENDPOINT + THEMIS_TOKEN)
source config/demo.env && source .env
ADAPTER_PORT=8799 python demos/themis-adapter/adapter.py &

# 3. Run the harness against the adapter
cd demos/benchmark/datapoint1
export NOL8_ENDPOINT="http://127.0.0.1:8799"
export MODES="nofilter re2 listmatch nol8_api"
bash scripts/run_all.sh
# -> results/run_01.csv, results/*_output.jsonl, report/report.html
```

Everything under `results/` and `report/report.html` and the Go binary are
generated (gitignored). Source, corpus, and reference lists are tracked.
