# Live validation log

Results of running vCommander against a real test org with the scripts in
`tools/live/`. Newest first.

## 2026-10-29 (part 2) — Template fixes: strobe response, AF64 level, VCE group, ACSE reset

Org left clean afterwards (only the owner's two accounts, no access roles).

### Newly recorded (web app → vCommander)

| Action | Call | Used by |
|---|---|---|
| Response → Automated Alarm Actions → Output devices → toggle the strobe | `vagent response/config/update`, `updateType: CONFIG_UPDATE_TYPE_SET_OUTPUT_DEVICES`, `setOutputDevicesInput.deviceIds` (replaces the list) | `alarm.response.set_outputs` |
| Access level → Add Groups → Save → Confirm | `PATCH vcerberus access/v2/user/schedules/{id}`: the level as listed (no events), full `userGroups`, doors/sites as `{add, remove}` | `access_level.update` |
| User → Roles → Manage (Organization / User Management / Site roles) | `vprovision org/set_user_permissions` grant/revoke `{entityId, permission}`: org and user-management roles on the org id, site roles (`SITE_ADMIN`, `SITE_VIEWER`, …) on the site id. The user list (`includeRoleGrants`) returns every user's direct grants; inherited roles ("Inherited from Org Admin") are not grants | ACSE reset |

### Changes and live results

| Change | Live result |
|---|---|
| ESS and AS put the Strobe Light (Output 1) in the Default Response's output devices; ESS now creates the strobe | AS 24/24 steps, ESS 21/22 (guest trial, known); the response lists the created strobe, and the web app shows it ticked |
| ESS creates "[DO NOT TOUCH] AF64" on HQ Door, granted to "All Participants" when that access group exists | Created with HQ Door; the group didn't exist yet, and the next invite run granted it; the re-run found it already granted |
| Invite Tool: participants also join "VCE Access Group" when it exists; "VCE Access Level" and "[DO NOT TOUCH] AF64" are granted to their group if they lack it | VSSL: 3 participants added to VCE Access Group (now 4 with the trainer); VCE Access Level already granted it |
| ACSE: "Remove existing user permissions (keeps Org Admin)", on by default, runs before anything else | A non-admin test user with Access System Admin, Command User Viewer, Access Credential Manager and Site Admin on HQ: all 4 removed in one call; the user stayed in the org and the web app shows None in all three sections. Org Admins were untouched |

**Note:** "ACSL: add strobe to the response" was taken to mean AS (the
Alarms Specialist lab); ACSL has no alarm panel or response.
The live script limits ACSE's reset to "VC Test" users, so the org's real
users are never changed by a test run.

## 2026-10-29 — Access roles, participant groups, stress and edge-case tests

The org was left clean: no sites, devices, API keys or test users, Global
Site Admin off, no access admin roles on the session user (only the owner's
two accounts remain).

### Changes

| Change | Commit |
|---|---|
| Decommission revokes both access admin roles at release, including ones held before the scan (as it already did for Global Site Admin). Only missing roles are granted. | `f7b6793` |
| Users tool: participants (invited now or already in the org) go into an "All Participants" **Command group and access group**. Each is found by name, created once, and only people not yet in it are added. The access group needs an access admin role: missing roles are granted for that step and revoked right after, also when it fails. | `6bb0ce1` |
| Edge cases: the read cache no longer keeps a failed read, and releases waiting threads on any exception. Batch deletes send ≤100 ids per call; a failed call is retried item by item. Review catches one serial entered in two device fields. A repeated email (any case) is invited once. `get_user` tolerates a user without an email. | `59ee242` |
| **Bug found by the stress run:** a scan failed outright in an org with no sites (camera search: 403 even with Global Site Admin on) or no cameras (people service: 403). This came in when Cameras and Persons of Interest moved to the internal API. Each 403 now means "none" only when the org really has no sites / cameras. The live script now prints scan alerts; the ACSE cycle had failed without showing it. | `3689cc2` |

### Live stress and edge-case results

| Test | Result |
|---|---|
| Invite 28 participants (25 new, 3 existing, one listed twice, addresses upper-cased), both groups on | 10.5 s, 32 calls, 0 errors, no rate limiting. 25 invited, 3 reported as already in the org, the repeat skipped; 25 added to each group with one call per group |
| Same batch again | 3.4 s, 5 calls: everyone already in the org and in both groups; nothing sent |
| Users-tool group step with no access roles held | roles granted, access group created, 2 added, roles revoked (13 calls) |
| Three scans in a row (VSSL + 27 users) | same items each time, 7.3–9.0 s. Scans 2–3 make one extra call to re-grant the roles scan 1 revoked |
| Decommission of that org | 27 users in one call, 12 categories, 0 failed, 14.9 s; both roles revoked although held before |
| Batch user delete with an unknown id beside a real one | accepted; the real user deleted, the unknown id ignored |
| Batch user delete of the session user / an empty list | refused locally / no call |
| Claim a nonexistent serial | Command returns it under `failedSerials` with no reason; the row fails with a clear message |
| Claim a serial already in this org | returns its existing device id; the device keeps its name |
| Alarm-site, Command-group and access-group lookups with nothing to find | `[]` / `None`, no error |
| Scan of an empty org; of an org with only a site | review state reached (after the fix above); the site deleted |
| Every template, commissioned then decommissioned | below |

| Template | Commission | Decommission |
|---|---|---|
| ESS | 17 ok, 1 failed (guest trial, see below), 23 calls, 23.0 s | 0 failed, 48 calls, 15.5 s |
| ACSL | 9 ok, 11 calls, 12.6 s | 0 failed, 37 calls, 12.2 s |
| ACSE | 2 ok, 3 calls, 5.3 s | nothing to delete (re-run after the fix) |
| VSSL | 21 ok, 25 calls, 15.1 s | 0 failed, 41 calls, 12.0 s |
| VSSE | 10 ok, 15 calls, 10.6 s | 0 failed, 36 calls, 9.4 s |
| AS | 23 ok, 26 calls, 18.1 s | 0 failed, 45 calls, 14.8 s |

Unit tests: 206, including a 64-thread read-cache test, batch chunking and
fallback, scan cancellation, and the role and group cases above.

### Known limitations

- **Guest trial.** ESS's "Creating Guest Site" fails on this test org with
  "Site creation is limited" (the trial call). The guest site itself is
  created. The org has run many guest-site cycles; fresh orgs are not
  affected as far as seen.
- **Re-running AS on an already commissioned org** fails 3 steps: Command
  refuses to claim alarm devices already set up, and the alarm site already
  exists. Decommission first, then commission again.
- **Large orgs.** Cameras and users list up to 1,000 each.

## 2026-10-28 (part 2) — Log review, internal-only Decommission, faster scan

Driven by the owner's `api_calls.log` (1,110 calls over 8 days, five
commissions, each into a fresh org) and by timing Decommission. The org was
left clean: no devices, no API keys, test users deleted, Global Site Admin
off, no access admin roles on the session user.

### What the log showed

| Finding | Effect | Change |
|---|---|---|
| Deletes were the most frequent calls: 87 public-API `DELETE core/v1/user`, 39 public-API POI deletes (two timed out), one call per item | slow, needed a temporary API key | Decommission is internal-API only (`465abf7`): users and POIs are deleted in one call each, and no key is created |
| 10 temporary API key secrets were written to `api_calls.log` | secrets in a local file | the key is masked in the log (`465abf7`); the keys had already been deleted |
| 11 "User already exists in this org" errors in one re-invite | an invite sent and refused for each person, and they never joined the group | invites skip people already in the org (`ba4a70f`) |
| The scan listed categories one at a time and repeated reads (`alarm_system/list` ×10, `alarm_system/get_devices` ×8) | about 55 calls before anything is deleted | parallel scan with shared reads (`b111a0c`) |
| `response/site/get` once per site to find alarm sites | one call per site | one `response/site/list` call (`4e6032d`) |
| Every login starts with a 400 (MFA required), then MFA | expected | none |

### Decommission

- **Internal API only.** Command Users and Persons of Interest are deleted
  with one call each (`vcorgi org/{id}/users/delete`, `videntity
  identity/delete`). Persons of Interest now come before Cameras: videntity
  answers 403 once the org has no cameras, even with Global Site Admin on.
  Verified live.
- **Scan.** All categories are listed at once, four requests at a time.
  Identical reads within one scan are sent once (`client.read_cache()`, for
  GETs and `*.list` / `*.get` endpoints only, never writes). Cameras and
  Access Controllers are listed last, so they can be de-duplicated against
  Intercoms and Access Station Pros.

| Scan of an AS org | Calls | Wall time (incl. login) |
|---|---|---|
| before (sequential) | 55 | 15.6 s |
| after | 33 | 8.4 s |

Every endpoint is now called once per scan. A full Decommission of an AS
org (scan, delete 11 categories, release) took 11.5 s and 44 calls, with 0
failures.

### Invites

One user list call before a batch. People already in the org get an
"Already in the org" row instead of an invite that Command refuses. In the
Users tool they still join the Command group. This applies to the Users tool
and to Commission's supporting users. Live (`tools/live/invite.py`): two test
users were invited, then a batch of three that included them. The second
batch made 3 calls (validate, user list, one invite) and reported
"1 invited; 2 already in the org", with no errors.

### Commission waits

| Wait | Result | Change |
|---|---|---|
| 3 s "Waiting for building to provision" (ESS, VSS, AS) | VSSL, AS and ESS ran without it: no failed steps; doors on the new floor created normally | removed; AS 20.9 s → 15.7 s of API time, 26 calls |
| 3 s role propagation after `custom_roles/enable` | `custom_roles/enable` returns `{}`, and nothing shows whether custom roles were already on. The test org has had them on for a while, so a fresh org's propagation can't be tested here | kept |

### Notes

- **Guest trial limit.** One ESS run failed at "Creating Guest Site":
  `site/software_trial/create` answered "Site creation is limited". The
  guest site was created; only the trial was refused. The test org has run
  many guest-site create/delete cycles. The web app doesn't call the trial
  endpoint (see question 4 of 2026-10-27).
- **VSSL access groups** are created on the internal API, which needs
  Access User Admin. Command grants that role when the controller is
  claimed, earlier in the same run.
- **Access admin roles at release.** Decommission revokes only the roles it
  granted. Roles Command grants at a controller claim stay. After these
  runs, both were revoked from the session user by hand to restore the
  earlier state. (Since 2026-10-29 Decommission revokes both.)

## 2026-10-28 — Batching: several devices, users and deletes at once

What the Command web app does when it handles several items, recorded live,
and what vCommander now does. Two spare serials were added for same-type
batches (`Dome2`, `Access_Controller2`; redacted like the others).

| Operation | Web app | vCommander before | vCommander now |
|---|---|---|---|
| Claim N devices | one `batch/commission` with all N (names included); response lists `successfulDevices` / `failedSerials` | one call per device | one call per template (`add_devices`), one progress row per device; a rejected serial fails only its row |
| Set up N cameras (Batch Setup) | one `camera/site/batch/set` and one `recommended_default_settings/apply` for all; `camera/location/set` per camera | name + site + location per camera | `configure_cameras`: one site call, locations in parallel, no rename (the claim's name sticks, verified) |
| Invite N users | one `org/invite` per user (no bulk Command invite; the CSV import `users/async_upload_csv` creates access users without a Command invite) | sequential | four at a time, one row each (Users tool and Commission) |
| Delete N devices | one delete call per device, all sent at once | sequential | four at a time per category; alarm devices, partitions, alarm sites and schedules stay sequential |
| Delete N users | one `vcorgi org/{id}/users/delete` with all ids (asynchronous) | public API, one call per user | one internal call (`delete_users`), never including the signed-in user |

**Measured on the test org** (recorded calls / wall time, same templates):

| Template | Before | After |
|---|---|---|
| ESS | 30 calls, 28.7 s | 24 calls, 22.9 s |
| VSSL | 34 calls, 24.4 s | 25 calls, 18.8 s |
| VSSE | 25 calls, 14.1 s | 15 calls, 9.6 s |
| AS | 33 calls, 25.1 s | 26 calls, 18.8 s |
| ACSL | 18 calls, 17.3 s | 11 calls, 13.3 s |

Three camera deletes finished within 6 ms of each other; four invites
within 7 ms; two and four test users were deleted with one call each while
the owner's accounts stayed.

**Changes:** `02fb289` (claims, camera setup, invites), `f966bb1`
(Decommission deletes, user batch delete).

**Next candidate:** Decommission's scan is now most of its time (47 of 69
calls are list reads, made one category at a time). The reads are
independent and could run in parallel, except that Cameras are de-duplicated
against Intercoms / Access Station Pro, which would need to be listed first.
(Done in part 2 above.)

## 2026-10-27 (part 2) — Owner's answers, remaining actions, internal-API database

Follow-up to the section below, after the owner answered its questions
(GSA lives under Modify Default Roles; Self-Monitored is the Response tab's
Response Level; test users are plus-addressed variants of the owner's email; the alarm
response may only ever be Self-Monitored). The org was left clean: only the
two existing users, Global Site Admin off, no API keys, no access admin
roles on the session user.

### Newly recorded (web app vs. vCommander)

| Action | vCommander | Web app | Status |
|---|---|---|---|
| Global Site Admin on/off | `vprovision org/settings/update {globalSiteAdmin}` | same (Modify Default Roles → Global Site Admin) | match |
| Self-Monitored response level | `vagent response/config/update` (`RESPONSE_LEVEL_SELF_MONITORED`) | same (Response → Response Level → Self-Monitored) | match |
| Invite user | `vprovision org/invite` | same keys (`orgAdmin`, `commandUserAdmin`, `inviteFf`) | match |
| Grant / revoke org roles | `org/set_user_permissions`, one call per role | same endpoint, all roles of a dialog in one call; Org Admin is `ORG_MANAGER` | **improved** (batched) |
| Command group create / add member / delete | `vauth security_entity_group/create`, `/members/add`, `/delete` | same | match |
| Delete user | public API `DELETE core/v1/user` (Decommission) | `vcorgi org/{id}/users/delete {userIds}` (batch, asynchronous) | changed; registered as `user.delete.batch`, verified live |
| Command Connector setup | `vprovision vfortress/update_box` | same keys | match |
| Standard controller setup | `vcerberus access/v2/user/access_device/setup` | first `vcerberus access/v2/user/roles/modify` (Access Site Admin on the site); 400 "Unknown entity" stops the setup | web app could not finish; vCommander unaffected |
| Standard door create | `api door/create` | same; web adds default face-unlock/MFA configs, omits `polling-frequency-ms` | **improved** (`polling-frequency-ms` dropped) |
| Access level delete | `DELETE vcerberus access/v2/user/schedules/{id}` | same | match |
| Access group create / add user / delete | public API (VSSL) | `api user_groups/add_group`, `user_groups/bulk_add_users`, `user_groups/remove_group` | **improved** (VSSL now internal) |
| License plate add / remove | public API `credentials/license_plate` | `GET api access/v2/user/license_plate/{plate}`, then `POST api access/v2/user/license_plate` (201); `POST …/license_plate/delete` | **improved** (VSSL now internal) |
| Keypad setup | `vproconfig unassigned_device/set_up_alarm_device` | same keys | match |
| Wired input | `vproconfig device/create_wired_input` | same keys | match |
| Mailroom trial / site | `vdoorman package_org/preferences/{id}`, `package_site/org/{id}` | same; the web app first creates a Command site "<name> Mailroom" | match |
| LPR mode | `user/camera/feature/set` + `user/camera/config/set` | same, after `camera/rotate {rotate:"0"}` | match |

Not recorded: LPR Unlock pairing on a door (the toggle doesn't appear for
an offline LPR camera; vCommander's `door/{id}/device_io` works), camera
partitions (need an online camera), PTZ Set Up through the web (the site
menu wouldn't select headlessly; same three camera calls as the Bullet),
persons of interest, intercoms, sensors, visits/visitors and scenarios (no
such devices or data in the org).

### Changes

| Change | Commit |
|---|---|
| AS strobe on the panel's Output 1 (`pinNum` 0; it was 1 = Output 2). Verified on the panel wiring page. | `20895ed` |
| ACSL creates its door with the three two-factor modes in the create configs (three calls fewer). Verified: all three ticked in the web app. | `20895ed` |
| Decommission reads the user's roles first (`permissions.user_roles.get`), grants only the missing access admin roles and revokes exactly those at release. Verified live. | `20895ed` |
| Commission needs no public-API key: VSSL's access group, member and plate go through the internal API, as in the web app. Every template saves the key create/connect/delete. Verified: VSSL 22/22, AS 23/23, no key or token call. | `bb05295` |
| Access admin roles granted / revoked in one call each. Verified live. | `bb05295` |
| Standard/LPR doors no longer send `polling-frequency-ms` (the default). Verified: still 10000 in the create response. | `cb0b091` |
| Registry: 14 endpoints added from the web recordings (`user.delete.batch`, `user.license_plate.get/delete`, `permissions.user_roles.get/set`, `org.features.get`, `access_controller.list.v4`, `door.list.v4`, `door.set_nearby_cameras`, `access.roles.modify`, `camera.rotate`, `camera.recommended_settings.apply`, `camera.create.ptz_install.web`, `alarm.keycode.generate`); 163 in total, none removed. | `bb05295`, `cb0b091` |

Steps per template now: ESS 18, ACSL 9, ACSE 2, VSSL 22, VSSE 12, AS 23
(before this run: 21, 15, 4, 24, 14, 25).

### Found along the way

- **Claiming an access controller or Access Station Pro makes Command
  grant the claiming user Access System Admin and Access User Admin.** So
  after any Commission with access hardware the instructor holds both
  roles, and Decommission (which only revokes what it granted itself)
  leaves them. Without them the user can't even list access controllers.
- The web app's user delete is asynchronous (`operationId`); the user list
  shows the user for a few more seconds.
- Verkada-employee emails default to a Temporary User in Add User; a full
  user needs the acknowledgement checkbox.

### Open questions

1. Should Decommission also revoke the access admin roles that Command
   granted at claim time (i.e. always revoke both at the end)? It would
   also remove them from someone who held them before vCommander ran.
2. Decommission still uses a temporary public-API key for cameras, persons
   of interest, guest sites, access groups and user deletes. Internal
   equivalents exist for all but persons of interest (`GET vdoorman
   site/org/{id}`, `user_groups/get` / `remove_group`, `user.delete.batch`,
   `camera.list`). Want Decommission moved off the public API too?
3. Device claims: one `batch/commission` call for all devices (web app) or
   one per device (current, clearer per-device result)?

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
