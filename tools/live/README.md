# Live checks against a real Command org

For the full endpoint-validation procedure (record the Command web app,
compare with vCommander, improve), see
[`docs/LIVE_VALIDATION_RUNBOOK.md`](../../docs/LIVE_VALIDATION_RUNBOOK.md).

Scripts for checking vCommander against a **test** org: the real Commission
and Decommission flows run headlessly, and a headless browser records which
API calls the Command web app makes, so they can be compared with
vCommander's endpoint registry (`apis/endpoints.py`).

**Use a throwaway org.** `commission.py` claims devices and changes org
settings; `decommission.py delete` deletes for real.

## Environment

Set these as environment secrets (never in files in the repo):

| Variable | Value |
|---|---|
| `VERKADA_ORG` | org short name |
| `VERKADA_EMAIL` | email of the account the session belongs to (excluded from user deletion) |
| `COOKIE` | the `Cookie` header of a logged-in Command browser tab |
| `X_VERKADA_TOKEN`, `X_VERKADA_USER_ID`, `X_VERKADA_ORGANIZATION_ID` | the matching `x-verkada-*` request headers |
| `Access_Controller`, `Access_Station_Pro`, `Alarm_Panel`, `Bullet`, `Command_Connector`, `Dome`, `Fisheye`, `Keypad`, `PTZ` | one device serial each |

The session cookies stand in for a password login, so orgs that enforce 2FA
work. Outputs (recordings, screenshots, `compare.json`) go to `$LIVE_OUT`
(default `~/.vcommander-live`), outside the repo. Printed output is
redacted: no tokens, ids, emails, org name or serials.

## Scripts

| Command | Effect |
|---|---|
| `python tools/live/check.py` | read-only: shard, session validity, which serials are in the org |
| `python tools/live/commission.py VSSL` | runs a Commission template (changes the org) |
| `python tools/live/decommission.py scan` | scan only, then release the org |
| `python tools/live/decommission.py delete "Command Users"` | deletes everything selected, keeping the listed categories |
| `NODE_PATH=$(npm root -g) node tools/live/web/probe.js` | opens Command headlessly, reports failed calls, records them |
| `python tools/live/compare.py <recording.json or .har> ...` | registry vs. web calls: method, service, payload keys |

## Cautions

- **Never let the browser log out.** A logout from the headless browser
  revokes the session token server-side, which also logs out the browser
  the cookies came from. `web/session.js` aborts every logout request.
- A revoked or expired session shows up as `vtki: token revoked` or 401s;
  `check.py` reports it. Refresh `COOKIE` and `X_VERKADA_TOKEN` and start a
  new session.
