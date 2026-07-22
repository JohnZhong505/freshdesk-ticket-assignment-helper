#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
WRAPPERS = ROOT / "skills" / "freshdesk-ticket-assignment-helper" / "scripts"
TECHNICAL_WRAPPER = WRAPPERS / "hermes_cron_technical_service.py"
CUSTOMER_WRAPPER = WRAPPERS / "hermes_cron_customer_service.py"

FAKE_DRIVER = '''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

log_path = Path(os.environ["FAKE_DRIVER_LOG"])
existing = log_path.read_text(encoding="utf-8").splitlines() if log_path.exists() else []
row = {
    "argv": sys.argv[1:],
    "HERMES_BIN": os.environ.get("HERMES_BIN"),
    "DWS_BIN": os.environ.get("DWS_BIN"),
}
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(row) + "\\n")
codes = [int(value) for value in os.environ["FAKE_DRIVER_CODES"].split(",")]
raise SystemExit(codes[len(existing)])
'''


def load_wrapper(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_wrapper(wrapper: Path, codes: str, base_delay: str = "0") -> tuple[subprocess.CompletedProcess[str], list[dict]]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        skill_dir = root / "skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "freshdesk_triage_cron.py").write_text(FAKE_DRIVER, encoding="utf-8")
        log_path = root / "driver.jsonl"
        hermes_home = root / ".hermes"
        hermes_home.mkdir()
        (hermes_home / ".env").write_text(
            "\n".join(
                [
                    "HERMES_BIN=/runtime/hermes",
                    "DWS_BIN=/runtime/dws",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        env = {
            "HOME": str(root),
            "USERPROFILE": str(root),
            "PATH": os.environ.get("PATH", ""),
            "PYTHONUTF8": "1",
            "FRESHDESK_TRIAGE_SKILL_DIR": str(skill_dir),
            "FRESHDESK_TRIAGE_RETRY_BASE_DELAY_SECONDS": base_delay,
            "FAKE_DRIVER_LOG": str(log_path),
            "FAKE_DRIVER_CODES": codes,
        }
        completed = subprocess.run(
            [sys.executable, str(wrapper)],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()] if log_path.exists() else []
        return completed, rows


def test_retryable_fail_then_success_stops_immediately_and_loads_dotenv() -> None:
    completed, rows = run_wrapper(TECHNICAL_WRAPPER, "75,0,1")
    assert completed.returncode == 0
    assert len(rows) == 2
    assert all(row["HERMES_BIN"] == "/runtime/hermes" for row in rows)
    assert all(row["DWS_BIN"] == "/runtime/dws" for row in rows)
    assert rows[0]["argv"] == ["--view", "technical-service", "--suppress-failure-card"]
    assert rows[1]["argv"] == ["--view", "technical-service", "--suppress-failure-card"]


def test_three_retryable_failures_only_make_final_attempt_notification_eligible() -> None:
    completed, rows = run_wrapper(CUSTOMER_WRAPPER, "75,75,75")
    assert completed.returncode == 75
    assert len(rows) == 3
    suppressions = ["--suppress-failure-card" in row["argv"] for row in rows]
    assert suppressions == [True, True, False]
    assert sum(not suppressed for suppressed in suppressions) == 1
    assert all(row["argv"][:2] == ["--view", "customer-service"] for row in rows)


def test_non_retryable_failure_stops_after_one_attempt() -> None:
    completed, rows = run_wrapper(TECHNICAL_WRAPPER, "1,0,0")
    assert completed.returncode == 1
    assert len(rows) == 1
    assert rows[0]["argv"] == ["--view", "technical-service", "--suppress-failure-card"]
    assert "retrying" not in completed.stderr


def test_retry_delay_configuration_fails_closed() -> None:
    completed, rows = run_wrapper(TECHNICAL_WRAPPER, "0", base_delay="-1")
    assert completed.returncode == 2
    assert rows == []
    assert "FRESHDESK_TRIAGE_RETRY_BASE_DELAY_SECONDS" in completed.stderr


def test_retry_delays_are_deterministic_exponential_defaults() -> None:
    for wrapper in (TECHNICAL_WRAPPER, CUSTOMER_WRAPPER):
        module = load_wrapper(wrapper)
        assert module.retry_delays({}) == (60.0, 120.0)
        assert module.retry_delays({module.RETRY_BASE_DELAY_ENV: "1.5"}) == (1.5, 3.0)


if __name__ == "__main__":
    test_retryable_fail_then_success_stops_immediately_and_loads_dotenv()
    test_three_retryable_failures_only_make_final_attempt_notification_eligible()
    test_non_retryable_failure_stops_after_one_attempt()
    test_retry_delay_configuration_fails_closed()
    test_retry_delays_are_deterministic_exponential_defaults()
    print("triage wrapper retry tests passed")
