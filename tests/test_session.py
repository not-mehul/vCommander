"""Run registry: one job at a time, cancelled by logout/expiry."""

from utils import session
from utils.cancellation import CancellationToken


def test_only_one_run_at_a_time():
    first, second = CancellationToken(), CancellationToken()
    assert session.begin_run("Decommission", first)
    assert session.running_job() == "Decommission"
    assert not session.begin_run("Commission", second)
    session.end_run(first)
    assert session.running_job() is None
    assert session.begin_run("Commission", second)


def test_end_run_ignores_other_tokens():
    token = CancellationToken()
    session.begin_run("Decommission", token)
    session.end_run(CancellationToken())
    assert session.running_job() == "Decommission"


def test_cancelled_run_is_not_running_but_still_blocks_a_new_one():
    token = CancellationToken()
    session.begin_run("Decommission", token)
    session.cancel_run()
    assert token.is_cancelled
    assert session.running_job() is None  # leaving is safe now
    assert not session.begin_run("Commission", CancellationToken())
    session.end_run(token)
    assert session.begin_run("Commission", CancellationToken())


def test_clear_session_cancels_the_running_job():
    token = CancellationToken()
    session.begin_run("Decommission", token)
    session.clear_session()
    assert token.is_cancelled
