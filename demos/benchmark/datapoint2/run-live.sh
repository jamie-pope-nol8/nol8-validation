#!/usr/bin/env bash
# Run the Data Point 2 pre/post-inference benchmark against BOTH real engines.
#
# Deploys the same literal boundary policy to Themis (:443) and Aergia (:444),
# then runs every mode through the Go harness. The `themis_api_infer` and
# `aergia_api_infer` modes call the engine directly at two control points (govern
# the prompt, then govern the model-stub output) and derive block/mask/route/tag
# from the policy sentinels. Runs on EC2 (the box that reaches the engines).
#
# Scope note: listMatch (literal) only. No regex. All reference lists are literal.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"   # repo root
cd "$ROOT"

source .venv/bin/activate
set -a; source config/demo.env; source .env; set +a
export PATH="$HOME/.local/go/bin:$PATH"

POLICY="${POLICY:-demos/policies/boundary.nol}"
MODES="${MODES:-nocontrol re2_guard listguard nol8sim_infer themis_api_infer aergia_api_infer}"
export ENGINE_TIMEOUT_MS="${ENGINE_TIMEOUT_MS:-15000}"

echo ">> deploying the boundary policy to both engines"
validate policy --file "$POLICY" --target themis >/dev/null
validate policy --file "$POLICY" --target aergia >/dev/null
echo ">> waiting for Aergia reload to propagate"
sleep 6

PACK="demos/benchmark/datapoint2"
# Overridable so the same runner drives either dataset (functional-test default, or
# the representative-policy set). See representative/README.md.
RESULTS="${DP2_RESULTS:-$ROOT/$PACK/results}"
INPUT="${DP2_INPUT:-$ROOT/$PACK/data/prompts/sample_prompts.jsonl}"
LISTS="${DP2_LISTS:-$ROOT/$PACK/data/reference_lists}"
COMBINED="$RESULTS/run_all.csv"
mkdir -p "$RESULTS"
rm -f "$COMBINED"

# The engine modes resolve their endpoint/token from these (data planes, valid certs).
export THEMIS_ENDPOINT="$THEMIS_PROCESS_ENDPOINT"
export AERGIA_ENDPOINT="$AERGIA_PROCESS_ENDPOINT"
# THEMIS_TOKEN / AERGIA_TOKEN come from .env already.

for mode in $MODES; do
  echo ">> mode: $mode"
  ( cd "$ROOT/$PACK/go" && GOCACHE="$ROOT/$PACK/.gocache" \
      go run . --mode "$mode" --input "$INPUT" --list-dir "$LISTS" --output-dir "$RESULTS" ) \
    | sed 's/^/   /'
  if [ ! -f "$COMBINED" ]; then head -n 1 "$RESULTS/run_01.csv" > "$COMBINED"; fi
  tail -n +2 "$RESULTS/run_01.csv" >> "$COMBINED"
done

echo ">> combined CSV: $COMBINED"
column -s, -t "$COMBINED" 2>/dev/null || cat "$COMBINED"
