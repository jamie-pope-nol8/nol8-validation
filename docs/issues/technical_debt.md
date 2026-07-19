Pytest warning:
framework/execution/run_functional_test.py::TestResult

Cause:
Dataclass named TestResult is being interpreted by pytest as a test class.

Potential fixes:
- Rename the dataclass.
- Move it outside test discovery paths.
- Configure pytest collection rules.

Priority:
Low. No functional impact.

----
Placement evidence consistency

Current:
Customer scenarios infer evidence through selected rules and output scanning.
Support ticket scenarios maintain explicit placement evidence.

Future:
Define a common placement evidence schema across workload builders.

Priority:
Medium. Important for future scale validation and AI workflow validation.

----
Add a technical debt entry documenting missing execution telemetry required for future Nol8 performance reporting.

Context:
The validation report now identifies the Nol8 FPGA-accelerated data path, but current execution evidence only exposes request latency and harness throughput.

Document the future requirement:

Execution telemetry should eventually capture:
- FPGA processing time
- service processing time
- network overhead
- CPU involvement
- bytes processed
- transformation throughput

Goal:
Enable reports to distinguish:
- harness performance
- service latency
- actual FPGA data path performance

Do not modify implementation files.
Only update technical_debt.md.