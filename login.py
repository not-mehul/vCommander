import flet as ft

from constants import (
    APP_NAME,
    APP_TAGLINE,
    APP_VERSION,
    BG_COLOR,
    BORDER_RADIUS,
    ELEVATION,
    PADDING,
    PRIMARY_COLOR,
    SECONDARY_COLOR,
    SURFACE_COLOR,
    TEXT_COLOR,
)
from tools.baseline_tools import connect
from utils.db_utils import get_connection_data, save_connection_data
from utils.ui_utils import show_alert


class LoginView(ft.View):
    def __init__(self, page: ft.Page):
        self.app_page = page

        # Primary Inputs
        self.email_input = ft.TextField(
            label="Email",
            prefix_icon=ft.Icons.EMAIL_OUTLINED,
            width=320,
            border_radius=BORDER_RADIUS,
            bgcolor=SURFACE_COLOR,
            color=TEXT_COLOR,
            border_color=PRIMARY_COLOR,
            content_padding=20,
        )
        self.password_input = ft.TextField(
            label="Password",
            prefix_icon=ft.Icons.LOCK_OUTLINED,
            width=320,
            password=True,
            can_reveal_password=True,
            border_radius=BORDER_RADIUS,
            bgcolor=SURFACE_COLOR,
            color=TEXT_COLOR,
            border_color=PRIMARY_COLOR,
            content_padding=20,
        )
        self.org_input = ft.TextField(
            label="Organization Short Name",
            prefix_icon=ft.Icons.BUSINESS_OUTLINED,
            width=320,
            border_radius=BORDER_RADIUS,
            bgcolor=SURFACE_COLOR,
            color=TEXT_COLOR,
            border_color=PRIMARY_COLOR,
            content_padding=20,
        )
        self.remember_checkbox = ft.Checkbox(
            label="Remember settings",
            value=False,
            fill_color=SURFACE_COLOR,
            check_color=PRIMARY_COLOR,
        )

        # Settings Input
        self.api_type_dropdown = ft.Dropdown(
            label="API Type",
            options=[
                ft.dropdown.Option("api"),
                ft.dropdown.Option("api.eu"),
                ft.dropdown.Option("api.au"),
            ],
            value="api",
            width=320,
            border_radius=BORDER_RADIUS,
            bgcolor=SURFACE_COLOR,
            color=TEXT_COLOR,
            border_color=PRIMARY_COLOR,
            content_padding=20,
        )
        self.region_dropdown = ft.Dropdown(
            label="Region",
            options=[
                ft.dropdown.Option("prod1"),
                ft.dropdown.Option("prod2"),
            ],
            value="prod1",
            width=320,
            border_radius=BORDER_RADIUS,
            bgcolor=SURFACE_COLOR,
            color=TEXT_COLOR,
            border_color=PRIMARY_COLOR,
            content_padding=20,
        )
        self.debug_checkbox = ft.Checkbox(
            label="Debugging Mode",
            value=False,
            fill_color=SURFACE_COLOR,
            check_color=PRIMARY_COLOR,
        )

        super().__init__(
            route="/login",
            bgcolor=BG_COLOR,
            padding=PADDING,
            controls=[self.login_ui(page)],
            vertical_alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.load_saved_credentials()

    def login_ui(self, page):
        # Settings Dialog
        self.settings_dialog = ft.AlertDialog(
            title=ft.Text("Advanced Settings", weight=ft.FontWeight.BOLD),
            content=ft.Column(
                [self.api_type_dropdown, self.region_dropdown, self.debug_checkbox],
                tight=True,
                spacing=15,
            ),
            actions=[
                ft.TextButton(
                    "Close", on_click=lambda _: self.close_dialog(self.settings_dialog)
                )
            ],
            shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS),
        )

        login_card = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.ROCKET_LAUNCH, size=50, color=PRIMARY_COLOR),
                        ft.Text(
                            APP_NAME,
                            size=32,
                            weight=ft.FontWeight.BOLD,
                            color=PRIMARY_COLOR,
                        ),
                        ft.Text(APP_TAGLINE, size=14, color=SECONDARY_COLOR),
                        ft.Container(height=20),
                        self.email_input,
                        self.password_input,
                        self.org_input,
                        ft.Row(
                            [self.remember_checkbox],
                            alignment=ft.MainAxisAlignment.START,
                            width=320,
                        ),
                        ft.Container(height=10),
                        ft.ElevatedButton(
                            "Login",
                            icon=ft.Icons.LOGIN,
                            on_click=self.handle_connect,
                            width=350,
                            height=50,
                            style=ft.ButtonStyle(
                                bgcolor=PRIMARY_COLOR,
                                color=SURFACE_COLOR,
                                shape=ft.RoundedRectangleBorder(radius=BORDER_RADIUS),
                            ),
                        ),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=15,
                ),
                padding=PADDING,
            ),
            elevation=ELEVATION,
        )

        return ft.Stack(
            [
                # Main Form
                ft.Container(
                    content=login_card,
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                ),
                # Footer
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text(f"v{APP_VERSION}", color=SECONDARY_COLOR, size=12),
                            ft.IconButton(
                                icon=ft.Icons.SETTINGS,
                                icon_color=SECONDARY_COLOR,
                                tooltip="Advanced Settings",
                                on_click=lambda _: self.open_dialog(
                                    self.settings_dialog
                                ),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    bottom=20,
                    left=20,
                    right=20,
                ),
            ],
            expand=True,
        )

    def load_saved_credentials(self):
        saved_credentials = get_connection_data()
        if saved_credentials:
            self.email_input.value = saved_credentials[0]
            self.password_input.value = saved_credentials[1]
            self.api_type_dropdown.value = saved_credentials[2] or "api"
            self.region_dropdown.value = saved_credentials[3] or "prod1"
            self.remember_cb = True

    def open_dialog(self, dialog):
        if dialog not in self.app_page.overlay:
            self.app_page.overlay.append(dialog)
        dialog.open = True
        self.app_page.update()

    def close_dialog(self, dialog):
        dialog.open = False
        self.app_page.update()

    # TODO - Handle Connection
    def handle_connect(self, e):
        if not all(
            [self.email_input.value, self.password_input.value, self.org_input.value]
        ):
            print("DEBUG: Validation failed.")
            show_alert(
                self.app_page, "Please fill in all primary fields.", is_error=True
            )
            return

        if self.remember_checkbox.value:
            save_connection_data(
                email=self.email_input.value,
                password=self.password_input.value,
                api_type=self.api_type_dropdown.value,
                region=self.region_dropdown.value,
            )

        connect(
            str(self.email_input.value),
            str(self.password_input.value),
            str(self.org_input.value),
        )
        self.app_page.go("/home")
