# Live validation runbook: Command web app vs. vCommander

This runbook is self-contained. It is written for a fresh session (person or
agent) with no prior knowledge of vCommander or of earlier work on it.

**Goal:** perform every action vCommander automates in the real Verkada
Command web app, record the API calls the web app makes, compare them with
the calls vCommander makes for the same action, and turn the differences
into concrete improvements, changes and updates to vCommander.

---

## 1. Background

### What vCommander is

A Python desktop app (Flet UI) that automates Verkada Command admin work.
It has four tools:

| Tool | What it does | Code |
|---|---|---|
| Login / 2FA | email + password + org short name; SMS or authenticator code | `pages/login_view.py`, `pages/two_factor_view.py` |
| Commission | builds a training org from a template (ESS, ACSL, ACSE, VSSL, VSSE, AS): claims devices, creates a site, building, doors, alarm system, access levels, and so on | `pages/commission_view.py` |
| Decommission | scans the org for every asset type, lets the user choose, then deletes in dependency order | `pages/decommission_view.py`, order in `constants.py` (`DELETION_ORDER`) |
| Users | imports users from another org through the public API and invites them | `pages/users_view.py` |

### How vCommander calls Command

- **Internal API** (the API the Command web app itself uses):
  `apis/internal_api.py`. Every endpoint is registered in
  `apis/endpoints.py` (`ENDPOINTS`, about 150 entries), each with a method,
  a service name (`subdomain`), a path under `/__v/<org>/`, and a sample
  payload and response.
- **Hosts are per shard.** Before login the client calls
  `org/validate_short_name` on `vglobal.global-prod.verkada.com`. The
  response names the org's shard and its domain. Every internal call then
  goes to `https://<service>.<shard domain>/__v/<org>/<path>`, for example
  `vprovision.prod-us-ohio.verkada.com`. Endpoints registered with
  subdomain `api` use the shard's gateway label instead.
- **Public API** (`apis/external_api.py`): `https://<label>.verkada.com`.
  The label comes from the shard: `prod1` uses `api`, `prod-us-ohio` uses
  `api.oh`, `prod2` uses `api.eu`, `prod-ap-syd` uses `api.au`. It is
  authenticated with a temporary API key that vCommander creates and later
  deletes through the internal API.
- **Headers:** `x-verkada-organization-id`, `x-verkada-user-id`,
  `x-verkada-token`, plus the cookies `auth`, `org`, `usr`, `token`.
  `origin` and `referer` are `https://<org>.command.verkada.com`.

### Already established (don't redo)

See `docs/LIVE_VALIDATION.md`. In short:

- All six Commission templates and Decommission ran successfully on a
  `prod-us-ohio` test org.
- Fixed: per-shard hosts, Ohio's public API host, and reuse of an existing
  same-named site or building. Command always rejects duplicate site names;
  it accepts duplicate building names.
- `host_metadata.public_api_endpoint` in the org lookup does not name the
  public API's host. Ignore it.
- `site.list` works with or without the web app's `targetPermissions`.

---

## 2. Setup

1. Work on branch **`v3.5`**. Commit and push there. Don't open a pull
   request unless the owner asks for one.
2. **Environment secrets** (set by the owner in the environment settings).
   Never print them, write them to files in the repo, or commit them:

   | Variable | Value |
   |---|---|
   | `VERKADA_ORG` | test org short name |
   | `VERKADA_EMAIL` | email of the account the session belongs to |
   | `COOKIE` | `Cookie` header from a logged-in Command browser tab |
   | `X_VERKADA_TOKEN`, `X_VERKADA_USER_ID`, `X_VERKADA_ORGANIZATION_ID` | the matching `x-verkada-*` headers |
   | `Access_Controller`, `Access_Station_Pro`, `Alarm_Panel`, `Bullet`, `Command_Connector`, `Dome`, `Fisheye`, `Keypad`, `PTZ` | one device serial each |

   The org enforces 2FA, so the session cookies stand in for a password
   login. Password login and the SMS step can't be tested unattended.
3. **Network:** the environment must allow `*.verkada.com`. Test it with
   `curl -s -o /dev/null -w '%{http_code}' https://api.verkada.com/`. A JSON
   `403 Insufficient permissions` from Verkada means the host is reachable.
4. **Python:**
   `python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest ruff`.
   Run the tests with `.venv/bin/python -m pytest -q` (all must pass) and
   `.venv/bin/ruff check .`.
5. **Browser:** Chromium and Playwright are preinstalled. Run Node scripts
   with `NODE_PATH=$(npm root -g) node ...`. Don't install Playwright again.
6. **Outputs:** set `LIVE_OUT` to a scratch directory outside the repo
   (default `~/.vcommander-live`). Recordings, screenshots and
   `compare.json` go there and must never be committed.

### Tools in `tools/live/` (read `tools/live/README.md`)

| Tool | Purpose |
|---|---|
| `check.py` | read-only: shard, session validity, which serials are in the org |
| `commission.py <TEMPLATE>` | runs the real Commission flow headlessly (changes the org) |
| `decommission.py scan` / `delete "Command Users"` | runs the real Decommission flow; `delete` deletes for real but keeps the listed categories |
| `web/session.js` | headless Command session from `COOKIE`; records every API call (redacted) |
| `web/probe.js` | opens Command's home page and reports failed calls |
| `compare.py <recordings>` | vCommander registry vs. recorded calls: method, service, payload keys |

---

## 3. Safety rules (non-negotiable)

1. **Ask the owner before any call or UI action that changes the org.**
   Group requests by phase, for example "record ESS-related actions: creates
   a site, claims Dome, Alarm Panel and Access Station Pro, …". Read-only
   calls need no approval.
2. **Never let the headless browser log out.** A logout revokes the session
   token server-side, which also logs out the owner's own browser.
   `web/session.js` aborts every logout request. Keep it that way, and use
   `session.js` for every browser script.
3. If `check.py` reports `vtki: token revoked` or 401s, stop. Ask the owner
   to refresh `COOKIE` and `X_VERKADA_TOKEN` and start a new session.
4. **Never delete user accounts.** When running Decommission, always keep
   `Command Users`.
5. Never print or commit secrets, serials, emails, ids or the org short
   name. Use `harness.redact()` and the redaction in `session.js`.
6. **Leave the org clean** at the end of each phase. Run
   `decommission.py delete "Command Users"`, then check with
   `decommission.py scan` that only the kept user remains. Also check that
   Global Site Admin is off and no temporary API keys are left.
7. If a serial fails to claim (`failedSerials` with no reason), it is
   probably still claimed in another org. Report it and ask the owner; don't
   retry in a loop.

---

## 4. Procedure

### Phase 0: access

1. Run `python tools/live/check.py` and expect `session OK`.
2. Run `web/probe.js` and expect no 401s and no blocked logout. If
   `feature_flags/init` returns 401, the identity headers are missing.
   `session.js` adds them from `X_VERKADA_*`; confirm those are set.

### Phase 1: record what vCommander actually sends

`compare.py` compares against the **registry samples**, which may have
drifted from what the code really sends. So first record vCommander's real
requests:

- Add a recorder to `tools/live/harness.py` that wraps
  `client.session.request` (and the external client's session). It should
  append `{method, host, path, body, status}` to a JSON file in `LIVE_OUT`,
  in the same format as `session.js`, and redact the body.
- Record each action from the catalogue below with vCommander, using
  `commission.py`, `decommission.py` or a direct client call.

### Phase 2: record the web app doing the same action

For each catalogue row:

1. Write a Playwright script in `tools/live/web/actions/<action>.js` that
   uses `open()` from `session.js`. It should navigate to the Command page
   and click through the UI the way an admin would. Discover selectors from
   screenshots and `page.accessibility.snapshot()`, and prefer role and
   label selectors. Save the result with `save('<action>.web.json')`.
2. Use the same names and inputs as vCommander where you can, such as site
   "HQ" and the template device names in `constants.py`, so payloads are
   comparable.
3. Where the UI can't be automated reliably, ask the owner to perform the
   action in their own browser and export a HAR. `compare.py` reads HARs.
   The owner must not send the HAR through the chat if it contains secrets;
   it should be uploaded as a file and never committed.

### Phase 3: compare

For each action, compare the vCommander recording with the web recording:

- **Endpoint:** service, method, path. Does the web app use a newer or
  different endpoint for the same thing?
- **Payload:** key paths, value types and enum values. Note fields only
  vCommander sends and fields only the web app sends.
- **Sequence:** extra calls the web app makes before or after (setup,
  validation, follow-up configuration) and any that vCommander skips.
- **Response:** the fields vCommander reads (see the parsing code in
  `apis/internal_api.py`). Are they still present?
- **Errors:** how the web app handles conflicts, for example duplicate
  names.

`python tools/live/compare.py <vcommander.json> <web.json>` gives the
registry-level view. Extend it, or write a per-action diff, to compare the
two recordings directly.

### Phase 4: improvements, changes, updates

Classify every difference:

| Kind | Action |
|---|---|
| vCommander sends a field the web app doesn't | **Test removing it live**; if the call still succeeds with the same result, remove it from the code and the registry sample |
| web app sends a field vCommander doesn't | decide whether it changes the result (verify live); add it if it does |
| web app uses a different or newer endpoint | evaluate migrating; verify live; keep the old one registered (the owner keeps unused endpoints) |
| web app makes extra calls | decide whether vCommander's result is incomplete without them |
| registry sample drifted from the code | update the sample in `apis/endpoints.py` |
| behaviour difference (conflicts, ordering) | fix in the flow, with a unit test |

Rules for changes:

- Make small commits, each with unit tests in `tests/`.
- Before pushing, `pytest` and `ruff` must pass.
- Don't remove registered endpoints even if they're unused; the owner wants
  them kept.
- After code changes, re-run the affected Commission template and a
  Decommission live to confirm.

### Phase 5: report

Update `docs/LIVE_VALIDATION.md` with a dated section. It needs:

- a per-action table (action → vCommander endpoint(s) → web endpoint(s) →
  status: match / changed / improved);
- every change made, with its commit;
- open questions for the owner.

Then give the owner a short summary.

---

## 5. Action catalogue

Check this against the code before starting: `grep -n "client\.\w*"` in
`pages/*.py`, plus the `_INTERNAL_GETTERS`, `_INTERNAL_DELETERS`,
`_EXTERNAL_GETTERS` and `_EXTERNAL_DELETERS` maps in `constants.py`. Endpoint
keys refer to `apis/endpoints.py`. Method names refer to
`apis/internal_api.py` unless marked *(public)*, which means
`apis/external_api.py`.

### Org settings and keys (Command: Admin → Org Settings)

| Action | vCommander method | Endpoint keys |
|---|---|---|
| Enable custom roles | `enable_custom_roles` | `org.custom_roles` |
| Enable org features (+ sign agreement) | `enable_org_features` | `org.features`, `org.sign_agreement` |
| Allow face unlock | `enable_org_face_unlock` | `org.allow_face_unlock` |
| Global Site Admin on/off | `enable_global_site_admin` / `disable_global_site_admin` | `permissions.global_site_admin.*` |
| Access System/User Admin | `enable_access_admin` | `permissions.access_system_admin.enable`, `permissions.access_user_admin.enable` |
| API key create/list/delete | `create_external_api_key`, `get_external_api_key`, `delete_external_api_key` | `org.api_key.*` |

### Sites, buildings, floors

| Action | Method | Endpoint keys |
|---|---|---|
| Create / list / rename / delete site | `create_site`, `get_site`, `rename_site`, `delete_site` | `site.*` |
| Create / list / delete building | `create_building`, `get_building`, `delete_building` | `building.*` |
| List / delete floor | `get_floor`, `delete_floor` | `floor.*` |

### Devices

| Action | Method | Endpoint keys |
|---|---|---|
| Claim device by serial | `add_device` | `org.add_device` |
| Unassigned devices | `get_unassigned_device` | `org.unassigned_devices.list` |
| Camera name / site / location | `configure_camera` | `camera.create.name`, `.site`, `.location` |
| Camera analytics | `enable_camera_analytics` | `camera.create.feature` |
| LPR mode | `enable_camera_lpr` | `camera.create.lpr_config` |
| PTZ install mode off | `disable_camera_install_mode` | `camera.create.ptz_install_disable` |
| Camera list / delete | `get_camera`, `delete_camera`; *(public)* `get_cameras` | `camera.list`, `camera.delete` |
| Command Connector configure / list / delete | `configure_connector`, `get_connector`, `delete_connector` | `command_connector.*` |
| Intercoms, desk stations, sensors (list/delete) | `get_intercom`/`delete_intercom`, … | `intercom.*`, `desk_station.*`, `sensor.*` |

### Access control

| Action | Method | Endpoint keys |
|---|---|---|
| Access controller configure / list / delete | `configure_access_controller`, … | `access_controller.*` |
| Door create (incl. LPR door) / list / delete | `create_door`, `get_door`, `delete_door` | `door.create`, `door.list`, `door.delete` |
| Door face unlock, MFA modes | `enable_door_face_unlock`, `enable_door_mfa_*` | `door.enable_face_unlock`, … |
| Pair LPR camera to door | `pair_lpr_camera` | `door.pair_lpr_camera` |
| Access Station Pro configure / door / list / delete | `configure_access_station_pro`, `create_access_station_pro_door`, … | `access_station_pro.*` |
| Access level create / list / delete | `create_access_level`, … | `access_level.*` |
| MFA schedule create; schedules list/delete | `create_mfa_schedule`, `get_schedule`, `delete_schedule` | `schedule.*` |
| Access group create / add user / license plate / delete | *(public)* `create_access_group`, `add_user_to_access_group`, `add_license_plate_to_user`, `delete_access_group` | public API |
| Visits, visitors, visitor access templates, scenarios (list/delete) | `get_visit`/`delete_visit`, … | `visit.*`, `visitor.*`, `visitor_access_type.*`, `scenario.*` |

### Alarms

| Action | Method | Endpoint keys |
|---|---|---|
| Alarm site create (+ trial) / self-monitored / list / delete | `create_alarm_site`, `set_alarm_self_monitored`, … | `alarm.site.*` |
| Alarm system create / general keycode / list / delete | `create_alarm_system`, `set_alarm_keycode`, … | `alarm.system.*` |
| Panel, keypad, expander configure / list / delete | `configure_alarm_panel`, `configure_keypad`, … | `alarm.panel.*`, `alarm.keypad.*`, `alarm.expander.*` |
| Wired outputs (strobe) / inputs | `create_wired_output`, `create_wired_input`, … | `alarm.wired_output.*`, `alarm.wired_input.*` |
| Wireless sensors, panic buttons, transmitters | `configure_wireless_*`, … | `alarm.wireless_*` |
| Guards, partitions | `create_alarm_guard`, `create_alarm_partition`, … | `alarm.guard.*`, `alarm.partition.*` |

### Guest, mailroom, users, investigations

| Action | Method | Endpoint keys |
|---|---|---|
| Guest site create (+ trial) / delete; list *(public)* | `create_guest_site`, `delete_guest_site`; `get_guest_sites` | `guest.*` |
| Mailroom site create / list / delete | `create_mailroom_site`, … | `mailroom.*` |
| Invite user | `invite_user` | `user.create` |
| Groups create / list / add members / delete | `create_group`, `get_group`, `add_users_to_group`, `delete_group` | `group.*` |
| Users list / delete; persons of interest; guest visits *(public)* | `get_users`, `delete_access_user`, … | public API |
| Incidents, archives, alerts (list/delete) | `get_incident`/`delete_incident`, … | `incident.*`, `archive.*`, `alert.*` |

### Device coverage per template

Use this to plan which serials each recording session needs. A serial can
only be claimed once, so run Decommission between overlapping templates.

| Template | Devices |
|---|---|
| ESS | Dome, Alarm Panel, Access Station Pro |
| ACSL | Access Station Pro |
| ACSE | none |
| VSSL | Bullet, PTZ, Command Connector, Access Controller (+ test license plate) |
| VSSE | Dome, Fisheye, Bullet |
| AS | Dome, Access Controller, Alarm Panel, Keypad |

---

## 6. Prompt for the new session

Paste this into a new session started on branch `v3.5` after the owner has
refreshed the environment secrets:

> Read `docs/LIVE_VALIDATION_RUNBOOK.md` and follow it from Phase 0. Use the
> tools in `tools/live/`. Ask me before any action that changes the test
> org, never let the browser log out, and never print or commit secrets.
> Record each catalogue action in Command and in vCommander, compare them,
> and implement and verify the improvements. Report in
> `docs/LIVE_VALIDATION.md`.
