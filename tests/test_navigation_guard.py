"""main.py's run guard: leaving, theme switches and logout ask first."""

import asyncio
from types import SimpleNamespace

import flet as ft
import pytest

import main
from pages.app_shell import AppShell
from pages.login_view import LoginView
from utils import session
from utils.cancellation import CancellationToken


class AppPage:
    def __init__(self):
        self.views = []
        self.dialogs = []
        self.window = SimpleNamespace()
        self.platform_brightness = ft.Brightness.DARK

    def update(self, *controls):
        pass

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        pass


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(main, "spawn", lambda coro: coro.close())
    monkeypatch.setattr(main.prefs, "set_theme_pref", lambda mode: None)
    page = AppPage()
    asyncio.run(main.main(page))
    navigate = page.views[-1].push_route
    navigate("/home")
    return page, navigate


def _shell(page) -> AppShell:
    return page.views[-1]


def _start_job():
    token = CancellationToken()
    assert session.begin_run("Decommission", token)
    return token


def _choose(dialog, label):
    for action in dialog.actions:
        content = action.content
        text = content if isinstance(content, str) else content.value
        if text == label:
            action.on_click(None)
            return
    raise AssertionError(f"no {label!r} button")


def test_navigation_is_free_without_a_running_job(app):
    page, navigate = app
    navigate("/users")
    assert _shell(page)._tool.route == "/users"
    assert page.dialogs == []


def test_leaving_a_running_job_asks_and_keep_running_stays(app):
    page, navigate = app
    token = _start_job()
    navigate("/users")
    assert page.dialogs[-1].title.value == "Decommission in progress"
    _choose(page.dialogs[-1], "Keep running")
    assert _shell(page)._tool.route == "/home"
    assert not token.is_cancelled


def test_stop_and_continue_cancels_the_job_then_navigates(app):
    page, navigate = app
    token = _start_job()
    navigate("/users")
    _choose(page.dialogs[-1], "Stop and continue")
    assert token.is_cancelled
    assert _shell(page)._tool.route == "/users"


def test_escape_is_guarded(app):
    page, navigate = app
    navigate("/commission")
    _start_job()
    page.on_keyboard_event(SimpleNamespace(key="Escape", ctrl=False, meta=False))
    assert page.dialogs and _shell(page)._tool.route == "/commission"


def test_theme_toggle_is_guarded(app):
    page, navigate = app
    shell_before = _shell(page)
    _start_job()
    shell_before._on_toggle_theme(None)
    assert _shell(page) is shell_before  # not rebuilt
    assert page.dialogs[-1].title.value == "Decommission in progress"


def test_logout_is_guarded_and_cancels_on_confirm(app):
    page, navigate = app
    token = _start_job()
    _shell(page)._on_logout(None)
    assert isinstance(page.views[-1], AppShell)
    _choose(page.dialogs[-1], "Stop and continue")
    assert token.is_cancelled
    assert isinstance(page.views[-1], LoginView)


def test_leaving_a_tool_calls_its_leave_hook(app, monkeypatch):
    page, navigate = app
    left = []
    navigate("/decommission")
    tool = _shell(page)._tool
    monkeypatch.setattr(tool, "on_leave", lambda: left.append(tool.route))
    navigate("/home")
    assert left == ["/decommission"]


def test_theme_switch_keeps_a_decommission_scan(app, monkeypatch):
    import pages.decommission_view as dv

    page, navigate = app
    released = []
    spawned = []
    monkeypatch.setattr(dv, "spawn", spawned.append)

    class Org:
        def disable_global_site_admin(self):
            released.append("gsa_off")

        def disable_access_admin(self, roles):
            released.append("roles_off")

    navigate("/decommission")
    old = _shell(page)._tool
    old._assets = {"Cameras": [{"id": "c1", "name": "Lobby"}]}
    old._selected = {"Cameras": {0}}
    old._search_query = "lob"
    old._int_client, old._gsa_enabled = Org(), True
    old._revoke_roles = ["ACCESS_CONTROL_SYSTEM_ADMIN"]
    old._state = dv.SELECT

    _shell(page)._on_toggle_theme(None)
    for coro in spawned:  # the old screen's leave hook
        asyncio.run(coro)
    new = _shell(page)._tool
    assert new is not old and new._state == dv.SELECT
    assert new._assets == old._assets and new._selected == {"Cameras": {0}}
    assert new._search_query == "lob"
    assert released == []  # the org stays elevated for the rebuilt screen

    spawned.clear()
    navigate("/home")  # leaving for real releases it
    for coro in spawned:
        asyncio.run(coro)
    assert released == ["gsa_off", "roles_off"]
