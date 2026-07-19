from __future__ import annotations

import csv
import json
import random
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import yaml

from framework.workload import generate_scale_artifacts as scale_generator
from framework.workload.generate_scale_artifacts import generate_scale_artifacts
from framework.workload.generate_scale_artifacts import (
    _build_realistic_customer_record,
    _rule_catalog,
)
from framework.workload.generate_workload import load_workload


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

    def test_5000_rule_catalog_is_unique_and_deterministic(self) -> None:
        workload = load_workload(self.config)
        workload["policy"]["rule_count"] = 5000

        first = _rule_catalog(workload)
        second = _rule_catalog(workload)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 5000)
        self.assertEqual(len({rule.variant for rule in first}), 5000)

    def test_clean_customer_records_do_not_collide_with_5000_rules(self) -> None:
        workload = load_workload(self.config)
        workload["policy"]["rule_count"] = 5000
        catalog = _rule_catalog(workload)
        catalog_values = {rule.variant for rule in catalog}
        fields = list(
            workload["documents"]["scenarios"]["customer_record"]["fields"]
        )
        rng = random.Random(int(workload["seed"]))

        for index in range(1, 101):
            record = _build_realistic_customer_record(
                f"document-{index:06d}",
                fields,
                [],
                catalog_values,
                rng,
            )
            serialized = json.dumps(record, sort_keys=True)
            self.assertFalse(
                any(value in serialized for value in catalog_values),
                msg=f"Clean record {index} contains a policy literal.",
            )

    def test_fixed_metadata_is_separated_from_policy_dates(self) -> None:
        workload = load_workload(self.config)
        workload["policy"]["rule_count"] = 5000
        catalog = _rule_catalog(workload)
        catalog_values = {rule.variant for rule in catalog}
        date_values = {
            rule.variant for rule in catalog if rule.pattern_id == "date_of_birth"
        }
        self.assertIn("2000-01-01", date_values)

        record = _build_realistic_customer_record(
            "document-000001",
            list(
                workload["documents"]["scenarios"]["customer_record"]["fields"]
            ),
            [],
            catalog_values,
            random.Random(int(workload["seed"])),
        )

        self.assertNotEqual(record["generated_at"], "2000-01-01T00:00:00Z")
        self.assertFalse(
            any(value in record["generated_at"] for value in catalog_values)
        )


if __name__ == "__main__":
    unittest.main()
