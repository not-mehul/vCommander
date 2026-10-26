"""Login screen.

Collects email, password, org short name, API region, and shard, then
constructs a VerkadaInternalAPIClient for that region and authenticates. On
success it stashes the client in `utils.session` and routes to /home;
on MFARequiredError it routes to /2fa. Saved credentials are loaded
from the local SQLite store on mount.

Validation is inline: empty/invalid required fields show a field-level
error, and an auth failure surfaces an inline error banner rather than a
blocking modal.
"""

import asyncio

import flet as ft

import theme
from apis.internal_api import MFARequiredError, VerkadaInternalAPIClient
from components import dropdown, primary_button, set_button_loading, text_field
from constants import API_REGION_LABELS, API_REGIONS, APP_VERSION, FIELD_SPACING
from utils.db import load_credentials, save_credentials
from utils.executor import _executor
from utils.session import set_internal_client


def _strip(value: str | None) -> str:
    """Coerce a possibly-None TextField value to a stripped string."""
    return (value or "").strip()


class LoginView(ft.View):
    def __init__(self, push_route, **kwargs):
        super().__init__(route="/login", bgcolor=theme.BG, padding=0, **kwargs)
        self.push_route = push_route
        self._build_ui()

    def _build_ui(self):
        creds = load_credentials() or {}

        self.email_field = text_field(
            "Email", value=creds.get("email", ""), on_change=self._clear_error
        )
        self.password_field = text_field(
            "Password",
            value=creds.get("password", ""),
            password=True,
            can_reveal_password=True,
            on_change=self._clear_error,
            on_submit=self._on_login,
        )
        self.org_field = text_field(
            "Org Short Name",
            value=creds.get("org_short_name", ""),
            on_change=self._clear_error,
            on_submit=self._on_login,
        )
        self.region_dropdown = dropdown(
            "API Region",
            [ft.dropdown.Option(key=r, text=API_REGION_LABELS[r]) for r in API_REGIONS],
            value=creds.get("api_region") or "api",
        )
        self.shard_dropdown = dropdown(
            "Shard",
            [ft.dropdown.Option("prod1"), ft.dropdown.Option("prod2")],
            value=creds.get("shard", "prod1"),
        )

        self.login_btn = primary_button("Login", on_click=self._on_login, height=45)

        # Inline auth-error banner (hidden until a login attempt fails).
        self._error_text = ft.Text("", color=theme.DANGER, size=theme.FONT_CAPTION)
        self._error_banner = ft.Container(
            visible=False,
            bgcolor=theme.palette.tint(theme.DANGER, 0.12),
            border=ft.Border.all(1, theme.palette.tint(theme.DANGER, 0.4)),
            border_radius=theme.RADIUS_MD,
            padding=ft.Padding.symmetric(
                horizontal=theme.SPACE_LG, vertical=theme.SPACE_MD
            ),
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ERROR_OUTLINE, color=theme.DANGER, size=18),
                    self._error_text,
                ],
                spacing=theme.SPACE_MD,
            ),
        )

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
                                    ft.Container(
                                        content=self.region_dropdown, expand=1
                                    ),
                                    ft.Container(
                                        content=self.shard_dropdown, expand=1
                                    ),
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
            bgcolor=theme.SURFACE,
            border_radius=theme.RADIUS_LG,
            border=ft.Border.all(1, theme.BORDER),
            shadow=theme.elevation(1),
            padding=ft.Padding.all(theme.SPACE_2XL),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(
                                "vCommander",
                                size=theme.FONT_DISPLAY,
                                color=theme.ACCENT,
                                weight=theme.WEIGHT_BOLD,
                            ),
                            ft.Text(
                                f"v{APP_VERSION}",
                                size=theme.FONT_CAPTION,
                                color=theme.TEXT_MUTED,
                            ),
                        ],
                        spacing=theme.SPACE_SM,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                    ),
                    ft.Text(
                        "Sign in with your Verkada Command org admin account.",
                        size=theme.FONT_BODY,
                        color=theme.TEXT_SECONDARY,
                    ),
                    ft.Container(height=FIELD_SPACING),
                    self._error_banner,
                    form_grid,
                    ft.Container(height=FIELD_SPACING + 5),
                    self.login_btn,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                tight=True,
            ),
        )

        self.controls = [
            ft.Container(
                content=card,
                alignment=ft.Alignment.CENTER,
                expand=True,
            )
        ]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _clear_error(self, e=None):
        """Clear field-level + banner errors as the user edits."""
        changed = False
        for field in (self.email_field, self.password_field, self.org_field):
            if field.error:
                field.error = None
                changed = True
        if self._error_banner.visible:
            self._error_banner.visible = False
            changed = True
        if changed:
            page = getattr(self, "page", None)
            if page:
                page.update()

    def _validate(self) -> bool:
        """Set inline field errors; return True when the form is valid."""
        ok = True
        email = _strip(self.email_field.value)
        if not email:
            self.email_field.error = "Email is required"
            ok = False
        elif "@" not in email or "." not in email:
            self.email_field.error = "Enter a valid email"
            ok = False
        # Passwords are used verbatim (never stripped), so only an empty
        # field is rejected — leading/trailing spaces may be intentional.
        if not self.password_field.value:
            self.password_field.error = "Password is required"
            ok = False
        if not _strip(self.org_field.value):
            self.org_field.error = "Org short name is required"
            ok = False
        return ok

    def _show_error(self, page, message: str):
        self._error_text.value = message
        self._error_banner.visible = True
        page.update()

    async def _on_login(self, e):
        self._clear_error()
        if not self._validate():
            e.page.update()
            return

        email = _strip(self.email_field.value)
        password = self.password_field.value or ""
        org = _strip(self.org_field.value)
        region = self.region_dropdown.value or "api"
        shard = self.shard_dropdown.value or "prod1"

        set_button_loading(self.login_btn, True, "Logging in")
        await asyncio.sleep(0)

        # Construct the client outside the try/except so it remains available
        # to the MFARequiredError handler. Login itself is what may raise.
        client = VerkadaInternalAPIClient(email, password, org, shard, region)
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
            self._show_error(e.page, str(ex))
