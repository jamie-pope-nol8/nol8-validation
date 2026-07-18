from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from framework.policy.generate_functional_test import generate_functional_artifacts


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


def generate_run(config_path: Path, runs_directory: Path) -> tuple[str, Path]:
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="validate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser(
        "generate", help="Create a functional validation run"
    )
    generate_parser.add_argument(
        "--config", type=Path, required=True, help="Functional test YAML"
    )
    generate_parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("artifacts/runs"),
        help="Parent directory for validation runs",
    )

    policy_parser = subparsers.add_parser(
        "policy", help="Deploy the generated policy for a validation run"
    )
    policy_parser.add_argument(
        "--run", type=Path, required=True, help="Existing validation Run directory"
    )
    policy_parser.add_argument(
        "--target",
        choices=("themis", "aergia"),
        default="themis",
        help="Policy deployment target (default: themis)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "generate":
        try:
            run_id, run_directory = generate_run(args.config, args.runs_dir)
        except (OSError, KeyError, TypeError, ValueError) as error:
            print(f"Generation failed: {error}", file=sys.stderr)
            return 1

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

    return 2
