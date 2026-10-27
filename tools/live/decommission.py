"""Run vCommander's real Decommission flow headlessly.

Usage:
  python tools/live/decommission.py scan
      Scan, print the review list, then release the org (Global Site Admin
      off, temporary API key deleted). Deletes nothing.
  python tools/live/decommission.py delete ["Category,Category"]
      DELETES FOR REAL: rescan and delete everything the scan pre-selects,
      except the listed categories (e.g. "Command Users"), as if unticked.
"""

import asyncio
import contextlib
import io
import re
import sys

from harness import Event, FakePage, make_client, redact

import pages.decommission_view as dv

MODE = sys.argv[1]
KEEP = sys.argv[2].split(",") if len(sys.argv) > 2 else []

client, _ = make_client()
page = FakePage()
dv.get_internal_client = lambda: client
view = dv.DecommissionView(lambda route: None)
view.page = page


async def main():
    await view._on_scan(Event(page))
    print(f"state after scan: {view._state}")
    for cat in dv.ASSET_CATEGORIES:
        items = view._assets.get(cat) or []
        if items:
            names = "(names hidden)" if cat == "Command Users" else ", ".join(
                redact(str(i.get("name") or i.get("id")))[:40] for i in items[:6]
            )
            more = f" (+{len(items) - 6} more)" if len(items) > 6 else ""
            sel = len(view._selected.get(cat, ()))
            print(f"  {cat:24} {len(items):3} found, {sel:3} selected: {names}{more}")
    if MODE == "delete" and view._state == dv.REVIEW:
        for cat in KEEP:
            view._selected[cat] = set()
        print(f"kept (unticked): {KEEP}")
        view._set_state(page, dv.CONFIRM)
        await view._on_delete(Event(page))
        print(f"state after delete: {view._state}, failed: {view._failed_total}")
        for cat, (ok, planned) in view._results.items():
            print(f"  deleted {cat:24} {ok}/{planned}")
    else:
        await view._release_org()
    print("cleanup:", [redact(f"{kind}: {msg}") for kind, msg in view._cleanup])


buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    asyncio.run(main())
lines = buf.getvalue().splitlines()
print("\n".join(line for line in lines if not line.startswith("[")))
print("non-2xx / warn / error log lines:")
for line in lines:
    if re.search(r"status: [45]\d\d|\[(ERROR|WARN)\]", line):
        print("  ", redact(re.sub(r"\| resp: (.{0,200}).*", r"| resp: \1", line)))
