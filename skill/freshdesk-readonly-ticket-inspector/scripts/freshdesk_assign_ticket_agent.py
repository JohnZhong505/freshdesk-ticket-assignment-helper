#!/usr/bin/env python3
"""Guarded helper for a supervised single-ticket Freshdesk assignment update."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


READ_TIMEOUT_SECONDS = 30


class FreshdeskError(RuntimeError):
    pass


def normalize_domain(domain: str) -> str:
    value = domain.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    if not value:
        raise FreshdeskError("Freshdesk domain is empty.")
    return value


def auth_header(api_key: str) -> str:
    token = base64.b64encode(f"{api_key}:X".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def request_json(domain: str, api_key: str, path: str, method: str, body: dict[str, Any] | None = None) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"https://{domain}{path}",
        data=data,
        headers={
            "Authorization": auth_header(api_key),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "freshdesk-readonly-ticket-inspector/1.0",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=READ_TIMEOUT_SECONDS) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FreshdeskError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise FreshdeskError(f"{method} {path} failed: {exc.reason}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare or execute a supervised single-ticket Freshdesk Agent/Group assignment update."
    )
    parser.add_argument("--domain", default=os.getenv("FRESHDESK_DOMAIN"), help="Freshdesk domain, e.g. example.freshdesk.com")
    parser.add_argument("--api-key", default=os.getenv("FRESHDESK_API_KEY"), help="Freshdesk API key. Prefer FRESHDESK_API_KEY.")
    parser.add_argument("--ticket-id", type=int, required=True, help="Exact Freshdesk Ticket ID to update.")
    parser.add_argument("--responder-id", type=int, required=True, help="Target Freshdesk Agent ID for responder_id.")
    parser.add_argument("--group-id", type=int, help="Optional target Freshdesk Group ID.")
    parser.add_argument("--execute", action="store_true", help="Actually send PUT /api/v2/tickets/[id]. Omit for dry-run.")
    parser.add_argument("--confirm-ticket-id", type=int, help="Must equal --ticket-id when --execute is used.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.domain:
        print("Missing Freshdesk domain. Set FRESHDESK_DOMAIN or pass --domain.", file=sys.stderr)
        return 2
    if not args.api_key:
        print("Missing Freshdesk API key. Set FRESHDESK_API_KEY or pass --api-key.", file=sys.stderr)
        return 2
    if args.execute and args.confirm_ticket_id != args.ticket_id:
        print("--execute requires --confirm-ticket-id equal to --ticket-id.", file=sys.stderr)
        return 2

    domain = normalize_domain(args.domain)
    body: dict[str, Any] = {"responder_id": args.responder_id}
    if args.group_id is not None:
        body["group_id"] = args.group_id

    try:
        before = request_json(domain, args.api_key, f"/api/v2/tickets/{args.ticket_id}", "GET")
        output: dict[str, Any] = {
            "domain": domain,
            "ticket_id": args.ticket_id,
            "execute": args.execute,
            "request": {
                "method": "PUT" if args.execute else "DRY_RUN_ONLY",
                "path": f"/api/v2/tickets/{args.ticket_id}",
                "body": body,
            },
            "before": {
                "ticket_id": before.get("id") if isinstance(before, dict) else None,
                "subject": before.get("subject") if isinstance(before, dict) else None,
                "responder_id": before.get("responder_id") if isinstance(before, dict) else None,
                "group_id": before.get("group_id") if isinstance(before, dict) else None,
            },
        }
        if args.execute:
            updated = request_json(domain, args.api_key, f"/api/v2/tickets/{args.ticket_id}", "PUT", body)
            output["after"] = {
                "ticket_id": updated.get("id") if isinstance(updated, dict) else None,
                "subject": updated.get("subject") if isinstance(updated, dict) else None,
                "responder_id": updated.get("responder_id") if isinstance(updated, dict) else None,
                "group_id": updated.get("group_id") if isinstance(updated, dict) else None,
            }
        else:
            output["after"] = None
            output["safety"] = "No Freshdesk write was sent. Add --execute and --confirm-ticket-id only under user supervision."
    except FreshdeskError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    indent = 2 if args.pretty else None
    print(json.dumps(output, ensure_ascii=False, indent=indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
