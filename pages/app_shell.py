"""Persistent application shell.

`AppShell` is a single `ft.View` mounted once for the authenticated session.
It owns the fixed left sidebar (wordmark, tool nav, org/session chips, logout),
the content header (title + theme toggle), the pre-expiry session banner, and
the live session countdown. Navigating between tools calls `show(route)`, which
swaps only the content host — the sidebar stays put and there's no page-stack
transition.

Tool screens are lightweight `ToolView`s: they build a body control and expose
`title`/`subtitle`/`body`; the shell hosts that body and calls the tool's
`on_leave()` when it is swapped out or the shell is torn down. The public
screens (login, 2FA) remain standalone `ft.View`s with no shell.
"""

from __future__ import annotations

import asyncio
import contextlib

import flet as ft

import theme
from components.buttons import secondary_button
from constants import APP_VERSION, SESSION_WARNING_MINUTES
from utils.db import load_credentials
from utils.session import (
    can_extend,
    clear_session,
    extend_session,
    get_internal_client,
    get_session_remaining,
    start_session,
)

# Sidebar navigation model: (route, label, icon, brand tint token). The brand
# color is used only as a small icon tint — never as a dominant surface color.
# Tints are theme token names, resolved when the item is drawn so a light/dark
# switch picks up the new palette.
NAV_ITEMS = [
    ("/home", "Home", ft.Icons.GRID_VIEW_ROUNDED, "ACCENT"),
    ("/commission", "Commission", ft.Icons.BUSINESS_ROUNDED, "BRAND_COMMISSION"),
    ("/users", "Users", ft.Icons.PEOPLE_ALT_ROUNDED, "BRAND_USERS"),
    (
        "/decommission",
        "Decommission",
        ft.Icons.DELETE_SWEEP_ROUNDED,
        "BRAND_DECOMMISSION",
    ),
]

_SIDEBAR_WIDTH = 232

# Set by main.py: a zero-arg callable that flips light/dark and rebuilds the
# view tree. Kept as a module hook so the shell can trigger a theme switch
# without importing main (which would be circular).
_THEME_TOGGLE = None


def set_theme_toggle(fn) -> None:
    global _THEME_TOGGLE
    _THEME_TOGGLE = fn


class ToolView:
    """Base for the authenticated tool screens.

    A tool builds its body control and calls `mount(body)`. It is NOT an
    `ft.Control`; the shell hosts `self.body` and sets `self.page` so the
    tool's `getattr(self, "page", ...)` update guards keep working.

    `push_route(route)` navigates (through main's run guard). Override
    `on_leave()` to release anything the tool holds when it is swapped out.
    """

    def __init__(
        self,
        push_route,
        *,
        route: str,
        title: str,
        subtitle: str | None = None,
    ):
        self.push_route = push_route
        self.route = route
        self.title = title
        self.subtitle = subtitle
        self.page = None
        self.body: ft.Control | None = None

    def mount(self, body: ft.Control):
        self.body = body

    def on_leave(self) -> None:
        """Called once when the shell stops hosting this tool."""

    def detach_state(self):
        """Hand over what this screen holds before it is rebuilt (e.g. for
        a theme switch), or None. After a hand-over, on_leave must not
        release it: the rebuilt screen owns it via restore_state()."""
        return None

    def restore_state(self, state) -> None:
        """Take over what detach_state() handed over from the old screen."""


class AppShell(ft.View):
    def __init__(self, *, navigate, tool_factory, logout):
        super().__init__(route="/app", bgcolor=theme.BG, padding=0)
        # navigate(route): nav clicks and session expiry route through this.
        # logout(): the guarded logout from main. tool_factory(route) ->
        # ToolView builds the screen to host.
        self._navigate = navigate
        self._logout = logout
        self._tool_factory = tool_factory
        self._tool: ToolView | None = None
        self._active_route: str | None = None
        self._timer_task: asyncio.Task | None = None

        self._session_text = ft.Text(
            "", size=theme.FONT_CAPTION, color=theme.TEXT_SECONDARY
        )
        self._title_text = ft.Text(
            "", size=theme.FONT_TITLE, color=theme.TEXT_PRIMARY,
            weight=theme.WEIGHT_SEMIBOLD,
        )
        self._subtitle_text = ft.Text(
            "", size=theme.FONT_CAPTION, color=theme.TEXT_SECONDARY, visible=False
        )
        self._content_host = ft.Container(expand=True)
        self._nav_column = ft.Column(spacing=theme.SPACE_XS)

        self._build_session_banner()
        self.controls = [
            ft.Row(
                [self._build_sidebar(), self._build_content()],
                spacing=0,
                expand=True,
            )
        ]
        self._render_nav()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def show(self, route: str, restore=None):
        """Swap the content area to `route`'s tool (sidebar stays constant).

        `restore` is what the previous instance of this tool handed over
        (detach_tool_state) when the screen is rebuilt, e.g. for a theme
        switch."""
        self.leave()
        tool = self._tool_factory(route)
        self._tool = tool
        tool.page = self._get_page()
        if restore is not None:
            tool.restore_state(restore)
        self._title_text.value = tool.title
        self._subtitle_text.value = tool.subtitle or ""
        self._subtitle_text.visible = bool(tool.subtitle)
        self._content_host.content = tool.body
        self._active_route = route
        self._render_nav()
        self._safe_update()

    def detach_tool_state(self):
        """What the hosted tool hands over before a rebuild, or None."""
        return self._tool.detach_state() if self._tool is not None else None

    def leave(self):
        """Tell the hosted tool it is going away (idempotent)."""
        tool, self._tool = self._tool, None
        if tool is not None:
            tool.on_leave()

    # ------------------------------------------------------------------
    # Content area
    # ------------------------------------------------------------------
    def _build_content(self) -> ft.Control:
        header_row = ft.Row(
            [
                ft.Column(
                    [self._title_text, self._subtitle_text], spacing=theme.SPACE_XS
                ),
                self._build_theme_toggle(),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
        return ft.Container(
            expand=True,
            padding=ft.Padding.all(theme.SPACE_2XL),
            content=ft.Column(
                [
                    self._session_banner,
                    header_row,
                    ft.Container(height=theme.SPACE_XL),
                    self._content_host,
                ],
                expand=True,
            ),
        )

    def _build_session_banner(self):
        self._session_banner_text = ft.Text(
            "", size=theme.FONT_CAPTION, color=theme.TEXT_PRIMARY, expand=True
        )
        self._extend_btn = ft.TextButton(
            content=ft.Text(
                "Extend session", color=theme.ACCENT, weight=theme.WEIGHT_MEDIUM
            ),
            on_click=self._on_extend,
        )
        self._session_banner = ft.Container(
            visible=False,
            bgcolor=theme.palette.tint(theme.WARNING, 0.12),
            border=ft.Border.all(1, theme.palette.tint(theme.WARNING, 0.4)),
            border_radius=theme.RADIUS_MD,
            margin=ft.Margin.only(bottom=theme.SPACE_LG),
            padding=ft.Padding.symmetric(
                horizontal=theme.SPACE_LG, vertical=theme.SPACE_SM
            ),
            content=ft.Row(
                [
                    ft.Icon(
                        ft.Icons.WARNING_AMBER_ROUNDED, color=theme.WARNING, size=18
                    ),
                    self._session_banner_text,
                    self._extend_btn,
                ],
                spacing=theme.SPACE_MD,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------
    def _build_sidebar(self) -> ft.Control:
        wordmark = ft.Column(
            [
                ft.Text(
                    "vCommander",
                    size=theme.FONT_TITLE,
                    color=theme.ACCENT,
                    weight=theme.WEIGHT_BOLD,
                ),
                ft.Text(
                    f"v{APP_VERSION}", size=theme.FONT_CAPTION, color=theme.TEXT_MUTED
                ),
            ],
            spacing=2,
        )

        footer = ft.Column(
            [
                ft.Divider(height=1, color=theme.BORDER_SUBTLE),
                ft.Container(height=theme.SPACE_SM),
                self._chip(ft.Icons.CORPORATE_FARE_ROUNDED, self._org_name()),
                self._chip(ft.Icons.PUBLIC_ROUNDED, self._shard_label()),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.SCHEDULE_ROUNDED,
                                size=14,
                                color=theme.TEXT_MUTED,
                            ),
                            self._session_text,
                        ],
                        spacing=theme.SPACE_SM,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(
                        horizontal=theme.SPACE_MD, vertical=theme.SPACE_XS
                    ),
                ),
                ft.Container(height=theme.SPACE_SM),
                secondary_button(
                    "Logout",
                    on_click=self._on_logout,
                    icon=ft.Icons.LOGOUT_ROUNDED,
                    height=40,
                ),
            ],
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        return ft.Container(
            width=_SIDEBAR_WIDTH,
            bgcolor=theme.SURFACE,
            border=ft.Border.only(right=ft.BorderSide(1, theme.BORDER_SUBTLE)),
            padding=ft.Padding.symmetric(
                horizontal=theme.SPACE_MD, vertical=theme.SPACE_XL
            ),
            content=ft.Column(
                [
                    ft.Container(
                        content=wordmark,
                        padding=ft.Padding.symmetric(horizontal=theme.SPACE_MD),
                    ),
                    ft.Container(height=theme.SPACE_2XL),
                    self._nav_column,
                    ft.Container(expand=True),
                    footer,
                ],
                expand=True,
            ),
        )

    def _render_nav(self):
        """(Re)build the nav items to reflect the active route."""
        self._nav_column.controls = [self._nav_item(*item) for item in NAV_ITEMS]

    def _nav_item(self, route, label, icon, brand) -> ft.Control:
        active = route == self._active_route
        item = ft.Container(
            border_radius=theme.RADIUS_MD,
            bgcolor=theme.palette.tint(theme.ACCENT, 0.13) if active else None,
            padding=ft.Padding.symmetric(
                horizontal=theme.SPACE_MD, vertical=theme.SPACE_MD
            ),
            content=ft.Row(
                [
                    ft.Icon(icon, size=20, color=getattr(theme, brand)),
                    ft.Text(
                        label,
                        size=16,
                        color=theme.TEXT_PRIMARY if active else theme.TEXT_SECONDARY,
                        weight=theme.WEIGHT_SEMIBOLD
                        if active
                        else theme.WEIGHT_MEDIUM,
                    ),
                ],
                spacing=theme.SPACE_MD,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=None if active else (lambda _, r=route: self._navigate(r)),
            ink=not active,
            animate=ft.Animation(120, ft.AnimationCurve.EASE_IN_OUT),
        )
        if not active:
            item.on_hover = lambda e, c=item: self._hover_nav(e, c)
        return item

    def _hover_nav(self, e, container: ft.Container):
        container.bgcolor = (
            theme.palette.tint(theme.TEXT_PRIMARY, 0.06)
            if e.data == "true"
            else None
        )
        self._safe_update()

    def _chip(self, icon, text: str) -> ft.Control:
        return ft.Container(
            padding=ft.Padding.symmetric(
                horizontal=theme.SPACE_MD, vertical=theme.SPACE_XS
            ),
            content=ft.Row(
                [
                    ft.Icon(icon, size=14, color=theme.TEXT_MUTED),
                    ft.Text(
                        text,
                        size=theme.FONT_CAPTION,
                        color=theme.TEXT_SECONDARY,
                        no_wrap=True,
                    ),
                ],
                spacing=theme.SPACE_SM,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _build_theme_toggle(self) -> ft.Control:
        is_dark = theme.palette.mode == "dark"
        return ft.IconButton(
            icon=ft.Icons.LIGHT_MODE_ROUNDED
            if is_dark
            else ft.Icons.DARK_MODE_ROUNDED,
            icon_color=theme.TEXT_SECONDARY,
            icon_size=18,
            tooltip="Switch to light theme" if is_dark else "Switch to dark theme",
            on_click=self._on_toggle_theme,
        )

    def _on_toggle_theme(self, e):
        if _THEME_TOGGLE is not None:
            _THEME_TOGGLE()

    @staticmethod
    def _client():
        try:
            return get_internal_client()
        except RuntimeError:
            return None

    def _org_name(self) -> str:
        """The org's display name from the shard lookup, else its short name."""
        client = self._client()
        if client is not None and client.shard and client.shard.org_name:
            return client.shard.org_name
        creds = load_credentials() or {}
        return creds.get("org_short_name") or "—"

    def _shard_label(self) -> str:
        """e.g. "US · prod-us-ohio" — where the session's org is hosted."""
        client = self._client()
        if client is None or client.shard is None:
            return "—"
        shard = client.shard
        return " · ".join(p for p in (shard.readable_name, shard.name) if p)

    def _get_page(self):
        """Return the page, or None if not mounted yet (0.85 raises otherwise)."""
        try:
            return self.page
        except Exception:
            return None

    def _safe_update(self):
        page = self._get_page()
        if page:
            with contextlib.suppress(Exception):
                page.update()

    # ------------------------------------------------------------------
    # Session timer
    # ------------------------------------------------------------------
    def did_mount(self):
        start_session()
        self._timer_task = asyncio.create_task(self._run_timer())

    def will_unmount(self):
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        self.leave()

    async def _run_timer(self):
        try:
            while True:
                page = self._get_page()
                if page is None:
                    return
                remaining = get_session_remaining()
                if remaining <= 0:
                    clear_session()
                    self._navigate("/login")
                    return
                mins = int(remaining // 60)
                secs = int(remaining % 60)
                self._session_text.value = f"Session {mins:02d}:{secs:02d}"
                in_warning = remaining <= SESSION_WARNING_MINUTES * 60
                self._session_text.color = (
                    theme.WARNING if in_warning else theme.TEXT_SECONDARY
                )
                if in_warning:
                    self._session_banner_text.value = (
                        f"Your session expires in {mins:02d}:{secs:02d}."
                    )
                    self._extend_btn.visible = can_extend()
                    self._session_banner.visible = True
                else:
                    self._session_banner.visible = False
                try:
                    page.update()
                except Exception:
                    return
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    def _on_extend(self, e):
        if extend_session():
            self._session_banner.visible = False
            self._safe_update()

    def _on_logout(self, e):
        self._logout()
