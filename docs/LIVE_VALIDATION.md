# Live validation log

Results of running vCommander against a real test org with the scripts in
`tools/live/`. Newest first.

## 2026-10-26 — Ohio shard (`prod-us-ohio`) test org

**Passed end to end** (real flows, headless, same code as the app):

| Run | Result |
|---|---|
| Org lookup, session, temporary API key, token at `api.oh.verkada.com` | OK |
| Commission ESS | 21/21 steps |
| Commission VSSL | OK after the "HQ" site fix (first run: site already existed) |
| Commission VSSE | 14/14 |
| Commission AS | 25/25 |
| Decommission scan / delete / release (4 runs) | every delete returned 200; GSA turned off and key deleted every time |

All 9 device types were claimed and configured; the running user was always
excluded from user deletion.

**API changes found and fixed**

1. Org hosts are per shard (`<service>.prod-us-ohio.verkada.com`); resolved
   before login via `org/validate_short_name`.
2. Ohio's public API is `api.oh.verkada.com`; `api.verkada.com` rejects an
   Ohio key with `409 Authentication error`. Mapped by shard name.
3. `host_metadata.public_api_endpoint` does not name the public API
   (`api` or `apiadmin`); ignored.
4. Command rejects duplicate site names under one parent; Commission reuses
   the existing site. It accepts duplicate building names; Commission now
   reuses the existing building too.

Paths, payloads, headers and response fields matched on every call made.

**Web app vs. vCommander (from the HARs of the Command web app)**

18 of 149 registry endpoints appear in the HARs. Differences:

- `site.list`: the web app adds `targetPermissions`; verified live to make
  no difference.
- `user.list`: the web app searched for one user (`query.terms`), a
  different use; vCommander's `paging.sortOrder` and `userDirectoryIds`
  were not seen.
- `camera.list`: the web app sends its full filter set; vCommander's subset
  works.
- `login`/`auth.twofactor.sms.new`: the web app used magic-link login
  (`magicToken`, `backendEnvironment`); vCommander uses password login.

**Pending** (procedure: [`LIVE_VALIDATION_RUNBOOK.md`](LIVE_VALIDATION_RUNBOOK.md)): record the web app for the remaining endpoints (the session
used for this run was revoked when the headless web app logged out; the
recorder now blocks logout) and drop payload fields the web app doesn't
send, after checking each live.
