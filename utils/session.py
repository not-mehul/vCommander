"""Process-wide session state.

Holds the authenticated internal/external API clients and the session
start time so any view can reach them without prop-drilling. The
SESSION_TIMEOUT_MINUTES window is enforced cooperatively by HomeView's
timer; when it expires the user is bounced back to the login screen.
"""

import time

from apis.external_api import VerkadaExternalAPIClient
from apis.internal_api import VerkadaInternalAPIClient
from constants import SESSION_TIMEOUT_MINUTES

_internal_client: VerkadaInternalAPIClient | None = None
_external_client: VerkadaExternalAPIClient | None = None
_session_start: float | None = None


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
    """Mark the session start time as 'now' (called after successful login)."""
    global _session_start
    _session_start = time.time()


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


def clear_session():
    """Drop the cached clients and start time. Called on logout/timeout."""
    global _internal_client, _external_client, _session_start
    _internal_client = None
    _external_client = None
    _session_start = None
