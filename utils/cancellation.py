"""Cooperative cancellation primitive for long-running orchestration flows.

Used by the Commission and Decommission orchestrators: the orchestrator
checks `is_cancelled` between steps; the Cancel button calls `cancel()`.
Cancellation is cooperative — an in-flight API call is allowed to
complete (we don't try to abort the underlying HTTP request) and the
loop bails before the next step. That keeps device state consistent
(no half-deleted asset, no partial commission step).
"""

from __future__ import annotations


class CancellationToken:
    __slots__ = ("_cancelled",)

    def __init__(self) -> None:
        self._cancelled = False

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

    def reset(self) -> None:
        """Clear the flag so the token can be reused for a new run."""
        self._cancelled = False
