#!/usr/bin/env python3
"""Read-only grouped Freshdesk actionable-ticket counter."""

from __future__ import annotations

import argparse
import base64
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
import http.client
import json
import os
from pathlib import Path
import random
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


FOLLOW_UP_DISPLAY_NAME = "\u5f85\u5904\u7406Ticket"
SCRIPT_VERSION = "1.7.1"
OPEN_STATUS = 2
OUTBOUND_EMAIL_SOURCE = 10
READ_TIMEOUT_SECONDS = 30
SEARCH_PAGE_HARD_LIMIT = 300
DEFAULT_CACHE_PATH = Path(__file__).resolve().parent.parent / ".cache" / "actionable_ticket_cache.json"
CACHE_VERSION = 2
DEFAULT_CACHE_RETENTION_DAYS = 30
DEFAULT_REQUEST_DELAY_SECONDS = 0.1
MAX_REQUEST_ATTEMPTS = 5
CACHE_CHECKPOINT_MISSES = 20
CUSTOMER_RESPONSE_RECHECK_WINDOW_SECONDS = 5 * 60
MAX_TICKET_CONVERSATIONS = 10_000
INTERNAL_SUPPORT_EMAIL_DOMAINS = {"gl-inet.com", "glinet.biz"}
INTERNAL_SUPPORT_EMAILS = {"support@gl-inet.com", "support@glinet.biz"}
INTERNAL_SUPPORT_EMAIL_PREFIXES = ("cs",)
ENGLISH_MONTH_ABBREVIATIONS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
GROUP_ALIASES = {
    "\u6280\u672f\u5ba2\u670d": ["Technical Service"],
    "\u6280\u672f\u5ba2\u670d\u7ec4": ["Technical Service"],
    "\u6280\u672f\u5ba2\u670d\u7684\u6570\u636e": ["Technical Service"],
    "cs\u5ba2\u670d": ["Customer Service", "Amazon"],
    "cs\u5ba2\u670d\u7ec4": ["Customer Service", "Amazon"],
    "cs\u5ba2\u670d\u7684\u6570\u636e": ["Customer Service", "Amazon"],
    "\u6df1\u5733\u56e2\u961f": ["Technical Service", "Technical Support", "Customer Service", "Amazon"],
    "\u58a8\u897f\u54e5\u56e2\u961f": ["MX Support"],
    "customer service + amazon": ["Customer Service", "Amazon"],
    "customer service+amazon": ["Customer Service", "Amazon"],
}


class FreshdeskError(RuntimeError):
    pass


def build_run_metadata(
    started_monotonic: float,
    finished_monotonic: float | None = None,
    finished_at: datetime | None = None,
) -> dict[str, Any]:
    finished_monotonic = time.perf_counter() if finished_monotonic is None else finished_monotonic
    finished_at = datetime.now().astimezone() if finished_at is None else finished_at
    offset = finished_at.utcoffset() or timedelta(0)
    offset_minutes = int(offset.total_seconds() / 60)
    sign = "+" if offset_minutes >= 0 else "-"
    offset_hours, offset_remainder = divmod(abs(offset_minutes), 60)
    hour = finished_at.hour % 12 or 12
    meridiem = "AM" if finished_at.hour < 12 else "PM"
    display = (
        f"{ENGLISH_MONTH_ABBREVIATIONS[finished_at.month - 1]} {finished_at.day}, {finished_at.year}, "
        f"{hour}:{finished_at.minute:02d} {meridiem} Local Time "
        f"(UTC{sign}{offset_hours:02d}:{offset_remainder:02d})"
    )
    return {
        "elapsed_seconds": round(max(0.0, finished_monotonic - started_monotonic), 2),
        "finished_at": finished_at.isoformat(timespec="seconds"),
        "finished_at_display": display,
    }


def normalize_domain(domain: str) -> str:
    value = domain.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    if not value:
        raise FreshdeskError("Freshdesk domain is empty.")
    return value


def auth_header(api_key: str) -> str:
    token = base64.b64encode(f"{api_key}:X".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def retry_delay_seconds(attempt: int) -> float:
    base_delay = min(30, 2**attempt)
    return base_delay * random.uniform(0.5, 1.5)


def is_retryable_reason(reason_text: str) -> bool:
    return any(
        token in reason_text
        for token in (
            "timed out",
            "timeout",
            "unexpected eof",
            "handshake",
            "certificate verify failed",
            "eof occurred in violation",
            "remote end closed",
            "closed connection without response",
            "connection reset",
            "incomplete read",
        )
    )


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
            "User-Agent": "freshdesk-needs-follow-up-ticket-numbers/2.0",
        },
        method="GET",
    )

    request_delay_seconds = env_float("FRESHDESK_REQUEST_DELAY_SECONDS", DEFAULT_REQUEST_DELAY_SECONDS)

    for attempt in range(MAX_REQUEST_ATTEMPTS):
        try:
            if request_delay_seconds > 0:
                time.sleep(request_delay_seconds)
            with urllib.request.urlopen(request, timeout=READ_TIMEOUT_SECONDS) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload) if payload else None
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < MAX_REQUEST_ATTEMPTS - 1:
                retry_after = exc.headers.get("Retry-After")
                delay = int(retry_after) if retry_after and retry_after.isdigit() else retry_delay_seconds(attempt)
                time.sleep(delay)
                continue
            if 500 <= exc.code <= 599 and attempt < MAX_REQUEST_ATTEMPTS - 1:
                time.sleep(retry_delay_seconds(attempt))
                continue
            detail = exc.read().decode("utf-8", errors="replace")
            raise FreshdeskError(f"GET {path} failed with HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            reason_text = str(exc.reason).lower()
            if attempt < MAX_REQUEST_ATTEMPTS - 1 and is_retryable_reason(reason_text):
                time.sleep(retry_delay_seconds(attempt))
                continue
            raise FreshdeskError(f"GET {path} failed: {exc.reason}") from exc
        except (
            TimeoutError,
            socket.timeout,
            ssl.SSLError,
            http.client.IncompleteRead,
            http.client.RemoteDisconnected,
            ConnectionResetError,
        ) as exc:
            if attempt < MAX_REQUEST_ATTEMPTS - 1:
                time.sleep(retry_delay_seconds(attempt))
                continue
            raise FreshdeskError(f"GET {path} failed: {exc}") from exc

    raise FreshdeskError(f"GET {path} failed after retries.")


def paginate_list(domain: str, api_key: str, path: str, limit: int, per_page: int = 100) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while len(rows) < limit:
        batch = get_json(domain, api_key, path, {"page": page, "per_page": min(per_page, limit - len(rows))})
        if not isinstance(batch, list):
            raise FreshdeskError(f"Freshdesk list response for {path} was not a JSON list.")
        if not batch:
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
        if len(batch) < 30 or page >= 10:
            break
        page += 1

    return rows, total


def fetch_groups(domain: str, api_key: str) -> list[dict[str, Any]]:
    groups = paginate_list(domain, api_key, "/api/v2/groups", limit=1000)
    return [group for group in groups if isinstance(group, dict) and group.get("id") is not None]


def fetch_group_agents(domain: str, api_key: str, group_id: int) -> list[dict[str, Any]]:
    payload = get_json(domain, api_key, f"/api/v2/admin/groups/{group_id}/agents")
    if not isinstance(payload, list):
        raise FreshdeskError(f"Freshdesk group-agent response for group {group_id} was not a JSON list.")
    return [row for row in payload if isinstance(row, dict)]


def fetch_ticket_with_stats(domain: str, api_key: str, ticket_id: int) -> dict[str, Any]:
    payload = get_json(domain, api_key, f"/api/v2/tickets/{ticket_id}", {"include": "stats"})
    if not isinstance(payload, dict):
        raise FreshdeskError(f"Freshdesk ticket response for ticket {ticket_id} was not a JSON object.")
    return payload


def fetch_ticket_conversations(domain: str, api_key: str, ticket_id: int) -> list[dict[str, Any]]:
    rows = paginate_list(
        domain,
        api_key,
        f"/api/v2/tickets/{ticket_id}/conversations",
        limit=MAX_TICKET_CONVERSATIONS,
    )
    if len(rows) >= MAX_TICKET_CONVERSATIONS:
        raise FreshdeskError(f"Freshdesk conversations for ticket {ticket_id} reached the safety limit.")
    return rows


def fetch_agent_by_id(domain: str, api_key: str, agent_id: int) -> dict[str, Any]:
    payload = get_json(domain, api_key, f"/api/v2/agents/{agent_id}")
    if not isinstance(payload, dict):
        raise FreshdeskError(f"Freshdesk agent response for agent {agent_id} was not a JSON object.")
    return payload


def group_label(group: dict[str, Any]) -> str:
    return str(group.get("name") or f"Group {group.get('id')}")


def group_lookup(groups: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[int, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for group in groups:
        group_id = int(group["id"])
        by_id[group_id] = group
        by_name[group_label(group).strip().lower()] = group
    return by_id, by_name


def expand_group_alias(token: str) -> list[str]:
    alias = GROUP_ALIASES.get(token.strip().lower())
    return list(alias) if alias else [token]


def prompt_for_groups(groups: list[dict[str, Any]]) -> list[str]:
    print("Available Freshdesk groups:", file=sys.stderr)
    for group in sorted(groups, key=lambda row: group_label(row).lower()):
        print(f"- {group['id']}: {group_label(group)}", file=sys.stderr)
    print("Alias groups:", file=sys.stderr)
    print("- 技术客服 / 技术客服组 / 技术客服的数据 => Technical Service", file=sys.stderr)
    print("- CS客服组 / CS客服 / CS客服的数据 => Customer Service + Amazon", file=sys.stderr)
    print("- 深圳团队 => Technical Service + Technical Support + Customer Service + Amazon", file=sys.stderr)
    print("- 墨西哥团队 => MX Support", file=sys.stderr)

    while True:
        raw = input("Enter one or more group IDs, exact names, or alias names, comma-separated: ").strip()
        tokens = [item.strip() for item in raw.split(",") if item.strip()]
        if tokens:
            return tokens
        print("Please choose at least one group.", file=sys.stderr)


def resolve_selected_groups(
    groups: list[dict[str, Any]],
    group_ids: list[int],
    group_names: list[str],
) -> list[dict[str, Any]]:
    by_id, by_name = group_lookup(groups)
    resolved: list[dict[str, Any]] = []
    seen_group_ids: set[int] = set()

    requested_tokens = [str(group_id) for group_id in group_ids] + list(group_names)
    if not requested_tokens:
        if sys.stdin.isatty():
            requested_tokens = prompt_for_groups(groups)
        else:
            raise FreshdeskError(
                "No group was selected. In non-interactive runs, pass --group-id or --group-name explicitly."
            )

    for original_token in requested_tokens:
        for token in expand_group_alias(original_token):
            token_stripped = token.strip()
            if not token_stripped:
                continue
            group: dict[str, Any] | None = None
            if token_stripped.isdigit():
                group = by_id.get(int(token_stripped))
            if group is None:
                group = by_name.get(token_stripped.lower())
            if group is None:
                raise FreshdeskError(f"Freshdesk group not found: {token_stripped}")
            group_id = int(group["id"])
            if group_id in seen_group_ids:
                continue
            seen_group_ids.add(group_id)
            resolved.append(group)

    if not resolved:
        raise FreshdeskError("No valid Freshdesk groups were selected.")
    return resolved


def agent_name(agent: dict[str, Any]) -> str:
    contact = agent.get("contact") if isinstance(agent.get("contact"), dict) else {}
    return str(contact.get("name") or agent.get("name") or f"Agent {agent.get('id')}")


def build_agent_maps(group_agents: list[dict[str, Any]]) -> tuple[dict[int, str], list[dict[str, Any]], list[dict[str, Any]]]:
    names: dict[int, str] = {}
    active_agents: list[dict[str, Any]] = []
    deactivated_agents: list[dict[str, Any]] = []
    for agent in group_agents:
        agent_id = agent.get("id")
        if agent_id is None:
            continue
        agent_int = int(agent_id)
        names[agent_int] = agent_name(agent)
        if agent.get("deactivated"):
            deactivated_agents.append(agent)
        else:
            active_agents.append(agent)
    return names, active_agents, deactivated_agents


def enrich_agent_names_for_tickets(
    domain: str,
    api_key: str,
    tickets: list[dict[str, Any]],
    agent_names: dict[int, str],
) -> dict[int, str]:
    resolved_names = dict(agent_names)
    missing_ids: set[int] = set()
    for ticket in tickets:
        responder_id = ticket.get("responder_id")
        if responder_id is None:
            continue
        responder_int = int(responder_id)
        if responder_int not in resolved_names:
            missing_ids.add(responder_int)

    for responder_int in sorted(missing_ids):
        try:
            agent = fetch_agent_by_id(domain, api_key, responder_int)
            resolved_names[responder_int] = agent_name(agent)
        except FreshdeskError:
            resolved_names[responder_int] = f"Agent {responder_int}"

    return resolved_names


def fetch_group_open_tickets(
    domain: str,
    api_key: str,
    group: dict[str, Any],
    group_agents: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    group_id = int(group["id"])
    direct_query = f"group_id:{group_id} AND status:{OPEN_STATUS}"
    direct_rows, direct_total = paginate_search(domain, api_key, direct_query)

    metadata = {
        "group_query": direct_query,
        "direct_total": direct_total,
        "search_strategy": "direct_group_query",
        "search_queries": [direct_query],
    }

    if direct_total is None or direct_total <= SEARCH_PAGE_HARD_LIMIT:
        return direct_rows, metadata

    names, active_agents, deactivated_agents = build_agent_maps(group_agents)
    del names
    batched_rows: list[dict[str, Any]] = []
    seen_ticket_ids: set[int] = set()
    search_queries = [direct_query]

    batched_agents = sorted(group_agents, key=lambda row: agent_name(row).lower())
    for agent in batched_agents:
        agent_id = int(agent["id"])
        query = f"group_id:{group_id} AND status:{OPEN_STATUS} AND agent_id:{agent_id}"
        search_queries.append(query)
        batch, _batch_total = paginate_search(domain, api_key, query)
        for ticket in batch:
            ticket_id = ticket.get("id")
            if ticket_id is None:
                continue
            ticket_int = int(ticket_id)
            if ticket_int in seen_ticket_ids:
                continue
            seen_ticket_ids.add(ticket_int)
            batched_rows.append(ticket)

    unassigned_query = f"group_id:{group_id} AND status:{OPEN_STATUS} AND agent_id:null"
    search_queries.append(unassigned_query)
    unassigned_rows, _unassigned_total = paginate_search(domain, api_key, unassigned_query)
    for ticket in unassigned_rows:
        ticket_id = ticket.get("id")
        if ticket_id is None:
            continue
        ticket_int = int(ticket_id)
        if ticket_int in seen_ticket_ids:
            continue
        seen_ticket_ids.add(ticket_int)
        batched_rows.append(ticket)

    metadata.update(
        {
            "search_strategy": "group_agents_batched",
            "search_queries": search_queries,
            "group_agents_total": len(group_agents),
            "group_agents_active": len(active_agents),
            "group_agents_deactivated": len(deactivated_agents),
        }
    )
    return batched_rows, metadata


def load_cache(cache_path: Path, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"version": CACHE_VERSION, "tickets": {}}
    if not cache_path.exists():
        return {"version": CACHE_VERSION, "tickets": {}}
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": CACHE_VERSION, "tickets": {}}
    if not isinstance(data, dict) or data.get("version") != CACHE_VERSION or not isinstance(data.get("tickets"), dict):
        return {"version": CACHE_VERSION, "tickets": {}}
    return data


def cache_entry_timestamp(entry: dict[str, Any]) -> datetime | None:
    for key in ("last_seen_at", "cached_at"):
        value = entry.get(key)
        if isinstance(value, str):
            parsed = parse_iso8601(value)
            if parsed is not None:
                return parsed.astimezone(timezone.utc)
    return None


def prune_cache(cache: dict[str, Any], now: datetime, retention_days: int) -> int:
    retention_days = max(1, int(retention_days or DEFAULT_CACHE_RETENTION_DAYS))
    ticket_cache = cache.get("tickets")
    if not isinstance(ticket_cache, dict):
        cache["tickets"] = {}
        return 0
    cutoff = now.astimezone(timezone.utc) - timedelta(days=retention_days)
    removed = 0
    for key, entry in list(ticket_cache.items()):
        if not isinstance(entry, dict):
            del ticket_cache[key]
            removed += 1
            continue
        seen_at = cache_entry_timestamp(entry)
        if seen_at is None or seen_at < cutoff:
            del ticket_cache[key]
            removed += 1
    return removed


def save_cache(
    cache_path: Path,
    cache: dict[str, Any],
    enabled: bool,
    now: datetime,
    retention_days: int,
) -> int:
    if not enabled:
        return 0
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    pruned_entries = prune_cache(cache, now, retention_days)
    cache["version"] = CACHE_VERSION
    cache["saved_at"] = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    cache["retention_days"] = max(1, int(retention_days or DEFAULT_CACHE_RETENTION_DAYS))
    cache["pruned_entries"] = pruned_entries
    temp_path = cache_path.with_suffix(f"{cache_path.suffix}.tmp")
    temp_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(cache_path)
    return pruned_entries


def cache_ticket_key(ticket_id: int) -> str:
    return str(ticket_id)


def cache_entry_matches(entry: dict[str, Any], ticket: dict[str, Any]) -> bool:
    return (
        entry.get("updated_at") == ticket.get("updated_at")
        and entry.get("status") == ticket.get("status")
        and entry.get("group_id") == ticket.get("group_id")
        and entry.get("responder_id") == ticket.get("responder_id")
        and entry.get("due_by") == ticket.get("due_by")
        and entry.get("fr_due_by") == ticket.get("fr_due_by")
    )


def internal_sender_rule_key() -> str:
    rules = [*INTERNAL_SUPPORT_EMAILS]
    rules.extend(
        f"{prefix}*@{domain}"
        for prefix in INTERNAL_SUPPORT_EMAIL_PREFIXES
        for domain in INTERNAL_SUPPORT_EMAIL_DOMAINS
    )
    return "|".join(sorted(rules))


def customer_response_sender_cache_matches(entry: dict[str, Any], stats: dict[str, Any]) -> bool:
    return (
        isinstance(entry.get("customer_response_sender_internal"), bool)
        and entry.get("customer_response_sender_requester_responded_at") == stats.get("requester_responded_at")
        and entry.get("customer_response_sender_agent_responded_at") == stats.get("agent_responded_at")
        and entry.get("customer_response_sender_rule_key") == internal_sender_rule_key()
    )


def cache_customer_response_sender(entry: dict[str, Any], stats: dict[str, Any], internal: bool) -> None:
    entry["customer_response_sender_internal"] = internal
    entry["customer_response_sender_requester_responded_at"] = stats.get("requester_responded_at")
    entry["customer_response_sender_agent_responded_at"] = stats.get("agent_responded_at")
    entry["customer_response_sender_rule_key"] = internal_sender_rule_key()


def ticket_cache_entry(
    ticket: dict[str, Any],
    stats: dict[str, Any],
    outbound_has_public_incoming_reply: bool | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "ticket_id": ticket.get("id"),
        "updated_at": ticket.get("updated_at"),
        "status": ticket.get("status"),
        "group_id": ticket.get("group_id"),
        "responder_id": ticket.get("responder_id"),
        "due_by": ticket.get("due_by"),
        "fr_due_by": ticket.get("fr_due_by"),
        "stats": stats,
        "outbound_has_public_incoming_reply": outbound_has_public_incoming_reply,
        "cached_at": timestamp,
        "last_seen_at": timestamp,
    }


def fetch_ticket_stats_for_pool(
    domain: str,
    api_key: str,
    tickets: list[dict[str, Any]],
    cache: dict[str, Any],
    cache_enabled: bool,
    cache_path: Path,
    now: datetime,
    cache_retention_days: int = DEFAULT_CACHE_RETENTION_DAYS,
) -> tuple[
    dict[int, dict[str, Any]],
    dict[int, bool | None],
    dict[int, bool | None],
    dict[str, int],
]:
    ticket_cache = cache.setdefault("tickets", {})
    stats_by_ticket: dict[int, dict[str, Any]] = {}
    outbound_reply_by_ticket: dict[int, bool | None] = {}
    customer_response_sender_by_ticket: dict[int, bool | None] = {}
    cache_hits = 0
    cache_misses = 0
    conversation_rechecks = 0
    pruned_entries = 0
    customer_response_recheck_candidates = 0
    customer_response_recheck_completed = 0
    customer_response_recheck_cache_hits = 0
    customer_response_internal_sender_exclusions = 0
    customer_response_recheck_unverified = 0

    for ticket in tickets:
        ticket_id = ticket.get("id")
        if ticket_id is None:
            continue
        ticket_int = int(ticket_id)
        cache_key = cache_ticket_key(ticket_int)
        entry = ticket_cache.get(cache_key) if cache_enabled else None
        cache_hit = isinstance(entry, dict) and cache_entry_matches(entry, ticket)
        if cache_hit:
            entry["last_seen_at"] = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            stats_by_ticket[ticket_int] = entry.get("stats") if isinstance(entry.get("stats"), dict) else {}
            outbound_reply_by_ticket[ticket_int] = (
                entry.get("outbound_has_public_incoming_reply")
                if isinstance(entry.get("outbound_has_public_incoming_reply"), bool) or entry.get("outbound_has_public_incoming_reply") is None
                else None
            )
            cache_hits += 1
        else:
            detailed_ticket = fetch_ticket_with_stats(domain, api_key, ticket_int)
            stats = detailed_ticket.get("stats") if isinstance(detailed_ticket.get("stats"), dict) else {}
            stats_by_ticket[ticket_int] = stats
            outbound_has_public_incoming_reply: bool | None = None
            if should_recheck_outbound_fr_overdue(ticket, stats, now):
                conversations = fetch_ticket_conversations(domain, api_key, ticket_int)
                outbound_has_public_incoming_reply = has_public_incoming_customer_reply(conversations)
                conversation_rechecks += 1
            outbound_reply_by_ticket[ticket_int] = outbound_has_public_incoming_reply
            if cache_enabled:
                entry = ticket_cache[cache_key] = ticket_cache_entry(ticket, stats, outbound_has_public_incoming_reply, now)
            cache_misses += 1

        stats = stats_by_ticket[ticket_int]
        customer_response_sender_internal: bool | None = None
        if should_recheck_customer_response_sender(stats):
            customer_response_recheck_candidates += 1
            if cache_enabled and isinstance(entry, dict) and customer_response_sender_cache_matches(entry, stats):
                customer_response_sender_internal = entry["customer_response_sender_internal"]
                customer_response_recheck_cache_hits += 1
            else:
                conversations = fetch_ticket_conversations(domain, api_key, ticket_int)
                customer_response_sender_internal = latest_public_sender_internal(conversations)
                customer_response_recheck_completed += 1
                if customer_response_sender_internal is None:
                    customer_response_recheck_unverified += 1
                elif cache_enabled and isinstance(entry, dict):
                    cache_customer_response_sender(entry, stats, customer_response_sender_internal)
            if customer_response_sender_internal is True:
                customer_response_internal_sender_exclusions += 1
        customer_response_sender_by_ticket[ticket_int] = customer_response_sender_internal

        if not cache_hit and cache_misses % CACHE_CHECKPOINT_MISSES == 0:
            pruned_entries += save_cache(cache_path, cache, cache_enabled, now, cache_retention_days)

    if cache_enabled:
        for ticket in tickets:
            ticket_id = ticket.get("id")
            if ticket_id is None:
                continue
            ticket_int = int(ticket_id)
            if ticket_int in stats_by_ticket and should_recheck_outbound_fr_overdue(ticket, stats_by_ticket[ticket_int], now):
                cache_key = cache_ticket_key(ticket_int)
                entry = ticket_cache.get(cache_key)
                if not isinstance(entry, dict):
                    continue
                cached_value = entry.get("outbound_has_public_incoming_reply")
                if isinstance(cached_value, bool) or cached_value is None:
                    if ticket_int not in outbound_reply_by_ticket or outbound_reply_by_ticket[ticket_int] is None:
                        if cached_value is None:
                            conversations = fetch_ticket_conversations(domain, api_key, ticket_int)
                            cached_value = has_public_incoming_customer_reply(conversations)
                            entry["outbound_has_public_incoming_reply"] = cached_value
                            conversation_rechecks += 1
                        outbound_reply_by_ticket[ticket_int] = cached_value

    return stats_by_ticket, outbound_reply_by_ticket, customer_response_sender_by_ticket, {
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "conversation_rechecks": conversation_rechecks,
        "pruned_entries": pruned_entries,
        "customer_response_recheck_candidates": customer_response_recheck_candidates,
        "customer_response_recheck_completed": customer_response_recheck_completed,
        "customer_response_recheck_cache_hits": customer_response_recheck_cache_hits,
        "customer_response_internal_sender_exclusions": customer_response_internal_sender_exclusions,
        "customer_response_recheck_unverified": customer_response_recheck_unverified,
        "customer_response_recheck_failures": 0,
    }


def is_new_ticket(stats: dict[str, Any]) -> bool:
    return not stats.get("first_responded_at")


def is_customer_responded_ticket(stats: dict[str, Any]) -> bool:
    first_responded_at = parse_iso8601(stats.get("first_responded_at"))
    requester_responded_at = parse_iso8601(stats.get("requester_responded_at"))
    agent_responded_at = parse_iso8601(stats.get("agent_responded_at"))

    if first_responded_at is None or requester_responded_at is None:
        return False
    if agent_responded_at is None:
        return False
    return requester_responded_at > agent_responded_at


def should_recheck_customer_response_sender(stats: dict[str, Any]) -> bool:
    requester_responded_at = parse_iso8601(stats.get("requester_responded_at"))
    agent_responded_at = parse_iso8601(stats.get("agent_responded_at"))
    if not is_customer_responded_ticket(stats) or requester_responded_at is None or agent_responded_at is None:
        return False
    return 0 < (requester_responded_at - agent_responded_at).total_seconds() <= CUSTOMER_RESPONSE_RECHECK_WINDOW_SECONDS


def is_internal_support_sender(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    email = parseaddr(value)[1].strip().casefold()
    if email in INTERNAL_SUPPORT_EMAILS:
        return True
    local, separator, domain = email.rpartition("@")
    return bool(
        separator
        and domain in INTERNAL_SUPPORT_EMAIL_DOMAINS
        and any(local.startswith(prefix) for prefix in INTERNAL_SUPPORT_EMAIL_PREFIXES)
    )


def latest_public_sender_internal(conversations: list[dict[str, Any]]) -> bool | None:
    public = [conversation for conversation in conversations if not conversation.get("private")]
    if not public:
        return None

    def sort_key(conversation: dict[str, Any]) -> tuple[datetime, int]:
        created_at = parse_iso8601(conversation.get("created_at"))
        if created_at is None:
            raise FreshdeskError("Freshdesk public conversation is missing created_at.")
        return created_at, int(conversation.get("id") or 0)

    latest = max(public, key=sort_key)
    from_email = latest.get("from_email")
    if not isinstance(from_email, str) or not parseaddr(from_email)[1]:
        return None
    return is_internal_support_sender(from_email)


def should_recheck_outbound_fr_overdue(ticket: dict[str, Any], stats: dict[str, Any], now: datetime) -> bool:
    if ticket.get("source") != OUTBOUND_EMAIL_SOURCE:
        return False
    if not is_new_ticket(stats):
        return False
    fr_due_by = parse_iso8601(ticket.get("fr_due_by"))
    return fr_due_by is not None and fr_due_by < now


def has_public_incoming_customer_reply(conversations: list[dict[str, Any]]) -> bool:
    for conversation in conversations:
        if conversation.get("private"):
            continue
        if conversation.get("incoming") is True:
            return True
    return False


def classify_ticket(
    ticket: dict[str, Any],
    stats: dict[str, Any],
    now: datetime,
    outbound_has_public_incoming_reply: bool | None = None,
    customer_response_sender_internal: bool | None = None,
) -> dict[str, bool]:
    fr_due_by = parse_iso8601(ticket.get("fr_due_by"))
    due_by = parse_iso8601(ticket.get("due_by"))
    new_ticket = is_new_ticket(stats)
    customer_responded_ticket = is_customer_responded_ticket(stats) and customer_response_sender_internal is not True
    if (
        ticket.get("source") == OUTBOUND_EMAIL_SOURCE
        and new_ticket
        and fr_due_by is not None
        and fr_due_by < now
        and outbound_has_public_incoming_reply is False
    ):
        new_ticket = False
    fr_overdue = new_ticket and fr_due_by is not None and fr_due_by < now
    resolution_overdue = due_by is not None and due_by < now

    return {
        "new_ticket": new_ticket,
        "customer_responded_ticket": customer_responded_ticket,
        "fr_overdue": fr_overdue,
        "resolution_overdue": resolution_overdue,
    }


def summarize_by_agent(
    tickets: list[dict[str, Any]],
    stats_by_ticket: dict[int, dict[str, Any]],
    outbound_reply_by_ticket: dict[int, bool | None],
    agent_names: dict[int, str],
    now: datetime,
    customer_response_sender_by_ticket: dict[int, bool | None] | None = None,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[int | None, str], dict[str, Any]] = {}

    def bucket_for(responder_int: int | None, name: str) -> dict[str, Any]:
        key = (responder_int, name)
        if key not in buckets:
            buckets[key] = {
                "responder_id": responder_int,
                "agent_name": name,
                "new_ticket_ids": [],
                "customer_responded_ticket_ids": [],
                "fr_overdue_ticket_ids": [],
                "resolution_overdue_ticket_ids": [],
                "all_ticket_ids": [],
            }
        return buckets[key]

    for ticket in tickets:
        ticket_id = ticket.get("id")
        if ticket_id is None:
            continue
        ticket_int = int(ticket_id)
        responder_id = ticket.get("responder_id")
        responder_int = int(responder_id) if responder_id is not None else None
        name = agent_names.get(responder_int) if responder_int is not None else "Unassigned"
        if not name:
            name = f"Agent {responder_int}" if responder_int is not None else "Unassigned"
        bucket = bucket_for(responder_int, name)
        bucket["all_ticket_ids"].append(ticket_int)

        stats = stats_by_ticket.get(ticket_int, {})
        classification = classify_ticket(
            ticket,
            stats,
            now,
            outbound_reply_by_ticket.get(ticket_int),
            (customer_response_sender_by_ticket or {}).get(ticket_int),
        )
        if classification["new_ticket"]:
            bucket["new_ticket_ids"].append(ticket_int)
        if classification["customer_responded_ticket"]:
            bucket["customer_responded_ticket_ids"].append(ticket_int)
        if classification["fr_overdue"]:
            bucket["fr_overdue_ticket_ids"].append(ticket_int)
        if classification["resolution_overdue"]:
            bucket["resolution_overdue_ticket_ids"].append(ticket_int)

    rows: list[dict[str, Any]] = []
    for row in buckets.values():
        row["all_ticket_ids"] = sorted(row["all_ticket_ids"])
        row["new_ticket_ids"] = sorted(row["new_ticket_ids"])
        row["customer_responded_ticket_ids"] = sorted(row["customer_responded_ticket_ids"])
        row["fr_overdue_ticket_ids"] = sorted(row["fr_overdue_ticket_ids"])
        row["resolution_overdue_ticket_ids"] = sorted(row["resolution_overdue_ticket_ids"])
        row["all_ticket_count"] = len(row["all_ticket_ids"])
        row["new_ticket_count"] = len(row["new_ticket_ids"])
        row["customer_responded_ticket_count"] = len(row["customer_responded_ticket_ids"])
        row["fr_overdue_count"] = len(row["fr_overdue_ticket_ids"])
        row["resolution_overdue_count"] = len(row["resolution_overdue_ticket_ids"])
        row["actionable_ticket_count"] = row["new_ticket_count"] + row["customer_responded_ticket_count"]
        rows.append(row)

    rows.sort(key=lambda row: (-row["actionable_ticket_count"], -row["all_ticket_count"], str(row["agent_name"]).lower()))
    return rows


def summarize_group_totals(summary_rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "all_ticket_count": sum(row["all_ticket_count"] for row in summary_rows),
        "new_ticket_count": sum(row["new_ticket_count"] for row in summary_rows),
        "customer_responded_ticket_count": sum(row["customer_responded_ticket_count"] for row in summary_rows),
        "fr_overdue_count": sum(row["fr_overdue_count"] for row in summary_rows),
        "resolution_overdue_count": sum(row["resolution_overdue_count"] for row in summary_rows),
    }


def format_groups_list_table(groups: list[dict[str, Any]]) -> str:
    rows = [("Group ID", "Group Name")]
    for group in sorted(groups, key=lambda row: group_label(row).lower()):
        rows.append((str(int(group["id"])), group_label(group)))

    widths = [max(len(row[idx]) for row in rows) for idx in range(2)]

    def render(row: tuple[str, str]) -> str:
        return f"{row[0].ljust(widths[0])}  {row[1].ljust(widths[1])}"

    separator = f"{'-' * widths[0]}  {'-' * widths[1]}"
    alias_lines = [
        "",
        "Alias groups:",
        "- 技术客服 / 技术客服组 / 技术客服的数据 => Technical Service",
        "- CS客服组 / CS客服 / CS客服的数据 => Customer Service + Amazon",
        "- 深圳团队 => Technical Service + Technical Support + Customer Service + Amazon",
        "- 墨西哥团队 => MX Support",
    ]
    return "\n".join([render(rows[0]), separator, *[render(row) for row in rows[1:]], *alias_lines])


def format_group_summary_table(group_output: dict[str, Any]) -> str:
    table_rows: list[list[str]] = [
        ["Agent", "Need Follow Up", "Customer Responded", "New", "FR overdue", "Resolution overdue"]
    ]
    for row in group_output["summary_by_agent"]:
        table_rows.append(
            [
                str(row["agent_name"]),
                str(row["actionable_ticket_count"]),
                str(row["customer_responded_ticket_count"]),
                str(row["new_ticket_count"]),
                str(row["fr_overdue_count"]),
                str(row["resolution_overdue_count"]),
            ]
        )

    widths = [max(len(row[idx]) for row in table_rows) for idx in range(len(table_rows[0]))]

    def render(row: list[str]) -> str:
        return "  ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row))

    separator = "  ".join("-" * width for width in widths)
    body = "\n".join([render(table_rows[0]), separator, *[render(row) for row in table_rows[1:]]])
    return f"Group: {group_output['group_name']}\n{body}"


def format_table_output(output: dict[str, Any]) -> str:
    rendered_groups = [format_group_summary_table(group_output) for group_output in output["groups"]]
    cache_hits = output["cache"]["cache_hits"]
    cache_misses = output["cache"]["cache_misses"]
    cache_total = cache_hits + cache_misses
    cache_hit_rate = round((cache_hits / cache_total) * 100) if cache_total else 0
    cache_line = (
        f"Cache: hit rate {cache_hit_rate}% ({cache_hits}/{cache_total}), "
        f"misses={cache_misses}, "
        f"enabled={str(output['cache']['enabled']).lower()}"
    )
    version_line = f"Version: {output['script_version']}"
    run_line = (
        f"Run time: {output['run']['elapsed_seconds']:.2f} seconds; "
        f"Finished: {output['run']['finished_at_display']}"
    )
    detail_line = "JSON detail is still available with: --format json --pretty"
    return "\n\n".join([*rendered_groups, cache_line, version_line, run_line, detail_line])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Return grouped counts and Ticket IDs for actionable Freshdesk tickets."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"freshdesk-needs-follow-up-ticket-numbers {SCRIPT_VERSION}",
    )
    parser.add_argument("--domain", default=os.getenv("FRESHDESK_DOMAIN"), help="Freshdesk domain, e.g. example.freshdesk.com")
    parser.add_argument("--api-key", default=os.getenv("FRESHDESK_API_KEY"), help="Freshdesk API key. Prefer FRESHDESK_API_KEY.")
    parser.add_argument("--group-id", action="append", type=int, default=[], help="Freshdesk group ID. Repeat for multiple groups.")
    parser.add_argument("--group-name", action="append", default=[], help="Freshdesk group name or alias. Repeat for multiple groups.")
    parser.add_argument("--list-groups", action="store_true", help="List Freshdesk groups and exit.")
    parser.add_argument("--cache-path", default=str(DEFAULT_CACHE_PATH), help="Local JSON cache path.")
    parser.add_argument("--cache-retention-days", type=int, default=DEFAULT_CACHE_RETENTION_DAYS, help="Prune ticket cache entries not seen within this many days.")
    parser.add_argument("--no-cache", action="store_true", help="Disable local cache reads and writes for this run.")
    parser.add_argument("--format", choices=("table", "json"), default="table", help="Output format. Default: table.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> int:
    started_monotonic = time.perf_counter()
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
        if args.list_groups:
            rows = [{"group_id": int(group["id"]), "group_name": group_label(group)} for group in groups]
            if args.format == "json":
                print(json.dumps(rows, ensure_ascii=False, indent=2 if args.pretty else None))
            else:
                print(format_groups_list_table(groups))
            return 0

        selected_groups = resolve_selected_groups(groups, args.group_id, args.group_name)
        cache_path = Path(args.cache_path)
        cache_enabled = not args.no_cache
        cache = load_cache(cache_path, cache_enabled)
        now = datetime.now(timezone.utc)

        group_outputs: list[dict[str, Any]] = []
        total_cache_hits = 0
        total_cache_misses = 0
        total_pruned_entries = 0
        total_http_tickets = 0
        customer_response_recheck_totals: defaultdict[str, int] = defaultdict(int)

        for group in selected_groups:
            group_id = int(group["id"])
            group_name_value = group_label(group)
            group_agents = fetch_group_agents(domain, args.api_key, group_id)
            agent_names, active_agents, deactivated_agents = build_agent_maps(group_agents)
            tickets, search_metadata = fetch_group_open_tickets(domain, args.api_key, group, group_agents)
            agent_names = enrich_agent_names_for_tickets(domain, args.api_key, tickets, agent_names)
            stats_by_ticket, outbound_reply_by_ticket, customer_response_sender_by_ticket, cache_stats = fetch_ticket_stats_for_pool(
                domain,
                args.api_key,
                tickets,
                cache,
                cache_enabled,
                cache_path,
                now,
                args.cache_retention_days,
            )
            summary_rows = summarize_by_agent(
                tickets,
                stats_by_ticket,
                outbound_reply_by_ticket,
                agent_names,
                now,
                customer_response_sender_by_ticket,
            )
            totals = summarize_group_totals(summary_rows)

            total_cache_hits += cache_stats["cache_hits"]
            total_cache_misses += cache_stats["cache_misses"]
            total_pruned_entries += cache_stats["pruned_entries"]
            total_http_tickets += cache_stats["cache_misses"]
            for key in (
                "customer_response_recheck_candidates",
                "customer_response_recheck_completed",
                "customer_response_recheck_cache_hits",
                "customer_response_internal_sender_exclusions",
                "customer_response_recheck_unverified",
                "customer_response_recheck_failures",
            ):
                customer_response_recheck_totals[key] += cache_stats[key]

            group_outputs.append(
                {
                    "group_id": group_id,
                    "group_name": group_name_value,
                    "query": search_metadata["group_query"],
                    "freshdesk_total": len(tickets),
                    "summary_by_agent": summary_rows,
                    "totals": totals,
                    "scope": {
                        "group_agents_total": len(group_agents),
                        "group_agents_active": len(active_agents),
                        "group_agents_deactivated": len(deactivated_agents),
                        "deactivated_agents": [
                            {"agent_id": int(agent["id"]), "agent_name": agent_names.get(int(agent["id"]), agent_name(agent))}
                            for agent in sorted(deactivated_agents, key=lambda row: agent_name(row).lower())
                        ],
                    },
                    "search": search_metadata,
                    "cache": cache_stats,
                }
            )

        total_pruned_entries += save_cache(cache_path, cache, cache_enabled, now, args.cache_retention_days)

        output = {
            "script_version": SCRIPT_VERSION,
            "domain": domain,
            "metric_name": "actionable_ticket_buckets",
            "metric_display_name": FOLLOW_UP_DISPLAY_NAME,
            "selection_mode": "explicit_group_choice",
            "group_aliases": GROUP_ALIASES,
            "groups": group_outputs,
            "rules": {
                "new_ticket": "ticket has no public agent reply yet",
                "customer_responded_ticket": "ticket has a public agent reply history and the latest customer reply is newer than the latest agent reply",
                "fr_overdue": "new ticket whose first response due time has already passed",
                "resolution_overdue": "open ticket whose resolution due time has already passed",
            },
            "cache": {
                "enabled": cache_enabled,
                "path": str(cache_path),
                "retention_days": max(1, int(args.cache_retention_days or DEFAULT_CACHE_RETENTION_DAYS)),
                "pruned_entries": total_pruned_entries,
                "cache_hits": total_cache_hits,
                "cache_misses": total_cache_misses,
            },
            "runtime_notes": {
                "group_scope_only": True,
                "default_group_removed": True,
                "conversations_full_scan_removed": True,
                "outbound_fr_overdue_recheck_enabled": True,
                "selected_groups_count": len(selected_groups),
                "ticket_stats_requests": total_http_tickets,
                "fr_outbound_conversation_rechecks": sum(
                    group_output["cache"].get("conversation_rechecks", 0) for group_output in group_outputs
                ),
                "customer_response_recheck_window_seconds": CUSTOMER_RESPONSE_RECHECK_WINDOW_SECONDS,
                **customer_response_recheck_totals,
            },
            "safety": {
                "freshdesk_methods_used": ["GET"],
                "writes_allowed": False,
            },
        }
    except FreshdeskError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    output["run"] = build_run_metadata(started_monotonic)
    if args.format == "json":
        indent = 2 if args.pretty else None
        print(json.dumps(output, ensure_ascii=False, indent=indent))
    else:
        print(format_table_output(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
