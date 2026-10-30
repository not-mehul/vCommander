"""Fire-and-forget asyncio tasks that are safe from garbage collection.

asyncio keeps only a weak reference to a bare `create_task()` result, so a
background task nobody awaits can be collected mid-run. `spawn` holds a
strong reference until the task finishes. Used for app-lifetime loops
(session watchdog, version check) and for cleanup a view starts as it is
being left (e.g. decommission reverting Global Site Admin).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine

_BACKGROUND_TASKS: set[asyncio.Task] = set()


def spawn(coro: Coroutine) -> asyncio.Task:
    """Start `coro` as a background task and keep it alive until done."""
    task = asyncio.get_running_loop().create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task
