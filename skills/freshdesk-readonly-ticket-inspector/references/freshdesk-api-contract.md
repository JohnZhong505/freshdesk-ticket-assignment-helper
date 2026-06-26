# Freshdesk API Contract

## Read-Only Endpoints

- `GET /api/v2/tickets`
- `GET /api/v2/search/tickets?query=[query]`
- `GET /api/v2/agents`
- `GET /api/v2/groups`

## Supervised Write Endpoint

- `PUT /api/v2/tickets/[id]`

Use only for a single user-confirmed Ticket. The assignment fields are:

- `responder_id`: Agent ID assigned to the Ticket.
- `group_id`: Group ID assigned to the Ticket.

Example request body:

```json
{
  "responder_id": 123456789,
  "group_id": 987654321
}
```

## Forbidden Without New Explicit User Approval

- Bulk updates: `POST /api/v2/tickets/bulk_update`
- Replies and notes
- Deletes, merges, restores, forwards, watcher changes, or contact changes
- Any automatic multi-Ticket assignment run

## Read Output Contract

The read-only inspector returns JSON with:

- `ticket_count`: number of ticket records returned in this run.
- `freshdesk_total`: Freshdesk search total when `--query` is used; otherwise `null`.
- `agent_count`: number of agent records available for ID-to-name resolution.
- `group_count`: number of group records available for ID-to-name resolution.
- `metric_name`: `needs_follow_up_ticket` when the run is computing the staffing follow-up metric.
- `metric_display_name`: `需跟进Ticket` when the run is computing the staffing follow-up metric.
- `tickets[]`: ticket records with `ticket_id`, `subject`, `responder_id`, `agent_name`, `group_id`, and `group_name`.
- `summary_by_agent[]`: grouped rows with `responder_id`, `agent_name`, `ticket_count`, and `ticket_ids` when the grouped workload mode is used.
- `safety.freshdesk_methods_used`: must be `["GET"]`.
- `safety.writes_allowed`: must be `false`.

## Staffing Follow-Up Metric

Preferred shortcut command:

```bash
python3 scripts/freshdesk_readonly_ticket_inspector.py \
  --group-name "Technical Service" \
  --needs-follow-up-ticket-summary \
  --pretty
```

Meaning of `需跟进Ticket`:

- Ticket is open.
- The Ticket already has at least one public agent reply.
- The latest effective public reply is from the customer.
- Ignore mirrored pseudo-replies where Freshdesk marks `incoming=true` but the sender is one of your own support mailboxes, including `cs@gl-inet.com`, `support@gl-inet.com`, and `support@glinet.biz`.

Keep live output out of Git by default because Ticket subjects can contain customer information.
