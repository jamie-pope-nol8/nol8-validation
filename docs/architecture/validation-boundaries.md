Purpose:
Document validation framework capability boundaries discovered through engineering experiments.

Include:

# Validation Boundaries

## Purpose
Explain that this document records tested capability limits, discoveries, and required evolution before customer-facing proof-of-concept use.

## Completed Validation Points

### Functional baseline
- Workload
- Records
- Rules
- Result
- Evidence produced

### First scale validation
- customer_record + CSV
- 1000 records
- 500 rules
- Result
- Performance observations

## Boundary Discovery

### 5000-rule experiment
Document:
- Attempted configuration
- Failure
- Root cause
- Why the validation guardrail correctly failed
- Required remediation

## Current Product Readiness

Separate:
- Customer-ready capabilities
- Engineering validation capabilities
- Remaining work before POC

---
## 5000 Rule / 10000 Record Qualification

Status:
Passed

Initial failure:
Clean-record collision caused by overlapping synthetic data domains.

Resolution:
- Unique policy literal generation.
- Deterministic collision avoidance in realistic customer data generation.
- Preserved clean-record collision invariant.

Qualification:
- 5000 unique rules.
- 10000 deterministic records.
- Zero clean collisions.

---
## Execution Model Boundary

### Sequential Validation Driver

Status:
Known limitation / planned evolution

Observed:
- 1,000 records / 500 rules sustained ~24 req/sec
- 10,000 records / 5,000 rules sustained ~24 req/sec

Conclusion:
The current validation driver scales in workload size but does not model a production streaming data path.

Current behavior:
- Sequential request execution
- One request in flight
- Harness throughput includes client-side overhead

Impact:
Reported throughput represents validation harness capacity, not Nol8 data-plane capacity.

Future evolution:
Introduce streaming execution mode:
- concurrent workers
- producer/consumer model
- configurable concurrency
- records/sec and bytes/sec measurement
- latency distribution under load

---
## 10,000 Record / 5,000 Rule Scale Qualification

Status:
Passed

Configuration:
- Workload: customer_record + CSV
- Records: 10,000
- Rules: 5,000

Results:
- Records processed: 10,000
- Requests succeeded: 10,000
- Requests failed: 0

Execution:
- Total duration: 416.045 seconds
- Sustained harness throughput: ~24 req/sec

Observed service latency:
- Average: 12.576 ms
- p50: 12.498 ms
- p95: 14.207 ms
- p99: 16.462 ms

Conclusion:
The current validation driver successfully executes and validates large workloads. Throughput is limited by the sequential execution model of the harness rather than workload size, policy size, or execution stability.

Future evolution:
Introduce streaming/concurrent validation execution to measure sustained data-path throughput.

----
## Replacement Interaction Boundary