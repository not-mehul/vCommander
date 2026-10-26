import asyncio

import flet as ft
from conftest import Event

import pages.login_view as lv
from apis.endpoints import OrgShard
from apis.internal_api import OrgNotFoundError
from utils import db

OHIO = OrgShard("prod-us-ohio", "prod-us-ohio.verkada.com", readable_name="US")


def _fake_client(captured, *, error=None):
    class FakeClient:
        def __init__(self, email, password, org):
            captured.update(email=email, password=password, org=org)
            self.email, self.password, self.org_short_name = email, password, org
            self.host_shard, self.public_api_region = OHIO, "api"

        def login(self):
            if error:
                raise error

    return FakeClient


def _fill(view, password="pw"):
    view.email_field.value = " me@example.com "
    view.password_field.value = password
    view.org_field.value = " sss-alpha "


def test_login_needs_no_shard_or_region(page, monkeypatch):
    captured = {}
    monkeypatch.setattr(lv, "VerkadaInternalAPIClient", _fake_client(captured))
    view = lv.LoginView(lambda route: captured.setdefault("route", route))
    dropdowns = [c for c in view.controls[0].content.content.controls if isinstance(c, ft.Dropdown)]
    assert not dropdowns and not hasattr(view, "shard_dropdown")
    _fill(view, password="  spaced pass  ")
    asyncio.run(view._on_login(Event(page)))
    assert captured == {
        "email": "me@example.com",
        "password": "  spaced pass  ",  # used verbatim
        "org": "sss-alpha",
        "route": "/home",
    }
    saved = db.load_credentials()
    assert (saved["shard"], saved["api_region"]) == ("prod-us-ohio", "api")


def test_unknown_org_is_flagged_on_the_org_field(page, monkeypatch):
    captured = {}
    error = OrgNotFoundError("No Verkada org named 'sss-alpha' was found.")
    monkeypatch.setattr(lv, "VerkadaInternalAPIClient", _fake_client(captured, error=error))
    view = lv.LoginView(lambda route: captured.setdefault("route", route))
    _fill(view)
    asyncio.run(view._on_login(Event(page)))
    assert view.org_field.error == str(error)
    assert "route" not in captured


def test_blank_password_is_rejected(page):
    view = lv.LoginView(lambda route: None)
    view.email_field.value = "me@example.com"
    view.org_field.value = "lab"
    view.password_field.value = ""
    assert not view._validate()
    view.password_field.value = "   "
    view.password_field.error = None
    assert view._validate()  # whitespace-only passwords are the user's call
