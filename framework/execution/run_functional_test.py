#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ENDPOINT = "https://tenant001-v1demo.nol8.net/v1/process"


@dataclass
class TestResult:
    record_id: str
    kind: str
    passed: bool
    http_status: int | None
    elapsed_ms: float
    expected_message: str
    actual_message: str | None
    expected_match_count: int
    error: str | None


def parse_args() -> argparse.Namespace:
    base_dir = Path.home() / "jamie" / "scale-test"

    parser = argparse.ArgumentParser(
        description="Run the Nol8 functional scale test."
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=base_dir / "generated" / "input.jsonl",
        help="Generated input JSONL file.",
    )

    parser.add_argument(
        "--expected",
        type=Path,
        default=base_dir / "generated" / "expected.jsonl",
        help="Generated expected-results JSONL file.",
    )

    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help="Nol8 process API endpoint.",
    )

    parser.add_argument(
        "--report-dir",
        type=Path,
        default=base_dir / "reports",
        help="Directory for test reports.",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds.",
    )

    parser.add_argument(
        "--progress-every",
        type=int,
        default=50,
        help="Print progress after this many records.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N records.",
    )

    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification.",
    )

    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {path} at line {line_number}: {exc}"
                ) from exc

            if not isinstance(row, dict):
                raise ValueError(
                    f"Expected a JSON object in {path} at line {line_number}"
                )

            rows.append(row)

    return rows


def index_by_record_id(
    rows: list[dict[str, Any]],
    source_name: str,
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}

    for row in rows:
        record_id = row.get("record_id")

        if not isinstance(record_id, str) or not record_id:
            raise ValueError(
                f"Missing or invalid record_id in {source_name}"
            )

        if record_id in indexed:
            raise ValueError(
                f"Duplicate record_id {record_id!r} in {source_name}"
            )

        indexed[record_id] = row

    return indexed


def validate_datasets(
    inputs: dict[str, dict[str, Any]],
    expected: dict[str, dict[str, Any]],
) -> None:
    input_ids = set(inputs)
    expected_ids = set(expected)

    missing_expected = sorted(input_ids - expected_ids)
    missing_input = sorted(expected_ids - input_ids)

    if missing_expected:
        raise ValueError(
            "Input records are missing expected results: "
            + ", ".join(missing_expected[:10])
        )

    if missing_input:
        raise ValueError(
            "Expected results are missing input records: "
            + ", ".join(missing_input[:10])
        )


def build_ssl_context(insecure: bool) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()

    return ssl.create_default_context()


def process_record(
    endpoint: str,
    input_row: dict[str, Any],
    expected_row: dict[str, Any],
    timeout: float,
    ssl_context: ssl.SSLContext,
) -> TestResult:
    record_id = input_row["record_id"]
    kind = input_row.get("kind", "unknown")
    message = input_row.get("message")
    expected_message = expected_row.get("expected_message")
    expected_match_count = int(
        expected_row.get("expected_match_count", 0)
    )

    if not isinstance(message, str):
        return TestResult(
            record_id=record_id,
            kind=kind,
            passed=False,
            http_status=None,
            elapsed_ms=0.0,
            expected_message=str(expected_message),
            actual_message=None,
            expected_match_count=expected_match_count,
            error="Input message is missing or is not a string",
        )

    if not isinstance(expected_message, str):
        return TestResult(
            record_id=record_id,
            kind=kind,
            passed=False,
            http_status=None,
            elapsed_ms=0.0,
            expected_message=str(expected_message),
            actual_message=None,
            expected_match_count=expected_match_count,
            error="Expected message is missing or is not a string",
        )

    payload = json.dumps(
        {"message": message},
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    started = time.perf_counter()

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout,
            context=ssl_context,
        ) as response:
            response_body = response.read()
            http_status = response.status

    except urllib.error.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000
        error_body = exc.read().decode("utf-8", errors="replace")

        return TestResult(
            record_id=record_id,
            kind=kind,
            passed=False,
            http_status=exc.code,
            elapsed_ms=elapsed_ms,
            expected_message=expected_message,
            actual_message=None,
            expected_match_count=expected_match_count,
            error=f"HTTP {exc.code}: {error_body}",
        )

    except urllib.error.URLError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000

        return TestResult(
            record_id=record_id,
            kind=kind,
            passed=False,
            http_status=None,
            elapsed_ms=elapsed_ms,
            expected_message=expected_message,
            actual_message=None,
            expected_match_count=expected_match_count,
            error=f"Connection error: {exc.reason}",
        )

    except TimeoutError:
        elapsed_ms = (time.perf_counter() - started) * 1000

        return TestResult(
            record_id=record_id,
            kind=kind,
            passed=False,
            http_status=None,
            elapsed_ms=elapsed_ms,
            expected_message=expected_message,
            actual_message=None,
            expected_match_count=expected_match_count,
            error=f"Request timed out after {timeout} seconds",
        )

    elapsed_ms = (time.perf_counter() - started) * 1000

    try:
        response_json = json.loads(response_body)
    except json.JSONDecodeError as exc:
        return TestResult(
            record_id=record_id,
            kind=kind,
            passed=False,
            http_status=http_status,
            elapsed_ms=elapsed_ms,
            expected_message=expected_message,
            actual_message=None,
            expected_match_count=expected_match_count,
            error=f"Response was not valid JSON: {exc}",
        )

    actual_message = (
        response_json.get("result", {}).get("message")
        if isinstance(response_json, dict)
        else None
    )

    if not isinstance(actual_message, str):
        return TestResult(
            record_id=record_id,
            kind=kind,
            passed=False,
            http_status=http_status,
            elapsed_ms=elapsed_ms,
            expected_message=expected_message,
            actual_message=None,
            expected_match_count=expected_match_count,
            error="Response did not contain result.message",
        )

    passed = actual_message == expected_message

    return TestResult(
        record_id=record_id,
        kind=kind,
        passed=passed,
        http_status=http_status,
        elapsed_ms=elapsed_ms,
        expected_message=expected_message,
        actual_message=actual_message,
        expected_match_count=expected_match_count,
        error=None if passed else "Processed message did not match expected output",
    )


def percentile(values: list[float], percentage: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)

    position = (len(ordered) - 1) * percentage
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index

    return (
        ordered[lower_index]
        + (ordered[upper_index] - ordered[lower_index]) * fraction
    )


def result_to_dict(result: TestResult) -> dict[str, Any]:
    return {
        "record_id": result.record_id,
        "kind": result.kind,
        "passed": result.passed,
        "http_status": result.http_status,
        "elapsed_ms": round(result.elapsed_ms, 3),
        "expected_match_count": result.expected_match_count,
        "error": result.error,
        "expected_message": result.expected_message,
        "actual_message": result.actual_message,
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False) + "\n"
            )


def main() -> int:
    args = parse_args()

    try:
        input_rows = read_jsonl(args.input)
        expected_rows = read_jsonl(args.expected)

        inputs = index_by_record_id(input_rows, str(args.input))
        expected = index_by_record_id(expected_rows, str(args.expected))

        validate_datasets(inputs, expected)

        ordered_record_ids = [
            row["record_id"] for row in input_rows
        ]

        if args.limit is not None:
            if args.limit < 1:
                raise ValueError("--limit must be at least 1")

            ordered_record_ids = ordered_record_ids[: args.limit]

        args.report_dir.mkdir(parents=True, exist_ok=True)

        ssl_context = build_ssl_context(args.insecure)

        started_at = datetime.now(timezone.utc)
        suite_started = time.perf_counter()

        results: list[TestResult] = []

        total_records = len(ordered_record_ids)

        print("Nol8 Functional Scale Test")
        print()
        print(f"Endpoint:  {args.endpoint}")
        print(f"Records:   {total_records}")
        print()

        for index, record_id in enumerate(
            ordered_record_ids,
            start=1,
        ):
            result = process_record(
                endpoint=args.endpoint,
                input_row=inputs[record_id],
                expected_row=expected[record_id],
                timeout=args.timeout,
                ssl_context=ssl_context,
            )

            results.append(result)

            if (
                index % args.progress_every == 0
                or index == total_records
            ):
                passed_so_far = sum(
                    item.passed for item in results
                )

                failed_so_far = len(results) - passed_so_far

                print(
                    f"Processed {index:>5}/{total_records} "
                    f"| Passed: {passed_so_far:>5} "
                    f"| Failed: {failed_so_far:>5}"
                )

        suite_elapsed = time.perf_counter() - suite_started
        completed_at = datetime.now(timezone.utc)

        passed_results = [
            result for result in results if result.passed
        ]

        failed_results = [
            result for result in results if not result.passed
        ]

        latencies = [
            result.elapsed_ms for result in results
        ]

        kind_totals = Counter(
            result.kind for result in results
        )

        kind_failures = Counter(
            result.kind
            for result in failed_results
        )

        expected_total_matches = sum(
            result.expected_match_count for result in results
        )

        timestamp = completed_at.strftime("%Y%m%dT%H%M%SZ")

        summary_path = (
            args.report_dir
            / f"functional-summary-{timestamp}.json"
        )

        failures_path = (
            args.report_dir
            / f"functional-failures-{timestamp}.jsonl"
        )

        all_results_path = (
            args.report_dir
            / f"functional-results-{timestamp}.jsonl"
        )

        summary = {
            "test_type": "functional",
            "endpoint": args.endpoint,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_seconds": round(suite_elapsed, 3),
            "records_processed": len(results),
            "records_passed": len(passed_results),
            "records_failed": len(failed_results),
            "pass_rate_percent": round(
                (
                    len(passed_results)
                    / len(results)
                    * 100
                )
                if results
                else 0.0,
                3,
            ),
            "expected_total_matches": expected_total_matches,
            "record_kinds": dict(sorted(kind_totals.items())),
            "failures_by_kind": dict(
                sorted(kind_failures.items())
            ),
            "latency_ms": {
                "minimum": round(min(latencies), 3)
                if latencies
                else 0.0,
                "average": round(
                    sum(latencies) / len(latencies),
                    3,
                )
                if latencies
                else 0.0,
                "p50": round(
                    percentile(latencies, 0.50),
                    3,
                ),
                "p95": round(
                    percentile(latencies, 0.95),
                    3,
                ),
                "p99": round(
                    percentile(latencies, 0.99),
                    3,
                ),
                "maximum": round(max(latencies), 3)
                if latencies
                else 0.0,
            },
            "reports": {
                "summary": str(summary_path),
                "all_results": str(all_results_path),
                "failures": str(failures_path),
            },
        }

        summary_path.write_text(
            json.dumps(
                summary,
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        write_jsonl(
            all_results_path,
            [result_to_dict(result) for result in results],
        )

        write_jsonl(
            failures_path,
            [
                result_to_dict(result)
                for result in failed_results
            ],
        )

        print()
        print("Functional Test Summary")
        print()
        print(
            f"Records processed:       {len(results)}"
        )
        print(
            f"Records passed:          {len(passed_results)}"
        )
        print(
            f"Records failed:          {len(failed_results)}"
        )
        print(
            f"Pass rate:               "
            f"{summary['pass_rate_percent']:.3f}%"
        )
        print(
            f"Expected replacements:   {expected_total_matches}"
        )
        print(
            f"Total duration:          "
            f"{suite_elapsed:.3f} seconds"
        )
        print()
        print(
            f"Latency average:         "
            f"{summary['latency_ms']['average']:.3f} ms"
        )
        print(
            f"Latency p50:             "
            f"{summary['latency_ms']['p50']:.3f} ms"
        )
        print(
            f"Latency p95:             "
            f"{summary['latency_ms']['p95']:.3f} ms"
        )
        print(
            f"Latency p99:             "
            f"{summary['latency_ms']['p99']:.3f} ms"
        )
        print()
        print(f"Summary:   {summary_path}")
        print(f"Results:   {all_results_path}")
        print(f"Failures:  {failures_path}")

        return 0 if not failed_results else 1

    except (
        FileNotFoundError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            f"Functional test failed: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
