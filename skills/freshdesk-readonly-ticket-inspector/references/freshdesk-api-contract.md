# Freshdesk API Contract

## Read-Only Endpoints

- `GET /api/v2/tickets`
- `GET /api/v2/search/tickets?query=[query]`
- `GET /api/v2/tickets/[id]/conversations`
- `GET /api/v2/agents`
- `GET /api/v2/groups`

## Supervised Write Endpoint

- `PUT /api/v2/tickets/[id]`

Use only for a single user-confirmed Ticket. The assignment fields are:

- `responder_id`: Agent ID assigned to the Ticket.
- `group_id`: Group ID assigned to the Ticket.

## Forbidden Without New Explicit User Approval

- Bulk updates: `POST /api/v2/tickets/bulk_update`
- Replies and notes
- Deletes, merges, restores, forwards, watcher changes, or contact changes
- Any automatic multi-Ticket assignment run

## Read Output Contract

The read-only inspector returns JSON with:

- `ticket_count`: number of ticket records returned in this run.
- `freshdesk_total`: Freshdesk search total when search is used; otherwise `null`.
- `agent_count`: number of agent records available for ID-to-name resolution.
- `group_count`: number of group records available for ID-to-name resolution.
- `tickets[]`: ticket records with `ticket_id`, `subject`, `responder_id`, `agent_name`, `group_id`, and `group_name`.
- `public_conversations[]`: public conversation rows for triage mode, with `body_text`, `incoming`, `source`, and `use_for_triage`.
- `triage_text`: joined public customer text that should drive routing decisions in triage mode.
- `safety.freshdesk_methods_used`: must be `["GET"]`.
- `safety.writes_allowed`: must be `false`.

## Unassigned Triage Pool

Preferred command:

```bash
python3 scripts/freshdesk_readonly_ticket_inspector.py \
  --triage-unassigned-view \
  --limit 30 \
  --pretty
```

This read-only mode mirrors the morning Freshdesk view:

- Agent is unassigned.
- Group is one of `Technical Service`, `Unassigned`, or `MX Support`.
- Status is `All unresolved`; include status `2` Open and `3` Pending, exclude status `4` Resolved and `5` Closed.
- Exclude `spam=true`.

Implementation:

- Resolve group IDs once with `GET /api/v2/groups`.
- Run one Freshdesk search per target group/status pair: `group_id:<id> AND agent_id:null AND status:<2-or-3>`.
- Dedupe by Ticket ID and apply local guards for unresolved, unassigned, selected group, and non-spam.
- Fetch conversations only for the resulting candidate Tickets with `GET /api/v2/tickets/[id]/conversations`.

For routing, use Ticket `subject` plus public conversation rows where `use_for_triage=true`. Do not rely on Ticket `description` or `description_text` for new Tickets because those fields are usually not human-filled yet. Public rows where `use_for_triage=false` are context only and may include automatic replies.

Keep live output out of Git by default because Ticket subjects and conversation text can contain customer information.
