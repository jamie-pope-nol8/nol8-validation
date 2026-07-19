from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import yaml

from framework.policy.generate_functional_test import generate_functional_artifacts
from framework.reporting.generate_report import aggregate_evidence, render_report_html
from framework.workload.generate_scale_artifacts import (
    generate_scale_artifacts,
    is_scale_workload,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class PolicyDeploymentError(Exception):
    def __init__(
        self,
        category: str,
        message: str,
        *,
        http_status: int | None = None,
        response: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.http_status = http_status
        self.response = response or {}


class RunExecutionError(Exception):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


class ComparisonError(Exception):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


class ReportingError(Exception):
    def __init__(self, category: str, message: str):
        super().__init__(message)
        self.category = category


def utc_now() -> datetime:
    return datetime.now(UTC)


def run_id_from_datetime(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def write_manifest_atomic(path: Path, manifest: dict[str, Any]) -> None:
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, path)


def artifact_metadata(run_directory: Path, relative_path: Path) -> dict[str, Any]:
    path = run_directory / relative_path
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return {
        "path": relative_path.as_posix(),
        "sha256": digest.hexdigest(),
        "size_bytes": path.stat().st_size,
    }


def _source_display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)


def create_run_directory(runs_directory: Path) -> tuple[str, Path, datetime]:
    runs_directory.mkdir(parents=True, exist_ok=True)

    while True:
        created_at = utc_now()
        run_id = run_id_from_datetime(created_at)
        run_directory = runs_directory / run_id

        try:
            run_directory.mkdir()
        except FileExistsError:
            continue

        return run_id, run_directory, created_at


def generate_run(
    config_path: Path,
    runs_directory: Path,
    *,
    scale_progress_callback: Callable[[str, int, int], None] | None = None,
    rule_count_override: int | None = None,
    record_count_override: int | None = None,
) -> tuple[str, Path]:
    run_id, run_directory, created = create_run_directory(runs_directory)
    created_at = isoformat_utc(created)
    manifest_path = run_directory / "manifest.json"
    snapshot_relative = Path("config") / config_path.name
    generated_directory = run_directory / "generated"

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "run_type": "functional",
        "status": "generating",
        "created_at": created_at,
        "updated_at": created_at,
        "repository_root": ".",
        "configuration": {
            "source": _source_display_path(config_path),
            "snapshot": snapshot_relative.as_posix(),
        },
        "artifacts": {},
        "stages": {
            "generation": {
                "status": "in_progress",
                "started_at": created_at,
                "generator": "framework.policy.generate_functional_test",
            },
            "policy": {"status": "pending"},
            "execution": {"status": "pending"},
            "comparison": {"status": "pending"},
            "reporting": {"status": "pending"},
        },
    }
    write_manifest_atomic(manifest_path, manifest)

    try:
        snapshot_path = run_directory / snapshot_relative
        snapshot_path.parent.mkdir(parents=True)
        shutil.copyfile(config_path, snapshot_path)
        generated_directory.mkdir()

        loaded_config = yaml.safe_load(snapshot_path.read_text(encoding="utf-8"))
        if not isinstance(loaded_config, dict):
            raise ValueError("The YAML configuration must contain a mapping.")
        if is_scale_workload(loaded_config):
            if rule_count_override is not None:
                loaded_config["policy"]["rule_count"] = rule_count_override
            if record_count_override is not None:
                loaded_config["documents"]["count"] = record_count_override
            if rule_count_override is not None or record_count_override is not None:
                snapshot_path.write_text(
                    yaml.safe_dump(loaded_config, sort_keys=False),
                    encoding="utf-8",
                )
            manifest["run_type"] = "scale"
            manifest["stages"]["generation"]["generator"] = (
                "framework.workload.generate_scale_artifacts"
            )
            generate_scale_artifacts(
                snapshot_path,
                generated_directory,
                progress_callback=scale_progress_callback,
            )
        else:
            if rule_count_override is not None or record_count_override is not None:
                raise ValueError(
                    "--rules and --records apply only to scale workload configurations."
                )
            generate_functional_artifacts(snapshot_path, generated_directory)
        os.replace(
            generated_directory / "manifest.json",
            generated_directory / "generation-manifest.json",
        )

        artifact_paths = {
            "configuration": snapshot_relative,
            "policy": Path("generated/scale-policy.nol"),
            "input": Path("generated/input.jsonl"),
            "expected": Path("generated/expected.jsonl"),
            "generation_manifest": Path("generated/generation-manifest.json"),
        }
        manifest["artifacts"] = {
            name: artifact_metadata(run_directory, path)
            for name, path in artifact_paths.items()
        }

        completed_at = isoformat_utc(utc_now())
        manifest["status"] = "generated"
        manifest["updated_at"] = completed_at
        manifest["stages"]["generation"].update(
            {"status": "completed", "completed_at": completed_at}
        )
        write_manifest_atomic(manifest_path, manifest)
        return run_id, run_directory

    except Exception as error:
        failed_at = isoformat_utc(utc_now())
        manifest["status"] = "failed"
        manifest["updated_at"] = failed_at
        manifest["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
        manifest["stages"]["generation"].update(
            {
                "status": "failed",
                "completed_at": failed_at,
                "error": manifest["error"],
            }
        )
        write_manifest_atomic(manifest_path, manifest)
        raise


def _policy_path(run_directory: Path, manifest: dict[str, Any]) -> tuple[Path, str]:
    generation = manifest.get("stages", {}).get("generation", {})
    if generation.get("status") != "completed":
        raise PolicyDeploymentError(
            "prerequisite", "Run generation has not completed successfully."
        )

    policy_artifact = manifest.get("artifacts", {}).get("policy")
    if not isinstance(policy_artifact, dict):
        raise PolicyDeploymentError(
            "prerequisite", "Run manifest does not describe a policy artifact."
        )

    relative_value = policy_artifact.get("path")
    if not isinstance(relative_value, str) or not relative_value:
        raise PolicyDeploymentError(
            "prerequisite", "Run manifest has an invalid policy artifact path."
        )

    relative_path = Path(relative_value)
    if relative_path.is_absolute():
        raise PolicyDeploymentError(
            "prerequisite", "Policy artifact path must be relative to the Run."
        )

    run_root = run_directory.resolve()
    policy_path = (run_directory / relative_path).resolve()
    try:
        policy_path.relative_to(run_root)
    except ValueError as error:
        raise PolicyDeploymentError(
            "prerequisite", "Policy artifact path escapes the Run directory."
        ) from error

    if not policy_path.is_file():
        raise PolicyDeploymentError(
            "prerequisite", f"Generated policy does not exist: {relative_value}"
        )

    policy_sha256 = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    recorded_sha256 = policy_artifact.get("sha256")
    if recorded_sha256 and recorded_sha256 != policy_sha256:
        raise PolicyDeploymentError(
            "integrity", "Generated policy SHA-256 does not match the Run manifest."
        )

    return policy_path, policy_sha256


def _sanitize_themis_response(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {}

    allowed_fields = (
        "ok",
        "command_id",
        "stage",
        "message",
        "error_code",
        "apollo_response",
        "rules",
    )
    sanitized: dict[str, Any] = {}
    for key in allowed_fields:
        if key not in response:
            continue
        value = response[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[key] = value
    return sanitized


def deploy_policy(policy_path: Path, target: str) -> tuple[int, dict[str, Any]]:
    deployment_script = REPOSITORY_ROOT / "scripts" / "load-policy.sh"
    result = subprocess.run(
        [str(deployment_script), target, str(policy_path)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    failure_categories = {
        2: ("configuration", "Policy deployment configuration is invalid."),
        3: ("authentication", "Policy deployment credentials are not configured."),
        4: ("authentication", "Policy deployment authentication was rejected."),
        5: ("network", "Policy deployment could not reach the target service."),
        6: ("deployment", "The target service rejected the policy deployment."),
    }
    if result.returncode != 0:
        category, message = failure_categories.get(
            result.returncode,
            ("deployment", "Policy deployment failed."),
        )
        raise PolicyDeploymentError(category, message)

    try:
        parsed = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise PolicyDeploymentError(
            "deployment", "Policy deployment returned an invalid response."
        )

    if not isinstance(parsed, dict):
        raise PolicyDeploymentError(
            "deployment", "Policy deployment returned an invalid response."
        )

    http_status = parsed.get("http_status")
    if not isinstance(http_status, int):
        raise PolicyDeploymentError(
            "deployment", "Policy deployment response did not include HTTP status."
        )

    response = _sanitize_themis_response(parsed.get("response"))
    if response.get("ok") is not True:
        service_message = response.get("message", "Themis did not confirm deployment.")
        error_code = response.get("error_code", "unavailable")
        raise PolicyDeploymentError(
            "deployment",
            f"{service_message} (error_code: {error_code})",
            http_status=http_status,
            response=response,
        )

    return http_status, response


def apply_policy_to_run(run_directory: Path, target: str) -> dict[str, Any]:
    if not run_directory.is_dir():
        raise PolicyDeploymentError(
            "prerequisite", f"Run directory does not exist: {run_directory}"
        )

    manifest_path = run_directory / "manifest.json"
    if not manifest_path.is_file():
        raise PolicyDeploymentError(
            "prerequisite", f"Run manifest does not exist: {manifest_path}"
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PolicyDeploymentError(
            "prerequisite", f"Run manifest is not valid JSON: {error}"
        ) from error

    if not isinstance(manifest, dict):
        raise PolicyDeploymentError(
            "prerequisite", "Run manifest must contain a JSON object."
        )

    started_at = isoformat_utc(utc_now())
    policy_stage: dict[str, Any] = {
        "status": "in_progress",
        "target": target,
        "started_at": started_at,
    }
    manifest.setdefault("stages", {})["policy"] = policy_stage
    manifest["updated_at"] = started_at
    write_manifest_atomic(manifest_path, manifest)

    try:
        policy_path, policy_sha256 = _policy_path(run_directory, manifest)
        relative_policy_path = policy_path.relative_to(run_directory.resolve()).as_posix()
        policy_stage.update(
            {
                "policy_path": relative_policy_path,
                "policy_sha256": policy_sha256,
            }
        )
        http_status, response = deploy_policy(policy_path, target)

        completed_at = isoformat_utc(utc_now())
        policy_stage.update(
            {
                "status": "completed",
                "completed_at": completed_at,
                "http_status": http_status,
                "response": response,
            }
        )
        manifest["status"] = "policy_deployed"
        manifest["updated_at"] = completed_at
        write_manifest_atomic(manifest_path, manifest)
        return manifest

    except PolicyDeploymentError as error:
        failed_at = isoformat_utc(utc_now())
        policy_stage.update(
            {
                "status": "failed",
                "completed_at": failed_at,
                "error": {
                    "category": error.category,
                    "message": str(error),
                },
            }
        )
        if error.http_status is not None:
            policy_stage["http_status"] = error.http_status
        if error.response:
            policy_stage["response"] = error.response
        manifest["status"] = "policy_failed"
        manifest["updated_at"] = failed_at
        write_manifest_atomic(manifest_path, manifest)
        raise


def _check_run_target(target: str) -> None:
    execution_script = REPOSITORY_ROOT / "scripts" / "run-validation.sh"
    result = subprocess.run(
        [str(execution_script), "--check", target],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RunExecutionError(
            "configuration", "Processing endpoint configuration is invalid."
        )


def execute_request(target: str, payload: dict[str, str]) -> dict[str, Any]:
    execution_script = REPOSITORY_ROOT / "scripts" / "run-validation.sh"
    result = subprocess.run(
        [str(execution_script), target],
        cwd=REPOSITORY_ROOT,
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        check=False,
    )

    parsed: dict[str, Any] = {}
    if result.stdout:
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, dict):
            parsed = value

    if result.returncode == 5:
        raise RunExecutionError(
            "network", "Processing endpoint request failed."
        )

    http_status = parsed.get("http_status")
    latency_ms = parsed.get("latency_ms", 0.0)
    response = parsed.get("response")
    success = (
        result.returncode == 0
        and isinstance(http_status, int)
        and 200 <= http_status < 300
    )
    return {
        "http_status": http_status if isinstance(http_status, int) else None,
        "latency_ms": round(float(latency_ms), 3)
        if isinstance(latency_ms, (int, float))
        else 0.0,
        "success": success,
        "response": response,
    }


def _write_jsonl_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary_path = path.with_name(f".{path.name}.tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(temporary_path, path)


def _initialize_jsonl_atomic(path: Path) -> None:
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_bytes(b"")
    os.replace(temporary_path, path)


def _append_jsonl_durable(path: Path, row: dict[str, Any]) -> None:
    encoded = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
    with path.open("ab", buffering=0) as handle:
        handle.write(encoded)
        os.fsync(handle.fileno())


def _repair_jsonl_tail(path: Path) -> None:
    if not path.is_file():
        return
    data = path.read_bytes()
    if not data or data.endswith(b"\n"):
        return
    last_complete = data.rfind(b"\n")
    repaired = data[: last_complete + 1] if last_complete >= 0 else b""
    temporary_path = path.with_name(f".{path.name}.repair")
    temporary_path.write_bytes(repaired)
    os.replace(temporary_path, path)


def run_validation_corpus(
    run_directory: Path,
    target: str,
    *,
    progress_callback: Callable[[int, int, int, int], None] | None = None,
    startup_callback: Callable[[int, int | None], None] | None = None,
    progress_interval: int = 50,
    limit: int | None = None,
) -> dict[str, Any]:
    if progress_interval < 1:
        raise ValueError("Progress interval must be at least 1.")
    if limit is not None and limit < 1:
        raise ValueError("Request limit must be at least 1.")

    if not run_directory.is_dir():
        raise RunExecutionError(
            "prerequisite", f"Run directory does not exist: {run_directory}"
        )

    manifest_path = run_directory / "manifest.json"
    if not manifest_path.is_file():
        raise RunExecutionError(
            "prerequisite", f"Run manifest does not exist: {manifest_path}"
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RunExecutionError(
            "prerequisite", f"Run manifest is not valid JSON: {error}"
        ) from error
    if not isinstance(manifest, dict):
        raise RunExecutionError(
            "prerequisite", "Run manifest must contain a JSON object."
        )

    started_at = isoformat_utc(utc_now())
    run_stage: dict[str, Any] = {
        "status": "in_progress",
        "target": target,
        "started_at": started_at,
        "requests_total": 0,
        "requests_completed": 0,
        "requests_failed": 0,
        "output_path": "generated/output.jsonl",
    }
    manifest.setdefault("stages", {})["run"] = run_stage
    manifest["updated_at"] = started_at
    write_manifest_atomic(manifest_path, manifest)

    suite_started = time.perf_counter()
    output_path = run_directory / run_stage["output_path"]
    output_rows: list[dict[str, Any]] = []
    stage_failure: RunExecutionError | None = None
    succeeded_so_far = 0
    failed_so_far = 0

    try:
        generation = manifest.get("stages", {}).get("generation", {})
        if generation.get("status") != "completed":
            raise RunExecutionError(
                "prerequisite", "Run generation has not completed successfully."
            )
        policy = manifest.get("stages", {}).get("policy", {})
        if policy.get("status") != "completed":
            raise RunExecutionError(
                "prerequisite", "Policy deployment has not completed successfully."
            )

        relative_input = "generated/input.jsonl"
        input_path = run_directory / relative_input
        if not input_path.is_file():
            raise RunExecutionError(
                "prerequisite", f"Generated input corpus does not exist: {relative_input}"
            )

        lines = input_path.read_text(encoding="utf-8").splitlines()
        execution_lines = lines if limit is None else lines[:limit]
        run_stage["requests_total"] = len(execution_lines)
        manifest["updated_at"] = isoformat_utc(utc_now())
        write_manifest_atomic(manifest_path, manifest)
        _initialize_jsonl_atomic(output_path)
        if startup_callback is not None:
            startup_callback(len(lines), limit)
        _check_run_target(target)

        for request_index, line in enumerate(execution_lines, start=1):
            request_result: dict[str, Any]
            try:
                request = json.loads(line)
                if not isinstance(request, dict) or not isinstance(
                    request.get("message"), str
                ):
                    raise ValueError("request must contain a string message")
                request_result = execute_request(
                    target, {"message": request["message"]}
                )
            except (json.JSONDecodeError, ValueError):
                request_result = {
                    "http_status": None,
                    "latency_ms": 0.0,
                    "success": False,
                    "response": None,
                    "error": {
                        "category": "malformed_request",
                        "message": "Request is not valid corpus JSON.",
                    },
                }
                if stage_failure is None:
                    stage_failure = RunExecutionError(
                        "malformed_request",
                        "The input corpus contains one or more malformed requests.",
                    )
            except RunExecutionError as error:
                request_result = {
                    "http_status": None,
                    "latency_ms": 0.0,
                    "success": False,
                    "response": None,
                    "error": {
                        "category": error.category,
                        "message": str(error),
                    },
                }
                if stage_failure is None:
                    stage_failure = error

            output_row = {"request_index": request_index, **request_result}
            _append_jsonl_durable(output_path, output_row)
            output_rows.append(output_row)
            if request_result["success"]:
                succeeded_so_far += 1
            else:
                failed_so_far += 1
            run_stage["requests_completed"] = request_index
            run_stage["requests_failed"] = failed_so_far
            manifest["updated_at"] = isoformat_utc(utc_now())
            write_manifest_atomic(manifest_path, manifest)
            if progress_callback is not None and (
                request_index == 1
                or request_index % progress_interval == 0
                or request_index == len(execution_lines)
            ):
                progress_callback(
                    request_index,
                    len(execution_lines),
                    succeeded_so_far,
                    failed_so_far,
                )

        failed_count = sum(not row["success"] for row in output_rows)
        run_stage["requests_completed"] = len(output_rows)
        run_stage["requests_failed"] = failed_count
        latencies = [float(row["latency_ms"]) for row in output_rows]
        run_stage["average_latency_ms"] = round(
            sum(latencies) / len(latencies), 3
        ) if latencies else 0.0
        run_stage["total_runtime_seconds"] = round(
            time.perf_counter() - suite_started, 3
        )

        completed_at = isoformat_utc(utc_now())
        run_stage["completed_at"] = completed_at
        manifest["updated_at"] = completed_at
        if stage_failure is None:
            run_stage["status"] = "completed"
            manifest["status"] = "run_completed"
        else:
            run_stage["status"] = "failed"
            run_stage["error"] = {
                "category": stage_failure.category,
                "message": str(stage_failure),
            }
            manifest["status"] = "run_failed"
        write_manifest_atomic(manifest_path, manifest)
        if stage_failure is not None:
            raise stage_failure
        return manifest

    except RunExecutionError as error:
        if run_stage.get("status") != "failed":
            failed_at = isoformat_utc(utc_now())
            run_stage.update(
                {
                    "status": "failed",
                    "completed_at": failed_at,
                    "error": {"category": error.category, "message": str(error)},
                }
            )
            manifest["status"] = "run_failed"
            manifest["updated_at"] = failed_at
            write_manifest_atomic(manifest_path, manifest)
        raise
    except BaseException as error:
        _repair_jsonl_tail(output_path)
        persisted_rows = (
            _read_comparison_jsonl(output_path, "output.jsonl")
            if output_path.is_file()
            else []
        )
        failed_at = isoformat_utc(utc_now())
        run_stage.update(
            {
                "status": "failed",
                "completed_at": failed_at,
                "requests_completed": len(persisted_rows),
                "requests_failed": sum(
                    row.get("success") is not True for row in persisted_rows
                ),
                "error": {
                    "category": (
                        "interrupted"
                        if isinstance(error, (KeyboardInterrupt, SystemExit))
                        else "execution"
                    ),
                    "message": (
                        "Run execution was interrupted."
                        if isinstance(error, (KeyboardInterrupt, SystemExit))
                        else str(error)
                    ),
                },
            }
        )
        manifest["status"] = "run_failed"
        manifest["updated_at"] = failed_at
        write_manifest_atomic(manifest_path, manifest)
        raise


def _read_comparison_jsonl(path: Path, artifact_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ComparisonError(
            "artifact", f"Unable to read {artifact_name}: {error}"
        ) from error

    for line_number, line in enumerate(lines, start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ComparisonError(
                "artifact",
                f"Invalid JSON in {artifact_name} at line {line_number}: {error}",
            ) from error
        if not isinstance(row, dict):
            raise ComparisonError(
                "artifact",
                f"Expected a JSON object in {artifact_name} at line {line_number}.",
            )
        rows.append(row)
    return rows


def _normalize_expected_replacements(
    expected_message: Any,
    expected_matches: Any,
    replacement_max_length: int | None,
) -> Any:
    if (
        replacement_max_length is None
        or not isinstance(expected_message, str)
        or not isinstance(expected_matches, list)
    ):
        return expected_message

    replacements = {
        match.get("replacement")
        for match in expected_matches
        if isinstance(match, dict)
        and isinstance(match.get("replacement"), str)
        and match.get("replacement")
    }
    normalized = expected_message
    for replacement in sorted(replacements, key=lambda value: (-len(value), value)):
        normalized = normalized.replace(
            replacement,
            replacement[:replacement_max_length],
        )
    return normalized


def compare_run(
    run_directory: Path,
    *,
    replacement_max_length: int | None = None,
) -> dict[str, Any]:
    if replacement_max_length is not None and replacement_max_length < 1:
        raise ComparisonError(
            "configuration", "Replacement maximum length must be at least 1."
        )
    if not run_directory.is_dir():
        raise ComparisonError(
            "prerequisite", f"Run directory does not exist: {run_directory}"
        )

    manifest_path = run_directory / "manifest.json"
    if not manifest_path.is_file():
        raise ComparisonError(
            "prerequisite", f"Run manifest does not exist: {manifest_path}"
        )

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ComparisonError(
            "prerequisite", f"Run manifest is not valid JSON: {error}"
        ) from error
    if not isinstance(manifest, dict):
        raise ComparisonError(
            "prerequisite", "Run manifest must contain a JSON object."
        )

    started_at = isoformat_utc(utc_now())
    comparison_stage: dict[str, Any] = {
        "status": "in_progress",
        "started_at": started_at,
        "output_path": "generated/comparison.jsonl",
    }
    if replacement_max_length is not None:
        comparison_stage["replacement_max_length"] = replacement_max_length
    manifest.setdefault("stages", {})["comparison"] = comparison_stage
    manifest["updated_at"] = started_at
    write_manifest_atomic(manifest_path, manifest)

    try:
        stages = manifest.get("stages", {})
        if stages.get("generation", {}).get("status") != "completed":
            raise ComparisonError(
                "prerequisite", "Run generation has not completed successfully."
            )
        if stages.get("policy", {}).get("status") != "completed":
            raise ComparisonError(
                "prerequisite", "Policy deployment has not completed successfully."
            )
        run_status = stages.get("run", {}).get("status")
        execution_status = stages.get("execution", {}).get("status")
        if run_status != "completed" and execution_status != "completed":
            raise ComparisonError(
                "prerequisite", "Run execution has not completed successfully."
            )

        artifact_paths = {
            "input": run_directory / "generated/input.jsonl",
            "expected": run_directory / "generated/expected.jsonl",
            "output": run_directory / "generated/output.jsonl",
        }
        for artifact_name, artifact_path in artifact_paths.items():
            if not artifact_path.is_file():
                raise ComparisonError(
                    "prerequisite",
                    f"Required comparison artifact does not exist: "
                    f"generated/{artifact_path.name}",
                )

        input_rows = _read_comparison_jsonl(artifact_paths["input"], "input.jsonl")
        expected_rows = _read_comparison_jsonl(
            artifact_paths["expected"], "expected.jsonl"
        )
        output_rows = _read_comparison_jsonl(artifact_paths["output"], "output.jsonl")

        row_count = len(input_rows)
        if len(expected_rows) != row_count or len(output_rows) != row_count:
            raise ComparisonError(
                "alignment",
                "Input, expected, and output row counts must match.",
            )

        request_indexes = [row.get("request_index") for row in output_rows]
        if request_indexes != list(range(1, row_count + 1)):
            raise ComparisonError(
                "alignment", "Output request_index values must be exactly 1..N."
            )

        def index_records(
            rows: list[dict[str, Any]], artifact_name: str
        ) -> dict[str, dict[str, Any]]:
            indexed: dict[str, dict[str, Any]] = {}
            for row in rows:
                record_id = row.get("record_id")
                if not isinstance(record_id, str) or not record_id:
                    raise ComparisonError(
                        "alignment", f"{artifact_name} contains an invalid record_id."
                    )
                if record_id in indexed:
                    raise ComparisonError(
                        "alignment",
                        f"{artifact_name} contains duplicate record_id {record_id!r}.",
                    )
                indexed[record_id] = row
            return indexed

        input_by_id = index_records(input_rows, "input.jsonl")
        expected_by_id = index_records(expected_rows, "expected.jsonl")
        if set(input_by_id) != set(expected_by_id):
            raise ComparisonError(
                "alignment", "Input and expected record_id sets must match."
            )

        comparison_rows: list[dict[str, Any]] = []
        status_counts = {
            "PASS": 0,
            "CONTENT_MISMATCH": 0,
            "EXECUTION_FAILURE": 0,
        }
        for request_index, output_row in enumerate(output_rows, start=1):
            input_row = input_rows[request_index - 1]
            record_id = input_row["record_id"]
            expected_row = expected_by_id[record_id]
            expected_matches = expected_row.get("expected_matches")
            expected_message = _normalize_expected_replacements(
                expected_row.get("expected_message"),
                expected_matches,
                replacement_max_length,
            )
            response = output_row.get("response")
            actual_message = (
                response.get("message") if isinstance(response, dict) else None
            )

            execution_succeeded = (
                output_row.get("success") is True
                and isinstance(output_row.get("http_status"), int)
                and 200 <= output_row["http_status"] < 300
                and isinstance(actual_message, str)
            )
            if not execution_succeeded:
                status = "EXECUTION_FAILURE"
                error = "Request execution did not produce a valid processed message."
            elif actual_message != expected_message:
                status = "CONTENT_MISMATCH"
                error = "Processed message did not match expected output."
            else:
                status = "PASS"
                error = None

            status_counts[status] += 1
            comparison_rows.append(
                {
                    "request_index": request_index,
                    "record_id": record_id,
                    "kind": expected_row.get("kind"),
                    "status": status,
                    "http_status": output_row.get("http_status"),
                    "latency_ms": output_row.get("latency_ms"),
                    "expected_message": expected_message,
                    "actual_message": actual_message,
                    "expected_match_count": expected_row.get(
                        "expected_match_count"
                    ),
                    "expected_matches": expected_matches,
                    "error": error,
                }
            )

        comparison_relative = Path("generated/comparison.jsonl")
        _write_jsonl_atomic(run_directory / comparison_relative, comparison_rows)
        manifest.setdefault("artifacts", {})["comparison"] = artifact_metadata(
            run_directory, comparison_relative
        )

        completed_at = isoformat_utc(utc_now())
        comparison_stage.update(
            {
                "status": "completed",
                "completed_at": completed_at,
                "records_total": row_count,
                "records_passed": status_counts["PASS"],
                "content_mismatches": status_counts["CONTENT_MISMATCH"],
                "execution_failures": status_counts["EXECUTION_FAILURE"],
            }
        )
        manifest["status"] = "comparison_completed"
        manifest["updated_at"] = completed_at
        write_manifest_atomic(manifest_path, manifest)
        return manifest

    except ComparisonError as error:
        failed_at = isoformat_utc(utc_now())
        comparison_stage.update(
            {
                "status": "failed",
                "completed_at": failed_at,
                "error": {"category": error.category, "message": str(error)},
            }
        )
        manifest["status"] = "comparison_failed"
        manifest["updated_at"] = failed_at
        write_manifest_atomic(manifest_path, manifest)
        raise


def report_run(run_directory: Path) -> dict[str, Any]:
    if not run_directory.is_dir():
        raise ReportingError(
            "prerequisite", f"Run directory does not exist: {run_directory}"
        )

    manifest_path = run_directory / "manifest.json"
    if not manifest_path.is_file():
        raise ReportingError(
            "prerequisite", f"Run manifest does not exist: {manifest_path}"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ReportingError(
            "prerequisite", f"Run manifest is not valid JSON: {error}"
        ) from error
    if not isinstance(manifest, dict):
        raise ReportingError("prerequisite", "Run manifest must contain a JSON object.")

    started_at = isoformat_utc(utc_now())
    reporting_stage: dict[str, Any] = {
        "status": "in_progress",
        "started_at": started_at,
        "output_path": "reports/validation-report.html",
    }
    manifest.setdefault("stages", {})["reporting"] = reporting_stage
    manifest["updated_at"] = started_at
    write_manifest_atomic(manifest_path, manifest)

    try:
        comparison_stage = manifest.get("stages", {}).get("comparison", {})
        if comparison_stage.get("status") != "completed":
            raise ReportingError(
                "prerequisite", "Run comparison has not completed successfully."
            )
        artifacts = manifest.get("artifacts", {})
        comparison_metadata = artifacts.get("comparison", {})
        generation_metadata = artifacts.get("generation_manifest", {})
        comparison_relative = comparison_metadata.get("path")
        generation_relative = generation_metadata.get("path")
        if not isinstance(comparison_relative, str):
            raise ReportingError("prerequisite", "Comparison artifact is not registered.")
        if not isinstance(generation_relative, str):
            raise ReportingError(
                "prerequisite", "Generation manifest artifact is not registered."
            )
        comparison_path = run_directory / comparison_relative
        generation_path = run_directory / generation_relative
        if not comparison_path.is_file():
            raise ReportingError(
                "artifact", f"Comparison artifact does not exist: {comparison_relative}"
            )
        if not generation_path.is_file():
            raise ReportingError(
                "artifact", f"Generation manifest does not exist: {generation_relative}"
            )
        comparison_rows = _read_comparison_jsonl(
            comparison_path, "comparison.jsonl"
        )
        try:
            generation = json.loads(generation_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ReportingError(
                "artifact", f"Generation manifest is not valid JSON: {error}"
            ) from error
        if not isinstance(generation, dict):
            raise ReportingError(
                "artifact", "Generation manifest must contain a JSON object."
            )

        evidence = aggregate_evidence(manifest, generation, comparison_rows)
        rendered = render_report_html(evidence)
        report_relative = Path(reporting_stage["output_path"])
        report_path = run_directory / report_relative
        report_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = report_path.with_name(f".{report_path.name}.tmp")
        temporary_path.write_text(rendered, encoding="utf-8")
        os.replace(temporary_path, report_path)
        manifest.setdefault("artifacts", {})["report"] = artifact_metadata(
            run_directory, report_relative
        )

        completed_at = isoformat_utc(utc_now())
        reporting_stage.update(
            {
                "status": "completed",
                "completed_at": completed_at,
                "records_total": evidence["total"],
                "records_passed": evidence["passed"],
                "records_failed": evidence["failed"],
            }
        )
        manifest["status"] = "report_completed"
        manifest["updated_at"] = completed_at
        write_manifest_atomic(manifest_path, manifest)
        return manifest
    except (ReportingError, ComparisonError) as error:
        reporting_error = (
            error
            if isinstance(error, ReportingError)
            else ReportingError("artifact", str(error))
        )
        failed_at = isoformat_utc(utc_now())
        reporting_stage.update(
            {
                "status": "failed",
                "completed_at": failed_at,
                "error": {
                    "category": reporting_error.category,
                    "message": str(reporting_error),
                },
            }
        )
        manifest["status"] = "report_failed"
        manifest["updated_at"] = failed_at
        write_manifest_atomic(manifest_path, manifest)
        raise reporting_error
    except OSError as error:
        failed_at = isoformat_utc(utc_now())
        reporting_error = ReportingError("artifact", str(error))
        reporting_stage.update(
            {
                "status": "failed",
                "completed_at": failed_at,
                "error": {
                    "category": reporting_error.category,
                    "message": str(reporting_error),
                },
            }
        )
        manifest["status"] = "report_failed"
        manifest["updated_at"] = failed_at
        write_manifest_atomic(manifest_path, manifest)
        raise reporting_error from error
    except Exception as error:
        failed_at = isoformat_utc(utc_now())
        reporting_error = ReportingError("rendering", str(error))
        reporting_stage.update(
            {
                "status": "failed",
                "completed_at": failed_at,
                "error": {
                    "category": reporting_error.category,
                    "message": str(reporting_error),
                },
            }
        )
        manifest["status"] = "report_failed"
        manifest["updated_at"] = failed_at
        write_manifest_atomic(manifest_path, manifest)
        raise reporting_error from error


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


DEFAULT_RUNS_DIRECTORY = Path("artifacts/runs")


def _run_directory(value: str) -> Path:
    """Resolve --run as either a run directory path or a bare run ID.

    A bare run ID is looked up under artifacts/runs, relative to the working
    directory first and then to the repository root, so the command works from
    anywhere. Unresolvable values are returned unchanged for the caller's
    existing "Run directory does not exist" error.
    """
    candidate = Path(value)
    if candidate.is_dir():
        return candidate
    if candidate.parent == Path("."):
        for base in (DEFAULT_RUNS_DIRECTORY, REPOSITORY_ROOT / DEFAULT_RUNS_DIRECTORY):
            resolved = base / candidate.name
            if resolved.is_dir():
                return resolved
    return candidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="validate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser(
        "generate", help="Create a validation run"
    )
    generate_parser.add_argument(
        "--config", type=Path, required=True, help="Validation generator YAML"
    )
    generate_parser.add_argument(
        "--runs-dir",
        type=Path,
        default=DEFAULT_RUNS_DIRECTORY,
        help="Parent directory for validation runs",
    )
    generate_parser.add_argument(
        "--rules",
        type=_positive_integer,
        help="Override the scale workload rule count",
    )
    generate_parser.add_argument(
        "--records",
        type=_positive_integer,
        help="Override the scale workload record count",
    )

    policy_parser = subparsers.add_parser(
        "policy", help="Deploy the generated policy for a validation run"
    )
    policy_parser.add_argument(
        "--run",
        type=_run_directory,
        required=True,
        help="Existing validation run directory or run ID",
    )
    policy_parser.add_argument(
        "--target",
        choices=("themis", "aergia"),
        default="themis",
        help="Policy deployment target (default: themis)",
    )

    run_parser = subparsers.add_parser(
        "run", help="Execute a generated validation corpus"
    )
    run_parser.add_argument(
        "--run",
        type=_run_directory,
        required=True,
        help="Existing validation run directory or run ID",
    )
    run_parser.add_argument(
        "--target",
        choices=("themis",),
        default="themis",
        help="Processing target (default: themis)",
    )
    run_parser.add_argument(
        "--progress-interval",
        type=_positive_integer,
        default=50,
        help="Requests between progress updates (default: 50)",
    )
    run_parser.add_argument(
        "--limit",
        type=_positive_integer,
        help="Execute only the first N generated requests",
    )

    compare_parser = subparsers.add_parser(
        "compare", help="Compare execution output with expected results"
    )
    compare_parser.add_argument(
        "--run",
        type=_run_directory,
        required=True,
        help="Existing validation run directory or run ID",
    )
    compare_parser.add_argument(
        "--replacement-max-length",
        type=_positive_integer,
        help="Normalize expected replacement literals to at most N characters",
    )
    report_parser = subparsers.add_parser(
        "report", help="Create a portable HTML validation report"
    )
    report_parser.add_argument(
        "--run",
        type=_run_directory,
        required=True,
        help="Existing validation run directory or run ID",
    )
    return parser


class _LiveRunProgress:
    def __init__(self) -> None:
        self.started_at = time.perf_counter()
        self.rendered = False

    def start(self, total: int, limit: int | None) -> None:
        print(f"Requests loaded: {total}", flush=True)
        if limit is not None:
            print(f"Execution limit: {limit}", flush=True)
        print(flush=True)
        print("Starting execution...", flush=True)
        print(flush=True)

    def __call__(
        self,
        processed: int,
        total: int,
        passed: int,
        failed: int,
    ) -> None:
        elapsed = time.perf_counter() - self.started_at
        rate = processed / elapsed if elapsed > 0 else 0.0
        bar_width = 40
        filled = int(bar_width * processed / total) if total else bar_width
        bar = "█" * filled + "-" * (bar_width - filled)
        color = "\033[32m" if failed == 0 else "\033[31m"
        reset = "\033[0m"

        if self.rendered:
            print("\033[2A", end="", flush=True)
        print(
            f"\r\033[2K{color}[{bar}] {processed}/{total}{reset}",
            flush=True,
        )
        print(
            f"\r\033[2K{color}Succeeded: {passed}  Failed: {failed}  "
            f"Rate: {rate:.1f} req/s{reset}",
            flush=True,
        )
        self.rendered = True


class _ScaleGenerationProgress:
    def __init__(self) -> None:
        self.completed = False

    def __call__(self, event: str, completed: int, total: int) -> None:
        if event == "configuration_loaded":
            print("Generating validation workload", flush=True)
            print(flush=True)
            print("Configuration:", flush=True)
            print(f"  Rules requested: {completed}", flush=True)
            print(f"  Records requested: {total}", flush=True)
            print(flush=True)
            print("Step 1/4: Loading workload configuration", flush=True)
            print("Complete", flush=True)
            print(flush=True)
        elif event == "rules_started":
            print("Step 2/4: Building rule catalog", flush=True)
        elif event == "rules_completed":
            print(f"Rules generated: {completed}/{total}", flush=True)
            print(flush=True)
        elif event == "documents_started":
            print("Step 3/4: Generating documents", flush=True)
        elif event == "expected_started":
            print(flush=True)
            print("Calculating expected transformations", flush=True)
        elif event == "documents_progress":
            print(f"Documents generated: {completed}/{total}", flush=True)
        elif event == "expected_progress":
            print(f"Expected records completed: {completed}/{total}", flush=True)
        elif event == "artifacts_started":
            print(flush=True)
            print("Step 4/4: Writing artifacts", flush=True)
        elif event == "complete":
            print("Complete", flush=True)
            print(flush=True)
            self.completed = True


def _cli_percentile(values: list[float], percentage: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentage
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] + (
        ordered[upper_index] - ordered[lower_index]
    ) * fraction


def _read_cli_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        row
        for line in path.read_text(encoding="utf-8").splitlines()
        if isinstance((row := json.loads(line)), dict)
    ]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "generate":
        scale_progress = _ScaleGenerationProgress()
        try:
            run_id, run_directory = generate_run(
                args.config,
                args.runs_dir,
                scale_progress_callback=scale_progress,
                rule_count_override=args.rules,
                record_count_override=args.records,
            )
        except (OSError, KeyError, TypeError, ValueError) as error:
            print(f"Generation failed: {error}", file=sys.stderr)
            return 1

        if scale_progress.completed:
            print("Generation completed")
        else:
            print("Validation run generated")
        print(f"Run ID:        {run_id}")
        print(f"Run directory: {run_directory}")
        return 0

    if args.command == "policy":
        try:
            manifest = apply_policy_to_run(args.run, args.target)
        except PolicyDeploymentError as error:
            print(f"Policy deployment failed: {error}", file=sys.stderr)
            return 1

        policy_stage = manifest["stages"]["policy"]
        response = policy_stage["response"]

        def display_response_value(field: str) -> str:
            if field not in response:
                return "unavailable"
            value = response[field]
            if value is None:
                return "null"
            if isinstance(value, bool):
                return str(value).lower()
            return str(value)

        print("Validation policy deployed")
        print()
        print(f"Run ID:        {manifest.get('run_id', 'unavailable')}")
        print(f"Run directory: {args.run}")
        print(f"Target:        {args.target}")
        print(f"Policy file:   {policy_stage['policy_path']}")
        print(f"Policy SHA256: {policy_stage['policy_sha256']}")
        print(f"HTTP status:   {policy_stage['http_status']}")
        print()
        print("Themis response")
        for field in (
            "ok",
            "command_id",
            "stage",
            "message",
            "error_code",
            "apollo_response",
            "rules",
        ):
            print(f"  {field}: {display_response_value(field)}")
        return 0

    if args.command == "run":
        print("Running validation corpus", flush=True)
        print(flush=True)
        print(f"Run ID: {args.run.name}", flush=True)
        print(f"Target: {args.target}", flush=True)
        print(flush=True)
        progress = _LiveRunProgress()
        try:
            manifest = run_validation_corpus(
                args.run,
                args.target,
                progress_callback=progress,
                startup_callback=progress.start,
                progress_interval=args.progress_interval,
                limit=args.limit,
            )
        except RunExecutionError as error:
            print(f"Run execution failed: {error}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("Run execution interrupted; completed evidence was preserved.", file=sys.stderr)
            return 130

        run_stage = manifest["stages"]["run"]
        succeeded = run_stage["requests_completed"] - run_stage["requests_failed"]
        output_rows = _read_cli_jsonl(args.run / run_stage["output_path"])
        latencies = [
            float(row["latency_ms"])
            for row in output_rows
            if isinstance(row.get("latency_ms"), (int, float))
        ]
        print("Functional Run Summary")
        print()
        print(f"Run ID:        {manifest.get('run_id', 'unavailable')}")
        print(f"Run directory: {args.run}")
        print(f"Target:        {args.target}")
        print()
        print(f"Records processed:  {run_stage['requests_completed']}")
        print(f"Requests succeeded: {succeeded}")
        print(f"Requests failed:    {run_stage['requests_failed']}")
        print()
        print(
            f"Total duration: {run_stage['total_runtime_seconds']:.3f} seconds"
        )
        print()
        print(f"Latency average: {run_stage['average_latency_ms']:.3f} ms")
        print(f"Latency p50:     {_cli_percentile(latencies, 0.50):.3f} ms")
        print(f"Latency p95:     {_cli_percentile(latencies, 0.95):.3f} ms")
        print(f"Latency p99:     {_cli_percentile(latencies, 0.99):.3f} ms")
        print()
        print(f"Output: {run_stage['output_path']}")
        return 0

    if args.command == "compare":
        try:
            manifest = compare_run(
                args.run,
                replacement_max_length=args.replacement_max_length,
            )
        except ComparisonError as error:
            print(f"Comparison failed: {error}", file=sys.stderr)
            return 1

        comparison_stage = manifest["stages"]["comparison"]
        comparison_rows = _read_cli_jsonl(
            args.run / comparison_stage["output_path"]
        )
        expected_replacements = sum(
            int(row.get("expected_match_count", 0))
            for row in comparison_rows
        )
        records_total = comparison_stage["records_total"]
        pass_rate = (
            comparison_stage["records_passed"] / records_total * 100
            if records_total
            else 0.0
        )
        clean_records = sum(row.get("kind") == "clean" for row in comparison_rows)
        dirty_records = sum(row.get("kind") == "dirty" for row in comparison_rows)
        category_counts: Counter[str] = Counter()
        for row in comparison_rows:
            expected_matches = row.get("expected_matches")
            if not isinstance(expected_matches, list):
                continue
            for expected_match in expected_matches:
                if not isinstance(expected_match, dict):
                    continue
                category_id = expected_match.get("category_id")
                if isinstance(category_id, str):
                    category_counts[category_id] += 1
        total_failures = (
            comparison_stage["content_mismatches"]
            + comparison_stage["execution_failures"]
        )
        comparison_latencies = [
            float(row["latency_ms"])
            for row in comparison_rows
            if isinstance(row.get("latency_ms"), (int, float))
        ]
        average_comparison_latency = (
            sum(comparison_latencies) / len(comparison_latencies)
            if comparison_latencies
            else 0.0
        )
        print("Functional Validation Summary")
        print()
        print(f"Run ID:             {manifest.get('run_id', 'unavailable')}")
        print(f"Run directory:      {args.run}")
        print()
        print(f"Records evaluated:  {records_total}")
        print(f"Records passed:     {comparison_stage['records_passed']}")
        print(f"Records failed:     {total_failures}")
        print(f"Pass rate:          {pass_rate:.3f}%")
        print()
        print("Record breakdown:")
        print(f"- Clean records: {clean_records}")
        print(f"- Dirty records: {dirty_records}")
        print()
        print("Expected transformations:")
        print(f"- Total expected replacements: {expected_replacements}")
        print()
        print("Transformations by category:")
        if category_counts:
            for category_id, count in sorted(category_counts.items()):
                print(f"- {category_id}: {count}")
        else:
            print("- none: 0")
        print()
        print("Outcome breakdown:")
        print(f"- PASS: {comparison_stage['records_passed']}")
        print(
            f"- CONTENT_MISMATCH: {comparison_stage['content_mismatches']}"
        )
        print(
            f"- EXECUTION_FAILURE: {comparison_stage['execution_failures']}"
        )
        print()
        print("Latency:")
        print(f"- Average latency: {average_comparison_latency:.3f} ms")
        print(
            f"- p50: {_cli_percentile(comparison_latencies, 0.50):.3f} ms"
        )
        print(
            f"- p95: {_cli_percentile(comparison_latencies, 0.95):.3f} ms"
        )
        print(
            f"- p99: {_cli_percentile(comparison_latencies, 0.99):.3f} ms"
        )
        print()
        print("Comparison artifact:")
        print(comparison_stage["output_path"])
        return 0

    if args.command == "report":
        try:
            manifest = report_run(args.run)
        except ReportingError as error:
            print(f"Report generation failed: {error}", file=sys.stderr)
            return 1
        stage = manifest["stages"]["reporting"]
        print("Validation report generated")
        print()
        print(f"Run ID:        {manifest.get('run_id', 'unavailable')}")
        print(f"Run directory: {args.run}")
        print(f"Report:        {stage['output_path']}")
        return 0

    return 2
