import flet as ft

from constants import APP_NAME, WINDOW_HEIGHT, WINDOW_WIDTH
from pages.home import HomeView
from pages.login import LoginView
from utils.db_utils import initialize_db


def main(page: ft.Page):
    page.title = APP_NAME
    page.fonts = {
        "Poppins": "https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-Regular.ttf",
    }
    page.theme_mode = ft.ThemeMode.SYSTEM
    page.window.width = WINDOW_WIDTH
    page.window.height = WINDOW_HEIGHT

    initialize_db()

    ROUTES = {
        "/login": LoginView,
        "/home": HomeView,
    }

    def _route_change(e):
        page.views.clear()

        route = page.route
        if route in ROUTES:
            page.views.append(ROUTES[route](page))
        else:
            page.views.append(ROUTES["/login"](page))
        page.update()

    def _view_pop(view):
        if len(page.views) > 1:
            page.views.pop()
            top_view = page.views[-1]
            page.go(top_view.route)

    page.on_route_change = _route_change
    page.on_view_pop = _view_pop

    page.go("/login")


if __name__ == "__main__":
    ft.app(target=main)
