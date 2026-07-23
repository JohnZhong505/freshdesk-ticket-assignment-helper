#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import ssl
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
    groups = {10: "Technical Service", 20: "MX Support", 30: "Customer Service"}
    assert inspector.resolve_triage_group_filters(groups, "technical-service") == [
        (10, "Technical Service"),
        (None, "Unassigned"),
    ]
    assert inspector.resolve_triage_group_filters(groups, "technical-service", include_mx_support=True) == [
        (10, "Technical Service"),
        (None, "Unassigned"),
        (20, "MX Support"),
    ]
    assert inspector.resolve_triage_group_filters(groups, "customer-service") == [
        (30, "Customer Service"),
    ]


def test_triage_view_cli_replaces_legacy_flag() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"--triage-view"' in source
    assert '"--include-mx-support"' in source
    assert "--triage-unassigned-view" not in source


def test_customer_service_triage_instruction() -> None:
    instruction = inspector.triage_instruction("customer-service")
    assert "every technical issue" in instruction
    assert "Do not output Technical Support" in instruction
    assert "Stay in Customer Service" in instruction


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
    assert shaped["ticket_link_markdown"] == "[136245](https://glinetservice.freshdesk.com/a/tickets/136245)"


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


def test_complete_triage_rejects_search_cap_truncation() -> None:
    original_fetch = inspector.fetch_tickets

    def fake_fetch(_domain: str, _api_key: str, limit: int | None, _query: str | None):
        assert limit is None
        return ([{"id": index, "status": 2, "spam": False, "responder_id": None, "group_id": 30} for index in range(300)], 301)

    inspector.fetch_tickets = fake_fetch
    try:
        try:
            inspector.fetch_triage_view("example.freshdesk.com", "key", {30: "Customer Service"}, {}, "customer-service")
        except inspector.FreshdeskError as exc:
            assert "partial triage" in str(exc)
        else:
            raise AssertionError("A truncated complete triage view was accepted")
    finally:
        inspector.fetch_tickets = original_fetch


def test_complete_search_retries_a_moving_view() -> None:
    original_fetch = inspector.fetch_tickets
    responses = [([{"id": 1}], 2), ([{"id": 1}, {"id": 2}], 2)]

    def fake_fetch(_domain: str, _api_key: str, limit: int | None, _query: str | None):
        assert limit is None
        return responses.pop(0)

    inspector.fetch_tickets = fake_fetch
    try:
        rows, total = inspector.fetch_complete_search("example.freshdesk.com", "key", "status:2")
    finally:
        inspector.fetch_tickets = original_fetch

    assert [row["id"] for row in rows] == [1, 2]
    assert total == 2
    assert responses == []


def test_complete_search_retries_duplicate_ticket_ids() -> None:
    original_fetch = inspector.fetch_tickets
    responses = [([{"id": 1}, {"id": 1}], 2), ([{"id": 1}, {"id": 2}], 2)]

    def fake_fetch(_domain: str, _api_key: str, limit: int | None, _query: str | None):
        assert limit is None
        return responses.pop(0)

    inspector.fetch_tickets = fake_fetch
    try:
        rows, total = inspector.fetch_complete_search("example.freshdesk.com", "key", "status:2")
    finally:
        inspector.fetch_tickets = original_fetch

    assert [row["id"] for row in rows] == [1, 2]
    assert total == 2
    assert responses == []


def test_required_group_names_must_be_unique() -> None:
    try:
        inspector.resolve_required_group_ids({10: "Customer Service", 20: "customer service"}, ("Customer Service",))
    except inspector.FreshdeskError as exc:
        assert "not unique" in str(exc)
    else:
        raise AssertionError("Duplicate Freshdesk Group names were accepted")


def test_get_json_retries_direct_ssl_eof() -> None:
    original_urlopen = inspector.urllib.request.urlopen
    original_sleep = inspector.time.sleep
    calls = 0

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ssl.SSLError("UNEXPECTED_EOF_WHILE_READING")
        return Response()

    inspector.urllib.request.urlopen = fake_urlopen
    inspector.time.sleep = lambda _seconds: None
    try:
        assert inspector.get_json("example.freshdesk.com", "key", "/api/v2/tickets") == {"ok": True}
    finally:
        inspector.urllib.request.urlopen = original_urlopen
        inspector.time.sleep = original_sleep
    assert calls == 3


def test_get_json_retries_http_5xx() -> None:
    original_urlopen = inspector.urllib.request.urlopen
    original_sleep = inspector.time.sleep
    calls = 0

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise inspector.urllib.error.HTTPError(
                "https://example.invalid",
                503,
                "Service Unavailable",
                {},
                io.BytesIO(b"temporary"),
            )
        return Response()

    inspector.urllib.request.urlopen = fake_urlopen
    inspector.time.sleep = lambda _seconds: None
    try:
        assert inspector.get_json("example.freshdesk.com", "key", "/api/v2/tickets") == {"ok": True}
    finally:
        inspector.urllib.request.urlopen = original_urlopen
        inspector.time.sleep = original_sleep
    assert calls == 3


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
    assert "simpoyo.com" in rules.lower()
    assert "registration and login" in rules.lower()
    assert "cloud-platform backend" in rules.lower()
    assert "shopify shop account" in rules.lower()
    assert "web-store account" in rules.lower()
    assert "ecommerce storefront accounts are the cs exception" in rules.lower()
    assert "hardware faults" in rules.lower()
    assert "## customer service perspective" in rules.lower()
    assert "do not output `technical support`" in rules.lower()
    assert "30 minutes" in rules.lower()
    assert "body length" in rules.lower()
    assert "ticket_link_markdown" in rules
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


def test_fragment_merge_window_and_target() -> None:
    first = {
        "id": 137077,
        "requester_id": 9,
        "subject": "",
        "description_text": "first message " + "x" * 500,
        "created_at": "2026-07-21T09:16:12Z",
    }
    second = {
        "id": 137079,
        "requester_id": 9,
        "subject": None,
        "description_text": "2nd!",
        "created_at": "2026-07-21T09:16:56Z",
    }
    same_subject = {
        **second,
        "id": 137080,
        "subject": "eSIM logs",
        "created_at": "2026-07-21T09:40:00Z",
    }
    previous_same_subject = {**first, "subject": "eSIM logs"}
    same_body_different_subject = {
        **second,
        "id": 137446,
        "subject": "New customer message on July 22, 2026 at 8:32 pm",
        "description_text": "Same order message\nwith whitespace",
        "created_at": "2026-07-21T09:17:12Z",
    }
    earlier_same_body = {
        **first,
        "id": 137445,
        "subject": "New customer message on July 22, 2026 at 8:31 pm",
        "description_text": "  Same order message with whitespace  ",
    }

    assert inspector.fragment_merge_pair(first, second)
    assert inspector.fragment_merge_pair(previous_same_subject, same_subject)
    assert inspector.fragment_merge_pair(earlier_same_body, same_body_different_subject)
    assert not inspector.fragment_merge_pair(first, {**second, "created_at": "2026-07-21T09:47:00Z"})
    assert not inspector.fragment_merge_pair(first, {**second, "requester_id": 10})
    assert not inspector.fragment_merge_pair(previous_same_subject, {**same_subject, "subject": "Different"})
    assert inspector.earliest_merge_target([second, first])["id"] == 137077
    assert inspector.earlier_fragment_tickets(earlier_same_body, [earlier_same_body, same_body_different_subject]) == []
    assert [
        row["id"]
        for row in inspector.earlier_fragment_tickets(
            same_body_different_subject,
            [same_body_different_subject, earlier_same_body],
        )
    ] == [137445]


if __name__ == "__main__":
    test_unresolved_unassigned_filter()
    test_triage_group_filters()
    test_triage_view_cli_replaces_legacy_flag()
    test_customer_service_triage_instruction()
    test_public_conversation_triage_flags()
    test_ticket_initial_text()
    test_ticket_url()
    test_api_key_is_environment_only()
    test_search_pagination_stops_at_freshdesk_page_cap()
    test_complete_triage_rejects_search_cap_truncation()
    test_complete_search_retries_a_moving_view()
    test_complete_search_retries_duplicate_ticket_ids()
    test_required_group_names_must_be_unique()
    test_get_json_retries_direct_ssl_eof()
    test_get_json_retries_http_5xx()
    test_attachment_metadata()
    test_routing_rules_contract()
    test_merge_history_signals()
    test_fragment_merge_window_and_target()
    print("triage helper tests passed")
