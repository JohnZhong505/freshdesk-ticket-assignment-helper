# Freshdesk Support Skills

This repository contains two installable Codex skills under `skills/`.

## Skills

| Skill | Definition | Best use |
| --- | --- | --- |
| `freshdesk-readonly-ticket-inspector` | Main Freshdesk operations skill for safe Ticket inspection, assignment context, and controlled single-Ticket assignment preparation. | Use when you need the broader Freshdesk support workflow, not just one metric. |
| `freshdesk-needs-follow-up-ticket-numbers` | Lightweight read-only skill that focuses only on grouped actionable Ticket counts by agent, including `New`, `Customer Responded`, `FR overdue`, and `Resolution overdue`. | Use when you want a fast, focused output for Hermes, cronjob runs, or staffing snapshots. |

## Shared Meaning Of Actionable Tickets

The lightweight skill reports four grouped buckets:

- `Need Follow Up`
  `New` + `Customer Responded`
- `Customer Responded`
  the latest customer reply is newer than the latest agent reply
- `New`
  no public agent reply yet
- `FR overdue`
  first-response due time has already passed for a `New` ticket
- `Resolution overdue`
  resolution due time has already passed for an open ticket

## Repository Layout

```text
skills/
  freshdesk-readonly-ticket-inspector/
  freshdesk-needs-follow-up-ticket-numbers/
scripts/
validation/
install-skill.sh
```

## Install

Install the main skill:

```bash
./install-skill.sh --skill freshdesk-readonly-ticket-inspector
```

Install the lightweight skill:

```bash
./install-skill.sh --skill freshdesk-needs-follow-up-ticket-numbers
```

The installer copies the selected skill into `${CODEX_HOME:-$HOME/.codex}/skills`.

## Direct Skill Paths

These are the repo paths to use when installing directly from GitHub:

- `skills/freshdesk-readonly-ticket-inspector`
- `skills/freshdesk-needs-follow-up-ticket-numbers`

## Built-In Group Aliases

These aliases are supported directly by `freshdesk-needs-follow-up-ticket-numbers`:

- `技术客服的数据`
  maps to `Technical Service`
- `技术客服组`
  maps to `Technical Service`
- `CS客服组`
  maps to `Customer Service` + `Amazon`
- `CS客服的数据`
  maps to `Customer Service` + `Amazon`

## Quick Usage

Main skill:

```bash
export FRESHDESK_DOMAIN="example.freshdesk.com"
export FRESHDESK_API_KEY="..."
python3 skills/freshdesk-readonly-ticket-inspector/scripts/freshdesk_readonly_ticket_inspector.py \
  --group-name "Technical Service" \
  --needs-follow-up-ticket-summary \
  --pretty
```

Lightweight skill:

```bash
export FRESHDESK_DOMAIN="example.freshdesk.com"
export FRESHDESK_API_KEY="..."
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "技术客服的数据"
```

Full JSON detail:

```bash
python3 skills/freshdesk-needs-follow-up-ticket-numbers/scripts/freshdesk_needs_follow_up_ticket_numbers.py \
  --group-name "Technical Service" \
  --format json \
  --pretty
```

## Runtime Note

Freshdesk search pagination is capped at page `10`.

That limit is now important for the lightweight skill because a group open-ticket pool can exceed what one plain group-level search can safely cover. The lightweight skill first tries one direct group-level query, then falls back to smaller selected-group agent-scoped batches only when needed. It also caches Ticket stats locally so repeated runs do not keep refetching unchanged Ticket details.

## Safety

- Freshdesk API keys must be supplied through `FRESHDESK_API_KEY` or an equivalent secret manager.
- Tracked files must not contain API keys, webhooks, or live Ticket exports.
- Live output is ignored under `validation/live-output*.json` because Ticket subjects can contain customer information.
- Bulk Ticket updates are intentionally outside this repository.
