---
name: freshdesk-needs-follow-up-ticket-numbers
description: Lightweight Freshdesk read-only actionable-ticket skill. Use when a user wants grouped counts and Ticket IDs for current New and Customer Responded workload, plus overdue visibility, especially for fast staffing snapshots, Hermes runs, or cronjob automation.
---

# Freshdesk Needs Follow Up Ticket Numbers

## Overview

Use this skill when the only goal is to answer one question quickly:

who currently owns how many actionable Tickets.

This skill is intentionally narrow. It does not try to be a general Freshdesk inspector or assignment helper.

## Selection Flow

- Always list available Freshdesk groups first.
- In human-in-the-loop runs, ask the user which `group` or `groups` to scan before running the metric.
- In automation or cron runs, pass the target groups explicitly. Do not silently default to one group.

The script supports:

- `--list-groups`
- repeated `--group-id`
- repeated `--group-name`
- `--format table|json`

## Built-in Group Aliases

These aliases are built into the skill:

- `技术客服的数据`
  maps to `Technical Service`
- `技术客服组`
  maps to `Technical Service`
- `技术客服`
  maps to `Technical Service`
- `CS客服组`
  maps to `Customer Service` + `Amazon`
- `CS客服的数据`
  maps to `Customer Service` + `Amazon`
- `CS客服`
  maps to `Customer Service` + `Amazon`

## Metric Definition

This skill reports four grouped buckets per agent:

- `New Ticket`
  the Ticket has no public agent reply yet
- `Customer Responded Ticket`
  the Ticket has agent public reply history, and the latest customer reply is newer than the latest agent reply
- `FR overdue`
  a `New Ticket` whose first-response due time has already passed
- `Resolution overdue`
  an open Ticket whose resolution due time has already passed

The result is grouped by current assignee, with `Unassigned` shown separately.

## Safety Rules

- Use read-only Freshdesk API calls only.
- Never update Ticket assignment, replies, notes, contacts, or watchers.
- Never bulk change Tickets.
- Read the API key from `FRESHDESK_API_KEY`; read the domain from `FRESHDESK_DOMAIN`.
- Do not include customer email addresses or message bodies in outputs unless the user explicitly asks and accepts the privacy risk.

## Quick Run

List groups first:

```bash
python3 scripts/freshdesk_needs_follow_up_ticket_numbers.py --list-groups
```

Technical Service via alias:

```bash
python3 scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "技术客服的数据" \
  --format table
```

CS group bundle via alias:

```bash
python3 scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "CS客服组" \
  --format table
```

Full JSON detail:

```bash
python3 scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "Technical Service" \
  --format json \
  --pretty
```

## Output

The grouped output includes:

- default `table` output for humans:
  - `Agent`
  - `Need Follow Up`
  - `Customer Responded`
  - `New`
  - `FR overdue`
  - `Resolution overdue`
- optional full `json` output for detailed Ticket IDs and metadata

The default table prints each selected `Group` name followed directly by the per-agent rows. It does not print group ID or group-level totals above the table.

## Runtime Notes

- Freshdesk search pagination is capped at page `10`.
- This skill first tries one direct group-level open-ticket search.
- Only when the group open pool exceeds the search limit does it fall back to smaller group-agent-scoped searches.
- Group-agent fallback stays inside the selected group. It does not scan all account agents.
- Ticket classification uses cached Ticket `stats` whenever the current Ticket `updated_at` still matches the cache.
- Changed or uncached Tickets are refreshed from Freshdesk with `GET /api/v2/tickets/[id]?include=stats`.
- The default output is `table`. Use `--format json --pretty` for full detail.

This behavior exists to prevent silent undercounting while avoiding unnecessary repeated Ticket-detail reads.

## Boundary

This skill is for fast grouped actionable-Ticket numbers only.

If the user also needs broader Ticket inspection, unassigned pools, assignment previews, or supervised single-Ticket reassignment steps, use the main skill `freshdesk-readonly-ticket-inspector` instead.
