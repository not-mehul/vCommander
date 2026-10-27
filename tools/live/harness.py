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

import atexit
import contextlib
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests

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
            # Serials also match with or without dashes (Command shows them dashed).
            pattern = "-?".join(re.escape(c) for c in secret.replace("-", ""))
            text = re.sub(pattern, "<redacted>", text, flags=re.I)
    return EMAIL.sub("<email>", UUID.sub("<id>", text))


# JSON keys whose values are credentials (API key secrets, tokens, passwords);
# names, ids and expiry times of keys are kept.
_SECRET_KEY = re.compile(r"(api_?key|secret|token|password|cookie)(?!.*(name|id|expir))", re.I)
OUT = Path(os.environ.get("LIVE_OUT", Path.home() / ".vcommander-live"))


def scrub(value):
    """Blank credential values in a decoded JSON value."""
    if isinstance(value, dict):
        return {
            k: "<secret>" if _SECRET_KEY.search(k) and isinstance(v, str) else scrub(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def _redact_body(raw) -> str:
    if not raw:
        return ""
    text = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
    try:
        text = json.dumps(scrub(json.loads(text)), separators=(",", ":"))
    except ValueError:
        pass
    return redact(text)


def record(name: str) -> list[dict]:
    """Record every HTTP request vCommander makes (internal and public API).

    Wraps requests.Session.send, so it covers clients the views create
    themselves. Entries use the web/session.js format ({t, method, host,
    path, body, status, resp}), redacted, and are written to $LIVE_OUT/<name>
    at exit. Headers are never recorded.
    """
    log: list[dict] = []
    send = requests.Session.send

    def recording_send(self, request, **kwargs):
        url = urlsplit(request.url)
        entry = {
            "t": int(time.time() * 1000),
            "method": request.method,
            "host": redact(url.hostname or ""),
            "path": redact(url.path + (f"?{url.query}" if url.query else "")),
            "body": _redact_body(request.body),
            "status": 0,
            "resp": "",
        }
        log.append(entry)
        response = send(self, request, **kwargs)
        entry["status"] = response.status_code
        entry["resp"] = _redact_body(response.content)[:4000]
        return response

    requests.Session.send = recording_send

    def save():
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / name).write_text(json.dumps(log, indent=1))
        print(f"recording: {len(log)} calls -> $LIVE_OUT/{name}")

    atexit.register(save)
    return log


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
    """An internal client on the org's shard, authenticated by the session.

    With LIVE_RECORD=<file>.json set, every call is recorded (see record()).
    """
    if os.environ.get("LIVE_RECORD"):
        record(os.environ["LIVE_RECORD"])
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
