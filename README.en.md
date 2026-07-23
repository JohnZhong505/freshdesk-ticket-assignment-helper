# Freshdesk Ticket Assignment Helper

[中文](./README.md) | English

This repository contains two installable Codex skills for lightweight Freshdesk workload counting, ticket triage, and controlled assignment.

## Skill List

| Skill | Status | Purpose |
| --- | --- | --- |
| `freshdesk-needs-follow-up-ticket-numbers` | Completed | Lightweight read-only counter for actionable Freshdesk tickets |
| `freshdesk-ticket-assignment-helper` | Available, evolving | Read-only Technical Service or Customer Service triage, plus confirmed fixed-route Group assignment |

## Recommended Skill

The current stable skill is `freshdesk-needs-follow-up-ticket-numbers`.

- Latest version: `v1.7.1`
- Updated on: `2026-07-22`
- Assignment helper version: `v2.2.2` (`2026-07-23`)
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
- `skills/freshdesk-ticket-assignment-helper`

Local installer:

```bash
./install-skill.sh --skill freshdesk-needs-follow-up-ticket-numbers
./install-skill.sh --skill freshdesk-ticket-assignment-helper
```

## Required Before Running

- `FRESHDESK_DOMAIN`
- `FRESHDESK_API_KEY`
- Python 3
- Network access to the Freshdesk API

Unattended card mode additionally requires a configured Hermes inference provider/model, DWS CLI `v1.0.52` or later, and valid DWS authentication. Targets are fixed in the Cron driver and cannot be overridden through environment variables: Technical Service and failure cards go to the DingTalk group named exactly `测试`, while Customer Service cards go directly to Amber (Customer Service). Cron never searches for a group or contact at runtime.

Hermes cron filters API-key environment variables, so provide the Freshdesk domain and API key through a permission-restricted `~/.config/freshdesk-ticket-assignment-helper/credentials.json`. Never commit that file or live customer data.

Freshdesk API key help:
[How To Find Your API Key](https://support.freshdesk.com/support/solutions/articles/215517-how-to-find-your-api-key)

## Metrics

- `Need Follow Up` = `New + Customer Responded`
- `Customer Responded` = customer replied most recently and there is no newer public agent reply; suspicious candidates within five minutes are checked against the latest public email sender
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
| Cache retention | Keeps entries seen within the last 30 days by default, supports legacy cache files, and allows `--cache-retention-days` overrides |
| Cache visibility | Shows cache hit rate and hit count in the default table output, for example `90% (220/250)` |
| Conversations scan | Avoids full scans and only rechecks conversations when needed |
| Customer Responded correction | Rechecks only suspicious candidates within five minutes and excludes the latest public email when its normalized `from_email` is an approved internal support sender |
| Default output | Shows a human-readable table directly in chat |
| Table simplification | Focuses on group name and per-agent actionable counts |
| Quick aliases | Supports business aliases such as Technical Service, CS, Shenzhen team, and Mexico team |
| README | Provides a Chinese main page plus a clear English entry point |
| FR false-positive fix | Excludes outbound-only tickets from real `FR overdue` workload |
| Agent name display | Tries to show real names instead of `Agent <id>` |
| Connection reliability | Retries transient failures including remote-end-closed cases |
| Rate-limit buffering | Adds a light default request delay to reduce burst pressure on Freshdesk |
| Run metadata | Reports elapsed run time and completion time in the running device's local timezone; version and JSON usage stay in `SKILL.md` instead of every table output |
| Runtime resilience | Extends SSL / EOF / IncompleteRead / 5xx retries, uses atomic cache writes, and checkpoints cache during long runs |

## Best Use Cases

- quick agent workload snapshots
- shift handoff and duty review
- lightweight Hermes / Codex / scheduled runs
- grouped triage suggestions for unresolved unassigned Tickets
- supervised fixed-route Group assignment between Technical Service and Customer Service
- scheduled dual-view triage cards on a separately configured Hermes host; repository code and tests do not prove that a cron job is deployed or running

## Assignment Helper

Read-only triage remains the default. Use one of two explicit views:

```bash
python3 skills/freshdesk-ticket-assignment-helper/scripts/freshdesk_readonly_ticket_inspector.py \
  --triage-view technical-service \
  --pretty
```

Replace the view with `customer-service` for the unassigned Customer Service pool. In that view, every technical issue routes to Technical Service; it does not distinguish Technical Support. Same-requester fragments within 30 minutes can match by empty subject, normalized subject, or identical normalized opening body; only later Tickets may target earlier Merge candidates. Ticket links always display their numeric IDs.

The Technical Service view excludes MX Support by default. Add `--include-mx-support` only for an explicit manual run that should include it.

Before the first interactive Technical Service run in a conversation, the skill asks whether MX Support should be included unless the user already specified the scope. Unattended Cron never asks and always uses the default pool without MX Support.

To preview selected Tickets without writing:

```bash
python3 skills/freshdesk-ticket-assignment-helper/scripts/freshdesk_assign_cs_group.py \
  --route technical-service-to-customer-service \
  --ticket-ids "136100,136101" \
  --pretty
```

Execution additionally requires `--execute` and an exact repetition of the IDs
in `--confirm-ticket-ids`; this is an internal CLI guard. In Codex, the user can
confirm the latest successful preview with a plain confirmation and does not
need to repeat the IDs. The action accepts only Open/Pending, non-spam,
unassigned Tickets from the selected fixed source Group, skips Escalation and
RMA tags, writes only `group_id`, and verifies that Agent remains empty. Use
`--route customer-service-to-technical-service` for technical Tickets in the
Customer Service view.

Each triage response reports identified and protected-tag-skipped counts, groups
Tickets by destination, then reports CS-eligible IDs and asks whether to enter
the supervised one-click assignment flow.

### Unattended Card Mode (v2.2.2)

`freshdesk_triage_cron.py` keeps scriptable work in a deterministic flow: it invokes the GET-only inspector, validates classifier JSON, applies view-specific ordering, renders a DWS streaming card, deduplicates unchanged same-day results, and writes redacted logs. The outer Hermes cron uses `--no-agent --script`; the inner turn uses `hermes chat -q --ignore-rules --quiet` with no inherited history or project context for the current Ticket batch. It receives only the `todo` toolset and cannot use the shell, files, browser, Computer Use, DWS, or Freshdesk tools. Classification sessions use dedicated source labels and are soft-archived after the run.

Technical Service cards use `CS -> Spam -> Sales -> Technical Support -> Merge -> Manual Review -> retained Technical Service`. Customer Service cards use `Technical Service -> Sales -> Spam -> Merge -> Manual Review -> retained Customer Service`. Long results are fully split under the byte limit with completed-part checkpoints. Empty and unchanged same-day results send no DingTalk card, while no-agent stdout emits a redacted JSON heartbeat so Hermes does not report `SILENT`; changed results may send again.

The cron path is always read-only in Freshdesk and never imports or invokes the assignment script. Thin wrappers retry only side-effect-free transient failures in fetch, classify, and DWS preflight, up to three attempts with 60- and 120-second delays; send failures are never retried. Each view has separate state and an OS-backed lock, so a long live run cannot be displaced by an elapsed-time guess. Failure cards go only to the fixed Technical Service group target. Bidirectional assignment remains an interactive dry-run-and-confirm workflow; Spam, Sales, Technical Support, and Merge remain suggestions only.

Interactive DingTalk delivery uses `freshdesk_send_triage_cards.py`: preview is the default, and `--send` is allowed only when the current user request authorizes the unchanged preview. It reuses the same validation, ordering, numeric Ticket links, splitting, and partial-send resume logic. The Customer Service view is fixed to Amber and the Technical Service view to the `测试` group; recipient overrides and runtime lookup are unavailable.

### Assignment Helper Improvements

| Area | Improvement |
| --- | --- |
| Dual-view triage and Merge | Supports both unassigned Group pools, uses role-specific routing, and lets only later same-requester fragments within 30 minutes target earlier Merge candidates when subjects or opening bodies match |
| Chinese evidence output | Requires every evidence cell to contain a concise Simplified Chinese paraphrase while allowing necessary English product names, errors, or keywords |
| Supervised assignment | Allows only the fixed TS-to-CS and CS-to-TS routes, writes only `group_id`, and verifies the destination Group and empty Agent after each update |
| Cron and card notifications | Uses a no-agent outer runner and context-free restricted classifier, fixed targets with no runtime lookup, per-view state and locking, side-effect-safe retries, session archiving, success heartbeats, complete split cards with resume, same-day deduplication, redacted failure reporting, and fail-closed validation |
| Interactive DingTalk delivery | Uses one preview-first fixed-target script that reuses Cron rendering and link validation; Customer Service goes only to Amber and Technical Service only to the `测试` group |

## Safety Boundary

- Freshdesk `GET` only by default
- unattended cron reads Freshdesk and sends suggestion cards only; it never assigns Tickets
- the only writes are confirmed moves across the two fixed Technical Service/Customer Service routes
- no Agent assignment, replies, notes, contact edits, or bulk writes
- production CLIs read the API key only from `FRESHDESK_API_KEY`, never from a command-line argument
- full customer text may be processed internally for explicit triage, but user-facing output contains only short evidence; do not commit API keys, webhooks, or live customer data

## Version History

### `freshdesk-needs-follow-up-ticket-numbers`

| Version | Date | Update |
| --- | --- | --- |
| v1.7.1 | 2026-07-22 | Declared the version in `SKILL.md`; table and JSON output report elapsed run time and completion time in the device's local timezone; cache format and metric rules are unchanged |
| v1.7 | 2026-07-15 | Added a five-minute Customer Responded sender recheck, paginated latest-public-conversation selection, cached sender results, and recheck metrics |
| v1.6 | 2026-07-15 | Added `last_seen_at` and a default 30-day cache retention period; supports legacy cache files; reports retention and pruned entries in JSON; preserves atomic writes and checkpoints |
| v1.5 | 2026-07-10 | Fixed Python 3.9 UTC compatibility; expanded transient error retries; added atomic cache writes and cache checkpoints; displays cache hit rate by default |
| v1.4 | 2026-07-02 | Added transient connection retries and a light default request delay for better Hermes reliability |
| v1.3 | 2026-07-01 | Improved agent name display to prefer real names over raw IDs |
| v1.2 | 2026-07-01 | Fixed false-positive `FR overdue` counts for outbound-only tickets |
| v1.1 | 2026-07-01 | Added business aliases for group bundles |
| v1.0 | 2026-06-30 | Added group selection, default table output, core counting logic, and local cache |

### `freshdesk-ticket-assignment-helper`

| Version | Date | Update |
| --- | --- | --- |
| v2.2.2 | 2026-07-23 | Fixed DWS `/usr/bin/env node` lookup in minimal macOS cron/SSH environments by prepending only the fixed DWS executable directory to DWS child-process PATH; Hermes configuration remains unchanged |
| v2.2.1 | 2026-07-23 | Fixed evidence cells to concise Simplified Chinese paraphrases while allowing necessary English product names, errors, and keywords; English-only evidence now fails closed and triggers reclassification |
| v2.2 | 2026-07-23 | Fixed successful no-agent runs being reported as `SILENT`; added earlier-ticket Merge candidates for same-sender identical-body fragments within 30 minutes; preserved complete results through card splitting; added preview-first fixed-target interactive DingTalk delivery with partial-send resume, plus 5xx retries and stronger fail-closed checks |
| v2.1 | 2026-07-22 | Merged v2.0.1 with the Hermes hardening branch: moved classification to context-free chat sessions with automatic archiving; added selective retries, per-view state isolation, and cross-platform OS locking; fixed delivery targets without runtime lookup; strengthened classifier JSON and project-verifier fail-closed checks |
| v2.0.1 | 2026-07-22 | Fixed Cron delivery to the exact `测试` group and Amber; excluded MX Support from the default Technical Service view while retaining an explicit opt-in flag |
| v2.0 | 2026-07-21 | Added unattended dual-view card runs with restricted Hermes classification, fixed view ordering, deployment-only DWS targets, same-day deduplication, redacted failure cards, and fail-closed validation; interactive bidirectional assignment remains available and cron never writes Freshdesk |
| v1.6 | 2026-07-21 | Added Customer Service triage, fixed-route assignment to Technical Service, deterministic numeric Ticket links, and 30-minute same-requester fragment Merge detection |
| v1.5 | 2026-07-21 | Added plain confirmation for the current CS dry-run batch, environment-only API-key input, the Freshdesk ten-page search boundary and truncation signal, and an explicit customer-text privacy boundary |
| v1.4.1 | 2026-07-17 | Standardized triage summaries with identified, skipped, CS-eligible counts and a one-click assignment confirmation prompt |
| v1.4 | 2026-07-16 | Renamed the skill and added confirmed, sequential Customer Service Group assignment with preflight and readback verification; read-only triage remains the default |
| v1.3 | 2026-07-16 | Added clickable Ticket IDs and refined routing rules for Technical Service and link-based Spam |
| v1.2 | 2026-07-15 | Added real-case routing rules, protected-tag skips, attachment metadata, narrow Merge checks, and grouped output |
| v1.1 | 2026-07-14 | Added unresolved unassigned triage and conversation retrieval |
| v1.0 | 2026-06-24 | Added read-only Ticket, Agent, and Group inspection |
