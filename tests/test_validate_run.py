from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from framework.cli.main import RunExecutionError, run_validation_corpus


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


if __name__ == "__main__":
    unittest.main()
