"""FW-6: failing reports are grouped by signature and rendered compactly.

Before FW-6 the report emitted one <article> per failing row carrying the FULL
expected and actual messages inline - at scale, megabytes of undifferentiated
blocks. These tests pin the new behaviour: failures are classified by an
explainable diff-shape signature, grouped, and shown as a summary table plus a
capped number of compact representatives. They are written to FAIL against the
old full-dump renderer (see test_grouping_is_non_vacuous).
"""

from __future__ import annotations

import unittest

from framework.reporting.generate_report import (
    aggregate_evidence,
    classify_failure,
    group_failures,
    render_failure_section,
    render_report_html,
)


def _mismatch_row(record_id: str, expected: str, actual: str, **overrides) -> dict:
    row = {
        "request_index": 1,
        "record_id": record_id,
        "kind": "dirty",
        "status": "CONTENT_MISMATCH",
        "http_status": 200,
        "latency_ms": 1.0,
        "expected_message": expected,
        "actual_message": actual,
        "expected_match_count": 1,
        "expected_matches": [
            {
                "category_id": "pii",
                "case_id": "person_name",
                "variant": "Jordan Reed",
                "replacement": "[PII:PERSON_NAME]",
            }
        ],
        "error": "Processed message did not match expected output.",
    }
    row.update(overrides)
    return row


# An ISSUE-003-shaped failure, modelled on artifacts/evidence/
# issue-003-failure-sample.jsonl: a replacement token is written at a displaced
# start offset, so the actual output has an extra fragment inserted and is
# longer than expected, diverging mid-record.
_ISSUE_003_EXPECTED = (
    "000071,customer_record,2100-01-01T00:00:00Z,CUST-516774,"
    "[PII:PERSON_NAM,taylor.hayes103@example.test,+1-704-857-9914,"
    "6449 Maple Avenue,closed"
)
# The displaced start offset writes the token early, leaving a "[PII:" fragment
# before the real token: same tail, five extra bytes (byte_delta 5 in the real
# sample), so the actual output is genuinely longer than expected.
_ISSUE_003_ACTUAL = (
    "000071,customer_record,2100-01-01T00:00:00Z,CUST-516774,"
    "[PII:[PII:PERSON_NAM,taylor.hayes103@example.test,+1-704-857-9914,"
    "6449 Maple Avenue,closed"
)


class ClassifyFailureTests(unittest.TestCase):
    def test_truncation_prefix_shape(self) -> None:
        row = _mismatch_row("r", "[FINANCIAL:CREDIT_CARD_NUMBER]", "[FINANCIAL:CRED")
        self.assertEqual(
            classify_failure(row),
            "Actual is a prefix of expected (consistent with truncation)",
        )

    def test_issue_003_shape_is_actual_longer(self) -> None:
        row = _mismatch_row("r", _ISSUE_003_EXPECTED, _ISSUE_003_ACTUAL)
        # Extra fragment inserted mid-string: longer, and NOT a clean extension.
        self.assertEqual(classify_failure(row), "Actual longer than expected")

    def test_execution_failure_subkeys_by_http_status(self) -> None:
        row = {
            "status": "EXECUTION_FAILURE",
            "http_status": 503,
            "record_id": "r",
            "expected_message": "x",
            "actual_message": None,
        }
        self.assertEqual(classify_failure(row), "Execution failure (HTTP 503)")

    def test_execution_failure_without_status(self) -> None:
        row = {
            "status": "EXECUTION_FAILURE",
            "http_status": None,
            "record_id": "r",
        }
        self.assertEqual(classify_failure(row), "Execution failure (no response)")

    def test_same_length_content_differs(self) -> None:
        row = _mismatch_row("r", "AAAAA", "AABAA")
        self.assertEqual(classify_failure(row), "Same length, content differs")

    def test_missing_messages_are_labelled_not_crashed(self) -> None:
        row = _mismatch_row("r", None, None)
        self.assertEqual(classify_failure(row), "Content mismatch (message unavailable)")


class GroupFailuresTests(unittest.TestCase):
    def test_grouped_and_ordered_by_count_then_name(self) -> None:
        failures = (
            [_mismatch_row(f"prefix-{i}", "[LONG_TOKEN_VALUE]", "[LONG") for i in range(3)]
            + [_mismatch_row(f"samelen-{i}", "AAAA", "AABA") for i in range(2)]
            + [_mismatch_row("longer-0", _ISSUE_003_EXPECTED, _ISSUE_003_ACTUAL)]
        )
        groups = group_failures(failures)
        signatures = [signature for signature, _ in groups]
        counts = [len(rows) for _, rows in groups]
        # Largest group first.
        self.assertEqual(counts, [3, 2, 1])
        self.assertEqual(
            signatures[0],
            "Actual is a prefix of expected (consistent with truncation)",
        )


class RenderFailureSectionTests(unittest.TestCase):
    def test_summary_table_and_capping_with_stated_drop(self) -> None:
        failures = [
            _mismatch_row(f"document-{i:06d}", "[LONG_TOKEN_VALUE]", "[LONG")
            for i in range(187)
        ]
        html = render_failure_section(failures)

        # A summary line naming the total and the number of signatures.
        self.assertIn("187 failing record(s) across 1 signature(s)", html)
        # Summary table header.
        self.assertIn("<th>Signature</th>", html)
        self.assertIn("<th>Count</th>", html)
        # Capping is explicit, never silent.
        self.assertIn("Showing 3 of 187 in this group", html)
        self.assertIn("184 further record ID(s)", html)

    def test_only_representatives_are_dumped_in_full(self) -> None:
        # 187 large messages; only 3 representatives may carry a full <pre> dump.
        big = "X" * 5000
        failures = [
            _mismatch_row(f"document-{i:06d}", big + "-expected", big + "-actual")
            for i in range(187)
        ]
        html = render_failure_section(failures)
        # The full-message <details> block appears once per representative only.
        self.assertEqual(html.count("Full expected and actual messages"), 3)
        # The 5000-char body must not be dumped 187 times.
        self.assertLessEqual(html.count(big), 6)  # <=2 per representative (exp+act)

    def test_compact_diff_anchors_on_first_divergence(self) -> None:
        failures = [_mismatch_row("document-000071", _ISSUE_003_EXPECTED, _ISSUE_003_ACTUAL)]
        html = render_failure_section(failures)
        self.assertIn("First difference at byte", html)
        self.assertIn("diff-expected", html)
        self.assertIn("diff-actual", html)

    def test_no_failures_message(self) -> None:
        self.assertEqual(render_failure_section([]), "<p>No comparison failures.</p>")

    def test_inconclusive_rows_never_reach_the_section(self) -> None:
        # aggregate_evidence excludes INCONCLUSIVE from failures; a report must
        # not present it as a product failure.
        rows = [
            {
                "status": "INCONCLUSIVE",
                "kind": "dirty",
                "record_id": "inconclusive-1",
                "expected_match_count": 0,
                "expected_matches": [],
                "expected_message": "x",
                "actual_message": "x",
            }
        ]
        evidence = aggregate_evidence({"run_id": "r", "stages": {}, "artifacts": {}}, {}, rows)
        self.assertEqual(evidence["failures"], [])
        self.assertNotIn("inconclusive-1", render_failure_section(evidence["failures"]))


class NonVacuousTests(unittest.TestCase):
    """Prove the new rendering differs from the old full-dump behaviour."""

    def test_grouping_is_non_vacuous(self) -> None:
        # 50 failing rows sharing one signature. The OLD renderer produced 50
        # <article> blocks; the new one produces a summary table plus exactly 3
        # representatives, and states that the rest were dropped.
        rows = [
            _mismatch_row(f"document-{i:06d}", "[LONG_TOKEN_VALUE]", "[LONG")
            for i in range(50)
        ]
        evidence = aggregate_evidence(
            {"run_id": "scale", "stages": {}, "artifacts": {}}, {}, rows
        )
        html = render_report_html(evidence)

        # Old behaviour would have emitted one <article class='failure'> per row.
        self.assertEqual(html.count("<article class='failure'>"), 3)
        # New behaviour: an explicit summary and drop statement the old renderer
        # never produced.
        self.assertIn("50 failing record(s) across 1 signature(s)", html)
        self.assertIn("Showing 3 of 50 in this group", html)
        # All 50 record IDs remain traceable (3 in full + 47 listed).
        for i in (0, 3, 49):
            self.assertIn(f"document-{i:06d}", html)


if __name__ == "__main__":
    unittest.main()
