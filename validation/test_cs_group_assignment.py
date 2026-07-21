#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "freshdesk-ticket-assignment-helper" / "scripts" / "freshdesk_assign_cs_group.py"

assert SCRIPT.exists(), f"Missing assignment helper: {SCRIPT}"
spec = importlib.util.spec_from_file_location("freshdesk_assign_cs_group", SCRIPT)
assert spec and spec.loader
assignment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assignment)


def expect_error(func, text: str) -> None:
    try:
        func()
    except assignment.FreshdeskError as exc:
        assert text in str(exc)
    else:
        raise AssertionError(f"Expected FreshdeskError containing: {text}")


def test_ticket_id_parsing() -> None:
    assert assignment.parse_ticket_ids("101, 202") == [101, 202]
    expect_error(lambda: assignment.parse_ticket_ids("101,101"), "Duplicate")
    expect_error(lambda: assignment.parse_ticket_ids("0"), "positive")
    expect_error(lambda: assignment.parse_ticket_ids(","), "at least one")
    expect_error(
        lambda: assignment.assign_cs_tickets("example.freshdesk.com", "key", [101, 101], execute=False),
        "Duplicate",
    )


def test_api_key_is_environment_only() -> None:
    assert 'parser.add_argument("--api-key"' not in SCRIPT.read_text(encoding="utf-8")
    expect_error(
        lambda: assignment.assign_cs_tickets(
            "example.freshdesk.com",
            "key",
            list(range(1, assignment.MAX_TICKETS + 2)),
            execute=False,
        ),
        "At most",
    )


def test_group_names_must_be_unique() -> None:
    expect_error(
        lambda: assignment.resolve_assignment_groups(
            {10: "Technical Service", 20: "Customer Service", 21: "Customer Service"},
            "technical-service-to-customer-service",
        ),
        "not unique",
    )
    expect_error(
        lambda: assignment.resolve_assignment_groups(
            {10: "Technical Service", 20: "customer service"},
            "technical-service-to-customer-service",
        ),
        "not found",
    )


def test_candidate_contract() -> None:
    valid = {
        "id": 101,
        "status": 2,
        "spam": False,
        "responder_id": None,
        "group_id": 10,
        "tags": [],
    }
    assert assignment.candidate_error(valid, 101, 10) is None
    assert "Agent" in assignment.candidate_error({**valid, "responder_id": 99}, 101, 10)
    assert "source Group" in assignment.candidate_error({**valid, "group_id": 30}, 101, 10)
    assert "status" in assignment.candidate_error({**valid, "status": 4}, 101, 10)
    assert "Spam" in assignment.candidate_error({**valid, "spam": True}, 101, 10)
    assert "protected tag" in assignment.candidate_error({**valid, "tags": ["RMA"]}, 101, 10)
    without_responder = {key: value for key, value in valid.items() if key != "responder_id"}
    assert "Agent" in assignment.candidate_error(without_responder, 101, 10)
    assert "tags" in assignment.candidate_error({**valid, "tags": "RMA"}, 101, 10)
    assert assignment.candidate_error({**valid, "group_id": None}, 101, 10) is None
    assert "source Group" in assignment.candidate_error({**valid, "group_id": 20}, 101, 10)
    assert assignment.assignment_payload(20) == {"group_id": 20}
    assert "responder_id" not in assignment.assignment_payload(20)


def test_fixed_assignment_routes() -> None:
    groups = {10: "Technical Service", 20: "Customer Service"}
    assert assignment.resolve_assignment_groups(groups, "technical-service-to-customer-service") == (10, 20)
    assert assignment.resolve_assignment_groups(groups, "customer-service-to-technical-service") == (20, 10)

    customer_service_ticket = {
        "id": 201,
        "status": 2,
        "spam": False,
        "responder_id": None,
        "group_id": 20,
        "tags": [],
    }
    assert assignment.candidate_error(customer_service_ticket, 201, 20, "Customer Service", False) is None
    assert "source Group" in assignment.candidate_error(
        {**customer_service_ticket, "group_id": None}, 201, 20, "Customer Service", False
    )


def test_customer_service_to_technical_service_dry_run() -> None:
    assignment.get_json = lambda domain, api_key, path: {
        "id": 201,
        "subject": "VPN setup",
        "status": 2,
        "spam": False,
        "responder_id": None,
        "group_id": 20,
        "tags": [],
    }
    result = assignment.assign_cs_tickets(
        "example.freshdesk.com",
        "key",
        [201],
        execute=False,
        route="customer-service-to-technical-service",
        group_fetcher=lambda domain, api_key: {10: "Technical Service", 20: "Customer Service"},
    )
    assert result["route"] == "customer-service-to-technical-service"
    assert result["target_group"] == {"group_id": 10, "group_name": "Technical Service"}
    assert result["request_body"] == {"group_id": 10}
    assert result["tickets"][0]["ticket_link_markdown"] == "[201](https://example.freshdesk.com/a/tickets/201)"


def test_dry_run_and_execute_contract() -> None:
    state = {
        101: {
            "id": 101,
            "subject": "Order question",
            "status": 2,
            "spam": False,
            "responder_id": None,
            "group_id": 10,
            "tags": [],
        }
    }
    puts: list[tuple[int, dict]] = []

    assignment.fetch_groups = lambda domain, api_key: {10: "Technical Service", 20: "Customer Service"}

    def fake_get(domain: str, api_key: str, path: str):
        return dict(state[int(path.rsplit("/", 1)[1])])

    def fake_put(domain: str, api_key: str, ticket_id: int, body: dict):
        puts.append((ticket_id, dict(body)))
        state[ticket_id]["group_id"] = body["group_id"]
        return dict(state[ticket_id])

    assignment.get_json = fake_get
    assignment.put_ticket = fake_put

    preview = assignment.assign_cs_tickets("example.freshdesk.com", "key", [101], execute=False)
    assert preview["mode"] == "dry_run"
    assert preview["tickets"][0]["eligible"] is True
    assert puts == []

    result = assignment.assign_cs_tickets(
        "example.freshdesk.com",
        "key",
        [101],
        execute=True,
        confirmed_ticket_ids=[101],
    )
    assert puts == [(101, {"group_id": 20})]
    assert result["mode"] == "execute"
    assert result["tickets"][0]["after"]["group_id"] == 20
    assert result["tickets"][0]["after"]["responder_id"] is None
    assert result["completed"][0]["ticket_id"] == 101
    assert result["failed"] == []
    assert result["ambiguous"] == []


def test_confirmation_rejection_never_fetches_or_writes() -> None:
    called = False

    def forbidden_group_fetch(domain: str, api_key: str):
        nonlocal called
        called = True
        return {}

    expect_error(
        lambda: assignment.assign_cs_tickets(
            "example.freshdesk.com",
            "key",
            [101, 102],
            execute=True,
            confirmed_ticket_ids=[102, 101],
            group_fetcher=forbidden_group_fetch,
        ),
        "exact Ticket IDs",
    )
    assert called is False


def test_preflight_checks_all_tickets_before_any_write() -> None:
    state = {
        101: {"id": 101, "status": 2, "spam": False, "responder_id": None, "group_id": 10, "tags": []},
        102: {"id": 102, "status": 2, "spam": False, "responder_id": None, "group_id": 30, "tags": []},
    }
    puts: list[int] = []
    assignment.get_json = lambda domain, api_key, path: dict(state[int(path.rsplit("/", 1)[1])])
    assignment.put_ticket = lambda domain, api_key, ticket_id, body: puts.append(ticket_id)
    expect_error(
        lambda: assignment.assign_cs_tickets(
            "example.freshdesk.com",
            "key",
            [101, 102],
            execute=True,
            confirmed_ticket_ids=[101, 102],
            group_fetcher=lambda domain, api_key: {
                10: "Technical Service",
                20: "Customer Service",
                30: "MX Support",
            },
        ),
        "Preflight failed",
    )
    assert puts == []


def test_mid_batch_precondition_stop_preserves_progress() -> None:
    state = {
        101: {"id": 101, "status": 2, "spam": False, "responder_id": None, "group_id": 10, "tags": []},
        102: {"id": 102, "status": 2, "spam": False, "responder_id": None, "group_id": 10, "tags": []},
    }
    reads = {101: 0, 102: 0}

    def fake_get(domain: str, api_key: str, path: str):
        ticket_id = int(path.rsplit("/", 1)[1])
        reads[ticket_id] += 1
        ticket = dict(state[ticket_id])
        if ticket_id == 102 and reads[ticket_id] > 1:
            ticket["responder_id"] = 77
        return ticket

    def fake_put(domain: str, api_key: str, ticket_id: int, body: dict):
        state[ticket_id]["group_id"] = body["group_id"]

    assignment.get_json = fake_get
    assignment.put_ticket = fake_put
    result = assignment.assign_cs_tickets(
        "example.freshdesk.com",
        "key",
        [101, 102],
        execute=True,
        confirmed_ticket_ids=[101, 102],
        group_fetcher=lambda domain, api_key: {10: "Technical Service", 20: "Customer Service"},
    )
    assert result["success"] is False
    assert [row["ticket_id"] for row in result["completed"]] == [101]
    assert result["failed"][0]["ticket_id"] == 102
    assert result["failed"][0]["phase"] == "pre_put"
    assert result["ambiguous"] == []
    assert result["unattempted_ticket_ids"] == []


def test_post_write_agent_assignment_is_not_completed() -> None:
    state = {
        101: {
            "id": 101,
            "subject": "Order question",
            "status": 2,
            "spam": False,
            "responder_id": None,
            "group_id": 10,
            "tags": [],
        }
    }

    assignment.fetch_groups = lambda domain, api_key: {10: "Technical Service", 20: "Customer Service"}
    assignment.get_json = lambda domain, api_key, path: dict(state[101])

    def fake_put(domain: str, api_key: str, ticket_id: int, body: dict):
        state[101]["group_id"] = body["group_id"]
        state[101]["responder_id"] = 99

    assignment.put_ticket = fake_put
    result = assignment.assign_cs_tickets(
        "example.freshdesk.com",
        "key",
        [101],
        execute=True,
        confirmed_ticket_ids=[101],
    )
    assert result["success"] is False
    assert result["completed"] == []
    assert result["failed"][0]["ticket_id"] == 101
    assert result["failed"][0]["phase"] == "verify"
    assert result["tickets"][0]["after"]["responder_id"] == 99


def test_post_write_readback_error_is_ambiguous() -> None:
    ticket = {"id": 101, "status": 2, "spam": False, "responder_id": None, "group_id": 10, "tags": []}
    reads = 0

    def fake_get(domain: str, api_key: str, path: str):
        nonlocal reads
        reads += 1
        if reads == 3:
            raise assignment.FreshdeskError("invalid JSON")
        return dict(ticket)

    assignment.get_json = fake_get
    assignment.put_ticket = lambda domain, api_key, ticket_id, body: None
    result = assignment.assign_cs_tickets(
        "example.freshdesk.com",
        "key",
        [101],
        execute=True,
        confirmed_ticket_ids=[101],
        group_fetcher=lambda domain, api_key: {10: "Technical Service", 20: "Customer Service"},
    )
    assert result["success"] is False
    assert result["completed"] == []
    assert result["failed"] == []
    assert result["ambiguous"][0] == {
        "ticket_id": 101,
        "phase": "readback",
        "reason": "post-write verification failed: invalid JSON",
    }
    assert result["unattempted_ticket_ids"] == []


def test_invalid_json_is_wrapped() -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b"not-json"

    with patch.object(assignment.urllib.request, "urlopen", return_value=FakeResponse()):
        expect_error(
            lambda: assignment.request_json("example.freshdesk.com", "key", "/api/v2/groups"),
            "invalid JSON",
        )


if __name__ == "__main__":
    test_ticket_id_parsing()
    test_api_key_is_environment_only()
    test_group_names_must_be_unique()
    test_candidate_contract()
    test_fixed_assignment_routes()
    test_customer_service_to_technical_service_dry_run()
    test_dry_run_and_execute_contract()
    test_confirmation_rejection_never_fetches_or_writes()
    test_preflight_checks_all_tickets_before_any_write()
    test_mid_batch_precondition_stop_preserves_progress()
    test_post_write_agent_assignment_is_not_completed()
    test_post_write_readback_error_is_ambiguous()
    test_invalid_json_is_wrapped()
    print("CS group assignment tests passed")
