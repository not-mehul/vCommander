"""Read-only access check: org lookup, session validity, device inventory.

Usage: python tools/live/check.py
"""

import json

from harness import make_client, quiet, serials

client, shard = make_client()
print(
    f"shard={shard.name} region={shard.readable_name} domain={shard.domain} "
    f"public API=https://{shard.public_api_region}.verkada.com"
)
try:
    print(f"session OK: {len(quiet(client.get_site))} site(s)")
except Exception as ex:  # a revoked/expired session lands here
    raise SystemExit(f"session check FAILED: {type(ex).__name__}: {str(ex)[:200]}") from None

found = {}
for kind, getter in (("cameras", client.get_camera), ("unassigned", client.get_unassigned_device)):
    try:
        found[kind] = json.dumps(quiet(getter)).upper()
    except Exception as ex:  # camera.list needs a site permission (or GSA)
        print(f"  {kind} not listed: {str(ex)[:120]}")
for kind, serial in serials().items():
    where = [k for k, blob in found.items() if serial in blob] or ["not in org"]
    print(f"  {kind:20} {', '.join(where)}")
