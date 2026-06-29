#!/usr/bin/env python3
"""Read-only grouped Freshdesk needs-follow-up Ticket counter."""

from __future__ import annotations

import argparse
import base64
from collections import defaultdict
from email.utils import parseaddr
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_GROUP_NAME = "Technical Service"
FOLLOW_UP_DISPLAY_NAME = "\u9700\u8ddf\u8fdbTicket"
READ_TIMEOUT_SECONDS = 30
INTERNAL_SUPPORT_EMAIL_DOMAINS = {"gl-inet.com", "glinet.biz"}
INTERNAL_SUPPORT_EMAILS = {"cs@gl-inet.com", "support@gl-inet.com", "support@glinet.biz"}


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


def extract_email(value: str | None) -> str | None:
    if not value:
        return None
    _, email = parseaddr(value)
    normalized = (email or value).strip().lower()
    return normalized or None


def email_domain(value: str | None) -> str | None:
    email = extract_email(value)
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[1]


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
            "User-Agent": "freshdesk-needs-follow-up-ticket-numbers/1.0",
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
            reason_text = str(exc.reason).lower()
            if attempt < 2 and any(token in reason_text for token in ("timed out", "timeout", "unexpected eof", "handshake")):
                time.sleep(2**attempt)
                continue
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


def paginate_search(domain: str, api_key: str, query: str) -> tuple[list[dict[str, Any]], int | None]:
    rows: list[dict[str, Any]] = []
    page = 1
    total: int | None = None

    while True:
        payload = get_json(domain, api_key, "/api/v2/search/tickets", {"query": f'"{query}"', "page": page})
        if not isinstance(payload, dict):
            raise FreshdeskError("Freshdesk search response was not a JSON object.")

        if total is None and payload.get("total") is not None:
            total = int(payload["total"])

        batch = payload.get("results")
        if not isinstance(batch, list) or not batch:
            break

        rows.extend(batch)
        if len(batch) < 30:
            break
        page += 1

    return rows, total


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


def fetch_conversations(domain: str, api_key: str, ticket_id: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1

    while True:
        payload = get_json(
            domain,
            api_key,
            f"/api/v2/tickets/{ticket_id}/conversations",
            {"page": page, "per_page": 100},
        )
        if not isinstance(payload, list):
            raise FreshdeskError(f"Freshdesk conversations response for ticket {ticket_id} was not a JSON list.")

        batch = [item for item in payload if isinstance(item, dict)]
        if not batch:
            break

        rows.extend(batch)
        if len(payload) < 100:
            break
        page += 1

    return rows


def resolve_group_id(groups: dict[int, str], group_id: int | None, group_name: str | None) -> int:
    if group_id is not None:
        return group_id

    candidate_name = (group_name or DEFAULT_GROUP_NAME).strip().lower()
    for candidate_id, name in groups.items():
        if name.strip().lower() == candidate_name:
            return candidate_id
    raise FreshdeskError(f"Freshdesk group not found: {group_name or DEFAULT_GROUP_NAME}")


def latest_public_conversation(conversations: list[dict[str, Any]]) -> dict[str, Any] | None:
    public_rows = [row for row in conversations if not row.get("private")]
    if not public_rows:
        return None
    return max(public_rows, key=lambda row: str(row.get("created_at") or ""))


def is_internal_mirror_incoming(ticket: dict[str, Any], conversation: dict[str, Any]) -> bool:
    if conversation.get("incoming") is not True or conversation.get("private"):
        return False

    from_email = extract_email(conversation.get("from_email"))
    if not from_email:
        return False

    if from_email in INTERNAL_SUPPORT_EMAILS:
        return True

    requester_id = ticket.get("requester_id")
    conversation_user_id = conversation.get("user_id")
    from_domain = email_domain(from_email)
    return (
        from_domain in INTERNAL_SUPPORT_EMAIL_DOMAINS
        and requester_id is not None
        and conversation_user_id is not None
        and conversation_user_id != requester_id
    )


def effective_public_conversations(ticket: dict[str, Any], conversations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in conversations
        if not row.get("private") and not is_internal_mirror_incoming(ticket, row)
    ]


def ticket_needs_follow_up(domain: str, api_key: str, ticket: dict[str, Any]) -> bool:
    ticket_id = ticket.get("id")
    if ticket_id is None or ticket.get("status") != 2:
        return False

    conversations = fetch_conversations(domain, api_key, int(ticket_id))
    public_rows = effective_public_conversations(ticket, conversations)
    latest_public = latest_public_conversation(public_rows)
    if latest_public is None:
        return False

    has_agent_reply = any(row.get("incoming") is False for row in public_rows)
    return has_agent_reply and latest_public.get("incoming") is True


def summarize_by_agent(tickets: list[dict[str, Any]], agents: dict[int, str]) -> list[dict[str, Any]]:
    buckets: dict[tuple[int | None, str], list[int]] = defaultdict(list)
    for ticket in tickets:
        ticket_id = ticket.get("id")
        if ticket_id is None:
            continue
        responder_id = ticket.get("responder_id")
        responder_int = int(responder_id) if responder_id is not None else None
        agent_name = agents.get(responder_int) if responder_int is not None else "Unassigned"
        buckets[(responder_int, agent_name)].append(int(ticket_id))

    rows: list[dict[str, Any]] = []
    for (responder_id, agent_name), ticket_ids in buckets.items():
        rows.append(
            {
                "responder_id": responder_id,
                "agent_name": agent_name,
                "ticket_count": len(ticket_ids),
                "ticket_ids": sorted(ticket_ids),
            }
        )

    rows.sort(key=lambda row: (-row["ticket_count"], str(row["agent_name"]).lower()))
    return rows


def fetch_group_open_tickets_by_agent(
    domain: str,
    api_key: str,
    group_id: int,
    agents: dict[int, str],
) -> tuple[list[dict[str, Any]], int]:
    seen_ticket_ids: set[int] = set()
    tickets: list[dict[str, Any]] = []
    total = 0

    agent_queries: list[tuple[int | None, str]] = sorted(
        [(agent_id, name) for agent_id, name in agents.items()],
        key=lambda item: str(item[1]).lower(),
    )
    agent_queries.append((None, "Unassigned"))

    for agent_id, _agent_name in agent_queries:
        if agent_id is None:
            query = f"group_id:{group_id} AND status:2 AND agent_id:null"
        else:
            query = f"group_id:{group_id} AND status:2 AND agent_id:{agent_id}"

        batch, batch_total = paginate_search(domain, api_key, query)
        if batch_total is not None:
            total += int(batch_total)
        else:
            total += len(batch)

        for ticket in batch:
            ticket_id = ticket.get("id")
            if ticket_id is None:
                continue
            ticket_int = int(ticket_id)
            if ticket_int in seen_ticket_ids:
                continue
            seen_ticket_ids.add(ticket_int)
            tickets.append(ticket)

    return tickets, total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Return grouped counts and Ticket IDs for the formal needs-follow-up Ticket metric."
    )
    parser.add_argument("--domain", default=os.getenv("FRESHDESK_DOMAIN"), help="Freshdesk domain, e.g. example.freshdesk.com")
    parser.add_argument("--api-key", default=os.getenv("FRESHDESK_API_KEY"), help="Freshdesk API key. Prefer FRESHDESK_API_KEY.")
    parser.add_argument("--group-id", type=int, help="Optional Freshdesk group ID. Overrides --group-name.")
    parser.add_argument("--group-name", default=DEFAULT_GROUP_NAME, help=f'Freshdesk group name. Default: "{DEFAULT_GROUP_NAME}".')
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

    try:
        domain = normalize_domain(args.domain)
        groups = fetch_groups(domain, args.api_key)
        agents = fetch_agents(domain, args.api_key)
        resolved_group_id = resolve_group_id(groups, args.group_id, args.group_name)
        query = f"group_id:{resolved_group_id} AND status:2"
        tickets, total = fetch_group_open_tickets_by_agent(domain, args.api_key, resolved_group_id, agents)
        matched_tickets = [ticket for ticket in tickets if ticket_needs_follow_up(domain, args.api_key, ticket)]
        summary = summarize_by_agent(matched_tickets, agents)
        output = {
            "domain": domain,
            "group_id": resolved_group_id,
            "group_name": groups.get(resolved_group_id),
            "query": query,
            "ticket_count": len(matched_tickets),
            "freshdesk_total": total,
            "metric_name": "needs_follow_up_ticket",
            "metric_display_name": FOLLOW_UP_DISPLAY_NAME,
            "needs_follow_up_rule": "open ticket where the latest public reply is from the customer and the ticket already has at least one agent reply",
            "summary_by_agent": summary,
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
