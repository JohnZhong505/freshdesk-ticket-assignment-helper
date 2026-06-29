---
name: freshdesk-needs-follow-up-ticket-numbers
description: Lightweight Freshdesk read-only follow-up workload skill. Use when a user wants grouped counts and Ticket IDs for the formal 需跟进Ticket metric by agent, especially for fast staffing snapshots, Hermes runs, or cronjob automation.
---

# Freshdesk Needs Follow Up Ticket Numbers

## Overview

Use this skill when the only goal is to answer one question quickly:

who currently owns how many `需跟进Ticket`.

This skill is intentionally narrow. It does not try to be a general Freshdesk inspector or assignment helper.

## Metric Definition

A Ticket counts as `需跟进Ticket` only when:

- the Ticket is open
- the Ticket already has at least one public agent reply
- the latest effective public reply is from the customer
- mirrored pseudo-replies from `cs@gl-inet.com`, `support@gl-inet.com`, and `support@glinet.biz` are ignored

## Safety Rules

- Use read-only Freshdesk API calls only.
- Never update Ticket assignment, replies, notes, contacts, or watchers.
- Never bulk change Tickets.
- Read the API key from `FRESHDESK_API_KEY`; read the domain from `FRESHDESK_DOMAIN`.
- Do not include customer email addresses or message bodies in outputs unless the user explicitly asks and accepts the privacy risk.

## Quick Run

Default group:

```bash
export FRESHDESK_DOMAIN="example.freshdesk.com"
export FRESHDESK_API_KEY="..."
python3 scripts/freshdesk_needs_follow_up_ticket_numbers.py --pretty
```

Explicit group:

```bash
python3 scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "Technical Service" \
  --pretty
```

## Output

The grouped output includes:

- `metric_name`
- `metric_display_name`
- `group_name`
- `ticket_count`
- `summary_by_agent[]` with `agent_name`, `ticket_count`, and `ticket_ids`

## Runtime Notes

- Freshdesk search pagination is capped at page `10`.
- When the open Ticket pool for one group grows beyond that search limit, this skill does not rely on one plain group-level search.
- Instead, it gathers open Tickets in smaller agent-scoped batches, merges them, and then applies the formal `需跟进Ticket` rule.

This behavior exists to prevent silent undercounting when the live group queue is large.

## Boundary

This skill is for fast grouped `需跟进Ticket` numbers only.

If the user also needs broader Ticket inspection, unassigned pools, assignment previews, or supervised single-Ticket reassignment steps, use the main skill `freshdesk-readonly-ticket-inspector` instead.
