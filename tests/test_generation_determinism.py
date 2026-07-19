"""Generation must be reproducible from the seed alone.

The existing determinism test used a text-only format configuration, so it
never exercised the log serializer, which fell back to wall-clock time. Roughly
9% of enterprise-dlp documents are log-formatted, so two runs of the same seed
produced different corpora while the test passed.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from framework.workload.generate_scale_artifacts import generate_scale_artifacts


BASE_WORKLOAD = {
    "schema": "enterprise-dlp-scale",
    "name": "determinism-check",
    "seed": 42,
    "policy": {
        "rule_count": 40,
        "families": {
            "pii": {"weight": 60, "patterns": ["person_name", "email_address"]},
            "financial": {"weight": 40, "patterns": ["invoice_number"]},
        },
    },
    "documents": {
        "count": 60,
        "progress_interval_records": 100,
        "scenarios": {
            "customer_record": {
                "weight": 50,
                "fields": ["customer_id", "person_name", "email_address"],
            },
            "application_log": {
                "weight": 50,
                "fields": ["request_id", "person_name", "email_address"],
            },
        },
        # The format that previously reintroduced wall-clock time.
        "formats": {"log": {"weight": 100}},
        "match_distribution": {
            "clean": {"weight": 30, "matches_per_document": {"minimum": 0, "maximum": 0}},
            "dirty": {"weight": 70, "matches_per_document": {"minimum": 1, "maximum": 3}},
        },
        "size_distribution": {
            "small": {"weight": 100, "minimum_bytes": 200, "maximum_bytes": 400}
        },
        "generate_clean_control_records": True,
    },
}


class GenerationDeterminismTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def write_config(self, workload: dict, name: str) -> Path:
        path = self.root / name
        path.write_text(yaml.safe_dump(workload, sort_keys=False), encoding="utf-8")
        return path

    def generate(self, config: Path, name: str) -> dict[str, bytes]:
        output = self.root / name
        generate_scale_artifacts(config, output)
        return {
            filename: (output / filename).read_bytes()
            for filename in ("input.jsonl", "expected.jsonl", "scale-policy.nol")
        }

    def test_log_format_generation_is_reproducible(self) -> None:
        config = self.write_config(BASE_WORKLOAD, "log-determinism.yaml")
        first = self.generate(config, "first")
        second = self.generate(config, "second")
        for filename, content in first.items():
            self.assertEqual(
                content, second[filename], f"{filename} differs between runs"
            )

    def test_no_wall_clock_year_appears_in_output(self) -> None:
        # Synthetic timestamps use an implausible year so a generated record is
        # never mistaken for a real one, and so a wall-clock leak is obvious.
        config = self.write_config(BASE_WORKLOAD, "epoch-check.yaml")
        artifacts = self.generate(config, "epoch")
        text = artifacts["input.jsonl"].decode("utf-8")
        for year in ("2024", "2025", "2026", "2027"):
            self.assertNotIn(
                f"{year}-", text, f"wall-clock year {year} leaked into output"
            )

    def test_differing_seeds_produce_differing_corpora(self) -> None:
        # Guards against the fix over-correcting into a constant.
        first_config = self.write_config(BASE_WORKLOAD, "seed-a.yaml")
        other = {**BASE_WORKLOAD, "seed": 43}
        second_config = self.write_config(other, "seed-b.yaml")
        self.assertNotEqual(
            self.generate(first_config, "seed-a")["input.jsonl"],
            self.generate(second_config, "seed-b")["input.jsonl"],
        )


if __name__ == "__main__":
    unittest.main()
