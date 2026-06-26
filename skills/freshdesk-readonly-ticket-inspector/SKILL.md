---
name: freshdesk-readonly-ticket-inspector
description: Freshdesk Ticket inspection and supervised assignment preparation. Use when a user needs Ticket counts, Ticket IDs, subjects, assigned Agent names, Group names, unassigned-ticket checks, follow-up workload context, or official Freshdesk API steps for changing responder_id/group_id, while default execution must remain read-only unless the user explicitly supervises a single-ticket write test.
---

# Freshdesk Readonly Ticket Inspector

## Overview

Use this skill as the main Freshdesk support operations skill.

Its default role is to inspect Freshdesk Tickets safely, resolve who owns them, and prepare controlled assignment decisions. It now also includes a formal follow-up workload capability for the metric `需跟进Ticket`.

## Formal Follow-Up Capability

When a user asks for `需跟进Ticket`, use this definition:

- The Ticket is open.
- The Ticket already has at least one public agent reply.
- The latest effective public reply is from the customer.
- Ignore mirrored pseudo-replies from your own support mailboxes, including `cs@gl-inet.com`, `support@gl-inet.com`, and `support@glinet.biz`.

This is now a first-class ability of the main skill, not a separate temporary variant.

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
export FRESHDESK_DOMAIN="example.freshdesk.com"
export FRESHDESK_API_KEY="..."
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

## Follow-Up Workload Summary

For a grouped `需跟进Ticket` summary by agent inside one Freshdesk Group:

```bash
python3 scripts/freshdesk_readonly_ticket_inspector.py \
  --group-name "Technical Service" \
  --needs-follow-up-ticket-summary \
  --pretty
```

This is the preferred quick command when the user wants current follow-up workload by person.

Equivalent long-form command:

```bash
python3 scripts/freshdesk_readonly_ticket_inspector.py \
  --group-name "Technical Service" \
  --needs-follow-up \
  --summary-by-agent \
  --pretty
```

## Official API Notes

Freshdesk documents:

- `GET /api/v2/tickets` for listing tickets.
- `GET /api/v2/search/tickets?query=[query]` for filtered search; search supports `agent_id`, `group_id`, `status`, priority, date fields, null filters, and returns a total count.
- `GET /api/v2/agents` for resolving Agent IDs to names.
- `GET /api/v2/groups` for resolving Group IDs to names.
- `PUT /api/v2/tickets/[id]` for updating a single Ticket.
- `responder_id` is the Agent assignment field.
- `group_id` is the Group assignment field.

## Supervised Assignment Procedure

Use this only after read-only inspection has identified one exact Ticket and the user is watching the test.

1. Re-read the current Ticket with `GET /api/v2/tickets/[ticket_id]`.
2. Re-read Agents and Groups to verify the target Agent and Group IDs.
3. Show the user a preview with:
   - Ticket ID and subject.
   - Current `responder_id`, Agent name, `group_id`, and Group name.
   - New `responder_id`, Agent name, optional `group_id`, and Group name.
4. Ask the user for an exact confirmation phrase:

```text
确认修改 Freshdesk Ticket <ticket_id> 分配
```

5. Only after that exact confirmation, perform a single-Ticket update:

```bash
python3 scripts/freshdesk_assign_ticket_agent.py \
  --ticket-id 12345 \
  --responder-id 67890 \
  --group-id 11111 \
  --execute \
  --confirm-ticket-id 12345
```

6. Immediately re-read the same Ticket and report before/after assignment fields.
7. Stop after one Ticket unless the user gives a new explicit instruction.

## Resources

- `scripts/freshdesk_readonly_ticket_inspector.py`: main read-only Freshdesk inspector, including the formal `需跟进Ticket` workload view.
- `scripts/freshdesk_assign_ticket_agent.py`: guarded single-Ticket assignment helper; defaults to dry-run and requires `--execute --confirm-ticket-id`.
- `references/freshdesk-api-contract.md`: endpoint, safety, and output contract.
