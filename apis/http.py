"""Shared HTTP session construction for the API clients.

Previously each client configured only half of the reliability story: the
external client mounted a retry adapter but passed no timeout, while the
internal client passed a per-call timeout but had no retry adapter. A retry
adapter alone does NOT impose a socket timeout — a peer that accepts the
connection then never responds hangs forever, pinning one of the executor's
few worker threads. `build_session()` gives both clients a single Session that
carries retries AND a default connect/read timeout, closing that gap in one
place.

Retries are deliberately asymmetric. Idempotent verbs (GET/PUT/DELETE) are
retried on connection errors, read timeouts and 5xx. POST — which creates
sites, claims devices, sends invites — is only retried when the server
provably did no work: a connection that never opened, or a 429 rejection.
A 502 or a read timeout can arrive *after* the server committed the create,
so replaying it would make a duplicate. The same holds for a PUT that
creates (Command's schedule upsert without an id): such endpoints are marked
replayable=False in the registry and sent through build_session(replay=False).
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from constants import DEFAULT_TIMEOUT

# Verbs that are safe to replay after the server may have processed them.
IDEMPOTENT_METHODS = frozenset({"GET", "PUT", "DELETE"})
# For replay=False: only verbs with no side effects (the app sends neither).
# Not an empty set — urllib3 2.x reads an empty allowed_methods as "any verb".
_SAFE_ONLY_METHODS = frozenset({"HEAD", "OPTIONS"})


class _SafeRetry(Retry):
    """Retry policy that never replays a non-idempotent request blindly.

    `allowed_methods` excludes POST, which already stops urllib3 from
    retrying POST on read errors and on `status_forcelist` codes (connect
    errors are still retried — the request never left). The one status a
    POST may retry on is 429: the server rejected it without acting.
    """

    def is_retry(
        self, method: str, status_code: int, has_retry_after: bool = False
    ) -> bool:
        if method and method.upper() not in (self.allowed_methods or ()):
            return status_code == 429 and bool(self.total)
        return super().is_retry(method, status_code, has_retry_after)


class _TimeoutRetryAdapter(HTTPAdapter):
    """HTTPAdapter that applies a default timeout when a caller omits one.

    `Retry` handles transient status/connection failures but leaves the socket
    timeout unset. Injecting a default here means every request through the
    session is bounded, without having to thread `timeout=` through each call
    site (callers that pass their own `timeout` still win).
    """

    def __init__(self, *args, timeout: float = DEFAULT_TIMEOUT, **kwargs) -> None:
        self._timeout = timeout
        super().__init__(*args, **kwargs)

    def send(self, request, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = self._timeout
        return super().send(request, **kwargs)


def build_session(
    timeout: float = DEFAULT_TIMEOUT, *, replay: bool = True
) -> requests.Session:
    """Return a Session with retry + a default timeout mounted on http/https.

    replay=False gives a session that treats every verb like POST: retried
    only when the request never left (connection errors) or on 429. For
    requests the registry marks non-replayable, e.g. a PUT that creates.
    """
    session = requests.Session()
    retries = _SafeRetry(
        total=4,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=IDEMPOTENT_METHODS if replay else _SAFE_ONLY_METHODS,
    )
    adapter = _TimeoutRetryAdapter(max_retries=retries, timeout=timeout)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
