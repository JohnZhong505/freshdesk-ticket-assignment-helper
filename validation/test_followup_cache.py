from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
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
    spec = importlib.util.spec_from_file_location("freshdesk_followup_cache_tests", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FreshdeskFollowupCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_module()
        cls.now = datetime(2026, 7, 15, 8, 30, tzinfo=timezone.utc)

    def test_prune_cache_removes_expired_entry(self) -> None:
        cache = {
            "version": self.mod.CACHE_VERSION,
            "tickets": {"old": {"last_seen_at": "2026-05-01T00:00:00Z"}},
        }

        removed = self.mod.prune_cache(cache, self.now, 30)

        self.assertEqual(removed, 1)
        self.assertEqual(cache["tickets"], {})

    def test_prune_cache_keeps_recent_entry(self) -> None:
        cache = {
            "version": self.mod.CACHE_VERSION,
            "tickets": {"recent": {"last_seen_at": "2026-07-01T00:00:00Z"}},
        }

        removed = self.mod.prune_cache(cache, self.now, 30)

        self.assertEqual(removed, 0)
        self.assertIn("recent", cache["tickets"])

    def test_prune_cache_falls_back_to_legacy_cached_at(self) -> None:
        cache = {
            "version": self.mod.CACHE_VERSION,
            "tickets": {
                "legacy-recent": {"cached_at": "2026-07-01T00:00:00Z"},
                "legacy-old": {"cached_at": "2026-05-01T00:00:00Z"},
            },
        }

        removed = self.mod.prune_cache(cache, self.now, 30)

        self.assertEqual(removed, 1)
        self.assertEqual(list(cache["tickets"]), ["legacy-recent"])

    def test_cache_hit_updates_last_seen_at(self) -> None:
        ticket = self.ticket(123)
        entry = self.mod.ticket_cache_entry(ticket, {"first_responded_at": "2026-07-01T00:00:00Z"})
        entry["last_seen_at"] = "2026-06-01T00:00:00Z"
        cache = {"version": self.mod.CACHE_VERSION, "tickets": {"123": entry}}

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            self.mod, "fetch_ticket_with_stats", side_effect=AssertionError("cache hit must not fetch")
        ):
            self.mod.fetch_ticket_stats_for_pool(
                "example.freshdesk.com",
                "key",
                [ticket],
                cache,
                True,
                Path(temp_dir) / "cache.json",
                self.now,
            )

        self.assertEqual(cache["tickets"]["123"]["last_seen_at"], "2026-07-15T08:30:00Z")

    def test_save_cache_prunes_and_replaces_atomically(self) -> None:
        cache = {
            "version": self.mod.CACHE_VERSION,
            "tickets": {
                "recent": {"last_seen_at": "2026-07-01T00:00:00Z"},
                "old": {"last_seen_at": "2026-05-01T00:00:00Z"},
            },
        }
        original_replace = Path.replace

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache.json"
            with patch.object(
                Path,
                "replace",
                autospec=True,
                side_effect=lambda source, target: original_replace(source, target),
            ) as replace_mock:
                removed = self.mod.save_cache(cache_path, cache, True, self.now, 30)

            saved = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(replace_mock.call_count, 1)
            self.assertFalse(cache_path.with_suffix(".json.tmp").exists())

        self.assertEqual(removed, 1)
        self.assertEqual(list(saved["tickets"]), ["recent"])
        self.assertEqual(saved["retention_days"], 30)
        self.assertEqual(saved["pruned_entries"], 1)

    def test_checkpoint_preserves_valid_cache_and_retention(self) -> None:
        tickets = [self.ticket(ticket_id) for ticket_id in range(1, self.mod.CACHE_CHECKPOINT_MISSES + 1)]
        cache = {
            "version": self.mod.CACHE_VERSION,
            "tickets": {
                "recent": {"last_seen_at": "2026-07-01T00:00:00Z"},
                "old": {"last_seen_at": "2026-05-01T00:00:00Z"},
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            self.mod,
            "fetch_ticket_with_stats",
            return_value={"stats": {"first_responded_at": "2026-07-01T00:00:00Z"}},
        ):
            cache_path = Path(temp_dir) / "cache.json"
            self.mod.fetch_ticket_stats_for_pool(
                "example.freshdesk.com",
                "key",
                tickets,
                cache,
                True,
                cache_path,
                self.now,
                30,
            )
            saved = json.loads(cache_path.read_text(encoding="utf-8"))

        self.assertNotIn("old", saved["tickets"])
        self.assertIn("recent", saved["tickets"])
        self.assertEqual(saved["retention_days"], 30)
        self.assertEqual(saved["pruned_entries"], 1)
        self.assertEqual(len(saved["tickets"]), self.mod.CACHE_CHECKPOINT_MISSES + 1)

    def test_json_output_includes_retention_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "version": self.mod.CACHE_VERSION,
                        "tickets": {"old": {"last_seen_at": "2026-05-01T00:00:00Z"}},
                    }
                ),
                encoding="utf-8",
            )
            argv = [
                str(SCRIPT),
                "--domain",
                "example.freshdesk.com",
                "--api-key",
                "test-key",
                "--group-name",
                "Technical Service",
                "--cache-path",
                str(cache_path),
                "--cache-retention-days",
                "30",
                "--format",
                "json",
            ]
            search_metadata = {
                "group_query": "group_id:1",
                "group_agents_total": 0,
                "group_agents_active": 0,
                "group_agents_deactivated": 0,
            }
            stdout = io.StringIO()
            with patch.object(sys, "argv", argv), patch.object(
                self.mod, "fetch_groups", return_value=[{"id": 1, "name": "Technical Service"}]
            ), patch.object(self.mod, "fetch_group_agents", return_value=[]), patch.object(
                self.mod, "fetch_group_open_tickets", return_value=([], search_metadata)
            ), redirect_stdout(stdout):
                result = self.mod.main()

        output = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(output["script_version"], "1.7.1")
        self.assertGreaterEqual(output["run"]["elapsed_seconds"], 0)
        self.assertIn("T", output["run"]["finished_at"])
        self.assertIn("Local Time (UTC", output["run"]["finished_at_display"])
        self.assertEqual(output["cache"]["retention_days"], 30)
        self.assertEqual(output["cache"]["pruned_entries"], 1)
        self.assertEqual(output["cache"]["cache_hits"], 0)
        self.assertEqual(output["cache"]["cache_misses"], 0)
        self.assertEqual(output["runtime_notes"]["customer_response_recheck_window_seconds"], 300)
        self.assertEqual(output["runtime_notes"]["customer_response_recheck_candidates"], 0)
        self.assertEqual(output["runtime_notes"]["customer_response_internal_sender_exclusions"], 0)
        self.assertEqual(output["runtime_notes"]["customer_response_recheck_unverified"], 0)

    def test_existing_ticket_classification_is_unchanged(self) -> None:
        new_ticket = self.mod.classify_ticket(
            {**self.ticket(1), "fr_due_by": "2026-07-14T00:00:00Z"}, {}, self.now
        )
        customer_responded = self.mod.classify_ticket(
            self.ticket(2),
            {
                "first_responded_at": "2026-07-10T00:00:00Z",
                "agent_responded_at": "2026-07-11T00:00:00Z",
                "requester_responded_at": "2026-07-12T00:00:00Z",
            },
            self.now,
        )
        outbound_only = self.mod.classify_ticket(
            {**self.ticket(3), "source": self.mod.OUTBOUND_EMAIL_SOURCE, "fr_due_by": "2026-07-14T00:00:00Z"},
            {},
            self.now,
            False,
        )

        self.assertEqual(
            new_ticket,
            {
                "new_ticket": True,
                "customer_responded_ticket": False,
                "fr_overdue": True,
                "resolution_overdue": False,
            },
        )
        self.assertTrue(customer_responded["customer_responded_ticket"])
        self.assertFalse(customer_responded["new_ticket"])
        self.assertFalse(outbound_only["new_ticket"])
        self.assertFalse(outbound_only["fr_overdue"])

    @staticmethod
    def ticket(ticket_id: int) -> dict[str, object]:
        return {
            "id": ticket_id,
            "updated_at": "2026-07-15T00:00:00Z",
            "status": 2,
            "group_id": 1,
            "responder_id": 2,
            "source": 1,
            "due_by": "2026-07-20T00:00:00Z",
            "fr_due_by": "2026-07-16T00:00:00Z",
        }


if __name__ == "__main__":
    unittest.main()
