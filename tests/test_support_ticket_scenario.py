from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path

from framework.scenarios.support_ticket import build_support_ticket
from framework.workload.generate_scale_artifacts import (
    ScaleRule,
    generate_scale_artifacts,
)


class SupportTicketScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = [
            ScaleRule("rule-1", "pii", "person_name", "Sandra Hernandez", "[PII:PERSON_NAME]"),
            ScaleRule("rule-2", "pii", "email_address", "Sandra.Hernandez@brightline.co", "[PII:EMAIL_ADDRESS]"),
            ScaleRule("rule-3", "pii", "phone_number", "+1-704-555-0184", "[PII:PHONE_NUMBER]"),
            ScaleRule("rule-4", "business_terms", "customer_id", "CUST-482193", "[BUSINESS_TERMS:CUSTOMER_ID]"),
            ScaleRule("rule-5", "business_terms", "support_case_id", "CASE-482193", "[BUSINESS_TERMS:SUPPORT_CASE_ID]"),
            ScaleRule("rule-6", "credentials", "access_token", "access_482193_synthetic_demo", "[CREDENTIALS:ACCESS_TOKEN]"),
            ScaleRule("rule-7", "financial", "credit_card_number", "4111-1111-4821-9317", "[FINANCIAL:CREDIT_CARD_NUMBER]"),
        ]

    def test_builder_is_deterministic_and_places_rules_naturally(self) -> None:
        arguments = (
            "document-000001",
            {"fields": []},
        )
        first = build_support_ticket(
            *arguments, random.Random(42), self.rules, {rule.variant for rule in self.rules}
        )
        second = build_support_ticket(
            *arguments, random.Random(42), self.rules, {rule.variant for rule in self.rules}
        )

        self.assertEqual(first, second)
        self.assertEqual(first.record["scenario"], "support_ticket")
        self.assertEqual(first.record["customer_name"], "Sandra Hernandez")
        self.assertEqual(first.record["requester_email"], "Sandra.Hernandez@brightline.co")
        self.assertEqual(first.record["customer_contact"]["phone_number"], "+1-704-555-0184")
        self.assertEqual(first.record["customer_id"], "CUST-482193")
        self.assertEqual(first.record["ticket_id"], "CASE-482193")
        self.assertIn("access_482193_synthetic_demo", first.record["security_notes"][0])
        self.assertIn("4111-1111-4821-9317", first.record["payment_notes"][0])
        self.assertNotIn("validation_rule_", json.dumps(first.record))
        self.assertEqual({placement.rule for placement in first.placements}, set(self.rules))

    def test_clean_ticket_contains_no_catalog_values(self) -> None:
        result = build_support_ticket(
            "document-000001",
            {"fields": []},
            random.Random(42),
            [],
            {rule.variant for rule in self.rules},
        )
        serialized = json.dumps(result.record, sort_keys=True)
        self.assertFalse(any(rule.variant in serialized for rule in self.rules))
        self.assertEqual(result.placements, ())

    def test_generated_artifacts_share_policy_and_expected_evidence(self) -> None:
        config = Path("config/workloads/support-ticket-json.yaml")
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            manifest = generate_scale_artifacts(config, output)
            input_rows = [
                json.loads(line)
                for line in (output / "input.jsonl").read_text().splitlines()
            ]
            expected_rows = [
                json.loads(line)
                for line in (output / "expected.jsonl").read_text().splitlines()
            ]
            policy = (output / "scale-policy.nol").read_text()
            catalog = {item["variant"] for item in manifest["rule_catalog"]}

            self.assertEqual(manifest["scenario_distribution"], {"support_ticket": 10})
            self.assertEqual(manifest["padding_bytes_total"], 0)
            self.assertEqual(manifest["padded_document_count"], 0)
            self.assertEqual(
                manifest["generation_mode_distribution"], {"realistic": 10}
            )
            for input_row, expected_row in zip(input_rows, expected_rows, strict=True):
                record = json.loads(input_row["message"])
                self.assertEqual(record["scenario"], "support_ticket")
                self.assertNotIn("_synthetic_padding", record)
                self.assertNotIn("validation_rule_", input_row["message"])
                if input_row["kind"] == "clean":
                    self.assertFalse(any(value in input_row["message"] for value in catalog))
                for match in expected_row["expected_matches"]:
                    self.assertIn(match["variant"], policy)
                    self.assertIn(match["variant"], input_row["message"])
                    self.assertIn(match["replacement"], expected_row["expected_message"])


if __name__ == "__main__":
    unittest.main()


class SupportTicketCatalogCollisionTests(unittest.TestCase):
    """Regression: generation must not abort on an identifier collision.

    build_support_ticket previously raised when a clean ticket contained a
    catalog literal. The value it tripped on was its own DEMO-CASE identifier,
    which contains the support_case_id literal, so generation aborted at
    realistic rule counts and passed only because the fixture used 12 rules.
    """

    def build_clean(self, catalog_values: set[str]):
        return build_support_ticket(
            "document-000123",
            {"fields": []},
            random.Random(42),
            (),
            catalog_values,
        )

    def test_colliding_identifier_is_repaired_not_raised(self) -> None:
        build = self.build_clean({"CASE-000123"})
        serialized = json.dumps(build.record, sort_keys=True)
        self.assertNotIn("CASE-000123", serialized)

    def test_clean_ticket_without_collision_is_unchanged(self) -> None:
        build = self.build_clean(set())
        self.assertEqual(build.record["ticket_id"], "DEMO-CASE-000123")

    def test_repair_is_deterministic(self) -> None:
        first = self.build_clean({"CASE-000123"})
        second = self.build_clean({"CASE-000123"})
        self.assertEqual(first.record, second.record)

    def test_unrepairable_collision_does_not_abort(self) -> None:
        # A collision in a field this repair does not own must not crash.
        build = self.build_clean({"support_ticket"})
        self.assertIsNotNone(build.record)
