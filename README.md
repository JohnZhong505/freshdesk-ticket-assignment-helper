# Freshdesk Support Skills

This repository contains two installable Codex skills under `skills/`.

## Skills

| Skill | Definition | Best use |
| --- | --- | --- |
| `freshdesk-readonly-ticket-inspector` | Main Freshdesk operations skill for safe Ticket inspection, assignment context, and controlled single-Ticket assignment preparation. It also formally includes the `需跟进Ticket` workload capability. | Use when you need the broader Freshdesk support workflow, not just one metric. |
| `freshdesk-needs-follow-up-ticket-numbers` | Lightweight read-only skill that focuses only on grouped `需跟进Ticket` counts and Ticket IDs by agent. | Use when you want a fast, focused output for Hermes, cronjob runs, or staffing snapshots. |

## Shared Meaning Of `需跟进Ticket`

A Ticket counts as `需跟进Ticket` only when:

- the Ticket is open
- the Ticket already has at least one public agent reply
- the latest effective public reply is from the customer
- mirrored pseudo-replies from `cs@gl-inet.com`, `support@gl-inet.com`, and `support@glinet.biz` are ignored

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
  --pretty
```

## Safety

- Freshdesk API keys must be supplied through `FRESHDESK_API_KEY` or an equivalent secret manager.
- Tracked files must not contain API keys, webhooks, or live Ticket exports.
- Live output is ignored under `validation/live-output*.json` because Ticket subjects can contain customer information.
- Bulk Ticket updates are intentionally outside this repository.
