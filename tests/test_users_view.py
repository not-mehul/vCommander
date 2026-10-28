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
            "prod2", "prod2.verkada.com",
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


def test_stopping_an_invite_batch_skips_the_next_chunks(page, monkeypatch):
    # Invites go out PARALLEL_REQUESTS at a time; a stop takes effect before
    # the next chunk (the chunk in flight completes).
    invited = []

    class FakeInternal:
        def get_user_ids_by_email(self):
            return {}

        def invite_user(self, email, first, last):
            invited.append(email)
            session.cancel_run()  # user chose "Stop and continue" mid-batch
            return {"user_id": f"id-{email}"}

    monkeypatch.setattr(uv, "get_internal_client", lambda: FakeInternal())
    view = uv.UsersView(lambda route: None)
    view.page = page
    n = uv.PARALLEL_REQUESTS + 2
    for i in range(n):
        view._participants_column.controls.append(
            view._create_participant_row("First", f"{i}", f"p{i}@x.com")
        )
    asyncio.run(view._on_invite_all(Event(page)))
    assert sorted(invited) == sorted(f"p{i}@x.com" for i in range(uv.PARALLEL_REQUESTS))
    texts = [row.text for row in view._invite_progress.controls if hasattr(row, "text")]
    assert f"Skipped p{n - 1}@x.com (cancelled)" in texts
    assert session._active_run is None


def test_invites_are_sent_in_parallel(page, monkeypatch):
    import threading
    import time

    lock, state = threading.Lock(), {"now": 0, "max": 0}

    class FakeInternal:
        def get_user_ids_by_email(self):
            return {}

        def invite_user(self, email, first, last):
            with lock:
                state["now"] += 1
                state["max"] = max(state["max"], state["now"])
            time.sleep(0.05)
            with lock:
                state["now"] -= 1
            return {"user_id": f"id-{email}"}

    monkeypatch.setattr(uv, "get_internal_client", lambda: FakeInternal())
    view = _view_with_participants(
        page, *[("A", str(i), f"a{i}@x.com") for i in range(4)]
    )
    view._add_to_group_switch.value = False
    asyncio.run(view._on_invite_all(Event(page)))
    assert state["max"] > 1
    assert [r[2] for r in view._invited_records] == [f"a{i}@x.com" for i in range(4)]


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
        def get_user_ids_by_email(self):
            return {}

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


def test_people_already_in_the_org_are_not_reinvited_but_join_the_group(page, monkeypatch):
    invited, grouped = [], []

    class FakeInternal:
        def get_user_ids_by_email(self):
            return {"old@x.com": "id-old"}

        def invite_user(self, email, first, last):
            invited.append(email)
            return {"user_id": f"id-{email}"}

        def get_group(self):
            return [{"id": "g1", "name": uv.COMMAND_GROUP_NAME}]

        def add_users_to_group(self, user_ids, group_id):
            grouped.extend(user_ids)

    monkeypatch.setattr(uv, "get_internal_client", lambda: FakeInternal())
    view = _view_with_participants(
        page, ("Old", "One", "Old@x.com"), ("New", "One", "new@x.com")
    )
    view._add_to_group_switch.value = True
    asyncio.run(view._on_invite_all(Event(page)))
    assert invited == ["new@x.com"]
    assert sorted(grouped) == ["id-new@x.com", "id-old"]
    assert view._invite_header.label == "2 / 2"
    texts = [row.text for row in view._invite_progress.controls if hasattr(row, "text")]
    assert "Already in the org: Old One (Old@x.com)" in texts
