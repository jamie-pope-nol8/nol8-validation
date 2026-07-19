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