"""Tests for the starter-policy generator's safety guards."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_policy  # noqa: E402


class CheckSafeTests(unittest.TestCase):
    def test_accepts_a_clean_policy(self) -> None:
        build_policy.check_safe(
            [
                ("[DENIED]", "denied", ["Red Flag Logistics", "Shadow Harbor"]),
                ("[CARD]", "cards", ["4111 1111 1111 1111"]),
            ]
        )  # no raise

    def test_rejects_token_over_15_chars(self) -> None:
        with self.assertRaisesRegex(ValueError, "truncate"):
            build_policy.check_safe([("[COMPROMISED_ACCOUNT]", "x", ["A"])])

    def test_rejects_duplicate_tokens(self) -> None:
        with self.assertRaisesRegex(ValueError, "distinct"):
            build_policy.check_safe(
                [("[X]", "a", ["one"]), ("[X]", "b", ["two"])]
            )

    def test_rejects_duplicate_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            build_policy.check_safe(
                [("[A]", "a", ["dup"]), ("[B]", "b", ["dup"])]
            )

    def test_rejects_contained_literals_issue_004(self) -> None:
        # "Redwood" inside "Redwood Identity" would overlap -> corruption.
        with self.assertRaisesRegex(ValueError, "ISSUE-004"):
            build_policy.check_safe(
                [("[PROJECT]", "p", ["Redwood Identity", "Redwood"])]
            )


class BuildNolTests(unittest.TestCase):
    def test_emits_one_rule_per_value_with_token(self) -> None:
        text = build_policy.build_nol(
            [("[DENIED]", "Denied entities", ["Red Flag Logistics"])]
        )
        self.assertIn('"Red Flag Logistics" -> "[DENIED]";', text)
        self.assertIn("# Denied entities -> [DENIED]", text)

    def test_real_value_lists_generate_a_safe_policy(self) -> None:
        # The shipped values/*.txt must pass the guards and produce rules.
        categories = build_policy.load_categories(build_policy.VALUES_DIR)
        self.assertTrue(categories, "no value lists found")
        build_policy.check_safe(categories)  # no raise
        text = build_policy.build_nol(categories)
        self.assertIn("->", text)


if __name__ == "__main__":
    unittest.main()
