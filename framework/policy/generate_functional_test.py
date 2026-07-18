#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print(
        "Missing dependency: PyYAML\n"
        "Install it with: python3 -m pip install --user pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)


RECORD_TEMPLATES = [
    """Customer support case {record_id}

Customer: {value_1}
Account note: {value_2}
Additional details: {value_3}
""",
    """Application event {record_id}

The following values were included in the request:
- Primary value: {value_1}
- Secondary value: {value_2}
- Context value: {value_3}
""",
    """Customer transaction record {record_id}

Submitted data:
{value_1}

Metadata:
{value_2}

Operator notes:
{value_3}
""",
    """AI workload request {record_id}

User content:
{value_1}

Attached context:
{value_2}

Execution instruction:
{value_3}
""",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Nol8 functional scale-test artifacts."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.home()
        / "jamie"
        / "scale-test"
        / "config"
        / "test-cases.yaml",
        help="Path to the YAML test manifest.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.home() / "jamie" / "scale-test" / "generated",
        help="Directory for generated artifacts.",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    if not isinstance(config, dict):
        raise ValueError("The YAML configuration must contain a mapping.")

    return config


def flatten_rules(config: dict[str, Any]) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    variant_replacements: dict[str, str] = {}

    for category in config.get("categories", []):
        category_id = category["id"]

        for case in category.get("cases", []):
            case_id = case["id"]
            replacement = case["replacement"]

            for variant in case.get("variants", []):
                if not isinstance(variant, str) or not variant:
                    raise ValueError(
                        f"Invalid variant in {category_id}/{case_id}: {variant!r}"
                    )

                existing = variant_replacements.get(variant)

                if existing is not None and existing != replacement:
                    raise ValueError(
                        f"Variant {variant!r} maps to conflicting replacements: "
                        f"{existing!r} and {replacement!r}"
                    )

                if existing is None:
                    variant_replacements[variant] = replacement
                    rules.append(
                        {
                            "category_id": category_id,
                            "case_id": case_id,
                            "variant": variant,
                            "replacement": replacement,
                        }
                    )

    if not rules:
        raise ValueError("No policy rules were found in the YAML configuration.")

    # Longer values are emitted first so a value such as "supersecret"
    # is considered before the shorter embedded value "secret".
    rules.sort(key=lambda rule: (-len(rule["variant"]), rule["variant"]))

    return rules


def escape_policy_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def write_policy(path: Path, rules: list[dict[str, str]]) -> None:
    lines = [
        f'"{escape_policy_value(rule["variant"])}"'
        f' -> "{escape_policy_value(rule["replacement"])}";'
        for rule in rules
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def transform_message(
    message: str,
    rules: list[dict[str, str]],
) -> tuple[str, list[dict[str, str]]]:
    transformed = message
    matches: list[dict[str, str]] = []

    for rule in rules:
        count = transformed.count(rule["variant"])

        if count == 0:
            continue

        transformed = transformed.replace(
            rule["variant"],
            rule["replacement"],
        )

        for _ in range(count):
            matches.append(rule)

    return transformed, matches


def build_dirty_record(
    record_id: int,
    selected_rules: list[dict[str, str]],
    negative_values: list[str],
    rng: random.Random,
) -> str:
    values = [rule["variant"] for rule in selected_rules]

    while len(values) < 3:
        values.append(rng.choice(negative_values))

    rng.shuffle(values)

    template = rng.choice(RECORD_TEMPLATES)

    return template.format(
        record_id=f"{record_id:06d}",
        value_1=values[0],
        value_2=values[1],
        value_3="\n".join(values[2:]),
    ).rstrip()


def build_clean_record(
    record_id: int,
    negative_values: list[str],
    rng: random.Random,
) -> str:
    selected = rng.sample(
        negative_values,
        k=min(3, len(negative_values)),
    )

    return (
        f"Clean control record {record_id:06d}\n\n"
        f"{selected[0]}\n"
        f"{selected[1]}\n"
        f"{selected[2]}"
    )


def generate_records(
    config: dict[str, Any],
    rules: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], Counter[str], Counter[str]]:
    test_config = config["test"]
    defaults = config["defaults"]

    record_count = int(test_config["records"])
    seed = int(test_config["seed"])
    clean_percent = float(defaults["clean_records_percent"])
    maximum_matches = int(defaults["maximum_matches_per_record"])

    negative_values = config.get("negative_controls", {}).get("values", [])

    if len(negative_values) < 3:
        raise ValueError("At least three negative-control values are required.")

    if record_count < len(rules):
        raise ValueError(
            f"Configured records ({record_count}) must be at least the number "
            f"of policy variants ({len(rules)}) to guarantee full coverage."
        )

    if maximum_matches < 1:
        raise ValueError("maximum_matches_per_record must be at least 1.")

    rng = random.Random(seed)

    clean_count = round(record_count * clean_percent / 100)
    dirty_count = record_count - clean_count

    if dirty_count < len(rules):
        raise ValueError(
            "There are not enough non-clean records to cover every rule variant."
        )

    records: list[dict[str, Any]] = []
    variant_coverage: Counter[str] = Counter()
    category_coverage: Counter[str] = Counter()

    # Guarantee that every policy variant appears in at least one record.
    required_rules = list(rules)
    rng.shuffle(required_rules)

    for index in range(dirty_count):
        if index < len(required_rules):
            selected_rules = [required_rules[index]]
        else:
            match_count = rng.randint(1, maximum_matches)
            selected_rules = rng.sample(
                rules,
                k=min(match_count, len(rules)),
            )

        message = build_dirty_record(
            record_id=index + 1,
            selected_rules=selected_rules,
            negative_values=negative_values,
            rng=rng,
        )

        expected_message, detected_matches = transform_message(message, rules)

        for match in detected_matches:
            variant_coverage[match["variant"]] += 1
            category_coverage[match["category_id"]] += 1

        records.append(
            {
                "record_id": f"record-{index + 1:06d}",
                "kind": "dirty",
                "message": message,
                "expected_message": expected_message,
                "expected_match_count": len(detected_matches),
                "expected_matches": [
                    {
                        "category_id": match["category_id"],
                        "case_id": match["case_id"],
                        "variant": match["variant"],
                        "replacement": match["replacement"],
                    }
                    for match in detected_matches
                ],
            }
        )

    for index in range(clean_count):
        record_number = dirty_count + index + 1
        message = build_clean_record(
            record_id=record_number,
            negative_values=negative_values,
            rng=rng,
        )

        expected_message, detected_matches = transform_message(message, rules)

        if detected_matches:
            matching_values = sorted(
                {match["variant"] for match in detected_matches}
            )
            raise ValueError(
                "A negative-control record unexpectedly matched policy rules: "
                + ", ".join(repr(value) for value in matching_values)
            )

        records.append(
            {
                "record_id": f"record-{record_number:06d}",
                "kind": "clean",
                "message": message,
                "expected_message": expected_message,
                "expected_match_count": 0,
                "expected_matches": [],
            }
        )

    rng.shuffle(records)

    return records, variant_coverage, category_coverage


def write_jsonl(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def generate_functional_artifacts(
    config_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Generate the proven functional artifacts and return their manifest."""
    config = load_config(config_path)
    rules = flatten_rules(config)

    output_dir.mkdir(parents=True, exist_ok=True)

    records, variant_coverage, category_coverage = generate_records(
        config,
        rules,
    )

    policy_path = output_dir / "scale-policy.nol"
    input_path = output_dir / "input.jsonl"
    expected_path = output_dir / "expected.jsonl"
    manifest_path = output_dir / "manifest.json"

    write_policy(policy_path, rules)

    write_jsonl(
        input_path,
        [
            {
                "record_id": record["record_id"],
                "kind": record["kind"],
                "message": record["message"],
            }
            for record in records
        ],
    )

    write_jsonl(
        expected_path,
        [
            {
                "record_id": record["record_id"],
                "kind": record["kind"],
                "expected_message": record["expected_message"],
                "expected_match_count": record["expected_match_count"],
                "expected_matches": record["expected_matches"],
            }
            for record in records
        ],
    )

    uncovered_variants = [
        rule["variant"]
        for rule in rules
        if variant_coverage[rule["variant"]] == 0
    ]

    manifest = {
        "generator_version": 1,
        "test_name": config["test"]["name"],
        "seed": config["test"]["seed"],
        "record_count": len(records),
        "dirty_record_count": sum(
            record["kind"] == "dirty" for record in records
        ),
        "clean_record_count": sum(
            record["kind"] == "clean" for record in records
        ),
        "policy_rule_count": len(rules),
        "expected_total_matches": sum(
            record["expected_match_count"] for record in records
        ),
        "full_variant_coverage": not uncovered_variants,
        "uncovered_variants": uncovered_variants,
        "variant_coverage": dict(sorted(variant_coverage.items())),
        "category_coverage": dict(sorted(category_coverage.items())),
        "artifacts": {
            "policy": str(policy_path),
            "input": str(input_path),
            "expected": str(expected_path),
        },
    }

    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return manifest


def main() -> int:
    args = parse_args()

    try:
        manifest = generate_functional_artifacts(args.config, args.output_dir)

        print("Functional test artifacts generated")
        print()
        print(f"Policy rules:           {manifest['policy_rule_count']}")
        print(f"Records:                {manifest['record_count']}")
        print(f"Expected replacements:  {manifest['expected_total_matches']}")
        print(
            "Full variant coverage:  "
            + ("Yes" if manifest["full_variant_coverage"] else "No")
        )
        print()
        print(f"Policy:    {args.output_dir / 'scale-policy.nol'}")
        print(f"Input:     {args.output_dir / 'input.jsonl'}")
        print(f"Expected:  {args.output_dir / 'expected.jsonl'}")
        print(f"Manifest:  {args.output_dir / 'manifest.json'}")

        return 0

    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        print(f"Generation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
