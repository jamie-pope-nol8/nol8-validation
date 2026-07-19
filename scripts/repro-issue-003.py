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

MESSAGE = "name: Elena Chen 1327, done"

FULL = "Elena Chen 1327"
PREFIX = "Elena Chen"
TOKEN = "[PII:PERSON_NAME]"

CASES: list[tuple[str, list[tuple[str, str]]]] = [
    ("full rule only", [(FULL, TOKEN)]),
    ("prefix rule only", [(PREFIX, TOKEN)]),
    ("both, prefix second", [(FULL, TOKEN), (PREFIX, TOKEN)]),
    ("both, prefix first", [(PREFIX, TOKEN), (FULL, TOKEN)]),
    ("both, short replacement", [(FULL, "[NAME]"), (PREFIX, "[NAME]")]),
    ("both, distinct replacements", [(FULL, "[FULL]"), (PREFIX, "[PFX]")]),
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
    print("ISSUE-003 - overlapping literal rules corrupt output")
    print("input: %r\n" % MESSAGE)
    print("%-30s %s" % ("policy", "output"))
    print("-" * 78)

    with tempfile.TemporaryDirectory() as scratch:
        policy_path = Path(scratch) / "repro-issue-003.nol"
        for name, rules in CASES:
            if not deploy(rules, policy_path):
                return 1
            actual = process(MESSAGE)
            if actual is None:
                print("%-30s REQUEST FAILED" % name)
                return 1
            print("%-30s %r" % (name, actual))

    print()
    print("Either rule alone renders correctly. Every policy containing both")
    print("rules corrupts the output, destroying content before the match.")
    print()
    print("Remember to restore the previous policy:")
    print("  ./scripts/load-policy.sh themis <previous-policy-file>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
