#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "freshdesk-ticket-assignment-helper" / "scripts" / "freshdesk_readonly_ticket_inspector.py"

spec = importlib.util.spec_from_file_location("freshdesk_readonly_ticket_inspector", SCRIPT)
assert spec and spec.loader
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


def test_unresolved_unassigned_filter() -> None:
    group_ids = {10, None}
    assert inspector.unresolved_unassigned_ticket({"status": 2, "spam": False, "responder_id": None, "group_id": 10}, group_ids)
    assert inspector.unresolved_unassigned_ticket({"status": 3, "spam": False, "responder_id": None, "group_id": 10}, group_ids)
    assert not inspector.unresolved_unassigned_ticket({"status": 4, "spam": False, "responder_id": None, "group_id": 10}, group_ids)
    assert not inspector.unresolved_unassigned_ticket({"status": 5, "spam": False, "responder_id": None, "group_id": 10}, group_ids)
    assert not inspector.unresolved_unassigned_ticket({"status": 2, "spam": True, "responder_id": None, "group_id": 10}, group_ids)
    assert not inspector.unresolved_unassigned_ticket({"status": 2, "spam": False, "responder_id": 99, "group_id": 10}, group_ids)
    assert not inspector.unresolved_unassigned_ticket(
        {"status": 2, "spam": False, "responder_id": None, "group_id": 10, "tags": [" Escalation "]},
        group_ids,
    )
    assert not inspector.unresolved_unassigned_ticket(
        {"status": 3, "spam": False, "responder_id": None, "group_id": 10, "tags": ["rma"]},
        group_ids,
    )
    assert inspector.unresolved_unassigned_ticket(
        {"status": 2, "spam": False, "responder_id": None, "group_id": None},
        group_ids,
    )


def test_triage_group_filters() -> None:
    assert inspector.resolve_triage_group_filters({10: "Technical Service", 20: "MX Support"}) == [
        (10, "Technical Service"),
        (None, "Unassigned"),
        (20, "MX Support"),
    ]


def test_public_conversation_triage_flags() -> None:
    ticket = {"requester_id": 1}
    customer = {"incoming": True, "private": False, "body_text": "Need help with VPN", "user_id": 1}
    auto_reply = {"incoming": False, "private": False, "body": "<p>We received your request</p>"}
    assert inspector.shape_public_conversation(ticket, customer)["use_for_triage"] is True
    shaped_auto = inspector.shape_public_conversation(ticket, auto_reply)
    assert shaped_auto["use_for_triage"] is False
    assert shaped_auto["body_text"] == "We received your request"


def test_ticket_initial_text() -> None:
    assert inspector.ticket_initial_text({"description_text": " First customer email "}) == "First customer email"
    assert inspector.ticket_initial_text({"description": "<p>HTML fallback</p>"}) == "HTML fallback"


def test_ticket_url() -> None:
    shaped = inspector.shape_ticket(
        "glinetservice.freshdesk.com",
        {"id": 136245, "responder_id": None, "group_id": None},
        {},
        {},
    )
    assert shaped["ticket_url"] == "https://glinetservice.freshdesk.com/a/tickets/136245"


def test_api_key_is_environment_only() -> None:
    assert 'parser.add_argument("--api-key"' not in SCRIPT.read_text(encoding="utf-8")


def test_search_pagination_stops_at_freshdesk_page_cap() -> None:
    calls: list[int] = []
    original = inspector.get_json

    def fake_get(_domain: str, _api_key: str, _path: str, params: dict):
        page = params["page"]
        calls.append(page)
        if page > 10:
            raise AssertionError("Freshdesk search page must not exceed 10")
        return {"total": 301, "results": [{"id": page * 100 + index} for index in range(30)]}

    inspector.get_json = fake_get
    try:
        rows, total = inspector.paginate_search("example.freshdesk.com", "key", "status:2")
    finally:
        inspector.get_json = original

    assert calls == list(range(1, 11))
    assert len(rows) == 300
    assert total == 301


def test_attachment_metadata() -> None:
    source = {
        "attachments": [
            {
                "name": "invoice.pdf",
                "content_type": "application/pdf",
                "size": 1234,
                "attachment_url": "https://example.invalid/private",
            }
        ]
    }
    assert inspector.shape_attachments(source) == [
        {"name": "invoice.pdf", "content_type": "application/pdf", "size": 1234}
    ]
    attachment_only = inspector.shape_public_conversation(
        {"requester_id": 1},
        {"incoming": True, "private": False, "user_id": 1, **source},
    )
    assert attachment_only["body_text"] is None
    assert attachment_only["attachments"][0]["name"] == "invoice.pdf"
    assert inspector.attachment_metadata_incomplete({"attachments": [{"attachment_url": "https://example.invalid/private"}]})
    assert not inspector.attachment_metadata_incomplete(source)
    assert not inspector.attachment_metadata_incomplete({"attachments": []})
    assert inspector.should_fetch_ticket_detail({"description_text": "I attached logs", "attachments": []})
    assert inspector.should_fetch_ticket_detail({"description_text": "附件请见邮件", "attachments": []})
    assert not inspector.should_fetch_ticket_detail({"description_text": "No files included", "attachments": []})


def test_routing_rules_contract() -> None:
    rules = (ROOT / "skills" / "freshdesk-ticket-assignment-helper" / "references" / "triage-routing-rules.md").read_text(
        encoding="utf-8"
    )
    assert "## Technical Service" in rules
    assert "feature request" in rules.lower()
    assert "invoice" in rules.lower()
    assert "separate Markdown table" in rules
    assert "Operations / Shopify" not in rules
    assert "CS hands off to Shopify" in rules
    assert "50 units" in rules
    assert "certification" in rules.lower()
    assert "previous quotation" in rules.lower()
    assert "product fit" in rules.lower()
    assert "third-party plugin" in rules.lower()
    assert "vlan" in rules.lower()
    assert "goodcloud site to site" in rules.lower()
    assert "api documentation" in rules.lower()
    assert "sample units" in rules.lower()
    assert "100 units" in rules.lower()
    assert "templated partnership" in rules.lower()
    assert "does not mention gl.inet" in rules.lower()
    assert "could be sent unchanged to any company" in rules.lower()
    assert "sender's own company" in rules.lower()
    assert "tr.ee" in rules.lower()
    assert "order status" in rules.lower()
    assert "generic delivery" in rules.lower()
    assert "no product, brand, or real order" in rules.lower()
    assert "newer confirmed rules take precedence" in rules.lower()
    assert "[ticket_id](ticket_url)" in rules.lower()
    assert "simpoyo.com" in rules.lower()
    assert "registration and login" in rules.lower()
    assert "cloud-platform backend" in rules.lower()
    assert "hardware faults" in rules.lower()
    assert "Cathy" not in rules
    assert "Zenia" not in rules


def test_merge_history_signals() -> None:
    assert inspector.merge_check_triggers(
        {"subject": "Request for Quotation", "description_text": "Dear Ann, please confirm the quote."}
    ) == ["named_salutation:Ann"]
    assert "subject_re" in inspector.merge_check_triggers(
        {"subject": "Re: Existing issue", "description_text": "Any update?"}
    )
    assert inspector.merge_check_triggers(
        {"subject": "Question", "description_text": "Dear Support, please help."}
    ) == []
    assert inspector.normalize_merge_subject(
        "Re: Re: Request for Quotation - GL iNet Mudi 7 #[Ticket-132922]"
    ) == "request for quotation - gl inet mudi 7"
    assert inspector.merge_subjects_match(
        "Request for Quotation - GL iNet Mudi 7",
        "Re: Request for Quotation - GL iNet Mudi 7 #132922",
    )


if __name__ == "__main__":
    test_unresolved_unassigned_filter()
    test_triage_group_filters()
    test_public_conversation_triage_flags()
    test_ticket_initial_text()
    test_ticket_url()
    test_api_key_is_environment_only()
    test_search_pagination_stops_at_freshdesk_page_cap()
    test_attachment_metadata()
    test_routing_rules_contract()
    test_merge_history_signals()
    print("triage helper tests passed")
