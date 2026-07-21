#!/usr/bin/env python3
"""Guarded Customer Service Group assignment for selected Freshdesk Tickets."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable


READ_TIMEOUT_SECONDS = 30
MAX_TICKETS = 20
SOURCE_GROUP_NAME = "Technical Service"
TARGET_GROUP_NAME = "Customer Service"
ALLOWED_STATUSES = {2, 3}
PROTECTED_TAGS = {"escalation", "rma"}


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


def request_json(
    domain: str,
    api_key: str,
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        f"https://{domain}{path}",
        data=data,
        headers={
            "Authorization": auth_header(api_key),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "freshdesk-ticket-assignment-helper/1.4",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=READ_TIMEOUT_SECONDS) as response:
            payload = response.read().decode("utf-8")
            if not payload:
                return None
            try:
                return json.loads(payload)
            except json.JSONDecodeError as exc:
                raise FreshdeskError(f"{method} {path} returned invalid JSON.") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FreshdeskError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        raise FreshdeskError(f"{method} {path} failed: {reason}") from exc


def get_json(domain: str, api_key: str, path: str) -> Any:
    return request_json(domain, api_key, path)


def put_ticket(domain: str, api_key: str, ticket_id: int, body: dict[str, Any]) -> Any:
    return request_json(domain, api_key, f"/api/v2/tickets/{ticket_id}", "PUT", body)


def fetch_groups(domain: str, api_key: str) -> dict[int, str]:
    groups: dict[int, str] = {}
    for page in range(1, 101):
        query = urllib.parse.urlencode({"page": page, "per_page": 100})
        payload = get_json(domain, api_key, f"/api/v2/groups?{query}")
        if not isinstance(payload, list):
            raise FreshdeskError("Freshdesk groups response was not a JSON list.")
        for group in payload:
            if isinstance(group, dict) and group.get("id") is not None:
                groups[int(group["id"])] = str(group.get("name") or f"Group {group['id']}")
        if len(payload) < 100:
            return groups
    raise FreshdeskError("Freshdesk groups pagination exceeded 100 pages.")


def parse_ticket_ids(value: str) -> list[int]:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise FreshdeskError("Provide at least one Ticket ID.")
    try:
        ticket_ids = [int(part) for part in parts]
    except ValueError as exc:
        raise FreshdeskError("Ticket IDs must be comma-separated integers.") from exc
    if any(ticket_id <= 0 for ticket_id in ticket_ids):
        raise FreshdeskError("Ticket IDs must be positive integers.")
    if len(set(ticket_ids)) != len(ticket_ids):
        raise FreshdeskError("Duplicate Ticket IDs are not allowed.")
    if len(ticket_ids) > MAX_TICKETS:
        raise FreshdeskError(f"At most {MAX_TICKETS} Tickets can be assigned in one run.")
    return ticket_ids


def resolve_assignment_groups(groups: dict[int, str]) -> tuple[int, int]:
    def unique_group_id(group_name: str) -> int:
        matches = [
            group_id
            for group_id, name in groups.items()
            if name == group_name
        ]
        if not matches:
            raise FreshdeskError(f"Freshdesk Group not found: {group_name}")
        if len(matches) != 1:
            raise FreshdeskError(f"Freshdesk Group name is not unique: {group_name}")
        return matches[0]

    source_id = unique_group_id(SOURCE_GROUP_NAME)
    target_id = unique_group_id(TARGET_GROUP_NAME)
    if source_id == target_id:
        raise FreshdeskError("Source and target Groups resolved to the same ID.")
    return source_id, target_id


def candidate_error(ticket: dict[str, Any], expected_ticket_id: int, source_group_id: int) -> str | None:
    if ticket.get("id") != expected_ticket_id:
        return "Freshdesk returned a different Ticket ID."
    if ticket.get("status") not in ALLOWED_STATUSES:
        return "Ticket status is not Open or Pending."
    if ticket.get("spam") is not False:
        return "Ticket is Spam or its Spam state is unavailable."
    if "responder_id" not in ticket or ticket["responder_id"] is not None:
        return "Ticket Agent is assigned; responder_id must remain empty."
    if ticket.get("group_id") not in {None, source_group_id}:
        return "Ticket source Group is not Technical Service or empty."
    raw_tags = ticket.get("tags")
    if not isinstance(raw_tags, list):
        return "Ticket tags are unavailable or malformed."
    tags = {
        str(tag).strip().casefold()
        for tag in raw_tags
        if isinstance(tag, str)
    }
    if tags & PROTECTED_TAGS:
        return "Ticket has a protected tag (Escalation or RMA)."
    return None


def assignment_payload(target_group_id: int) -> dict[str, int]:
    return {"group_id": target_group_id}


def shape_ticket(domain: str, ticket: dict[str, Any]) -> dict[str, Any]:
    ticket_id = ticket.get("id")
    return {
        "ticket_id": ticket_id,
        "ticket_url": f"https://{domain}/a/tickets/{ticket_id}" if ticket_id is not None else None,
        "subject": ticket.get("subject"),
        "status": ticket.get("status"),
        "group_id": ticket.get("group_id"),
        "responder_id": ticket.get("responder_id"),
        "tags": ticket.get("tags") or [],
    }


def assign_cs_tickets(
    domain: str,
    api_key: str,
    ticket_ids: list[int],
    *,
    execute: bool,
    confirmed_ticket_ids: list[int] | None = None,
    group_fetcher: Callable[[str, str], dict[int, str]] | None = None,
) -> dict[str, Any]:
    if not ticket_ids:
        raise FreshdeskError("Provide at least one Ticket ID.")
    if any(ticket_id <= 0 for ticket_id in ticket_ids):
        raise FreshdeskError("Ticket IDs must be positive integers.")
    if len(set(ticket_ids)) != len(ticket_ids):
        raise FreshdeskError("Duplicate Ticket IDs are not allowed.")
    if len(ticket_ids) > MAX_TICKETS:
        raise FreshdeskError(f"At most {MAX_TICKETS} Tickets can be assigned in one run.")
    if execute and confirmed_ticket_ids != ticket_ids:
        raise FreshdeskError("Execution confirmation must repeat the exact Ticket IDs in the same order.")

    group_fetcher = group_fetcher or fetch_groups
    groups = group_fetcher(domain, api_key)
    source_group_id, target_group_id = resolve_assignment_groups(groups)
    payload = assignment_payload(target_group_id)
    preflight: list[dict[str, Any]] = []
    errors: list[str] = []

    for ticket_id in ticket_ids:
        ticket = get_json(domain, api_key, f"/api/v2/tickets/{ticket_id}")
        if not isinstance(ticket, dict):
            errors.append(f"Ticket {ticket_id}: response was not a JSON object.")
            continue
        error = candidate_error(ticket, ticket_id, source_group_id)
        preflight.append({**shape_ticket(domain, ticket), "eligible": error is None, "error": error})
        if error:
            errors.append(f"Ticket {ticket_id}: {error}")

    if errors:
        raise FreshdeskError("Preflight failed; no writes were sent. " + " ".join(errors))

    output: dict[str, Any] = {
        "domain": domain,
        "mode": "execute" if execute else "dry_run",
        "target_group": {"group_id": target_group_id, "group_name": TARGET_GROUP_NAME},
        "request_body": payload,
        "ticket_count": len(ticket_ids),
        "tickets": preflight,
        "writes_sent": 0,
        "success": True,
        "safety": {
            "source_groups_allowed": [SOURCE_GROUP_NAME, "Unassigned"],
            "agent_assignment_allowed": False,
            "bulk_update_used": False,
        },
    }
    if not execute:
        return output

    completed: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    output.update(completed=completed, failed=failed, ambiguous=ambiguous)

    def stop(
        *,
        index: int,
        ticket_id: int,
        phase: str,
        reason: str,
        uncertain: bool = False,
    ) -> None:
        record = {"ticket_id": ticket_id, "phase": phase, "reason": reason}
        (ambiguous if uncertain else failed).append(record)
        unattempted = ticket_ids[index + 1 :]
        output.update(
            success=False,
            error=f"Ticket {ticket_id}: {reason}",
            unattempted_ticket_ids=unattempted,
            remaining_ticket_ids=unattempted,
        )

    for index, ticket_id in enumerate(ticket_ids):
        try:
            current = get_json(domain, api_key, f"/api/v2/tickets/{ticket_id}")
        except FreshdeskError as exc:
            stop(index=index, ticket_id=ticket_id, phase="pre_put", reason=str(exc))
            break
        if not isinstance(current, dict):
            stop(
                index=index,
                ticket_id=ticket_id,
                phase="pre_put",
                reason="write-time response was not a JSON object.",
            )
            break
        error = candidate_error(current, ticket_id, source_group_id)
        if error:
            stop(
                index=index,
                ticket_id=ticket_id,
                phase="pre_put",
                reason=f"write-time precondition failed: {error}",
            )
            break

        before = shape_ticket(domain, current)
        try:
            put_ticket(domain, api_key, ticket_id, payload)
            output["writes_sent"] += 1
        except FreshdeskError as exc:
            stop(
                index=index,
                ticket_id=ticket_id,
                phase="put",
                reason=f"PUT result is ambiguous or failed: {exc}",
                uncertain=True,
            )
            break

        try:
            after = get_json(domain, api_key, f"/api/v2/tickets/{ticket_id}")
        except FreshdeskError as exc:
            stop(
                index=index,
                ticket_id=ticket_id,
                phase="readback",
                reason=f"post-write verification failed: {exc}",
                uncertain=True,
            )
            break
        if not isinstance(after, dict):
            stop(
                index=index,
                ticket_id=ticket_id,
                phase="readback",
                reason="post-write verification response was not a JSON object.",
                uncertain=True,
            )
            break
        shaped_after = shape_ticket(domain, after)
        preflight[index]["before"] = before
        preflight[index]["after"] = shaped_after
        if (
            after.get("group_id") != target_group_id
            or "responder_id" not in after
            or after["responder_id"] is not None
        ):
            stop(
                index=index,
                ticket_id=ticket_id,
                phase="verify",
                reason=(
                    "verification failed; expected Customer Service Group with an empty Agent. "
                    "Stop and review Freshdesk manually."
                ),
            )
            break
        completed.append({"ticket_id": ticket_id, "before": before, "after": shaped_after})
    if output["success"]:
        output.update(unattempted_ticket_ids=[], remaining_ticket_ids=[])
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or execute a guarded Customer Service Group assignment for selected Freshdesk Tickets."
    )
    parser.add_argument("--domain", default=os.getenv("FRESHDESK_DOMAIN"), help="Freshdesk domain.")
    parser.add_argument("--ticket-ids", required=True, help="Comma-separated Ticket IDs selected for CS routing.")
    parser.add_argument("--execute", action="store_true", help="Send one PUT per Ticket. Omit for dry-run.")
    parser.add_argument(
        "--confirm-ticket-ids",
        help="Required with --execute; repeat --ticket-ids exactly and in the same order.",
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

    try:
        domain = normalize_domain(args.domain)
        ticket_ids = parse_ticket_ids(args.ticket_ids)
        confirmed = parse_ticket_ids(args.confirm_ticket_ids) if args.confirm_ticket_ids else None
        output = assign_cs_tickets(
            domain,
            api_key,
            ticket_ids,
            execute=args.execute,
            confirmed_ticket_ids=confirmed,
        )
    except FreshdeskError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    indent = 2 if args.pretty else None
    print(json.dumps(output, ensure_ascii=False, indent=indent))
    return 0 if output.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
