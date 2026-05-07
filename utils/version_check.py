"""GitHub release version check.

Hits the GitHub Releases API on startup and compares the latest tag
against APP_VERSION. Failures (no network, rate limit, no releases yet)
are swallowed — the check is best-effort and must never block startup.
"""

from __future__ import annotations

import requests
from packaging.version import InvalidVersion, Version

from constants import APP_VERSION, GITHUB_REPO


def _normalize(tag: str) -> str:
    """Strip a leading 'v' so 'v3.1' and '3.1' compare equal."""
    return tag[1:] if tag.startswith(("v", "V")) else tag


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
        latest = Version(_normalize(tag))
        current = Version(_normalize(APP_VERSION))
        print(f"Comparing: latest={latest}, current={current}")
        if latest > current:
            return (str(latest), html_url)
    except (requests.RequestException, ValueError, InvalidVersion):
        return None
    return None
