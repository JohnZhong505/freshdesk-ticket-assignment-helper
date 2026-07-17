#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="$ROOT_DIR/skills"
VALIDATOR="${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py"

validate_skill() {
  local skill_dir="$1"
  local script

  while IFS= read -r -d '' script; do
    python3 -m py_compile "$script"
    python3 "$script" --help >/dev/null
  done < <(find "$skill_dir/scripts" -type f -name '*.py' -print0)

  if [[ -f "$VALIDATOR" ]]; then
    if python3 -c "import yaml" >/dev/null 2>&1; then
      PYTHONUTF8=1 python3 "$VALIDATOR" "$skill_dir"
    else
      TMP_VENV="$(mktemp -d)"
      python3 -m venv "$TMP_VENV"
      VENV_PYTHON="$TMP_VENV/bin/python"
      if [[ ! -x "$VENV_PYTHON" ]]; then
        VENV_PYTHON="$TMP_VENV/Scripts/python.exe"
      fi
      "$VENV_PYTHON" -m pip install --quiet PyYAML
      PYTHONUTF8=1 "$VENV_PYTHON" "$VALIDATOR" "$skill_dir"
      rm -rf "$TMP_VENV"
    fi
  fi
}

for skill_dir in "$SKILLS_DIR"/*; do
  [[ -d "$skill_dir" ]] || continue
  validate_skill "$skill_dir"
done

for test_script in "$ROOT_DIR"/validation/test_*.py; do
  [[ -f "$test_script" ]] || continue
  python3 "$test_script"
done

if rg -n "gho_[A-Za-z0-9_]+|xoxb-[A-Za-z0-9-]+|https://oapi\\.dingtalk\\.com/robot/send" "$ROOT_DIR" \
  --glob '!validation/live-output*.json' \
  --glob '!validation/*.log'; then
  echo "Potential secret found in tracked project files." >&2
  exit 1
fi

if rg -n "method=\"POST\"|method='POST'|method=\"PATCH\"|method='PATCH'|method=\"DELETE\"|method='DELETE'" "$SKILLS_DIR"; then
  echo "Forbidden Freshdesk operation found." >&2
  exit 1
fi

PUT_MATCHES="$(rg -n '"PUT"' "$SKILLS_DIR" --glob '*.py' || true)"
UNEXPECTED_PUTS="$(printf '%s\n' "$PUT_MATCHES" | grep -v 'freshdesk-ticket-assignment-helper/scripts/freshdesk_assign_cs_group.py:' || true)"
if [[ -n "$UNEXPECTED_PUTS" ]]; then
  printf '%s\n' "$UNEXPECTED_PUTS"
  echo "PUT is only allowed in freshdesk_assign_cs_group.py." >&2
  exit 1
fi

if git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$ROOT_DIR" diff --check
fi

echo "Project verification passed."
