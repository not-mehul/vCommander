# Live validation log

Results of running vCommander against a real test org with the scripts in
`tools/live/`. Newest first.

## 2026-10-27 — Web app vs. vCommander, action by action

Procedure: [`LIVE_VALIDATION_RUNBOOK.md`](LIVE_VALIDATION_RUNBOOK.md), same
`prod-us-ohio` test org. Each action was recorded twice: vCommander through
the real Commission/Decommission flows (`LIVE_RECORD`), and the Command web
app driven headlessly through its UI (`tools/live/web/actions/`). The two
were compared with `compare.py --diff`. The org was left clean after every
phase: only the session's own user, Global Site Admin off, no API keys.

**vCommander runs (recorded):** ESS 21/21, ACSL 15/15, ACSE 4/4, VSSE 14/14,
AS 25/25, VSSL 23/24 (license plate already in use, fixed below, then
24/24). Seven Decommission runs, all with 0 failures.

### Per action

Status: **match** = same endpoint, method and payload keys; **changed** = the
web app does it differently and both work; **improved** = vCommander changed
in this run; **not compared** = see the note.

| Action | vCommander | Web app | Status |
|---|---|---|---|
| Create site | `vprovision org/camera_group/create` | same, same body | match |
| Delete site | `vprovision org/camera_group/delete` | same | match |
| Create building + floor | `vprovision building/create` | same, same keys | match |
| Delete floor / building | `floor/delete`, `building/delete` | same | match |
| Claim devices | `vconductor …/device/batch/commission`, one call per device | same endpoint and keys; all devices in one call | match |
| Camera name / site / location | `camera/name/set`, `camera/site/batch/set`, `camera/location/set` | same three, same keys (from the Set Up dialog) | match |
| Camera analytics | `vdeviceconfig user/camera/feature/set` | `vcorgi device/recommended_default_settings/apply` (`features` list, from Set Up) | changed |
| LPR mode on | `user/camera/feature/set` + `vprovision user/camera/config/set` (operating mode `lpr`) | same two, plus `camera/rotate {rotate:"0"}` first | match |
| PTZ install mode off | `vdeviceconfig user/camera/config/set` `{cameraIds, params, consumable}` | `vprovision user/camera/config/set` `{cameraId, params}` | changed |
| Camera delete | `vprovision camera/decommission` | same | match |
| Access controller / ASP decommission | `vcerberus access_device/decommission` | same path and body via the `api` gateway | match |
| Access Station Pro setup | `vcerberus access/v2/user/access_device/setup` | same, same keys | match |
| ASP door create | `door/create` (config profile incl. `face-unlock-enabled`) | same; adds default MFA modes, face-unlock distance/cooldown/beep, `ble-unlock-proximity`, `has-door-sensor` True; then `door/set_nearby_cameras` | changed |
| Door face unlock | follow-up `door/config/set` after create | none (comes with create) | **improved** |
| Door MFA modes | `door/config/set`, `paramValue: true` | same, `paramValue: "True"`/`"False"` strings | match |
| Door delete | `door/delete` | same | match |
| Org face unlock | `organization/config/set` | same | match |
| MFA door schedule delete | `PUT …/schedules`, full object with `deleted: true` | same (via `vcerberus`) | match |
| Access level create | `vcerberus access/v2/user/schedules` | same, identical keys | match |
| License plate to user (public API) | `POST access/v1/credentials/license_plate` | n/a (web uses the internal API) | **improved** (re-runs) |
| Alarm site create + trial | `vagent response/site/create`, `site/software_trial/create` | same; adds `dispatchEnabled: true` (already the default) | match |
| Alarm site delete | `vagent response/site/delete` | same | match |
| Alarm system + panel setup | `alarm_system/create`, `unassigned_device/setup_colossus` | same, same keys | match |
| Alarm panel / system delete | `device/decommission`, `alarm_system/delete` | same pair | match |
| General keycode | `vproconfig keycode/create` | same, same keys | match |
| Wired output (strobe) | `device/create_wired_output`, `pinNum: 1` | same; the UI's "Output 1" is `pinNum: 0` | match (see question 2) |
| Guest site create | `vdoorman site/org/{id}` + `guest/trial` | `site/org/{id}` with `skipDefaultSetting: true`, no trial | changed |
| Guest site delete | `DELETE vdoorman site/org/{id}` | same | match |
| API key create / delete | `apiadmin …/granular_apikeys`, `…/apikeys/{id}` | same, same keys | match |
| Self-monitored response | `vagent response/config/update` | no control for a trial site in the UI | not compared |
| Custom roles, org features + agreements | `custom_roles/enable`, `user/org/feature/set`, `sign_agreement` | already on in the org; the UI offers no way to turn them back on | not compared |
| Global Site Admin on/off | `org/settings/update` | no UI control found | not compared |
| Access System/User Admin grant | `org/set_user_permissions` | Roles dialog found; recording blocked (it grants roles to the owner's user) | not compared |
| Command Connector, standard controller, standard/LPR door, keypad, access group, access level delete | see code | not recorded yet | not compared |
| Invite user, groups, mailroom, intercoms, sensors, visits, incidents | — | not recorded (invites skipped by the owner; no such assets in the org) | not compared |

The web app's Feature Manager no longer lists the camera analytics flags
vCommander sets (only AI-powered search); the `vcorgi org/{id}/features`
read shows them all enabled from earlier runs.

### Changes

| Change | Commit |
|---|---|
| Adding the VSSL license plate is idempotent: "already in use" succeeds when the plate is already on this user (Decommission keeps users, so every second VSSL run failed). Verified: VSSL 24/24. | `ecfc3c9` |
| ESS and ACSL no longer set `face-unlock-enabled` on the Access Station Pro door a second time; it is in the create configs, as in the web app. Verified: ESS 20/20, Face Unlock on in the web app. | `6d7322f` |
| Recorder for vCommander's calls (`LIVE_RECORD`), secret scrubbing by JSON key, dash-insensitive serial redaction, blocked logouts recorded | `674353e` |
| Web action scripts, `explore.js`, `run.js`, `compare.py --diff`; `decommission.py` releases the org when there is nothing to delete; `check.py` lists API keys | `c2e98cb` |

Registry samples match what the code sends; the apparent differences come
from endpoints that share a path.

### Open questions for the owner

1. **Access admin roles stay granted.** Decommission grants the running user
   Access System Admin and Access User Admin and never revokes them, unlike
   Global Site Admin. Should the release step revoke them? Recording the web
   app's grant/revoke also needs your approval, since it changes your
   user's roles.
2. **AS strobe pin.** `AS_STROBE_OUTPUT_PIN = 1` puts the strobe on the
   panel's Output 2; the web app's Output 1 is `pinNum: 0`. Intended?
3. **ACSL MFA in one call.** The web app creates doors with the MFA modes in
   the create configs. ACSL could do the same and drop three steps (the run
   log would no longer list them). Want it?
4. **Guest trial.** The web app enables Guest with `skipDefaultSetting:
   true` and no trial call. vCommander keeps its trial and default settings;
   say if the training orgs should match the web app instead.
5. **Remaining rows.** Command Connector setup, standard controller and
   LPR door, keypad setup and access groups weren't recorded on the web side.
   Should I continue with them?
6. **Device claims.** The web app claims all devices in one
   `batch/commission` call. vCommander's one-per-device calls give a clear
   per-device result, so they were kept.

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
