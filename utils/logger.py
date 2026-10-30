import os
import re
from datetime import datetime, timedelta

from utils.db import get_data_dir

# Entries older than this (relative to when the tool starts) are dropped.
LOG_RETENTION_DAYS = 30

_STAMP = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]")


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


def prune_old_entries(days: int = LOG_RETENTION_DAYS, now: datetime | None = None) -> int:
    """Drop log entries older than `days` before `now` (default: the current
    run). Returns how many lines were removed.

    Every entry starts with a "[YYYY-MM-DD HH:MM:SS]" stamp; a line without
    one (e.g. a server message that contained a newline) belongs to the entry
    above it and is kept or dropped with it. Lines before the first stamp, or
    with a stamp that doesn't parse, are kept. The file is rewritten through
    a temporary file and os.replace, so an interrupted prune never truncates
    the log. Best effort: an unreadable or unwritable log is left alone.
    """
    path = get_log_path()
    cutoff = (now or datetime.now()) - timedelta(days=days)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return 0
    kept: list[str] = []
    keep = True
    for line in lines:
        match = _STAMP.match(line)
        if match:
            try:
                keep = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S") >= cutoff
            except ValueError:
                keep = True
        if keep:
            kept.append(line)
    removed = len(lines) - len(kept)
    if not removed:
        return 0
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(kept)
        os.replace(tmp, path)
    except OSError:
        return 0
    return removed
