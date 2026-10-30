"""Guards for the flet 1.x migration.

flet only warns about deprecated input properties when a page renders them,
which unit tests never do — so check the built control trees directly.
"""

import pathlib

import flet as ft
import pytest

from pages.app_shell import AppShell
from pages.commission_view import CommissionView
from pages.decommission_view import DecommissionView
from pages.home_view import HomeView
from pages.login_view import LoginView
from pages.two_factor_view import TwoFactorView
from pages.users_view import UsersView

_REPO = pathlib.Path(__file__).resolve().parent.parent
# Deprecated in flet 1.0 (removed in 1.3) in favour of `border=`.
_DEPRECATED_INPUT_PROPS = (
    "border_color",
    "focused_border_color",
    "border_radius",
    "border_width",
    "focused_border_width",
)


def _walk(control):
    yield control
    for attr in ("content", "controls", "title", "actions"):
        child = getattr(control, attr, None)
        for sub in child if isinstance(child, list) else [child]:
            if isinstance(sub, ft.Control):
                yield from _walk(sub)


def _views():
    nav = lambda *a: None  # noqa: E731
    yield LoginView(nav)
    yield TwoFactorView(nav)
    for cls in (HomeView, CommissionView, DecommissionView, UsersView):
        yield cls(nav).body
    yield AppShell(navigate=nav, tool_factory=None, logout=nav)


@pytest.mark.parametrize("root", list(_views()), ids=lambda v: type(v).__name__)
def test_inputs_use_the_border_api(root):
    inputs = [c for c in _walk(root) if isinstance(c, ft.TextField | ft.Dropdown)]
    for control in inputs:
        set_props = [p for p in _DEPRECATED_INPUT_PROPS if getattr(control, p, None)]
        assert not set_props, f"{type(control).__name__} {control.label!r}: {set_props}"
        assert control.border, f"{control.label!r} has no themed border"


def test_dropdowns_fill_their_slot():
    # flet 1.x sizes a non-expanding Dropdown to its widest option.
    for root in _views():
        for control in _walk(root):
            if isinstance(control, ft.Dropdown):
                assert control.expand, f"{control.label!r} does not expand"


def test_removed_flet_apis_are_not_used():
    sources = [p for p in _REPO.rglob("*.py") if "tests" not in p.parts]
    offenders = [str(p) for p in sources if "ElevatedButton" in p.read_text()]
    assert offenders == []
