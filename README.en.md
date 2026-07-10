# Freshdesk Ticket Assignment Helper

[中文](./README.md) | English

This repository contains two installable Codex skills for lightweight Freshdesk workload counting and broader read-only ticket inspection.

## Skill List

| Skill | Status | Purpose |
| --- | --- | --- |
| `freshdesk-needs-follow-up-ticket-numbers` | Completed | Lightweight read-only counter for actionable Freshdesk tickets |
| `freshdesk-readonly-ticket-inspector` | In Progress | Broader Freshdesk inspection and assisted analysis skill |

## Recommended Skill

The current stable skill is `freshdesk-needs-follow-up-ticket-numbers`.

- Latest version: `v1.5`
- Updated on: `2026-07-10`
- Repository: [JohnZhong505/freshdesk-ticket-assignment-helper](https://github.com/JohnZhong505/freshdesk-ticket-assignment-helper)

## Install

For first-time Codex users, send this directly in chat:

```text
Help me install this skill from GitHub:
https://github.com/JohnZhong505/freshdesk-ticket-assignment-helper
Skill path: skills/freshdesk-needs-follow-up-ticket-numbers
```

Available install paths:

- `skills/freshdesk-needs-follow-up-ticket-numbers`
- `skills/freshdesk-readonly-ticket-inspector`

Local installer:

```bash
./install-skill.sh --skill freshdesk-needs-follow-up-ticket-numbers
./install-skill.sh --skill freshdesk-readonly-ticket-inspector
```

## Required Before Running

- `FRESHDESK_DOMAIN`
- `FRESHDESK_API_KEY`
- Python 3
- Network access to the Freshdesk API

Freshdesk API key help:
[How To Find Your API Key](https://support.freshdesk.com/support/solutions/articles/215517-how-to-find-your-api-key)

## Metrics

- `Need Follow Up` = `New + Customer Responded`
- `Customer Responded` = customer replied most recently and there is no newer public agent reply
- `New` = customer-created ticket with no public agent reply yet
- `FR overdue` = first response overdue
- `Resolution overdue` = resolution overdue

Default table column order:

1. `Need Follow Up`
2. `Customer Responded`
3. `New`
4. `FR overdue`
5. `Resolution overdue`

## Built-in Aliases

- `技术客服` / `技术客服组` / `技术客服的数据` => `Technical Service`
- `CS客服` / `CS客服组` / `CS客服的数据` => `Customer Service` + `Amazon`
- `深圳团队` => `Technical Service` + `Technical Support` + `Customer Service` + `Amazon`
- `墨西哥团队` => `MX Support`

## Key Improvements

| Improvement | Details |
| --- | --- |
| Scan scope | Only scans selected groups instead of every agent in the account |
| Group selection | Lists groups first, then runs only after explicit selection |
| Deactivated accounts | Excludes deactivated agents from active scan scope |
| Small cache | Reduces repeated requests and speeds up repeated runs |
| Cache visibility | Shows cache hit rate and hit count in the default table output, for example `90% (220/250)` |
| Conversations scan | Avoids full scans and only rechecks conversations when needed |
| Default output | Shows a human-readable table directly in chat |
| Table simplification | Focuses on group name and per-agent actionable counts |
| Quick aliases | Supports business aliases such as Technical Service, CS, Shenzhen team, and Mexico team |
| README | Provides a Chinese main page plus a clear English entry point |
| FR false-positive fix | Excludes outbound-only tickets from real `FR overdue` workload |
| Agent name display | Tries to show real names instead of `Agent <id>` |
| Connection reliability | Retries transient failures including remote-end-closed cases |
| Rate-limit buffering | Adds a light default request delay to reduce burst pressure on Freshdesk |
| Runtime resilience | Extends SSL / EOF / IncompleteRead / 5xx retries, uses atomic cache writes, and checkpoints cache during long runs |

## Best Use Cases

- quick agent workload snapshots
- shift handoff and duty review
- lightweight Hermes / Codex / scheduled runs

## Version History

| Version | Date | Update |
| --- | --- | --- |
| v1.5 | 2026-07-10 | Fixed Python 3.9 UTC compatibility; expanded transient error retries; added atomic cache writes and cache checkpoints; displays cache hit rate by default |
| v1.4 | 2026-07-02 | Added transient connection retries and a light default request delay for better Hermes reliability |
| v1.3 | 2026-07-01 | Improved agent name display to prefer real names over raw IDs |
| v1.2 | 2026-07-01 | Fixed false-positive `FR overdue` counts for outbound-only tickets |
| v1.1 | 2026-07-01 | Added business aliases for group bundles |
| v1.0 | 2026-06-30 | Added group selection, default table output, core counting logic, and local cache |

## Safety Boundary

- Freshdesk `GET` only by default
- no replies, assignments, notes, contact edits, or bulk writes
- do not commit API keys, webhooks, or live customer data
