from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from framework.cli.main import (
    RunExecutionError,
    _LiveRunProgress,
    main,
    run_validation_corpus,
)


class ValidateRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def create_run(
        self,
        *,
        policy_status: str = "completed",
        include_corpus: bool = True,
        lines: list[str] | None = None,
        run_name: str = "20260718T031425123456Z",
    ) -> Path:
        run_directory = self.root / run_name
        generated = run_directory / "generated"
        generated.mkdir(parents=True)
        if lines is None:
            lines = [
                json.dumps({"record_id": "record-1", "message": "first"}),
                json.dumps({"record_id": "record-2", "message": "second"}),
                json.dumps({"record_id": "record-3", "message": "third"}),
            ]
        if include_corpus:
            (generated / "input.jsonl").write_text("\n".join(lines) + "\n")

        manifest = {
            "schema_version": 1,
            "run_id": run_directory.name,
            "status": "policy_deployed",
            "updated_at": "2026-07-18T03:14:25.123456Z",
            "artifacts": {"input": {"path": "generated/input.jsonl"}},
            "stages": {
                "generation": {"status": "completed"},
                "policy": {"status": policy_status},
                "execution": {"status": "pending"},
                "comparison": {"status": "pending"},
                "reporting": {"status": "pending"},
            },
        }
        (run_directory / "manifest.json").write_text(json.dumps(manifest))
        return run_directory

    def read_manifest(self, run_directory: Path) -> dict:
        return json.loads((run_directory / "manifest.json").read_text())

    def read_output(self, run_directory: Path) -> list[dict]:
        return [
            json.loads(line)
            for line in (run_directory / "generated/output.jsonl")
            .read_text()
            .splitlines()
        ]

    def test_missing_run_and_manifest_are_rejected(self) -> None:
        with self.assertRaisesRegex(RunExecutionError, "does not exist"):
            run_validation_corpus(self.root / "missing", "themis")

        empty_run = self.root / "empty"
        empty_run.mkdir()
        with self.assertRaisesRegex(RunExecutionError, "manifest does not exist"):
            run_validation_corpus(empty_run, "themis")

    @patch("framework.cli.main._check_run_target")
    @patch("framework.cli.main.execute_request")
    def test_successful_execution_preserves_order_and_counts(
        self, mocked_execute, mocked_check
    ) -> None:
        del mocked_check
        mocked_execute.side_effect = [
            {
                "http_status": 200,
                "latency_ms": 1.1,
                "success": True,
                "response": {"message": "processed-first"},
            },
            {
                "http_status": 200,
                "latency_ms": 2.2,
                "success": True,
                "response": {"message": "processed-second"},
            },
            {
                "http_status": 200,
                "latency_ms": 3.3,
                "success": True,
                "response": {"message": "processed-third"},
            },
        ]
        run_directory = self.create_run()

        manifest = run_validation_corpus(run_directory, "themis")
        output = self.read_output(run_directory)

        self.assertEqual([row["request_index"] for row in output], [1, 2, 3])
        self.assertEqual(
            [row["response"]["message"] for row in output],
            ["processed-first", "processed-second", "processed-third"],
        )
        self.assertEqual(
            set(output[0]),
            {"request_index", "http_status", "latency_ms", "success", "response"},
        )
        stage = manifest["stages"]["run"]
        self.assertEqual(stage["status"], "completed")
        self.assertEqual(stage["requests_total"], 3)
        self.assertEqual(stage["requests_completed"], 3)
        self.assertEqual(stage["requests_failed"], 0)
        self.assertEqual(stage["output_path"], "generated/output.jsonl")
        self.assertEqual(manifest["stages"]["comparison"], {"status": "pending"})

    @patch("framework.cli.main._check_run_target")
    @patch("framework.cli.main.execute_request")
    def test_partial_failures_do_not_stop_execution(
        self, mocked_execute, mocked_check
    ) -> None:
        del mocked_check
        mocked_execute.side_effect = [
            {"http_status": 200, "latency_ms": 1.0, "success": True, "response": {}},
            {"http_status": 500, "latency_ms": 2.0, "success": False, "response": None},
            {"http_status": 200, "latency_ms": 3.0, "success": True, "response": {}},
        ]
        run_directory = self.create_run()

        manifest = run_validation_corpus(run_directory, "themis")

        self.assertEqual(mocked_execute.call_count, 3)
        self.assertEqual(manifest["stages"]["run"]["requests_failed"], 1)
        self.assertEqual(len(self.read_output(run_directory)), 3)

    @patch("framework.cli.main._check_run_target")
    @patch("framework.cli.main.execute_request")
    def test_all_http_failures_are_recorded(
        self, mocked_execute, mocked_check
    ) -> None:
        del mocked_check
        mocked_execute.return_value = {
            "http_status": 503,
            "latency_ms": 4.0,
            "success": False,
            "response": None,
        }
        run_directory = self.create_run()

        manifest = run_validation_corpus(run_directory, "themis")

        self.assertEqual(mocked_execute.call_count, 3)
        self.assertEqual(manifest["stages"]["run"]["requests_completed"], 3)
        self.assertEqual(manifest["stages"]["run"]["requests_failed"], 3)

    @patch("framework.cli.main._check_run_target")
    @patch("framework.cli.main.execute_request")
    def test_network_failures_attempt_every_request_and_fail_stage(
        self, mocked_execute, mocked_check
    ) -> None:
        del mocked_check
        mocked_execute.side_effect = RunExecutionError("network", "unavailable")
        run_directory = self.create_run()

        with self.assertRaises(RunExecutionError):
            run_validation_corpus(run_directory, "themis")

        manifest = self.read_manifest(run_directory)
        self.assertEqual(mocked_execute.call_count, 3)
        self.assertEqual(manifest["stages"]["run"]["status"], "failed")
        self.assertEqual(manifest["stages"]["run"]["requests_completed"], 3)
        self.assertEqual(manifest["stages"]["run"]["requests_failed"], 3)
        self.assertEqual(len(self.read_output(run_directory)), 3)

    @patch("framework.cli.main._check_run_target")
    @patch("framework.cli.main.execute_request")
    def test_malformed_request_is_recorded_without_stopping(
        self, mocked_execute, mocked_check
    ) -> None:
        del mocked_check
        mocked_execute.return_value = {
            "http_status": 200,
            "latency_ms": 1.0,
            "success": True,
            "response": {},
        }
        run_directory = self.create_run(
            lines=[json.dumps({"message": "first"}), "not-json", json.dumps({"message": "third"})]
        )

        with self.assertRaises(RunExecutionError):
            run_validation_corpus(run_directory, "themis")

        output = self.read_output(run_directory)
        self.assertEqual(mocked_execute.call_count, 2)
        self.assertFalse(output[1]["success"])
        self.assertEqual([row["request_index"] for row in output], [1, 2, 3])

    def test_missing_and_failed_policy_stage_are_rejected(self) -> None:
        for index, status in enumerate(("pending", "failed"), start=1):
            with self.subTest(status=status):
                run_directory = self.create_run(
                    policy_status=status, run_name=f"policy-{index}"
                )
                with self.assertRaises(RunExecutionError):
                    run_validation_corpus(run_directory, "themis")
                manifest = self.read_manifest(run_directory)
                self.assertEqual(manifest["stages"]["run"]["status"], "failed")

    def test_missing_corpus_is_rejected_and_recorded(self) -> None:
        run_directory = self.create_run(include_corpus=False)
        with self.assertRaisesRegex(RunExecutionError, "corpus does not exist"):
            run_validation_corpus(run_directory, "themis")
        manifest = self.read_manifest(run_directory)
        self.assertEqual(manifest["stages"]["run"]["status"], "failed")

    @patch("framework.cli.main._check_run_target")
    def test_missing_endpoint_configuration_is_recorded(self, mocked_check) -> None:
        mocked_check.side_effect = RunExecutionError(
            "configuration", "Processing endpoint configuration is invalid."
        )
        run_directory = self.create_run()

        with self.assertRaises(RunExecutionError):
            run_validation_corpus(run_directory, "themis")

        manifest = self.read_manifest(run_directory)
        self.assertEqual(manifest["stages"]["run"]["status"], "failed")
        self.assertEqual(
            manifest["stages"]["run"]["error"]["category"], "configuration"
        )

    @patch("framework.cli.main._check_run_target")
    @patch("framework.cli.main.execute_request")
    def test_progress_callback_uses_configured_interval_and_completion(
        self, mocked_execute, mocked_check
    ) -> None:
        del mocked_check
        mocked_execute.return_value = {
            "http_status": 200,
            "latency_ms": 1.0,
            "success": True,
            "response": {"message": "processed"},
        }
        lines = [json.dumps({"message": f"record-{index}"}) for index in range(120)]
        run_directory = self.create_run(lines=lines)
        progress: list[tuple[int, int, int, int]] = []

        run_validation_corpus(
            run_directory,
            "themis",
            progress_callback=lambda *values: progress.append(values),
            progress_interval=40,
        )

        self.assertEqual(
            progress,
            [(40, 120, 40, 0), (80, 120, 80, 0), (120, 120, 120, 0)],
        )

    @patch("framework.cli.main._check_run_target")
    @patch("framework.cli.main.execute_request")
    def test_direct_run_is_quiet_without_callback(
        self, mocked_execute, mocked_check
    ) -> None:
        del mocked_check
        mocked_execute.return_value = {
            "http_status": 200,
            "latency_ms": 1.0,
            "success": True,
            "response": {"message": "processed"},
        }
        run_directory = self.create_run()
        stdout = StringIO()

        with redirect_stdout(stdout):
            run_validation_corpus(run_directory, "themis")

        self.assertEqual(stdout.getvalue(), "")

    @patch("framework.cli.main._check_run_target")
    @patch("framework.cli.main.execute_request")
    def test_progress_callback_does_not_change_execution_results(
        self, mocked_execute, mocked_check
    ) -> None:
        del mocked_check
        mocked_execute.return_value = {
            "http_status": 200,
            "latency_ms": 1.25,
            "success": True,
            "response": {"message": "processed"},
        }
        quiet_run = self.create_run(run_name="quiet-run")
        reported_run = self.create_run(run_name="reported-run")

        quiet_manifest = run_validation_corpus(quiet_run, "themis")
        reported_manifest = run_validation_corpus(
            reported_run,
            "themis",
            progress_callback=lambda *_values: None,
            progress_interval=2,
        )

        self.assertEqual(self.read_output(quiet_run), self.read_output(reported_run))
        for field in (
            "requests_total",
            "requests_completed",
            "requests_failed",
            "average_latency_ms",
            "output_path",
            "status",
        ):
            self.assertEqual(
                quiet_manifest["stages"]["run"][field],
                reported_manifest["stages"]["run"][field],
            )

    @patch("framework.cli.main._check_run_target")
    @patch("framework.cli.main.execute_request")
    def test_interrupted_execution_preserves_output_and_manifest_counters(
        self, mocked_execute, mocked_check
    ) -> None:
        del mocked_check
        mocked_execute.side_effect = [
            {
                "http_status": 200,
                "latency_ms": 1.0,
                "success": True,
                "response": {"message": "processed-first"},
            },
            {
                "http_status": 503,
                "latency_ms": 2.0,
                "success": False,
                "response": {"message": "service unavailable"},
            },
            KeyboardInterrupt(),
        ]
        run_directory = self.create_run()

        with self.assertRaises(KeyboardInterrupt):
            run_validation_corpus(run_directory, "themis")

        output = self.read_output(run_directory)
        manifest = self.read_manifest(run_directory)
        stage = manifest["stages"]["run"]
        self.assertEqual([row["request_index"] for row in output], [1, 2])
        self.assertEqual(stage["requests_total"], 3)
        self.assertEqual(stage["requests_completed"], 2)
        self.assertEqual(stage["requests_failed"], 1)
        self.assertEqual(stage["status"], "failed")
        self.assertEqual(stage["error"]["category"], "interrupted")
        self.assertEqual(manifest["status"], "run_failed")

    @patch("framework.cli.main.write_manifest_atomic")
    @patch("framework.cli.main._check_run_target")
    @patch("framework.cli.main.execute_request")
    def test_manifest_counters_are_updated_during_execution(
        self, mocked_execute, mocked_check, mocked_write_manifest
    ) -> None:
        del mocked_check
        mocked_execute.return_value = {
            "http_status": 200,
            "latency_ms": 1.0,
            "success": True,
            "response": {"message": "processed"},
        }
        run_directory = self.create_run()
        snapshots: list[dict] = []
        mocked_write_manifest.side_effect = lambda _path, manifest: snapshots.append(
            json.loads(json.dumps(manifest))
        )

        run_validation_corpus(run_directory, "themis")

        completed_values = [
            snapshot["stages"]["run"]["requests_completed"]
            for snapshot in snapshots
        ]
        self.assertIn(1, completed_values)
        self.assertIn(2, completed_values)
        self.assertIn(3, completed_values)

    @patch("framework.cli.main.time.perf_counter")
    def test_terminal_progress_renderer_updates_same_area_with_color_and_rate(
        self, mocked_clock
    ) -> None:
        mocked_clock.side_effect = [100.0, 110.0, 120.0]
        output = StringIO()
        progress = _LiveRunProgress()
        with redirect_stdout(output):
            progress(250, 1000, 250, 0)
            progress(500, 1000, 499, 1)

        rendered = output.getvalue()
        self.assertIn("[██████████------------------------------]", rendered)
        self.assertIn("250/1000", rendered)
        self.assertIn("Succeeded: 250", rendered)
        self.assertIn("Rate: 25.0 req/s", rendered)
        self.assertIn("\033[32m", rendered)
        self.assertIn("\033[31m", rendered)
        self.assertIn("\033[2A", rendered)
        self.assertIn("Failed: 1", rendered)

    @patch("framework.cli.main.run_validation_corpus")
    def test_cli_prints_v1_functional_run_summary(self, mocked_run) -> None:
        run_directory = self.create_run()
        output_rows = [
            {"latency_ms": 1.0},
            {"latency_ms": 2.0},
            {"latency_ms": 3.0},
        ]
        (run_directory / "generated/output.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in output_rows)
        )
        mocked_run.return_value = {
            "run_id": run_directory.name,
            "stages": {
                "run": {
                    "requests_total": 3,
                    "requests_completed": 3,
                    "requests_failed": 1,
                    "average_latency_ms": 2.0,
                    "total_runtime_seconds": 0.25,
                    "output_path": "generated/output.jsonl",
                }
            },
        }
        output = StringIO()

        with redirect_stdout(output):
            exit_code = main(["run", "--run", str(run_directory)])

        self.assertEqual(exit_code, 0)
        rendered = output.getvalue()
        for expected in (
            "Functional Run Summary",
            "Records processed:  3",
            "Requests succeeded: 2",
            "Requests failed:    1",
            "Total duration: 0.250 seconds",
            "Latency average: 2.000 ms",
            "Latency p50:     2.000 ms",
            "Latency p95:     2.900 ms",
            "Latency p99:     2.980 ms",
            "Output: generated/output.jsonl",
        ):
            self.assertIn(expected, rendered)


if __name__ == "__main__":
    unittest.main()
