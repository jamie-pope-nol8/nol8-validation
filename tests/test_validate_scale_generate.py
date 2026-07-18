from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from framework.cli.main import generate_run
from framework.workload.generate_scale_artifacts import generate_scale_artifacts


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


if __name__ == "__main__":
    unittest.main()
