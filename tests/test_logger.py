"""Log pruning: entries older than the retention window are dropped."""

from datetime import datetime

import pytest

from utils import logger

NOW = datetime(2026, 10, 30, 12, 0, 0)


@pytest.fixture
def log(tmp_path, monkeypatch):
    path = tmp_path / "api_calls.log"
    monkeypatch.setattr(logger, "get_log_path", lambda: str(path))
    return path


def test_entries_older_than_30_days_are_dropped(log):
    log.write_text(
        "[2026-09-01 08:00:00] POST org/site/create | req: {} | status: 200 | resp: \n"
        "[2026-09-30 11:59:59] POST org/user/login | req: {} | status: 400 | resp: line one\n"
        "  continued message on its own line\n"
        "[2026-09-30 12:00:00] [INFO] exactly 30 days old is kept\n"
        "[2026-10-29 09:00:00] GET org/doors | req: {} | status: 200 | resp: \n",
        encoding="utf-8",
    )
    assert logger.prune_old_entries(now=NOW) == 3
    kept = log.read_text(encoding="utf-8").splitlines()
    assert [line[:21] for line in kept] == ["[2026-09-30 12:00:00]", "[2026-10-29 09:00:00]"]


def test_lines_before_the_first_stamp_and_bad_stamps_are_kept(log):
    log.write_text(
        "header written by hand\n"
        "[2026-13-45 99:99:99] unparseable stamp\n"
        "[2025-01-01 00:00:00] old\n",
        encoding="utf-8",
    )
    assert logger.prune_old_entries(now=NOW) == 1
    assert "old" not in log.read_text(encoding="utf-8")


def test_nothing_to_drop_leaves_the_file_untouched(log):
    log.write_text("[2026-10-30 10:00:00] recent\n", encoding="utf-8")
    before = log.stat().st_mtime_ns
    assert logger.prune_old_entries(now=NOW) == 0
    assert log.stat().st_mtime_ns == before


def test_a_missing_log_is_fine(log):
    assert logger.prune_old_entries(now=NOW) == 0
    assert not log.exists()
