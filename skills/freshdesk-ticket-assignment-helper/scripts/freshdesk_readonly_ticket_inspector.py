#!/usr/bin/env python3
"""Read-only Freshdesk Ticket metadata inspector."""

from __future__ import annotations

import argparse
import base64
from email.utils import parseaddr
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


READ_TIMEOUT_SECONDS = 30
INTERNAL_SUPPORT_EMAIL_DOMAINS = {"gl-inet.com", "glinet.biz"}
INTERNAL_SUPPORT_EMAILS = {"cs@gl-inet.com", "support@gl-inet.com", "support@glinet.biz"}
TRIAGE_GROUP_NAMES = ("Technical Service", "Unassigned", "MX Support")
TRIAGE_EXCLUDED_TAGS = {"escalation", "rma"}
UNRESOLVED_STATUSES = {2, 3}
RESOLVED_OR_CLOSED_STATUSES = {4, 5}


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
            "User-Agent": "freshdesk-ticket-assignment-helper/1.4",
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
            reason_text = str(exc.reason).lower().replace("_", " ")
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


def paginate_search(domain: str, api_key: str, query: str, limit: int | None = None) -> tuple[list[dict[str, Any]], int | None]:
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
        if limit is not None and len(rows) >= limit:
            return rows[:limit], total
        if len(batch) < 30:
            break
        if page == 10:
            break
        page += 1

    return rows[:limit] if limit is not None else rows, total


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
        return paginate_search(domain, api_key, query, limit)

    tickets = paginate_list(domain, api_key, "/api/v2/tickets", limit=limit)
    return tickets, None


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


def strip_html(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def ticket_initial_text(ticket: dict[str, Any]) -> str | None:
    value = ticket.get("description_text")
    if isinstance(value, str) and value.strip():
        return value.strip()
    body = ticket.get("description")
    return strip_html(body if isinstance(body, str) else None)


def merge_check_triggers(ticket: dict[str, Any]) -> list[str]:
    subject = str(ticket.get("subject") or "")
    text = ticket_initial_text(ticket) or ""
    triggers: list[str] = []
    salutation = re.match(r"^\s*(?:dear|hi|hello)\s+([A-Za-z][A-Za-z'-]{1,30})\s*[,!:]", text, re.IGNORECASE)
    if salutation and salutation.group(1).casefold() not in {
        "admin", "all", "customer", "friend", "madam", "sales", "sir", "support", "team", "there"
    }:
        triggers.append(f"named_salutation:{salutation.group(1)}")
    if re.match(r"^\s*(?:re\s*:\s*)+", subject, re.IGNORECASE):
        triggers.append("subject_re")
    if re.search(r"\b(?:follow[- ]?up|previous quotation|previously quoted|earlier quote|existing ticket)\b", text, re.IGNORECASE):
        triggers.append("continuation_phrase")
    return triggers


def normalize_merge_subject(subject: str | None) -> str:
    value = str(subject or "")
    value = re.sub(r"^\s*(?:(?:re|fw|fwd)\s*:\s*)+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*(?:#\s*)?\[?ticket[- #]?\d+\]?\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+#\d+\s*$", "", value)
    return re.sub(r"\s+", " ", value).strip(" -:#[]").casefold()


def merge_subjects_match(left: str | None, right: str | None) -> bool:
    normalized = normalize_merge_subject(left)
    return bool(normalized) and normalized == normalize_merge_subject(right)


def resolve_group_id(groups: dict[int, str], group_id: int | None, group_name: str | None) -> int | None:
    if group_id is not None:
        return group_id
    if not group_name:
        return None

    lowered = group_name.strip().lower()
    for candidate_id, candidate_name in groups.items():
        if candidate_name.strip().lower() == lowered:
            return candidate_id
    raise FreshdeskError(f"Freshdesk group not found: {group_name}")


def resolve_required_group_ids(groups: dict[int, str], group_names: tuple[str, ...]) -> dict[int, str]:
    resolved: dict[int, str] = {}
    lowered = {name.strip().lower(): group_id for group_id, name in groups.items()}
    for group_name in group_names:
        group_id = lowered.get(group_name.lower())
        if group_id is None:
            raise FreshdeskError(f"Freshdesk group not found: {group_name}")
        resolved[group_id] = groups[group_id]
    return resolved


def resolve_triage_group_filters(groups: dict[int, str]) -> list[tuple[int | None, str]]:
    actual_names = tuple(name for name in TRIAGE_GROUP_NAMES if name != "Unassigned")
    actual_groups = resolve_required_group_ids(groups, actual_names)
    ids_by_name = {name: group_id for group_id, name in actual_groups.items()}
    return [(None, name) if name == "Unassigned" else (ids_by_name[name], name) for name in TRIAGE_GROUP_NAMES]


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


def conversation_text(conversation: dict[str, Any]) -> str | None:
    value = conversation.get("body_text")
    if isinstance(value, str) and value.strip():
        return value.strip()
    body = conversation.get("body")
    return strip_html(body if isinstance(body, str) else None)


def shape_attachments(container: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": attachment.get("name"),
            "content_type": attachment.get("content_type"),
            "size": attachment.get("size"),
        }
        for attachment in (container.get("attachments") or [])
        if isinstance(attachment, dict)
    ]


def attachment_metadata_incomplete(container: dict[str, Any]) -> bool:
    attachments = container.get("attachments") or []
    return bool(attachments) and any(
        not isinstance(attachment, dict) or not attachment.get("name") or not attachment.get("content_type")
        for attachment in attachments
    )


def should_fetch_ticket_detail(ticket: dict[str, Any]) -> bool:
    text = ticket_initial_text(ticket) or ""
    return attachment_metadata_incomplete(ticket) or bool(re.search(r"\battach(?:ed|ment|ments)?\b|附件", text, re.IGNORECASE))


def shape_public_conversation(ticket: dict[str, Any], conversation: dict[str, Any]) -> dict[str, Any] | None:
    if conversation.get("private"):
        return None
    text = conversation_text(conversation)
    attachments = shape_attachments(conversation)
    if not text and not attachments:
        return None
    internal_mirror = is_internal_mirror_incoming(ticket, conversation)
    use_for_triage = conversation.get("incoming") is True and not internal_mirror
    return {
        "created_at": conversation.get("created_at"),
        "incoming": conversation.get("incoming"),
        "source": conversation.get("source"),
        "use_for_triage": use_for_triage,
        "triage_role": "customer" if use_for_triage else "public_non_customer",
        "body_text": text,
        "attachments": attachments,
    }


def has_excluded_triage_tag(ticket: dict[str, Any]) -> bool:
    return any(
        isinstance(tag, str) and tag.strip().casefold() in TRIAGE_EXCLUDED_TAGS
        for tag in (ticket.get("tags") or [])
    )


def unresolved_unassigned_ticket(ticket: dict[str, Any], group_ids: set[int | None]) -> bool:
    if ticket.get("status") not in UNRESOLVED_STATUSES:
        return False
    if ticket.get("spam") is True:
        return False
    if ticket.get("responder_id") is not None:
        return False
    if has_excluded_triage_tag(ticket):
        return False
    return ticket.get("group_id") in group_ids


def fetch_triage_unassigned_view(
    domain: str,
    api_key: str,
    groups: dict[int, str],
    agents: dict[int, str],
    limit: int,
) -> dict[str, Any]:
    triage_group_filters = resolve_triage_group_filters(groups)
    triage_group_ids = {group_id for group_id, _ in triage_group_filters}
    tickets_by_id: dict[int, dict[str, Any]] = {}
    excluded_tag_ticket_ids: set[int] = set()
    merge_history_check_count = 0
    searches: list[dict[str, Any]] = []

    for group_id, group_name in triage_group_filters:
        for status in sorted(UNRESOLVED_STATUSES):
            group_query = "group_id:null" if group_id is None else f"group_id:{group_id}"
            query = f"{group_query} AND agent_id:null AND status:{status}"
            rows, total = fetch_tickets(domain, api_key, limit, query)
            searches.append({
                "group_id": group_id,
                "group_name": group_name,
                "status": status,
                "query": query,
                "freshdesk_total": total,
                "returned_count": len(rows),
                "truncated": total is not None and total > len(rows),
            })
            for ticket in rows:
                ticket_id = ticket.get("id")
                if ticket_id is not None and ticket.get("spam") is not True and has_excluded_triage_tag(ticket):
                    excluded_tag_ticket_ids.add(int(ticket_id))
                if ticket_id is not None and unresolved_unassigned_ticket(ticket, triage_group_ids):
                    tickets_by_id[int(ticket_id)] = ticket

    tickets = sorted(tickets_by_id.values(), key=lambda row: str(row.get("created_at") or ""), reverse=True)[:limit]
    shaped_tickets = []
    for ticket in tickets:
        public_conversations = []
        ticket_id = ticket.get("id")
        if ticket_id is not None:
            if should_fetch_ticket_detail(ticket):
                detail = get_json(domain, api_key, f"/api/v2/tickets/{ticket_id}")
                if isinstance(detail, dict):
                    ticket = detail
            public_conversations = [
                shaped
                for conversation in fetch_conversations(domain, api_key, int(ticket_id))
                if (shaped := shape_public_conversation(ticket, conversation)) is not None
            ]
        shaped = shape_ticket(domain, ticket, agents, groups)
        shaped["initial_attachments"] = shape_attachments(ticket)
        shaped["public_conversations"] = public_conversations
        triage_parts = [ticket_initial_text(ticket)]
        triage_parts.extend(row["body_text"] for row in public_conversations if row.get("use_for_triage"))
        shaped["triage_text"] = "\n\n".join(part for part in triage_parts if part)
        merge_triggers = merge_check_triggers(ticket)
        merge_candidates = []
        requester_id = ticket.get("requester_id")
        if merge_triggers and requester_id is not None:
            merge_history_check_count += 1
            history = get_json(
                domain,
                api_key,
                "/api/v2/tickets",
                {
                    "requester_id": requester_id,
                    "order_by": "created_at",
                    "order_type": "desc",
                    "per_page": 10,
                },
            )
            if isinstance(history, list):
                current_created_at = str(ticket.get("created_at") or "")
                for previous in history:
                    if not isinstance(previous, dict) or previous.get("id") == ticket_id:
                        continue
                    previous_created_at = str(previous.get("created_at") or "")
                    if current_created_at and previous_created_at >= current_created_at:
                        continue
                    same_subject = merge_subjects_match(ticket.get("subject"), previous.get("subject"))
                    subject_re = bool(re.match(r"^\s*(?:re\s*:\s*)+", str(previous.get("subject") or ""), re.IGNORECASE))
                    if not same_subject and not subject_re:
                        continue
                    previous_shaped = shape_ticket(domain, previous, agents, groups)
                    merge_candidates.append(
                        {
                            key: previous_shaped.get(key)
                            for key in (
                                "ticket_id", "ticket_url", "subject", "status", "created_at", "responder_id",
                                "agent_name", "group_id", "group_name"
                            )
                        }
                        | {
                            "same_normalized_subject": same_subject,
                            "subject_starts_with_re": subject_re,
                        }
                    )
        shaped["merge_check"] = {
            "triggered": bool(merge_triggers),
            "triggers": merge_triggers,
            "history_checked": bool(merge_triggers and requester_id is not None),
            "candidates": merge_candidates[:10],
        }
        shaped_tickets.append(shaped)

    return {
        "domain": domain,
        "mode": "triage_unassigned_view",
        "query": None,
        "triage_filters": {
            "agent": "Unassigned",
            "groups": list(TRIAGE_GROUP_NAMES),
            "status": "All unresolved",
            "included_statuses": sorted(UNRESOLVED_STATUSES),
            "excluded_statuses": sorted(RESOLVED_OR_CLOSED_STATUSES),
            "exclude_spam": True,
            "excluded_tags": ["Escalation", "RMA"],
        },
        "excluded_tag_ticket_count": len(excluded_tag_ticket_ids),
        "merge_history_check_count": merge_history_check_count,
        "triage_instruction": (
            "Classify each ticket from subject, triage_text, attachment metadata, and merge_check candidates. "
            "Treat public_non_customer rows as context only, because they may include automatic replies."
        ),
        "group_id": None,
        "group_name": None,
        "ticket_count": len(shaped_tickets),
        "freshdesk_total": sum(row["freshdesk_total"] or 0 for row in searches),
        "search_results_truncated": any(row["truncated"] for row in searches),
        "agent_count": len(agents),
        "group_count": len(groups),
        "metric_name": "triage_unassigned_ticket_pool",
        "metric_display_name": "Freshdesk unassigned triage pool",
        "triage_searches": searches,
        "tickets": shaped_tickets,
        "safety": {
            "freshdesk_methods_used": ["GET"],
            "writes_allowed": False,
        },
    }


def shape_ticket(domain: str, ticket: dict[str, Any], agents: dict[int, str], groups: dict[int, str]) -> dict[str, Any]:
    responder_id = ticket.get("responder_id")
    group_id = ticket.get("group_id")
    ticket_id = ticket.get("id")
    responder_int = int(responder_id) if responder_id is not None else None
    group_int = int(group_id) if group_id is not None else None
    return {
        "ticket_id": ticket_id,
        "ticket_url": f"https://{domain}/a/tickets/{ticket_id}" if ticket_id is not None else None,
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
    parser.add_argument("--limit", type=int, default=20, help="Maximum tickets to return. Default: 20")
    parser.add_argument("--query", help="Optional Freshdesk search query, e.g. 'group_id:123 AND agent_id:null'")
    parser.add_argument("--group-id", type=int, help="Optional Freshdesk group ID used to build a query when --query is omitted.")
    parser.add_argument("--group-name", help="Optional Freshdesk group name used to build a query when --query is omitted.")
    parser.add_argument(
        "--triage-unassigned-view",
        action="store_true",
        help="Fetch the Freshdesk unassigned triage view: unresolved, non-spam tickets in Technical Service, Unassigned, and MX Support.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.getenv("FRESHDESK_API_KEY")
    if not args.domain:
        print("Missing Freshdesk domain. Set FRESHDESK_DOMAIN or pass --domain.", file=sys.stderr)
        return 2
    if not api_key:
        print("Missing Freshdesk API key. Set FRESHDESK_API_KEY.", file=sys.stderr)
        return 2
    if args.limit < 1:
        print("--limit must be at least 1.", file=sys.stderr)
        return 2

    try:
        domain = normalize_domain(args.domain)
        groups = fetch_groups(domain, api_key)
        agents = fetch_agents(domain, api_key)
        if args.triage_unassigned_view:
            output = fetch_triage_unassigned_view(domain, api_key, groups, agents, args.limit)
            indent = 2 if args.pretty else None
            print(json.dumps(output, ensure_ascii=False, indent=indent))
            return 0

        resolved_group_id = resolve_group_id(groups, args.group_id, args.group_name)
        query = args.query
        if query is None and resolved_group_id is not None:
            query = f"group_id:{resolved_group_id}"
        tickets, total = fetch_tickets(domain, api_key, args.limit, query)

        output = {
            "domain": domain,
            "mode": "search" if query else "recent",
            "query": query,
            "group_id": resolved_group_id,
            "group_name": groups.get(resolved_group_id) if resolved_group_id is not None else None,
            "ticket_count": len(tickets),
            "freshdesk_total": total,
            "search_results_truncated": total is not None and total > len(tickets),
            "agent_count": len(agents),
            "group_count": len(groups),
            "tickets": [shape_ticket(domain, ticket, agents, groups) for ticket in tickets],
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
