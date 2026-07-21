"""T5-2: an end-to-end pipeline test on real generated artifacts.

Every other stage test runs against hand-written fixtures, so schema drift
between stages - a field one stage writes and the next reads under a different
name or shape - is invisible. This drives generate -> policy -> run -> compare
-> report through the real stage functions on a real generated corpus, with only
the network faked (a "perfect engine" that returns each record's real expected
output). Any inter-stage schema mismatch surfaces as an exception here.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from framework.cli.main import (
    apply_policy_to_run,
    compare_run,
    generate_run,
    report_run,
    run_validation_corpus,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPOSITORY_ROOT / "config/workloads/customer-record-csv.yaml"


class EndToEndPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.runs_directory = Path(self.temporary_directory.name) / "runs"

    @staticmethod
    def _rows(path: Path) -> list[dict]:
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_full_pipeline_on_real_generated_artifacts(self) -> None:
        # 1. Generate - real artifacts and a real manifest, not a fixture.
        run_id, run_directory = generate_run(
            CONFIG,
            self.runs_directory,
            rule_count_override=16,
            record_count_override=8,
        )
        generated = run_directory / "generated"
        self.assertTrue((generated / "input.jsonl").is_file())
        self.assertTrue((generated / "expected.jsonl").is_file())

        input_rows = self._rows(generated / "input.jsonl")
        expected_rows = self._rows(generated / "expected.jsonl")
        self.assertEqual(len(input_rows), 8)

        # A perfect engine: return each record's real expected output. Keyed by
        # the input message, which is unique per record.
        expected_output_by_input = {
            inp["message"]: exp["expected_message"]
            for inp, exp in zip(input_rows, expected_rows, strict=True)
        }

        def fake_execute(target: str, payload: dict) -> dict:
            del target
            processed = expected_output_by_input[payload["message"]]
            return {
                "http_status": 200,
                "latency_ms": 11.0,
                "success": True,
                "response": {"message": processed},
            }

        # 2. Policy - real manifest update; only the network deploy is faked.
        deploy_response = (
            200,
            {
                "ok": True,
                "command_id": "cmd-e2e",
                "stage": "apollo",
                "message": "loaded 16 rule(s)",
                "error_code": None,
                "apollo_response": "OK reload_rules dispatched",
                "rules": 16,
            },
        )
        with patch("framework.cli.main.deploy_policy", return_value=deploy_response), patch(
            "framework.cli.main._policy_ledger_path",
            return_value=self.runs_directory / "policy-ledger.jsonl",
        ):
            policy_manifest = apply_policy_to_run(run_directory, "themis")
        self.assertEqual(policy_manifest["stages"]["policy"]["status"], "completed")

        # 3. Run - real output.jsonl written from the faked engine's responses.
        with patch("framework.cli.main.execute_request", side_effect=fake_execute):
            run_manifest = run_validation_corpus(
                run_directory, "themis", skip_preflight=True
            )
        run_stage = run_manifest["stages"]["run"]
        self.assertEqual(run_stage["requests_completed"], 8)
        self.assertEqual(run_stage["requests_failed"], 0)

        # 4. Compare - real comparison.jsonl. The engine returned exactly the
        # expected output, so every record must pass.
        compare_manifest = compare_run(run_directory)
        comparison = compare_manifest["stages"]["comparison"]
        self.assertEqual(comparison["records_total"], 8)
        self.assertEqual(comparison["records_passed"], 8)
        self.assertEqual(comparison.get("records_inconclusive", 0), 0)

        # 5. Report - reads the real comparison artifact and manifest.
        report_manifest = report_run(run_directory)
        report_path = run_directory / report_manifest["stages"]["reporting"]["output_path"]
        self.assertTrue(report_path.is_file())
        html = report_path.read_text()
        self.assertIn('<span class="status">PASS</span>', html)


if __name__ == "__main__":
    unittest.main()
