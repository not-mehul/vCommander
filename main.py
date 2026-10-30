"""vCommander entry point.

Configures the Flet `Page` and owns navigation. Public screens (login, 2FA)
replace the whole view; authenticated tools are hosted inside one persistent
`AppShell` whose content area swaps per route. Every view receives a single
`push_route(route)` callback so it can navigate without importing the others.

Navigation, theme switches and logout all pass through a run guard: while a
long-running job (commission, decommission scan/delete, invite batch) is in
progress, the user is asked before it is abandoned, and leaving cancels it
cooperatively instead of letting it keep calling the API in the background.
"""

import asyncio
import sys
import webbrowser

import flet as ft

import constants
import theme
from components import CommandPalette
from constants import (
    APP_VERSION,
    BG,
    BUILD_VARIANT_LABEL,
    MIN_HEIGHT,
    MIN_WIDTH,
    WARNING,
)
from pages import (
    app_shell,
    commission_view,
    decommission_view,
    home_view,
    login_view,
    two_factor_view,
    users_view,
)
from pages.commission_view import CommissionView
from pages.decommission_view import DecommissionView
from pages.home_view import HomeView
from pages.login_view import LoginView
from pages.two_factor_view import TwoFactorView
from pages.users_view import UsersView
from utils import prefs
from utils.logger import (
    LOG_RETENTION_DAYS,
    get_log_path,
    log_api_call,
    prune_old_entries,
)
from utils.session import (
    cancel_run,
    clear_session,
    is_session_expired,
    running_job,
    session_active,
)
from utils.tasks import spawn
from utils.ui_utils import show_confirm
from utils.version_check import check_for_update

# Modules that imported flat color names by value and therefore need their
# globals re-pointed at the active palette on a theme switch.
_THEMED_MODULES = [
    constants,
    login_view,
    two_factor_view,
    home_view,
    commission_view,
    decommission_view,
    users_view,
]

# How often the background watchdog re-checks the session clock. Enforcement
# is independent of any view's own timer, so the timeout still fires while
# the user is inside a tool or the window is backgrounded.
_SESSION_WATCHDOG_INTERVAL = 5


async def main(page: ft.Page):
    """Flet app entry point. Sets window chrome and pushes the login screen."""
    pruned = prune_old_entries()
    log_api_call(
        "APP", "startup", "{}", "200",
        f"vCommander v{APP_VERSION}"
        + (f"; dropped {pruned} log lines older than {LOG_RETENTION_DAYS} days" if pruned else ""),
    )
    print(f"Logs → {get_log_path()}")

    page.title = f"vCommander {BUILD_VARIANT_LABEL}v{APP_VERSION}"
    page.window.min_width = MIN_WIDTH
    page.window.min_height = MIN_HEIGHT
    page.window.width = MIN_WIDTH
    page.window.height = MIN_HEIGHT
    page.padding = 0

    # Authenticated tool routes are shown inside one persistent AppShell;
    # public routes replace the whole view.
    TOOL_ROUTES = {
        "/home": HomeView,
        "/commission": CommissionView,
        "/users": UsersView,
        "/decommission": DecommissionView,
    }
    PUBLIC = {"/login": LoginView, "/2fa": TwoFactorView}

    state = {"shell": None}
    current = {"route": "/login"}

    def _set_palette(mode: str):
        """Switch the active palette and re-point every themed module at it."""
        theme.set_theme_mode(mode)
        theme.apply_to([*_THEMED_MODULES, sys.modules[__name__]])
        page.theme_mode = (
            ft.ThemeMode.DARK if mode == "dark" else ft.ThemeMode.LIGHT
        )
        page.bgcolor = theme.BG

    def guarded(action: str, proceed):
        """Run `proceed()` now, or after confirming that the active job stops.

        `action` completes the sentence "<Leaving> will cancel it…".
        """
        job = running_job()
        if job is None:
            proceed()
            return

        def stop_and_proceed():
            cancel_run()
            proceed()

        show_confirm(
            page,
            f"{job} in progress",
            f"{action} will cancel it after the current step finishes. "
            "Steps already done are not undone.",
            confirm_label="Stop and continue",
            cancel_label="Keep running",
            on_confirm=stop_and_proceed,
        )

    def make_tool(route):
        return TOOL_ROUTES[route](push_route=navigate)

    def _drop_shell():
        """Discard the shell, letting the hosted tool release what it holds."""
        shell = state["shell"]
        state["shell"] = None
        if shell is not None:
            shell.leave()

    def _go(route: str, restore=None):
        """Unguarded navigation. Callers decide whether a job may be abandoned.

        `restore` is handed to the new tool screen (see AppShell.show).

        Public routes (login/2FA) replace the whole view. Tool routes are
        shown inside the one persistent AppShell — only the content area
        swaps, so the sidebar stays constant and there's no page transition.
        """
        if route in PUBLIC:
            # Leaving the app drops the shell (will_unmount cancels its timer).
            _drop_shell()
            page.views.clear()
            page.views.append(PUBLIC[route](push_route=navigate))
            current["route"] = route
            page.update()
            return

        # Authenticated tool route — enforce the session clock lazily.
        if session_active() and is_session_expired():
            clear_session()
            _go("/login")
            return

        shell = state["shell"]
        if shell is None or not page.views or page.views[-1] is not shell:
            shell = app_shell.AppShell(
                navigate=navigate, tool_factory=make_tool, logout=logout
            )
            state["shell"] = shell
            page.views.clear()
            page.views.append(shell)
            page.update()  # mounts shell; did_mount starts the session timer
        shell.show(route, restore)
        current["route"] = route

    def navigate(route: str):
        """Single navigation entry point for views, the sidebar and shortcuts."""
        guarded("Leaving this screen", lambda: _go(route))

    def back():
        """Esc / back without a growing history stack."""
        route = current["route"]
        if route == "/2fa":
            navigate("/login")
        elif route in TOOL_ROUTES and route != "/home":
            navigate("/home")
        # On /home or /login, back is a no-op.

    def logout():
        def proceed():
            clear_session()
            _go("/login")

        guarded("Logging out", proceed)

    def toggle_theme():
        def proceed():
            new_mode = "light" if theme.palette.mode == "dark" else "dark"
            _set_palette(new_mode)
            prefs.set_theme_pref(new_mode)
            # Rebuild the current screen with the new palette (colors are
            # captured at build time). Tool routes need a fresh shell; the
            # old screen hands over what it holds (e.g. a Decommission scan)
            # so the switch doesn't lose it.
            route = current["route"]
            handed_over = None
            if route in TOOL_ROUTES:
                shell = state["shell"]
                handed_over = shell.detach_tool_state() if shell else None
                _drop_shell()
            _go(route, handed_over)

        guarded("Switching theme", proceed)

    app_shell.set_theme_toggle(toggle_theme)

    # Startup theme: saved preference, else follow the OS brightness.
    startup_mode = prefs.get_theme_pref()
    if startup_mode is None:
        startup_mode = (
            "light" if page.platform_brightness == ft.Brightness.LIGHT else "dark"
        )
    _set_palette(startup_mode)

    async def session_watchdog():
        """App-level timeout enforcement, independent of the active screen."""
        try:
            while True:
                await asyncio.sleep(_SESSION_WATCHDOG_INTERVAL)
                if session_active() and is_session_expired():
                    # clear_session() also cancels any running job.
                    clear_session()
                    if current["route"] not in PUBLIC:
                        _go("/login")
        except asyncio.CancelledError:
            pass

    _go("/login")

    def show_update_banner(latest: str, url: str):
        def dismiss(_):
            page.pop_dialog()

        def open_release(_):
            webbrowser.open(url)
            page.pop_dialog()

        dialog = ft.AlertDialog(
            bgcolor=BG,
            title=ft.Text("Update available", color=WARNING),
            content=ft.Text(
                f"A newer version of vCommander (v{latest}) is available. "
                f"You're running v{APP_VERSION}. "
                f"If running an older version, you may experience bugs or missing features. "
                f"Please update to the latest version via GitHub or Slack.",
                color=WARNING,
            ),
            actions=[
                ft.TextButton("View release", on_click=open_release),
                ft.TextButton("Dismiss", on_click=dismiss),
            ],
        )

        page.show_dialog(dialog)

    async def run_version_check():
        result = await asyncio.to_thread(check_for_update)
        if result is None:
            return
        latest, url = result
        show_update_banner(latest, url)

    def open_command_palette():
        """Build and show the Cmd/Ctrl-K palette (only inside the app)."""
        commands = [
            ("Go to Home", ft.Icons.GRID_VIEW_ROUNDED, lambda: navigate("/home")),
            (
                "Go to Commission",
                ft.Icons.BUSINESS_ROUNDED,
                lambda: navigate("/commission"),
            ),
            (
                "Go to User Management",
                ft.Icons.PEOPLE_ALT_ROUNDED,
                lambda: navigate("/users"),
            ),
            (
                "Go to Decommission",
                ft.Icons.DELETE_SWEEP_ROUNDED,
                lambda: navigate("/decommission"),
            ),
            (
                "Toggle light / dark theme",
                ft.Icons.BRIGHTNESS_6_ROUNDED,
                toggle_theme,
            ),
            ("Log out", ft.Icons.LOGOUT_ROUNDED, logout),
        ]
        CommandPalette(page, commands).open()

    def _in_app() -> bool:
        """True only on an authenticated tool route (not login/2FA)."""
        return current["route"] in TOOL_ROUTES

    def on_key(e: ft.KeyboardEvent):
        """Global shortcuts.

        Esc          → back (no-op on /home and the public screens).
        Cmd/Ctrl-K   → command palette (only inside the app; never on 2FA/login).
        Cmd/Ctrl-,   → log out (only inside the app).

        Per-screen TextField submissions stay handled by `on_submit` on the
        form's last field, so Enter on a focused field still fires the primary
        action without going through this dispatcher.
        """
        ctrl_or_meta = e.ctrl or e.meta
        if e.key == "Escape":
            back()
            return
        if ctrl_or_meta and e.key.upper() == "K":
            if _in_app():
                open_command_palette()
            return
        if ctrl_or_meta and e.key == ",":
            if _in_app():
                logout()
            return

    page.on_keyboard_event = on_key

    spawn(run_version_check())
    spawn(session_watchdog())


if __name__ == "__main__":
    ft.run(main)
