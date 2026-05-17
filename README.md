# vCommander

vCommander is a desktop GUI application that helps create, populate and tear down Verkada Command organizations with a few clicks instead of hours of point-and-click management and cleanup. This tool is built on [Flet](https://flet.dev/), and ships three tools behind a single Verkada Command login.

<p align="center">
  <img src="docs/screenshots/Home-Page.png" alt="vCommander home screen" width="85%" />
</p>

---

## Table of Contents
 
- [What is vCommander?](#what-is-vcommander)
- [Who is this for?](#who-is-this-for)
- [The Three Tools at a Glance](#the-three-tools-at-a-glance)
- [Quick Start](#quick-start)
- [Developers Setup Guide](#developers-setup-guide)
- [Detailed Usage Guide](#detailed-usage-guide)
  - [Logging In](#logging-in)
  - [Commission Tool](#commission-tool)
  - [Users Invite Tool](#users-invite-tool)
  - [Decommission Tool](#decommission-tool)
- [Per-Template Walkthroughs](#per-template-walkthroughs)
- [Supported Assets (Decommission)](#supported-assets-decommission)
- [Where Data Lives](#where-data-lives)
- [Configuration](#configuration)
- [Developer Details](#developers-details)
  - [Architecture](#architecture)
  - [API Clients](#api-clients)
  - [Deletion Order](#deletion-order)
- [Troubleshooting & FAQ](#troubleshooting--faq)
- [Security Considerations](#security-considerations)
- [Disclaimer](#disclaimer)
- [License](#license)

---

## What is vCommander?

vCommander is a desktop application that automates the most tedious parts of running a Verkada Command organization at scale — especially the kind of bulk setup and teardown that happens around **Verkada Certified Engineer (VCE) training sessions**, demos, and lab environments.
 
Instead of clicking through dozens of pages in Command to add 40 cameras, invite 30 students, or wipe a lab org clean after a class, vCommander lets you do all of it from a single login screen, with progress bars, and in a few minutes.
 
It runs as a native window on macOS, Windows, and Linux. You log in with your normal Verkada Command credentials (MFA supported), pick a tool, and go.

## Who is this for?

| You are… | This tool helps you… |
|---|---|
| 🎓 A Verkada training instructor | Reset student lab orgs to a clean slate between classes. |
| 🤝 A Verkada partner or SE | Quickly stand up a demo org with a realistic device mix. |
| 🛠️ An admin who inherited a messy org | Inventory and selectively delete sprawl in one pass. |
| 👨‍💻 A developer | Extend the templates, deletion order, or API clients for your own internal automation. |

## The Three Tools at a Glance

vCommander bundles three tools behind a single login. Pick whichever you need from the home screen.
 
| Tool | What it does | When to use it |
|---|---|---|
| 🚀 **Commission** | Spins up a brand-new org from a template — sites, buildings, cameras, panels, controllers, and supporting users. | Before a training session or demo, when you need a populated org fast. |
| 📩 **Users Invite** | Pulls guest-visit participants from another Verkada org and invites them to your current org. | When you need to onboard a roster of trainees who already visited as guests. |
| 🔥 **Decommission** | Inventories every asset in the org and lets you tick the ones you want gone. Deletes them in dependency-safe order. | After a training class — wipe the lab clean for the next group. |
 
---

## Quick Start

### Step 1 — Download the app
 
1. Go to the [**Releases** page](https://github.com/not-mehul/vCommander/releases).
2. Find the latest release at the top.
3. Download the file that matches your computer:
   - **macOS** → `vCommander.app.zip` (or similar `.dmg` / `.zip`)
   - **Windows** → `vCommander.exe` or `vCommander-windows.zip` (unavailable)
   - **Linux** → see the [developer setup](#quick-start--for-developers) below (unavailable)
4. Unzip the file.
5. Drag `vCommander.app` (macOS) or the executable (Windows) into your **Applications** folder (or anywhere convenient).

> [!WARNING]
> **macOS first-launch warning:** macOS may say *"vCommander cannot be opened because the developer cannot be verified"* or *"the app is damaged"*. This is normal for apps not distributed through the App Store. To fix it:
> - **Right-click** the app and choose **Open** (don't double-click). You'll get a different prompt that lets you continue.
> - If you see *"app is damaged"*, open Terminal and run: `xattr -cr /Applications/vCommander.app`
 
### Step 2 — Launch the app and log in
 
1. Double-click **vCommander** to launch it. A login window will appear.
2. Enter your login info:
   - **Email** — the email you use to sign into Verkada Command.
   - **Password** — your Verkada Command password.
   - **Org Short Name** — the part before `.command.verkada.com` in your Command URL. For example, if you log in at `acme-training.command.verkada.com`, your short name is `acme-training`.
   - **Region** — pick `api` for US, `api.eu` for Europe, or `api.au` for Australia.
3. Click **Login**.
4. You'll be prompted for a code from SMS or your authenticator app. Enter it.

> [!TIP]
> Your credentials are saved locally so you don't have to retype them next time. Your password lives only on your computer — it's never uploaded anywhere except Verkada itself.
 
### Step 3 — Pick a tool
 
You'll land on a home screen with three buttons. Click the one you need. See the [Detailed Usage Guide](#detailed-usage-guide) below for what each tool does step-by-step.
 
---

## Developers Setup Guide

If you want to run vCommander from source, modify it, or build your own packaged version, follow the standard Python project flow.

### Prerequisites
 
- **Python 3.10+** (the codebase uses PEP 604 `X | None` typing).
- **OS:** macOS, Windows, or Linux. Flet runs as a native desktop window.
- **A Verkada Command account** with **Org Admin** rights on the target org.
- **Network access** to `*.command.verkada.com` and `api.verkada.com` (or `api.eu.verkada.com` / `api.au.verkada.com` depending on region).

### Install from source
 
```bash
# 1. Clone the repo
git clone https://github.com/not-mehul/vCommander.git
cd vCommander
 
# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
 
# 3. Install dependencies
pip install -r requirements.txt
 
# 4. Run it
python main.py
```

## Detailed Usage Guide

### Logging In
 
The login screen captures four fields plus an optional 2FA step:
 
| Field | What to enter | Example |
|---|---|---|
| Email | Your Verkada Command admin email | `you@company.com` |
| Password | Your Verkada Command password | — |
| Org Short Name | The subdomain of your Command URL | `acme-training` |
| Region | The API region your org lives in | `api`, `api.eu`, or `api.au` |

<p align="center">
  <img src="docs/screenshots/Login-Page.png" alt="Login screen" width="48%" />
  &nbsp;
  <img src="docs/screenshots/2FA-Page.png" alt="Two-Factor Authentication screen" width="48%" />
</p>
 
After successful login (and 2FA), you land on the **home screen** with the three tool tiles.
 
> ⏱ **Session timeout:** You'll be logged out automatically after **30 minutes of inactivity** (configurable in `constants.py` via `SESSION_TIMEOUT_MINUTES`). A warning appears 5 minutes before logout.
 
### Commission Tool
 
Spins up a populated org from a template.
 
**Steps:**
 
1. **Pick a template** from the dropdown:
   | Code | Display Name | Devices Created |
   |---|---|---|
   | `ESS` | Essentials | Dome, Alarm Panel |
   | `ACS` | Access Control Specialist | Disable Global Site Admin Only |
   | `VSSL` | Video Security Specialist – Lab | Bullet, PTZ, Command Connector, Access Controller, License Plate |
   | `VSSE` | Video Security Specialist – Exam | Dome, Fisheye, Bullet |
   | `AS` | Alarms Specialist | Dome, Access Controller, Alarm Panel, Keypad |
2. *(Optional)* **Pick a kit** from `assets/kits.csv` — this auto-fills device serials so you don't have to type them in.
3. **Review/override** the device serials and the supporting-user list inline if needed.
4. Click **Commission**. Watch the progress in the console pane — sites, buildings, devices, and users are created in dependency-safe order.

<p align="center">
  <img src="docs/screenshots/Commission-Templates.png" alt="Selecting a commission template" width="48%" />
  &nbsp;
  <img src="docs/screenshots/Commission-Autofill-Templates.png" alt="Commission form with kit-filled serials" width="48%" />
</p>

> 💡 Selecting a kit auto-fills every serial-number field — handy when you're cycling through the same hardware between classes.

### Users Invite Tool
 
Bulk-invites users to your current org by pulling them from another org's **guest visits** in a date range.
 
**Steps:**
 
1. **Connect to a source org** — enter its short name and a Verkada **public-API key** (generate one in the source org's Command settings).
2. **Pick a date range** — vCommander fetches the guest-visit participants who checked in during that window.
3. **Review the list** — you can edit names and emails inline, or remove rows you don't want to invite.
4. **Send invites** — invitations are sent against the org you're logged into. A copy-able summary at the end breaks down successful vs. failed invites.

<p align="center">
  <img src="docs/screenshots/User-Invite-API.png" alt="Step 1 — External org API key" width="48%" />
  &nbsp;
  <img src="docs/screenshots/User-Invite-Site-Select.png" alt="Step 2 — Site & date selection" width="48%" />
</p>
<p align="center">
  <img src="docs/screenshots/User-Invite-Review-Participants.png" alt="Step 3 — Review participants" width="48%" />
  &nbsp;
  <img src="docs/screenshots/User-Invite-Invitation-Complete.png" alt="Step 4 — Invitations complete" width="48%" />
</p>

### Decommission Tool
 
Inventories the entire org, lets you select what to wipe, then deletes it all in dependency-safe order.

> [!CAUTION]
> **The Decommission Tool is destructive**. It deletes users, devices, sites, and configurations and the operation **cannot be undone**. Always review the inventory carefully before confirming deletion. **Do not run this tool against a production org** unless you intend to wipe it completely.
 
**Steps:**
 
1. **Start Scan** — vCommander walks through the org and lists every asset, grouped by category with counts.
2. **Review** — expand each category to see individual items. Embedded devices (like cameras inside intercoms) are automatically deduplicated.
3. **Select** — tick the rows you want gone. Use *Select All* per category for shortcuts.
4. **Decommission** — click the button, **confirm in the dialog**, and watch deletion progress.
5. **Results** — see a summary of successful vs. failed deletions. Export a TXT report at any time for your records.

<p align="center">
  <img src="docs/screenshots/Decommission-Scan-Complete.png" alt="Asset inventory after scan" width="48%" />
  &nbsp;
  <img src="docs/screenshots/Decommission-In-Progress.png" alt="Deletion progress in dependency order" width="48%" />
</p>

> 🛡 **Safety net:** Nothing is deleted until you both tick boxes *and* click through the confirmation dialog. You can always close the app to abort before confirming.
 
---

## Per-Template Walkthroughs

Each template provisions a different shape of org, and a matching decommission cleans up exactly what was created. The pairs below show what a successful run looks like end-to-end — handy for verifying your output, or sanity-checking what's about to disappear.

### Essentials (`ESS`)

A minimal org with a camera, an alarm panel, and a guest site — useful for quick demos. Decommission removes the camera, alarm device, and guest site.

<p align="center">
  <img src="docs/screenshots/ESS-Commission-Complete.png" alt="ESS commission complete" width="48%" />
  &nbsp;
  <img src="docs/screenshots/Decommission-Complete-ESS.png" alt="ESS decommission complete" width="48%" />
</p>

### Access Control Specialist (`ACS`)

The lightest template — only enables custom roles and disables global site admin. No physical devices are claimed, so there's nothing for the Decommission tool to clean up afterward.

<p align="center">
  <img src="docs/screenshots/ACS-Commission-Complete.png" alt="ACS commission complete" width="60%" />
</p>

### Video Security Specialist – Lab (`VSSL`)

The full lab build: bullet, PTZ, command connector, access controller, with LPR + face analytics enabled and access groups, levels, and users provisioned. Decommission walks back through users, cameras, the connector, and the access controller in dependency order.

<p align="center">
  <img src="docs/screenshots/VSSL-Commission-Complete.png" alt="VSSL commission complete" width="48%" />
  &nbsp;
  <img src="docs/screenshots/Decommission-Complete-VSSL.png" alt="VSSL decommission complete" width="48%" />
</p>

### Video Security Specialist – Exam (`VSSE`)

Three cameras (dome, fisheye, bullet) with org-wide LPR analytics and camera analytics turned on. Decommission removes all three cameras.

<p align="center">
  <img src="docs/screenshots/VSSE-Commission-Complete.png" alt="VSSE commission complete" width="48%" />
  &nbsp;
  <img src="docs/screenshots/Decommission-Complete-VSSE.png" alt="VSSE decommission complete" width="48%" />
</p>

### Alarms Specialist (`AS`)

Camera + access controller + alarm panel + keypad, plus a configured alarm site. Decommission removes the camera, access controller, and both alarm devices.

<p align="center">
  <img src="docs/screenshots/AS-Commission-Complete.png" alt="AS commission complete" width="48%" />
  &nbsp;
  <img src="docs/screenshots/Decommission-Complete-AS.png" alt="AS decommission complete" width="48%" />
</p>

> 📋 If your run finished without "Commission complete!" or "Decommission Complete" at the bottom, open the API call log (see [Where Data Lives](#where-data-lives)) and look for the failing step — the missing line in the log will line up with whichever step is missing from the screenshots above.

---

## Supported Assets (Decommission)
 
The Decommission tool can delete:
 
- Cameras
- Command Connectors
- Access Controllers
- Environmental Sensors
- Intercoms
- Desk Stations
- Mailroom Sites
- Guest Sites
- Alarm Sites & Alarm Systems
- Alarm Devices
- Users (Admins / Members)
> ℹ️ **Read-only category:** "Unassigned Devices" appears in the inventory but cannot be deleted — Verkada does not expose a delete endpoint for those.

See the [Per-Template Walkthroughs](#per-template-walkthroughs) section above for examples of what a successful decommission summary looks like for each template.
 
---

## Where Data Lives
 
vCommander stores a small amount of state on your machine — no cloud, no telemetry.
 
| File | Contents |
|---|---|
| `<data_dir>/vcommander.db` | Saved login + import settings (SQLite). |
| `<data_dir>/api_calls.log` | One line per API call, with timestamp. |
 
Where `<data_dir>` lives:
 
- **macOS** — `~/Library/Application Support/vCommander`
- **Windows** — `%APPDATA%\vCommander`
- **Linux** — `${XDG_DATA_HOME:-~/.local/share}/vCommander`
> 🧹 **To reset saved credentials:** delete `vcommander.db`. The app will start fresh on next launch.
 
---

## Configuration
 
Everything user-tunable lives at the top of [`constants.py`](constants.py):
 
| Constant | Default | Purpose |
|---|---|---|
| `APP_VERSION` | `3.1` | Shown in the title bar and used in API key names. |
| `GITHUB_REPO` | `not-mehul/vcommander` | Repo polled for the auto-update banner. |
| `DEV_SKIP_LOGIN` | `False` | Set `True` to bypass auth and land on Home (dev only). |
| `MIN_WIDTH` / `MIN_HEIGHT` | 1100 × 800 | Window minimum size. |
| `SESSION_TIMEOUT_MINUTES` | `30` | Idle time before auto-logout. |
| `SESSION_WARNING_MINUTES` | `5` | When to show the "session ending" warning. |
| `ESS_*` / `VSSL_*` / `AS_*` … | HQ data | Default site/building/address constants per template. |
| `TEMPLATE_FIELDS` | — | Add/remove devices that a template asks for. |
| `DELETION_ORDER` | — | Order in which categories are deleted — **dependency-sensitive, edit with care.** |

### Auto-Update Check
 
On launch, vCommander checks the latest published GitHub Release and shows a dismissible dialog if a newer version is available. You can ignore it, but you'll get the most reliable behavior on the latest release since Verkada's internal APIs occasionally shift.
 
---

## Developer Details
 
### Architecture
 
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
 
`main.py` configures the Flet `Page`, defines a tiny `push/pop` route stack (Flet's built-in router was overkill for the half-dozen screens here), and mounts the `LoginView`. Each view receives `push_route` and `pop_route` callbacks so it can navigate without importing the others.
 
### API Clients
 
**`VerkadaInternalAPIClient`** (`apis/internal_api.py`)
- Mimics browser behavior using session cookies and CSRF tokens.
- Accesses internal/private APIs for comprehensive device management.
- Handles login, MFA verification, and privilege escalation.
- Dynamically generates temporary API keys with a 1-hour TTL.
**`VerkadaExternalAPIClient`** (`apis/external_api.py`)
- Uses the standard public API endpoints documented at [`apidocs.verkada.com`](https://apidocs.verkada.com).
- Automatic token generation and retry logic.
- Used for guest-visit pulls and cross-org user invitations.
The Decommission tool uses a **hybrid architecture** — combining the internal client (for assets the public API doesn't expose) with the external client (for everything else) to get full coverage.

### Deletion Order
 
To prevent dependency errors, the Decommission tool deletes assets in this fixed order (configurable via `DELETION_ORDER` in `constants.py`):
 
1. **Users** (deleted first to prevent interference)
2. Sensors
3. Intercoms
4. Desk Stations
5. Mailroom Sites
6. Guest Sites
7. Access Controllers
8. Cameras
9. Command Connector
10. Alarm Devices
11. **Alarm Sites** (includes Alarm Systems, last because they own children)
> ⚠️ Editing `DELETION_ORDER` carelessly will produce foreign-key-style API errors mid-run. If you add a new asset type, slot it where its dependencies are already gone.

## Troubleshooting & FAQ
 
<details>
<summary><b>"Internal client is not available. Please log in again."</b></summary>
Your session expired or the process restarted. Just log in again — credentials are remembered.
</details>
<details>
<summary><b>I'm stuck in an MFA loop.</b></summary>
Make sure your phone is reachable and the SMS/TOTP code is for the **same account** you typed in the login form. Codes expire quickly — request a new one if it's been more than 30 seconds.
</details>
<details>
<summary><b>API failures during Commission.</b></summary>
Open the log file (path is printed on startup, also see [Where Data Lives](#where-data-lives)) and look for the failing line. The status code and a response summary are inline.
</details>
<details>
<summary><b>A delete from Decommission silently does nothing.</b></summary>
Check that the category is wired up in `_INTERNAL_DELETE_SLUGS` or `_EXTERNAL_DELETERS` in `constants.py`. Note: "Unassigned Devices" has no delete endpoint by design — Verkada does not expose one.
</details>
<details>
<summary><b>"Exceeded 10 API Keys Limit"</b></summary>
Delete old API keys from your Verkada dashboard. Keys generated by vCommander expire after 1 hour automatically, but if you've been running it heavily you may have stacked up before they expired.
</details>
<details>
<summary><b>macOS says the app "is damaged and can't be opened."</b></summary>
This is Gatekeeper, not actual damage. Run:
```bash
xattr -cr /Applications/vCommander.app
```
Then reopen.
</details>
<details>
<summary><b>I'm not a developer — do I really need Python?</b></summary>
No. Download a prebuilt release from the [Releases page](https://github.com/not-mehul/vCommander/releases) and skip the Python setup entirely. The Python instructions are only for people who want to run from source or modify the code.
</details>
<details>
<summary><b>Where are my credentials stored? Is this safe?</b></summary>
Credentials are stored locally in a SQLite file on your computer (see [Where Data Lives](#where-data-lives)). They're never uploaded anywhere except to Verkada itself when you log in. To wipe them, delete `vcommander.db`. MFA is supported and strongly recommended.
</details>

---

## Security Considerations
 
- Login credentials are stored locally in a SQLite file. Delete `vcommander.db` to wipe.
- Internal-API tokens are temporary (1-hour expiration).
- MFA is supported and recommended.
- The tool requires Organization Admin privileges.
- All deletions are permanent and cannot be undone.

---
 
## Disclaimer
 
> [!IMPORTANT]
> This software is an **unofficial tool** and is **not supported by Verkada**. It uses internal APIs which may change without notice. Use at your own risk. Always test in a non-production environment first. The authors are not responsible for any data loss or damage caused by using this tool.
 
---
 
## License
 
[MIT License](LICENSE)
