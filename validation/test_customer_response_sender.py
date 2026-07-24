from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "skills"
    / "freshdesk-needs-follow-up-ticket-numbers"
    / "scripts"
    / "freshdesk_needs_follow_up_ticket_numbers.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("freshdesk_customer_sender_tests", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class CustomerResponseSenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_module()
        cls.now = datetime(2026, 7, 15, 8, 30, tzinfo=timezone.utc)

    def test_recheck_window_is_five_minutes(self) -> None:
        self.assertTrue(self.mod.should_recheck_customer_response_sender(self.stats("08:00:00", "08:05:00")))
        self.assertFalse(self.mod.should_recheck_customer_response_sender(self.stats("08:00:00", "08:05:01")))

    def test_internal_sender_rules_are_scoped_to_internal_domains(self) -> None:
        for sender in (
            "support@gl-inet.com",
            "Support Team <support@glinet.biz>",
            "cs@gl-inet.com",
            "CS-Europe@glinet.biz",
        ):
            with self.subTest(sender=sender):
                self.assertTrue(self.mod.is_internal_support_sender(sender))

        self.assertFalse(self.mod.is_internal_support_sender("cs-customer@example.com"))

    def test_latest_public_sender_ignores_private_and_input_order(self) -> None:
        conversations = [
            self.conversation(3, "2026-07-15T08:03:00Z", "customer@example.com", private=True),
            self.conversation(2, "2026-07-15T08:02:00Z", "Support <support@gl-inet.com>"),
            self.conversation(1, "2026-07-15T08:01:00Z", "customer@example.com"),
        ]

        self.assertTrue(self.mod.latest_public_sender_internal(conversations))

    def test_latest_public_sender_uses_numeric_id_for_timestamp_ties(self) -> None:
        conversations = [
            self.conversation(9, "2026-07-15T08:02:00Z", "customer@example.com"),
            self.conversation(10, "2026-07-15T08:02:00Z", "support@gl-inet.com"),
        ]

        self.assertTrue(self.mod.latest_public_sender_internal(conversations))

    def test_fast_external_reply_is_kept_even_when_support_email_is_internal(self) -> None:
        conversation = self.conversation(1, "2026-07-15T08:00:10Z", "customer@example.com")
        conversation["support_email"] = "support@gl-inet.com"
        classification = self.mod.classify_ticket(
            self.ticket(1), self.stats("08:00:00", "08:00:10"), self.now, None, False
        )

        self.assertFalse(self.mod.latest_public_sender_internal([conversation]))
        self.assertTrue(classification["customer_responded_ticket"])

    def test_source_one_internal_sender_is_excluded(self) -> None:
        classification = self.mod.classify_ticket(
            self.ticket(1), self.stats("08:00:00", "08:00:10"), self.now, None, True
        )

        self.assertEqual(self.ticket(1)["source"], 1)
        self.assertFalse(classification["customer_responded_ticket"])

    def test_outbound_new_latest_external_sender_becomes_customer_responded(self) -> None:
        ticket = {**self.ticket(1), "source": self.mod.OUTBOUND_EMAIL_SOURCE}

        classification = self.mod.classify_ticket(ticket, {}, self.now, True)

        self.assertFalse(classification["new_ticket"])
        self.assertTrue(classification["customer_responded_ticket"])

    def test_outbound_new_latest_internal_sender_is_waiting_for_customer(self) -> None:
        ticket = {**self.ticket(1), "source": self.mod.OUTBOUND_EMAIL_SOURCE}

        classification = self.mod.classify_ticket(ticket, {}, self.now, False)

        self.assertFalse(classification["new_ticket"])
        self.assertFalse(classification["customer_responded_ticket"])
        self.assertFalse(classification["fr_overdue"])

    def test_outbound_new_sender_check_is_cached_before_fr_due(self) -> None:
        ticket = {**self.ticket(1), "source": self.mod.OUTBOUND_EMAIL_SOURCE}
        cache = {"version": self.mod.CACHE_VERSION, "tickets": {}}
        conversations = [self.conversation(1, "2026-07-15T08:00:10Z", "customer@example.com")]

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            self.mod, "fetch_ticket_with_stats", return_value={"stats": {}}
        ), patch.object(
            self.mod, "fetch_ticket_conversations", return_value=conversations
        ) as conversations_mock:
            cache_path = Path(temp_dir) / "cache.json"
            _, first_outbound, _, first_stats = self.mod.fetch_ticket_stats_for_pool(
                "example.freshdesk.com", "key", [ticket], cache, True, cache_path, self.now
            )
            _, cached_outbound, _, cached_stats = self.mod.fetch_ticket_stats_for_pool(
                "example.freshdesk.com", "key", [ticket], cache, True, cache_path, self.now
            )

        self.assertTrue(first_outbound[1])
        self.assertTrue(cached_outbound[1])
        self.assertEqual(conversations_mock.call_count, 1)
        self.assertEqual(first_stats["conversation_rechecks"], 1)
        self.assertEqual(cached_stats["conversation_rechecks"], 0)

    def test_outbound_sender_check_replaces_legacy_or_stale_cache_data(self) -> None:
        ticket = {**self.ticket(1), "source": self.mod.OUTBOUND_EMAIL_SOURCE}
        internal = [self.conversation(1, "2026-07-15T08:00:10Z", "support@gl-inet.com")]

        for cache_variant in ("legacy", "stale-rule"):
            with self.subTest(cache_variant=cache_variant):
                entry = self.mod.ticket_cache_entry(ticket, {})
                if cache_variant == "legacy":
                    entry["outbound_has_public_incoming_reply"] = True
                else:
                    entry["outbound_latest_public_customer_reply"] = True
                    entry["outbound_latest_public_customer_reply_rule_key"] = "old-rules"
                cache = {"version": self.mod.CACHE_VERSION, "tickets": {"1": entry}}

                with tempfile.TemporaryDirectory() as temp_dir, patch.object(
                    self.mod, "fetch_ticket_with_stats", side_effect=AssertionError("stats cache should hit")
                ), patch.object(
                    self.mod, "fetch_ticket_conversations", return_value=internal
                ) as conversations_mock:
                    _, outbound, _, _ = self.mod.fetch_ticket_stats_for_pool(
                        "example.freshdesk.com",
                        "key",
                        [ticket],
                        cache,
                        True,
                        Path(temp_dir) / "cache.json",
                        self.now,
                    )

                self.assertFalse(outbound[1])
                self.assertEqual(conversations_mock.call_count, 1)
                self.assertEqual(
                    cache["tickets"]["1"]["outbound_latest_public_customer_reply_rule_key"],
                    self.mod.internal_sender_rule_key(),
                )

    def test_outbound_missing_sender_stays_new_as_fail_safe(self) -> None:
        conversation = self.conversation(1, "2026-07-15T08:00:10Z", "customer@example.com")
        conversation.pop("from_email")
        ticket = {**self.ticket(1), "source": self.mod.OUTBOUND_EMAIL_SOURCE}

        sender_result = self.mod.latest_public_customer_reply([conversation])
        classification = self.mod.classify_ticket(ticket, {}, self.now, sender_result)

        self.assertIsNone(sender_result)
        self.assertTrue(classification["new_ticket"])
        self.assertFalse(classification["customer_responded_ticket"])

    def test_conversations_are_paginated_before_selecting_latest(self) -> None:
        page_one = [self.conversation(index, f"2026-07-15T08:00:{index % 60:02d}Z", "customer@example.com") for index in range(100)]
        latest = self.conversation(101, "2026-07-15T09:00:00Z", "support@gl-inet.com")

        def fake_get_json(_domain, _api_key, _path, params=None):
            return page_one if params["page"] == 1 else [latest]

        with patch.object(self.mod, "get_json", side_effect=fake_get_json) as get_json_mock:
            conversations = self.mod.fetch_ticket_conversations("example.freshdesk.com", "key", 1)

        self.assertEqual(len(conversations), 101)
        self.assertEqual(get_json_mock.call_count, 2)
        self.assertTrue(self.mod.latest_public_sender_internal(conversations))

    def test_invalid_conversations_response_fails_the_run(self) -> None:
        with patch.object(self.mod, "get_json", return_value={"error": "unexpected"}):
            with self.assertRaises(self.mod.FreshdeskError):
                self.mod.fetch_ticket_conversations("example.freshdesk.com", "key", 1)

    def test_sender_result_is_cached_and_allowlist_changes_invalidate_it(self) -> None:
        ticket = self.ticket(1)
        stats = self.stats("08:00:00", "08:00:10")
        cache = {"version": self.mod.CACHE_VERSION, "tickets": {}}
        internal = [self.conversation(1, "2026-07-15T08:00:10Z", "support@gl-inet.com")]

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            self.mod, "fetch_ticket_with_stats", return_value={"stats": stats}
        ), patch.object(self.mod, "fetch_ticket_conversations", return_value=internal) as conversations_mock:
            cache_path = Path(temp_dir) / "cache.json"
            _, _, sender_by_ticket, first_stats = self.mod.fetch_ticket_stats_for_pool(
                "example.freshdesk.com", "key", [ticket], cache, True, cache_path, self.now
            )
            _, _, cached_sender_by_ticket, cached_stats = self.mod.fetch_ticket_stats_for_pool(
                "example.freshdesk.com", "key", [ticket], cache, True, cache_path, self.now
            )

        self.assertTrue(sender_by_ticket[1])
        self.assertTrue(cached_sender_by_ticket[1])
        self.assertEqual(conversations_mock.call_count, 1)
        self.assertEqual(first_stats["customer_response_recheck_completed"], 1)
        self.assertEqual(cached_stats["customer_response_recheck_cache_hits"], 1)

        changed_allowlist = {*self.mod.INTERNAL_SUPPORT_EMAILS, "new-support@gl-inet.com"}
        external = [self.conversation(2, "2026-07-15T08:00:10Z", "customer@example.com")]
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            self.mod, "INTERNAL_SUPPORT_EMAILS", changed_allowlist
        ), patch.object(
            self.mod, "fetch_ticket_with_stats", side_effect=AssertionError("ticket cache should still hit")
        ), patch.object(self.mod, "fetch_ticket_conversations", return_value=external) as conversations_mock:
            _, _, changed_sender_by_ticket, changed_stats = self.mod.fetch_ticket_stats_for_pool(
                "example.freshdesk.com",
                "key",
                [ticket],
                cache,
                True,
                Path(temp_dir) / "cache.json",
                self.now,
            )

        self.assertFalse(changed_sender_by_ticket[1])
        self.assertEqual(conversations_mock.call_count, 1)
        self.assertEqual(changed_stats["customer_response_recheck_completed"], 1)

    @staticmethod
    def ticket(ticket_id: int) -> dict[str, object]:
        return {
            "id": ticket_id,
            "updated_at": "2026-07-15T08:05:00Z",
            "status": 2,
            "group_id": 1,
            "responder_id": 2,
            "requester_id": 3,
            "source": 1,
            "due_by": "2026-07-20T00:00:00Z",
            "fr_due_by": "2026-07-16T00:00:00Z",
        }

    @staticmethod
    def stats(agent_time: str, requester_time: str) -> dict[str, str]:
        return {
            "first_responded_at": "2026-07-15T07:00:00Z",
            "agent_responded_at": f"2026-07-15T{agent_time}Z",
            "requester_responded_at": f"2026-07-15T{requester_time}Z",
        }

    @staticmethod
    def conversation(conversation_id: int, created_at: str, from_email: str, private: bool = False) -> dict[str, object]:
        return {
            "id": conversation_id,
            "created_at": created_at,
            "from_email": from_email,
            "incoming": True,
            "private": private,
        }


if __name__ == "__main__":
    unittest.main()
