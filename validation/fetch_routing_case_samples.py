#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "validation" / "routing-source.md"
OUTPUT = ROOT / "validation" / "live-output-routing-samples.json"
INSPECTOR = ROOT / "skills" / "freshdesk-readonly-ticket-inspector" / "scripts" / "freshdesk_readonly_ticket_inspector.py"


def load_inspector() -> Any:
    spec = importlib.util.spec_from_file_location("freshdesk_readonly_ticket_inspector", INSPECTOR)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load {INSPECTOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_cases(markdown: str) -> list[dict[str, str]]:
    bucket = "Uncategorized"
    seen: set[str] = set()
    cases: list[dict[str, str]] = []
    for line in markdown.splitlines():
        heading = re.match(r"^##\s+\*\*(.+?)\*\*", line.strip())
        if heading:
            bucket = heading.group(1).strip(" :：")
        for ticket_id in re.findall(r"/tickets/(\d+)", line):
            if ticket_id in seen:
                continue
            seen.add(ticket_id)
            cases.append({"ticket_id": ticket_id, "source_bucket": bucket, "source_note": line.strip()})
    return cases


def first_customer_text(inspector: Any, ticket: dict[str, Any], conversations: list[dict[str, Any]]) -> str:
    description = ticket.get("description_text") or inspector.strip_html(ticket.get("description"))
    if isinstance(description, str) and description.strip():
        return description.strip()

    public_customer = [
        row
        for row in conversations
        if row.get("incoming") is True and not row.get("private") and not inspector.is_internal_mirror_incoming(ticket, row)
    ]
    public_customer.sort(key=lambda row: str(row.get("created_at") or ""))
    if not public_customer:
        return ""
    return inspector.conversation_text(public_customer[0]) or ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch first customer texts for DingTalk routing examples.")
    parser.add_argument("--source", default=str(SOURCE))
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--domain", default=os.getenv("FRESHDESK_DOMAIN") or "glinetservice.freshdesk.com")
    parser.add_argument("--api-key", default=os.getenv("FRESHDESK_API_KEY"))
    args = parser.parse_args()

    if not args.api_key:
        print("Missing FRESHDESK_API_KEY.", file=sys.stderr)
        return 2

    inspector = load_inspector()
    domain = inspector.normalize_domain(args.domain)
    source = Path(args.source)
    cases = parse_cases(source.read_text(encoding="utf-8"))

    rows = []
    for case in cases:
        ticket_id = int(case["ticket_id"])
        ticket = inspector.get_json(domain, args.api_key, f"/api/v2/tickets/{ticket_id}")
        conversations = inspector.fetch_conversations(domain, args.api_key, ticket_id)
        rows.append(
            {
                **case,
                "subject": ticket.get("subject"),
                "first_customer_text": first_customer_text(inspector, ticket, conversations),
            }
        )

    output = Path(args.output)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} samples to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
