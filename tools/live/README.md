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
| `python tools/live/check.py` | read-only: shard, session validity, API keys left, which serials are in the org |
| `python tools/live/commission.py VSSL` | runs a Commission template (changes the org) |
| `python tools/live/decommission.py scan` | scan only, then release the org |
| `python tools/live/decommission.py delete "Command Users"` | deletes everything selected, keeping the listed categories |
| `NODE_PATH=$(npm root -g) node tools/live/web/probe.js` | opens Command headlessly, reports failed calls, records them |
| `LIVE_RECORD=ESS.vc.json python tools/live/commission.py ESS` | any script above, recording every vCommander call (internal and public API) to `$LIVE_OUT` |
| `NODE_PATH=$(npm root -g) node tools/live/web/explore.js /admin/sites name ["Button" ...]` | read-only: open a page, click through menus/dialogs (never a submit), print the aria tree, screenshot |
| `NODE_PATH=$(npm root -g) node tools/live/web/run.js <action> [args]` | runs `web/actions/<action>.js` and records it to `$LIVE_OUT/<action>.web.json` (most actions change the org; see each file's header) |
| `python tools/live/compare.py <recording.json or .har> ...` | registry vs. web calls: method, service, payload keys |
| `python tools/live/compare.py --diff a.vc.json,b.vc.json x.web.json,y.web.json` | vCommander's real calls vs. the web app's, per registry endpoint |

`web/ui.js` holds the UI helpers the actions share: closing Command's
pop-ups, clicking by role or text, picking address suggestions, and the two
confirm dialogs Command uses for destructive actions (a 6-digit verification
code, or "Type \"HQ\" to confirm").

## Cautions

- **Never let the browser log out.** A logout from the headless browser
  revokes the session token server-side, which also logs out the browser
  the cookies came from. `web/session.js` aborts every logout request.
- The web app tries `POST /user/logout` once or twice on every fresh load
  (a cookie-only session has no local session store). `session.js` aborts
  it, records it as `status: "blocked"`, and the session survives.
- A revoked or expired session shows up as `vtki: token revoked` or 401s;
  `check.py` reports it. Refresh `COOKIE` and `X_VERKADA_TOKEN` and start a
  new session.
