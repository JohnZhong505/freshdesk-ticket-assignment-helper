#!/usr/bin/env python3
"""Hermes no-agent entrypoint for the Technical Service triage view."""

from pathlib import Path
import math
import os
import runpy
import sys
import time


DEFAULT_RETRY_BASE_DELAY_SECONDS = 60.0
RETRYABLE_EXIT_CODE = 75  # EX_TEMPFAIL from freshdesk_triage_cron.py
RETRY_BASE_DELAY_ENV = "FRESHDESK_TRIAGE_RETRY_BASE_DELAY_SECONDS"
RUNTIME_ENV_NAMES = frozenset(
    {
        "HERMES_BIN",
        "DWS_BIN",
        "FRESHDESK_TRIAGE_TECH_GROUP_ID",
        "FRESHDESK_TRIAGE_CS_RECEIVER_ID",
    }
)


def load_runtime_dotenv(path: Path, env: dict[str, str]) -> None:
    """Load only the cron's allowlisted runtime values without shell evaluation."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ValueError(f"Cannot read Hermes dotenv file: {path}") from exc

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or key not in RUNTIME_ENV_NAMES:
            continue
        value = raw_value.strip()
        if value[:1] in {"'", '"'}:
            quote = value[0]
            if len(value) < 2 or value[-1] != quote:
                raise ValueError(f"Malformed allowlisted value in {path} at line {line_number}")
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        env.setdefault(key, value)


def retry_delays(env: dict[str, str]) -> tuple[float, float]:
    raw = env.get(RETRY_BASE_DELAY_ENV)
    if raw is None:
        base_delay = DEFAULT_RETRY_BASE_DELAY_SECONDS
    else:
        try:
            base_delay = float(raw)
        except ValueError as exc:
            raise ValueError(f"{RETRY_BASE_DELAY_ENV} must be a number") from exc
    if not math.isfinite(base_delay) or base_delay < 0:
        raise ValueError(f"{RETRY_BASE_DELAY_ENV} must be finite and non-negative")
    return base_delay, base_delay * 2


def driver() -> Path:
    candidates = [
        os.getenv("FRESHDESK_TRIAGE_SKILL_DIR"),
        Path.home() / ".hermes" / "skills" / "freshdesk-ticket-assignment-helper",
        Path.home() / ".codex" / "skills" / "freshdesk-ticket-assignment-helper",
        Path.home() / ".agents" / "skills" / "freshdesk-ticket-assignment-helper",
    ]
    for root in candidates:
        if root and (path := Path(root) / "scripts" / "freshdesk_triage_cron.py").is_file():
            return path
    raise SystemExit("freshdesk-ticket-assignment-helper is not installed")


def invoke_driver(path: Path, suppress_failure_card: bool) -> int:
    original_argv = sys.argv
    sys.argv = [str(path), "--view", "technical-service"]
    if suppress_failure_card:
        sys.argv.append("--suppress-failure-card")
    try:
        runpy.run_path(str(path), run_name="__main__")
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1
    except Exception as exc:
        print(f"Freshdesk triage wrapper attempt crashed: {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        sys.argv = original_argv
    return 0


def main() -> int:
    if any(argument in {"-h", "--help"} for argument in sys.argv[1:]):
        print("Run the Technical Service Freshdesk triage view as a Hermes no-agent cron script.")
        return 0

    try:
        load_runtime_dotenv(Path.home() / ".hermes" / ".env", os.environ)
        os.environ.setdefault("HERMES_BIN", str(Path.home() / ".hermes" / "scripts" / "hermes-opencode-go-mimo-v2.5-pro"))
        os.environ.setdefault("DWS_BIN", str(Path.home() / ".local" / "bin" / "dws"))
        delays = retry_delays(os.environ)
        path = driver()
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    for attempt in range(3):
        result = invoke_driver(path, suppress_failure_card=attempt < 2)
        if result == 0:
            return 0
        if result != RETRYABLE_EXIT_CODE:
            return result
        if attempt < 2:
            print(f"Freshdesk triage attempt {attempt + 1}/3 failed retryably; retrying.", file=sys.stderr)
            time.sleep(delays[attempt])
    return result


if __name__ == "__main__":
    raise SystemExit(main())
