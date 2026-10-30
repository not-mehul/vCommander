"""Process-wide session state.

Holds the authenticated internal/external API clients and the session
start time so any view can reach them without prop-drilling.

The SESSION_TIMEOUT_MINUTES window is an absolute limit measured from
login — it is deliberately NOT reset by navigating between tools. The
clock is started once (start_session is idempotent) and enforced both
by an app-level watchdog (main.py) and lazily on navigation, so the
timeout still fires while the user is inside a tool or the window is
backgrounded.

It also tracks the one long-running job (commission run, decommission
scan/delete, invite batch) so navigation, theme switches and logout can
warn before abandoning it, and so logout/expiry can cancel it instead of
letting it keep calling the API in the background.
"""

import time
from typing import NamedTuple

from apis.external_api import VerkadaExternalAPIClient
from apis.internal_api import VerkadaInternalAPIClient
from constants import (
    SESSION_EXTENSION_MINUTES,
    SESSION_MAX_EXTENSIONS,
    SESSION_TIMEOUT_MINUTES,
)
from utils.cancellation import CancellationToken


class _ActiveRun(NamedTuple):
    label: str
    token: CancellationToken


_internal_client: VerkadaInternalAPIClient | None = None
_external_client: VerkadaExternalAPIClient | None = None
_session_start: float | None = None
_extensions_used: int = 0
_active_run: _ActiveRun | None = None


def set_internal_client(client: VerkadaInternalAPIClient) -> None:
    """Store the authenticated internal API client for the current session."""
    global _internal_client
    _internal_client = client


def get_internal_client() -> VerkadaInternalAPIClient:
    """Return the active internal client; raise if the user isn't logged in."""
    if not isinstance(_internal_client, VerkadaInternalAPIClient):
        raise RuntimeError("Internal client is not available. Please log in again.")
    return _internal_client


def set_external_client(client: VerkadaExternalAPIClient) -> None:
    """Store the authenticated external (public-API) client for this session."""
    global _external_client
    _external_client = client


def get_external_client() -> VerkadaExternalAPIClient:
    """Return the active external client; raise if it hasn't been connected."""
    if not isinstance(_external_client, VerkadaExternalAPIClient):
        raise RuntimeError("External client is not available. Please connect first.")
    return _external_client


def start_session():
    """Start the session clock if it isn't already running.

    Idempotent: callers fire this whenever an authenticated screen mounts,
    but only the first call after a login (or re-login) sets the clock.
    Navigating between tools therefore neither resets nor extends the
    timeout — clear_session() is the only thing that stops it.
    """
    global _session_start
    if _session_start is None:
        _session_start = time.time()


def session_active() -> bool:
    """True once the session clock is running (i.e. the user is logged in)."""
    return _session_start is not None


def get_session_remaining() -> float:
    """Return seconds left in the session, or 0 if it's expired/not started."""
    if _session_start is None:
        return 0.0
    elapsed = time.time() - _session_start
    remaining = (SESSION_TIMEOUT_MINUTES * 60) - elapsed
    return max(0.0, remaining)


def is_session_expired() -> bool:
    """True if the session has run past SESSION_TIMEOUT_MINUTES."""
    return get_session_remaining() <= 0


def can_extend() -> bool:
    """True if the session can still be extended (under the per-session cap)."""
    return session_active() and _extensions_used < SESSION_MAX_EXTENSIONS


def extend_session() -> bool:
    """Grant one bounded extension by pushing the start time forward.

    Adds SESSION_EXTENSION_MINUTES to the remaining budget, up to
    SESSION_MAX_EXTENSIONS times. Returns True if an extension was granted.
    The absolute-limit model is preserved: extensions are finite, not an
    unlimited reset.
    """
    global _session_start, _extensions_used
    if not can_extend() or _session_start is None:
        return False
    _session_start += SESSION_EXTENSION_MINUTES * 60
    _extensions_used += 1
    return True


def begin_run(label: str, token: CancellationToken) -> bool:
    """Register `token` as the active long-running job.

    Returns False (and registers nothing) while another job is still
    registered — including one that was cancelled but hasn't finished its
    in-flight API call yet — so two runs never overlap.
    """
    global _active_run
    if _active_run is not None:
        return False
    _active_run = _ActiveRun(label, token)
    return True


def end_run(token: CancellationToken) -> None:
    """Unregister the job owning `token` (no-op for any other token)."""
    global _active_run
    if _active_run is not None and _active_run.token is token:
        _active_run = None


def running_job() -> str | None:
    """Label of the job that is still running, or None.

    A job that has been asked to stop is not "running": leaving it is
    already safe, it just hasn't unregistered yet.
    """
    if _active_run is None or _active_run.token.is_cancelled:
        return None
    return _active_run.label


def cancel_run() -> None:
    """Ask the active job to stop after its current step."""
    if _active_run is not None:
        _active_run.token.cancel()


def clear_session():
    """Drop the cached clients and start time. Called on logout/timeout.

    Also cancels any running job: its coroutine keeps its own client
    reference, so without this a decommission would carry on deleting
    after the user was logged out.
    """
    global _internal_client, _external_client, _session_start
    global _extensions_used
    cancel_run()
    _internal_client = None
    _external_client = None
    _session_start = None
    _extensions_used = 0
