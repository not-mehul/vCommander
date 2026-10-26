"""Report export helpers.

Writes run reports to the user's Downloads folder, matching the convention
already used by the decommission asset-list export
(`vCommander_<prefix>_<timestamp>.<ext>`).
"""

from __future__ import annotations

import csv
import os
from datetime import datetime


def _downloads_path(prefix: str, ext: str) -> str:
    downloads = os.path.expanduser("~/Downloads")
    os.makedirs(downloads, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(downloads, f"vCommander_{prefix}_{timestamp}.{ext}")


def export_csv(rows: list[dict], fieldnames: list[str], prefix: str) -> str:
    """Write `rows` as CSV and return the file path."""
    path = _downloads_path(prefix, "csv")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path

