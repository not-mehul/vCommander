"""Two-factor verification screen.

Shown after the login screen raises MFARequiredError. The user enters
the SMS/authenticator code and we re-call `login_with_mfa`; on success
we set the internal client in session state and route to /home."""

import asyncio

import flet as ft

from constants import (
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
from utils.executor import _executor
from utils.session import get_internal_client
from utils.ui_utils import set_button_loading, show_alert


def _strip(value: str | None) -> str:
    """Coerce a possibly-None TextField value to a stripped string."""
    return (value or "").strip()


class TwoFactorView(ft.View):
    def __init__(self, push_route, pop_route, **kwargs):
        super().__init__(route="/2fa", bgcolor=BG, padding=0, **kwargs)
        self.push_route = push_route
        self.pop_route = pop_route
        self._build_ui()

    def _build_ui(self):
        self.code_field = ft.TextField(
            label="Verification Code",
            border_color=BORDER,
            focused_border_color=PRIMARY,
            color=TEXT_PRIMARY,
            label_style=ft.TextStyle(color=TEXT_SECONDARY),
            text_align=ft.TextAlign.CENTER,
            keyboard_type=ft.KeyboardType.NUMBER,
            max_length=6,
            input_filter=ft.NumbersOnlyInputFilter(),
            on_submit=self._on_verify,
            autofocus=True,
        )

        self.verify_btn = ft.ElevatedButton(
            content=ft.Text("Verify", color=TEXT_PRIMARY, weight=ft.FontWeight.W_600),
            bgcolor=PRIMARY,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            height=45,
            on_click=self._on_verify,
        )

        card = ft.Container(
            width=400,
            bgcolor=SURFACE,
            border_radius=12,
            border=ft.border.all(1, BORDER),
            shadow=CARD_SHADOW,
            padding=ft.padding.all(CARD_PADDING + 10),
            content=ft.Column(
                [
                    ft.Text(
                        "Two-Factor Authentication",
                        size=22,
                        color=PRIMARY,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Text(
                        "Enter the code from your authenticator app",
                        size=13,
                        color=TEXT_SECONDARY,
                    ),
                    ft.Container(height=FIELD_SPACING + 5),
                    self.code_field,
                    ft.Container(height=FIELD_SPACING + 5),
                    ft.Container(content=self.verify_btn, expand=False),
                    ft.Container(height=10),
                    ft.TextButton(
                        content=ft.Text("Back to Login", color=TEXT_SECONDARY, size=13),
                        on_click=lambda _: self.push_route("/login"),
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        )

        self.controls = [
            ft.Container(
                content=card,
                alignment=ft.Alignment.CENTER,
                expand=True,
            )
        ]

    async def _on_verify(self, e):
        code = _strip(self.code_field.value)
        if not code.isdigit() or len(code) != 6:
            show_alert(
                e.page,
                "Validation Error",
                "Verification code must be exactly 6 digits.",
            )
            return

        set_button_loading(self.verify_btn, True, "Verifying")
        await asyncio.sleep(0)

        try:
            client = get_internal_client()
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(_executor, client.verify_mfa, code)
            self.push_route("/home")
        except Exception as ex:
            set_button_loading(self.verify_btn, False, "Verify")
            show_alert(e.page, "Verification Failed", str(ex))
