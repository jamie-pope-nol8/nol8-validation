#!/usr/bin/env python3
"""Minimal reproduction for ISSUE-003.

Two rules whose literals overlap - one a strict prefix of the other - cause the
Themis runtime to compute the wrong start offset for the replacement, silently
destroying content that precedes the match.

Either rule alone produces correct output. Only their coexistence triggers it.
Rule order does not matter. Replacement length does not prevent it.

Usage:

    ./scripts/repro-issue-003.py

Requires config/demo.env and .env (token), as with all validation execution.
The script deploys policies to the configured Themis policy endpoint, which
REPLACES the active policy. Restore the previous policy afterwards:

    ./scripts/load-policy.sh themis <previous-policy-file>
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOAD_POLICY = REPOSITORY_ROOT / "scripts" / "load-policy.sh"
RUN_VALIDATION = REPOSITORY_ROOT / "scripts" / "run-validation.sh"

FULL = "Elena Chen 1327"
PREFIX = "Elena Chen"
TOKEN = "[PII:PERSON_NAME]"

# (label, rules, input, correct output)
CASES: list[tuple[str, list[tuple[str, str]], str, str]] = [
    # Containment: one literal is a strict prefix of the other.
    ("containment: full rule only", [(FULL, TOKEN)],
     "name: Elena Chen 1327, done", "name: [PII:PERSON_NAM, done"),
    ("containment: prefix rule only", [(PREFIX, TOKEN)],
     "name: Elena Chen 1327, done", "name: [PII:PERSON_NAM 1327, done"),
    ("containment: both, prefix 2nd", [(FULL, TOKEN), (PREFIX, TOKEN)],
     "name: Elena Chen 1327, done", "name: [PII:PERSON_NAM, done"),
    ("containment: both, prefix 1st", [(PREFIX, TOKEN), (FULL, TOKEN)],
     "name: Elena Chen 1327, done", "name: [PII:PERSON_NAM, done"),
    ("containment: short replacement", [(FULL, "[NAME]"), (PREFIX, "[NAME]")],
     "name: Elena Chen 1327, done", "name: [NAME], done"),

    # Partial overlap: neither literal contains the other, but their matches
    # share input bytes. This class is missed by a containment-only check.
    ("overlap 1 char: first only", [("ABCD", "[P]"), ("ZZZZ", "[Q]")],
     "x ABCDEFG y", "x [P]EFG y"),
    ("overlap 1 char: second only", [("ZZZZ", "[P]"), ("DEFG", "[Q]")],
     "x ABCDEFG y", "x ABC[Q] y"),
    ("overlap 1 char: both", [("ABCD", "[P]"), ("DEFG", "[Q]")],
     "x ABCDEFG y", "x [P]EFG y"),
    ("overlap 3 chars: both", [("ABCDEF", "[P]"), ("DEFGHI", "[Q]")],
     "x ABCDEFGHI y", "x [P]GHI y"),

    # Controls: no shared bytes.
    ("control: disjoint", [("ONE-TWO", "[P]"), ("SIX-NINE", "[Q]")],
     "a ONE-TWO b SIX-NINE c", "a [P] b [Q] c"),
    ("control: adjacent", [("AAAA", "[P]"), ("BBBB", "[Q]")],
     "x AAAABBBB y", "x [P][Q] y"),
]


def _run(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=REPOSITORY_ROOT,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def deploy(rules: list[tuple[str, str]], path: Path) -> bool:
    path.write_text(
        "".join('"%s" -> "%s";\n' % (literal, token) for literal, token in rules)
    )
    result = _run([str(LOAD_POLICY), "themis", str(path)])
    if result.returncode != 0:
        print("  policy deployment failed: %s" % result.stderr.strip(),
              file=sys.stderr)
        return False
    return True


def process(message: str) -> str | None:
    result = _run([str(RUN_VALIDATION), "themis"],
                  stdin=json.dumps({"message": message}))
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)["response"]["message"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def main() -> int:
    print("ISSUE-003 - overlapping matches corrupt output\n")
    print("%-31s %-24s %-24s %s" % ("case", "correct", "actual", ""))
    print("-" * 92)

    corrupted = 0
    with tempfile.TemporaryDirectory() as scratch:
        policy_path = Path(scratch) / "repro-issue-003.nol"
        for name, rules, message, correct in CASES:
            if not deploy(rules, policy_path):
                return 1
            actual = process(message)
            if actual is None:
                print("%-31s REQUEST FAILED" % name)
                return 1
            ok = actual == correct
            corrupted += not ok
            print("%-31s %-24r %-24r %s"
                  % (name, correct, actual, "ok" if ok else "CORRUPT"))

    print()
    print("Corrupted cases: %d of %d" % (corrupted, len(CASES)))
    print()
    print("Either rule alone renders correctly. Two rules whose matches share")
    print("input bytes corrupt the output, destroying content before the match.")
    print("Adjacent matches that do not share bytes are correct.")
    print()
    print("Remember to restore the previous policy:")
    print("  ./scripts/load-policy.sh themis <previous-policy-file>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
