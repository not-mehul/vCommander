"""Light/dark switching reaches every themed surface; buttons stay readable."""

import flet as ft
import pytest

import theme
from components import StepRow, banner, danger_button, primary_button, status_row
from pages import app_shell
from pages.home_view import HomeView
from utils.ui_utils import show_toast


def _contrast(fg: str, bg: str) -> float:
    def luminance(hex_color: str) -> float:
        h = hex_color.lstrip("#")
        channels = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    hi, lo = sorted([luminance(fg), luminance(bg)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _icon_colors(control) -> list[str]:
    found = []

    def walk(c):
        if isinstance(c, ft.Icon):
            found.append(c.color)
        for attr in ("content", "controls"):
            child = getattr(c, attr, None)
            for sub in child if isinstance(child, list) else [child]:
                if isinstance(sub, ft.Control):
                    walk(sub)

    walk(control)
    return found


def test_status_surfaces_follow_light_mode():
    theme.set_theme_mode("light")
    assert theme.SUCCESS == theme.LIGHT.success
    assert _icon_colors(banner("ok", kind="success")) == [theme.LIGHT.success]
    assert _icon_colors(status_row("failed", "x")) == [theme.LIGHT.danger]
    row = StepRow("step")
    row.succeed("done")
    assert _icon_colors(row) == [theme.LIGHT.success]


def test_toast_follows_light_mode(page):
    theme.set_theme_mode("light")
    show_toast(page, "saved", kind="success")
    snack = page.dialogs[-1]
    assert snack.bgcolor == theme.LIGHT.surface_variant
    assert _icon_colors(snack) == [theme.LIGHT.success]


def test_nav_and_home_tints_follow_light_mode():
    theme.set_theme_mode("light")
    shell = app_shell.AppShell(navigate=lambda r: None, tool_factory=None, logout=lambda: None)
    colors = _icon_colors(shell._nav_column)
    assert theme.LIGHT.brand_commission in colors
    assert theme.DARK.brand_users not in colors
    home = HomeView(lambda r: None)
    assert theme.LIGHT.brand_decommission in _icon_colors(home.body)


@pytest.mark.parametrize("mode", ["dark", "light"])
@pytest.mark.parametrize("factory", [primary_button, danger_button])
def test_filled_buttons_meet_wcag_aa(mode, factory):
    theme.set_theme_mode(mode)
    button = factory("Delete 3 Assets")
    assert _contrast(button.content.color, button.bgcolor) >= 4.5
