#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$ROOT_DIR/skills"
TARGET_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"
SKILL_NAME="freshdesk-ticket-assignment-helper"

usage() {
  cat <<'EOF'
Usage:
  ./install-skill.sh [--skill <skill-name>] [--target <target-root>]

Available skills:
  freshdesk-ticket-assignment-helper
  freshdesk-needs-follow-up-ticket-numbers
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skill)
      SKILL_NAME="${2:?missing skill name}"
      shift 2
      ;;
    --target)
      TARGET_ROOT="${2:?missing target path}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

SOURCE_DIR="$SKILLS_DIR/$SKILL_NAME"
if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Skill not found: $SKILL_NAME" >&2
  usage >&2
  exit 1
fi

mkdir -p "$TARGET_ROOT"
rm -rf "$TARGET_ROOT/$SKILL_NAME"
cp -R "$SOURCE_DIR" "$TARGET_ROOT/"
if [[ "$SKILL_NAME" == "freshdesk-ticket-assignment-helper" ]]; then
  LEGACY_SKILL_DIR="$TARGET_ROOT/freshdesk-readonly-ticket-inspector"
  if [[ -d "$LEGACY_SKILL_DIR" ]]; then
    rm -rf "$LEGACY_SKILL_DIR"
    echo "Removed legacy skill: freshdesk-readonly-ticket-inspector"
  fi
fi
echo "Installed $SKILL_NAME to $TARGET_ROOT"
