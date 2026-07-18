from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from framework.cli.main import ComparisonError, compare_run, main


class ValidateCompareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def create_run(
        self,
        output_rows: list[dict],
        *,
        input_rows: list[dict] | None = None,
        expected_rows: list[dict] | None = None,
    ) -> Path:
        run_directory = self.root / "20260718T031425123456Z"
        generated = run_directory / "generated"
        generated.mkdir(parents=True)

        if input_rows is None:
            input_rows = [
                {"record_id": "record-1", "kind": "dirty", "message": "secret"},
                {"record_id": "record-2", "kind": "clean", "message": "clean"},
            ]
        if expected_rows is None:
            expected_rows = [
                {
                    "record_id": "record-1",
                    "kind": "dirty",
                    "expected_message": "[REDACTED]",
                    "expected_match_count": 1,
                    "expected_matches": [
                        {
                            "category_id": "credentials",
                            "case_id": "secret-value",
                            "variant": "secret",
                            "replacement": "[REDACTED]",
                        }
                    ],
                },
                {
                    "record_id": "record-2",
                    "kind": "clean",
                    "expected_message": "clean",
                    "expected_match_count": 0,
                    "expected_matches": [],
                },
            ]

        for filename, rows in (
            ("input.jsonl", input_rows),
            ("expected.jsonl", expected_rows),
            ("output.jsonl", output_rows),
        ):
            (generated / filename).write_text(
                "".join(json.dumps(row) + "\n" for row in rows)
            )

        manifest = {
            "schema_version": 1,
            "run_id": run_directory.name,
            "status": "run_completed",
            "updated_at": "2026-07-18T03:14:25.123456Z",
            "artifacts": {},
            "stages": {
                "generation": {"status": "completed"},
                "policy": {"status": "completed"},
                "run": {"status": "completed"},
                "execution": {"status": "pending"},
                "comparison": {"status": "pending"},
                "reporting": {"status": "pending"},
            },
        }
        (run_directory / "manifest.json").write_text(json.dumps(manifest))
        return run_directory

    def read_comparison(self, run_directory: Path) -> list[dict]:
        return [
            json.loads(line)
            for line in (run_directory / "generated/comparison.jsonl")
            .read_text()
            .splitlines()
        ]

    def test_successful_comparison_creates_evidence_and_updates_manifest(self) -> None:
        run_directory = self.create_run(
            [
                {
                    "request_index": 1,
                    "http_status": 200,
                    "latency_ms": 1.1,
                    "success": True,
                    "response": {"message": "[REDACTED]"},
                },
                {
                    "request_index": 2,
                    "http_status": 200,
                    "latency_ms": 1.2,
                    "success": True,
                    "response": {"message": "clean"},
                },
            ]
        )

        manifest = compare_run(run_directory)
        rows = self.read_comparison(run_directory)

        self.assertEqual([row["status"] for row in rows], ["PASS", "PASS"])
        self.assertEqual(rows[0]["record_id"], "record-1")
        self.assertEqual(rows[0]["expected_match_count"], 1)
        self.assertEqual(len(rows[0]["expected_matches"]), 1)
        stage = manifest["stages"]["comparison"]
        self.assertEqual(stage["status"], "completed")
        self.assertEqual(stage["records_total"], 2)
        self.assertEqual(stage["records_passed"], 2)
        self.assertEqual(stage["content_mismatches"], 0)
        self.assertEqual(stage["execution_failures"], 0)
        self.assertEqual(manifest["status"], "comparison_completed")
        artifact = manifest["artifacts"]["comparison"]
        comparison_path = run_directory / artifact["path"]
        self.assertEqual(artifact["size_bytes"], comparison_path.stat().st_size)
        self.assertEqual(
            artifact["sha256"],
            hashlib.sha256(comparison_path.read_bytes()).hexdigest(),
        )

    def test_content_mismatch_is_durable_evidence(self) -> None:
        run_directory = self.create_run(
            [
                {
                    "request_index": 1,
                    "http_status": 200,
                    "latency_ms": 1.0,
                    "success": True,
                    "response": {"message": "wrong"},
                },
                {
                    "request_index": 2,
                    "http_status": 200,
                    "latency_ms": 1.0,
                    "success": True,
                    "response": {"message": "clean"},
                },
            ]
        )

        manifest = compare_run(run_directory)
        first = self.read_comparison(run_directory)[0]

        self.assertEqual(first["status"], "CONTENT_MISMATCH")
        self.assertEqual(first["actual_message"], "wrong")
        self.assertIsNotNone(first["error"])
        self.assertEqual(manifest["stages"]["comparison"]["content_mismatches"], 1)

    def test_execution_failure_is_distinct_from_content_mismatch(self) -> None:
        run_directory = self.create_run(
            [
                {
                    "request_index": 1,
                    "http_status": None,
                    "latency_ms": 0.0,
                    "success": False,
                    "response": None,
                },
                {
                    "request_index": 2,
                    "http_status": 200,
                    "latency_ms": 1.0,
                    "success": True,
                    "response": {"message": "clean"},
                },
            ]
        )

        manifest = compare_run(run_directory)
        first = self.read_comparison(run_directory)[0]

        self.assertEqual(first["status"], "EXECUTION_FAILURE")
        self.assertIsNone(first["actual_message"])
        self.assertEqual(manifest["stages"]["comparison"]["execution_failures"], 1)

    def test_long_replacement_mismatches_without_maximum_length(self) -> None:
        expected_message = "Contact: [PII:EMAIL_ADDRESS]"
        actual_message = "Contact: [PII:EMAIL_ADDR"
        input_rows = [
            {
                "record_id": "record-1",
                "kind": "dirty",
                "message": "Contact: user@example.test",
            }
        ]
        expected_rows = [
            {
                "record_id": "record-1",
                "kind": "dirty",
                "expected_message": expected_message,
                "expected_match_count": 1,
                "expected_matches": [
                    {
                        "category_id": "pii",
                        "case_id": "email_address",
                        "variant": "user@example.test",
                        "replacement": "[PII:EMAIL_ADDRESS]",
                    }
                ],
            }
        ]
        run_directory = self.create_run(
            [
                {
                    "request_index": 1,
                    "http_status": 200,
                    "latency_ms": 1.0,
                    "success": True,
                    "response": {"message": actual_message},
                }
            ],
            input_rows=input_rows,
            expected_rows=expected_rows,
        )

        manifest = compare_run(run_directory)
        row = self.read_comparison(run_directory)[0]

        self.assertEqual(row["status"], "CONTENT_MISMATCH")
        self.assertEqual(row["record_id"], "record-1")
        self.assertEqual(row["expected_message"], expected_message)
        self.assertEqual(row["actual_message"], actual_message)
        self.assertEqual(row["expected_matches"][0]["category_id"], "pii")
        self.assertEqual(manifest["stages"]["comparison"]["content_mismatches"], 1)

    def test_long_replacement_passes_with_maximum_length(self) -> None:
        input_rows = [
            {
                "record_id": "record-1",
                "kind": "dirty",
                "message": "Contact: user@example.test",
            }
        ]
        expected_rows = [
            {
                "record_id": "record-1",
                "kind": "dirty",
                "expected_message": "Contact: [PII:EMAIL_ADDRESS]",
                "expected_match_count": 1,
                "expected_matches": [
                    {
                        "category_id": "pii",
                        "case_id": "email_address",
                        "variant": "user@example.test",
                        "replacement": "[PII:EMAIL_ADDRESS]",
                    }
                ],
            }
        ]
        run_directory = self.create_run(
            [
                {
                    "request_index": 1,
                    "http_status": 200,
                    "latency_ms": 1.0,
                    "success": True,
                    "response": {"message": "Contact: [PII:EMAIL_ADDR"},
                }
            ],
            input_rows=input_rows,
            expected_rows=expected_rows,
        )

        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "compare",
                    "--run",
                    str(run_directory),
                    "--replacement-max-length",
                    "15",
                ]
            )
        row = self.read_comparison(run_directory)[0]
        manifest = json.loads((run_directory / "manifest.json").read_text())

        self.assertEqual(exit_code, 0)
        self.assertEqual(row["status"], "PASS")
        self.assertEqual(row["expected_message"], "Contact: [PII:EMAIL_ADDR")
        self.assertEqual(
            manifest["stages"]["comparison"]["replacement_max_length"], 15
        )

    def test_short_replacement_is_unchanged_by_maximum_length(self) -> None:
        input_rows = [
            {
                "record_id": "record-1",
                "kind": "dirty",
                "message": "Customer CUST-1",
            }
        ]
        expected_rows = [
            {
                "record_id": "record-1",
                "kind": "dirty",
                "expected_message": "Customer [CUSTOMER]",
                "expected_match_count": 1,
                "expected_matches": [
                    {
                        "category_id": "business_terms",
                        "case_id": "customer_id",
                        "variant": "CUST-1",
                        "replacement": "[CUSTOMER]",
                    }
                ],
            }
        ]
        run_directory = self.create_run(
            [
                {
                    "request_index": 1,
                    "http_status": 200,
                    "latency_ms": 1.0,
                    "success": True,
                    "response": {"message": "Customer [CUSTOMER]"},
                }
            ],
            input_rows=input_rows,
            expected_rows=expected_rows,
        )

        compare_run(run_directory, replacement_max_length=15)
        row = self.read_comparison(run_directory)[0]
        self.assertEqual(row["status"], "PASS")
        self.assertEqual(row["expected_message"], "Customer [CUSTOMER]")

    def test_invalid_alignment_fails_stage_without_comparison_artifact(self) -> None:
        run_directory = self.create_run(
            [
                {
                    "request_index": 2,
                    "http_status": 200,
                    "latency_ms": 1.0,
                    "success": True,
                    "response": {"message": "[REDACTED]"},
                },
                {
                    "request_index": 1,
                    "http_status": 200,
                    "latency_ms": 1.0,
                    "success": True,
                    "response": {"message": "clean"},
                },
            ]
        )

        with self.assertRaises(ComparisonError) as caught:
            compare_run(run_directory)

        self.assertEqual(caught.exception.category, "alignment")
        manifest = json.loads((run_directory / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "comparison_failed")
        self.assertEqual(manifest["stages"]["comparison"]["status"], "failed")
        self.assertFalse((run_directory / "generated/comparison.jsonl").exists())

    def test_cli_prints_v1_functional_validation_summary(self) -> None:
        run_directory = self.create_run(
            [
                {
                    "request_index": 1,
                    "http_status": 200,
                    "latency_ms": 1.0,
                    "success": True,
                    "response": {"message": "[REDACTED]"},
                },
                {
                    "request_index": 2,
                    "http_status": 200,
                    "latency_ms": 1.0,
                    "success": True,
                    "response": {"message": "wrong"},
                },
            ]
        )
        manifest = compare_run(run_directory)
        output = StringIO()

        with patch("framework.cli.main.compare_run", return_value=manifest):
            with redirect_stdout(output):
                exit_code = main(["compare", "--run", str(run_directory)])

        self.assertEqual(exit_code, 0)
        rendered = output.getvalue()
        for expected in (
            "Functional Validation Summary",
            "Records evaluated:  2",
            "Records passed:     1",
            "Records failed:     1",
            "Pass rate:          50.000%",
            "Record breakdown:",
            "- Clean records: 1",
            "- Dirty records: 1",
            "Expected transformations:",
            "- Total expected replacements: 1",
            "Transformations by category:",
            "- credentials: 1",
            "Outcome breakdown:",
            "- PASS: 1",
            "- CONTENT_MISMATCH: 1",
            "- EXECUTION_FAILURE: 0",
            "Latency:",
            "- Average latency: 1.000 ms",
            "- p50: 1.000 ms",
            "- p95: 1.000 ms",
            "- p99: 1.000 ms",
            "Comparison artifact:",
            "generated/comparison.jsonl",
        ):
            self.assertIn(expected, rendered)


if __name__ == "__main__":
    unittest.main()
