# Demos

The demo-environment workspace. **Self-contained and isolated** from the
validation framework (`framework/`, `tests/`): its own code, tests, and docs, so
it can later graduate to its own repository by lifting this directory out - no
disentangling.

It lives inside `nol8-validation` for now because it reuses the same live
endpoints (`config/demo.env` + `.env`), Themis transport knowledge, and policy
expertise. It does **not** import from `framework/`.

## Provenance and the "don't modify" rule

Assets are reused from `~/Code/nol8/preindex-benchmark-kit` (a benchmark
workbench with three use cases: pre-index / pre-post-inference / agent-mesh).
**That repo is never edited in place** - we copy what we need *out* of it into
here. See the review in `docs/continue-conversation.md` ("Next horizon").

## Contents

- `themis-adapter/` - the bridge that lets the benchmark harness run against real
  Themis. The benchmark speaks `{"text"}->{"action","text"}` (keep/mask/drop/
  route); Themis speaks `{"message"}->{"result":{"message"}}` (redaction only).
  The adapter translates between them and derives the action.

## Running the adapter tests

Self-contained; no network needed (point discovery at each demo's own dir):

```bash
source .venv/bin/activate
python -m unittest discover -s demos/themis-adapter -p 'test_*.py'
```

## Live-checking the adapter against Themis

Source the endpoints/token, deploy a tiny policy, start the adapter, POST text:

```bash
source config/demo.env && source .env    # THEMIS_PROCESS_ENDPOINT + THEMIS_TOKEN
python demos/themis-adapter/adapter.py &  # listens on 127.0.0.1:8799
curl -sS -X POST http://127.0.0.1:8799/ -d '{"text":"hello John Smith"}'
# -> {"action":"mask","text":"hello [PII:PERSON_NAME]"}  (given a matching policy)
```
