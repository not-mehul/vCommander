"""Shared thread pool for running blocking I/O off the Flet UI loop.

Views submit `requests` calls to this executor via
`asyncio.get_event_loop().run_in_executor(_executor, ...)` so the GUI
stays responsive while API calls are in flight.
"""

from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=4)
