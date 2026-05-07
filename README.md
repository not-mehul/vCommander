# vCommander

A desktop GUI tool for bulk-managing a Verkada Command organization. It
wraps the internal Verkada API plus the external Verkada API behind a
[Flet](https://flet.dev/) frontend, and ships three workflows:

| Tool             | What it does                                                                                  |
| ---------------- | --------------------------------------------------------------------------------------------- |
| **Commission**   | Spins up a brand-new org from a template (sites, buildings, cameras, panels, controllers, users) using a saved hardware kit. |
| **Users**        | Pull guest participants from an external org and invites them to the org you're logged in to. |
| **Decommission** | Inventory every asset in the org and delete selected ones in dependency-safe order.            |

> ⚠️ vCommander uses undocumented internal APIs in addition to the
> public API. Treat it as an internal-only training/lab tool — do not
> point it at production orgs.

## Requirements

- Python **3.10+** (the codebase uses PEP 604 `X | None` typing).
- macOS, Windows, or Linux (Flet runs as a native desktop window).
- A Verkada Command account with Org admin rights on the target org.

## First-time Setup

1. **Log in.** Enter the email, password, and **org short name** for
   the org you want to operate on. Pick the matching API region
   (`api`, `api.eu`, or `api.au`). Credentials are saved to a local SQLite file (see
   [Where data lives](#where-data-lives)) so you don't have to retype
   them.
2. **Complete 2FA.** If your account has SMS / authenticator MFA
   enabled, you'll be routed to the 2FA screen automatically.
3. **Pick a tool** from the home screen. Each tool has its own session
   timer in the header — after 30 minutes of inactivity (configurable
   in `constants.py`) you'll be bounced back to the login screen.

## Tools

### Commission

Use this to provision a new org from one of the built-in templates:

| Code   | Display name                       | Devices created                                      |
| ------ | ---------------------------------- | ---------------------------------------------------- |
| `ESS`  | Essentials                         | Dome, Alarm Panel                                    |
| `ACS`  | Access Control Specialist          | (users + access groups only)                         |
| `VSSL` | Video Security Specialist – Lab    | Bullet, PTZ, Command Connector, Access Controller, License Plate |
| `VSSE` | Video Security Specialist – Exam   | Dome, Fisheye, Bullet                                |
| `AS`   | Alarms Specialist                  | Dome, Access Controller, Alarm Panel, Keypad         |

Steps inside the screen:

1. Pick a **template**.
2. (Optional) pick a **kit** from `assets/kits.csv` to auto-fill device
   serial numbers.
3. Review/override the device serials and the supporting-user list.
4. Click **Commission**.

### Users Invite

A 4-step wizard for inviting guests from one org to another:

1. **Connect** to the *source* (external) org with its short name and a
   public-API key.
2. **Pick a date range** — the app pulls guest visits in that window
   from the source org.
3. **Review** the participant list. Remove rows you don't want to
   invite or fix typos in name/email.
4. **Send invites** against the org you logged in to in step 1 of the
   app. A copy-able summary lists who was invited successfully and who
   failed.

### Decommission

Lists every asset in the logged-in org grouped by category (Cameras,
Sensors, Intercoms, Alarm Devices, …). Tick the rows you want gone and
click delete.

> The "Unassigned Devices" category is read-only — Verkada has no
> endpoint to delete those.

## Project layout

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
│   ├── home_view.py         # /home    – tool picker + session timer
│   ├── commission_view.py   # /commission
│   ├── users_view.py        # /users
│   └── decommission_view.py # /decommission
├── utils/
│   ├── db.py        # SQLite credentials + import-settings store
│   ├── executor.py  # Shared ThreadPoolExecutor (4 workers)
│   ├── logger.py    # Append-only API call log
│   ├── session.py   # Process-wide auth state (current user / clients)
│   └── ui_utils.py  # Button-loading, alerts, loading overlay
└── assets/
    ├── kits.csv         # Editable device-serial presets
    ├── templates.csv    # (informational — actual template logic lives in constants.py)
    └── logo.icns
```

## Where data lives

| File                                     | Contents                                  |
| ---------------------------------------- | ----------------------------------------- |
| `<data_dir>/vcommander.db`               | Saved login + import settings (SQLite).   |
| `<data_dir>/api_calls.log`               | One line per API call, with timestamp.    |

`<data_dir>` resolves to:
- macOS: `~/Library/Application Support/vCommander`
- Windows: `%APPDATA%\vCommander`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/vCommander`

To reset the saved credentials, just delete `vcommander.db`.

## Configuration knobs

Everything user-tunable lives at the top of `constants.py`:

| Constant                      | Default | Purpose                                           |
| ----------------------------- | ------- | ------------------------------------------------- |
| `APP_VERSION`                 | `3.0`   | Shown in the title bar and used in API key names. |
| `DEV_SKIP_LOGIN`              | `False` | Set `True` to bypass auth and land on Home (dev only). |
| `MIN_WIDTH` / `MIN_HEIGHT`    | 1100×800| Window minimum size.                              |
| `SESSION_TIMEOUT_MINUTES`     | `30`    | How long until auto-logout.                       |
| `SESSION_WARNING_MINUTES`     | `5`     | When to show the "session ending" warning.        |
| `ESS_*` / `VSSL_*` / `AS_*` … | HQ data | Default site/building/address constants per template. Adjust if your reference site isn't 406 E 3rd Ave. |
| `TEMPLATE_FIELDS`             | —       | Add/remove devices a template asks for.           |
| `DELETION_ORDER`              | —       | Order in which categories are deleted on the Decommission screen — **dependency-sensitive, edit with care.** |

## Troubleshooting

- **"Internal client is not available. Please log in again."** — your
  session expired or the process was restarted; log in again.
- **MFA loop** — make sure your phone is reachable and the SMS/TOTP
  code is for the same account you typed in the login form.
- **API failures during Commission** — open the log file (path is
  printed on startup) and look for the failing line; status code and
  response summary are inline.
- **A delete from Decommission silently does nothing** — check that
  the category you're trying to delete is in `_INTERNAL_DELETE_SLUGS`
  or `_EXTERNAL_DELETERS` in `constants.py`. "Unassigned Devices" has
  no delete endpoint by design
