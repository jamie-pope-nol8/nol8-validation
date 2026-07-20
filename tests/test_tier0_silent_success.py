"""Regression guards against the framework reporting success falsely.

These cover the Tier 0 findings in docs/CODE_REVIEW_PLAN.md: conditions under
which the framework could report a passing result while nothing was actually
validated. Each test fails if the corresponding guard is removed.
"""
from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch

from framework.cli.main import RunExecutionError, execute_request
from framework.reporting.generate_report import aggregate_evidence, render_report_html


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["run-validation.sh"], returncode=returncode, stdout=stdout, stderr=""
    )


def _transport(payload: dict, returncode: int = 0) -> subprocess.CompletedProcess:
    return _completed(json.dumps(payload), returncode)


class ExecuteRequestSuccessContractTests(unittest.TestCase):
    """T0-1: a 2xx alone must not be recorded as success."""

    def run_with(self, completed: subprocess.CompletedProcess) -> dict:
        with patch("framework.cli.main.subprocess.run", return_value=completed):
            return execute_request("themis", {"message": "hello"})

    def test_processed_message_is_success(self) -> None:
        result = self.run_with(_transport({
            "http_status": 200,
            "latency_ms": 12.5,
            "response": {"message": "redacted"},
        }))
        self.assertTrue(result["success"])
        self.assertNotIn("error", result)

    def test_2xx_without_result_is_not_success(self) -> None:
        # Themis returning 200 with no processed message, e.g. no policy
        # loaded. Previously recorded as success with a null response.
        result = self.run_with(_transport({
            "http_status": 200,
            "latency_ms": 3.0,
            "response": None,
        }))
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["category"], "invalid_response")

    def test_2xx_with_non_string_message_is_not_success(self) -> None:
        result = self.run_with(_transport({
            "http_status": 200,
            "latency_ms": 3.0,
            "response": {"message": None},
        }))
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["category"], "invalid_response")

    def test_non_2xx_is_not_success_and_is_categorised(self) -> None:
        result = self.run_with(_transport({
            "http_status": 500,
            "latency_ms": 1.0,
            "response": {"message": "irrelevant"},
        }))
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["category"], "http_status")
        self.assertIn("500", result["error"]["message"])


class TransportExitClassificationTests(unittest.TestCase):
    """T0-4: every transport failure carries an error category."""

    def run_with(self, returncode: int) -> dict:
        completed = _completed("", returncode)
        with patch("framework.cli.main.subprocess.run", return_value=completed):
            return execute_request("themis", {"message": "hello"})

    def test_configuration_failure_aborts_the_run(self) -> None:
        with self.assertRaises(RunExecutionError) as caught:
            self.run_with(2)
        self.assertEqual(caught.exception.category, "configuration")

    def test_network_failure_aborts_the_run(self) -> None:
        with self.assertRaises(RunExecutionError) as caught:
            self.run_with(5)
        self.assertEqual(caught.exception.category, "network")

    def test_rejected_payload_is_recorded_per_request(self) -> None:
        result = self.run_with(3)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["category"], "malformed_request")

    def test_unusable_response_is_recorded_per_request(self) -> None:
        result = self.run_with(6)
        self.assertFalse(result["success"])
        self.assertEqual(result["error"]["category"], "transport")

    def test_unknown_exit_code_still_carries_an_error(self) -> None:
        # The previous implementation returned a row with no error key at all
        # for any exit code it did not recognise.
        result = self.run_with(99)
        self.assertFalse(result["success"])
        self.assertIn("error", result)
        self.assertIn("99", result["error"]["message"])


def _manifest() -> dict:
    return {
        "run_id": "20260719T000000000000Z",
        "run_type": "scale",
        "stages": {
            "generation": {"status": "completed"},
            "policy": {"status": "completed", "target": "themis"},
            "comparison": {"status": "completed"},
        },
        "artifacts": {},
    }


def _render(rows: list[dict]) -> str:
    return render_report_html(aggregate_evidence(_manifest(), {}, rows))


def _passing(index: int) -> dict:
    return {
        "record_id": f"r{index}",
        "status": "PASS",
        "kind": "dirty",
        "latency_ms": 1.0,
        "expected_match_count": 1,
    }


def _failing(index: int) -> dict:
    return {
        "record_id": f"f{index}",
        "status": "CONTENT_MISMATCH",
        "kind": "dirty",
        "latency_ms": 1.0,
        "expected_match_count": 1,
        "expected_message": "a",
        "actual_message": "b",
    }


def _inconclusive(index: int) -> dict:
    return {
        "record_id": f"i{index}",
        "status": "INCONCLUSIVE",
        "kind": "dirty",
        "latency_ms": 1.0,
        "expected_match_count": 1,
    }


class InconclusiveReportTests(unittest.TestCase):
    """A record the comparison could not confirm is neither pass nor failure."""

    def _render_with_collisions(self, rows: list[dict]) -> str:
        manifest = _manifest()
        manifest["stages"]["comparison"] = {
            "status": "completed",
            "replacement_max_length": 15,
            "replacement_collisions": {
                "count": 1,
                "examples": {
                    "[FINANCIAL:CRED": [
                        "[FINANCIAL:CREDIT_CARD_NUMBER]",
                        "[FINANCIAL:CREDIT_ROUTING]",
                    ]
                },
                "truncated": False,
            },
        }
        return render_report_html(aggregate_evidence(manifest, {}, rows))

    def test_inconclusive_records_are_not_counted_as_passes(self) -> None:
        evidence = aggregate_evidence(_manifest(), {}, [_passing(1), _inconclusive(1)])
        self.assertEqual(evidence["passed"], 1)
        self.assertEqual(evidence["inconclusive"], 1)
        self.assertEqual(evidence["failed"], 0)

    def test_inconclusive_records_are_not_counted_as_failures(self) -> None:
        # Blaming the product for a limit of the comparison would be as wrong
        # as certifying a pass that was never established.
        evidence = aggregate_evidence(_manifest(), {}, [_inconclusive(1)])
        self.assertEqual(evidence["failed"], 0)
        self.assertEqual(evidence["failures"], [])

    def test_zero_failures_with_inconclusive_records_is_not_a_pass(self) -> None:
        html = self._render_with_collisions([_passing(1), _inconclusive(1)])
        self.assertIn('<span class="status">INCONCLUSIVE</span>', html)
        self.assertNotIn('<span class="status">PASS</span>', html)
        self.assertNotIn('class="metric status-pass"', html)

    def test_report_names_the_colliding_tokens(self) -> None:
        html = self._render_with_collisions([_inconclusive(1)])
        self.assertIn("could not be confirmed as passes", html)
        self.assertIn("[FINANCIAL:CRED", html)
        self.assertIn("[FINANCIAL:CREDIT_CARD_NUMBER]", html)
        self.assertIn("not an observed product failure", html)

    def test_a_real_failure_outranks_inconclusive(self) -> None:
        html = self._render_with_collisions([_inconclusive(1), _failing(1)])
        self.assertIn('<span class="status">FAIL</span>', html)

    def test_no_note_when_nothing_is_inconclusive(self) -> None:
        html = _render([_passing(1)])
        self.assertNotIn("could not be confirmed as passes", html)


class ReportHonestyTests(unittest.TestCase):
    """T0-2 and T0-3: the report must not overstate the outcome."""

    def test_empty_comparison_is_inconclusive_not_pass(self) -> None:
        html = _render([])
        self.assertIn("INCONCLUSIVE", html)
        self.assertIn("does not establish", html)
        self.assertNotIn('<span class="status">PASS</span>', html)

    def test_all_passing_is_a_pass(self) -> None:
        html = _render([_passing(1)])
        self.assertIn('<span class="status">PASS</span>', html)
        self.assertIn("<strong>100.00%</strong>", html)

    def test_pass_rate_never_displays_100_percent_with_failures(self) -> None:
        # 9999 passing, 1 failing rounds to 100.00% at two decimal places.
        rows = [_passing(i) for i in range(9999)] + [_failing(0)]
        html = _render(rows)
        self.assertIn('<span class="status">FAIL</span>', html)
        self.assertNotIn("<strong>100.00%</strong>", html)

    def test_any_failure_is_not_styled_as_passing(self) -> None:
        html = _render([_passing(1), _failing(1)])
        self.assertNotIn('class="metric status-pass"', html)


if __name__ == "__main__":
    unittest.main()
