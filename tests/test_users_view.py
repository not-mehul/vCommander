import asyncio

from conftest import Event

import pages.users_view as uv
from utils import db, session


def test_connect_uses_and_saves_the_external_region(page, monkeypatch):
    seen = {}

    class FakeExternal:
        def __init__(self, api_key, org, region):
            seen["region"] = region

        def get_sites(self):
            return [{"site_id": "s1", "name": "HQ"}]

    monkeypatch.setattr(uv, "VerkadaExternalAPIClient", FakeExternal)
    view = uv.UsersView(lambda route: None)
    view.page = page
    view._api_key_field.value = "key"
    view._import_org_field.value = "source-org"
    view._import_region_dropdown.value = "api.eu"
    asyncio.run(view._on_connect(Event(page)))
    assert seen["region"] == "api.eu"
    assert db.load_import_settings()["api_region"] == "api.eu"
    assert view._current_step == 1


def test_stopping_an_invite_batch_skips_the_rest(page, monkeypatch):
    invited = []

    class FakeInternal:
        def invite_user(self, email, first, last):
            invited.append(email)
            session.cancel_run()  # user chose "Stop and continue" mid-batch
            return {"user_id": f"id-{email}"}

    monkeypatch.setattr(uv, "get_internal_client", lambda: FakeInternal())
    view = uv.UsersView(lambda route: None)
    view.page = page
    for n in range(3):
        view._participants_column.controls.append(
            view._create_participant_row("First", f"{n}", f"p{n}@x.com")
        )
    asyncio.run(view._on_invite_all(Event(page)))
    assert invited == ["p0@x.com"]
    texts = [row.text for row in view._invite_progress.controls if hasattr(row, "text")]
    assert "Skipped p1@x.com (cancelled)" in texts
    assert session._active_run is None
