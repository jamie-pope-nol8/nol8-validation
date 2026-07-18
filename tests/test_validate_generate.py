from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from framework.cli.main import generate_run, main, run_id_from_datetime


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPOSITORY_ROOT / "config" / "test-cases.yaml"


class ValidateGenerateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.runs_directory = Path(self.temporary_directory.name) / "runs"

    def create_run(self) -> tuple[str, Path, dict]:
        run_id, run_directory = generate_run(CONFIG_PATH, self.runs_directory)
        manifest = json.loads((run_directory / "manifest.json").read_text())
        return run_id, run_directory, manifest

    def test_run_id_uses_required_utc_format(self) -> None:
        value = datetime(2026, 7, 18, 3, 14, 25, 123456, tzinfo=UTC)
        run_id = run_id_from_datetime(value)
        self.assertEqual(run_id, "20260718T031425123456Z")
        self.assertRegex(run_id, r"^\d{8}T\d{12}Z$")

    def test_generate_creates_expected_directory_structure(self) -> None:
        _, run_directory, _ = self.create_run()
        expected_files = {
            "manifest.json",
            "config/test-cases.yaml",
            "generated/scale-policy.nol",
            "generated/input.jsonl",
            "generated/expected.jsonl",
            "generated/generation-manifest.json",
        }
        actual_files = {
            path.relative_to(run_directory).as_posix()
            for path in run_directory.rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual_files, expected_files)

    def test_configuration_snapshot_matches_source(self) -> None:
        _, run_directory, _ = self.create_run()
        snapshot = run_directory / "config/test-cases.yaml"
        self.assertEqual(snapshot.read_bytes(), CONFIG_PATH.read_bytes())

    def test_generation_manifest_preserves_expected_statistics(self) -> None:
        _, run_directory, _ = self.create_run()
        generation_manifest = json.loads(
            (run_directory / "generated/generation-manifest.json").read_text()
        )
        self.assertEqual(generation_manifest["record_count"], 1000)
        self.assertEqual(generation_manifest["dirty_record_count"], 900)
        self.assertEqual(generation_manifest["clean_record_count"], 100)
        self.assertEqual(generation_manifest["policy_rule_count"], 60)
        self.assertEqual(generation_manifest["expected_total_matches"], 3018)
        self.assertTrue(generation_manifest["full_variant_coverage"])

    def test_run_manifest_reports_generated_status(self) -> None:
        run_id, _, manifest = self.create_run()
        self.assertEqual(manifest["run_id"], run_id)
        self.assertEqual(manifest["status"], "generated")
        self.assertEqual(manifest["stages"]["generation"]["status"], "completed")

    def test_artifact_paths_are_relative(self) -> None:
        _, _, manifest = self.create_run()
        for artifact in manifest["artifacts"].values():
            self.assertFalse(Path(artifact["path"]).is_absolute())

    def test_recorded_hashes_and_sizes_match_files(self) -> None:
        _, run_directory, manifest = self.create_run()
        for artifact in manifest["artifacts"].values():
            path = run_directory / artifact["path"]
            self.assertEqual(artifact["size_bytes"], path.stat().st_size)
            self.assertEqual(
                artifact["sha256"], hashlib.sha256(path.read_bytes()).hexdigest()
            )

    def test_standalone_functional_generator_still_works(self) -> None:
        output_directory = Path(self.temporary_directory.name) / "standalone"
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "framework/policy/generate_functional_test.py",
                "--config",
                str(CONFIG_PATH),
                "--output-dir",
                str(output_directory),
            ],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((output_directory / "manifest.json").read_text())
        self.assertEqual(manifest["expected_total_matches"], 3018)

    def test_two_runs_never_overwrite_each_other(self) -> None:
        first_id, first_directory, _ = self.create_run()
        second_id, second_directory, _ = self.create_run()
        self.assertNotEqual(first_id, second_id)
        self.assertNotEqual(first_directory, second_directory)
        self.assertTrue((first_directory / "manifest.json").is_file())
        self.assertTrue((second_directory / "manifest.json").is_file())

    def test_functional_generation_rejects_scale_only_overrides(self) -> None:
        with self.assertRaisesRegex(ValueError, "only to scale workload"):
            generate_run(
                CONFIG_PATH,
                self.runs_directory,
                rule_count_override=10,
                record_count_override=5,
            )

    def test_failure_returns_nonzero_and_records_state(self) -> None:
        missing_config = Path(self.temporary_directory.name) / "missing.yaml"
        stderr = StringIO()
        with redirect_stdout(StringIO()), redirect_stderr(stderr):
            result = main(
                [
                    "generate",
                    "--config",
                    str(missing_config),
                    "--runs-dir",
                    str(self.runs_directory),
                ]
            )

        self.assertNotEqual(result, 0)
        run_directories = list(self.runs_directory.iterdir())
        self.assertEqual(len(run_directories), 1)
        manifest = json.loads(
            (run_directories[0] / "manifest.json").read_text()
        )
        self.assertEqual(manifest["status"], "failed")
        self.assertEqual(manifest["stages"]["generation"]["status"], "failed")
        self.assertEqual(manifest["error"]["type"], "FileNotFoundError")
        self.assertIn("Generation failed:", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
