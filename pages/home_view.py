"""Home / tool-picker screen.

Three tool cards (Commission, Users, Decommission) and a session
countdown timer in the header. The timer pops a warning dialog at
SESSION_WARNING_MINUTES and force-logs-out at zero."""

import asyncio

import flet as ft

from constants import (
    APP_VERSION,
    BG,
    BORDER,
    CARD_PADDING,
    CARD_SHADOW,
    ERROR,
    PAGE_PADDING,
    PRIMARY,
    SECONDARY,
    SESSION_WARNING_MINUTES,
    SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from utils.session import (
    clear_session,
    get_session_remaining,
    mark_warning_shown,
    start_session,
    was_warning_shown,
)
from utils.ui_utils import show_alert


class HomeView(ft.View):
    def __init__(self, push_route, pop_route, **kwargs):
        super().__init__(route="/home", bgcolor=BG, padding=PAGE_PADDING, **kwargs)
        self.push_route = push_route
        self.pop_route = pop_route
        self._timer_task: asyncio.Task | None = None
        self._build_ui()

    def _build_ui(self):
        # Idempotent: only the first Home mount after login starts the
        # clock; returning here from a tool neither resets nor extends it.
        start_session()

        self._timer_text = ft.Text("", size=13, color=TEXT_SECONDARY)

        header = ft.Row(
            [
                ft.Text(
                    f"vCommander v{APP_VERSION}",
                    size=24,
                    color=PRIMARY,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Row(
                    [
                        self._timer_text,
                        ft.Container(width=15),
                        ft.OutlinedButton(
                            content=ft.Text("Logout", color=TEXT_SECONDARY),
                            style=ft.ButtonStyle(
                                side=ft.BorderSide(1, BORDER),
                                shape=ft.RoundedRectangleBorder(radius=8),
                            ),
                            on_click=self._on_logout,
                        ),
                    ],
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        cards_row = ft.Row(
            [
                self._build_tool_card(
                    "Commission\nOrganization",
                    ft.Icons.BUSINESS,
                    "Set up sites, claim devices, and configure templates",
                    PRIMARY,
                    "/commission",
                ),
                self._build_tool_card(
                    "User\nManagement",
                    ft.Icons.PEOPLE,
                    "Import and invite guest participants from external orgs",
                    SECONDARY,
                    "/users",
                ),
                self._build_tool_card(
                    "Decommission\nOrganization",
                    ft.Icons.DELETE_SWEEP,
                    "Scan and remove assets with dependency-aware ordering",
                    ERROR,
                    "/decommission",
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=20,
            expand=True,
        )

        self.controls = [
            ft.Column(
                [header, ft.Container(height=10), cards_row],
                expand=True,
            )
        ]

    def _build_tool_card(
        self, title: str, icon, description: str, accent: str, route: str
    ) -> ft.Container:
        card_content = ft.Container(
            bgcolor=SURFACE,
            border_radius=12,
            border=ft.border.all(1, BORDER),
            shadow=CARD_SHADOW,
            padding=ft.padding.all(CARD_PADDING + 10),
            expand=True,
            content=ft.Column(
                [
                    ft.Icon(icon, size=48, color=accent),
                    ft.Container(height=15),
                    ft.Text(
                        title,
                        size=18,
                        color=TEXT_PRIMARY,
                        weight=ft.FontWeight.W_600,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=8),
                    ft.Text(
                        description,
                        size=13,
                        color=TEXT_SECONDARY,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True,
            ),
            on_click=lambda _: self.push_route(route),
            ink=True,
            animate=ft.Animation(200, ft.AnimationCurve.EASE_IN_OUT),
        )

        return ft.Container(
            content=card_content,
            expand=1,
            on_hover=lambda e: self._on_card_hover(e, card_content),
        )

    def _on_card_hover(self, e, card: ft.Container):
        if e.data == "true":
            card.border = ft.border.all(1, PRIMARY)
            card.shadow = ft.BoxShadow(
                spread_radius=1,
                blur_radius=20,
                color=ft.Colors.with_opacity(0.15, PRIMARY),
                offset=ft.Offset(0, 6),
            )
        else:
            card.border = ft.border.all(1, BORDER)
            card.shadow = CARD_SHADOW
        page = getattr(self, "page", None)
        if page:
            page.update()

    # ------------------------------------------------------------------
    # Lifecycle / session timer
    # ------------------------------------------------------------------

    def did_mount(self):
        self._timer_task = asyncio.create_task(self._run_timer())

    def will_unmount(self):
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()

    async def _run_timer(self):
        """
        Tick once a second to update the visible session timer, surface a
        one-shot warning when SESSION_WARNING_MINUTES is reached, and force
        a logout when time runs out.

        Every page-touching call is guarded by an `if not page` bail so the
        timer can't push routes or show alerts after the view has unmounted.
        The `page.update()` call is additionally wrapped because the Flet
        session can be torn down between the `page is None` check and the
        actual call (race during navigation away from Home), surfacing as
        "An attempt to fetch destroyed session" — when that happens the
        new view is already mounted and owns its own timer, so we just
        bail silently.
        """
        try:
            while True:
                # Bail if we've been unmounted between ticks. Cheaper than
                # racing with will_unmount's cancel().
                page = getattr(self, "page", None)
                if page is None:
                    return

                remaining = get_session_remaining()
                if remaining <= 0:
                    clear_session()
                    self.push_route("/login")
                    return

                mins = int(remaining // 60)
                secs = int(remaining % 60)
                self._timer_text.value = f"Session: {mins:02d}:{secs:02d}"

                if (
                    remaining <= SESSION_WARNING_MINUTES * 60
                    and not was_warning_shown()
                ):
                    mark_warning_shown()
                    show_alert(
                        page,
                        "Session Warning",
                        f"Your session expires in {SESSION_WARNING_MINUTES} minutes.",
                    )

                try:
                    page.update()
                except Exception:
                    return
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def _on_logout(self, e):
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        clear_session()
        self.push_route("/login")
