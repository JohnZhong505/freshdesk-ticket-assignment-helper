#!/usr/bin/env python3
"""Hermes no-agent entrypoint for the Customer Service triage view."""

from pathlib import Path
import os
import runpy
import sys


if any(argument in {"-h", "--help"} for argument in sys.argv[1:]):
    print("Run the Customer Service Freshdesk triage view as a Hermes no-agent cron script.")
    raise SystemExit(0)


def driver() -> Path:
    candidates = [
        os.getenv("FRESHDESK_TRIAGE_SKILL_DIR"),
        Path.home() / ".hermes" / "skills" / "freshdesk-ticket-assignment-helper",
        Path.home() / ".codex" / "skills" / "freshdesk-ticket-assignment-helper",
        Path.home() / ".agents" / "skills" / "freshdesk-ticket-assignment-helper",
    ]
    for root in candidates:
        if root and (path := Path(root) / "scripts" / "freshdesk_triage_cron.py").is_file():
            return path
    raise SystemExit("freshdesk-ticket-assignment-helper is not installed")


path = driver()
sys.argv = [str(path), "--view", "customer-service"]
runpy.run_path(str(path), run_name="__main__")
