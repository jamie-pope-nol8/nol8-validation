"""Replacement tokens must survive KB-001 truncation distinguishably.

Themis truncates replacements to 15 characters, and comparison normalises
expected values to match. Truncation is not injective, so two tokens sharing a
15-character prefix become indistinguishable and validation cannot tell whether
the runtime applied the correct rule.

Three [BUSINESS_TERMS:*] tokens previously collapsed to "[BUSINESS_TERMS",
covering 4,755 transformations in a qualification run that reported 100%.
"""
from __future__ import annotations

import unittest

from framework.workload.generate_scale_artifacts import (
    REPLACEMENT_TRUNCATION_LIMIT,
    ScaleRule,
    _assert_replacements_distinct_when_truncated,
    _replacement_token,
    supported_patterns,
)

CATEGORIES = (
    "business_terms",
    "credentials",
    "financial",
    "healthcare",
    "infrastructure",
    "pii",
)


def rule(replacement: str) -> ScaleRule:
    return ScaleRule(
        rule_id="rule-000001",
        category_id="test",
        pattern_id="test",
        variant="value",
        replacement=replacement,
    )


class TokenDistinctnessTests(unittest.TestCase):
    def test_every_category_and_pattern_pair_is_distinct_at_the_limit(self) -> None:
        seen: dict[str, str] = {}
        for category in CATEGORIES:
            for pattern in supported_patterns():
                token = _replacement_token(category, pattern)
                key = token[:REPLACEMENT_TRUNCATION_LIMIT]
                if key in seen and seen[key] != token:
                    self.fail(
                        f"{token} and {seen[key]} both truncate to {key!r}"
                    )
                seen[key] = token

    def test_business_terms_tokens_no_longer_collapse(self) -> None:
        tokens = [
            _replacement_token("business_terms", pattern)[
                :REPLACEMENT_TRUNCATION_LIMIT
            ]
            for pattern in ("contract_number", "customer_id", "support_case_id")
        ]
        self.assertEqual(len(tokens), len(set(tokens)))


class CatalogGuardTests(unittest.TestCase):
    def test_guard_accepts_distinct_tokens(self) -> None:
        _assert_replacements_distinct_when_truncated(
            [rule("[PII:PERSON_NAME]"), rule("[PII:PHONE_NUMBER]")]
        )

    def test_guard_rejects_colliding_tokens(self) -> None:
        with self.assertRaises(ValueError) as caught:
            _assert_replacements_distinct_when_truncated([
                rule("[BUSINESS_TERMS:CONTRACT_NUMBER]"),
                rule("[BUSINESS_TERMS:CUSTOMER_ID]"),
            ])
        self.assertIn("truncated", str(caught.exception))

    def test_guard_allows_repeated_identical_tokens(self) -> None:
        # Many rules legitimately share one replacement.
        _assert_replacements_distinct_when_truncated(
            [rule("[PII:PERSON_NAME]")] * 50
        )


if __name__ == "__main__":
    unittest.main()
