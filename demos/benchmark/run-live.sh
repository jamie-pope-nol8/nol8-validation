#!/usr/bin/env bash
# Run the datapoint1 benchmark against REAL Themis, via the adapter.
#
# One-shot: starts the Themis adapter as a child of this process, runs the Go
# harness (nol8_api mode hits the adapter -> Themis) plus the local baselines,
# then generates the combined HTML report and stops the adapter. Runs entirely
# on EC2 (the box that can reach Themis). Deploy the policy first:
#   validate policy --file demos/policies/starter-known-values.nol --target themis
#
# Env overrides: MODES, ADAPTER_PORT, NOL8_TIMEOUT_MS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # repo root
cd "$ROOT"

source .venv/bin/activate
set -a; source config/demo.env; source .env; set +a
export PATH="$HOME/.local/go/bin:$PATH"

MODES="${MODES:-nofilter re2 listmatch nol8_api}"
PORT="${ADAPTER_PORT:-8799}"
export NOL8_TIMEOUT_MS="${NOL8_TIMEOUT_MS:-10000}"

echo ">> starting Themis adapter on 127.0.0.1:$PORT"
ADAPTER_PORT="$PORT" python demos/themis-adapter/adapter.py >/tmp/adapter.log 2>&1 &
ADAPTER_PID=$!
trap 'kill "$ADAPTER_PID" 2>/dev/null || true' EXIT

# Wait for the adapter to accept connections.
for _ in $(seq 1 30); do
  if curl -sS -o /dev/null --max-time 5 -X POST "http://127.0.0.1:$PORT/" \
       -d '{"text":"ping"}' 2>/dev/null; then
    ready=1; break
  fi
  sleep 0.3
done
if [ "${ready:-0}" != 1 ]; then
  echo "!! adapter did not become ready" >&2; cat /tmp/adapter.log >&2; exit 1
fi
echo ">> adapter ready: $(cat /tmp/adapter.log)"

cd demos/benchmark/datapoint1
export NOL8_ENDPOINT="http://127.0.0.1:$PORT"
export MODES
echo ">> MODES=$MODES  NOL8_ENDPOINT=$NOL8_ENDPOINT"
bash scripts/run_all.sh
