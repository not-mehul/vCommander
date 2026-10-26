import asyncio

from conftest import Event

import pages.users_view as uv
from apis.endpoints import OrgShard
from apis.internal_api import OrgNotFoundError
from utils import db, session


def test_connect_looks_up_the_source_org_region(page, monkeypatch):
    seen = {}

    class FakeExternal:
        def __init__(self, api_key, org, region):
            seen["region"] = region

        def get_sites(self):
            return [{"site_id": "s1", "name": "HQ"}]

    monkeypatch.setattr(uv, "VerkadaExternalAPIClient", FakeExternal)
    monkeypatch.setattr(
        uv,
        "validate_org_short_name",
        lambda org: OrgShard(
            "prod-eu", "prod-eu.verkada.com", public_api_endpoint="api.eu",
            readable_name="EU", org_name="Source Org",
        ),
    )
    view = uv.UsersView(lambda route: None)
    view.page = page
    view._api_key_field.value = "key"
    view._import_org_field.value = "source-org"
    asyncio.run(view._on_connect(Event(page)))
    assert seen["region"] == "api.eu"
    assert db.load_import_settings()["api_region"] == "api.eu"
    assert view._current_step == 1
    assert view._source_org_text.value == "Connected to Source Org · EU"


def test_connect_flags_an_unknown_source_org(page, monkeypatch):
    def not_found(org):
        raise OrgNotFoundError(f"No Verkada org named '{org}' was found.")

    monkeypatch.setattr(uv, "validate_org_short_name", not_found)
    view = uv.UsersView(lambda route: None)
    view.page = page
    view._api_key_field.value = "key"
    view._import_org_field.value = "typo-org"
    asyncio.run(view._on_connect(Event(page)))
    assert view._import_org_field.error == "No Verkada org named 'typo-org' was found."
    assert view._current_step == 0


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


def _view_with_participants(page, *rows):
    view = uv.UsersView(lambda route: None)
    view.page = page
    for first, last, email in rows:
        view._participants_column.controls.append(
            view._create_participant_row(first, last, email)
        )
    return view


def test_invalid_email_blocks_inviting(page, monkeypatch):
    monkeypatch.setattr(uv, "get_internal_client", lambda: None)
    view = _view_with_participants(page, ("A", "B", "not-an-email"))
    asyncio.run(view._on_invite_all(Event(page)))
    email_field = view._participants_column.controls[0].controls[2]
    assert email_field.error == "Enter a valid email"
    assert view._current_step == 0  # never advanced to the invite step
    assert session._active_run is None


def test_back_buttons_step_backwards(page):
    view = _view_with_participants(page)
    view._go_to_step(2, page)
    back = view._steps[2].controls[-1].controls[0]
    back.on_click(Event(page))
    assert view._current_step == 1
    back = view._steps[1].controls[-1].controls[0]
    back.on_click(Event(page))
    assert view._current_step == 0


def test_invite_progress_reaches_the_total(page, monkeypatch):
    class FakeInternal:
        def invite_user(self, email, first, last):
            return {"user_id": None}

    monkeypatch.setattr(uv, "get_internal_client", lambda: FakeInternal())
    view = _view_with_participants(
        page, ("A", "1", "a1@x.com"), ("A", "2", "a2@x.com"), ("A", "3", "")
    )
    view._add_to_group_switch.value = False
    asyncio.run(view._on_invite_all(Event(page)))
    assert view._invite_header.label == "2 / 2"
    assert view._invite_result.visible
