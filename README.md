# Freshdesk Readonly Ticket Skill

Portable Codex Skill for Freshdesk Ticket inspection and supervised assignment preparation. Its default workflow gets Ticket count, Ticket IDs, Ticket subjects, Agent names, and Group names without changing Freshdesk data.

## Install

```bash
./install-skill.sh
```

The installer copies `skill/freshdesk-readonly-ticket-inspector` into `${CODEX_HOME:-$HOME/.codex}/skills`.

## Read-Only Run

```bash
export FRESHDESK_DOMAIN="example.freshdesk.com"
export FRESHDESK_API_KEY="..."
python3 skill/freshdesk-readonly-ticket-inspector/scripts/freshdesk_readonly_ticket_inspector.py --limit 20 --pretty
```

For a filtered pool:

```bash
python3 skill/freshdesk-readonly-ticket-inspector/scripts/freshdesk_readonly_ticket_inspector.py \
  --query "group_id:123456 AND agent_id:null" \
  --limit 30 \
  --pretty
```

## Supervised Assignment Test

Do not run this during normal verification. After selecting one safe Ticket and target Agent under human supervision:

```bash
python3 skill/freshdesk-readonly-ticket-inspector/scripts/freshdesk_assign_ticket_agent.py \
  --ticket-id 12345 \
  --responder-id 67890 \
  --group-id 11111 \
  --execute \
  --confirm-ticket-id 12345 \
  --pretty
```

Without `--execute`, the helper performs a dry-run preview only.

## Safety

- Freshdesk API key must be supplied through `FRESHDESK_API_KEY` or an equivalent secret manager.
- Tracked files must not contain API keys, webhooks, or live Ticket exports.
- Live output is ignored under `validation/live-output*.json` because Ticket subjects can contain customer information.
- Bulk Ticket updates are intentionally outside this project.

## Verify

```bash
./scripts/verify-project.sh
```

For live read-only verification, set `FRESHDESK_DOMAIN` and `FRESHDESK_API_KEY`, then run the read-only inspector with a small `--limit`.
