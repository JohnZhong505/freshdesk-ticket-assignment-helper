#!/usr/bin/env python3
from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "skills" / "freshdesk-ticket-assignment-helper" / "scripts"
SCRIPT = SCRIPT_DIR / "freshdesk_send_triage_cards.py"
sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("freshdesk_send_triage_cards", SCRIPT)
assert spec and spec.loader
delivery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(delivery)


def payload() -> dict:
    tickets = [
        {
            "ticket_id": 137100,
            "ticket_url": "https://glinetservice.freshdesk.com/a/tickets/137100",
            "ticket_link_markdown": "[137100](https://glinetservice.freshdesk.com/a/tickets/137100)",
            "merge_check": {"candidates": []},
        },
        {
            "ticket_id": 137101,
            "ticket_url": "https://glinetservice.freshdesk.com/a/tickets/137101",
            "ticket_link_markdown": "[137101](https://glinetservice.freshdesk.com/a/tickets/137101)",
            "merge_check": {"candidates": []},
        },
    ]
    return {
        "snapshot": {"triage_view": "customer-service", "ticket_count": 2, "tickets": tickets},
        "classification": {
            "view": "customer-service",
            "tickets": [
                {
                    "ticket_id": 137100,
                    "bucket": "Stay in Customer Service",
                    "confidence": "high",
                    "reason": "Shop account",
                    "evidence": "客户咨询网店账号",
                    "merge_target_ticket_id": None,
                },
                {
                    "ticket_id": 137101,
                    "bucket": "Technical Service",
                    "confidence": "medium",
                    "reason": "Cloud account",
                    "evidence": "客户反馈 GoodCloud 登录问题",
                    "merge_target_ticket_id": None,
                },
            ],
        },
    }


def run_main(arguments: list[str], value: dict) -> tuple[int, dict]:
    original_stdin = sys.stdin
    output = io.StringIO()
    sys.stdin = io.StringIO(json.dumps(value))
    try:
        with redirect_stdout(output):
            code = delivery.main(arguments)
    finally:
        sys.stdin = original_stdin
    return code, json.loads(output.getvalue()) if output.getvalue() else {}


def test_preview_is_default_and_uses_fixed_rendering() -> None:
    original_find_binary = delivery.find_binary
    delivery.find_binary = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("preview touched DWS"))
    try:
        code, result = run_main(["--view", "customer-service"], payload())
    finally:
        delivery.find_binary = original_find_binary
    assert code == 0
    assert result["status"] == "preview"
    assert result["view"] == "customer-service"
    assert result["target"] == "Amber"
    card = result["cards"][0]
    assert card.index("### Technical Service") < card.index("### 保留 Customer Service")
    assert "[137100](https://glinetservice.freshdesk.com/a/tickets/137100)" in card
    assert "Loading..." not in card

    with tempfile.TemporaryDirectory() as directory:
        input_path = Path(directory) / "delivery.json"
        input_path.write_text(json.dumps(payload()), encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            assert delivery.main(["--view", "customer-service", "--input", str(input_path)]) == 0
        assert json.loads(output.getvalue())["status"] == "preview"


def test_mismatched_view_fails_closed() -> None:
    code, _result = run_main(["--view", "technical-service"], payload())
    assert code == 1


def test_empty_input_never_contacts_dws() -> None:
    value = {
        "snapshot": {"triage_view": "technical-service", "ticket_count": 0, "tickets": []},
        "classification": {"view": "technical-service", "tickets": []},
    }
    original_find_binary = delivery.find_binary
    delivery.find_binary = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("empty result touched DWS"))
    try:
        code, result = run_main(["--view", "technical-service", "--send"], value)
    finally:
        delivery.find_binary = original_find_binary
    assert code == 0
    assert result == {"status": "empty", "view": "technical-service", "target": "测试群", "card_count": 0}


def test_send_uses_fixed_target_and_requires_explicit_flag() -> None:
    original_find_binary = delivery.find_binary
    original_preflight = delivery.preflight_dws
    original_send = delivery.send_stream_card
    calls: list[tuple[str, str, str]] = []
    delivery.find_binary = lambda _explicit, _name: "dws"
    delivery.preflight_dws = lambda _binary: None
    delivery.send_stream_card = lambda binary, view, card: calls.append((binary, view, card)) or "biz-1"
    try:
        with tempfile.TemporaryDirectory() as directory:
            code, result = run_main(
                ["--view", "customer-service", "--send", "--state-dir", directory], payload()
            )
    finally:
        delivery.find_binary = original_find_binary
        delivery.preflight_dws = original_preflight
        delivery.send_stream_card = original_send
    assert code == 0
    assert result == {"status": "sent", "view": "customer-service", "target": "Amber", "card_count": 1}
    assert calls and calls[0][1] == "customer-service"
    assert delivery.dws_target_args("customer-service") == [
        "--receiver",
        "DesWciiDKviS2g4tfIxy7uH14hiPX2oeF9Jl",
    ]


def test_technical_target_and_partial_send_resume() -> None:
    value = payload()
    value["snapshot"]["triage_view"] = "technical-service"
    value["classification"]["view"] = "technical-service"
    value["classification"]["tickets"][0]["bucket"] = "CS"
    value["classification"]["tickets"][1]["bucket"] = "Technical Service"
    original_find_binary = delivery.find_binary
    original_preflight = delivery.preflight_dws
    original_render = delivery.render_card_parts
    original_send = delivery.send_stream_card
    sent: list[str] = []
    fail_second = True
    delivery.find_binary = lambda _explicit, _name: "dws"
    delivery.preflight_dws = lambda _binary: None
    delivery.render_card_parts = lambda *_args, **_kwargs: ["part one", "part two"]

    def send(_binary, view, card):
        nonlocal fail_second
        assert view == "technical-service"
        if card == "part two" and fail_second:
            fail_second = False
            raise delivery.CronError("second part failed")
        sent.append(card)
        return "biz"

    delivery.send_stream_card = send
    try:
        with tempfile.TemporaryDirectory() as directory:
            first, _result = run_main(
                ["--view", "technical-service", "--send", "--state-dir", directory], value
            )
            second, result = run_main(
                ["--view", "technical-service", "--send", "--state-dir", directory], value
            )
    finally:
        delivery.find_binary = original_find_binary
        delivery.preflight_dws = original_preflight
        delivery.render_card_parts = original_render
        delivery.send_stream_card = original_send
    assert first == 1
    assert second == 0
    assert sent == ["part one", "part two"]
    assert result["target"] == "测试群"
    assert delivery.dws_target_args("technical-service") == ["--group", "cidOXHoLP3FMfLpv2jif+iWPQ=="]


if __name__ == "__main__":
    test_preview_is_default_and_uses_fixed_rendering()
    test_mismatched_view_fails_closed()
    test_empty_input_never_contacts_dws()
    test_send_uses_fixed_target_and_requires_explicit_flag()
    test_technical_target_and_partial_send_resume()
    print("interactive triage delivery tests passed")
