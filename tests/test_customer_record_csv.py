from __future__ import annotations

import csv
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import yaml

from framework.workload import generate_scale_artifacts as scale_generator
from framework.workload.generate_scale_artifacts import generate_scale_artifacts


class CustomerRecordCsvTests(unittest.TestCase):
    config = Path("config/workloads/customer-record-csv.yaml")

    def _generate(self, output: Path) -> dict:
        return generate_scale_artifacts(self.config, output)

    @staticmethod
    def _jsonl(path: Path) -> list[dict]:
        return [json.loads(line) for line in path.read_text().splitlines()]

    @staticmethod
    def _csv_row(message: str) -> dict[str, str]:
        rows = list(csv.DictReader(StringIO(message)))
        if len(rows) != 1:
            raise AssertionError("Expected one customer row per CSV document.")
        return rows[0]

    def test_csv_generation_is_deterministic_and_parseable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = root / "first"
            second = root / "second"
            self._generate(first)
            self._generate(second)

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

            for input_row in self._jsonl(first / "input.jsonl"):
                parsed = self._csv_row(input_row["message"])
                self.assertEqual(parsed["scenario"], "customer_record")
                self.assertEqual(parsed["document_id"], input_row["record_id"])
                self.assertIn("customer_id", parsed)
                self.assertIn("internal_notes", parsed)

    def test_policy_literals_and_expected_evidence_share_csv_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            manifest = self._generate(output)
            inputs = self._jsonl(output / "input.jsonl")
            expected = self._jsonl(output / "expected.jsonl")
            policy = (output / "scale-policy.nol").read_text()
            catalog = {item["variant"] for item in manifest["rule_catalog"]}

            self.assertGreater(manifest["dirty_record_count"], 0)
            for input_row, expected_row in zip(inputs, expected, strict=True):
                parsed = self._csv_row(input_row["message"])
                serialized_cells = "\n".join(parsed.values())
                self.assertNotIn("validation_rule_", input_row["message"])
                self.assertNotIn("_synthetic_padding", input_row["message"])

                if input_row["kind"] == "clean":
                    self.assertEqual(expected_row["expected_matches"], [])
                    self.assertFalse(
                        any(value in input_row["message"] for value in catalog)
                    )
                    continue

                for match in expected_row["expected_matches"]:
                    self.assertIn(match["variant"], catalog)
                    self.assertIn(match["variant"], policy)
                    self.assertIn(match["variant"], serialized_cells)
                    self.assertIn(
                        match["replacement"], expected_row["expected_message"]
                    )

            first_record = self._csv_row(inputs[0]["message"])
            first_matches = {
                match["case_id"]: match["variant"]
                for match in expected[0]["expected_matches"]
            }
            self.assertEqual(
                first_record["email_address"], first_matches["email_address"]
            )
            self.assertEqual(
                first_record["phone_number"], first_matches["phone_number"]
            )
            self.assertEqual(
                first_record["street_address"], first_matches["street_address"]
            )

    def test_realistic_routing_is_limited_to_csv_small(self) -> None:
        workload = yaml.safe_load(self.config.read_text())
        workload["documents"]["size_distribution"] = {
            "medium": {
                "weight": 100,
                "minimum_bytes": 4097,
                "maximum_bytes": 5000,
            }
        }

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            medium_config = root / "customer-record-csv-medium.yaml"
            medium_config.write_text(yaml.safe_dump(workload, sort_keys=False))
            with patch.object(
                scale_generator,
                "_build_realistic_customer_record",
                wraps=scale_generator._build_realistic_customer_record,
            ) as builder:
                generate_scale_artifacts(medium_config, root / "generated")

            builder.assert_not_called()

    def test_existing_customer_json_small_route_remains_realistic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            generate_scale_artifacts(
                Path("config/workloads/customer-record-json.yaml"), output
            )
            for input_row in self._jsonl(output / "input.jsonl"):
                record = json.loads(input_row["message"])
                self.assertEqual(record["scenario"], "customer_record")
                self.assertNotIn("_synthetic_padding", record)
                self.assertNotIn("validation_rule_", input_row["message"])


if __name__ == "__main__":
    unittest.main()
