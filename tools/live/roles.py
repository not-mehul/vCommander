"""Read-only: the session user's access-control admin roles.

Usage: python tools/live/roles.py
"""

from harness import make_client, quiet

client, _ = make_client()
held = sorted(r for r in quiet(client.get_org_role_keys) if r.startswith("ACCESS_CONTROL"))
print("access roles:", held or "none")
