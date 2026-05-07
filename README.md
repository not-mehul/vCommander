vCommander

vCommander is a desktop GUI application for bulk-managing a Verkada Command organization. Built on [Flet](https://flet.dev/), it ships three tools behind a single Verkada Command login: provisioning new orgs from templates, inviting guests across orgs, and decommissioning every asset in an org in dependency-safe order.

> [!CAUTION]
> **The Decommission Tool is destructive**. It deletes users, devices, sites, and configurations and the operation **cannot be undone**. Always review the inventory carefully before confirming deletion. **Do not run this tool against a production org** unless you intend to wipe it completely.

## Key Features
### Multi-Tool Dashboard
- **Commission Tool** — Spin up a brand-new org from a template (sites, buildings, cameras, panels, controllers, users) using a saved hardware kit.
- **Users Invite Tool** — Pull guest participants from an external org and invite them to the org you're logged in to.
- **Decommission Tool** — Inventory every asset in the org and delete selected ones in dependency-safe order.
### Authentication & Security
- **Secure Login** — Email/password authentication with optional MFA/2FA support.
- **Session Management** — A per-tool session timer auto-logs you out after 30 minutes of inactivity (configurable).
- **Local Credential Storage** — Login + import settings persist in a local SQLite file so you don't have to retype them.
### Commission Tool
- **Built-in Templates** — `ESS`, `ACS`, `VSSL`, `VSSE`, and `AS` templates each provision a different mix of devices, users, and access groups.
- **Editable Hardware Kits** — `assets/kits.csv` holds device-serial presets that auto-fill template fields. Override per run if needed.
- **Dependency-Aware Provisioning** — Sites, buildings, devices, and users are created in the correct order via the internal API.
### Users Invite Tool
- **Cross-Organization Import** — Connect to a *source* Verkada org with a public-API key and short name.
- **Date-Ranged Guest Pull** — Select a window and the app fetches guest-visit participants from the source org.
- **Review Before Invite** — Edit names/emails inline, drop unwanted rows, then send invites against the logged-in org. A summary breaks down successes vs. failures.
### Decommission Tool
- **Hybrid API Architecture** — Combines the internal API (browser-emulated session) with the public API for full asset coverage.
- **Smart Inventory** — Automatically deduplicates embedded devices (e.g. cameras inside intercoms).
- **Selective Deletion** — Tick the rows you want gone; everything else stays.
- **Dependency-Safe Deletion Order** — Deletes assets in a fixed order to avoid foreign-key style API errors.
### Auto-Update Check
On launch, vCommander checks the latest published GitHub Release and shows a dismissible dialog if a newer version is available.
## Supported Assets (Decommission)
- Cameras
- Access Controllers
- Environmental Sensors
- Intercoms
- Desk Stations
- Mailroom Sites
- Guest Sites
- Alarm Sites & Alarm Systems
- Alarm Devices
- Users (Admins / Members)
> The "Unassigned Devices" category is read-only — Verkada has no endpoint to delete those.
## Prerequisites
- **Python 3.10+** (the codebase uses PEP 604 `X | None` typing).
- **OS** — macOS, Windows, or Linux. Flet runs as a native desktop window.
- **Verkada Command account** with Org Admin rights on the target org.
- **Network Access** to `*.command.verkada.com` and `api.verkada.com` (or `api.eu.verkada.com` / `api.au.verkada.com` depending on region).
## Dependencies
```
flet>=0.21
requests>=2.31
urllib3>=2.0
```
## Installation
1. **Clone the repository:**
   ```bash
   git clone https://github.com/not-mehul/vCommander
   cd vCommander
   ```
2. **Set up a virtual environment (recommended):**
   ```bash
   python -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
## Usage
### Starting the Application
```bash
python main.py
```

## Login
1. Enter your Verkada credentials:
   - **Email** — your admin email address.
   - **Password** — your admin password.
   - **Org Short Name** — the subdomain from `<short-name>.command.verkada.com`.
   - **Region** — `api`, `api.eu`, or `api.au` depending on where the org lives.
2. Click **Login**. Credentials are saved locally for next time.
3. If MFA is enabled, you'll be routed to the 2FA screen automatically — enter the SMS or authenticator code.
### Commission Tool
1. **Pick a template** from the dropdown:
   | Code   | Display name                       | Devices created                                                  |
   | ------ | ---------------------------------- | ---------------------------------------------------------------- |
   | `ESS`  | Essentials                         | Dome, Alarm Panel                                                |
   | `ACS`  | Access Control Specialist          | (users + access groups only)                                     |
   | `VSSL` | Video Security Specialist – Lab    | Bullet, PTZ, Command Connector, Access Controller, License Plate |
   | `VSSE` | Video Security Specialist – Exam   | Dome, Fisheye, Bullet                                            |
   | `AS`   | Alarms Specialist                  | Dome, Access Controller, Alarm Panel, Keypad                     |
2. *(Optional)* **Pick a kit** from `assets/kits.csv` to auto-fill device serials.
3. **Review/override** the device serials and the supporting-user list.
4. Click **Commission** and watch progress in the console.
### Users Invite Tool
1. **Connect** to the *source* (external) org by entering its short name and a public-API key.
2. **Pick a date range** — the app fetches guest visits in that window.
3. **Review** the participant list. Remove rows you don't want or fix typos in name/email.
4. **Send invites** against the org you logged in to. A copy-able summary lists who was invited successfully and who failed.
### Decommission Tool
1. **Scan** — click *Start Scan* to inventory every asset.
2. **Review** — assets are grouped by category with counts.
3. **Select** — tick the rows you want gone. Use *Select All* per-category as a shortcut.
4. **Decommission** — click and confirm. Assets are deleted in a strict dependency-safe order.
5. **Results** — view summary of successful and failed deletions; export a TXT report at any time.
## Where Data Lives
| File                         | Contents                                |
| ---------------------------- | --------------------------------------- |
| `<data_dir>/vcommander.db`   | Saved login + import settings (SQLite). |
| `<data_dir>/api_calls.log`   | One line per API call, with timestamp.  |
`<data_dir>` resolves to:
- **macOS** — `~/Library/Application Support/vCommander`
- **Windows** — `%APPDATA%\vCommander`
- **Linux** — `${XDG_DATA_HOME:-~/.local/share}/vCommander`
To reset saved credentials, delete `vcommander.db`.
## Configuration Knobs
Everything user-tunable lives at the top of `constants.py`:
| Constant                      | Default  | Purpose                                                                  |
| ----------------------------- | -------- | ------------------------------------------------------------------------ |
| `APP_VERSION`                 | `3.0`    | Shown in the title bar and used in API key names.                        |
| `GITHUB_REPO`                 | `not-mehul/vcommander` | Repo polled for the auto-update banner.                    |
| `DEV_SKIP_LOGIN`              | `False`  | Set `True` to bypass auth and land on Home (dev only).                   |
| `MIN_WIDTH` / `MIN_HEIGHT`    | 1100×800 | Window minimum size.                                                     |
| `SESSION_TIMEOUT_MINUTES`     | `30`     | Idle time before auto-logout.                                            |
| `SESSION_WARNING_MINUTES`     | `5`      | When to show the "session ending" warning.                               |
| `ESS_*` / `VSSL_*` / `AS_*` … | HQ data  | Default site/building/address constants per template.                    |
| `TEMPLATE_FIELDS`             | —        | Add/remove devices a template asks for.                                  |
| `DELETION_ORDER`              | —        | Order in which categories are deleted — **dependency-sensitive, edit with care.** |
## Building a Standalone macOS App
vCommander can be packaged into a standard `.app` bundle using Flet's built-in builder.
### Prerequisites
- Xcode + Command Line Tools (`xcode-select --install`)
- CocoaPods (`brew install cocoapods`)
- Flutter SDK (`brew install --cask flutter` then `flutter config --enable-macos-desktop`)
- A 1024×1024 `assets/icon.png` (Flet's icon generator does not read `.icns`).
### Build
From the repo root:
```bash
flet build macos \
  --project vCommander \
  --product "vCommander" \
  --org com.example.vcommander \
  --build-version 3.0
```
The output lands in `build/macos/vCommander.app`. Open it with `open build/macos/vCommander.app`.
### Sharing Without an Apple Developer Account
You don't need a paid Apple Developer membership to build or share the `.app`, but recipients will hit Gatekeeper on first launch. The cheapest workaround is an **ad-hoc signature**:
```bash
codesign --force --deep --sign - build/macos/vCommander.app
```
Recipients will still see "unidentified developer" on first launch — they can right-click → *Open* once to whitelist it. If they see "*app is damaged*", strip the quarantine attribute:
```bash
xattr -cr /Applications/vCommander.app
```
For a fully smooth experience (no warnings), you'd need a paid Apple Developer Program membership to sign with a Developer ID and submit for notarization.
## Architecture Overview
```
vCommander/
├── main.py                  # Flet entry point + tiny push/pop router
├── constants.py             # Theme, layout, template + decommission tables
├── requirements.txt
├── apis/
│   ├── internal_api.py      # VerkadaInternalAPIClient (vprovision)
│   └── external_api.py      # VerkadaExternalAPIClient (apidocs.verkada.com)
├── pages/
│   ├── login_view.py        # /login
│   ├── two_factor_view.py   # /2fa
│   ├── home_view.py         # /home – tool picker + session timer
│   ├── commission_view.py   # /commission
│   ├── users_view.py        # /users
│   └── decommission_view.py # /decommission
├── utils/
│   ├── db.py                # SQLite credentials + import-settings store
│   ├── executor.py          # Shared ThreadPoolExecutor (4 workers)
│   ├── logger.py            # Append-only API call log
│   ├── session.py           # Process-wide auth state
│   ├── ui_utils.py          # Button-loading, alerts, loading overlay
│   └── version_check.py     # GitHub release version check
└── assets/
    ├── kits.csv             # Editable device-serial presets
    ├── templates.csv        # Informational template list
    └── logo.icns
```
### API Clients
**`VerkadaInternalAPIClient`**
- Mimics browser behavior using session cookies and CSRF tokens.
- Accesses internal/private APIs for comprehensive device management.
- Handles login, MFA verification, and privilege escalation.
- Dynamically generates temporary API keys (1-hour TTL).
**`VerkadaExternalAPIClient`**
- Uses the standard public API endpoints documented at `apidocs.verkada.com`.
- Automatic token generation and retry logic.
- Used for guest-visit pulls and cross-org user invitations.
### Deletion Order
To prevent dependency errors, the Decommission tool deletes assets in this order (configurable via `DELETION_ORDER` in `constants.py`):
1. **Users** (prevents interference)
2. **Sensors**
3. **Intercoms**
4. **Desk Stations**
5. **Mailroom Sites**
6. **Guest Sites**
7. **Access Controllers**
8. **Cameras**
9. **Alarm Devices**
10. **Alarm Sites** (includes Alarm Systems)
## Troubleshooting
- **"Internal client is not available. Please log in again."** — your session expired or the process was restarted; log in again.
- **MFA loop** — make sure your phone is reachable and the SMS/TOTP code is for the same account you typed in the login form.
- **API failures during Commission** — open the log file (path is printed on startup) and look for the failing line. Status code and response summary are inline.
- **A delete from Decommission silently does nothing** — check that the category is wired up in `_INTERNAL_DELETE_SLUGS` or `_EXTERNAL_DELETERS` in `constants.py`. "Unassigned Devices" has no delete endpoint by design.
- **"Exceeded 10 API Keys Limit"** — delete old API keys from your Verkada dashboard. Keys generated by this tool expire after 1 hour automatically.
## Security Considerations
- Login credentials are stored locally in a SQLite file; delete `vcommander.db` to wipe.
- Internal-API tokens are temporary (1-hour expiration).
- MFA is supported and recommended.
- The tool requires Organization Admin privileges.
- All deletions are permanent and cannot be undone.
## Disclaimer
> [!IMPORTANT]
> This software is an unofficial tool and is **not supported by Verkada**. It uses internal APIs which may change without notice. Use at your own risk. Always test in a non-production environment first. The authors are not responsible for any data loss or damage caused by using this tool.
## License
[MIT License](LICENSE)
