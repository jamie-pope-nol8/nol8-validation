"""Detection of policy literals that can produce overlapping matches.

Two rules whose matches share input bytes trigger ISSUE-003: the Themis runtime
computes the wrong match start offset and destroys content preceding the match,
silently and with no error signal.

Whether two matches actually overlap depends on the input, but whether they
*can* is a static property of the literal pair:

- containment - one literal contains the other, so wherever the longer matches
  the shorter also matches inside it;
- suffix/prefix - a non-empty proper suffix of one equals a proper prefix of
  the other, so a document containing the join produces overlapping matches.

The second class is easy to miss. `"ACCT-1234"` and `"1234-5678"` have no
containment relationship yet corrupt `ACCT-1234-5678`.

Adjacent matches that do not share bytes are correct and are not reported.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class OverlapPair:
    """Two literals that can produce overlapping matches."""

    left: str
    right: str
    kind: str  # "containment" | "suffix_prefix"
    detail: str

    def describe(self) -> str:
        return f"{self.left!r} / {self.right!r} - {self.detail}"


def _longest_join(left: str, right: str) -> str:
    """Longest non-empty proper suffix of `left` that is a proper prefix of `right`."""
    limit = min(len(left), len(right)) - 1
    for size in range(limit, 0, -1):
        if left[-size:] == right[:size]:
            return left[-size:]
    return ""


def find_overlapping_pairs(literals: Iterable[str]) -> list[OverlapPair]:
    """Return every literal pair that can produce overlapping matches.

    Deterministic: results are ordered by the sorted literal values so a
    generation report is stable across runs.
    """
    unique = sorted({literal for literal in literals if literal})
    pairs: list[OverlapPair] = []

    for index, left in enumerate(unique):
        for right in unique[index + 1:]:
            if left in right:
                pairs.append(OverlapPair(
                    left, right, "containment",
                    f"{left!r} occurs inside {right!r}",
                ))
                continue
            if right in left:
                pairs.append(OverlapPair(
                    left, right, "containment",
                    f"{right!r} occurs inside {left!r}",
                ))
                continue
            # Both directions matter: "AB"+"BC" joins as ABC, and the reverse
            # pair joins as BCAB. Either ordering can appear in a document.
            join = _longest_join(left, right) or _longest_join(right, left)
            if join:
                pairs.append(OverlapPair(
                    left, right, "suffix_prefix",
                    f"share the join {join!r}",
                ))

    return pairs


def find_contained_literals(literals: Iterable[str]) -> list[tuple[str, str]]:
    """Literal pairs where one occurs inside the other, as (inner, outer).

    Containment is the class that actually bites: wherever the outer literal
    appears the inner one necessarily matches inside it, so the overlap is
    unavoidable rather than dependent on a particular document.

    The suffix/prefix class in `find_overlapping_pairs` is theoretically real
    but requires the two literals to abut in the input. On generated corpora it
    never occurs, and reporting it drowns the signal - it produced 1.28 million
    pairs on the 5,000 rule catalog.

    Uses one Aho-Corasick pass rather than comparing every pair.
    """
    from framework.policy.matching import LiteralMatcher

    unique = sorted({literal for literal in literals if literal})
    matcher = LiteralMatcher(unique)
    contained: list[tuple[str, str]] = []
    for literal in unique:
        for match in matcher.find_all(literal):
            if match.literal != literal:
                contained.append((match.literal, literal))
    return contained


def summarize_overlaps(pairs: Sequence[OverlapPair], limit: int = 10) -> str:
    """Human-readable summary for generation output and reports."""
    if not pairs:
        return "No overlapping literal pairs detected."

    containment = sum(1 for pair in pairs if pair.kind == "containment")
    suffix_prefix = len(pairs) - containment

    lines = [
        f"{len(pairs)} literal pair(s) can produce overlapping matches "
        f"({containment} containment, {suffix_prefix} suffix/prefix).",
        "Overlapping matches corrupt Themis output silently - see ISSUE-003.",
    ]
    for pair in pairs[:limit]:
        lines.append(f"  {pair.describe()}")
    if len(pairs) > limit:
        lines.append(f"  ... and {len(pairs) - limit} more")
    return "\n".join(lines)
