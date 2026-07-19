"""Multi-pattern literal matching over documents.

The validation framework needs to answer two questions about a document that a
per-rule scan cannot answer efficiently:

1. Which catalog literals occur in it? Computing expected output from only the
   rules the generator *intended* to inject is wrong - unrelated generated
   values collide with catalog literals in practice.
2. Do any of those matches overlap? Overlapping matches trigger ISSUE-003, so
   a corpus containing them cannot produce trustworthy validation results.

A naive scan is O(rules x documents): 5,000 rules over 10,000 documents is 50
million substring searches. Aho-Corasick finds every occurrence of every
literal in a single pass over each document, after one build of the automaton.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Match:
    """One literal occurrence, as a half-open byte range [start, end)."""

    start: int
    end: int
    literal: str

    @property
    def length(self) -> int:
        return self.end - self.start


class LiteralMatcher:
    """Aho-Corasick automaton over a fixed set of literals.

    Build once per catalog, then scan many documents.
    """

    __slots__ = ("_goto", "_fail", "_output", "_literal_count")

    def __init__(self, literals: Iterable[str]) -> None:
        # Node 0 is the root. _goto[node] maps character -> node.
        self._goto: list[dict[str, int]] = [{}]
        # Literals terminating at each node.
        self._output: list[list[str]] = [[]]
        unique = {literal for literal in literals if literal}
        self._literal_count = len(unique)

        for literal in sorted(unique):
            node = 0
            for character in literal:
                next_node = self._goto[node].get(character)
                if next_node is None:
                    next_node = len(self._goto)
                    self._goto.append({})
                    self._output.append([])
                    self._goto[node][character] = next_node
                node = next_node
            self._output[node].append(literal)

        self._fail: list[int] = [0] * len(self._goto)
        queue: deque[int] = deque()
        for node in self._goto[0].values():
            queue.append(node)
        while queue:
            node = queue.popleft()
            for character, target in self._goto[node].items():
                queue.append(target)
                fallback = self._fail[node]
                while fallback and character not in self._goto[fallback]:
                    fallback = self._fail[fallback]
                self._fail[target] = (
                    self._goto[fallback].get(character, 0)
                    if fallback or character in self._goto[0]
                    else 0
                )
                if self._fail[target] == target:
                    self._fail[target] = 0
                # Inherit outputs so a literal contained in another is still
                # reported at every position where it occurs.
                self._output[target].extend(self._output[self._fail[target]])

    def __len__(self) -> int:
        return self._literal_count

    def find_all(self, text: str) -> list[Match]:
        """Every occurrence of every literal, ordered by start then length."""
        matches: list[Match] = []
        node = 0
        for index, character in enumerate(text):
            while node and character not in self._goto[node]:
                node = self._fail[node]
            node = self._goto[node].get(character, 0)
            if self._output[node]:
                end = index + 1
                for literal in self._output[node]:
                    matches.append(Match(end - len(literal), end, literal))
        matches.sort(key=lambda match: (match.start, -match.length))
        return matches


def overlapping_matches(matches: Sequence[Match]) -> list[tuple[Match, Match]]:
    """Pairs of matches that share at least one character.

    Adjacency is not overlap: a match ending at index n and another starting at
    index n share no characters, and Themis renders that correctly.
    """
    ordered = sorted(matches, key=lambda match: (match.start, match.end))
    pairs: list[tuple[Match, Match]] = []
    for index, current in enumerate(ordered):
        for other in ordered[index + 1:]:
            if other.start >= current.end:
                break  # ordered by start, so nothing later can overlap either
            pairs.append((current, other))
    return pairs


def resolve_non_overlapping(matches: Sequence[Match]) -> list[Match]:
    """Leftmost-longest selection of non-overlapping matches.

    Used to compute expected output. Where matches do not overlap, Themis was
    observed to produce exactly this result. Where they DO overlap, Themis
    corrupts the output (ISSUE-003) and no expected value is correct - callers
    should treat such documents as unusable rather than compare against them.
    """
    selected: list[Match] = []
    cursor = 0
    for match in sorted(matches, key=lambda item: (item.start, -item.length)):
        if match.start < cursor:
            continue
        selected.append(match)
        cursor = match.end
    return selected
