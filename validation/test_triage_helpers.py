#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "freshdesk-readonly-ticket-inspector" / "scripts" / "freshdesk_readonly_ticket_inspector.py"

spec = importlib.util.spec_from_file_location("freshdesk_readonly_ticket_inspector", SCRIPT)
assert spec and spec.loader
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


def test_unresolved_unassigned_filter() -> None:
    group_ids = {10}
    assert inspector.unresolved_unassigned_ticket({"status": 2, "spam": False, "responder_id": None, "group_id": 10}, group_ids)
    assert inspector.unresolved_unassigned_ticket({"status": 3, "spam": False, "responder_id": None, "group_id": 10}, group_ids)
    assert not inspector.unresolved_unassigned_ticket({"status": 4, "spam": False, "responder_id": None, "group_id": 10}, group_ids)
    assert not inspector.unresolved_unassigned_ticket({"status": 5, "spam": False, "responder_id": None, "group_id": 10}, group_ids)
    assert not inspector.unresolved_unassigned_ticket({"status": 2, "spam": True, "responder_id": None, "group_id": 10}, group_ids)
    assert not inspector.unresolved_unassigned_ticket({"status": 2, "spam": False, "responder_id": 99, "group_id": 10}, group_ids)


def test_public_conversation_triage_flags() -> None:
    ticket = {"requester_id": 1}
    customer = {"incoming": True, "private": False, "body_text": "Need help with VPN", "user_id": 1}
    auto_reply = {"incoming": False, "private": False, "body": "<p>We received your request</p>"}
    assert inspector.shape_public_conversation(ticket, customer)["use_for_triage"] is True
    shaped_auto = inspector.shape_public_conversation(ticket, auto_reply)
    assert shaped_auto["use_for_triage"] is False
    assert shaped_auto["body_text"] == "We received your request"


if __name__ == "__main__":
    test_unresolved_unassigned_filter()
    test_public_conversation_triage_flags()
    print("triage helper tests passed")
