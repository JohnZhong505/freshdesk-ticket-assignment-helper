from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "skills"
    / "freshdesk-needs-follow-up-ticket-numbers"
    / "scripts"
    / "freshdesk_needs_follow_up_ticket_numbers.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("freshdesk_followup_runtime_tests", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FreshdeskFollowupRuntimeMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_module()

    def test_version_flag_needs_no_credentials(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--version"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "freshdesk-needs-follow-up-ticket-numbers 1.7.1")
        self.assertEqual(result.stderr, "")

    def test_run_metadata_uses_device_local_time_and_english_format(self) -> None:
        finished_at = datetime(2026, 7, 22, 17, 0, tzinfo=timezone(timedelta(hours=8)))

        metadata = self.mod.build_run_metadata(10.0, 12.345, finished_at)

        self.assertEqual(metadata["elapsed_seconds"], 2.35)
        self.assertEqual(metadata["finished_at"], "2026-07-22T17:00:00+08:00")
        self.assertEqual(
            metadata["finished_at_display"],
            "Jul 22, 2026, 5:00 PM Local Time (UTC+08:00)",
        )

    def test_table_output_appends_version_and_run_information(self) -> None:
        output = {
            "script_version": "1.7.1",
            "groups": [],
            "cache": {"cache_hits": 9, "cache_misses": 1, "enabled": True},
            "run": {
                "elapsed_seconds": 12.34,
                "finished_at": "2026-07-22T17:00:00+08:00",
                "finished_at_display": "Jul 22, 2026, 5:00 PM Local Time (UTC+08:00)",
            },
        }

        rendered = self.mod.format_table_output(output)

        self.assertIn("Version: 1.7.1", rendered)
        self.assertIn("Run time: 12.34 seconds", rendered)
        self.assertIn("Finished: Jul 22, 2026, 5:00 PM Local Time (UTC+08:00)", rendered)


if __name__ == "__main__":
    unittest.main()
