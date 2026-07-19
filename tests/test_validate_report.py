from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from framework.cli.main import ReportingError, main, report_run
from framework.reporting.generate_report import aggregate_evidence, render_report_html


class ValidateReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def create_run(
        self,
        *,
        comparison_status: str = "completed",
        generation: dict | None = None,
        comparison_rows: list[dict] | None = None,
    ) -> Path:
        run_directory = self.root / "20260719T120000000000Z"
        generated = run_directory / "generated"
        generated.mkdir(parents=True)
        if generation is None:
            generation = {
                "generator_schema": "enterprise-dlp-scale",
                "workload_name": "customer-record-json",
                "seed": 42,
                "requested_records": 3,
                "realized_records": 3,
                "requested_rules": 10,
                "realized_rules": 10,
                "clean_record_count": 1,
                "dirty_record_count": 2,
                "scenario_distribution": {"customer_record": 3},
                "format_distribution": {"json": 3},
                "expected_total_matches": 2,
            }
        if comparison_rows is None:
            comparison_rows = [
                {
                    "request_index": 1,
                    "record_id": "record-1",
                    "kind": "dirty",
                    "status": "PASS",
                    "http_status": 200,
                    "latency_ms": 1.0,
                    "expected_message": "[PII:EMAIL]",
                    "actual_message": "[PII:EMAIL]",
                    "expected_match_count": 1,
                    "expected_matches": [
                        {
                            "category_id": "pii",
                            "case_id": "email_address",
                            "variant": "person@example.test",
                            "replacement": "[PII:EMAIL]",
                        }
                    ],
                    "error": None,
                },
                {
                    "request_index": 2,
                    "record_id": "record-2",
                    "kind": "dirty",
                    "status": "CONTENT_MISMATCH",
                    "http_status": 200,
                    "latency_ms": 2.0,
                    "expected_message": "&lt;expected&gt;",
                    "actual_message": "<script>alert('bad')</script>",
                    "expected_match_count": 1,
                    "expected_matches": [
                        {
                            "category_id": "credentials",
                            "case_id": "api_key",
                            "variant": "synthetic-key",
                            "replacement": "[CREDENTIAL]",
                        }
                    ],
                    "error": "Processed message did not match expected output.",
                },
                {
                    "request_index": 3,
                    "record_id": "record-3",
                    "kind": "clean",
                    "status": "EXECUTION_FAILURE",
                    "http_status": 503,
                    "latency_ms": 3.0,
                    "expected_message": "clean",
                    "actual_message": None,
                    "expected_match_count": 0,
                    "expected_matches": [],
                    "error": "Request execution failed.",
                },
            ]
        generation_path = generated / "generation-manifest.json"
        comparison_path = generated / "comparison.jsonl"
        generation_path.write_text(json.dumps(generation))
        comparison_path.write_text(
            "".join(json.dumps(row) + "\n" for row in comparison_rows)
        )
        manifest = {
            "schema_version": 1,
            "run_id": run_directory.name,
            "run_type": "scale",
            "status": "comparison_completed",
            "created_at": "2026-07-19T12:00:00Z",
            "updated_at": "2026-07-19T12:01:00Z",
            "configuration": {"snapshot": "config/workload.yaml"},
            "THEMIS_TOKEN": "must-never-appear",
            "artifacts": {
                "generation_manifest": {
                    "path": "generated/generation-manifest.json"
                },
                "comparison": {"path": "generated/comparison.jsonl"},
            },
            "stages": {
                "generation": {"status": "completed"},
                "policy": {
                    "status": "completed",
                    "target": "themis",
                    "policy_path": "generated/scale-policy.nol",
                    "response": {
                        "command_id": "cmd-1",
                        "message": "loaded",
                        "rules": 10,
                        "authorization": "Bearer must-never-appear",
                    },
                },
                "run": {
                    "status": "completed",
                    "requests_total": 3,
                    "requests_completed": 3,
                    "requests_failed": 1,
                    "total_runtime_seconds": 0.1,
                },
                "comparison": {"status": comparison_status},
                "reporting": {"status": "pending"},
            },
        }
        (run_directory / "manifest.json").write_text(json.dumps(manifest))
        return run_directory

    def test_missing_run_and_manifest_are_rejected(self) -> None:
        with self.assertRaises(ReportingError):
            report_run(self.root / "missing")
        empty_run = self.root / "empty"
        empty_run.mkdir()
        with self.assertRaises(ReportingError):
            report_run(empty_run)

    def test_incomplete_comparison_records_reporting_failure(self) -> None:
        run_directory = self.create_run(comparison_status="in_progress")
        with self.assertRaisesRegex(ReportingError, "has not completed"):
            report_run(run_directory)
        manifest = json.loads((run_directory / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "report_failed")
        self.assertEqual(manifest["stages"]["reporting"]["status"], "failed")

    def test_report_succeeds_with_validation_failures_and_updates_manifest(self) -> None:
        run_directory = self.create_run()
        manifest = report_run(run_directory)
        report_path = run_directory / "reports/validation-report.html"

        self.assertTrue(report_path.is_file())
        stage = manifest["stages"]["reporting"]
        self.assertEqual(stage["status"], "completed")
        self.assertEqual(stage["records_total"], 3)
        self.assertEqual(stage["records_passed"], 1)
        self.assertEqual(stage["records_failed"], 2)
        self.assertEqual(manifest["status"], "report_completed")
        artifact = manifest["artifacts"]["report"]
        self.assertEqual(artifact["path"], "reports/validation-report.html")
        self.assertEqual(artifact["size_bytes"], report_path.stat().st_size)
        self.assertEqual(
            artifact["sha256"], hashlib.sha256(report_path.read_bytes()).hexdigest()
        )

    def test_html_is_escaped_and_contains_summary_and_failure_details(self) -> None:
        run_directory = self.create_run()
        report_run(run_directory)
        html = (run_directory / "reports/validation-report.html").read_text()

        self.assertIn("CONTENT_MISMATCH", html)
        self.assertIn("EXECUTION_FAILURE", html)
        self.assertIn("record-2", html)
        self.assertIn("credentials", html)
        self.assertIn("1</strong>Passed", html)
        self.assertIn("2</strong>Failed", html)
        self.assertIn("33.33%</strong>Pass rate", html)
        self.assertIn('class="metric metric-passed"', html)
        self.assertIn('class="metric metric-failed"', html)
        self.assertIn('class="metric status-fail"', html)
        self.assertIn("Harness runtime</th><td>0.100 seconds", html)
        self.assertIn("Harness throughput</th><td>30.00 req/sec", html)
        self.assertIn("Service latency from request evidence", html)
        self.assertIn("average</th><td>2.000 ms", html)
        self.assertIn("p50</th><td>2.000 ms", html)
        self.assertIn(
            "End-to-end throughput includes validation harness overhead. "
            "Latency reflects observed request processing time.",
            html,
        )
        self.assertIn("&lt;script&gt;alert(&#x27;bad&#x27;)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert('bad')</script>", html)
        self.assertNotIn("must-never-appear", html)

    def test_zero_runtime_renders_safe_throughput(self) -> None:
        run_directory = self.create_run()
        manifest_path = run_directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["stages"]["run"]["total_runtime_seconds"] = 0
        manifest_path.write_text(json.dumps(manifest))

        report_run(run_directory)
        html = (run_directory / "reports/validation-report.html").read_text()
        self.assertIn("Harness runtime</th><td>0.000 seconds", html)
        self.assertIn("Harness throughput</th><td>0.00 req/sec", html)

    def test_pass_rate_status_classification(self) -> None:
        cases = (
            (99, 1, "99.00%", "status-pass"),
            (97, 3, "97.00%", "status-warning"),
            (94, 6, "94.00%", "status-fail"),
        )
        for passed, failed, formatted, status_class in cases:
            with self.subTest(status_class=status_class):
                rows = [
                    {
                        "status": "PASS" if index < passed else "CONTENT_MISMATCH",
                        "kind": "dirty",
                        "expected_match_count": 0,
                        "expected_matches": [],
                    }
                    for index in range(passed + failed)
                ]
                evidence = aggregate_evidence(
                    {"run_id": "classification-run", "stages": {}, "artifacts": {}},
                    {},
                    rows,
                )
                html = render_report_html(evidence)
                self.assertIn(
                    f'class="metric {status_class}"><strong>{formatted}</strong>',
                    html,
                )

    def test_functional_and_scale_generation_manifests_render(self) -> None:
        generation_manifests = (
            {
                "test_name": "functional-baseline",
                "seed": 42,
                "record_count": 3,
                "policy_rule_count": 2,
                "clean_record_count": 1,
                "dirty_record_count": 2,
                "expected_total_matches": 2,
            },
            {
                "generator_schema": "enterprise-dlp-scale",
                "workload_name": "enterprise-dlp",
                "seed": 42,
                "requested_records": 3,
                "realized_records": 3,
                "requested_rules": 5,
                "realized_rules": 5,
            },
        )
        for index, generation in enumerate(generation_manifests):
            with self.subTest(index=index):
                self.root = Path(self.temporary_directory.name) / str(index)
                self.root.mkdir()
                run_directory = self.create_run(generation=generation)
                report_run(run_directory)
                html = (run_directory / "reports/validation-report.html").read_text()
                self.assertIn(
                    generation.get("workload_name", generation.get("test_name")), html
                )

    def test_cli_prints_report_location(self) -> None:
        run_directory = self.create_run()
        output = StringIO()
        with redirect_stdout(output):
            exit_code = main(["report", "--run", str(run_directory)])
        self.assertEqual(exit_code, 0)
        self.assertIn("Validation report generated", output.getvalue())
        self.assertIn("reports/validation-report.html", output.getvalue())


if __name__ == "__main__":
    unittest.main()
