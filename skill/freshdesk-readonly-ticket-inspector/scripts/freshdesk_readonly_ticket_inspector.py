#!/usr/bin/env python3
"""Read-only Freshdesk Ticket metadata inspector."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
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


def get_json(domain: str, api_key: str, path: str, params: dict[str, Any] | None = None) -> Any:
    query = urllib.parse.urlencode(params or {})
    url = f"https://{domain}{path}"
    if query:
        url = f"{url}?{query}"

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": auth_header(api_key),
            "Accept": "application/json",
            "User-Agent": "freshdesk-readonly-ticket-inspector/1.0",
        },
        method="GET",
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=READ_TIMEOUT_SECONDS) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload) if payload else None
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 2:
                retry_after = exc.headers.get("Retry-After")
                delay = int(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                time.sleep(delay)
                continue
            detail = exc.read().decode("utf-8", errors="replace")
            raise FreshdeskError(f"GET {path} failed with HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise FreshdeskError(f"GET {path} failed: {exc.reason}") from exc

    raise FreshdeskError(f"GET {path} failed after retries.")


def paginate_list(domain: str, api_key: str, path: str, limit: int, per_page: int = 100) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while len(rows) < limit:
        batch = get_json(domain, api_key, path, {"page": page, "per_page": min(per_page, limit - len(rows))})
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return rows[:limit]


def fetch_groups(domain: str, api_key: str) -> dict[int, str]:
    groups = paginate_list(domain, api_key, "/api/v2/groups", limit=1000)
    return {
        int(group["id"]): str(group.get("name") or f"Group {group['id']}")
        for group in groups
        if group.get("id") is not None
    }


def fetch_agents(domain: str, api_key: str) -> dict[int, str]:
    agents = paginate_list(domain, api_key, "/api/v2/agents", limit=1000)
    names: dict[int, str] = {}
    for agent in agents:
        agent_id = agent.get("id")
        if agent_id is None:
            continue
        contact = agent.get("contact") if isinstance(agent.get("contact"), dict) else {}
        name = contact.get("name") or agent.get("name") or f"Agent {agent_id}"
        names[int(agent_id)] = str(name)
    return names


def fetch_tickets(domain: str, api_key: str, limit: int, query: str | None) -> tuple[list[dict[str, Any]], int | None]:
    if query:
        payload = get_json(domain, api_key, "/api/v2/search/tickets", {"query": f'"{query}"', "page": 1})
        if not isinstance(payload, dict):
            raise FreshdeskError("Freshdesk search response was not a JSON object.")
        results = payload.get("results")
        if not isinstance(results, list):
            raise FreshdeskError("Freshdesk search response did not include a results list.")
        return results[:limit], int(payload["total"]) if payload.get("total") is not None else None

    tickets = paginate_list(domain, api_key, "/api/v2/tickets", limit=limit)
    return tickets, None


def shape_ticket(ticket: dict[str, Any], agents: dict[int, str], groups: dict[int, str]) -> dict[str, Any]:
    responder_id = ticket.get("responder_id")
    group_id = ticket.get("group_id")
    responder_int = int(responder_id) if responder_id is not None else None
    group_int = int(group_id) if group_id is not None else None
    return {
        "ticket_id": ticket.get("id"),
        "subject": ticket.get("subject"),
        "status": ticket.get("status"),
        "priority": ticket.get("priority"),
        "created_at": ticket.get("created_at"),
        "updated_at": ticket.get("updated_at"),
        "requester_id": ticket.get("requester_id"),
        "responder_id": responder_id,
        "agent_name": agents.get(responder_int) if responder_int is not None else None,
        "group_id": group_id,
        "group_name": groups.get(group_int) if group_int is not None else None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read Freshdesk Ticket IDs, subjects, Agent names, and Group names using GET-only API calls."
    )
    parser.add_argument("--domain", default=os.getenv("FRESHDESK_DOMAIN"), help="Freshdesk domain, e.g. example.freshdesk.com")
    parser.add_argument("--api-key", default=os.getenv("FRESHDESK_API_KEY"), help="Freshdesk API key. Prefer FRESHDESK_API_KEY.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum tickets to return. Default: 20")
    parser.add_argument("--query", help="Optional Freshdesk search query, e.g. 'group_id:123 AND agent_id:null'")
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
    if args.limit < 1:
        print("--limit must be at least 1.", file=sys.stderr)
        return 2

    try:
        domain = normalize_domain(args.domain)
        groups = fetch_groups(domain, args.api_key)
        agents = fetch_agents(domain, args.api_key)
        tickets, total = fetch_tickets(domain, args.api_key, args.limit, args.query)
        output = {
            "domain": domain,
            "mode": "search" if args.query else "recent",
            "query": args.query,
            "ticket_count": len(tickets),
            "freshdesk_total": total,
            "agent_count": len(agents),
            "group_count": len(groups),
            "tickets": [shape_ticket(ticket, agents, groups) for ticket in tickets],
            "safety": {
                "freshdesk_methods_used": ["GET"],
                "writes_allowed": False,
            },
        }
    except FreshdeskError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    indent = 2 if args.pretty else None
    print(json.dumps(output, ensure_ascii=False, indent=indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
