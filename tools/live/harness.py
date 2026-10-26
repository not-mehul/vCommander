"""Shared setup for the live checks: a vCommander internal client built from
a browser session taken from the environment, plus redaction helpers.

The client is built from session cookies instead of a password login, so an
org that enforces 2FA can be tested without an SMS code. Nothing here prints
tokens, ids, emails, the org short name or device serials.

Environment (see README.md): VERKADA_ORG, VERKADA_EMAIL, COOKIE,
X_VERKADA_TOKEN, X_VERKADA_USER_ID, X_VERKADA_ORGANIZATION_ID, and one
variable per device type holding its serial (SERIAL_VARS).
"""

from __future__ import annotations

import contextlib
import io
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from apis.internal_api import VerkadaInternalAPIClient  # noqa: E402

# Device-type variable name -> the device field label used by Commission.
SERIAL_VARS = {
    "Access_Controller": "Access Controller",
    "Access_Station_Pro": "Access Station Pro",
    "Alarm_Panel": "Alarm Panel",
    "Bullet": "Bullet",
    "Command_Connector": "Command Connector",
    "Dome": "Dome",
    "Fisheye": "Fisheye",
    "Keypad": "Keypad",
    "PTZ": "PTZ",
}

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_LOG_LINE = re.compile(r"\[[^]]+\] (\S+) (\S+) \| req: .* \| status: (\S+)")


def serials() -> dict[str, str]:
    """Device-type variable -> serial (upper-case), for the ones that are set."""
    return {v: os.environ[v].strip().upper() for v in SERIAL_VARS if os.environ.get(v)}


def redact(text: str) -> str:
    """Strip serials, the org short name, emails and ids from text."""
    for secret in [*serials().values(), os.environ.get("VERKADA_ORG", "")]:
        if secret:
            text = re.sub(re.escape(secret), "<redacted>", text, flags=re.I)
    return EMAIL.sub("<email>", UUID.sub("<id>", text))


def quiet(fn, *args, **kwargs):
    """Run fn with the API log captured; print one redacted line per call."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            return fn(*args, **kwargs)
    finally:
        for line in buf.getvalue().splitlines():
            m = _LOG_LINE.match(line)
            if m:
                print(f"    {m[1]} {redact(m[2])} -> {m[3]}")


def make_client():
    """An internal client on the org's shard, authenticated by the session."""
    client = VerkadaInternalAPIClient(
        os.environ["VERKADA_EMAIL"], "unused", os.environ["VERKADA_ORG"]
    )
    shard = quiet(client.resolve_shard)
    jar = dict(
        p.strip().split("=", 1) for p in os.environ["COOKIE"].split(";") if "=" in p
    )
    for name in ("auth", "org", "usr", "token"):  # session cookies only
        client.session.cookies.set(name, jar[name])
    client.auth_data = {
        "organizationId": os.environ["X_VERKADA_ORGANIZATION_ID"],
        "csrfToken": os.environ["X_VERKADA_TOKEN"],
        "adminUserId": os.environ["X_VERKADA_USER_ID"],
    }
    return client, shard


class FakePage:
    """Just enough of ft.Page to drive a view without a running app."""

    def update(self, *controls):
        pass

    def show_dialog(self, dialog):
        pass

    def pop_dialog(self):
        pass


class Event:
    def __init__(self, page, control=None):
        self.page, self.control = page, control
