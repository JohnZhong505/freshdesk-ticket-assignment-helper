---
name: freshdesk-readonly-ticket-inspector
description: Freshdesk Ticket inspection, unassigned Ticket triage, and supervised assignment preparation. Use when a user needs Ticket counts, Ticket IDs, subjects, assigned Agent names, Group names, unassigned-ticket checks, read-only routing suggestions for unresolved unassigned Tickets, or official Freshdesk API steps for changing responder_id/group_id, while default execution must remain read-only unless the user explicitly supervises a single-ticket write test.
---

# Freshdesk Readonly Ticket Inspector

## Overview

Use this skill as the main read-only Freshdesk support operations inspector.

Its role is to inspect Freshdesk Tickets safely, triage unresolved unassigned Tickets, resolve ownership metadata, and prepare controlled assignment decisions. It does not compute `需跟进Ticket` workload; use the separate `freshdesk-needs-follow-up-ticket-numbers` skill for that.

## Unassigned Ticket Triage

When the user asks to triage or route unassigned Tickets, run:

```bash
python3 scripts/freshdesk_readonly_ticket_inspector.py \
  --triage-unassigned-view \
  --limit 30 \
  --pretty
```

This mode mirrors the Freshdesk view used for morning routing:

- Agent: `Unassigned`
- Groups: `Technical Service`, `Unassigned`, `MX Support`
- API mapping: the Freshdesk UI pseudo-group `Unassigned` is searched as `group_id:null`
- Status: `All unresolved`; include Freshdesk status `2` Open and `3` Pending, exclude `4` Resolved and `5` Closed
- Exclude Tickets where `spam=true`
- Exclude Tickets tagged `Escalation` or `RMA`; these require full manual review

Use each Ticket's `subject`, the API `description_text` opening message, attachment metadata, and later public conversations where `use_for_triage=true` to decide whether it belongs with Merge, Sales, CS, Technical Service, Technical Support, or another routing bucket. From this Technical Service skill, ecommerce and small-batch quotation work is routed to CS; CS decides whether to hand it off to Shopify. In Freshdesk's API, `description_text` is the customer's initial ticket message; this is separate from later human-filled notes or custom fields. Attachment metadata contains names, types, and sizes only; do not download files during initial triage.

Public conversation rows with `use_for_triage=false` are context only. They may include public automatic replies or internal support mailbox mirrors, and should not drive the routing decision.

Merge history is checked only when the new Ticket has a direct named salutation such as `Dear Ann`, a subject beginning with `Re:`, or explicit continuation language such as `follow-up` or `previously quoted`. The check uses `GET /api/v2/tickets?requester_id=<id>` with at most 10 recent Tickets and returns metadata only for older Tickets whose normalized subject matches or whose subject begins with `Re:`. Do not fetch old Ticket descriptions or conversations.

Before giving routing suggestions, read `references/triage-routing-rules.md` and apply its bucket rules, examples, and confidence guidance.

Group the final answer by suggested routing bucket. Give every non-empty bucket its own Markdown table; do not mix different routing destinations into one table.

## Safety Rules

- Default to read-only Freshdesk API calls.
- Do not perform any Ticket update unless the user explicitly asks for a supervised write test after reviewing the exact Ticket ID, target Agent ID, and optional Group ID.
- Never bulk update Tickets during initial validation.
- Never write API keys into `SKILL.md`, scripts, config files, logs, shell snippets, Git commits, or chat summaries.
- Read the API key from `FRESHDESK_API_KEY`; read the domain from `FRESHDESK_DOMAIN`.
- Do not include customer email addresses or message bodies in outputs unless the user explicitly asks and accepts the privacy risk.

## Read-Only Inspection

Run the bundled inspector:

```bash
python3 scripts/freshdesk_readonly_ticket_inspector.py --limit 20 --pretty
```

For a filtered pool, use Freshdesk search syntax:

```bash
python3 scripts/freshdesk_readonly_ticket_inspector.py \
  --query "group_id:123456 AND agent_id:null" \
  --limit 30 \
  --pretty
```

Report:

- `ticket_count` from the fetched result set.
- `freshdesk_total` when using search and Freshdesk returns a total.
- Ticket IDs and subjects.
- Resolved Agent names from `responder_id`.
- Resolved Group names from `group_id`.

## Official API Notes

Freshdesk documents:

- `GET /api/v2/tickets` for listing tickets.
- `GET /api/v2/search/tickets?query=[query]` for filtered search; search supports `agent_id`, `group_id`, `status`, priority, date fields, null filters, and returns a total count.
- `GET /api/v2/tickets/[ticket_id]/conversations` for public conversation text used by triage mode.
- `GET /api/v2/agents` for resolving Agent IDs to names.
- `GET /api/v2/groups` for resolving Group IDs to names.
- `PUT /api/v2/tickets/[id]` for updating a single Ticket.
- `responder_id` is the Agent assignment field.
- `group_id` is the Group assignment field.

## Supervised Assignment Procedure

Use this only after read-only inspection has identified one exact Ticket and the user is watching the test.

1. Re-read the current Ticket with `GET /api/v2/tickets/[ticket_id]`.
2. Re-read Agents and Groups to verify the target Agent and Group IDs.
3. Show the user a preview with Ticket ID, subject, current assignment fields, and proposed assignment fields.
4. Ask the user for an exact confirmation phrase naming the Ticket ID.
5. Only after that exact confirmation, perform a single-Ticket update with `scripts/freshdesk_assign_ticket_agent.py --execute --confirm-ticket-id`.
6. Immediately re-read the same Ticket and report before/after assignment fields.
7. Stop after one Ticket unless the user gives a new explicit instruction.

## Resources

- `scripts/freshdesk_readonly_ticket_inspector.py`: main read-only Freshdesk inspector and unassigned Ticket triage view.
- `scripts/freshdesk_assign_ticket_agent.py`: guarded single-Ticket assignment helper; defaults to dry-run and requires `--execute --confirm-ticket-id`.
- `references/freshdesk-api-contract.md`: endpoint, safety, and output contract.
- `references/triage-routing-rules.md`: routing rules and seed examples from real manual triage cases.
