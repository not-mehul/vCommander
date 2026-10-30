"""Form input components: text fields and dropdowns.

Every text field and dropdown in the app goes through these so they share
one border/colour language. Borders use flet's `border=` API (a per-state
OutlineInputBorder map) — the older border_color / focused_border_color /
border_radius properties are deprecated in flet 1.0 and removed in 1.3.
"""

from __future__ import annotations

import flet as ft

import theme


def input_border() -> dict:
    """Outline border per state, resolved from the active palette."""
    radius = theme.RADIUS_MD
    return {
        ft.ControlState.DEFAULT: ft.OutlineInputBorder(
            side=ft.BorderSide(1, theme.BORDER), border_radius=radius
        ),
        ft.ControlState.FOCUSED: ft.OutlineInputBorder(
            side=ft.BorderSide(2, theme.ACCENT), border_radius=radius
        ),
        ft.ControlState.ERROR: ft.OutlineInputBorder(
            side=ft.BorderSide(1, theme.DANGER), border_radius=radius
        ),
    }


def text_field(
    label: str | None = None,
    *,
    value: str = "",
    password: bool = False,
    can_reveal_password: bool = False,
    hint: str | None = None,
    on_submit=None,
    on_change=None,
    expand=None,
    width=None,
    compact: bool = False,
    **extra,
) -> ft.TextField:
    """A styled TextField matching the app's input language.

    `compact=True` tightens the padding for dense rows (participant lists,
    search bars). Any other TextField option (max_length, prefix_icon,
    text_align, input_filter, autofocus, …) is passed through.
    """
    if compact:
        extra.setdefault(
            "content_padding", ft.Padding.symmetric(horizontal=12, vertical=10)
        )
    return ft.TextField(
        label=label,
        value=value,
        password=password,
        can_reveal_password=can_reveal_password,
        hint_text=hint,
        on_submit=on_submit,
        on_change=on_change,
        expand=expand,
        width=width,
        border=input_border(),
        color=theme.TEXT_PRIMARY,
        cursor_color=theme.ACCENT,
        label_style=ft.TextStyle(color=theme.TEXT_SECONDARY),
        hint_style=ft.TextStyle(color=theme.TEXT_MUTED),
        **extra,
    )


def dropdown(
    label: str,
    options: list[ft.dropdown.Option],
    *,
    value: str = "",
    on_select=None,
    expand=True,
    width=None,
) -> ft.Dropdown:
    """A styled Dropdown matching the app's input language.

    flet 1.x sizes a Dropdown to its widest option unless it expands, so it
    expands by default: place it in a Row (or a Container) to fill that slot.
    Pass `expand=None` with a `width` for a fixed-size one.
    """
    return ft.Dropdown(
        label=label,
        options=options,
        value=value,
        on_select=on_select,
        expand=expand,
        width=width,
        border=input_border(),
        color=theme.TEXT_PRIMARY,
        label_style=ft.TextStyle(color=theme.TEXT_SECONDARY),
    )
