import asyncio

from conftest import Event

import pages.login_view as lv


def test_login_keeps_password_verbatim_and_passes_region(page, monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, email, password, org, shard, region):
            captured.update(email=email, password=password, region=region)

        def login(self):
            pass

    monkeypatch.setattr(lv, "VerkadaInternalAPIClient", FakeClient)
    view = lv.LoginView(lambda route: captured.setdefault("route", route))
    view.email_field.value = " me@example.com "
    view.password_field.value = "  spaced pass  "
    view.org_field.value = "lab"
    view.region_dropdown.value = "api.au"
    view.shard_dropdown.value = "prod1"
    asyncio.run(view._on_login(Event(page)))
    assert captured == {
        "email": "me@example.com",
        "password": "  spaced pass  ",
        "region": "api.au",
        "route": "/home",
    }


def test_blank_password_is_rejected(page):
    view = lv.LoginView(lambda route: None)
    view.email_field.value = "me@example.com"
    view.org_field.value = "lab"
    view.password_field.value = ""
    assert not view._validate()
    view.password_field.value = "   "
    view.password_field.error = None
    assert view._validate()  # whitespace-only passwords are the user's call
