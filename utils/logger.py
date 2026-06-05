import os
from datetime import datetime

from utils.db import get_data_dir


def get_log_path() -> str:
    """Return the absolute path of the API call log file."""
    return os.path.join(get_data_dir(), "api_calls.log")


def log_api_call(
    method: str,
    endpoint: str,
    request_summary: str,
    response_status: str,
    response_summary: str,
):
    """Append a one-line summary of an API call to the log file.

    The line is also printed to stdout for live debugging during development.
    Encoding is UTF-8 explicitly so non-ASCII content (server error messages,
    user names, locale-dependent strings) doesn't crash on Windows where
    the default text-mode encoding is cp1252.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = (
        f"[{timestamp}] {method} {endpoint} "
        f"| req: {request_summary} "
        f"| status: {response_status} "
        f"| resp: {response_summary}"
    )
    print(line)
    with open(get_log_path(), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def log_system(message: str, *, level: str = "INFO") -> None:
    """Append a free-form system/progress message to the log + stdout.

    Used by orchestration flows (e.g. the decommission tool) to narrate
    what they're doing around the raw API-call lines that log_api_call
    emits. `level` is a short tag (INFO/WARN/ERROR) shown in the prefix.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}"
    print(line)
    with open(get_log_path(), "a", encoding="utf-8") as f:
        f.write(line + "\n")
