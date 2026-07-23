#!/usr/bin/env python3
"""Fail-closed unattended Freshdesk triage and DingTalk card delivery."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from typing import Any


BUCKET_ORDER_BY_VIEW = {
    "technical-service": (
        "CS",
        "Spam",
        "Sales",
        "Technical Support",
        "Merge",
        "Manual Review",
        "Technical Service",
    ),
    "customer-service": (
        "Technical Service",
        "Sales",
        "Spam",
        "Merge",
        "Manual Review",
        "Stay in Customer Service",
    ),
}
CONFIDENCES = {"high", "medium", "low"}
TARGET_BY_VIEW = {
    "technical-service": ("--group", "cidOXHoLP3FMfLpv2jif+iWPQ=="),
    "customer-service": ("--receiver", "DesWciiDKviS2g4tfIxy7uH14hiPX2oeF9Jl"),
}
SESSION_SOURCE_BY_VIEW = {
    "technical-service": "freshdesk-triage-tech",
    "customer-service": "freshdesk-triage-cs",
}
RETRYABLE_EXIT_CODE = 75  # EX_TEMPFAIL
RETRYABLE_STAGES = frozenset({"fetch", "classify", "dws-preflight"})
MAX_CARD_BYTES = 10_000


class CronError(RuntimeError):
    pass


def hermes_command(binary: str, prompt: str, source: str) -> list[str]:
    # The normal chat path propagates --ignore-rules to both project context
    # and memory isolation; the Hermes --oneshot fast path currently does not.
    return [
        binary,
        "chat",
        "-q",
        prompt,
        "--toolsets",
        "todo",
        "--ignore-rules",
        "--quiet",
        "--source",
        source,
    ]


def dws_target_args(view: str) -> list[str]:
    try:
        flag, value = TARGET_BY_VIEW[view]
    except KeyError as exc:
        raise CronError(f"Unknown triage view: {view}") from exc
    return [flag, value]


def dws_update_command(binary: str, biz_id: str, content: str) -> list[str]:
    return [
        binary,
        "chat",
        "message",
        "update-card",
        "--biz-id",
        biz_id,
        "--content",
        content,
        "--flow-status",
        "3",
        "-f",
        "json",
    ]


def card_required(snapshot: dict[str, Any]) -> bool:
    return bool(snapshot.get("ticket_count") and snapshot.get("tickets"))


def emit_success(outcome: str, view: str, ticket_count: int, **details: Any) -> None:
    print(json.dumps({"status": "ok", "outcome": outcome, "view": view, "ticket_count": ticket_count, **details}))


def load_credentials(env: dict[str, str], path: Path) -> tuple[str, str]:
    domain = env.get("FRESHDESK_DOMAIN", "").strip()
    api_key = env.get("FRESHDESK_API_KEY", "").strip()
    if domain and api_key:
        return domain, api_key
    try:
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise CronError(f"Freshdesk credentials file must use mode 0600: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        domain = str(payload.get("domain") or "").strip()
        api_key = str(payload.get("api_key") or "").strip()
    except CronError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        raise CronError(f"Cannot read Freshdesk credentials file: {path}") from exc
    if not domain or not api_key:
        raise CronError("Freshdesk domain or API key is missing.")
    return domain, api_key


def scrub_child_env(env: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in env.items() if key.upper() != "FRESHDESK_API_KEY"}


def ticket_batches(tickets: list[dict[str, Any]], max_chars: int) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for ticket in tickets:
        candidate = current + [ticket]
        if current and len(json.dumps(candidate, ensure_ascii=False)) > max_chars:
            batches.append(current)
            current = [ticket]
        else:
            current = candidate
        if len(json.dumps(current, ensure_ascii=False)) > max_chars:
            raise CronError(f"Ticket {ticket.get('ticket_id')} exceeds the Agent batch limit.")
    if current:
        batches.append(current)
    return batches


def _trim(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    half = (limit - 30) // 2
    return f"{text[:half]}\n[...truncated...]\n{text[-half:]}"


def compact_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    conversation_attachments = [
        attachment
        for conversation in ticket.get("public_conversations", [])
        if isinstance(conversation, dict)
        for attachment in conversation.get("attachments", [])
        if isinstance(attachment, dict)
    ]
    return {
        "ticket_id": ticket.get("ticket_id"),
        "subject": _trim(ticket.get("subject"), 500),
        "current_group": ticket.get("group_name"),
        "triage_text": _trim(ticket.get("triage_text"), 6000),
        "initial_attachments": ticket.get("initial_attachments", []),
        "public_attachment_metadata": conversation_attachments,
        "merge_check": ticket.get("merge_check", {}),
    }


def build_agent_prompt(template: str, rules: str, view: str, tickets: list[dict[str, Any]]) -> str:
    payload = json.dumps({"view": view, "tickets": tickets}, ensure_ascii=False, indent=2)
    return f"{template.strip()}\n\nROUTING_RULES\n{rules.strip()}\n\nTICKET_DATA\n{payload}\n"


def version_at_least(value: str, minimum: tuple[int, int, int]) -> bool:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", value)
    return bool(match and tuple(map(int, match.groups())) >= minimum)


def _run_text(
    command: list[str],
    runner: Any,
    env: dict[str, str],
    timeout: int,
) -> str:
    completed = runner(command, capture_output=True, text=True, timeout=timeout, env=env)
    if completed.returncode != 0:
        detail = _redact((completed.stderr or completed.stdout or "command failed").strip())[:500]
        raise CronError(f"Command failed with exit {completed.returncode}: {detail}")
    return (completed.stdout or "").strip()


def archive_classification_sessions(
    hermes_runtime_python: str,
    source: str,
    runner: Any = subprocess.run,
    env: dict[str, str] | None = None,
) -> None:
    if source not in SESSION_SOURCE_BY_VIEW.values():
        raise CronError(f"Refusing to archive an unknown session source: {source}")
    child_env = scrub_child_env(dict(env or os.environ))
    archive_script = Path(__file__).resolve().parent / "archive_hermes_sessions.py"
    _run_text(
        [hermes_runtime_python, str(archive_script), "--source", source],
        runner,
        child_env,
        60,
    )


def fetch_snapshot(
    view: str,
    domain: str,
    api_key: str,
    inspector: Path,
    python_binary: str,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    command = [
        python_binary,
        str(inspector),
        "--domain",
        domain,
        "--triage-view",
        view,
    ]
    child_env = os.environ.copy()
    child_env["FRESHDESK_API_KEY"] = api_key
    payload = parse_agent_output(_run_text(command, runner, child_env, 300))
    safety = payload.get("safety")
    if (
        payload.get("triage_view") != view
        or not isinstance(payload.get("tickets"), list)
        or payload.get("ticket_count") != len(payload["tickets"])
        or not isinstance(safety, dict)
        or safety.get("freshdesk_methods_used") != ["GET"]
        or safety.get("writes_allowed") is not False
    ):
        raise CronError("Freshdesk inspector returned an invalid or non-read-only snapshot.")
    return payload


def classify_snapshot(
    snapshot: dict[str, Any],
    hermes_binary: str,
    template: str,
    rules: str,
    runner: Any = subprocess.run,
    env: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    view = snapshot.get("triage_view")
    try:
        source = SESSION_SOURCE_BY_VIEW[view]
    except KeyError as exc:
        raise CronError(f"Unknown triage view: {view}") from exc
    compact = [compact_ticket(ticket) for ticket in snapshot.get("tickets", [])]
    classified: list[dict[str, Any]] = []
    child_env = scrub_child_env(dict(env or os.environ))
    for batch in ticket_batches(compact, max_chars=9000):
        prompt = build_agent_prompt(template, rules, view, batch)
        last_error: CronError | None = None
        for attempt in range(2):
            try:
                output = _run_text(hermes_command(hermes_binary, prompt, source), runner, child_env, 300)
                batch_result = parse_agent_output(output)
                if batch_result.get("view") != view or not isinstance(batch_result.get("tickets"), list):
                    raise CronError("Hermes Agent returned an invalid batch object.")
                expected = {ticket["ticket_id"] for ticket in batch}
                returned = [row.get("ticket_id") for row in batch_result["tickets"] if isinstance(row, dict)]
                if len(returned) != len(batch_result["tickets"]) or len(set(returned)) != len(returned) or set(returned) != expected:
                    raise CronError("Hermes Agent batch did not classify every Ticket exactly once.")
                classified.extend(batch_result["tickets"])
                last_error = None
                break
            except CronError as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(1)
        if last_error is not None:
            raise last_error
    return validate_classifications(snapshot, {"view": view, "tickets": classified})


def _run_json(command: list[str], runner: Any, env: dict[str, str], timeout: int = 60) -> dict[str, Any]:
    payload = parse_agent_output(_run_text(command, runner, env, timeout))
    if payload.get("success") is False:
        raise CronError(f"DWS command failed: {_redact(str(payload.get('error') or payload.get('message') or 'unknown error'))[:300]}")
    return payload


def send_stream_card(
    dws_binary: str,
    view: str,
    content: str,
    runner: Any = subprocess.run,
    env: dict[str, str] | None = None,
) -> str:
    child_env = scrub_child_env(dict(env or os.environ))
    created = _run_json(dws_send_command(dws_binary, view), runner, child_env)
    result = created.get("result") if isinstance(created.get("result"), dict) else {}
    biz_id = result.get("bizId")
    if not isinstance(biz_id, str) or not biz_id:
        raise CronError("DWS send-card did not return a bizId; create is ambiguous and was not retried.")
    last_error: CronError | None = None
    for attempt in range(3):
        try:
            _run_json(dws_update_command(dws_binary, biz_id, content), runner, child_env)
            return biz_id
        except CronError as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2**attempt)
    raise last_error or CronError("DWS update-card failed.")


def preflight_dws(
    dws_binary: str,
    runner: Any = subprocess.run,
    env: dict[str, str] | None = None,
) -> None:
    child_env = scrub_child_env(dict(env or os.environ))
    version = _run_json([dws_binary, "version", "-f", "json"], runner, child_env)
    if not version_at_least(str(version.get("version") or ""), (1, 0, 52)):
        raise CronError("DWS CLI v1.0.52 or newer is required.")
    auth = _run_json([dws_binary, "auth", "status", "-f", "json"], runner, child_env)
    if auth.get("authenticated") is not True or auth.get("token_valid") is not True:
        raise CronError("DWS authentication is not valid.")


def send_failure_card(
    dws_binary: str,
    stage: str,
    retries: int,
    error: str,
    runner: Any = subprocess.run,
    env: dict[str, str] | None = None,
) -> str:
    return send_stream_card(dws_binary, "technical-service", failure_card(stage, retries, error), runner, env)


def find_binary(explicit: str | None, name: str) -> str:
    suffix = ".exe" if os.name == "nt" else ""
    if explicit:
        if Path(explicit).is_file():
            return str(Path(explicit))
        raise CronError(f"Configured executable was not found for {name}: {explicit}")
    candidates = [
        shutil.which(name),
        str(Path.home() / ".local" / "bin" / f"{name}{suffix}"),
        f"/opt/homebrew/bin/{name}",
        f"/usr/local/bin/{name}",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate))
    raise CronError(f"Required executable was not found: {name}")


def find_hermes_runtime_python(explicit: str | None = None) -> str:
    suffix = ".exe" if os.name == "nt" else ""
    hermes_dir = Path(os.getenv("HERMES_DIR", Path.home() / ".hermes" / "hermes-agent"))
    candidates = [
        explicit,
        os.getenv("HERMES_RUNTIME_PYTHON"),
        str(hermes_dir / "venv" / "bin" / "python3"),
        str(hermes_dir / "venv" / "Scripts" / f"python{suffix}"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate))
    raise CronError("Hermes runtime Python was not found for session archiving.")


def default_state_dir() -> Path:
    override = os.getenv("FRESHDESK_TRIAGE_STATE_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt" and os.getenv("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "freshdesk-ticket-assignment-helper"
    return Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "freshdesk-ticket-assignment-helper"


def append_log(path: Path, event: str, **fields: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "event": event,
        **{key: _redact(str(value))[:500] for key, value in fields.items()},
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


@contextmanager
def view_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = path.open("a+b")
    except OSError as exc:
        raise CronError(f"Unable to open the {path.stem} triage lock.") from exc

    with handle:
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise CronError(f"Another {path.stem} triage run is still active.") from exc

        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Run fail-closed Freshdesk triage and send a DingTalk card.")
    parser.add_argument("--view", choices=tuple(BUCKET_ORDER_BY_VIEW), required=True)
    parser.add_argument("--dry-run", action="store_true", help="Classify and render without sending DingTalk messages.")
    parser.add_argument("--credentials-file", type=Path)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--inspector", type=Path, default=script_dir / "freshdesk_readonly_ticket_inspector.py")
    parser.add_argument("--hermes")
    parser.add_argument("--dws")
    parser.add_argument(
        "--suppress-failure-card",
        action="store_true",
        help="Suppress failure cards only for retryable side-effect-free failures on intermediate wrapper attempts.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    script_root = Path(__file__).resolve().parents[1]
    prompt_path = script_root / "references" / "hermes-cron-prompt.md"
    rules_path = script_root / "references" / "triage-routing-rules.md"
    credentials_path = args.credentials_file or Path(
        os.getenv(
            "FRESHDESK_CREDENTIALS_FILE",
            Path.home() / ".config" / "freshdesk-ticket-assignment-helper" / "credentials.json",
        )
    ).expanduser()
    state_dir = (args.state_dir or default_state_dir()).expanduser()
    log_path = state_dir / "runs.jsonl"
    sent_path = state_dir / f"sent-{args.view}.json"
    failure_path = state_dir / f"failures-{args.view}.json"
    stage = "startup"
    retry_counts = {"startup": 0, "fetch": 2, "classify": 1, "dws-preflight": 0, "send": 2}
    dws_binary: str | None = None
    classification_started = False
    session_source = SESSION_SOURCE_BY_VIEW[args.view]

    try:
        with view_lock(state_dir / f"{args.view}.lockfile"):
            domain, api_key = load_credentials(os.environ, credentials_path)
            stage = "fetch"
            snapshot = fetch_snapshot(
                args.view,
                domain,
                api_key,
                args.inspector,
                sys.executable,
            )
            if not card_required(snapshot):
                append_log(log_path, "zero_tickets", view=args.view)
                emit_success("zero_tickets", args.view, 0)
                return 0

            stage = "startup"
            hermes_binary = find_binary(args.hermes or os.getenv("HERMES_BIN"), "hermes")
            template = prompt_path.read_text(encoding="utf-8")
            rules = rules_path.read_text(encoding="utf-8")
            stage = "classify"
            classification_started = True
            rows = classify_snapshot(snapshot, hermes_binary, template, rules)
            cards = render_card_parts(args.view, snapshot, rows)
            day = datetime.now().astimezone().date().isoformat()
            fingerprint = routing_fingerprint(day, args.view, rows)
            if already_sent(sent_path, args.view, fingerprint):
                append_log(log_path, "duplicate_suppressed", view=args.view, fingerprint=fingerprint[:12])
                emit_success("duplicate_suppressed", args.view, snapshot["ticket_count"], fingerprint=fingerprint[:12])
                return 0
            if args.dry_run:
                append_log(
                    log_path,
                    "dry_run_completed",
                    view=args.view,
                    ticket_count=snapshot["ticket_count"],
                    fingerprint=fingerprint[:12],
                )
                print(json.dumps({"view": args.view, "fingerprint": fingerprint, "cards": cards}, ensure_ascii=False, indent=2))
                return 0

            stage = "startup"
            dws_binary = find_binary(args.dws or os.getenv("DWS_BIN"), "dws")
            stage = "dws-preflight"
            preflight_dws(dws_binary)
            stage = "send"
            part_path = state_dir / f"parts-{args.view}-{fingerprint}.json"
            for index, card in enumerate(cards, start=1):
                part_hash = hashlib.sha256(card.encode("utf-8")).hexdigest()
                if already_sent(part_path, str(index), part_hash):
                    continue
                send_stream_card(dws_binary, args.view, card)
                record_sent(part_path, str(index), part_hash)
            record_sent(sent_path, args.view, fingerprint)
            part_path.unlink(missing_ok=True)
            append_log(
                log_path,
                "card_sent",
                view=args.view,
                ticket_count=snapshot["ticket_count"],
                card_count=len(cards),
                fingerprint=fingerprint[:12],
            )
            emit_success(
                "card_sent",
                args.view,
                snapshot["ticket_count"],
                card_count=len(cards),
                fingerprint=fingerprint[:12],
            )
            return 0
    except Exception as exc:
        error = _redact(str(exc))[:500]
        retryable = stage in RETRYABLE_STAGES
        append_log(log_path, "run_failed", view=args.view, stage=stage, error=error)
        if not args.dry_run and (not retryable or not args.suppress_failure_card):
            try:
                dws_binary = dws_binary or find_binary(args.dws or os.getenv("DWS_BIN"), "dws")
                failure_fingerprint = hashlib.sha256(
                    f"{datetime.now().astimezone().date()}|{stage}|{error}".encode("utf-8")
                ).hexdigest()
                if not already_sent(failure_path, "failure", failure_fingerprint):
                    send_failure_card(dws_binary, stage, retry_counts.get(stage, 0), error)
                    record_sent(failure_path, "failure", failure_fingerprint)
            except Exception as notify_exc:
                append_log(log_path, "failure_card_failed", error=_redact(str(notify_exc))[:500])
        print(f"Freshdesk triage failed at {stage}: {error}", file=sys.stderr)
        return RETRYABLE_EXIT_CODE if retryable else 1
    finally:
        if classification_started:
            try:
                hermes_runtime_python = find_hermes_runtime_python()
                archive_classification_sessions(hermes_runtime_python, session_source)
                append_log(
                    log_path,
                    "session_archived",
                    view=args.view,
                    source=session_source,
                )
            except Exception as archive_exc:
                try:
                    append_log(
                        log_path,
                        "session_archive_failed",
                        view=args.view,
                        source=session_source,
                        error=_redact(str(archive_exc))[:500],
                    )
                except Exception:
                    pass


def parse_agent_output(value: str) -> dict[str, Any]:
    candidate = value.strip() if isinstance(value, str) else value
    if isinstance(candidate, str):
        session_header = re.match(
            r"\Asession_id: [0-9]{8}_[0-9]{6}_[0-9a-f]{6}\r?\n",
            candidate,
        )
        if session_header:
            candidate = candidate[session_header.end():].strip()
        fenced = re.fullmatch(r"```json\s*(\{.*\})\s*```", candidate, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            candidate = fenced.group(1)
    try:
        payload = json.loads(candidate)
    except (json.JSONDecodeError, TypeError) as exc:
        raise CronError("Hermes Agent did not return exact JSON or one exact JSON code fence.") from exc
    if not isinstance(payload, dict):
        raise CronError("Hermes Agent JSON must be an object.")
    return payload


def dws_send_command(binary: str, view: str) -> list[str]:
    return [binary, "chat", "message", "send-card", *dws_target_args(view), "-f", "json"]


def already_sent(path: Path, view: str, fingerprint: str) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    return payload.get(view) == fingerprint


def record_sent(path: Path, view: str, fingerprint: str) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (ValueError, TypeError):
        payload = {}
    path.parent.mkdir(parents=True, exist_ok=True)
    payload[view] = fingerprint
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _redact(value: str) -> str:
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[redacted-email]", value)
    return re.sub(r"\b[A-Za-z0-9_+/=-]{24,}\b", "[redacted-token]", value)


def failure_card(stage: str, retries: int, error: str) -> str:
    summary = _cell(_redact(error))[:300]
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    return (
        "| 阶段 | 时间 | 重试次数 | 错误摘要 |\n"
        "|---|---|---:|---|\n"
        f"| {_cell(stage)} | {timestamp} | {retries} | {summary} |"
    )


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CronError(f"Classification {field} must be a non-empty string.")
    return _redact(" ".join(value.split()))[:300]


def _chinese_evidence(value: Any) -> str:
    evidence = _text(value, "evidence")
    if not re.search(r"[\u3400-\u9fff]", evidence):
        raise CronError("Classification evidence must include a concise Chinese explanation.")
    return evidence


def validate_classifications(snapshot: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    view = snapshot.get("triage_view")
    if view not in BUCKET_ORDER_BY_VIEW or result.get("view") != view:
        raise CronError("Classification view does not match the Freshdesk snapshot.")

    tickets = snapshot.get("tickets")
    rows = result.get("tickets")
    if not isinstance(tickets, list) or not isinstance(rows, list):
        raise CronError("Snapshot and classification tickets must be lists.")

    snapshot_by_id = {
        int(ticket["ticket_id"]): ticket
        for ticket in tickets
        if isinstance(ticket, dict) and ticket.get("ticket_id") is not None
    }
    row_ids = [row.get("ticket_id") for row in rows if isinstance(row, dict)]
    if len(row_ids) != len(rows) or len(set(row_ids)) != len(row_ids) or set(row_ids) != set(snapshot_by_id):
        raise CronError("Every snapshot Ticket must be classified exactly once, with no extra IDs.")

    validated: list[dict[str, Any]] = []
    for row in rows:
        ticket_id = int(row["ticket_id"])
        bucket = row.get("bucket")
        confidence = row.get("confidence")
        if bucket not in BUCKET_ORDER_BY_VIEW[view]:
            raise CronError(f"Classification bucket is not allowed for {view}: {bucket!r}")
        if confidence not in CONFIDENCES:
            raise CronError(f"Classification confidence is invalid for Ticket {ticket_id}.")
        source = snapshot_by_id[ticket_id]
        expected_link = source.get("ticket_link_markdown")
        if expected_link != f"[{ticket_id}]({source.get('ticket_url')})":
            raise CronError(f"Snapshot link is invalid for Ticket {ticket_id}.")
        merge_target = row.get("merge_target_ticket_id")
        candidates = source.get("merge_check", {}).get("candidates", [])
        candidates_by_id = {
            int(candidate["ticket_id"]): candidate
            for candidate in candidates
            if isinstance(candidate, dict) and candidate.get("ticket_id") is not None
        }
        merge_target_link = None
        if bucket == "Merge":
            if merge_target is None or int(merge_target) not in candidates_by_id:
                raise CronError(f"Merge target is not an allowed candidate for Ticket {ticket_id}.")
            merge_target = int(merge_target)
            target = candidates_by_id[merge_target]
            merge_target_link = target.get("ticket_link_markdown")
            if merge_target_link != f"[{merge_target}]({target.get('ticket_url')})":
                raise CronError(f"Merge target link is invalid for Ticket {ticket_id}.")
        elif merge_target is not None:
            raise CronError(f"Merge target is only allowed for Merge Ticket {ticket_id}.")
        validated.append(
            {
                "ticket_id": ticket_id,
                "ticket_link_markdown": expected_link,
                "bucket": bucket,
                "confidence": confidence,
                "reason": _text(row.get("reason"), "reason"),
                "evidence": _chinese_evidence(row.get("evidence")),
                "merge_target_ticket_id": merge_target,
                "merge_target_ticket_link_markdown": merge_target_link,
            }
        )
    return validated


def _cell(value: Any) -> str:
    return " ".join(str(value).split()).replace("|", "\\|")


def render_card(view: str, snapshot: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    if view not in BUCKET_ORDER_BY_VIEW or snapshot.get("triage_view") != view:
        raise CronError("Cannot render a card for a mismatched view.")
    retained_heading = {
        "technical-service": {"Technical Service": "保留 Technical Service"},
        "customer-service": {"Stay in Customer Service": "保留 Customer Service"},
    }
    sections: list[str] = []
    for bucket in BUCKET_ORDER_BY_VIEW[view]:
        bucket_rows = [row for row in rows if row["bucket"] == bucket]
        if not bucket_rows:
            continue
        heading = retained_heading[view].get(bucket, bucket)
        if bucket == "Merge":
            lines = [
                f"### {heading}",
                "| Ticket | 合并目标 | 置信度 | 原因 | 证据 |",
                "|---|---|---|---|---|",
            ]
            lines.extend(
                f"| {row['ticket_link_markdown']} | {row['merge_target_ticket_link_markdown']} | {_cell(row['confidence'])} | {_cell(row['reason'])} | {_cell(row['evidence'])} |"
                for row in bucket_rows
            )
        else:
            lines = [
                f"### {heading}",
                "| Ticket | 置信度 | 原因 | 证据 |",
                "|---|---|---|---|",
            ]
            lines.extend(
                f"| {row['ticket_link_markdown']} | {_cell(row['confidence'])} | {_cell(row['reason'])} | {_cell(row['evidence'])} |"
                for row in bucket_rows
            )
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def render_card_parts(
    view: str,
    snapshot: dict[str, Any],
    rows: list[dict[str, Any]],
    max_bytes: int = MAX_CARD_BYTES,
) -> list[str]:
    if max_bytes < 1000:
        raise CronError("Card byte limit is too small.")
    ordered = [row for bucket in BUCKET_ORDER_BY_VIEW[view] for row in rows if row["bucket"] == bucket]
    parts: list[str] = []
    current: list[dict[str, Any]] = []
    payload_limit = max_bytes - 100
    for row in ordered:
        candidate = render_card(view, snapshot, [*current, row])
        if current and len(candidate.encode("utf-8")) > payload_limit:
            parts.append(render_card(view, snapshot, current))
            current = [row]
        else:
            current.append(row)
    if current:
        parts.append(render_card(view, snapshot, current))
    if len(parts) > 1:
        count = len(parts)
        parts = [f"## 分流结果 {index}/{count}\n\n{part}" for index, part in enumerate(parts, 1)]
    if any(len(part.encode("utf-8")) > max_bytes for part in parts):
        raise CronError("A rendered DingTalk card exceeds the configured byte limit.")
    return parts


def routing_fingerprint(day: str, view: str, rows: list[dict[str, Any]]) -> str:
    payload = {
        "day": day,
        "view": view,
        "rows": sorted(rows, key=lambda row: int(row["ticket_id"])),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
