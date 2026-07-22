#!/usr/bin/env python3
"""Soft-archive allowlisted Freshdesk classifier sessions via Hermes SessionDB."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ALLOWED_SOURCES = ("freshdesk-triage-tech", "freshdesk-triage-cs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=ALLOWED_SOURCES, required=True)
    return parser.parse_args()


def hermes_source_root() -> Path:
    configured = os.getenv("HERMES_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    # This script runs under <hermes-root>/venv/bin/python3. Avoid resolve(),
    # which follows the venv symlink back to the system Python installation.
    return Path(sys.executable).absolute().parents[2]


def main() -> int:
    args = parse_args()
    source_root = hermes_source_root()
    state_module = source_root / "hermes_state.py"
    if not state_module.is_file():
        print(f"Hermes state module not found under {source_root}", file=sys.stderr)
        return 1
    sys.path.insert(0, str(source_root))

    from hermes_state import SessionDB

    db = SessionDB()
    archived_count = 0
    try:
        while True:
            rows = db.list_sessions_rich(
                source=args.source,
                limit=500,
                offset=0,
                include_children=True,
                project_compression_tips=False,
                include_archived=False,
            )
            if not rows:
                break
            for row in rows:
                if row.get("source") != args.source:
                    raise RuntimeError("Hermes returned a session outside the requested source scope")
                if not db.set_session_archived(str(row["id"]), True):
                    raise RuntimeError("Hermes failed to archive a matched session")
                archived_count += 1
    finally:
        db.close()

    print(json.dumps({"success": True, "source": args.source, "archived_count": archived_count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
