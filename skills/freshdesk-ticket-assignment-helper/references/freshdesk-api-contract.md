# Freshdesk API Contract

## Default Mode: Read-Only

The skill defaults to triage and inspection. It may use:

- `GET /api/v2/tickets`
- `GET /api/v2/search/tickets?query=[query]`
- `GET /api/v2/tickets/[id]`
- `GET /api/v2/tickets/[id]/conversations`
- `GET /api/v2/agents`
- `GET /api/v2/groups`

The triage command must not write to Freshdesk. Its JSON output includes
`safety.freshdesk_methods_used: ["GET"]` and `safety.writes_allowed: false`.

## Unassigned Triage Pool

Preferred command:

```bash
python3 scripts/freshdesk_readonly_ticket_inspector.py \
  --triage-view technical-service \
  --limit 30 \
  --pretty
```

Use `--triage-view customer-service` for the Customer Service queue.

The views mirror their morning Freshdesk queues:

- Agent is unassigned.
- `technical-service`: Group is `Technical Service`, empty, or `MX Support`.
- `customer-service`: Group is `Customer Service`.
- Status is Open (`2`) or Pending (`3`), not Resolved (`4`) or Closed (`5`).
- Exclude `spam=true`.
- Exclude Tickets tagged `Escalation` or `RMA` before fetching conversations.

Resolve Group IDs once, run one Freshdesk search per Group/status pair, dedupe by
Ticket ID, and apply the filters again locally. Fetch conversations only for the
remaining candidates. Initial triage reads attachment metadata but does not
download attachments. Requester history is limited to narrow Merge signals.

Routing uses the subject, opening `description_text`, later public customer
conversations, and attachment metadata. Automatic replies are context only.
This explicit triage mode may return full customer text for internal model
classification. Treat that JSON as sensitive transient data; user-facing output
must use only short evidence snippets and must not reproduce full messages or
customer email addresses.

## Unattended Cron Contract

`freshdesk_triage_cron.py` invokes only the existing read-only inspector for Freshdesk data. It rejects a snapshot unless `safety.freshdesk_methods_used` is exactly `["GET"]`, `safety.writes_allowed` is `false`, the view matches, and `ticket_count` matches the returned Ticket list.

The semantic classifier receives compact Ticket data in bounded batches. Its Hermes process enables only the `todo` toolset and ignores ambient project rules. The Freshdesk API key is removed from classifier and DWS child environments. Classifier output is accepted only when every snapshot Ticket appears exactly once, no unknown ID appears, every bucket is allowed for the view, and every Merge target is an API-supplied candidate.

Hermes must have a configured inference provider and model. Missing model credentials, malformed model output, or any classifier process failure stops the run before normal card delivery.

The driver sends a DWS stream card with `send-card`, then completes it with `update-card --flow-status 3`. It never retries ambiguous card creation; a known-`bizId` update may be retried. Normal destinations come from `FRESHDESK_TRIAGE_TECH_GROUP_ID` and `FRESHDESK_TRIAGE_CS_RECEIVER_ID`. Redacted failure cards use only the Technical Service group target when DWS remains available.

Same-day duplicate delivery uses a hash of date, view, and validated routing rows. Zero candidates produce no card. State and JSONL logs contain only Ticket counts, short hashes, stages, and redacted errors, never customer bodies or the Freshdesk API key.

The Cron driver contains no Freshdesk write path and cannot call the supervised assignment helper. Enabling unattended assignment requires a future explicit version and a separately reviewed contract; it must not be activated through an environment flag.

## Allowed Writes: Two Fixed Group Routes

The only write operation authorized by this skill is a selected fixed route:

- `technical-service-to-customer-service`: source `Technical Service` or empty; target `Customer Service`.
- `customer-service-to-technical-service`: source exactly `Customer Service`; target `Technical Service`.
- `PUT /api/v2/tickets/[id]` with `{"group_id": <fixed target group ID>}`.

The source and target are resolved by their exact Freshdesk Group names.
The request body must not contain `responder_id` or any other field.

Every selected Ticket must pass all preflight checks before any PUT is sent:

- source Group matches the selected fixed route;
- Agent is empty (`responder_id:null`);
- status is Open (`2`) or Pending (`3`);
- `spam` is explicitly `false`;
- neither `Escalation` nor `RMA` is present;
- Freshdesk returns the requested Ticket ID.

The script defaults to dry-run. Execution requires `--execute` and an exact,
same-order repetition of the selected IDs in `--confirm-ticket-ids`. This is an
internal CLI guard: after the user confirms the latest displayed dry-run batch,
the Agent supplies both ID arguments; the user does not need to repeat them.
A run may contain at most 20 unique positive Ticket IDs.

Immediately before each PUT, fetch that Ticket again and repeat the eligibility
checks. After each PUT, fetch it once more and count it as completed only when
the Group is the fixed target and the Agent is still empty.

Writes are sequential single-Ticket updates. Stop on the first failed or
ambiguous request, changed precondition, or failed readback. Report completed
and remaining IDs; do not claim atomicity or rollback. Freshdesk automations may
react to Group changes, so verification covers the Group and Agent fields only.

## Assignment Output Contract

The assignment script returns JSON containing:

- `mode`: `dry_run` or `execute`;
- `route`: selected fixed route name;
- `target_group`: resolved target Group ID and name;
- `request_body`: exactly the body that would be or was sent;
- `tickets[]`: preflight records and, after a write, `before` and `after` fields;
- `writes_sent`: number of PUT requests that returned normally;
- `completed[]`: only Tickets that passed post-write Group and Agent checks;
- `failed[]`: Tickets that definitely failed a precondition or verification;
- `ambiguous[]`: Tickets whose PUT or post-write readback result is uncertain;
- `success`: false for any partial, ambiguous, or verification failure;
- `unattempted_ticket_ids`: later Tickets not attempted after the first stop;
- `remaining_ticket_ids`: compatibility alias for `unattempted_ticket_ids`.

## Forbidden Operations

- Freshdesk bulk update APIs
- assigning an Agent
- writing to a Group outside the two fixed routes
- changing status, tags, subject, priority, type, custom fields, or requester
- replies, notes, forwards, merges, deletes, restores, watchers, or contacts
- automatic execution based only on model routing output

Keep live output out of Git because Ticket subjects and conversations may contain
customer information. The production CLIs accept `FRESHDESK_API_KEY` only from
the environment and must never receive it on a command line.
