---
name: freshdesk-ticket-assignment-helper
description: Use when inspecting, triaging, or safely assigning unresolved unassigned Freshdesk Tickets from the Technical Service or Customer Service queues.
---

# Freshdesk Ticket Assignment Helper

## Overview

Use this skill for Freshdesk morning triage and controlled Ticket routing. It remains read-only by default. Its only write capability changes the Group for explicitly selected eligible Tickets between `Technical Service` and `Customer Service`, while leaving the Agent unassigned.

This skill does not compute `需跟进Ticket` workload; use `freshdesk-needs-follow-up-ticket-numbers` for that.

## Read-Only Triage

Run:

```bash
python3 scripts/freshdesk_readonly_ticket_inspector.py \
  --triage-view technical-service \
  --pretty
```

Available views:

- `technical-service`: Agent `Unassigned`; Groups `Technical Service` and UI pseudo-group `Unassigned`. Add `--include-mx-support` only when the user explicitly asks to include `MX Support`.
- `customer-service`: Agent `Unassigned`; Group `Customer Service`.

Before the first interactive `technical-service` run in a conversation, if the user has not already specified the MX scope, ask: `本次是否包含 MX Support？` Recommend excluding it. Do not start that first run until the user answers. Reuse the answer for later Technical Service runs in the same conversation unless the user changes it. This question does not apply to unattended Cron: Cron always uses the default pool without MX Support.

Optional Technical Service run with MX Support:

```bash
python3 scripts/freshdesk_readonly_ticket_inspector.py \
  --triage-view technical-service \
  --include-mx-support \
  --pretty
```

Both triage pools use:

- Status: `All unresolved`; include `Open` and `Pending`, exclude `Resolved` and `Closed`
- Exclude `spam=true`
- Skip Tickets tagged `Escalation` or `RMA`

Triage views always read every available Search API page and return the complete matching pool. `--limit` applies only to general inspection. Completeness is checked by unique Ticket ID; a missing total, repeated moving-view mismatch, or single query above the API's 300-ticket cap fails closed. Unattended DingTalk output is split into numbered cards when needed; successful parts are checkpointed so a later run resumes without duplicating completed parts.

Before suggesting routes, read `references/triage-routing-rules.md`. Use `subject`, the opening customer message, later public customer conversations, attachment metadata, and narrow Merge metadata. Automatic replies are context only. Explicit triage may process full customer text internally, but every user-facing evidence cell must be a short Simplified Chinese paraphrase; retain English product names or error keywords only when useful. Do not download attachments during initial triage.

Group the answer by routing destination. Copy each API-provided `ticket_link_markdown` value verbatim; never load a page title or display `Loading...`. Do not mix destinations in one table.

## Triage Response Contract

Every triage response must use this order:

1. Start with: `本次识别 **N 张候选 Ticket**，另有 **M 张 Escalation/RMA Ticket 已跳过**。全程仅使用 Freshdesk GET，没有执行改派。` Use `ticket_count` for N and `excluded_tag_ticket_count` for M.
2. Output separate Markdown tables for each non-empty routing destination.
3. For `technical-service`, count `CS` candidates whose current Group is `Technical Service` or empty. For `customer-service`, count `Technical Service` candidates whose current Group is exactly `Customer Service`. This count is advisory; the assignment helper must still run its live preflight.
4. If the count is greater than zero, state the current view, candidate count, linked IDs, target Group, and ask whether to assign them. After the dry-run preview, the user may reply `确认`; they do not need to repeat the Ticket IDs.
5. If the count is zero, state that the current view has 0 eligible one-click assignment candidates.

Use these table orders:

- `technical-service`: `CS`, `Spam`, `Sales`, `Technical Support`, `Merge`, `Manual Review`, then retained `Technical Service`.
- `customer-service`: `Technical Service`, `Sales`, `Spam`, `Merge`, `Manual Review`, then retained `Customer Service`.

## Unattended Cron Cards (v2.2.1)

Use `scripts/freshdesk_triage_cron.py` for unattended Hermes runs. The outer Hermes job must use `--no-agent --script`. The driver invokes an isolated nested `hermes chat -q --ignore-rules --quiet` only for semantic classification with the `todo` toolset; Ticket text is untrusted data and the classifier has no terminal, file, browser, Computer Use, DWS, or Freshdesk tools. It tags nested sessions with source `freshdesk-triage-tech` or `freshdesk-triage-cs` and, after every started classification run, soft-archives all sessions carrying that exact allowlisted source. Archived sessions remain searchable and recoverable but are hidden from normal Desktop/session listings. Because one-shot chat sessions may exit without `ended_at`, `scripts/archive_hermes_sessions.py` runs under the Hermes runtime Python and calls the official `SessionDB.set_session_archived()` API instead of the bulk archive CLI. Cleanup failure is logged as `session_archive_failed` and does not override the primary triage result.

The driver performs GET-only collection, Agent JSON validation, view-specific sorting, table rendering, DWS delivery, retry, OS-backed per-view locking, redacted logging, and same-day result fingerprinting. The lock is released by the operating system if the process exits, so a long-running live task is never displaced by a time-based stale-lock guess. Missing, duplicate, extra, malformed, or forbidden classifications fail closed before a normal card is sent. It returns exit `75` (`EX_TEMPFAIL`) only when the side-effect-free `fetch`, `classify`, or `dws-preflight` stage fails. Startup/configuration and `send` failures return exit `1`. The wrappers retry only exit `75`, at most three attempts, with deterministic delays of 60 and 120 seconds by default; set `FRESHDESK_TRIAGE_RETRY_BASE_DELAY_SECONDS` to a finite non-negative number to change the base delay (use `0` only in tests). Intermediate attempts suppress failure cards only for retryable failures. A non-retryable failure ignores that suppression and immediately attempts one failure card because the wrapper stops; after three retryable failures, only the final attempt is notification-eligible.

Fixed recipients embedded in the Cron driver:

- `technical-service`: the DingTalk group whose exact title is `测试`, with fixed `openConversationId` `cidOXHoLP3FMfLpv2jif+iWPQ==`.
- `customer-service`: Amber (黄轩, CS客服) in a direct message, with fixed `openDingTalkId` `DesWciiDKviS2g4tfIxy7uH14hiPX2oeF9Jl`.
- Failure cards: the `测试` group only, never Amber.

Normal cards contain only non-empty routing-suggestion tables in the order above. They do not contain assignment prompts. Complete results are split into numbered cards under the byte limit, and completed parts are checkpointed for resume after a partial send. A zero-Ticket or unchanged duplicate result sends no DingTalk card, but every successful no-agent path prints a small redacted JSON heartbeat so Hermes does not classify the run as `SILENT`. A changed result may be sent again on the same day.

Cron is always read-only toward Freshdesk. It never imports the assignment helper or exposes unattended assignment. The supervised bidirectional assignment flow below remains available only in an interactive conversation after dry-run and user confirmation.

## Interactive DingTalk Delivery

Use `scripts/freshdesk_send_triage_cards.py` when the user asks to send the current interactive triage tables to DingTalk. Do not compose an ad-hoc `dws chat` command. The script accepts one redacted JSON object from `--input` or stdin containing `snapshot` and `classification`; keep only Ticket IDs, API-provided Ticket links, Merge candidates, buckets, confidence, concise reason, and concise evidence. Do not include customer email addresses or full message bodies, and delete any transient delivery file after the request is complete.

Run preview first:

```bash
python3 scripts/freshdesk_send_triage_cards.py --view customer-service --input delivery.json
```

The default performs validation and renders all cards without contacting DWS. It verifies the complete Ticket set, view-specific buckets and order, API-provided numeric links, allowed Merge targets, and card byte limits. Empty input returns `status: empty` and does not contact DWS.

Use `--send` only when the current user request explicitly authorizes sending the unchanged preview to that view's fixed target. The user does not need to repeat the target ID. A partial multi-card send is checkpointed and a rerun resumes at the first unsent part.

```bash
python3 scripts/freshdesk_send_triage_cards.py --view customer-service --input delivery.json --send
```

The only targets are constants shared with Cron: `customer-service` sends to Amber and `technical-service` sends to the `测试` group. The CLI accepts no recipient ID or search argument. Interactive delivery sends only DingTalk suggestion cards; it does not call Freshdesk or authorize Group assignment.

For unattended runs, store Freshdesk credentials at `~/.config/freshdesk-ticket-assignment-helper/credentials.json`, set mode `0600` on macOS, and never commit it. The driver explicitly removes `FRESHDESK_API_KEY` from the nested classifier, session archiver, and DWS subprocess environments:

```json
{
  "domain": "example.freshdesk.com",
  "api_key": "YOUR_API_KEY"
}
```

Hermes must have a working inference provider and model because the nested isolated chat performs semantic classification. The validated wrappers default `HERMES_BIN` to `~/.hermes/scripts/hermes-opencode-go-mimo-v2.5-pro` and `DWS_BIN` to `~/.local/bin/dws`; a configured path must exist or the run fails closed. DWS v1.0.52 or newer and a valid `dws auth status -f json` are also required. If headless macOS cannot use the Keychain-backed DWS credential, run the migration dry-run before applying it:

```bash
env -u DWS_DISABLE_KEYCHAIN dws auth migrate-keychain --to file-dek --dry-run --format json
env -u DWS_DISABLE_KEYCHAIN dws auth migrate-keychain --to file-dek --yes --format json
```

Copy the two thin wrappers to `~/.hermes/scripts/`. These are weekday 09:00 examples; choose the production schedules during deployment:

```bash
hermes cron create "0 9 * * 1-5" --name freshdesk-triage-technical-service --script hermes_cron_technical_service.py --no-agent --deliver local
hermes cron create "0 9 * * 1-5" --name freshdesk-triage-customer-service --script hermes_cron_customer_service.py --no-agent --deliver local
```

The wrappers safely load only `HERMES_BIN` and `DWS_BIN` from `~/.hermes/.env` without shell evaluation; already-exported values take precedence. DingTalk targets are constants in the driver and cannot be overridden by environment variables. The wrappers locate the single installed driver under `~/.hermes/skills`, `~/.codex/skills`, or `~/.agents/skills`. Set `FRESHDESK_TRIAGE_SKILL_DIR` only when the skill is installed elsewhere.

## Controlled Group Assignment

Use this only after the user reviews the relevant read-only table and asks to assign its displayed candidates. The user may select individual Ticket IDs or refer to the whole displayed batch.

### Eligibility

Every selected Ticket must still satisfy all shared conditions:

- Agent is empty (`responder_id=null`).
- Status is `Open` or `Pending`.
- Ticket is not Spam.
- Ticket has neither `Escalation` nor `RMA` tag.
- `technical-service-to-customer-service`: source Group is `Technical Service` or empty; target resolves exactly to `Customer Service`.
- `customer-service-to-technical-service`: source Group is exactly `Customer Service`; target resolves exactly to `Technical Service`.

The helper never accepts a target Group or Agent argument. Its PUT body contains only `group_id`; it does not write `responder_id`.

### 1. Preview

Always run dry-run first:

```bash
python3 scripts/freshdesk_assign_cs_group.py \
  --route technical-service-to-customer-service \
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
  --route technical-service-to-customer-service \
  --ticket-ids "136100,136101" \
  --execute \
  --confirm-ticket-ids "136100,136101" \
  --pretty
```

For the Customer Service view, use `--route customer-service-to-technical-service`. The helper rechecks each Ticket immediately before its PUT, sends one `PUT /api/v2/tickets/[id]` with only the fixed route's target `group_id`, then re-reads the Ticket. Success requires the target Group and an empty Agent in the readback.

If a write or verification fails, stop immediately. Report completed, failed/ambiguous, and unattempted Ticket IDs. Never claim atomic behavior and never auto-rollback.

## Safety Rules

- Default to read-only mode. Never add `--execute` without the user's current explicit confirmation.
- A dry-run is not an authorization token. Never reuse old approval or run execute mode from Hermes, cron, or another unattended flow.
- Do not use Freshdesk bulk update for this flow.
- Do not assign Agents, clear an assigned Agent, change status, add tags, reply, note, merge, or modify contacts.
- Do not write Tickets from `MX Support` or any Group outside the selected fixed route.
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
- `scripts/freshdesk_assign_cs_group.py`: guarded selected-Ticket assignment across the two fixed Group routes; dry-run by default.
- `scripts/freshdesk_triage_cron.py`: unattended validation, ordering, idempotency, and DWS cards.
- `scripts/freshdesk_send_triage_cards.py`: preview-first interactive delivery to the fixed DingTalk target for each view.
- `scripts/hermes_cron_technical_service.py`: fixed Technical Service no-agent wrapper.
- `scripts/hermes_cron_customer_service.py`: fixed Customer Service no-agent wrapper.
- `references/freshdesk-api-contract.md`: API, precondition, failure, and output contract.
- `references/triage-routing-rules.md`: routing rules and confirmed examples.
- `references/hermes-cron-prompt.md`: prompt-injection boundary and exact Agent JSON contract.
