"""Run vCommander's real Users-tool invite batch headlessly.

Usage: python tools/live/invite.py 1 2 3
Invites "VC Test <n>" at the plus address <user>+test<n>@<domain> of
VERKADA_EMAIL for each number given. LIVE_GROUP=1 also runs the group step.
CHANGES THE ORG: invites users (decommission.py deletes "VC Test" users).
"""

import asyncio
import contextlib
import io
import os
import re
import sys

from harness import Event, FakePage, make_client, redact

import pages.users_view as uv

local, domain = os.environ["VERKADA_EMAIL"].strip().split("@")
client, _ = make_client()
page = FakePage()
uv.get_internal_client = lambda: client
view = uv.UsersView(lambda route: None)
view.page = page
for n in sys.argv[1:]:
    view._participants_column.controls.append(
        view._create_participant_row("VC Test", n, f"{local}+test{n}@{domain}")
    )
view._add_to_group_switch.value = bool(os.environ.get("LIVE_GROUP"))

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    asyncio.run(view._on_invite_all(Event(page)))
for row in view._invite_progress.controls:
    if hasattr(row, "text"):
        print("  ", redact(row.text))


def texts(control):
    """Every Text value inside a control (the result banner)."""
    value = getattr(control, "value", None)
    found = [value] if isinstance(value, str) else []
    for child in [getattr(control, "content", None), *getattr(control, "controls", [])]:
        if child is not None:
            found += texts(child)
    return found


print("result:", redact(" ".join(texts(view._invite_result))))
print("non-2xx / warn / error log lines:")
for line in buf.getvalue().splitlines():
    if re.search(r"status: [45]\d\d|\[(ERROR|WARN)\]", line):
        print("  ", redact(re.sub(r"\| resp: (.{0,250}).*", r"| resp: \1", line)))
