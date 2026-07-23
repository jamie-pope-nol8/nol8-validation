#!/usr/bin/env python3
"""Build the Data Point 3 mesh policy from the agent-to-agent reference lists.

Data Point 3 generalizes DP2 from two control points to many: governance is applied
at every hop of an agent workflow (Triage -> Research -> Decision -> Action -> Final),
plus tool calls and the final output. The controls are literal, so the same `.nol`
policy runs on both engines (NOL8/Themis and RE2/Aergia) exactly like DP1 and DP2.

Each reference list maps every literal value to a short SENTINEL token. The engine only
does literal replacement; the harness reads which sentinel appears and, given the
control point (stage), derives the governance action:

  list                     sentinel        action          stage
  ----------------------   -------------   -------------   ------------
  blocked_tool_phrases     [BLOCK_TOOL]    block_tool      tool
  internal_projects        [BLOCK_HAND]    block_handoff   handoff
  flagged_customers        [ROUTE]         route           handoff
  denied_entities          [ROUTE]         route           handoff
  payment_cards            [MASK_CARD]     mask            handoff + final
  account_ids             [MASK_ACCT]     mask            handoff + final
  output_block_phrases     [BLOCK_OUT]     block           final
  output_tag_phrases       [TAG_PRIV]      tag             final

Sentinels are UNIQUE per action (route is shared by two lists that both route), so the
action is unambiguous from the sentinel; the stage only says which control point we are
at. Sentinels are <= 15 chars so the runtime's 15-char truncation (ISSUE-005) never
garbles them, and the generator refuses containing literals (ISSUE-004) exactly like
build_policy.py / build_boundary_policy.py.

Regenerate:  python demos/policies/build_mesh_policy.py
"""
from __future__ import annotations

from pathlib import Path

import build_policy  # reuse MAX_TOKEN_LENGTH and the safety discipline

# (list file, sentinel, action, stage, human label). Sentinels <= 15 chars, unique per action.
LISTS: list[tuple[str, str, str, str, str]] = [
    ("blocked_tool_phrases.txt", "[BLOCK_TOOL]", "block_tool", "tool", "Tool calls blocked before external send"),
    ("internal_projects.txt", "[BLOCK_HAND]", "block_handoff", "handoff", "Internal projects, handoff to external agent blocked"),
    ("flagged_customers.txt", "[ROUTE]", "route", "handoff", "Flagged customers, routed to a controlled path"),
    ("denied_entities.txt", "[ROUTE]", "route", "handoff", "Denied entities, routed"),
    ("payment_cards.txt", "[MASK_CARD]", "mask", "handoff+final", "Payment card numbers, masked"),
    ("account_ids.txt", "[MASK_ACCT]", "mask", "handoff+final", "Account identifiers, masked"),
    ("output_block_phrases.txt", "[BLOCK_OUT]", "block", "final", "Generated output blocked"),
    ("output_tag_phrases.txt", "[TAG_PRIV]", "tag", "final", "Generated output tagged privileged"),
]

HERE = Path(__file__).resolve().parent
LIST_DIR = HERE.parent / "benchmark" / "datapoint3" / "data" / "policies"
OUTPUT = HERE / "mesh.nol"


def load_lists(list_dir: Path) -> list[tuple[str, str, str, str, list[str]]]:
    """Return [(sentinel, action, stage, label, values)] for each present list."""
    loaded = []
    for filename, sentinel, action, stage, label in LISTS:
        path = list_dir / filename
        if not path.is_file():
            continue
        values = [line.strip() for line in path.read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith("#")]
        if values:
            loaded.append((sentinel, action, stage, label, values))
    return loaded


def check_safe(lists: list[tuple[str, str, str, str, list[str]]]) -> None:
    """Refuse an unsafe policy: over-length sentinels (ISSUE-005) or containing
    literals (ISSUE-004). Sentinels MAY repeat across lists (several lists share an
    action), so distinctness of sentinels is not enforced; values must be unique and
    non-overlapping.
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

    # Containment: no value may be a substring of another, or the engine corrupts the
    # output where their matches overlap (ISSUE-004). Case-insensitive, because the
    # harness matches case-insensitively and engine matching is literal.
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
        "# Data Point 3 mesh policy - agent-to-agent control (literal matching).",
        "# Generated by demos/policies/build_mesh_policy.py; edit the reference lists",
        "# under demos/benchmark/datapoint3/data/policies/ and regenerate.",
        "# Same file deploys to both engines. The harness derives the action from the",
        "# sentinel and the control point (handoff / tool call / final output).",
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
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list-dir", type=Path, default=LIST_DIR,
                    help="directory of reference lists (default: the DP3 policy lists)")
    ap.add_argument("--output", type=Path, default=OUTPUT,
                    help="output .nol path (default: demos/policies/mesh.nol)")
    args = ap.parse_args()

    lists = load_lists(args.list_dir)
    if not lists:
        raise SystemExit(f"No reference lists found under {args.list_dir}")
    check_safe(lists)
    args.output.write_text(build_nol(lists))
    rule_count = sum(len(values) for _, _, _, _, values in lists)
    sentinels = sorted({sentinel for sentinel, _, _, _, _ in lists})
    print(f"Wrote {args.output.name}: {rule_count} rules across {len(lists)} lists; "
          f"sentinels {', '.join(sentinels)}.")


if __name__ == "__main__":
    main()
