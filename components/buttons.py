"""Button components and the shared loading-state helper.

Four variants cover every button in the app:
  - primary    : filled accent, the screen's main action
  - secondary  : outlined, neutral secondary action
  - danger     : filled danger, destructive confirmation (Decommission)
  - ghost      : text-only, low-emphasis (links, "Add participant")

`set_button_loading` swaps a button between a spinner+label state and its
normal label, preserving the project's semibold weight.
"""

from __future__ import annotations

import flet as ft

import theme

_DEFAULT_HEIGHT = 44


def _shape() -> ft.RoundedRectangleBorder:
    return ft.RoundedRectangleBorder(radius=theme.RADIUS_MD)


def primary_button(
    label: str,
    *,
    on_click=None,
    height: int = _DEFAULT_HEIGHT,
    expand=None,
    width=None,
) -> ft.ElevatedButton:
    """Filled accent button for the primary action on a screen."""
    return ft.ElevatedButton(
        content=ft.Text(
            label, color=theme.ON_ACCENT, weight=theme.WEIGHT_SEMIBOLD
        ),
        bgcolor=theme.ACCENT,
        style=ft.ButtonStyle(shape=_shape()),
        height=height,
        on_click=on_click,
        expand=expand,
        width=width,
    )


def secondary_button(
    label: str,
    *,
    on_click=None,
    height: int = _DEFAULT_HEIGHT,
    expand=None,
    width=None,
) -> ft.OutlinedButton:
    """Outlined neutral button for secondary actions."""
    return ft.OutlinedButton(
        content=ft.Text(
            label, color=theme.TEXT_SECONDARY, weight=theme.WEIGHT_SEMIBOLD
        ),
        style=ft.ButtonStyle(
            side=ft.BorderSide(1, theme.BORDER),
            shape=_shape(),
        ),
        height=height,
        on_click=on_click,
        expand=expand,
        width=width,
    )


def danger_button(
    label: str,
    *,
    on_click=None,
    height: int = _DEFAULT_HEIGHT,
    expand=None,
    width=None,
) -> ft.ElevatedButton:
    """Filled danger button for destructive confirmations."""
    return ft.ElevatedButton(
        # ON_ACCENT, not white: white on the dark palette's pastel red is
        # 2.7:1; ON_ACCENT clears 4.5:1 on DANGER in both themes.
        content=ft.Text(label, color=theme.ON_ACCENT, weight=theme.WEIGHT_SEMIBOLD),
        bgcolor=theme.DANGER,
        style=ft.ButtonStyle(shape=_shape()),
        height=height,
        on_click=on_click,
        expand=expand,
        width=width,
    )


def ghost_button(
    label: str,
    *,
    on_click=None,
    color: str | None = None,
    icon: str | None = None,
) -> ft.TextButton:
    """Low-emphasis text button (e.g. '+ Add participant').

    Pass `icon` for a leading Material icon (preferred over unicode arrows,
    which aren't guaranteed to exist in the bundled font).
    """
    fg = color or theme.ACCENT
    text = ft.Text(label, color=fg, weight=theme.WEIGHT_MEDIUM)
    content = (
        text
        if icon is None
        else ft.Row(
            [ft.Icon(icon, size=16, color=fg), text],
            spacing=theme.SPACE_XS,
            tight=True,
        )
    )
    return ft.TextButton(
        content=content,
        style=ft.ButtonStyle(shape=_shape()),
        on_click=on_click,
    )


def set_button_loading(
    btn: ft.ElevatedButton, loading: bool, label: str, auto_update: bool = True
):
    """Toggle a button between a spinner state and its normal label.

    The label color is captured from the button's own content the first time
    it toggles, so the restored label keeps whatever color the button was built
    with (accent-on-fill for `primary_button`, the neutral text color for the
    older filled buttons, …) instead of assuming a single variant. Preserving
    the semibold weight keeps a post-round-trip button from looking lighter
    than its siblings.
    """
    base_color = getattr(btn, "_loading_base_color", None)
    if base_color is None:
        base_color = getattr(btn.content, "color", None) or theme.ON_ACCENT
        btn._loading_base_color = base_color
    if loading:
        btn.content = ft.Row(
            [
                ft.ProgressRing(
                    width=16, height=16, stroke_width=2, color=base_color
                ),
                ft.Text(f"  {label}...", color=base_color),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
        )
        btn.disabled = True
    else:
        btn.content = ft.Text(
            label, color=base_color, weight=theme.WEIGHT_SEMIBOLD
        )
        btn.disabled = False
    if auto_update:
        try:
            page = btn.page
        except RuntimeError:  # flet raises (not AttributeError) when unmounted
            page = None
        if page:
            page.update()
