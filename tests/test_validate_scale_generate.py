from __future__ import annotations

import json
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import yaml

from framework.cli.main import generate_run, main
from framework.workload.generate_scale_artifacts import (
    ScaleRule,
    _expected_result,
    generate_scale_artifacts,
)


class ValidateScaleGenerateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.config = self.root / "enterprise-dlp.yaml"
        self.config.write_text(
            yaml.safe_dump(
                {
                    "name": "enterprise-dlp-test",
                    "version": 0.1,
                    "seed": 42,
                    "policy": {
                        "rule_count": 12,
                        "families": {
                            "pii": {
                                "weight": 2,
                                "patterns": ["email_address", "phone_number"],
                            },
                            "credentials": {
                                "weight": 1,
                                "patterns": ["api_key"],
                            },
                        },
                    },
                    "documents": {
                        "count": 8,
                        "progress_interval_records": 3,
                        "scenarios": {
                            "customer_record": {
                                "weight": 1,
                                "fields": ["customer_id", "internal_notes"],
                            }
                        },
                        "formats": {"text": {"weight": 1}},
                        "match_distribution": {
                            "dirty": {
                                "weight": 1,
                                "matches_per_document": {"minimum": 2, "maximum": 2},
                            }
                        },
                        "size_distribution": {
                            "small": {
                                "weight": 1,
                                "minimum_bytes": 300,
                                "maximum_bytes": 400,
                            }
                        },
                    },
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def _rows(self, path: Path) -> list[dict]:
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_generation_is_deterministic(self) -> None:
        first = self.root / "first"
        second = self.root / "second"
        generate_scale_artifacts(self.config, first)
        generate_scale_artifacts(self.config, second)
        for filename in (
            "scale-policy.nol",
            "input.jsonl",
            "expected.jsonl",
            "manifest.json",
        ):
            self.assertEqual(
                (first / filename).read_bytes(),
                (second / filename).read_bytes(),
            )

    def test_generates_requested_policy_rule_count(self) -> None:
        output = self.root / "generated"
        manifest = generate_scale_artifacts(self.config, output)
        policy_lines = (output / "scale-policy.nol").read_text().splitlines()
        self.assertEqual(len(policy_lines), 12)
        self.assertEqual(manifest["requested_rules"], 12)
        self.assertEqual(manifest["realized_rules"], 12)
        self.assertTrue(all(" -> " in line for line in policy_lines))

    def test_scale_values_and_distributions_come_from_configuration(self) -> None:
        output = self.root / "generated"
        manifest = generate_scale_artifacts(self.config, output)
        requested = manifest["requested_scale"]
        realized = manifest["realized_scale"]

        self.assertEqual(requested["rule_count"], 12)
        self.assertEqual(requested["record_count"], 8)
        self.assertEqual(
            requested["size_distribution"]["small"],
            {"weight": 1, "minimum_bytes": 300, "maximum_bytes": 400},
        )
        self.assertEqual(realized["rule_count"], 12)
        self.assertEqual(realized["record_count"], 8)
        self.assertEqual(realized["size_profile_distribution"], {"small": 8})
        self.assertGreaterEqual(realized["payload_bytes"]["minimum"], 300)
        self.assertLessEqual(realized["payload_bytes"]["maximum"], 400)

    def test_canonical_input_and_expected_artifacts_share_evidence(self) -> None:
        output = self.root / "generated"
        manifest = generate_scale_artifacts(self.config, output)
        inputs = self._rows(output / "input.jsonl")
        expected = self._rows(output / "expected.jsonl")

        self.assertEqual(len(inputs), 8)
        self.assertEqual(len(expected), 8)
        self.assertEqual(manifest["realized_records"], 8)
        self.assertEqual(
            [row["record_id"] for row in inputs],
            [row["record_id"] for row in expected],
        )
        self.assertEqual(set(inputs[0]), {"record_id", "kind", "message"})
        self.assertEqual(
            set(expected[0]),
            {
                "record_id",
                "kind",
                "expected_message",
                "expected_match_count",
                "expected_matches",
            },
        )
        match = expected[0]["expected_matches"][0]
        self.assertTrue(
            {"category_id", "case_id", "variant", "replacement"} <= set(match)
        )
        self.assertIn(match["variant"], inputs[0]["message"])
        self.assertNotIn(match["variant"], expected[0]["expected_message"])
        self.assertIn(match["replacement"], expected[0]["expected_message"])

    def test_generate_cli_path_registers_canonical_artifacts(self) -> None:
        _, run_directory = generate_run(self.config, self.root / "runs")
        manifest = json.loads((run_directory / "manifest.json").read_text())
        self.assertEqual(manifest["run_type"], "scale")
        self.assertEqual(
            manifest["stages"]["generation"]["generator"],
            "framework.workload.generate_scale_artifacts",
        )
        for artifact in ("policy", "input", "expected", "generation_manifest"):
            self.assertTrue(
                (run_directory / manifest["artifacts"][artifact]["path"]).is_file()
            )

    def test_scale_cli_reports_bounded_generation_progress(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            result = main(
                [
                    "generate",
                    "--config",
                    str(self.config),
                    "--runs-dir",
                    str(self.root / "progress-runs"),
                ]
            )

        output = stdout.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("Generating validation workload", output)
        self.assertIn("Step 1/4: Loading workload configuration", output)
        self.assertIn("Step 2/4: Building rule catalog", output)
        self.assertIn("Rules generated: 12/12", output)
        self.assertIn("Step 3/4: Generating documents", output)
        self.assertIn("Calculating expected transformations", output)
        self.assertIn("Documents generated: 3/8", output)
        self.assertIn("Documents generated: 6/8", output)
        self.assertIn("Documents generated: 8/8", output)
        self.assertIn("Expected records completed: 3/8", output)
        self.assertIn("Expected records completed: 6/8", output)
        self.assertIn("Expected records completed: 8/8", output)
        self.assertIn("Step 4/4: Writing artifacts", output)
        self.assertIn("Generation completed", output)
        self.assertEqual(output.count("Documents generated:"), 3)
        self.assertEqual(output.count("Expected records completed:"), 3)

    def test_direct_scale_generation_is_quiet_without_callback(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            generate_scale_artifacts(self.config, self.root / "quiet-generated")
        self.assertEqual(stdout.getvalue(), "")

    def test_callback_receives_configured_document_progress_updates(self) -> None:
        events: list[tuple[str, int, int]] = []
        generate_scale_artifacts(
            self.config,
            self.root / "callback-generated",
            progress_callback=lambda event, completed, total: events.append(
                (event, completed, total)
            ),
        )

        self.assertEqual(
            [event for event in events if event[0] == "documents_progress"],
            [
                ("documents_progress", 3, 8),
                ("documents_progress", 6, 8),
                ("documents_progress", 8, 8),
            ],
        )
        self.assertEqual(
            [event for event in events if event[0] == "expected_progress"],
            [
                ("expected_progress", 3, 8),
                ("expected_progress", 6, 8),
                ("expected_progress", 8, 8),
            ],
        )

    def test_progress_callback_does_not_change_generation_results(self) -> None:
        quiet = self.root / "quiet-results"
        reported = self.root / "reported-results"
        generate_scale_artifacts(self.config, quiet)
        generate_scale_artifacts(
            self.config,
            reported,
            progress_callback=lambda _event, _completed, _total: None,
        )

        for filename in (
            "scale-policy.nol",
            "input.jsonl",
            "expected.jsonl",
            "manifest.json",
        ):
            self.assertEqual(
                (quiet / filename).read_bytes(),
                (reported / filename).read_bytes(),
            )

    def test_optimized_expected_results_match_full_catalog_scan(self) -> None:
        output = self.root / "expected-correctness"
        manifest = generate_scale_artifacts(self.config, output)
        inputs = self._rows(output / "input.jsonl")
        expected = self._rows(output / "expected.jsonl")

        catalog = [ScaleRule(**item) for item in manifest["rule_catalog"]]

        for input_row, expected_row in zip(inputs, expected, strict=True):
            full_message, full_matches = _expected_result(
                input_row["message"], catalog
            )
            self.assertEqual(expected_row["expected_message"], full_message)
            self.assertEqual(expected_row["expected_matches"], full_matches)

    def test_large_rule_catalog_generation_completes_promptly(self) -> None:
        workload = yaml.safe_load(self.config.read_text(encoding="utf-8"))
        workload["policy"]["rule_count"] = 5000
        workload["documents"]["count"] = 100
        workload["documents"]["progress_interval_records"] = 50
        scale_config = self.root / "performance-enterprise-dlp.yaml"
        scale_config.write_text(
            yaml.safe_dump(workload, sort_keys=False),
            encoding="utf-8",
        )

        started = time.perf_counter()
        manifest = generate_scale_artifacts(
            scale_config, self.root / "performance-generated"
        )
        elapsed = time.perf_counter() - started

        self.assertEqual(manifest["realized_rules"], 5000)
        self.assertEqual(manifest["realized_records"], 100)
        self.assertLess(elapsed, 3.0)


if __name__ == "__main__":
    unittest.main()
