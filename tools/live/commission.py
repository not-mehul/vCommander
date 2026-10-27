"""Run vCommander's real Commission flow headlessly for one template.

Usage: python tools/live/commission.py <ESS|ACSL|ACSE|VSSL|VSSE|AS>
CHANGES THE ORG: claims devices and applies the template's org settings.
"""

import asyncio
import contextlib
import io
import os
import re
import sys

from harness import SERIAL_VARS, Event, FakePage, make_client, redact

import pages.commission_view as cv

TEMPLATE = sys.argv[1]
FIELD_TO_VAR = {label: var for var, label in SERIAL_VARS.items()}

client, _ = make_client()
page = FakePage()
cv.get_internal_client = lambda: client
view = cv.CommissionView(lambda route: None)
view.page = page
view.template_dropdown.value = TEMPLATE
view._on_template_change(Event(page))
for name, field in view._device_fields.items():
    field.value = (
        "VCTEST1" if name == "License Plate" else os.environ[FIELD_TO_VAR[name]].strip()
    )

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    asyncio.run(view._on_commission(Event(page)))
print(f"== {TEMPLATE}: {view._steps_done} ok, {view._steps_failed} failed")
for line in view._run_log:
    print("  ", redact(line)[:300])
print("non-2xx / warn / error log lines:")
for line in buf.getvalue().splitlines():
    if re.search(r"status: [45]\d\d|\[(ERROR|WARN)\]", line):
        print("  ", redact(re.sub(r"\| resp: (.{0,250}).*", r"| resp: \1", line)))
