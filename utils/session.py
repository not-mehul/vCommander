import time

from apis.external_api import VerkadaExternalAPIClient
from apis.internal_api import VerkadaInternalAPIClient
from constants import SESSION_TIMEOUT_MINUTES

_internal_client: VerkadaInternalAPIClient | None = None
_external_client: VerkadaExternalAPIClient | None = None
_session_start: float | None = None


def set_internal_client(client: VerkadaInternalAPIClient) -> None:
    global _internal_client
    _internal_client = client


def get_internal_client() -> VerkadaInternalAPIClient:
    if not isinstance(_internal_client, VerkadaInternalAPIClient):
        raise RuntimeError("Internal client is not available. Please log in again.")
    return _internal_client


def set_external_client(client: VerkadaExternalAPIClient) -> None:
    global _external_client
    _external_client = client


def get_external_client() -> VerkadaExternalAPIClient:
    if not isinstance(_external_client, VerkadaExternalAPIClient):
        raise RuntimeError("External client is not available. Please connect first.")
    return _external_client


def start_session():
    global _session_start
    _session_start = time.time()


def get_session_remaining() -> float:
    if _session_start is None:
        return 0.0
    elapsed = time.time() - _session_start
    remaining = (SESSION_TIMEOUT_MINUTES * 60) - elapsed
    return max(0.0, remaining)


def is_session_expired() -> bool:
    return get_session_remaining() <= 0


def clear_session():
    global _internal_client, _external_client, _session_start
    _internal_client = None
    _external_client = None
    _session_start = None
