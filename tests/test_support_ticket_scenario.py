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
            for input_row, expected_row in zip(input_rows, expected_rows, strict=True):
                record = json.loads(input_row["message"])
                self.assertEqual(record["scenario"], "support_ticket")
                self.assertNotIn("validation_rule_", input_row["message"])
                if input_row["kind"] == "clean":
                    self.assertFalse(any(value in input_row["message"] for value in catalog))
                for match in expected_row["expected_matches"]:
                    self.assertIn(match["variant"], policy)
                    self.assertIn(match["variant"], input_row["message"])
                    self.assertIn(match["replacement"], expected_row["expected_message"])


if __name__ == "__main__":
    unittest.main()
