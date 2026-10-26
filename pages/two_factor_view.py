"""Two-factor verification screen.

Shown after the login screen raises MFARequiredError. The user enters
the SMS/authenticator code and we re-call `login_with_mfa`; on success
we set the internal client in session state and route to /home."""

import asyncio

import flet as ft

from components import primary_button, set_button_loading
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
from utils.ui_utils import show_alert, show_toast


def _strip(value: str | None) -> str:
    """Coerce a possibly-None TextField value to a stripped string."""
    return (value or "").strip()


class TwoFactorView(ft.View):
    def __init__(self, push_route, **kwargs):
        super().__init__(route="/2fa", bgcolor=BG, padding=0, **kwargs)
        self.push_route = push_route
        self._build_ui()

    def _mfa_prompt(self) -> tuple[str, bool]:
        """Return (subtitle, sms_enabled) describing the active 2FA factor.

        Reads the flags login() stashed on the client. Falls back to the
        authenticator-app wording if the client isn't reachable (e.g. a
        hard refresh landed straight on /2fa)."""
        try:
            client = get_internal_client()
        except Exception:
            return "Enter the code from your authenticator app", False

        sms_enabled = getattr(client, "mfa_sms_enabled", False)
        contact = getattr(client, "mfa_sms_contact", None)
        if sms_enabled and contact:
            return f"Enter the code we texted to your phone ending in {contact}", True
        if sms_enabled:
            return "Enter the code sent to your phone via SMS", True
        return "Enter the code from your authenticator app", False

    def _build_ui(self):
        subtitle, sms_enabled = self._mfa_prompt()

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

        self.verify_btn = primary_button("Verify", on_click=self._on_verify, height=45)

        # Resend is only meaningful for SMS — an authenticator app generates
        # its own rolling code, so there's nothing for us to re-dispatch.
        self.resend_btn = (
            ft.TextButton(
                content=ft.Text("Resend code", color=TEXT_SECONDARY, size=13),
                on_click=self._on_resend,
            )
            if sms_enabled
            else None
        )

        column_controls = [
            ft.Text(
                "Two-Factor Authentication",
                size=22,
                color=PRIMARY,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text(subtitle, size=13, color=TEXT_SECONDARY),
            ft.Container(height=FIELD_SPACING + 5),
            self.code_field,
            ft.Container(height=FIELD_SPACING + 5),
            ft.Container(content=self.verify_btn, expand=False),
        ]
        if self.resend_btn is not None:
            column_controls.append(self.resend_btn)
        column_controls.extend(
            [
                ft.Container(height=10),
                ft.TextButton(
                    content=ft.Text("Back to Login", color=TEXT_SECONDARY, size=13),
                    on_click=lambda _: self.push_route("/login"),
                ),
            ]
        )

        card = ft.Container(
            width=400,
            bgcolor=SURFACE,
            border_radius=12,
            border=ft.Border.all(1, BORDER),
            shadow=CARD_SHADOW,
            padding=ft.Padding.all(CARD_PADDING + 10),
            content=ft.Column(
                column_controls,
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

    async def _on_verify(self, e):
        code = _strip(self.code_field.value)
        if not code.isdigit() or len(code) != 6:
            show_toast(
                e.page,
                "Verification code must be exactly 6 digits.",
                kind="warning",
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

    async def _on_resend(self, e):
        """Re-dispatch the SMS code via auth/twofactor/sms/new."""
        if self.resend_btn is None:
            return
        self.resend_btn.disabled = True
        e.page.update()
        try:
            client = get_internal_client()
            loop = asyncio.get_running_loop()
            contact = await loop.run_in_executor(_executor, client.resend_mfa_sms)
            message = (
                f"Code resent to your phone ending in {contact}"
                if contact
                else "Code resent."
            )
            show_toast(e.page, message, kind="success")
        except Exception as ex:
            show_alert(e.page, "Couldn't Resend Code", str(ex))
        finally:
            self.resend_btn.disabled = False
            e.page.update()
