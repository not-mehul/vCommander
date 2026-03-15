import flet as ft

from constants import BG_COLOR, PADDING, TEXT_COLOR, BORDER_RADIUS, SURFACE_COLOR


class HomeView(ft.View):
    def __init__(self, page: ft.Page):
        super().__init__(
            route="/home",
            bgcolor=BG_COLOR,
            padding=PADDING,
            controls=[self.home_ui(page)],
        )

    def home_ui(self, page):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text("vCommander Dashboard", size=24, weight="bold", color=TEXT_COLOR),
                            ft.IconButton(
                                icon=ft.Icons.LOGOUT_ROUNDED,
                                on_click=lambda _: page.go("/login"),
                                tooltip="Logout",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=40, color=ft.Colors.TRANSPARENT),
                    ft.Text("Welcome back, Explorer.", size=18, color=ft.Colors.BLUE_GREY_600),
                    ft.Container(
                        content=ft.Text("Feature Content Goes Here", color=TEXT_COLOR),
                        bgcolor=SURFACE_COLOR,
                        padding=40,
                        border_radius=BORDER_RADIUS,
                        expand=True,
                    ),
                ],
                expand=True,
            ),
            expand=True,
        )
