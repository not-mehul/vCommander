"""Input formatting/validation for device serial numbers.

Verkada device serials are twelve alphanumerics shown in three groups of
four, e.g. ``A1A1-B2B2-C3C3``. The commission form masks its serial fields
as the user types, so these helpers are the single definition of the
format: `format_serial` for the mask, `is_valid_serial` for the gate.

License plates are not serials — they are free text and never go through
either helper.
"""

from __future__ import annotations

import re

SERIAL_GROUP_LEN = 4
SERIAL_GROUPS = 3
# 12 alphanumerics, plus the 2 separators between the 3 groups.
SERIAL_LEN = SERIAL_GROUP_LEN * SERIAL_GROUPS
SERIAL_DISPLAY_LEN = SERIAL_LEN + SERIAL_GROUPS - 1

SERIAL_PLACEHOLDER = "XXXX-XXXX-XXXX"

_NOT_SERIAL_CHAR = re.compile(r"[^0-9A-Z]")
_SERIAL_RE = re.compile(
    rf"^[0-9A-Z]{{{SERIAL_GROUP_LEN}}}"
    rf"(?:-[0-9A-Z]{{{SERIAL_GROUP_LEN}}}){{{SERIAL_GROUPS - 1}}}$"
)


def format_serial(raw: str | None) -> str:
    """
    Coerce free-typed text into the ``A1A1-B2B2-C3C3`` mask.

    Upper-cases, drops everything that is not an ASCII alphanumeric (so a
    typed or pasted separator is re-derived rather than trusted), caps the
    result at twelve characters, then regroups in fours. Anything shorter
    formats as far as it goes — ``"a1a1b"`` becomes ``"A1A1-B"`` — so the
    mask can be re-applied on every keystroke without fighting the typist.
    """
    chars = _NOT_SERIAL_CHAR.sub("", (raw or "").upper())[:SERIAL_LEN]
    return "-".join(
        chars[i : i + SERIAL_GROUP_LEN] for i in range(0, len(chars), SERIAL_GROUP_LEN)
    )


def is_valid_serial(value: str | None) -> bool:
    """True only for a complete serial; partial input is rejected."""
    return bool(_SERIAL_RE.match((value or "").strip()))


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(value: str | None) -> bool:
    """Loose shape check (something@domain.tld) for inline form feedback.

    Deliberately permissive: the server is the real validator; this only
    catches typos like a missing "@" or domain before a run starts.
    """
    return bool(_EMAIL_RE.match((value or "").strip()))
