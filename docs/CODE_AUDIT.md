# vCommander — Code Audit (v3.5 branch)

Full-codebase audit covering weaknesses, dead code, and improvement
opportunities. It supersedes the July audit that lived at this path (see git
history); items that audit marked as fixed were re-checked and are not repeated.

> Line numbers reflect the `v3.5` branch at commit `7b8c125` and will drift.

## How this was checked

Findings marked **(verified)** were reproduced, not just read:

| Check | How |
|---|---|
| Runtime compatibility | Constructed all 6 views + `AppShell` under **flet 0.85.3** and under **flet 1.0.5** (what `pip install -r requirements.txt` resolves to today). |
| Logic bugs | Drove the real `CommissionView` / `DecommissionView` code with fake API clients and a stub page. |
| HTTP retry behaviour | Sent POSTs through `apis/http.build_session()` to a local server that returns 502 / stalls past the read timeout, and counted arrivals. |
| Dispatch integrity | Resolved every name in `_INTERNAL_*` / `_EXTERNAL_*` maps against the client classes; cross-checked `ASSET_CATEGORIES`, `DELETION_ORDER`, `CATEGORY_GROUPS`. |
| Theme switching | Switched to light mode and read back the colors held by module-level maps. |
| Contrast | WCAG relative-luminance ratios for the button/text color pairs actually used. |
| Static analysis | `vulture` (filtered against the string-dispatch maps), `ruff` (extended rule set), `bandit`. |

When this audit was written there were no tests, no CI and no
`pyproject.toml`; see the status section below.

## Status after the follow-up fix

| Item | Status |
|---|---|
| H1 flet 1.0 crash | **Fixed:** migrated to flet 1.0.5 (`flet>=1.0.5,<1.1`): `ElevatedButton` → `ft.Button`, input borders moved to the `border=` API (the old properties are removed in 1.3). `tests/test_flet_api.py` guards both, and flet deprecation warnings fail the test suite. |
| H2 duplicate POSTs | **Fixed:** POST retries only on connection errors and 429 (`apis/http.py`); covered by `tests/test_http.py`. |
| H3 runs in background | **Fixed:** run registry in `utils/session.py`; `main.py` guards navigation, Esc, theme switch, Cmd-K and logout; logout/expiry cancel the run. |
| H4 API key leak | **Fixed (deletion):** commission and decommission delete their temporary key whenever the flow ends. The key is still written to the log, by request. |
| H5 incomplete deletes | **Fixed:** public API follows `next_page_token`; Visits/Visitors/Archives/Incidents are re-listed and drained when a whole category is deleted. The internal `get_user`/`get_camera` 1000-item caps remain, but neither is used by any flow. |
| H6 commission hang | **Fixed:** key/client creation are reported steps; any error ends in a report. |
| H7 region ignored | **Fixed, superseded:** there is no region/shard picker any more. Before login the client calls `org/validate_short_name` (global `vglobal` service) and builds every host from the org's shard metadata (`<service>.<domain>`, gateway label); the public API host comes from the shard's region (`US`/`EU`/`AU`), not from `public_api_endpoint`, which is `apiadmin` on every shard. This replaced the earlier guess of `api.eu.command.verkada.com`-style EU/AU hosts, which the Ohio-shard HARs showed to be the wrong model. |
| M1 wrong report | **Fixed:** outcome derived from step counters; `track()` removed. |
| M2 count mismatch | **Fixed:** read-only categories (`READ_ONLY_CATEGORIES`) are never selectable or counted. |
| M3 search vs delete | **Fixed:** item-level selection; Select all/none scope to search matches. |
| M4 light-mode colors | **Fixed:** colors resolved at draw time; toasts use a neutral surface. |
| M5 unreadable buttons | **Fixed:** shared components everywhere; `danger_button` text also corrected (was 2.66:1 in dark mode). |
| M7 scan changes org | **Fixed per owner decision:** Global Site Admin is turned back off on every exit; Access System/User Admin stay granted. |
| M9 password trimmed | **Fixed.** |
| M12 wrong version | **Fixed:** `APP_VERSION = "3.5"`. |
| M13 search focus | **Fixed:** search field is reused across re-renders. |
| Section 4a dead code | **Removed**, except `image_url` (kept as API output), `assets/templates.csv` and `docs/REDESIGN_PLAN.md` (non-code). Section 4b API methods/endpoints kept, by request. |
| I1 tests + CI | **Done:** `tests/` (pytest), `.github/workflows/ci.yml`, ruff config in `pyproject.toml`. |
| I3 one step runner | **Done:** `components.progress.StepRow` / `run_step`. |
| Section 6 docs | **Done:** README updated. |

I2 (run-lifecycle owner) was done as part of H3. I4 is done: every text
field, dropdown and button goes through `components/`. M8 is partly done:
supporting-user rows are validated before Review (dependent steps are still
not gated). Still open: M6, the rest of M8, M10, M11, M14, the security
items in section 3 (apart from API-key deletion), and I5–I11.

---

## 1. Critical / high severity

### H1. A fresh install crashes on the login screen (verified)
`requirements.txt` says `flet>=0.85`, which now resolves to **flet 1.0.5**.
flet 1.0 removed `ft.ElevatedButton`, so `LoginView`, `TwoFactorView`,
`CommissionView`, `DecommissionView` and `UsersView` all raise
`AttributeError: module 'flet' has no attribute 'ElevatedButton'` at
construction. Anyone following the README's "Install from source" steps today
gets an app that cannot reach the login form.

- Uses: `components/buttons.py:35`, `:81`; `pages/commission_view.py:202`, `:547`, `:1474`; `pages/two_factor_view.py:76`.
- **Fix now:** pin `flet>=0.85,<0.86` (or `<1.0`). **Then:** migrate to `ft.Button` — four of the six call sites disappear once the views use `primary_button`/`danger_button` (see I4).

### H2. Non-idempotent POSTs are replayed, which can create duplicates (verified)
`apis/http.py:44-49` retries `POST` on 500/502/503/504 **and** on read
timeouts. Against a local server, one `session.post()` arrived **twice** in
both cases. Every commission step is a POST (`site.create`, `org.add_device`,
`building.create`, `user.create`, `alarm.system.create`, `create_access_group`,
…). A gateway 502 or a slow response after the server already committed means a
second "HQ" site, a duplicate building, a double invite, etc.
- **Fix:** keep retries for `GET/PUT/DELETE`; for `POST`, retry only connection
  errors (request never sent) and `429` with `Retry-After`. In `urllib3`, that means
  `allowed_methods` without POST plus a separate POST policy, or `read=0` for POST.

### H3. Running jobs keep going invisibly after you navigate away, change theme, or get logged out
`main.navigate()` (`main.py:117`) builds a **new** tool view on every route
change, and nothing checks whether a run is in flight. During a
decommission/commission run:
- **Esc** (`back()`, `main.py:149`), a sidebar click, Cmd-K, or the theme toggle
  (`toggle_theme`, `main.py:158`, which rebuilds the shell) replaces the view.
  The `_run_deletions` / `_on_commission` coroutine keeps running against
  detached controls. The user loses progress, the Cancel button, and the
  report, and can start a **second concurrent run** on a fresh view.
- **Session expiry / logout** (`main.py:135,185,230,284`, `app_shell.py:431`)
  clears the *global* client, but the coroutine holds its own reference. **Deletions
  continue after the app shows the login screen.**
- **Fix:** give `AppShell` a "busy" state that views set while a run is active.
  While busy, block navigation, theme toggle and Cmd-K/Esc (or ask "Cancel the
  run?"). On logout or expiry, trip the run's `CancellationToken` before
  navigating.

### H4. External API keys leak, and their secret value is logged
`create_external_api_key()` (`apis/internal_api.py:917`) mints an **all-roles
READ_WRITE** public-API key (1 h TTL) on every decommission **scan**
(`decommission_view.py:257`) and every commission **run**
(`commission_view.py:609`), including the 5 templates that never use the
external client. Keys are never deleted (`delete_external_api_key` exists but
is unused), which is the root cause of the README's "Exceeded 10 API Keys
Limit" FAQ. Worse, the full key is written to `api_calls.log` and stdout
(`internal_api.py:965`), while the external client carefully masks its own
token.
- **Fix:** redact the key in the log line (now). Create one key per session,
  lazily and only when a flow needs it, cache it, and delete it on logout. For
  commission, create it only for VSSL.

### H5. Decommission silently misses assets in larger orgs
No list call follows a pagination cursor, so assets beyond the first page are
never scanned. They are never deleted, and the report still says "All N assets
deleted successfully".

| Call | Cap | Where |
|---|---|---|
| Public API: cameras, users, POIs, guest sites | 200 | `external_api.py:257` (no `next_page_token` loop) |
| Guest visits (Users tool) | 100 | `external_api.py:346` |
| Visitors, archives, incidents (visits too) | 99 | `internal_api.py:1851`, `:1900`, `:1927` |
| Users / cameras (internal) | 1000 | `internal_api.py:888`, `:1189` |

- **Fix:** add a paging helper to each client (`next_page_token` for the public
  API, `searchAfter`/`lastKey` for internal) and use it in every `get_*`. At
  minimum, warn in the Review step when a category returns exactly the page size.

### H6. Commission hangs if the API key or external client can't be created (verified)
In `_on_commission` (`commission_view.py:606-616`), `get_internal_client()`,
`create_external_api_key` and the `VerkadaExternalAPIClient(...)` constructor run
**outside** any `try`. With the 10-key limit reached, the exception escapes. The
screen stays on "Run" with a live Cancel button, an indeterminate progress bar,
and no report or error message. `decommission_view._on_scan` wraps the same calls
correctly.

### H7. The "API Region" selector does nothing
The login form collects `api` / `api.eu` / `api.au` and saves it
(`login_view.py:214`), but it is never passed to either client.
`VerkadaInternalAPIClient(email, password, org, shard)` (`login_view.py:222`)
has no region, and every `VerkadaExternalAPIClient(...)` call uses the default
`"api"`. In addition, three external methods hardcode
`https://api.verkada.com` (`external_api.py:379`, `:417`, `:457`) instead of
using `self.region`. EU/AU users are told by the README to pick a region that
has no effect. **Fix:** thread the region through, or remove the field until
it's supported.

---

## 2. Medium severity: correctness

| # | Finding | Where | Notes |
|---|---|---|---|
| M1 | **AS commission reports "0 failed" when a step failed** (verified). The "Configuring Wired Strobe" step has no `track(ok)`. With that step failing, the banner reads *"Commission complete — 22 steps, 0 failed."* | `commission_view.py:1341-1348` | Root cause: `all_success` duplicates state already held in `self._steps_failed`. Derive the outcome from `_steps_failed == 0` and delete `track()` and its 79 call sites. |
| M2 | **Confirm shows more assets than will be deleted** (verified). "Unassigned Devices" has no deleter but is selectable and pre-checked; Confirm counts it (*"Delete 8 Assets"*), Processing skips it (*"Deleting 5 assets"*). The README says this category is read-only. | `decommission_view.py:870`, `constants.py:293` | Render it without a checkbox and exclude it from Confirm totals. |
| M3 | **Search looks like item selection but deletion is per category.** Searching "Lab Cam" shows one camera, but the checkbox still deletes *every* camera. The README says "tick the rows you want gone". | `decommission_view.py:545` | Either add item-level selection or label the search "filter view only" and show the category total next to the checkbox. |
| M4 | **Theme switch leaves stale colors** (verified). `_KIND`, `_STATUS`, `_TOAST_BG`, `NAV_ITEMS`, `_TOOLS` capture palette colors at import time, so light mode keeps dark-mode banners, status icons, toasts, nav icons and home tiles. Example: success mint `#8fd4b0` on white measures **1.72:1**. | `components/surfaces.py:16`, `components/progress.py:22`, `utils/ui_utils.py:5`, `pages/app_shell.py:35`, `pages/home_view.py:16` | Store token *names* and resolve with `getattr(theme, name)` at render time. Same pattern makes `_THEMED_MODULES`/`apply_to` unnecessary. |
| M5 | **Unreadable primary buttons in dark mode.** Hand-rolled buttons put `TEXT_PRIMARY` on `PRIMARY` (**1.63:1**: Review, Commission Organization, Verify) or on `SECONDARY` (**1.30:1**: commission "Return to Home"). WCAG AA needs 4.5:1; `primary_button` (`ON_ACCENT`) is 7.56:1. | `commission_view.py:202,547,1474`, `two_factor_view.py:76` | Use the components. |
| M6 | **Alarm sites hidden on transient errors.** `get_alarm_site` treats *any* `APIError` (401/403/500) as "this site has no alarm site". | `internal_api.py:2375` | Skip only the specific not-found response; re-raise the rest. |
| M7 | **The scan changes org-wide settings.** Scanning enables Global Site Admin (org-wide, affects every admin) and Access Admin before the user decides anything. GSA is reverted only after a fully successful delete; Access Admin is never reverted. Scan and leave, or have a single failed delete, and the org stays elevated. | `decommission_view.py:278-289`, `:1202` | Track what the scan changed and restore it on exit / any outcome, or make it an explicit opt-in. |
| M8 | **Commission steps are not gated on their prerequisites.** Review counts supporting users with *any* field filled, but the run silently skips rows missing first/last/email; there's no email validation. Dependent steps run with `None` ids: VSSL "Adding User to Access Group" with a failed `group_id` (`:1068`), ESS/ACSL door creation with a failed `floor_id`. | `commission_view.py:479`, `:1373`, `:1068`, `:1087` | Validate rows in `_validate_form`; skip dependents when the prerequisite failed (as other steps already do). |
| M9 | **Passwords are `.strip()`ped**, so a password with leading/trailing whitespace can never log in. | `login_view.py:212` | Strip email/org only. |
| M10 | **Guest invites:** every participant is invited as **Org Admin** via the hidden default `role="Org Admin"`. Duplicate visits by the same guest become duplicate rows (the 2nd invite fails). Single-word names produce `first == last` ("Cher Cher"). | `internal_api.py:815`, `users_view.py:588`, `external_api.py:336` | Make role explicit at the call site (confirm intent); de-duplicate by email; use `last=""` for one-word names. |
| M11 | **CSV exports use the locale encoding**, so on Windows (cp1252) any non-Latin-1 name raises `UnicodeEncodeError`. | `utils/export.py:26`, `decommission_view.py:828` | `encoding="utf-8-sig"` (Excel-friendly). Also make the asset export reuse `export_csv` (I8). |
| M12 | **Version not bumped:** branch and changelog are v3.5, `APP_VERSION = "3.4"`. A v3.5 release built from this branch will show v3.4, and its own update checker will tell users to upgrade to v3.5. | `constants.py:5` | Bump at release; consider deriving from a single source. |
| M13 | **Show-items search rebuilds the whole SELECT screen on every keystroke**, including the search field itself, which likely drops input focus after each character. | `decommission_view.py:786` | Re-render only the item lists. |
| M14 | **Public `kits.csv` contains placeholder serials** (`XXXX-XXXX-XXXX`), which pass `is_valid_serial`, so "Kit X" sails through validation and fails at the API. | `assets/kits.csv` | Reject the placeholder, or ship the public file without kits. |

---

## 3. Security posture

| Finding | Where | Recommendation |
|---|---|---|
| Command **password stored in plaintext** in SQLite; the external-org **API key** too. Files are created with default permissions (typically world-readable on macOS/Linux). | `utils/db.py` | Use the OS keychain (`keyring`) and keep only email/org/shard in SQLite; `chmod 600` the DB; add a "Remember me" toggle. |
| Public-API key value written to `api_calls.log` / stdout. | `internal_api.py:965` | See H4. Redact. |
| Internal builds bundle an API key file inside the app (`assets/users_invite.internal.json`). Correctly gitignored, but anyone with the `.app` can read it. | `constants.py:11` | Treat internal builds as secret-bearing; prefer prompting once and storing in the keychain. |
| A **half-authenticated client** is put in session state before MFA succeeds, and `navigate()` has **no auth guard** for tool routes. Today only UI reachability prevents entry (Cmd-K is gated). | `login_view.py:232`, `main.py:117` | Hold the pending client privately in the 2FA flow; make `navigate()` refuse tool routes unless the client has `auth_data`. |
| **Logout is client-side only.** Server session cookies are not invalidated. | `app_shell.py:431` | Call the logout endpoint (or at least drop the session cookie jar) on logout/expiry. |
| `DEV_SKIP_LOGIN` bypass lives in the production client. | `constants.py:27`, `internal_api.py:611` | Move it behind an env var read only by `tools/` or a dev entry point. |

`bandit` reported only two low-severity false positives (`"<password>"`
placeholders in the endpoint registry).

---

## 4. Dead code

All candidates were checked against the string-dispatch maps in `constants.py`
(`_INTERNAL_GETTERS`, `_INTERNAL_DELETERS`, `_EXTERNAL_GETTERS`,
`_EXTERNAL_DELETERS`). Methods reached only through those maps are **live**.
`vulture` flags ~90 of them as unused; those are false positives.

### 4a. Non-API dead code: safe to delete

| Symbol | Where | Notes |
|---|---|---|
| `pop_route` parameter | `ToolView` + all 6 views, `main.py` | Passed everywhere, **never called**. `push_route` is really `navigate`; rename and drop `pop_route`. |
| `_run_deleted`, `_run_total`, `_run_failed`, `_run_cancelled` | `decommission_view.py:1214-1217` | Write-only. |
| `mark_warning_shown`, `was_warning_shown`, `_warning_shown` | `utils/session.py` | Dead trio (warning is computed in `app_shell`). |
| `mfa_qr_enabled` | `internal_api.py:129`, `:670` | Write-only. |
| `image_url` in guest-visit rows | `external_api.py:332`, `:337` | Added in the latest commit, not consumed anywhere yet. |
| `CancellationToken.reset` | `utils/cancellation.py:27` | Fresh token per run. |
| `export_json` | `utils/export.py:33` | |
| `create_loading_overlay` | `utils/ui_utils.py:62` | |
| `badge` | `components/surfaces.py` | Exported, never used. |
| `space()`, `SPACE_3XL`, `RADIUS_SM`, `FONT_SUBTITLE` | `theme.py` | Unused tokens; keep only if the design system is meant to be complete. |
| `PAGE_PADDING`, `ESS_PARTITION_NAME` | `constants.py:53`, `:118` | |
| `if code in ("ESS", …, "AS")` | `commission_view.py:630` | Always true (lists every template). |
| Duplicate "PROCESSING state" banner comment | `decommission_view.py:939-947` | |
| `assets/templates.csv` | | Not read by code (README calls it informational). |
| `docs/REDESIGN_PLAN.md` | | Completed plan pinned to an old branch; archive or delete. |

### 4b. API layer: currently unreferenced (owner previously chose to keep as scaffolding)

**`VerkadaInternalAPIClient`: 22 methods**, updated from the July list
(`create_wired_output` is now used by AS; `access_card.*` keys are new):

- Provisioning not wired to any template: `create_alarm_partition`,
  `assign_alarm_partition_response`, `create_alarm_guard`,
  `configure_alarm_expander`, `configure_wireless_contact_sensor`,
  `configure_wireless_panic_button`, `configure_wireless_universal_transmitter`,
  `create_wired_input`, `create_mailroom_site`.
- Duplicates of live public-API methods: `get_user`, `delete_user`,
  `get_camera`, `create_access_group`, `get_access_group`,
  `delete_access_group`, `add_user_to_access_group`.
- Other: `is_org_empty`, `get_device_count`, `get_external_api_key`,
  `delete_external_api_key` (**should become live**, see H4), `get_alarm_device`,
  `delete_alarm_device`.

**`apis/endpoints.py`: 12 of 148 keys never referenced:**
`access_card.delete`, `access_card.list`, `floorplan.delete`,
`guest_type.create`, `guest_type.delete`, `guest_type.list`,
`org.device_information.list`, `permissions.access_system_admin.disable`,
`permissions.access_user_admin.disable`, `scenario.create`,
`user.add_license_plate`, `user.hard_delete`.

**~44 KB of sample `payload`/`response` data in `ENDPOINTS` is never read at
runtime** (`Endpoint.payload` / `.response` have no readers). It is documentation
living in a hot module. Moving it to `docs/` or test fixtures would shrink
`endpoints.py` from ~3,200 lines to a few hundred and make the registry
reviewable.

---

## 5. Improvements: architecture, maintainability, performance

| # | Improvement | Why |
|---|---|---|
| I1 | **Add tests + CI.** Start with pure logic: `validation`, `version_check._parse`, dispatch-map integrity (every category has a getter/deleter that exists), `DELETION_ORDER` invariants, report/outcome computation, and the view-level reproductions used for M1/M2/H6 (fake client + stub page). Add `ruff` in CI and a `pyproject.toml`. | Nothing currently catches H1, M1 or M2-class regressions. |
| I2 | **One owner for run lifecycle** (see H3): `AppShell` busy flag + cancel-on-exit. | Fixes H3 and the theme-toggle variant. |
| I3 | **Consolidate the step runner.** Three near-identical spinner→check/error implementations: `commission_view._run_step` (`:1541`), `decommission_view._run_prep_step` (`:332`), `users_view._progress_step` (`:531`). Move one into `components/progress.py`. | ~120 lines removed; consistent status rows and logging. |
| I4 | **Finish the component migration.** Commission, Decommission, Users, 2FA and the shell still hand-roll 7 `TextField`s, 4 `ElevatedButton`s, 9 `OutlinedButton`s, 3 `Dropdown`s and 16 hard-coded `radius=8/12` values that bypass `theme`. | Fixes M5, most of H1, and theme drift. |
| I5 | **Data-driven commission templates.** The five `_run_*_flow` methods (~700 lines) repeat the same create → add device → configure pattern. A per-template step list (label, callable, args-from-context, prerequisites) would make templates declarative and make prerequisite gating (M8) automatic. | Smaller, testable, and new templates become config. |
| I6 | **Faster, cheaper scans.** One scan calls `alarm.system.list` 10×, `alarm_system/get_devices` 8× per system (each returns *all* devices and filters client-side), `site.list` 3×, and probes every site twice for alarm sites. Cache these per scan and fetch independent categories concurrently (the executor is already 4 workers; only the dedup pairs Intercoms/ASP→Cameras/ACs are order-dependent). | Scan time scales with categories × round-trips today. |
| I7 | **Separate the two external-client roles.** `utils.session` has one `_external_client` slot used for *your* org (commission/decommission) and for the *source* org (Users tool, `users_view.py:182`). `decommission_view._run_deletions` re-reads the global (`:1101`) instead of using the client from its own scan. | Avoids a cross-tool collision once runs survive navigation (I2). |
| I8 | **Single export path.** `decommission_view._export_assets_csv` (`:812`) re-implements `utils.export.export_csv` (without the Downloads `makedirs`). | Less duplication; M11 fixed once. |
| I9 | **Use `logging`.** `log_api_call`/`log_system` reopen the file per line, `print` every call, and the log grows forever. A `RotatingFileHandler` with a redaction filter fixes growth and H4's logging half. | Ops hygiene. |
| I10 | **Cheaper session timer.** `AppShell._run_timer` calls `page.update()` every second (`app_shell.py:419`), diffing the whole tree, including long decommission lists. Update only the chip/banner controls. | Smoother UI on big runs. |
| I11 | **Small API-client cleanups.** `external_api.__init__` validates `region` but stores `region or "api"` (`:22`), so `None` raises. `get_alarm_device` passes `"alarm.panel.list"` as a generic key. The `set_alarm_keycode` docstring is copy-pasted from `create_alarm_system`. `delete_persons_of_interest` logs `user_id` for a person id. | Correctness of logs/docs. |

---

## 6. Documentation drift

- **README:** Architecture tree is missing `components/`, `theme.py`,
  `app_shell.py`, `utils/{prefs,validation,export,cancellation}.py` and `tools/`;
  it still describes a "push/pop route stack" (also in `main.py`'s docstring)
  and `assets/logo.icns`. Cmd/Ctrl-K is described as "jumps to Home" (it opens
  the command palette). The Users tool "date range" is a single date.
  Decommission exports CSV, not TXT. Troubleshooting points at
  `_INTERNAL_DELETE_SLUGS` (doesn't exist). The Configuration table says
  `APP_VERSION` 3.3. The per-template walkthrough still documents the retired
  `ACS` template. The Deletion Order and Supported Assets lists omit Visits,
  Visitors, Groups, Persons of Interest, Incidents, Archives and Alerts. The
  `[MIT License](LICENSE)` link is broken: there is no LICENSE file.
- `pages/home_view.py` docstring refers to `ShellView` (now `AppShell`).

---

## 7. Suggested order of work

1. **Today:** pin `flet<0.86` (H1); redact the API key in the log (H4); wrap
   commission prelude in `try` (H6); add the missing `track` / derive outcome
   from counters (M1); make Unassigned Devices non-selectable (M2); stop
   stripping passwords (M9); bump `APP_VERSION` (M12).
2. **Next:** POST retry policy (H2); run-lifecycle guard (H3/I2); API-key
   lifecycle (H4); region wiring or removal (H7); theme map fix (M4) plus
   component migration (I4/M5).
3. **Then:** pagination (H5), scan permission restore (M7), keychain storage,
   tests + CI (I1), followed by the refactors (I3, I5, I6) and dead-code removal.
