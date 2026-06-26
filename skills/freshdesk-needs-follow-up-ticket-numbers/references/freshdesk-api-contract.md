# Freshdesk Needs Follow Up Ticket Numbers API Contract

## Read-Only Endpoints

- `GET /api/v2/search/tickets?query=[query]`
- `GET /api/v2/tickets/[id]/conversations`
- `GET /api/v2/agents`
- `GET /api/v2/groups`

## Output Contract

The lightweight skill returns JSON with:

- `metric_name`: always `needs_follow_up_ticket`
- `metric_display_name`: always `需跟进Ticket`
- `group_id`
- `group_name`
- `ticket_count`
- `summary_by_agent[]`: grouped rows with `responder_id`, `agent_name`, `ticket_count`, and `ticket_ids`
- `safety.freshdesk_methods_used`: must be `["GET"]`
- `safety.writes_allowed`: must be `false`

## Metric Definition

A Ticket counts only when:

- it is open
- it already has at least one public agent reply
- the latest effective public reply is from the customer
- mirrored pseudo-replies from `cs@gl-inet.com`, `support@gl-inet.com`, and `support@glinet.biz` are ignored
