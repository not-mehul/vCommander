"""GitHub release version check.

Hits the GitHub Releases API on startup and compares the latest tag
against APP_VERSION. Failures (no network, rate limit, no releases yet)
are swallowed — the check is best-effort and must never block startup.
"""

from __future__ import annotations

import re

import requests

from constants import APP_VERSION, GITHUB_REPO


def _parse(version: str) -> tuple[int, ...]:
    """Turn '3.1.2' or 'v3.1' into (3, 1, 2) / (3, 1). Non-numeric parts are dropped."""
    cleaned = version[1:] if version.startswith(("v", "V")) else version
    parts = re.findall(r"\d+", cleaned)
    return tuple(int(p) for p in parts)


def check_for_update(timeout: float = 3.0) -> tuple[str, str] | None:
    """Return (latest_version, release_url) if a newer release exists, else None."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    print(f"Checking for update: {url}")
    try:
        resp = requests.get(
            url, timeout=timeout, headers={"Accept": "application/vnd.github+json"}
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        tag = data.get("tag_name")
        html_url = data.get("html_url", f"https://github.com/{GITHUB_REPO}/releases")
        if not tag:
            return None
        latest = _parse(tag)
        current = _parse(APP_VERSION)
        if latest and current and latest > current:
            return (tag.lstrip("vV"), html_url)
    except (requests.RequestException, ValueError):
        return None
    return None
