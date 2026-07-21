#!/usr/bin/env python3
"""Build the Data Point 2 boundary policy from the pre/post-inference reference lists.

Data Point 2 governs a model boundary: what may reach the model (pre-inference) and
what may leave it (post-inference). The controls are literal, so the same `.nol`
policy runs on both engines (NOL8/Themis and RE2/Aergia) exactly like DP1.

Each reference list maps every literal value to a short SENTINEL token. The engine
only does literal replacement; the benchmark harness/adapter reads which sentinel
appears and derives the governance action:

  list                     sentinel        action        stage
  ----------------------   -------------   -----------   ------------
  block_phrases            [BLOCK]         block          pre
  route_phrases            [ROUTE]         route          pre
  flagged_customers        [ROUTE]         route          pre
  denied_entities          [ROUTE]         route          pre
  payment_cards            [MASK_CARD]     mask           pre + post
  account_ids             [MASK_ACCT]     mask           pre + post
  internal_projects        [TAG_INT]       tag            pre
  output_block_phrases     [BLOCK_OUT]     block (output)  post
  output_tag_phrases       [TAG_PRIV]      tag (output)    post

One policy carries every rule; the engine is called once per control point, and the
harness interprets sentinels per stage (step 2). Sentinels are <= 15 chars so the
runtime's 15-char truncation (ISSUE-005) never garbles them, and the generator
refuses containing literals (ISSUE-004) exactly like build_policy.py.

Regenerate:  python demos/policies/build_boundary_policy.py
"""
from __future__ import annotations

from pathlib import Path

import build_policy  # reuse MAX_TOKEN_LENGTH and the safety discipline

# (list file, sentinel, action, stage, human label). Sentinels <= 15 chars.
LISTS: list[tuple[str, str, str, str, str]] = [
    ("block_phrases.txt", "[BLOCK]", "block", "pre", "Prompts blocked before inference"),
    ("route_phrases.txt", "[ROUTE]", "route", "pre", "Prompts routed to a controlled path"),
    ("flagged_customers.txt", "[ROUTE]", "route", "pre", "Flagged customers, routed"),
    ("denied_entities.txt", "[ROUTE]", "route", "pre", "Denied entities, routed"),
    ("payment_cards.txt", "[MASK_CARD]", "mask", "pre+post", "Payment card numbers, masked"),
    ("account_ids.txt", "[MASK_ACCT]", "mask", "pre+post", "Account identifiers, masked"),
    ("internal_projects.txt", "[TAG_INT]", "tag", "pre", "Internal projects, tagged internal_only"),
    ("output_block_phrases.txt", "[BLOCK_OUT]", "block", "post", "Generated output blocked"),
    ("output_tag_phrases.txt", "[TAG_PRIV]", "tag", "post", "Generated output tagged privileged"),
]

HERE = Path(__file__).resolve().parent
LIST_DIR = HERE.parent / "benchmark" / "datapoint2" / "data" / "reference_lists"
OUTPUT = HERE / "boundary.nol"


def load_lists(list_dir: Path) -> list[tuple[str, str, str, str, list[str]]]:
    """Return [(sentinel, action, stage, label, values)] for each present list."""
    loaded = []
    for filename, sentinel, action, stage, label in LISTS:
        path = list_dir / filename
        if not path.is_file():
            continue
        values = [line.strip() for line in path.read_text().splitlines() if line.strip()]
        if values:
            loaded.append((sentinel, action, stage, label, values))
    return loaded


def check_safe(lists: list[tuple[str, str, str, str, list[str]]]) -> None:
    """Refuse an unsafe policy: over-length sentinels (ISSUE-005) or containing
    literals (ISSUE-004). Unlike build_policy, sentinels MAY repeat across lists
    (several lists share the same action), so distinctness is not enforced.
    """
    for sentinel, _, _, _, _ in lists:
        if len(sentinel) > build_policy.MAX_TOKEN_LENGTH:
            raise ValueError(
                f"Sentinel {sentinel!r} exceeds {build_policy.MAX_TOKEN_LENGTH} chars; "
                "it would truncate at runtime (ISSUE-005)."
            )

    all_values = [value for _, _, _, _, values in lists for value in values]
    if len(set(all_values)) != len(all_values):
        raise ValueError("Duplicate values across the reference lists; each must be unique.")

    # Containment: no value may be a substring of another, or Themis corrupts the
    # output where their matches overlap (ISSUE-004). Case-insensitive, because the
    # harness matches case-insensitively and Themis matching is literal.
    lowered = {value: value.lower() for value in all_values}
    for outer in all_values:
        for inner in all_values:
            if inner != outer and lowered[inner] in lowered[outer]:
                raise ValueError(
                    f"Value {inner!r} is contained in {outer!r}; overlapping literals "
                    "trigger ISSUE-004. Remove one or make them disjoint."
                )


def build_nol(lists: list[tuple[str, str, str, str, list[str]]]) -> str:
    lines = [
        "# Data Point 2 boundary policy - pre/post-inference control (literal matching).",
        "# Generated by demos/policies/build_boundary_policy.py; edit the reference",
        "# lists under demos/benchmark/datapoint2/data/reference_lists/ and regenerate.",
        "# Same file deploys to both engines. The harness derives the action from the",
        "# sentinel and the control point (pre-inference prompt vs post-inference output).",
        "",
    ]
    for sentinel, action, stage, label, values in lists:
        lines.append(f"# {label} -> {sentinel}  (action={action}, stage={stage})")
        for value in values:
            escaped = value.replace('"', '\\"')
            lines.append(f'"{escaped}" -> "{sentinel}";')
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    lists = load_lists(LIST_DIR)
    if not lists:
        raise SystemExit(f"No reference lists found under {LIST_DIR}")
    check_safe(lists)
    OUTPUT.write_text(build_nol(lists))
    rule_count = sum(len(values) for _, _, _, _, values in lists)
    sentinels = sorted({sentinel for sentinel, _, _, _, _ in lists})
    print(f"Wrote {OUTPUT.name}: {rule_count} rules across {len(lists)} lists; "
          f"sentinels {', '.join(sentinels)}.")


if __name__ == "__main__":
    main()
