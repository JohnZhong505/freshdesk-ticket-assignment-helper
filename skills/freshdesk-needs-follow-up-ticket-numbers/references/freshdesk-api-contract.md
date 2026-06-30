# Freshdesk Needs Follow Up Ticket Numbers API Contract

## Read-Only Endpoints

- `GET /api/v2/groups`
- `GET /api/v2/admin/groups/[group_id]/agents`
- `GET /api/v2/search/tickets?query=[query]`
- `GET /api/v2/tickets/[id]?include=stats`

## Search Pagination Constraint

- Freshdesk search pagination is capped at page `10`.
- A plain query like `group_id:<id> AND status:2` can therefore underfetch when one group's open Ticket pool exceeds that limit.
- This skill now tries one direct group-level open-ticket search first.
- Only when `total > 300` does it fall back to group-agent-scoped searches inside the selected group.

## Group Selection Contract

- Human-in-the-loop runs should list groups first, then require an explicit group selection.
- Automation runs must pass `--group-id` or `--group-name`. The script must not silently default to one group.
- Group-agent fallback is limited to the selected group. It does not enumerate every agent in the account.
- The skill also supports built-in alias bundles:
  - `技术客服的数据` => `Technical Service`
  - `技术客服组` => `Technical Service`
  - `CS客服组` => `Customer Service` + `Amazon`
  - `CS客服的数据` => `Customer Service` + `Amazon`

## Cache Contract

- The skill may store a local JSON cache keyed by `ticket_id`.
- Cache re-use is allowed only when the current Ticket `updated_at`, `status`, `group_id`, `responder_id`, `due_by`, and `fr_due_by` still match the cached entry.
- Cached Ticket `stats` are reused for category classification.
- Overdue flags are recomputed at runtime from the cached due-time fields and current time.

## Output Contract

The lightweight skill returns JSON with:

- `metric_name`: always `actionable_ticket_buckets`
- `metric_display_name`: always `待处理Ticket`
- `groups[]`
- `groups[].group_id`
- `groups[].group_name`
- `groups[].totals`
- `groups[].summary_by_agent[]`
- `groups[].cache`
- `groups[].scope`
- `cache.cache_hits`
- `cache.cache_misses`
- `safety.freshdesk_methods_used`: must be `["GET"]`
- `safety.writes_allowed`: must be `false`

The default CLI output is a human-readable table with columns:

- `Agent`
- `Need Follow Up`
- `Customer Responded`
- `New`
- `FR overdue`
- `Resolution overdue`

The default table prints only the `Group` name and the per-agent rows. Full JSON detail remains available through `--format json`.

## Metric Definition

The skill reports:

- `New Ticket`
  no public agent reply yet
- `Customer Responded Ticket`
  public agent reply history exists, and the latest customer reply is newer than the latest agent reply
- `FR overdue`
  `New Ticket` whose first-response due time has already passed
- `Resolution overdue`
  open Ticket whose resolution due time has already passed
