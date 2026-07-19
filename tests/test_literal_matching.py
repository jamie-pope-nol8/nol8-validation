"""Multi-pattern matching and overlap detection over documents."""
from __future__ import annotations

import unittest

from framework.policy.matching import (
    LiteralMatcher,
    Match,
    overlapping_matches,
    resolve_non_overlapping,
)


def found(literals: list[str], text: str) -> list[tuple[int, int, str]]:
    return [(m.start, m.end, m.literal) for m in LiteralMatcher(literals).find_all(text)]


class FindAllTests(unittest.TestCase):
    def test_single_literal(self) -> None:
        self.assertEqual(found(["BCD"], "aBCDe"), [(1, 4, "BCD")])

    def test_absent_literal(self) -> None:
        self.assertEqual(found(["ZZZ"], "aBCDe"), [])

    def test_repeated_occurrences(self) -> None:
        self.assertEqual(
            found(["ab"], "abXab"), [(0, 2, "ab"), (3, 5, "ab")]
        )

    def test_contained_literal_reported_at_every_position(self) -> None:
        # 'Chen' occurs inside 'Elena Chen'; both must be reported.
        result = found(["Elena Chen", "Chen"], "x Elena Chen y")
        self.assertIn((2, 12, "Elena Chen"), result)
        self.assertIn((8, 12, "Chen"), result)

    def test_disjoint_literals(self) -> None:
        self.assertEqual(
            found(["ONE", "SIX"], "a ONE b SIX c"),
            [(2, 5, "ONE"), (8, 11, "SIX")],
        )

    def test_adjacent_literals(self) -> None:
        self.assertEqual(
            found(["AAAA", "BBBB"], "x AAAABBBB y"),
            [(2, 6, "AAAA"), (6, 10, "BBBB")],
        )

    def test_overlapping_literals_both_found(self) -> None:
        # The ISSUE-003 partial-overlap case.
        self.assertEqual(
            found(["ABCD", "DEFG"], "x ABCDEFG y"),
            [(2, 6, "ABCD"), (5, 9, "DEFG")],
        )

    def test_empty_inputs(self) -> None:
        self.assertEqual(found([], "anything"), [])
        self.assertEqual(found(["ab"], ""), [])

    def test_unicode_literals(self) -> None:
        self.assertEqual(found(["café"], "a café b"), [(2, 6, "café")])

    def test_literal_count(self) -> None:
        self.assertEqual(len(LiteralMatcher(["a", "b", "a", ""])), 2)


class OverlapDetectionTests(unittest.TestCase):
    """Anchored to behaviour observed from Themis."""

    def detect(self, literals: list[str], text: str) -> int:
        return len(overlapping_matches(LiteralMatcher(literals).find_all(text)))

    def test_adjacent_is_not_overlap(self) -> None:
        # Themis rendered 'x AAAABBBB y' correctly.
        self.assertEqual(self.detect(["AAAA", "BBBB"], "x AAAABBBB y"), 0)

    def test_disjoint_is_not_overlap(self) -> None:
        self.assertEqual(
            self.detect(["ONE-TWO", "SIX-NINE"], "a ONE-TWO b SIX-NINE c"), 0
        )

    def test_partial_overlap_detected(self) -> None:
        # Themis corrupted this: 'x [P[Q] y'
        self.assertEqual(self.detect(["ABCD", "DEFG"], "x ABCDEFG y"), 1)

    def test_containment_overlap_detected(self) -> None:
        # Themis corrupted this: 'name: [PII:[PII:PERSON_NAM, done'
        self.assertEqual(
            self.detect(["Elena Chen 1327", "Elena Chen"],
                        "name: Elena Chen 1327, done"),
            1,
        )

    def test_literal_present_but_partner_absent_is_safe(self) -> None:
        self.assertEqual(self.detect(["ABCD", "ZZZZ"], "x ABCDEFG y"), 0)

    def test_three_way_overlap(self) -> None:
        self.assertEqual(self.detect(["ABC", "BCD", "CDE"], "ABCDE"), 3)


class ResolveTests(unittest.TestCase):
    def test_leftmost_longest_selection(self) -> None:
        matches = [Match(0, 4, "ABCD"), Match(3, 7, "DEFG")]
        self.assertEqual(
            [m.literal for m in resolve_non_overlapping(matches)], ["ABCD"]
        )

    def test_longer_match_wins_at_same_start(self) -> None:
        matches = [Match(0, 4, "ABCD"), Match(0, 2, "AB")]
        self.assertEqual(
            [m.literal for m in resolve_non_overlapping(matches)], ["ABCD"]
        )

    def test_adjacent_matches_both_selected(self) -> None:
        matches = [Match(0, 4, "AAAA"), Match(4, 8, "BBBB")]
        self.assertEqual(len(resolve_non_overlapping(matches)), 2)


class ScaleTests(unittest.TestCase):
    def test_large_catalog_scan_is_fast(self) -> None:
        # Guards the reason this exists: a per-rule scan over a realistic
        # catalog is too slow to run during generation.
        literals = [f"LITERAL-{index:06d}" for index in range(5000)]
        matcher = LiteralMatcher(literals)
        document = "filler " * 200 + "LITERAL-004242" + " tail" * 200
        for _ in range(50):
            matches = matcher.find_all(document)
        self.assertEqual([m.literal for m in matches], ["LITERAL-004242"])


if __name__ == "__main__":
    unittest.main()
