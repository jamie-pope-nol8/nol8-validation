"""Network-free tests for the Themis adapter's contract translation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import adapter  # noqa: E402


class DeriveActionTests(unittest.TestCase):
    def test_unchanged_text_is_keep(self) -> None:
        self.assertEqual(adapter.derive_action("hello", "hello"), "keep")

    def test_changed_text_is_mask(self) -> None:
        self.assertEqual(
            adapter.derive_action("ssn 123-45-6789", "ssn [PII:SSN]"), "mask"
        )

    def test_drop_sentinel_wins_over_mask(self) -> None:
        self.assertEqual(
            adapter.derive_action(
                "acct ACC-1", "acct [DROP]", drop_token="[DROP]"
            ),
            "drop",
        )

    def test_route_sentinel(self) -> None:
        self.assertEqual(
            adapter.derive_action(
                "confidential brief", "[ROUTE] brief", route_token="[ROUTE]"
            ),
            "route",
        )


class ResponseShapeTests(unittest.TestCase):
    def test_keep_returns_original_text(self) -> None:
        self.assertEqual(
            adapter.to_benchmark_response("keep me", "keep me"),
            {"action": "keep", "text": "keep me"},
        )

    def test_mask_returns_processed_text(self) -> None:
        self.assertEqual(
            adapter.to_benchmark_response("a 4111111111111111 b", "a [CARD] b"),
            {"action": "mask", "text": "a [CARD] b"},
        )

    def test_drop_returns_empty_text(self) -> None:
        self.assertEqual(
            adapter.to_benchmark_response(
                "x [DROP] y", "x [DROP] y", drop_token="[DROP]"
            ),
            {"action": "drop", "text": ""},
        )


class CallThemisTests(unittest.TestCase):
    def test_extracts_result_message_from_themis_envelope(self) -> None:
        envelope = {
            "jid": 1,
            "frameId": 1,
            "last": True,
            "result": {"message": "x [PII:PERSON_NAME] y"},
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                import json

                return json.dumps(envelope).encode("utf-8")

        with mock.patch("adapter.urllib.request.urlopen", return_value=FakeResponse()):
            processed = adapter.call_themis(
                "x John Smith y", endpoint="https://tenant/v1/process", token="t"
            )
        self.assertEqual(processed, "x [PII:PERSON_NAME] y")

    def test_unexpected_shape_raises(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"error": "nope"}'

        with mock.patch("adapter.urllib.request.urlopen", return_value=FakeResponse()):
            with self.assertRaises(ValueError):
                adapter.call_themis(
                    "x", endpoint="https://tenant/v1/process", token="t"
                )


if __name__ == "__main__":
    unittest.main()
