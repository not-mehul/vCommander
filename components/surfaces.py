"""Surface & feedback components: cards, section headers, stat rows,
and banners.

These replace the repeated `ft.Container(bgcolor=SURFACE, border_radius=…,
border=…, shadow=…)` blocks scattered across the views with one consistent
panel, plus a few small primitives the redesigned screens lean on.
"""

from __future__ import annotations

import flet as ft

import theme

# Map a semantic kind to its (theme color token, icon) for banners. The
# token is resolved at draw time so a light/dark switch is picked up.
_KIND = {
    "info": ("INFO", ft.Icons.INFO_OUTLINE),
    "success": ("SUCCESS", ft.Icons.CHECK_CIRCLE_OUTLINE),
    "warning": ("WARNING", ft.Icons.WARNING_AMBER_ROUNDED),
    "danger": ("DANGER", ft.Icons.ERROR_OUTLINE),
}


def kind_style(kind: str) -> tuple[str, str]:
    """(color, icon) for a semantic kind in the active palette."""
    token, icon = _KIND.get(kind, _KIND["info"])
    return getattr(theme, token), icon


def card(
    content: ft.Control,
    *,
    padding: int = theme.SPACE_XL,
    expand=None,
    elevation: int = 1,
    on_click=None,
    ink: bool = False,
) -> ft.Container:
    """A standard surface panel: bg + 1px border + radius + shadow."""
    return ft.Container(
        content=content,
        bgcolor=theme.SURFACE,
        border_radius=theme.RADIUS_LG,
        border=ft.Border.all(1, theme.BORDER),
        shadow=theme.elevation(elevation),
        padding=ft.Padding.all(padding),
        expand=expand,
        on_click=on_click,
        ink=ink,
    )


def section_header(
    title: str,
    subtitle: str | None = None,
    *,
    trailing: ft.Control | None = None,
) -> ft.Control:
    """A title (+ optional subtitle) with optional trailing control.

    Used at the top of a panel/section to replace ad-hoc stacked Texts.
    """
    texts = [
        ft.Text(
            title,
            size=theme.FONT_HEADING,
            color=theme.TEXT_PRIMARY,
            weight=theme.WEIGHT_SEMIBOLD,
        )
    ]
    if subtitle:
        texts.append(
            ft.Text(subtitle, size=theme.FONT_CAPTION, color=theme.TEXT_SECONDARY)
        )
    title_block = ft.Column(texts, spacing=theme.SPACE_XS)
    if trailing is None:
        return title_block
    return ft.Row(
        [title_block, trailing],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def stat_row(label: str, value, *, accent: str | None = None) -> ft.Control:
    """One label-left / value-right line, used in count lists (Assets Found).

    `value` is shown muted at zero and accented (or primary) when non-zero,
    so a scan result reads at a glance instead of as a flat column.
    """
    is_zero = str(value) in ("0", "", "None")
    value_color = (
        theme.TEXT_MUTED if is_zero else (accent or theme.TEXT_PRIMARY)
    )
    return ft.Row(
        [
            ft.Text(label, size=theme.FONT_BODY, color=theme.TEXT_SECONDARY),
            ft.Text(
                str(value),
                size=theme.FONT_BODY,
                color=value_color,
                weight=theme.WEIGHT_SEMIBOLD if not is_zero else theme.WEIGHT_REGULAR,
            ),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )


def banner(message: str, *, kind: str = "info") -> ft.Container:
    """An inline, non-blocking banner with a semantic icon + tinted fill."""
    color, icon = kind_style(kind)
    return ft.Container(
        bgcolor=theme.palette.tint(color, 0.12),
        border=ft.Border.all(1, theme.palette.tint(color, 0.4)),
        border_radius=theme.RADIUS_MD,
        padding=ft.Padding.symmetric(
            horizontal=theme.SPACE_LG, vertical=theme.SPACE_MD
        ),
        content=ft.Row(
            [
                ft.Icon(icon, color=color, size=18),
                ft.Text(
                    message,
                    color=theme.TEXT_PRIMARY,
                    size=theme.FONT_BODY,
                    expand=True,
                ),
            ],
            spacing=theme.SPACE_MD,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )



def scroll_area(content: ft.Control, *, expand=True) -> ft.Column:
    """A vertically scrolling region whose scrollbar never covers content.

    flet draws the scrollbar on top of a scrolling Column's children, so
    right-aligned values (counts, chevrons) ended up underneath it. The
    content is inset by a gutter the width of the scrollbar.
    """
    return ft.Column(
        [
            ft.Container(
                content=content, padding=ft.Padding.only(right=theme.SPACE_LG)
            )
        ],
        scroll=ft.ScrollMode.AUTO,
        expand=expand,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
