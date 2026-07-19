# Nol8 Validation Framework

## Project purpose

This repository validates Nol8/Themis processing behavior with deterministic,
enterprise-shaped workloads. It is a staged validation framework rather than a
single test script: generation, policy deployment, request execution, and
comparison produce durable artifacts in a timestamped Run directory.

The implemented lifecycle is:

```text
generate
   |
policy deploy
   |
run
   |
compare
```

Each stage validates its prerequisites and records status, timestamps, counters,
errors, and artifact metadata in `manifest.json`. Generated and execution
evidence is retained when a later stage fails.

## Architecture overview

### Design principles

- **Deterministic and reproducible validation:** the same resolved configuration
  and seed produce the same policy, corpus, and expected evidence.
- **Realistic enterprise-shaped workloads:** synthetic values are placed in
  coherent business records rather than exposed as generator markers.
- **Durable validation evidence:** stage state and artifacts are retained so
  results and failures can be inspected after execution.
- **Explainable comparison results:** outcomes preserve record identifiers,
  expected and actual content, and the rule evidence behind transformations.

### Workload configurations

YAML files define deterministic inputs to generation:

- `config/test-cases.yaml` drives the original functional generator.
- `config/workloads/customer-record-json.yaml` is the focused realistic
  `customer_record + JSON + small` workload.
- `config/workloads/support-ticket-json.yaml` is the focused realistic
  `support_ticket + JSON + small` workload.
- `config/workloads/enterprise-dlp.yaml` defines the broader mixed enterprise-DLP
  schema and scale controls.

Scale-oriented workload configuration includes the seed, rule count, record
count, policy families, scenario and format weights, match distributions, size
profiles, and progress interval. `validate generate --rules N --records N` can
override rule and record counts for scale-oriented configurations without
modifying their source YAML. The resolved configuration is snapshotted into the
Run.

### Synthetic enterprise data generation

`framework/workload/generate_scale_artifacts.py` builds one deterministic rule
catalog and uses it for all three parts of the validation contract:

```text
policy literal -> natural document placement -> expected replacement evidence
```

Rule values are synthetic and non-production, but shaped like enterprise data:
names, email addresses, telephone numbers, customer and case identifiers,
credentials, financial identifiers, infrastructure values, and related data.

The currently implemented realistic slices are:

- Customer records serialized as small JSON documents.
- Support tickets serialized as small JSON documents.

These documents contain enterprise-like fields and natural placement of selected
policy literals. Clean controls are checked to ensure that no configured policy
literal occurs in the serialized record. Realistic documents do not contain
generator markers or `_synthetic_padding` fields.

The broader enterprise-DLP YAML also describes employee records, email messages,
application logs, API transactions, financial transactions, healthcare claims,
and AI interactions across multiple formats. Those combinations currently use
the generic generation path unless a dedicated realistic slice exists; they
should not be described as fully modeled scenarios yet.

### Policy generation and deployment

Generation emits `generated/scale-policy.nol`. Every policy literal and
replacement comes from the same rule catalog used to create the corpus and its
expected evidence.

`validate policy` deploys that artifact through `scripts/load-policy.sh`.
Authentication, endpoint selection, curl invocation, and network timeouts remain
inside the shell transport. The Python stage records only sanitized deployment
facts and the allowlisted Themis response fields; it does not persist credentials
or request headers.

Policy deployment supports `themis` (default) and `aergia`. Execution currently
supports `themis`.

### Workload execution

`validate run` reads `generated/input.jsonl` sequentially and calls
`scripts/run-validation.sh` for each request. It writes
`generated/output.jsonl` incrementally, preserving request order and completed
evidence if execution is interrupted. The Run manifest counters are updated as
requests complete.

The shell transport owns endpoint configuration and bearer authentication. It
returns only transport facts: HTTP status, latency, and the sanitized processing
response. Both transports use a 5-second connection timeout and a 30-second
overall timeout.

Use `--limit N` to execute only the first N generated records for smoke testing.
This does not modify the generated corpus.

### Validation comparison

`validate compare` aligns artifacts using:

```text
output.request_index -> input row -> record_id -> expected row
```

It validates row counts, exact `request_index` ordering, unique record IDs, and
matching input/expected record-ID sets. Each record receives one outcome:

- `PASS`: execution succeeded and `response.message` exactly equals the expected
  message.
- `CONTENT_MISMATCH`: execution succeeded but the processed content differs.
- `EXECUTION_FAILURE`: transport, HTTP, or response-shape evidence is invalid.

Results are written to `generated/comparison.jsonl` with the record ID, expected
and actual messages, latency, outcome, and expected rule evidence.

## Validation model

### Functional validation

Functional validation uses small deterministic workloads and an explicit oracle:

```text
generated/input.jsonl
generated/expected.jsonl
generated/output.jsonl
generated/comparison.jsonl
```

`input.jsonl` contains the requests sent to Themis. `expected.jsonl` contains the
full intended processed message and structured match evidence. `output.jsonl`
contains the observed processing results. `comparison.jsonl` records the durable
comparison outcome.

The expected artifact is necessary because HTTP success alone does not establish
correct processing. Exact expected messages can detect:

- Missed matches.
- Incorrect or truncated replacements.
- Content corruption.
- Unexpected changes to clean or unrelated content.
- Execution failures that did not produce a valid processed message.

### Scale validation

The current scale-oriented generator preserves the same functional artifact contract,
including one `expected.jsonl` row per input row. This is suitable for bounded
scale-oriented exercises, but generating full expected output documents is not the target
design for workloads containing millions of records.

A future large-scale validation mode should use compact evidence:

```text
input.jsonl
validation_manifest.jsonl
output.jsonl
```

In that model, `validation_manifest.jsonl` would record deterministic placement
and transformation evidence rather than duplicating every complete expected
document. Comparison would reconstruct or verify only the required invariants.
This manifest-based mode is a roadmap item; it is not implemented in the current
CLI or artifact schema.

## Quickstart

### Prerequisites

- Python 3.12 or newer.
- `bash`, `curl`, and `jq` for policy and execution transports.
- PyYAML (`pip install -r requirements.txt`) or an editable project install.
- `config/demo.env` containing non-secret endpoint configuration.
- A local `.env` containing the required non-production bearer token, such as
  `THEMIS_TOKEN`. Do not commit secrets.
- Network access to the configured non-production services. See
  `KNOWN_BEHAVIORS.md` for the current sandbox-access limitation.

Install the project in a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

The examples below use the module entry point and therefore also work without
installing the `validate` console script when dependencies are available.

### 1. Generate a Run

```bash
python -m framework.cli generate \
  --config config/workloads/customer-record-json.yaml
```

Generation prints a Run directory such as:

```text
artifacts/runs/20260719T120000000000Z
```

For a small scale-oriented workload smoke corpus:

```bash
python -m framework.cli generate \
  --config config/workloads/enterprise-dlp.yaml \
  --rules 100 \
  --records 10
```

### 2. Deploy its policy

```bash
python -m framework.cli policy \
  --run artifacts/runs/<run-id> \
  --target themis
```

The stage requires completed generation and a generated policy. A successful
HTTP response must contain valid JSON with `ok` exactly equal to `true`.

### 3. Execute the corpus

```bash
python -m framework.cli run \
  --run artifacts/runs/<run-id> \
  --target themis
```

For a smoke test:

```bash
python -m framework.cli run \
  --run artifacts/runs/<run-id> \
  --target themis \
  --limit 5
```

The Run stage requires successful generation and policy stages. Progress is
shown in the terminal while evidence is persisted incrementally.

### 4. Compare actual and expected behavior

```bash
python -m framework.cli compare \
  --run artifacts/runs/<run-id>
```

The Compare stage requires completed generation, policy, and execution stages.
It writes `generated/comparison.jsonl` and prints transformation, outcome, and
latency summaries.

## Workload generation

A scale-oriented workload YAML is the source of truth for:

- Deterministic seed.
- Rule and record counts.
- Policy families and pattern IDs.
- Scenario and serialization-format distributions.
- Clean, light, moderate, and heavy match profiles.
- Payload-size profiles and explicit size-boundary padding behavior.

The realistic builders receive selected catalog rules and place their exact
values into semantically appropriate fields. Examples include requester email in
a support ticket, customer ID in record metadata, credentials in security notes,
and financial values in billing notes. The builder returns placement evidence;
the generator handles serialization, artifacts, and final expected-message
calculation.

Padding remains available for explicitly configured size-boundary workloads via
`pad_to_target: true`. It is not used by realistic JSON slices; document content
there contains only enterprise-like data. Generation manifests record actual
payload bytes, padding totals, and generation-mode distribution.

## Comparison behavior and replacement normalization

By default, Compare validates the full replacement strings stored in
`expected.jsonl`:

```bash
python -m framework.cli compare --run artifacts/runs/<run-id>
```

The current Themis implementation has an observed limitation that truncates
replacement strings to 15 characters (Issue #001 in `KNOWN_BEHAVIORS.md`). To
validate current behavior explicitly, normalize expected replacement literals at
comparison time:

```bash
python -m framework.cli compare \
  --run artifacts/runs/<run-id> \
  --replacement-max-length 15
```

This option changes only comparison-time normalization. It does not modify the
rule catalog, emitted policy, `input.jsonl`, or `expected.jsonl`; those artifacts
continue to represent the correct product contract. Omitting the option after the
Themis implementation is corrected will validate full replacement behavior and
expose truncation as `CONTENT_MISMATCH`.

## Run artifacts

A typical Run contains:

```text
artifacts/runs/<run-id>/
├── config/
│   └── <resolved-workload>.yaml
├── generated/
│   ├── scale-policy.nol
│   ├── input.jsonl
│   ├── expected.jsonl
│   ├── output.jsonl
│   ├── comparison.jsonl
│   └── generation-manifest.json
└── manifest.json
```

Later-stage artifacts appear only after those stages run. Artifact paths in the
Run manifest are relative and include SHA-256 and byte-size metadata where the
stage supports it. Manifest writes and completed comparison artifacts use atomic
replacement; execution output is appended durably so interrupted work remains
usable.

## Adding a new validation slice

Extend the existing `scenario + format + size` pattern. A new realistic slice
should include:

1. A deterministic scenario builder that creates coherent enterprise data.
2. Natural placement of selected rule-catalog values.
3. Placement evidence linking each value to its rule, category, and replacement.
4. Clean controls proven not to contain any catalog literal.
5. Routing limited to the intended scenario, format, and size profile.
6. Focused deterministic, placement, policy, expected-output, and clean-record
   tests.
7. A small generated corpus that can complete policy deployment, execution, and
   comparison with `PASS` when the target service is available.

Scenario builders should not load YAML, choose rules, serialize documents, write
artifacts, or calculate complete expected messages. Those responsibilities remain
in the workload generator and lifecycle stages.

## Testing

Run the complete unit suite without contacting live services:

```bash
.venv/bin/python3 -B -m unittest discover -v
```

Focused examples:

```bash
.venv/bin/python3 -B -m unittest -v tests.test_support_ticket_scenario
.venv/bin/python3 -B -m unittest -v tests.test_validate_scale_generate
.venv/bin/python3 -B -m unittest -v tests.test_validate_compare
.venv/bin/python3 -B -m unittest -v tests.test_workload_padding
```

Transport tests mock curl and do not contact production services. Live policy and
execution validation requires explicit non-production configuration and suitable
network access. The current suite covers generation, realistic scenario
placement, policy-stage semantics, transport sanitization, incremental execution,
comparison alignment and outcomes, replacement normalization, and format-safe
padding. As of 2026-07-19, the repository suite contains 80 passing unit tests.

## Future roadmap

- Add realistic builders for more enterprise-DLP scenarios and formats.
- Introduce compact manifest-based validation for very large corpora.
- Add controlled performance and throughput benchmarking.
- Build repeatable enterprise regression suites across policy and workload
  versions.
- Add the report stage using existing durable comparison evidence.

## Known behaviors

See `KNOWN_BEHAVIORS.md` for confirmed product limitations and environment
constraints, including Themis replacement truncation and sandbox service
accessibility.
