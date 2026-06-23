#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_DIR="$ROOT_DIR/skill/freshdesk-readonly-ticket-inspector"
READ_SCRIPT="$SKILL_DIR/scripts/freshdesk_readonly_ticket_inspector.py"
ASSIGN_SCRIPT="$SKILL_DIR/scripts/freshdesk_assign_ticket_agent.py"

python3 -m py_compile "$READ_SCRIPT" "$ASSIGN_SCRIPT"
python3 "$READ_SCRIPT" --help >/dev/null
python3 "$ASSIGN_SCRIPT" --help >/dev/null
if python3 -c "import yaml" >/dev/null 2>&1; then
  python3 /Users/a1/.codex/skills/.system/skill-creator/scripts/quick_validate.py "$SKILL_DIR"
else
  TMP_VENV="$(mktemp -d)"
  python3 -m venv "$TMP_VENV"
  "$TMP_VENV/bin/python" -m pip install --quiet PyYAML
  "$TMP_VENV/bin/python" /Users/a1/.codex/skills/.system/skill-creator/scripts/quick_validate.py "$SKILL_DIR"
  rm -rf "$TMP_VENV"
fi

if rg -n "gho_[A-Za-z0-9_]+|xoxb-[A-Za-z0-9-]+|https://oapi\\.dingtalk\\.com/robot/send" "$ROOT_DIR" \
  --glob '!validation/live-output*.json' \
  --glob '!validation/*.log'; then
  echo "Potential secret found in tracked project files." >&2
  exit 1
fi

if rg -n "method=\"POST\"|method='POST'|method=\"PATCH\"|method='PATCH'|method=\"DELETE\"|method='DELETE'" "$SKILL_DIR/scripts"; then
  echo "Forbidden Freshdesk operation found." >&2
  exit 1
fi

if git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$ROOT_DIR" diff --check
fi

echo "Project verification passed."
