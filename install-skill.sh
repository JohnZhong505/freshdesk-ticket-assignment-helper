#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$ROOT_DIR/skill/freshdesk-readonly-ticket-inspector"
TARGET_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"

if [[ "${1:-}" == "--target" ]]; then
  TARGET_ROOT="${2:?missing target path}"
fi

mkdir -p "$TARGET_ROOT"
rm -rf "$TARGET_ROOT/freshdesk-readonly-ticket-inspector"
cp -R "$SOURCE_DIR" "$TARGET_ROOT/"
echo "Installed freshdesk-readonly-ticket-inspector to $TARGET_ROOT"
