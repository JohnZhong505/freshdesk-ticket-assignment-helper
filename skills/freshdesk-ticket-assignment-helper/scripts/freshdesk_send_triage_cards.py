#!/usr/bin/env python3
"""Preview or explicitly send validated interactive triage cards to fixed DingTalk targets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from freshdesk_triage_cron import (
    BUCKET_ORDER_BY_VIEW,
    CronError,
    already_sent,
    default_state_dir,
    dws_target_args,
    find_binary,
    preflight_dws,
    record_sent,
    render_card_parts,
    send_stream_card,
    validate_classifications,
)


TARGET_LABEL_BY_VIEW = {
    "technical-service": "测试群",
    "customer-service": "Amber",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preview or send validated triage tables to the view's fixed DingTalk target.")
    parser.add_argument("--view", choices=tuple(BUCKET_ORDER_BY_VIEW), required=True)
    parser.add_argument("--input", type=Path, help="Redacted delivery JSON. Defaults to stdin.")
    parser.add_argument("--send", action="store_true", help="Send after validation; default is preview only.")
    parser.add_argument("--dws", help="Explicit DWS executable path. Recipient arguments are not accepted.")
    parser.add_argument("--state-dir", type=Path, help="Checkpoint directory for resuming a partial multi-card send.")
    return parser.parse_args(argv)


def load_input(path: Path | None = None) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path else json.load(sys.stdin)
    except (OSError, ValueError, TypeError) as exc:
        raise CronError("stdin must contain one JSON object with snapshot and classification.") from exc
    if not isinstance(payload, dict):
        raise CronError("stdin JSON must be an object.")
    return payload


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = load_input(args.input)
        snapshot = payload.get("snapshot")
        classification = payload.get("classification")
        if not isinstance(snapshot, dict) or not isinstance(classification, dict):
            raise CronError("Input requires snapshot and classification objects.")
        if snapshot.get("triage_view") != args.view or classification.get("view") != args.view:
            raise CronError("Input view does not match --view.")
        rows = validate_classifications(snapshot, classification)
        cards = render_card_parts(args.view, snapshot, rows)
        target = TARGET_LABEL_BY_VIEW[args.view]
        if not cards:
            print(json.dumps({"status": "empty", "view": args.view, "target": target, "card_count": 0}, ensure_ascii=False))
            return 0
        if not args.send:
            print(json.dumps({"status": "preview", "view": args.view, "target": target, "cards": cards}, ensure_ascii=False))
            return 0
        dws_binary = find_binary(args.dws or os.getenv("DWS_BIN"), "dws")
        preflight_dws(dws_binary)
        fingerprint = hashlib.sha256(json.dumps(cards, ensure_ascii=False).encode("utf-8")).hexdigest()
        state_dir = (args.state_dir or default_state_dir()).expanduser()
        part_path = state_dir / f"parts-interactive-{args.view}-{fingerprint}.json"
        for index, card in enumerate(cards, start=1):
            part_hash = hashlib.sha256(card.encode("utf-8")).hexdigest()
            if already_sent(part_path, str(index), part_hash):
                continue
            send_stream_card(dws_binary, args.view, card)
            record_sent(part_path, str(index), part_hash)
        part_path.unlink(missing_ok=True)
        print(json.dumps({"status": "sent", "view": args.view, "target": target, "card_count": len(cards)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"Interactive triage delivery failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
