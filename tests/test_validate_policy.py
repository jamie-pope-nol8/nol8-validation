from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from framework.cli.main import (
    PolicyDeploymentError,
    apply_policy_to_run,
    deploy_policy,
)


class ValidatePolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def create_run(
        self,
        *,
        generation_status: str = "completed",
        include_policy: bool = True,
    ) -> tuple[Path, dict]:
        run_directory = self.root / "20260718T031425123456Z"
        generated_directory = run_directory / "generated"
        generated_directory.mkdir(parents=True)
        policy_path = generated_directory / "scale-policy.nol"
        policy_content = b'"secret" -> "[REDACTED]";\n'
        if include_policy:
            policy_path.write_bytes(policy_content)

        manifest = {
            "schema_version": 1,
            "run_id": run_directory.name,
            "run_type": "functional",
            "status": "generated",
            "created_at": "2026-07-18T03:14:25.123456Z",
            "updated_at": "2026-07-18T03:14:25.123456Z",
            "artifacts": {
                "policy": {
                    "path": "generated/scale-policy.nol",
                    "sha256": hashlib.sha256(policy_content).hexdigest(),
                    "size_bytes": len(policy_content),
                }
            },
            "stages": {
                "generation": {"status": generation_status},
                "policy": {"status": "pending"},
                "execution": {"status": "pending"},
                "comparison": {"status": "pending"},
                "reporting": {"status": "pending"},
            },
        }
        (run_directory / "manifest.json").write_text(json.dumps(manifest))
        return run_directory, manifest

    def read_manifest(self, run_directory: Path) -> dict:
        return json.loads((run_directory / "manifest.json").read_text())

    def test_missing_run_fails_clearly(self) -> None:
        with self.assertRaisesRegex(PolicyDeploymentError, "does not exist"):
            apply_policy_to_run(self.root / "missing-run", "themis")

    def test_missing_manifest_fails_clearly(self) -> None:
        run_directory = self.root / "empty-run"
        run_directory.mkdir()
        with self.assertRaisesRegex(PolicyDeploymentError, "manifest does not exist"):
            apply_policy_to_run(run_directory, "themis")

    def test_incomplete_generation_records_policy_failure(self) -> None:
        run_directory, _ = self.create_run(generation_status="in_progress")
        with self.assertRaises(PolicyDeploymentError):
            apply_policy_to_run(run_directory, "themis")

        manifest = self.read_manifest(run_directory)
        self.assertEqual(manifest["status"], "policy_failed")
        self.assertEqual(manifest["stages"]["policy"]["status"], "failed")
        self.assertEqual(
            manifest["stages"]["policy"]["error"]["category"], "prerequisite"
        )

    def test_missing_policy_records_policy_failure(self) -> None:
        run_directory, _ = self.create_run(include_policy=False)
        with self.assertRaisesRegex(PolicyDeploymentError, "does not exist"):
            apply_policy_to_run(run_directory, "themis")

        manifest = self.read_manifest(run_directory)
        self.assertEqual(manifest["stages"]["policy"]["status"], "failed")

    @patch("framework.cli.main.deploy_policy")
    def test_successful_deployment_updates_manifest(self, mocked_deploy) -> None:
        mocked_deploy.return_value = {
            "deployment_id": "deployment-123",
            "status": "active",
        }
        run_directory, original = self.create_run()

        manifest = apply_policy_to_run(run_directory, "aergia")

        mocked_deploy.assert_called_once()
        stage = manifest["stages"]["policy"]
        self.assertEqual(manifest["status"], "policy_deployed")
        self.assertEqual(stage["status"], "completed")
        self.assertEqual(stage["target"], "aergia")
        self.assertEqual(stage["policy_path"], "generated/scale-policy.nol")
        self.assertEqual(
            stage["policy_sha256"], original["artifacts"]["policy"]["sha256"]
        )
        self.assertEqual(stage["response"]["deployment_id"], "deployment-123")
        self.assertIn("started_at", stage)
        self.assertIn("completed_at", stage)
        for later_stage in ("execution", "comparison", "reporting"):
            self.assertEqual(manifest["stages"][later_stage], {"status": "pending"})

    @patch("framework.cli.main.deploy_policy")
    def test_deployment_failure_is_recorded(self, mocked_deploy) -> None:
        mocked_deploy.side_effect = PolicyDeploymentError(
            "network", "Policy deployment could not reach the target service."
        )
        run_directory, _ = self.create_run()

        with self.assertRaises(PolicyDeploymentError):
            apply_policy_to_run(run_directory, "themis")

        manifest = self.read_manifest(run_directory)
        stage = manifest["stages"]["policy"]
        self.assertEqual(manifest["status"], "policy_failed")
        self.assertEqual(stage["status"], "failed")
        self.assertEqual(stage["error"]["category"], "network")
        self.assertEqual(manifest["stages"]["execution"]["status"], "pending")

    @patch("framework.cli.main.subprocess.run")
    def test_deployment_exit_codes_are_distinguishable(self, mocked_run) -> None:
        policy_path = self.root / "policy.nol"
        policy_path.write_text('"x" -> "y";\n')
        expectations = {
            2: "configuration",
            3: "authentication",
            4: "authentication",
            5: "network",
            6: "deployment",
            9: "deployment",
        }

        for returncode, category in expectations.items():
            with self.subTest(returncode=returncode):
                mocked_run.return_value = subprocess.CompletedProcess(
                    [], returncode, stdout="", stderr=""
                )
                with self.assertRaises(PolicyDeploymentError) as caught:
                    deploy_policy(policy_path, "themis")
                self.assertEqual(caught.exception.category, category)

    @patch("framework.cli.main.subprocess.run")
    def test_success_response_is_allowlisted_and_secrets_are_not_written(
        self, mocked_run
    ) -> None:
        policy_path = self.root / "policy.nol"
        policy_path.write_text('"x" -> "y";\n')
        mocked_run.return_value = subprocess.CompletedProcess(
            [],
            0,
            stdout=json.dumps(
                {
                    "deployment_id": "deployment-123",
                    "status": "active",
                    "token": "top-secret-token",
                    "authorization": "Bearer top-secret-token",
                    "nested": {"password": "secret"},
                }
            ),
            stderr="",
        )

        response = deploy_policy(policy_path, "themis")

        serialized = json.dumps(response)
        self.assertEqual(
            response, {"deployment_id": "deployment-123", "status": "active"}
        )
        self.assertNotIn("top-secret-token", serialized)
        self.assertNotIn("Bearer", serialized)


if __name__ == "__main__":
    unittest.main()
