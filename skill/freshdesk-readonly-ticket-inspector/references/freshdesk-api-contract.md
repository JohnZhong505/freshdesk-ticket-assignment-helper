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
- `tickets[]`: ticket records with `ticket_id`, `subject`, `responder_id`, `agent_name`, `group_id`, and `group_name`.
- `safety.freshdesk_methods_used`: must be `["GET"]`.
- `safety.writes_allowed`: must be `false`.

Keep live output out of Git by default because Ticket subjects can contain customer information.
