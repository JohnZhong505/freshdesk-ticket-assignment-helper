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
  --triage-unassigned-view \
  --limit 30 \
  --pretty
```

This mode mirrors the morning Freshdesk view:

- Agent is unassigned.
- Group is `Technical Service`, empty, or `MX Support`.
- Status is Open (`2`) or Pending (`3`), not Resolved (`4`) or Closed (`5`).
- Exclude `spam=true`.
- Exclude Tickets tagged `Escalation` or `RMA` before fetching conversations.

Resolve Group IDs once, run one Freshdesk search per Group/status pair, dedupe by
Ticket ID, and apply the filters again locally. Fetch conversations only for the
remaining candidates. Initial triage reads attachment metadata but does not
download attachments. Requester history is limited to narrow Merge signals.

Routing uses the subject, opening `description_text`, later public customer
conversations, and attachment metadata. Automatic replies are context only.

## Allowed Write: Customer Service Group Only

The only write operation authorized by this skill is:

- `PUT /api/v2/tickets/[id]` with `{"group_id": <Customer Service group ID>}`

The target is resolved by the exact Freshdesk Group name `Customer Service`.
The request body must not contain `responder_id` or any other field.

Every selected Ticket must pass all preflight checks before any PUT is sent:

- source Group is exactly `Technical Service` or empty;
- Agent is empty (`responder_id:null`);
- status is Open (`2`) or Pending (`3`);
- `spam` is explicitly `false`;
- neither `Escalation` nor `RMA` is present;
- Freshdesk returns the requested Ticket ID.

The script defaults to dry-run. Execution requires `--execute` and an exact,
same-order repetition of the selected IDs in `--confirm-ticket-ids`. A run may
contain at most 20 unique positive Ticket IDs.

Immediately before each PUT, fetch that Ticket again and repeat the eligibility
checks. After each PUT, fetch it once more and count it as completed only when
the Group is `Customer Service` and the Agent is still empty.

Writes are sequential single-Ticket updates. Stop on the first failed or
ambiguous request, changed precondition, or failed readback. Report completed
and remaining IDs; do not claim atomicity or rollback. Freshdesk automations may
react to Group changes, so verification covers the Group and Agent fields only.

## Assignment Output Contract

The assignment script returns JSON containing:

- `mode`: `dry_run` or `execute`;
- `target_group`: resolved Customer Service ID and name;
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
- writing to any Group other than `Customer Service`
- changing status, tags, subject, priority, type, custom fields, or requester
- replies, notes, forwards, merges, deletes, restores, watchers, or contacts
- automatic execution based only on model routing output

Keep live output out of Git because Ticket subjects and conversations may contain
customer information. Never pass API keys on a command line when an environment
variable can be used.
