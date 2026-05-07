"""vCommander entry point.

Configures the Flet `Page`, defines a tiny `push/pop` route stack
(Flet's built-in router was overkill for the half-dozen screens here),
and mounts the LoginView. Each view receives `push_route` and
`pop_route` callbacks so it can navigate without importing the others.
"""

import flet as ft

from constants import APP_VERSION, BG, MIN_HEIGHT, MIN_WIDTH
from pages.commission_view import CommissionView
from pages.decommission_view import DecommissionView
from pages.home_view import HomeView
from pages.login_view import LoginView
from pages.two_factor_view import TwoFactorView
from pages.users_view import UsersView
from utils.logger import get_log_path, log_api_call

# Maps a route string to the View class that renders it. Adding a new
# screen is a matter of writing a `View` subclass and adding one entry.
ROUTE_MAP = {
    "/login": LoginView,
    "/2fa": TwoFactorView,
    "/home": HomeView,
    "/commission": CommissionView,
    "/users": UsersView,
    "/decommission": DecommissionView,
}


async def main(page: ft.Page):
    """Flet app entry point. Sets window chrome and pushes the login screen."""
    log_api_call("APP", "startup", "{}", "200", f"vCommander v{APP_VERSION}")
    print(f"Logs → {get_log_path()}")

    page.title = f"vCommander v{APP_VERSION}"
    page.bgcolor = BG
    page.theme_mode = ft.ThemeMode.DARK
    page.window.min_width = MIN_WIDTH
    page.window.min_height = MIN_HEIGHT
    page.window.width = MIN_WIDTH
    page.window.height = MIN_HEIGHT
    page.padding = 0

    history: list[str] = []

    def push_route(route: str):
        """Navigate forward by replacing the current view with `route`."""
        history.append(route)
        page.views.clear()
        view_class = ROUTE_MAP[route]
        view = view_class(push_route=push_route, pop_route=pop_route)
        page.views.append(view)
        page.update()

    def pop_route():
        """Navigate back to the previous view; no-op at the bottom of the stack."""
        if len(history) > 1:
            history.pop()
            route = history[-1]
            page.views.clear()
            view_class = ROUTE_MAP[route]
            view = view_class(push_route=push_route, pop_route=pop_route)
            page.views.append(view)
            page.update()

    push_route("/login")


ft.app(target=main)
