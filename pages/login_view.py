"""Login screen.

Collects email, password, org short name, region, and (optional) shard,
then constructs a VerkadaInternalAPIClient and authenticates. On
success it stashes the client in `utils.session` and routes to /home;
on MFARequiredError it routes to /2fa. Saved credentials are loaded
from the local SQLite store on mount."""

import asyncio

import flet as ft

from apis.internal_api import MFARequiredError, VerkadaInternalAPIClient
from constants import (
    APP_VERSION,
    BG,
    BORDER,
    CARD_PADDING,
    CARD_SHADOW,
    FIELD_SPACING,
    PRIMARY,
    SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from utils.db import load_credentials, save_credentials
from utils.executor import _executor
from utils.session import set_internal_client
from utils.ui_utils import set_button_loading, show_alert, show_toast


def _strip(value: str | None) -> str:
    """Coerce a possibly-None TextField value to a stripped string."""
    return (value or "").strip()


def _make_text_field(
    label: str,
    *,
    value: str = "",
    password: bool = False,
    can_reveal_password: bool = False,
    on_submit=None,
) -> ft.TextField:
    """Build a styled TextField matching the rest of the app."""
    return ft.TextField(
        label=label,
        value=value,
        password=password,
        can_reveal_password=can_reveal_password,
        on_submit=on_submit,
        border_color=BORDER,
        focused_border_color=PRIMARY,
        color=TEXT_PRIMARY,
        label_style=ft.TextStyle(color=TEXT_SECONDARY),
    )


def _make_dropdown(
    label: str,
    options: list[ft.dropdown.Option],
    *,
    value: str = "",
) -> ft.Dropdown:
    """Build a styled Dropdown matching the rest of the app."""
    return ft.Dropdown(
        label=label,
        options=options,
        value=value,
        border_color=BORDER,
        focused_border_color=PRIMARY,
        color=TEXT_PRIMARY,
        label_style=ft.TextStyle(color=TEXT_SECONDARY),
    )


class LoginView(ft.View):
    def __init__(self, push_route, pop_route, **kwargs):
        super().__init__(route="/login", bgcolor=BG, padding=0, **kwargs)
        self.push_route = push_route
        self.pop_route = pop_route
        self._build_ui()

    def _build_ui(self):
        creds = load_credentials() or {}

        self.email_field = _make_text_field("Email", value=creds.get("email", ""))
        self.password_field = _make_text_field(
            "Password",
            value=creds.get("password", ""),
            password=True,
            can_reveal_password=True,
            on_submit=self._on_login,
        )
        self.org_field = _make_text_field(
            "Org Short Name",
            value=creds.get("org_short_name", ""),
            on_submit=self._on_login,
        )
        self.region_dropdown = _make_dropdown(
            "API Region",
            [ft.dropdown.Option(r) for r in ("api", "api.eu", "api.au")],
            value=creds.get("api_region", "api"),
        )
        self.shard_dropdown = _make_dropdown(
            "Shard",
            [ft.dropdown.Option("prod1"), ft.dropdown.Option("prod2")],
            value=creds.get("shard", "prod1"),
        )

        self.login_btn = ft.ElevatedButton(
            content=ft.Text("Login", color=TEXT_PRIMARY, weight=ft.FontWeight.W_600),
            bgcolor=PRIMARY,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            height=45,
            on_click=self._on_login,
        )

        # Two-column form: email | password on the first row, then
        # org-short-name on the left of the second row with region+shard
        # on the right. Fills the available width better than the prior
        # single-column 450-wide card on a 1100-wide window.
        row_spacing = FIELD_SPACING
        form_grid = ft.Column(
            [
                ft.Row(
                    [
                        ft.Container(content=self.email_field, expand=1),
                        ft.Container(content=self.password_field, expand=1),
                    ],
                    spacing=row_spacing,
                ),
                ft.Row(
                    [
                        ft.Container(content=self.org_field, expand=1),
                        ft.Container(
                            content=ft.Row(
                                [
                                    ft.Container(content=self.region_dropdown, expand=1),
                                    ft.Container(content=self.shard_dropdown, expand=1),
                                ],
                                spacing=row_spacing,
                            ),
                            expand=1,
                        ),
                    ],
                    spacing=row_spacing,
                ),
            ],
            spacing=row_spacing,
        )

        card = ft.Container(
            width=720,
            bgcolor=SURFACE,
            border_radius=12,
            border=ft.border.all(1, BORDER),
            shadow=CARD_SHADOW,
            padding=ft.padding.all(CARD_PADDING + 10),
            content=ft.Column(
                [
                    ft.Text(
                        "vCommander", size=28, color=PRIMARY, weight=ft.FontWeight.BOLD
                    ),
                    ft.Text(f"v{APP_VERSION}", size=12, color=TEXT_SECONDARY),
                    ft.Container(height=FIELD_SPACING),
                    form_grid,
                    ft.Container(height=FIELD_SPACING + 5),
                    self.login_btn,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                scroll=ft.ScrollMode.ADAPTIVE,
            ),
        )

        self.controls = [
            ft.Container(
                content=card,
                alignment=ft.Alignment.CENTER,
                expand=True,
            )
        ]

    async def _on_login(self, e):
        email = _strip(self.email_field.value)
        password = _strip(self.password_field.value)
        org = _strip(self.org_field.value)
        region = self.region_dropdown.value or "api"
        shard = self.shard_dropdown.value or "prod1"

        if not email or not password or not org:
            show_toast(
                e.page,
                "Please fill in email, password, and org short name.",
                kind="warning",
            )
            return

        set_button_loading(self.login_btn, True, "Logging in")
        await asyncio.sleep(0)

        # Construct the client outside the try/except so it remains available
        # to the MFARequiredError handler. Login itself is what may raise.
        client = VerkadaInternalAPIClient(email, password, org, shard)
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(_executor, client.login)
            save_credentials(email, password, org, region, shard)
            set_internal_client(client)
            self.push_route("/home")
        except MFARequiredError:
            # Reuse the same client instance — it holds partial auth state
            # from login that verify_mfa() needs to complete the flow.
            set_internal_client(client)
            save_credentials(email, password, org, region, shard)
            self.push_route("/2fa")
        except Exception as ex:
            set_button_loading(self.login_btn, False, "Login")
            show_alert(e.page, "Login Failed", str(ex))
