"""Home / dashboard screen.

With the persistent sidebar now owning navigation, org/session chips, and
logout, Home is a compact landing dashboard rather than the app's primary
navigation surface: a short intro, a tidy row of tool cards, and a keyboard
shortcut hint. The session countdown and auto-logout live in `AppShell`.
"""

import flet as ft

import theme
from components import card
from pages.app_shell import ToolView

# (route, title, icon, brand tint token, description) for the three tool
# cards. Tints are theme token names, resolved when the card is drawn.
_TOOLS = [
    (
        "/commission",
        "Commission",
        ft.Icons.BUSINESS_ROUNDED,
        "BRAND_COMMISSION",
        "Set up sites, claim devices, and configure templates.",
    ),
    (
        "/users",
        "User Management",
        ft.Icons.PEOPLE_ALT_ROUNDED,
        "BRAND_USERS",
        "Import and invite guest participants from external orgs.",
    ),
    (
        "/decommission",
        "Decommission",
        ft.Icons.DELETE_SWEEP_ROUNDED,
        "BRAND_DECOMMISSION",
        "Scan and remove assets with dependency-aware ordering.",
    ),
]


_CARD_HEIGHT = 240

# (keys, action) for the shortcut reference. Plain-text key names: the
# bundled font has no guaranteed glyph for the macOS command symbol.
_SHORTCUTS = [
    ("Ctrl/Cmd + K", "Command palette"),
    ("Esc", "Back"),
    ("Ctrl/Cmd + ,", "Log out"),
    ("Enter", "Submit the current form"),
]


class HomeView(ToolView):
    def __init__(self, push_route):
        super().__init__(
            push_route,
            route="/home",
            title="Home",
            subtitle="Pick a tool to get started.",
        )
        self._build_ui()

    def _build_ui(self):
        # Three equal tool tiles at a fixed height (stretching them to the
        # window bottom left them mostly empty), then the shortcut reference.
        cards_row = ft.Row(
            [self._tool_card(*t) for t in _TOOLS],
            spacing=theme.SPACE_LG,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            height=_CARD_HEIGHT,
        )
        self.mount(
            ft.Column(
                [cards_row, self._shortcuts_card()],
                spacing=theme.SPACE_LG,
                scroll=ft.ScrollMode.AUTO,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            )
        )

    def _shortcuts_card(self) -> ft.Control:
        def shortcut(keys: str, action: str) -> ft.Control:
            return ft.Row(
                [
                    ft.Container(
                        content=ft.Text(
                            keys,
                            size=theme.FONT_CAPTION,
                            color=theme.TEXT_PRIMARY,
                            weight=theme.WEIGHT_MEDIUM,
                            font_family=theme.FONT_MONO,
                        ),
                        bgcolor=theme.SURFACE_VARIANT,
                        border=ft.Border.all(1, theme.BORDER),
                        border_radius=theme.RADIUS_MD,
                        padding=ft.Padding.symmetric(
                            horizontal=theme.SPACE_SM, vertical=2
                        ),
                    ),
                    ft.Text(action, size=theme.FONT_BODY, color=theme.TEXT_SECONDARY),
                ],
                spacing=theme.SPACE_SM,
                tight=True,
            )

        return card(
            ft.Column(
                [
                    ft.Text(
                        "Keyboard shortcuts",
                        size=theme.FONT_BODY,
                        color=theme.TEXT_PRIMARY,
                        weight=theme.WEIGHT_SEMIBOLD,
                    ),
                    ft.Row(
                        [
                            shortcut(keys, action)
                            for keys, action in _SHORTCUTS
                        ],
                        spacing=theme.SPACE_2XL,
                        wrap=True,
                        run_spacing=theme.SPACE_SM,
                    ),
                ],
                spacing=theme.SPACE_MD,
            ),
            padding=theme.SPACE_XL,
        )

    def _tool_card(self, route, title, icon, brand, description) -> ft.Control:
        brand = getattr(theme, brand)
        inner = card(
            ft.Column(
                [
                    ft.Container(
                        width=56,
                        height=56,
                        border_radius=theme.RADIUS_MD,
                        bgcolor=theme.palette.tint(brand, 0.16),
                        alignment=ft.Alignment.CENTER,
                        content=ft.Icon(icon, size=28, color=brand),
                    ),
                    ft.Container(height=theme.SPACE_LG),
                    ft.Text(
                        title,
                        size=theme.FONT_HEADING,
                        color=theme.TEXT_PRIMARY,
                        weight=theme.WEIGHT_SEMIBOLD,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(height=theme.SPACE_XS),
                    ft.Text(
                        description,
                        size=theme.FONT_BODY,
                        color=theme.TEXT_SECONDARY,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                # Center the icon + label block in the tile, both axes.
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=0,
                expand=True,
            ),
            padding=theme.SPACE_XL,
            expand=True,
            on_click=lambda _, r=route: self.push_route(r),
            ink=True,
        )
        inner.animate = ft.Animation(160, ft.AnimationCurve.EASE_IN_OUT)
        wrapper = ft.Container(content=inner, expand=1)
        wrapper.on_hover = lambda e, c=inner: self._hover(e, c)
        return wrapper

    def _hover(self, e, c: ft.Container):
        active = e.data == "true"
        c.border = ft.Border.all(1, theme.ACCENT if active else theme.BORDER)
        c.shadow = theme.elevation(2 if active else 1)
        page = getattr(self, "page", None)
        if page:
            page.update()
