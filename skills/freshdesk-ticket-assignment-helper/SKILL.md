---
name: freshdesk-ticket-assignment-helper
description: Use when inspecting, triaging, or safely assigning selected Freshdesk Tickets, especially unresolved unassigned Tickets that need routing suggestions or a supervised Customer Service Group handoff.
---

# Freshdesk Ticket Assignment Helper

## Overview

Use this skill for Freshdesk morning triage and controlled Ticket routing. It remains read-only by default. Its only current write capability moves explicitly selected eligible Tickets to the `Customer Service` Group while leaving the Agent unassigned.

This skill does not compute `需跟进Ticket` workload; use `freshdesk-needs-follow-up-ticket-numbers` for that.

## Read-Only Triage

Run:

```bash
python3 scripts/freshdesk_readonly_ticket_inspector.py \
  --triage-unassigned-view \
  --limit 30 \
  --pretty
```

The triage pool mirrors the morning Freshdesk view:

- Agent: `Unassigned`
- Groups: `Technical Service`, UI pseudo-group `Unassigned`, and `MX Support`
- Status: `All unresolved`; include `Open` and `Pending`, exclude `Resolved` and `Closed`
- Exclude `spam=true`
- Skip Tickets tagged `Escalation` or `RMA`

Before suggesting routes, read `references/triage-routing-rules.md`. Use `subject`, the opening customer message, later public customer conversations, attachment metadata, and narrow Merge metadata. Automatic replies are context only. Explicit triage may process full customer text internally, but the user-facing response must contain only short evidence snippets. Do not download attachments during initial triage.

Group the answer by routing destination. Render every current or referenced Ticket ID as `[ticket_id](ticket_url)`. Do not mix destinations in one table.

## Triage Response Contract

Every triage response must use this order:

1. Start with: `本次识别 **N 张候选 Ticket**，另有 **M 张 Escalation/RMA Ticket 已跳过**。全程仅使用 Freshdesk GET，没有执行改派。` Use `ticket_count` for N and `excluded_tag_ticket_count` for M.
2. Output separate Markdown tables for each non-empty routing destination.
3. Count CS assignment candidates: Tickets routed to `CS` whose current Group is `Technical Service` or empty. This count is advisory; the assignment helper must still run its live preflight.
4. If the count is greater than zero, end with: `当前适合一键改派至 Customer Service 的 Ticket 共 N 张：IDs。是否要一键改派以上 N 张？` State that after the dry-run preview, the user may reply `确认`; they do not need to repeat the Ticket IDs.
5. If the count is zero, end with: `当前适合一键改派至 Customer Service 的 Ticket 共 0 张，本次无需改派。`

## Customer Service Group Assignment

Use this only after the user reviews the read-only CS table and asks to assign the displayed CS candidates. The user may select individual Ticket IDs or refer to the whole displayed CS batch.

### Eligibility

Every selected Ticket must still satisfy all conditions:

- Group is `Technical Service` or empty.
- Agent is empty (`responder_id=null`).
- Status is `Open` or `Pending`.
- Ticket is not Spam.
- Ticket has neither `Escalation` nor `RMA` tag.
- Target Group resolves exactly to `Customer Service`.

The helper never accepts a target Group or Agent argument. Its PUT body contains only `group_id`; it does not write `responder_id`.

### 1. Preview

Always run dry-run first:

```bash
python3 scripts/freshdesk_assign_cs_group.py \
  --ticket-ids "136100,136101" \
  --pretty
```

Review the returned Ticket links, subjects, current Group/Agent, target Group, and `request_body`. If any Ticket is ineligible, the helper aborts the whole preflight and sends no writes.

### 2. Confirm

Show the exact Ticket list after a successful dry-run and ask for confirmation. The user may reply `确认`; this authorizes only the exact IDs in the latest dry-run preview in the current conversation. Do not reuse that confirmation after a newer triage/preview, a changed selection, or any ambiguity about which batch it refers to.

### 3. Execute

Only after confirmation, pass the latest previewed IDs to both CLI arguments in the same order; this repetition is an internal script guard and is not required in the user's reply:

```bash
python3 scripts/freshdesk_assign_cs_group.py \
  --ticket-ids "136100,136101" \
  --execute \
  --confirm-ticket-ids "136100,136101" \
  --pretty
```

The helper rechecks each Ticket immediately before its PUT, sends one `PUT /api/v2/tickets/[id]` with only the resolved Customer Service `group_id`, then re-reads the Ticket. Success requires the target Group and an empty Agent in the readback.

If a write or verification fails, stop immediately. Report completed, failed/ambiguous, and unattempted Ticket IDs. Never claim atomic behavior and never auto-rollback.

## Safety Rules

- Default to read-only mode. Never add `--execute` without the user's current explicit confirmation.
- A dry-run is not an authorization token. Never reuse old approval or run execute mode from Hermes, cron, or another unattended flow.
- Do not use Freshdesk bulk update for this flow.
- Do not assign Agents, clear an assigned Agent, change status, add tags, reply, note, merge, or modify contacts.
- Do not write Tickets from `MX Support`, `Customer Service`, or any other non-eligible Group.
- Never put API keys in files, logs, commands shown to users, commits, or summaries. The CLIs read `FRESHDESK_API_KEY` only from the environment; read `FRESHDESK_DOMAIN` from the environment by default.
- Do not include customer email addresses or full message bodies in the user-facing response. Explicit triage may process full customer text internally; treat its JSON as sensitive transient data and never commit it.
- Freshdesk automations may react to a Group change. The helper verifies Ticket fields, not downstream automation outcomes.
- A state change between the final GET and PUT remains a supervised residual risk; stop and review any failed or ambiguous result manually.

## General Read-Only Inspection

```bash
python3 scripts/freshdesk_readonly_ticket_inspector.py --limit 20 --pretty
```

For a filtered pool:

```bash
python3 scripts/freshdesk_readonly_ticket_inspector.py \
  --query "group_id:123456 AND agent_id:null" \
  --limit 30 \
  --pretty
```

## API Notes

- `GET /api/v2/tickets/[id]`: preflight and verification.
- `GET /api/v2/groups`: exact Group-name resolution.
- `GET /api/v2/search/tickets`: filtered read-only triage.
- `GET /api/v2/tickets/[id]/conversations`: customer-authored triage context.
- `PUT /api/v2/tickets/[id]`: selected CS Group assignment only.
- `group_id`: assigned Group field.
- `responder_id`: assigned Agent field; this flow requires it to remain `null`.

## Resources

- `scripts/freshdesk_readonly_ticket_inspector.py`: read-only inspection and unassigned triage.
- `scripts/freshdesk_assign_cs_group.py`: guarded selected-Ticket assignment to Customer Service; dry-run by default.
- `references/freshdesk-api-contract.md`: API, precondition, failure, and output contract.
- `references/triage-routing-rules.md`: routing rules and confirmed examples.
