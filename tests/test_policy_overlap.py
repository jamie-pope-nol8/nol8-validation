"""Detection of literal pairs that can produce overlapping matches (ISSUE-003).

The expectations below are anchored to behaviour observed directly from Themis,
not to the implementation. Cases marked CORRUPT were reproduced with curl; the
detector must flag every one of them and must not flag the correct cases.
"""
from __future__ import annotations

import unittest

from framework.policy.overlap import find_overlapping_pairs, summarize_overlaps


def kinds(literals: list[str]) -> set[str]:
    return {pair.kind for pair in find_overlapping_pairs(literals)}


def count(literals: list[str]) -> int:
    return len(find_overlapping_pairs(literals))


class ObservedCorruptionTests(unittest.TestCase):
    """Pairs Themis was observed to corrupt must be detected."""

    def test_containment_prefix(self) -> None:
        # 'name: Elena Chen 1327, done' -> 'name: [PII:[PII:PERSON_NAM, done'
        self.assertEqual(kinds(["Elena Chen 1327", "Elena Chen"]),
                         {"containment"})

    def test_overlap_by_one_character(self) -> None:
        # 'x ABCDEFG y' -> 'x [P[Q] y'
        self.assertEqual(kinds(["ABCD", "DEFG"]), {"suffix_prefix"})

    def test_overlap_by_three_characters(self) -> None:
        # 'x ABCDEFGHI y' -> 'x [Q] y', destroying 'AB'
        self.assertEqual(kinds(["ABCDEF", "DEFGHI"]), {"suffix_prefix"})

    def test_realistic_suffix_prefix_pair(self) -> None:
        # Neither literal contains the other; a containment-only check misses
        # this entirely.
        pairs = find_overlapping_pairs(["ACCT-1234", "1234-5678"])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].kind, "suffix_prefix")

    def test_realistic_containment_pair(self) -> None:
        pairs = find_overlapping_pairs(["Acme Corp", "Acme Corporation"])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].kind, "containment")


class ObservedCorrectTests(unittest.TestCase):
    """Pairs Themis handled correctly must NOT be reported."""

    def test_adjacent_matches_are_not_overlapping(self) -> None:
        # 'x AAAABBBB y' -> 'x [P][Q] y' rendered correctly.
        self.assertEqual(count(["AAAA", "BBBB"]), 0)

    def test_disjoint_literals(self) -> None:
        self.assertEqual(count(["ONE-TWO", "SIX-NINE"]), 0)

    def test_single_literal_never_overlaps_itself(self) -> None:
        self.assertEqual(count(["Elena Chen 1327"]), 0)

    def test_shared_interior_substring_is_not_an_overlap(self) -> None:
        # 'XmidY' and 'ZmidW' share 'mid' but no suffix of one is a prefix of
        # the other, so their matches cannot overlap.
        self.assertEqual(count(["XmidY", "ZmidW"]), 0)


class DetectorSemanticsTests(unittest.TestCase):
    def test_join_detected_in_either_direction(self) -> None:
        # 'AB' + 'BC' joins as 'ABC'; the reverse ordering joins as 'BCAB'.
        self.assertEqual(count(["AB", "BC"]), 1)
        self.assertEqual(count(["BC", "AB"]), 1)

    def test_duplicate_literals_collapse(self) -> None:
        self.assertEqual(count(["SAME", "SAME"]), 0)

    def test_empty_literals_ignored(self) -> None:
        self.assertEqual(count(["", "ABCD"]), 0)

    def test_results_are_deterministic(self) -> None:
        literals = ["DEFG", "ABCD", "Acme Corp", "Acme Corporation"]
        first = find_overlapping_pairs(literals)
        second = find_overlapping_pairs(list(reversed(literals)))
        self.assertEqual(first, second)

    def test_containment_takes_precedence_over_join(self) -> None:
        # 'ABA' inside 'XABAX' is containment; do not double-report.
        pairs = find_overlapping_pairs(["ABA", "XABAX"])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].kind, "containment")


class SummaryTests(unittest.TestCase):
    def test_clean_catalog_summary(self) -> None:
        self.assertIn("No overlapping", summarize_overlaps([]))

    def test_summary_counts_both_classes(self) -> None:
        pairs = find_overlapping_pairs(
            ["Acme Corp", "Acme Corporation", "ACCT-1234", "1234-5678"]
        )
        summary = summarize_overlaps(pairs)
        self.assertIn("containment", summary)
        self.assertIn("suffix/prefix", summary)
        self.assertIn("ISSUE-003", summary)

    def test_summary_truncates_long_lists(self) -> None:
        literals = [f"AB{index}" for index in range(40)] + ["ZAB"]
        summary = summarize_overlaps(find_overlapping_pairs(literals), limit=3)
        self.assertIn("more", summary)


if __name__ == "__main__":
    unittest.main()
