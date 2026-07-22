#!/usr/bin/env python3
"""Adjudicate the DP2 engine outputs against an independent oracle.

The integrity check pointed at us, generalized to the pre/post-inference boundary.
For every prompt (and every model-stub output) the framework's Aho-Corasick matcher
computes the correct leftmost-longest literal replacement of `boundary.nol`. We
then derive the expected block/mask/route/tag action from the sentinels exactly as
the harness does, and compare against what each engine actually produced:

  - action correctness: recorded pre/post action + tags match the oracle's.
  - byte correctness: where text is forwarded (allow/mask/tag), the engine's
    forwarded text matches the oracle's replacement byte-for-byte.

If Themis matches the oracle, its parity with Aergia is a genuinely correct result,
not two engines agreeing on the same mistake.

Usage (run where the DP2 output jsonls live, e.g. EC2 results/):

  python demos/benchmark/datapoint2/verify-oracle.py \
      --policy demos/policies/boundary.nol \
      --results demos/benchmark/datapoint2/results \
      themis_api_infer aergia_api_infer
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from framework.policy.matching import LiteralMatcher, resolve_non_overlapping  # noqa: E402

_RULE = re.compile(r'^"((?:[^"\\]|\\.)*)"\s*->\s*"((?:[^"\\]|\\.)*)";\s*$')


def _unescape(s: str) -> str:
    return s.replace('\\"', '"').replace("\\\\", "\\")


def parse_policy(path: Path) -> dict[str, str]:
    rules: dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _RULE.match(line)
        if not m:
            raise ValueError(f"{path}:{lineno}: not a rule: {raw!r}")
        rules[_unescape(m.group(1))] = _unescape(m.group(2))
    return rules


def oracle_output(text: str, matcher: LiteralMatcher, rules: dict[str, str]) -> str:
    selected = resolve_non_overlapping(matcher.find_all(text))
    out, cursor = [], 0
    for match in selected:
        out.append(text[cursor:match.start])
        out.append(rules[match.literal])
        cursor = match.end
    out.append(text[cursor:])
    return "".join(out)


# The harness's action derivation, mirrored (engine_infer.go).
def derive_pre(processed: str):
    if "[BLOCK]" in processed:
        return "block", []
    if "[ROUTE]" in processed:
        return "route", []
    action, tags = "allow", []
    if "[MASK_CARD]" in processed or "[MASK_ACCT]" in processed:
        action = "mask"
    if "[TAG_INT]" in processed:
        tags.append("internal_only")
        if action == "allow":
            action = "tag"
    return action, tags


def derive_post(processed: str):
    if "[BLOCK_OUT]" in processed:
        return "block", "[BLOCKED_OUTPUT]", []
    action, tags = "allow", []
    if "[MASK_CARD]" in processed or "[MASK_ACCT]" in processed:
        action = "mask"
    if "[TAG_PRIV]" in processed:
        tags.append("privileged_context")
        if action == "allow":
            action = "tag"
    return action, processed, tags


def load_records(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def verify_engine(records, matcher, rules, samples):
    problems = []
    for r in records:
        oracle_pre = oracle_output(r["prompt_original"], matcher, rules)
        exp_action, exp_tags = derive_pre(oracle_pre)
        if r["pre_action"] != exp_action or sorted(r["pre_tags"]) != sorted(exp_tags):
            problems.append((r["prompt_id"], "pre_action",
                             f"{r['pre_action']}{r['pre_tags']}", f"{exp_action}{exp_tags}"))
        elif exp_action in ("allow", "mask", "tag") and r["prompt_processed"] != oracle_pre:
            problems.append((r["prompt_id"], "prompt_processed",
                             repr(r["prompt_processed"]), repr(oracle_pre)))

        if r["inference_called"]:
            oracle_post = oracle_output(r["raw_model_output"], matcher, rules)
            exp_paction, exp_final, exp_ptags = derive_post(oracle_post)
            if r["post_action"] != exp_paction or sorted(r["post_tags"]) != sorted(exp_ptags):
                problems.append((r["prompt_id"], "post_action",
                                 f"{r['post_action']}{r['post_tags']}", f"{exp_paction}{exp_ptags}"))
            elif r["final_output"] != exp_final:
                problems.append((r["prompt_id"], "final_output",
                                 repr(r["final_output"]), repr(exp_final)))
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("engines", nargs="+")
    ap.add_argument("--policy", type=Path, default=REPO_ROOT / "demos/policies/boundary.nol")
    ap.add_argument("--results", type=Path, default=REPO_ROOT / "demos/benchmark/datapoint2/results")
    ap.add_argument("--samples", type=int, default=5)
    args = ap.parse_args()

    rules = parse_policy(args.policy)
    matcher = LiteralMatcher(rules.keys())
    print(f"Policy: {args.policy.name} ({len(rules)} literal rules)\n")

    any_bad = False
    for engine in args.engines:
        path = args.results / f"{engine}_output.jsonl"
        if not path.exists():
            print(f"[{engine}] MISSING {path}")
            any_bad = True
            continue
        records = load_records(path)
        problems = verify_engine(records, matcher, rules, args.samples)
        verdict = "MATCHES ORACLE" if not problems else "DIVERGES FROM ORACLE"
        print(f"[{engine}] {len(records)} prompts; {len(records) - len({p[0] for p in problems})}"
              f"/{len(records)} fully match oracle -> {verdict}")
        for pid, field, got, exp in problems[:args.samples]:
            print(f"  - {pid} [{field}]\n      engine: {got}\n      oracle: {exp}")
        if len(problems) > args.samples:
            print(f"  ... and {len(problems) - args.samples} more")
        print()
        any_bad = any_bad or bool(problems)

    print("VERDICT: " + ("at least one engine diverges from the oracle."
                          if any_bad else "every engine matches the oracle."))
    return 1 if any_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
