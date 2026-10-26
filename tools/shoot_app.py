"""Screenshot harness — renders a single view (and optional state) directly.

Driven by env vars so an external browser can grab one screenshot per state
without going through login:
  SHOT_VIEW  = login|twofa|home|commission|decommission|users|palette
  SHOT_STATE = view-specific (e.g. commission: configure|review|report)
  SHOT_THEME = dark|light
  SHOT_PORT  = web server port

Forces the locally-bundled CanvasKit (no_cdn) so it renders in an offline
headless browser.
"""

import contextlib
import os

import flet as ft

import constants
import theme
from constants import TEMPLATE_FIELDS
from pages import app_shell
from pages import (
    commission_view as cv,
)
from pages import (
    decommission_view as dv,
)
from pages import (
    home_view as hv,
)
from pages import (
    login_view as lv,
)
from pages import (
    two_factor_view as tv,
)
from pages import (
    users_view as uv,
)
from utils import session

VIEW = os.environ.get("SHOT_VIEW", "login")
STATE = os.environ.get("SHOT_STATE", "")
MODE = os.environ.get("SHOT_THEME", "dark")
PORT = int(os.environ.get("SHOT_PORT", "8700"))

_noop = lambda *a, **k: None  # noqa: E731

_SERIAL = "ABCD-12345678"


_PUBLIC_BUILDERS = {
    "login": lambda: lv.LoginView(_noop),
    "twofa": lambda: tv.TwoFactorView(_noop),
}
_TOOL_BUILDERS = {
    "home": lambda: hv.HomeView(_noop),
    "commission": lambda: cv.CommissionView(_noop),
    "decommission": lambda: dv.DecommissionView(_noop),
    "users": lambda: uv.UsersView(_noop),
}


def _fake_assets():
    return {
        "Cameras": [{"id": f"c{i}", "name": f"HQ Camera {i}", "serial_number": f"AAAA-{i:04d}"} for i in range(7)],
        "Access Controllers": [{"id": "ac1", "name": "HQ Controller"}],
        "Command Connectors": [{"id": "cc1", "name": "HQ Command Connector"}],
        "Doors": [{"id": "d1", "name": "Garage Door"}, {"id": "d2", "name": "Front Door"}],
        "Command Users": [{"id": "u1", "name": "Supporting Trainer"}],
        "Sites": [{"id": "s1", "name": "HQ"}],
    }


def _drive(page, view, key, state):
    if not state:
        return
    try:
        if key == "home" and state == "palette":
            from components import CommandPalette

            cmds = [
                ("Go to Home", ft.Icons.GRID_VIEW_ROUNDED, lambda: None),
                ("Go to Commission", ft.Icons.BUSINESS_ROUNDED, lambda: None),
                ("Go to User Management", ft.Icons.PEOPLE_ALT_ROUNDED, lambda: None),
                ("Go to Decommission", ft.Icons.DELETE_SWEEP_ROUNDED, lambda: None),
                ("Toggle light / dark theme", ft.Icons.BRIGHTNESS_6_ROUNDED, lambda: None),
                ("Log out", ft.Icons.LOGOUT_ROUNDED, lambda: None),
            ]
            CommandPalette(page, cmds).open()
            return
        if key == "commission":
            if state in ("review", "report"):
                view.template_dropdown.value = "AS"
                with contextlib.suppress(Exception):
                    view._on_template_change(type("E", (), {"page": page})())
                for dt in TEMPLATE_FIELDS["AS"]["devices"]:
                    f = view._device_fields.get(dt)
                    if f:
                        f.value = _SERIAL
            if state == "review":
                view._review_section.controls = view._build_review_summary("AS")
                view._form_section.visible = False
                view._review_section.visible = True
                view._stepper.set_active(1)
            elif state == "report":
                view._form_section.visible = False
                view._run_section.visible = True
                view._progress_column.visible = True
                view._steps_done = 17
                view._steps_failed = 1
                view._failures = [("Adding PTZ camera", "device offline (timeout)")]
                view._run_log = (
                    ["[ok]   Enabling custom roles", "[ok]   Creating site HQ"]
                    + ["[ok]   Configuring device"] * 14
                    + ["[FAIL] Adding PTZ camera: device offline (timeout)"]
                )
                view._render_summary(page)
        elif key == "decommission":
            view._assets = _fake_assets()
            view._selected = {c: set(range(len(i))) for c, i in view._assets.items()}
            if state == "scanning":
                # Simulate the mid-scan UI (spinner button + progress bar).
                view._scan_btn.disabled = True
                view._prep_progress.visible = True
                view._prep_progress.controls = [
                    ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, size=16), ft.Text("Enabling Global Site Admin — done", size=13)], spacing=8),
                    ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, size=16), ft.Text("Granting Access System Admin — done", size=13)], spacing=8),
                ]
                view._scan_progress_box.visible = True
                view._scan_progress.set_progress(14, 35, prefix="Scanning Cameras")
            elif state == "review":
                view._state = dv.REVIEW
                view._render_state()
            elif state == "select":
                view._state = dv.SELECT
                view._render_state()
            elif state == "confirm":
                view._selected = {
                    "Cameras": {0, 1, 2}, "Doors": {0, 1}, "Command Users": {0}
                }
                view._state = dv.CONFIRM
                view._render_state()
            elif state == "complete":
                view._results = {
                    "Command Users": (1, 1),
                    "Doors": (2, 2),
                    "Cameras": (6, 7),
                    "Access Controllers": (1, 1),
                }
                view._cancelled_at = None
                view._cleanup = [
                    ("done", "Global Site Admin turned back off"),
                    ("done", "Temporary API key deleted"),
                ]
                view._stepper.set_active(dv._STATE_STEP[dv.COMPLETE])
                view._render_complete()
        elif key == "users":
            if state.isdigit():
                step = int(state)
                if step == 2:
                    view._participants = [
                        {"first_name": "Participant", "last_name": f"{n}",
                         "email": f"trainee+{n}@verkada.com"} for n in range(1, 5)
                    ]
                    with contextlib.suppress(Exception):
                        view._rebuild_participants_list()
                view._current_step = step
                for i, s in enumerate(view._steps):
                    s.visible = i == step
                view._update_step_indicators()
    except Exception as ex:
        print("DRIVE ERROR:", ex)


def main(page: ft.Page):
    theme.set_theme_mode(MODE)
    theme.apply_to([constants, lv, tv, hv, cv, dv, uv])
    page.theme_mode = ft.ThemeMode.DARK if MODE == "dark" else ft.ThemeMode.LIGHT
    page.bgcolor = theme.BG
    page.padding = 0
    session.start_session()
    if VIEW in _PUBLIC_BUILDERS:
        page.views.append(_PUBLIC_BUILDERS[VIEW]())
        page.update()
        return
    if VIEW not in _TOOL_BUILDERS:
        raise SystemExit(f"unknown SHOT_VIEW {VIEW}")
    # Mount the tool inside the persistent shell (same as the real app).
    holder = {}

    def factory(route):
        tool = _TOOL_BUILDERS[VIEW]()
        holder["tool"] = tool
        return tool

    shell = app_shell.AppShell(navigate=_noop, tool_factory=factory, logout=_noop)
    page.views.append(shell)
    page.update()
    shell.show("/" + VIEW)
    _drive(page, holder["tool"], VIEW, STATE)
    page.update()


ft.run(main, port=PORT, web_renderer=ft.WebRenderer.CANVAS_KIT, no_cdn=True)
