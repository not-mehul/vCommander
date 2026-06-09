"""Process-wide session state.

Holds the authenticated internal/external API clients and the session
start time so any view can reach them without prop-drilling.

The SESSION_TIMEOUT_MINUTES window is an absolute limit measured from
login — it is deliberately NOT reset by navigating between tools. The
clock is started once (start_session is idempotent) and enforced both
by an app-level watchdog (main.py) and lazily on navigation, so the
timeout still fires while the user is inside a tool or the window is
backgrounded.
"""

import time

from apis.external_api import VerkadaExternalAPIClient
from apis.internal_api import VerkadaInternalAPIClient
from constants import SESSION_TIMEOUT_MINUTES

_internal_client: VerkadaInternalAPIClient | None = None
_external_client: VerkadaExternalAPIClient | None = None
_session_start: float | None = None
_warning_shown: bool = False


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
    global _session_start, _warning_shown
    if _session_start is None:
        _session_start = time.time()
        _warning_shown = False


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


def mark_warning_shown() -> None:
    """Record that the pre-expiry warning has been shown for this session."""
    global _warning_shown
    _warning_shown = True


def was_warning_shown() -> bool:
    """True if the pre-expiry warning has already fired this session."""
    return _warning_shown


def clear_session():
    """Drop the cached clients and start time. Called on logout/timeout."""
    global _internal_client, _external_client, _session_start, _warning_shown
    _internal_client = None
    _external_client = None
    _session_start = None
    _warning_shown = False
