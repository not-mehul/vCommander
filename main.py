import flet as ft
from constants import APP_VERSION, BG, MIN_WIDTH, MIN_HEIGHT
from utils.logger import get_log_path, log_api_call
from pages.login_view import LoginView
from pages.two_factor_view import TwoFactorView
from pages.home_view import HomeView
from pages.commission_view import CommissionView
from pages.users_view import UsersView
from pages.decommission_view import DecommissionView


ROUTE_MAP = {
    "/login": LoginView,
    "/2fa": TwoFactorView,
    "/home": HomeView,
    "/commission": CommissionView,
    "/users": UsersView,
    "/decommission": DecommissionView,
}


async def main(page: ft.Page):
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
        history.append(route)
        page.views.clear()
        view_class = ROUTE_MAP[route]
        view = view_class(push_route=push_route, pop_route=pop_route)
        page.views.append(view)
        page.update()

    def pop_route():
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
