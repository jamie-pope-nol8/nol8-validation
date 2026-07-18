"""Build realistic deterministic support-ticket records."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence


class SupportTicketRule(Protocol):
    category_id: str
    pattern_id: str
    variant: str


@dataclass(frozen=True)
class RulePlacement:
    rule: SupportTicketRule
    field_path: str


@dataclass(frozen=True)
class SupportTicketBuild:
    record: dict[str, Any]
    placements: tuple[RulePlacement, ...]


def build_support_ticket(
    document_id: str,
    scenario_config: Mapping[str, Any],
    random_source: random.Random,
    selected_rules: Sequence[SupportTicketRule],
    catalog_values: set[str],
) -> SupportTicketBuild:
    """Return a coherent record and exact evidence for every placed rule."""

    priorities = ("low", "normal", "high", "urgent")
    subjects = (
        "Unable to complete account verification",
        "Billing profile update requires assistance",
        "Customer portal access needs review",
        "Account contact details could not be updated",
    )
    suffix = document_id.rsplit("-", 1)[-1]
    record: dict[str, Any] = {
        "document_id": document_id,
        "scenario": "support_ticket",
        "ticket_id": f"DEMO-CASE-{suffix}",
        "customer_id": f"DEMO-CUSTOMER-{suffix}",
        "customer_name": random_source.choice(
            ("Jordan Ellis", "Morgan Brooks", "Casey Rivera", "Taylor Monroe")
        ),
        "requester_email": f"requester-{suffix}@example.invalid",
        "customer_contact": {"phone_number": f"+1-980-555-{int(suffix) % 10000:04d}"},
        "priority": random_source.choice(priorities),
        "status": "open",
        "subject": random_source.choice(subjects),
        "issue_description": (
            "Customer reported a verification issue after updating account "
            "information through the self-service portal."
        ),
        "conversation_history": [
            {
                "timestamp": "2026-01-15T10:32:00Z",
                "author": "support-agent",
                "message": "Verification details were reviewed with the customer.",
            }
        ],
        "internal_notes": "Account ownership checks are pending final review.",
        "security_notes": [],
        "payment_notes": [],
    }

    direct_fields = {
        "support_case_id": "ticket_id",
        "customer_id": "customer_id",
        "person_name": "customer_name",
        "email_address": "requester_email",
    }
    occupied: set[str] = set()
    placements: list[RulePlacement] = []

    for rule in selected_rules:
        direct_field = direct_fields.get(rule.pattern_id)
        if direct_field is not None and direct_field not in occupied:
            record[direct_field] = rule.variant
            occupied.add(direct_field)
            placements.append(RulePlacement(rule, direct_field))
            continue

        if rule.pattern_id == "phone_number" and "customer_contact.phone_number" not in occupied:
            record["customer_contact"]["phone_number"] = rule.variant
            occupied.add("customer_contact.phone_number")
            placements.append(RulePlacement(rule, "customer_contact.phone_number"))
            continue

        if rule.category_id == "credentials":
            record["security_notes"].append(
                f"Troubleshooting reference for {rule.pattern_id.replace('_', ' ')}: {rule.variant}."
            )
            field_path = f"security_notes[{len(record['security_notes']) - 1}]"
        elif rule.category_id == "financial":
            record["payment_notes"].append(
                f"Billing discussion referenced {rule.pattern_id.replace('_', ' ')}: {rule.variant}."
            )
            field_path = f"payment_notes[{len(record['payment_notes']) - 1}]"
        elif rule.pattern_id in {"person_name", "email_address", "phone_number"}:
            record["conversation_history"].append(
                {
                    "timestamp": "2026-01-15T10:41:00Z",
                    "author": "customer",
                    "message": (
                        f"Customer supplied {rule.pattern_id.replace('_', ' ')} "
                        f"{rule.variant} for verification."
                    ),
                }
            )
            field_path = (
                f"conversation_history[{len(record['conversation_history']) - 1}].message"
            )
        else:
            record["internal_notes"] += (
                f" Ticket metadata referenced {rule.pattern_id.replace('_', ' ')}: "
                f"{rule.variant}."
            )
            field_path = "internal_notes"
        placements.append(RulePlacement(rule, field_path))

    if not selected_rules:
        serialized = json.dumps(record, sort_keys=True)
        if any(value in serialized for value in catalog_values):
            raise ValueError("Clean support ticket unexpectedly contains a policy value.")

    return SupportTicketBuild(record=record, placements=tuple(placements))
