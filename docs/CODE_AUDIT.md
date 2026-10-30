# vCommander — Code Audit (v3.5, October 2026)

Full-codebase audit after the v3.5 work (shard support, batching,
internal-only Decommission, participant groups, ACSE permission reset).
It replaces the July/August audit that lived at this path (see git
history); everything that audit listed as fixed was re-checked and is not
repeated.

> Line numbers are for commit `6087a98` and will drift.

## How this was checked

| Check | How |
|---|---|
| Reading | Every module in `apis/`, `pages/`, `utils/`, `main.py`, `constants.py`; the request, retry, auth, scan, delete and invite paths line by line. |
| Static analysis | `ruff` with an extended rule set (bugbear, blind-except, security, pylint, perf), `vulture` checked against the string-dispatch maps in `constants.py`, a script listing client methods nothing references. |
| Coverage | `pytest --cov` over the 223 tests. |
| Reproduction | Findings marked **(verified)** were reproduced with a script against the real code; the role finding also against the live test org (read-only). |

## Status (fixes after the audit)

| Item | Status |
|---|---|
| H1 role check | **Fixed** (`3d2710e`): only grants with `granteeId == user_id` count. |
| M1 schedule-create replay | **Fixed** (`6b2bd5b`): registry entries can be `replayable=False`; such requests go through a session that only retries connection errors and 429. Live: ACSL made exactly one schedule. |
| M6 theme switch | **Fixed** (`acfd2e3`): the Decommission scan, selection and pending org release are handed to the rebuilt screen. |
| M7 client tests | **Fixed** (`87ed383`): contract tests for every call the app makes; `internal_api.py` coverage 57% → 85%. |
| Dead code | **Removed** (`3925b73`): about 1,100 lines; the endpoint registry keeps every entry. |
| L1 update check | **Fixed** (`8223850`). |
| L12 log growth | **Fixed** (`8223850`): entries older than 30 days are dropped at startup. PII in the log remains. |
| Everything else | Open. |

## Summary

| Severity | Count | Items |
|---|---|---|
| High | 3 | H1 role check counts other users' roles · H2 password stored and revealable · H3 org left elevated when the app closes mid-Decommission |
| Medium | 7 | M1 retried "create" PUT duplicates a schedule · M2 kits file can stop Commission opening · M3 license plate not URL-encoded · M4 internal build ships an API key · M5 old archives never deleted · M6 theme switch discards a scan · M7 client code is the least tested |
| Low | 15 | L1–L15 |
| Dead code | 23 methods | see "Dead code" |

---

## High

### H1. The access-role check counts other users' roles as the signed-in user's (verified)

`get_org_role_keys()` (`apis/internal_api.py:1409`) reads the user's roles
through `org/set_user_permissions` with `returnPermissions`, and keeps every
`roleGrant` in the response. That response carries **other users' grants
too**: on the test org it returned 6 grants from 2 grantees for the
signed-in user. Nothing filters on `granteeId`.

- **Effect:** if anyone else in the org holds Access System Admin or Access
  User Admin — common after an access-control lab, where attendees are often
  given them — Decommission believes the trainer already holds the role and
  doesn't grant it. Access-control deletes then fail with "Insufficient
  permissions". The Users tool's access-group step (participant groups,
  VCE Access Group, AF64 level) fails the same way.
- **Reproduced:** a response with `ORG_MANAGER` for the signed-in user and
  `ACCESS_CONTROL_SYSTEM_ADMIN` for another user → `get_org_role_keys()`
  reports Access System Admin as held.
- **Fix:** keep only grants with `granteeId == self.user_id` (one-line
  filter), and add a test with a mixed response.

### H2. The login password is stored in plain text and can be revealed from the login screen

`LoginView._save` (`pages/login_view.py:192`) writes email, **password** and
org to `vcommander.db` on every login, with no opt-out, before 2FA has
succeeded. The database (and `prefs.json`, `api_calls.log`) are created with
the default file mode (world-readable on Linux under a typical umask). The
login screen pre-fills the saved password in a field with
`can_reveal_password=True`, so after a logout or session timeout anyone at
the machine can reveal it.

The Users tool stores the source org's public-API key the same way
(`save_import_settings`).

- **Fix:** store secrets in the OS keychain (`keyring`), or at least make
  "Remember password" opt-in, never pre-fill a revealable password, and
  create the data files with mode `0600`.

### H3. Closing the app after a scan leaves Global Site Admin on, org-wide

After a Decommission scan the org stays elevated — Global Site Admin on and
both access admin roles on the trainer — for as long as the Review/Select
screens are open. Leaving the screen, logging out and session expiry all
release it (`on_leave` → `_release_org`). Closing the window, quitting, or a
crash does not: there is no window-close handler anywhere (`main.py`,
`pages/`).

- **Effect:** Global Site Admin is an org-wide setting; left on, every admin
  sees every site, which is exactly what the templates turn off.
- **Fix:** handle the window close event (`page.window.prevent_close` +
  `on_event`) to run `_release_org()` before exiting; and on the next scan,
  warn if Global Site Admin is already on.

---

## Medium

### M1. A retried schedule "create" can make a duplicate (verified)

`apis/http.py:29` treats every PUT as safe to replay and retries it on read
timeouts and 5xx. But `create_mfa_schedule` (`apis/internal_api.py:2066`,
ACSL's "[DO NOT TOUCH] AF64 2FA") creates a schedule with a PUT that has no
id. **Reproduced:** one schedule PUT answered with 502 reached a local
server 5 times. A slow first response that Command actually processed would
leave duplicate schedules. It is the only PUT that creates; the others
(schedule delete) are idempotent.

- **Fix:** let endpoints opt out of replay (e.g. `idempotent=False` on the
  registry entry) and use it for `schedule.create.mfa`.

### M2. A kits file saved by Excel stops Commission from opening (verified)

`_load_kits` (`pages/commission_view.py:151`) runs when the view is built,
opens the file without an encoding, and indexes `r["Kit Name"]`. Excel's
"CSV UTF-8" adds a byte-order mark, so the header becomes `﻿Kit Name`
and the view raises `KeyError` — Commission won't open. A missing kits file
does the same. `kits.internal.csv` is the file most likely to be edited in
Excel.

- **Fix:** `open(path, encoding="utf-8-sig", newline="")`, skip malformed
  rows, and catch file errors (no kits instead of no Commission).

### M3. Path parameters aren't URL-encoded (verified)

`build_url` (`apis/endpoints.py:418`) inserts path values as-is. The VSSL
license plate is free text and goes into
`access/v2/user/license_plate/{license_plate}`: **reproduced**, the plate
`AB/12 #3` becomes `…/license_plate/AB/12 #3` — two path segments, and
`#3` is dropped as a URL fragment. The plate lookup then hits the wrong
path.

- **Fix:** `urllib.parse.quote(value, safe="")` each path parameter in
  `resolve()`; validate plates as alphanumeric on the form.

### M4. The internal build ships a public-API key inside the app

`constants.load_internal_invite_defaults()` reads
`assets/users_invite.internal.json` (gitignored, bundled into internal
builds) and pre-fills the Users tool with its API key. Anyone with an
internal build can read the key from the bundle as plain JSON, and it is
long-lived.

- **Fix:** don't bundle keys; have each user paste one (stored per H2), or
  issue short-lived keys from the logged-in session.

### M5. Decommission never finds archives older than 7 days

`get_archive` (`apis/internal_api.py:2550`) filters by footage time over the
last `SEARCH_DURATION` (7) days. Archives of older footage are never listed,
so an org used for more than a week isn't fully cleaned — and the report
doesn't say so.

- **Fix:** list without a footage window (or a long one), or state the
  window on the Review screen.

### M6. Switching theme on the Review/Select screens discards the scan

The run guard only protects running jobs. Toggling the theme on Review or
Select (`main.py:199`) rebuilds the shell, which releases the org and drops
the scan results without asking. The user must scan again.

- **Fix:** treat "scan results held" as a guarded state, or keep the view
  instance across the theme rebuild.

### M7. The API client is the least-tested code

Coverage is 76% overall, but `apis/internal_api.py` is at **57%**: most
`get_*` field mappings (`x["deviceId"]`, `x["name"]`, …) and many deleters
run in no test. A renamed field in a Command response would only show up in
a live run, as a scan failure for the whole Decommission.

- **Fix:** table-driven tests feeding each getter a recorded response
  (the live recordings in `$LIVE_OUT` are a ready source).

---

## Low

| # | Finding | Where |
|---|---|---|
| L1 | **Update check (verified):** tuples of different length compare wrongly, so a release tagged `v3.5.0` reads as newer than `3.5` and shows a false "Update available". Pad both to the same length. | `utils/version_check.py:17` |
| L2 | CSV export opens the file without `encoding="utf-8"`; on Windows a non-ASCII name (e.g. "José") raises `UnicodeEncodeError` and the export fails. Values starting with `=`/`+`/`-`/`@` aren't neutralised for Excel. | `utils/export.py:22` |
| L3 | External client: every 403 triggers a token regeneration and retry, also for genuine permission refusals (an extra token call each time). Refresh on 401 only. | `apis/external_api.py:144` |
| L4 | `get_guest_visits` assumes `guest` and `full_name` are present; a `null` in either raises and loses the whole participant load. | `apis/external_api.py:373` |
| L5 | `_post_login` assumes the body is a JSON object; a JSON list or string raises `AttributeError` instead of a clear login error. | `apis/internal_api.py:703` |
| L6 | After retries are exhausted on a 5xx, requests raises a generic `RetryError`, so the user sees "Max retries exceeded" instead of Command's message. Set `raise_on_status=False` and let `_send` report the last response. | `apis/http.py` |
| L7 | A retried DELETE whose first attempt succeeded comes back 404 and is reported as a failed delete. Treat 404 on delete as "already gone". | `apis/http.py`, `_delete` |
| L8 | Cancelling during the first device row of a claim marks the remaining devices "skipped (cancelled)", although the one batch call already claimed them. | `pages/commission_view.py:1481` |
| L9 | Choosing a kit that lacks a device type clears a serial the user had typed in that field. | `pages/commission_view.py:374` |
| L10 | The session timer is started with a bare `asyncio.create_task`; the codebase's own `spawn()` exists to avoid this garbage-collection risk. | `pages/app_shell.py:413` |
| L11 | Users, cameras and the permission reset read at most 1,000 users/cameras (no paging). Fine for training orgs; silent truncation beyond. | `get_user`, `get_camera` |
| L12 | `api_calls.log` grows without limit and holds emails, names, user ids and plates. Rotate it (e.g. 5 × 5 MB) and document what it contains. | `utils/logger.py` |
| L13 | The scan's prep row says "Granting Access System Admin" also when it grants Access User Admin. | `pages/decommission_view.py:418` |
| L14 | Reusing a site relies on matching the text "already exists" in Command's error message; a reworded message breaks re-runs. Look the site up first (one list call), as buildings do. | `create_or_reuse_site` |
| L15 | `DEV_SKIP_LOGIN` is a hard-coded constant with no guard; a commit that flips it ships an app that skips login. Read it from an environment variable, or fail CI when it is `True`. | `constants.py:27` |

## Design risks worth a deliberate decision

- **Decommission selects every Command user by default**, including other
  trainers' and admins' accounts (only the signed-in user is excluded).
  That matches "delete all users except yourself", but a single click
  deletes accounts that may not belong to the training. Consider leaving
  Command Users unticked by default, or listing admins separately on Confirm.
- **Participants are invited as Org Admins** (Users tool default role).
  That is the training design, but every participant gets full control of
  the org, including deleting devices and inviting others.
- **The session is capped at 60 minutes** (30 + two 15-minute extensions)
  and expiry cancels a running job. A very large Decommission could be cut
  off part-way; the report shows where it stopped.

## Dead code

Nothing calls these (checked against the string-dispatch maps and
`tools/`):

- **Public-API client** — only `get_sites` and `get_guest_visits` are used
  (Users tool). Unused: `get_guest_sites`, `get_cameras`,
  `get_person_of_interest`, `get_users`, `create_access_group`,
  `add_user_to_access_group`, `add_license_plate_to_user`,
  `_user_has_plate`, `delete_user`, `delete_access_user`,
  `delete_persons_of_interest`, `get_access_groups`, `delete_access_group`,
  and the `get_object` categories behind them.
- **Internal client** — `create_external_api_key`,
  `delete_external_api_key` (and `ExternalApiKey`), `configure_camera`,
  `enable_door_face_unlock`, `enable_door_mfa_card_code` /
  `_face_card` / `_face_code`, `find_access_group`, `is_org_empty`,
  `get_device_count`.
- **Kept deliberately** (registry for future templates, not dead by
  mistake): alarm partition/guard/expander/wireless/wired-input creators,
  `create_mailroom_site`, `get_alarm_device`/`delete_alarm_device`.

Removing the first two groups takes about 450 lines and the API-key code
path with them.

## What is in good shape

- Retry policy: POSTs are never replayed except on 429 or a connection that
  never opened (M1 is the one PUT exception).
- Run guard: navigation, logout, Cmd-K and expiry can't silently abandon a
  run; cancellation is cooperative and reports what was skipped.
- Decommission always reverts Global Site Admin and the access roles on
  every exit path inside the app (H3 covers the exits outside it).
- Batch deletes fall back to one-by-one on failure; the read cache never
  keeps a failure and can't deadlock (the request's owner always runs).
- No secrets in the repo; live tooling redacts serials, ids, emails and
  keys; API key secrets are masked in the log.
- CI runs ruff and 223 tests on Python 3.10 and 3.13.

## Suggested order

1. H1 (one-line filter + test) — it can break Decommission in real lab orgs.
2. H3 and M6 — leaving the org elevated / losing a scan.
3. H2 and M4 — credential handling.
4. M1–M3, L1, L2 — small, contained fixes.
5. M7 — tests for the client's response mappings.
6. Dead-code removal.
