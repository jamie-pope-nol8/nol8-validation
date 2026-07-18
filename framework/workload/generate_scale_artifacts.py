"""Generate canonical validation artifacts from a scale workload definition."""

from __future__ import annotations

import json
import os
import random
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from framework.workload.generate_workload import (
    _generate_field_value,
    _pad_document,
    _serialize_record,
    _weighted_item,
    load_workload,
)


@dataclass(frozen=True)
class ScaleRule:
    rule_id: str
    category_id: str
    pattern_id: str
    variant: str
    replacement: str


ScaleProgressCallback = Callable[[str, int, int], None]


def _report_progress(
    callback: ScaleProgressCallback | None,
    event: str,
    completed: int,
    total: int,
) -> None:
    if callback is not None:
        callback(event, completed, total)


def is_scale_workload(config: Mapping[str, Any]) -> bool:
    """Return whether a loaded configuration uses the workload schema."""

    return all(key in config for key in ("name", "seed", "policy", "documents"))


def _rule_catalog(workload: Mapping[str, Any]) -> list[ScaleRule]:
    policy = workload.get("policy")
    if not isinstance(policy, Mapping):
        raise ValueError("'policy' must be a mapping.")

    rule_count = int(policy.get("rule_count", 0))
    families = policy.get("families")
    if rule_count < 1:
        raise ValueError("'policy.rule_count' must be at least 1.")
    if not isinstance(families, Mapping) or not families:
        raise ValueError("'policy.families' must be a non-empty mapping.")

    rng = random.Random(int(workload["seed"]))
    rules: list[ScaleRule] = []
    for index in range(1, rule_count + 1):
        category_id, family = _weighted_item(families, rng)
        patterns = family.get("patterns")
        if not isinstance(patterns, list) or not patterns:
            raise ValueError(
                f"'policy.families.{category_id}.patterns' must be a non-empty list."
            )
        pattern_id = str(patterns[(index - 1) % len(patterns)])
        rule_id = f"rule-{index:06d}"
        variant = f"NOL8_{category_id}_{pattern_id}_{index:06d}"
        replacement = f"[{category_id.upper()}:{pattern_id.upper()}]"
        rules.append(
            ScaleRule(
                rule_id=rule_id,
                category_id=str(category_id),
                pattern_id=pattern_id,
                variant=variant,
                replacement=replacement,
            )
        )
    return rules


def _write_policy(path: Path, rules: list[ScaleRule]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for rule in sorted(rules, key=lambda item: (-len(item.variant), item.variant)):
            variant = rule.variant.replace("\\", "\\\\").replace('"', '\\"')
            replacement = rule.replacement.replace("\\", "\\\\").replace(
                '"', '\\"'
            )
            handle.write(f'"{variant}" -> "{replacement}";\n')
    os.replace(temporary, path)


def _deterministic_record(
    document_id: str,
    scenario_name: str,
    fields: list[str],
    rng: random.Random,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "document_id": document_id,
        "scenario": scenario_name,
        "generated_at": "2000-01-01T00:00:00Z",
    }
    for field_name in fields:
        if field_name == "timestamp":
            record[field_name] = "2000-01-01T00:00:00Z"
        else:
            record[field_name] = _generate_field_value(field_name, rng)
    return record


def _inject_rules(record: dict[str, Any], rules: list[ScaleRule]) -> None:
    preferred_fields = (
        "internal_notes",
        "issue_description",
        "message_body",
        "message",
        "request_body",
        "response_body",
        "description",
        "retrieved_context",
        "tool_output",
        "model_response",
        "user_prompt",
    )
    injection_field = next(
        (field for field in preferred_fields if field in record),
        "validation_content",
    )
    existing = record.get(injection_field, "")
    if isinstance(existing, (dict, list)):
        existing_text = json.dumps(existing, sort_keys=True)
    else:
        existing_text = str(existing)
    markers = [
        f"validation_rule_{index}: {rule.variant}"
        for index, rule in enumerate(rules, start=1)
    ]
    record[injection_field] = "\n".join([existing_text, *markers]).strip()


def _expected_result(
    message: str, rules: list[ScaleRule]
) -> tuple[str, list[dict[str, str]]]:
    expected = message
    matches: list[dict[str, str]] = []
    for rule in sorted(rules, key=lambda item: (-len(item.variant), item.variant)):
        count = expected.count(rule.variant)
        if not count:
            continue
        expected = expected.replace(rule.variant, rule.replacement)
        for _ in range(count):
            matches.append(
                {
                    "category_id": rule.category_id,
                    "case_id": rule.pattern_id,
                    "variant": rule.variant,
                    "replacement": rule.replacement,
                }
            )
    return expected, matches


def generate_scale_artifacts(
    workload_path: Path,
    output_dir: Path,
    *,
    document_count: int | None = None,
    progress_callback: ScaleProgressCallback | None = None,
) -> dict[str, Any]:
    """Generate policy, input, expected, and metadata artifacts for a workload."""

    workload = load_workload(workload_path)
    if not is_scale_workload(workload):
        raise ValueError("Configuration is not an enterprise workload schema.")
    _report_progress(progress_callback, "configuration_loaded", 1, 1)

    documents = workload["documents"]
    requested_rules = int(workload["policy"]["rule_count"])
    _report_progress(progress_callback, "rules_started", 0, requested_rules)
    rules = _rule_catalog(workload)
    _report_progress(
        progress_callback, "rules_completed", len(rules), requested_rules
    )
    requested_records = int(documents["count"])
    realized_records = (
        requested_records if document_count is None else int(document_count)
    )
    if realized_records < 1:
        raise ValueError("Document count must be at least 1.")
    progress_interval = int(documents.get("progress_interval_records", 1000))
    if progress_interval < 1:
        raise ValueError("'documents.progress_interval_records' must be at least 1.")

    output_dir.mkdir(parents=True, exist_ok=True)
    policy_path = output_dir / "scale-policy.nol"
    input_path = output_dir / "input.jsonl"
    expected_path = output_dir / "expected.jsonl"
    manifest_path = output_dir / "manifest.json"
    input_temporary = input_path.with_name(f".{input_path.name}.tmp")
    expected_temporary = expected_path.with_name(f".{expected_path.name}.tmp")

    _write_policy(policy_path, rules)
    rng = random.Random(int(workload["seed"]))
    clean_count = 0
    dirty_count = 0
    expected_total = 0
    scenario_counts: Counter[str] = Counter()
    format_counts: Counter[str] = Counter()
    match_profile_counts: Counter[str] = Counter()
    size_profile_counts: Counter[str] = Counter()
    payload_bytes_total = 0
    payload_bytes_min: int | None = None
    payload_bytes_max = 0

    _report_progress(
        progress_callback, "documents_started", 0, realized_records
    )
    _report_progress(
        progress_callback, "expected_started", 0, realized_records
    )

    try:
        with input_temporary.open("w", encoding="utf-8") as input_handle, \
                expected_temporary.open("w", encoding="utf-8") as expected_handle:
            for index in range(1, realized_records + 1):
                document_id = f"document-{index:06d}"
                scenario_name, scenario = _weighted_item(documents["scenarios"], rng)
                format_name, _ = _weighted_item(documents["formats"], rng)
                match_profile_name, match_profile = _weighted_item(
                    documents["match_distribution"], rng
                )
                size_profile_name, size_profile = _weighted_item(
                    documents["size_distribution"], rng
                )
                match_range = match_profile["matches_per_document"]
                match_count = rng.randint(
                    int(match_range["minimum"]), int(match_range["maximum"])
                )
                selected_rules = rng.sample(rules, k=min(match_count, len(rules)))

                record = _deterministic_record(
                    document_id,
                    scenario_name,
                    list(scenario["fields"]),
                    rng,
                )
                _inject_rules(record, selected_rules)
                message = _serialize_record(
                    record=record,
                    format_name=format_name,
                    scenario_name=scenario_name,
                )
                target_size = rng.randint(
                    int(size_profile["minimum_bytes"]),
                    int(size_profile["maximum_bytes"]),
                )
                message = _pad_document(
                    content=message,
                    target_size=target_size,
                    format_name=format_name,
                    random_source=rng,
                )
                if index % progress_interval == 0 or index == realized_records:
                    _report_progress(
                        progress_callback,
                        "documents_progress",
                        index,
                        realized_records,
                    )

                # Only selected rules can occur as generated scale markers. Using
                # that exact injection evidence preserves the full transformation
                # contract without rescanning the message for every policy rule.
                expected_message, expected_matches = _expected_result(
                    message, selected_rules
                )
                kind = "dirty" if expected_matches else "clean"

                input_handle.write(
                    json.dumps(
                        {"record_id": document_id, "kind": kind, "message": message},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                expected_handle.write(
                    json.dumps(
                        {
                            "record_id": document_id,
                            "kind": kind,
                            "expected_message": expected_message,
                            "expected_match_count": len(expected_matches),
                            "expected_matches": expected_matches,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                scenario_counts[scenario_name] += 1
                format_counts[format_name] += 1
                match_profile_counts[match_profile_name] += 1
                size_profile_counts[size_profile_name] += 1
                message_size = len(message.encode("utf-8"))
                payload_bytes_total += message_size
                payload_bytes_min = (
                    message_size
                    if payload_bytes_min is None
                    else min(payload_bytes_min, message_size)
                )
                payload_bytes_max = max(payload_bytes_max, message_size)
                expected_total += len(expected_matches)
                if kind == "dirty":
                    dirty_count += 1
                else:
                    clean_count += 1
                if index % progress_interval == 0 or index == realized_records:
                    _report_progress(
                        progress_callback,
                        "expected_progress",
                        index,
                        realized_records,
                    )
        _report_progress(progress_callback, "artifacts_started", 0, 0)
        os.replace(input_temporary, input_path)
        os.replace(expected_temporary, expected_path)
    except Exception:
        input_temporary.unlink(missing_ok=True)
        expected_temporary.unlink(missing_ok=True)
        raise

    manifest = {
        "generator_version": 1,
        "generator_schema": "enterprise-dlp-scale",
        "workload_name": workload["name"],
        "workload_version": workload.get("version"),
        "seed": workload["seed"],
        "requested_records": requested_records,
        "realized_records": realized_records,
        "requested_rules": requested_rules,
        "realized_rules": len(rules),
        "clean_record_count": clean_count,
        "dirty_record_count": dirty_count,
        "scenario_distribution": dict(sorted(scenario_counts.items())),
        "format_distribution": dict(sorted(format_counts.items())),
        "match_profile_distribution": dict(sorted(match_profile_counts.items())),
        "size_profile_distribution": dict(sorted(size_profile_counts.items())),
        "payload_bytes_total": payload_bytes_total,
        "payload_bytes_minimum": payload_bytes_min or 0,
        "payload_bytes_maximum": payload_bytes_max,
        "payload_bytes_average": round(
            payload_bytes_total / realized_records, 3
        ),
        "requested_scale": {
            "rule_count": requested_rules,
            "record_count": requested_records,
            "policy_families": deepcopy(workload["policy"]["families"]),
            "scenarios": deepcopy(documents["scenarios"]),
            "formats": deepcopy(documents["formats"]),
            "match_distribution": deepcopy(documents["match_distribution"]),
            "size_distribution": deepcopy(documents["size_distribution"]),
        },
        "realized_scale": {
            "rule_count": len(rules),
            "record_count": realized_records,
            "policy_family_distribution": dict(
                sorted(Counter(rule.category_id for rule in rules).items())
            ),
            "scenario_distribution": dict(sorted(scenario_counts.items())),
            "format_distribution": dict(sorted(format_counts.items())),
            "match_profile_distribution": dict(
                sorted(match_profile_counts.items())
            ),
            "size_profile_distribution": dict(sorted(size_profile_counts.items())),
            "payload_bytes": {
                "total": payload_bytes_total,
                "minimum": payload_bytes_min or 0,
                "maximum": payload_bytes_max,
                "average": round(payload_bytes_total / realized_records, 3),
            },
        },
        "expected_total_matches": expected_total,
        "rule_catalog": [
            {
                "rule_id": rule.rule_id,
                "category_id": rule.category_id,
                "pattern_id": rule.pattern_id,
                "variant": rule.variant,
                "replacement": rule.replacement,
            }
            for rule in rules
        ],
        "artifacts": {
            "policy": "scale-policy.nol",
            "input": "input.jsonl",
            "expected": "expected.jsonl",
        },
    }
    temporary_manifest = manifest_path.with_name(f".{manifest_path.name}.tmp")
    temporary_manifest.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_manifest, manifest_path)
    _report_progress(progress_callback, "complete", realized_records, realized_records)
    return manifest
