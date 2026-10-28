"""Decommission flow end to end against a fake org.

Covers: read-only categories, Confirm == Processing totals, item-level
selection + search, draining one-page categories, and reverting Global
Site Admin / the access admin roles on every exit. Decommission uses the
internal API only (no public-API key).
"""

import asyncio
import contextlib

import pytest
from conftest import Event

import constants as C
import pages.decommission_view as dv
from utils import session

_GETTER_TO_CATEGORY = {**{v: k for k, v in C._INTERNAL_GETTERS.items()}}
_DELETER_TO_CATEGORY = {v: k for k, v in C._INTERNAL_DELETERS.items()}


class FakeOrg:
    """In-memory org. Paged categories return one INTERNAL_PAGE_SIZE page."""

    org_short_name, public_api_region, user_id = "lab", "api", "me"

    def __init__(self, assets, *, fail_ids=(), scan_error=None, roles=()):
        self.store = {c: [dict(i) for i in items] for c, items in assets.items()}
        self.roles = set(roles)  # org roles the user already holds
        self.fail_ids = set(fail_ids)
        self.scan_error = scan_error
        self.calls = []
        self.deleted = []
        self.caching = False
        self.listed_while_caching = []  # categories listed inside read_cache

    # -- org settings / key ------------------------------------------------
    def create_external_api_key(self):
        raise AssertionError("Decommission must not create a public-API key")

    def delete_external_api_key(self, key_id):
        self.calls.append(f"delete_key:{key_id}")

    def enable_global_site_admin(self):
        self.calls.append("gsa_on")

    def disable_global_site_admin(self):
        self.calls.append("gsa_off")

    def get_org_role_keys(self):
        return set(self.roles)

    def enable_access_admin(self, roles):
        self.calls.append("access_admin_on:" + ",".join(roles))

    def disable_access_admin(self, roles):
        self.calls.append("access_admin_off:" + ",".join(roles))

    # -- dispatch ------------------------------------------------------------
    def _list(self, category):
        if self.caching:
            self.listed_while_caching.append(category)
        if category == self.scan_error:
            raise ConnectionError("boom")
        items = list(self.store.get(category, []))
        if category in C.PAGED_CATEGORIES:
            items = items[: C.INTERNAL_PAGE_SIZE]
        return items

    def _delete(self, category, item_id):
        if item_id in self.fail_ids:
            raise ConnectionError("refused")
        self.store[category] = [i for i in self.store[category] if i["id"] != item_id]
        self.deleted.append((category, item_id))

    def delete_persons_of_interest(self, person_ids):
        self.calls.append(f"delete_poi:{len(person_ids)}")
        for person_id in person_ids:
            self._delete("Persons of Interest", person_id)

    def delete_users(self, user_ids):
        self.calls.append(f"delete_users:{len(user_ids)}")
        for user_id in user_ids:
            self._delete("Command Users", user_id)

    def rename_site(self, site_id, name):
        self.calls.append(f"rename:{site_id}")

    @contextlib.contextmanager
    def read_cache(self):
        self.caching = True
        try:
            yield
        finally:
            self.caching = False

    def __getattr__(self, name):
        if name in _GETTER_TO_CATEGORY:
            category = _GETTER_TO_CATEGORY[name]
            return lambda: self._list(category)
        if name in _DELETER_TO_CATEGORY:
            category = _DELETER_TO_CATEGORY[name]
            return lambda item_id, *rest: self._delete(category, item_id)
        raise AttributeError(name)


_BOTH = "ACCESS_CONTROL_SYSTEM_ADMIN,ACCESS_CONTROL_USER_ADMIN"
_ROLES_ON, _ROLES_OFF = f"access_admin_on:{_BOTH}", f"access_admin_off:{_BOTH}"


def _items(prefix, n):
    return [{"id": f"{prefix}{i}", "name": f"{prefix} {i}"} for i in range(n)]


@pytest.fixture
def make(page, monkeypatch):
    def _make(assets, **kw):
        org = FakeOrg(assets, **kw)
        monkeypatch.setattr(dv, "get_internal_client", lambda: org)
        view = dv.DecommissionView(lambda route: None)
        view.page = page
        return view, org

    return _make


def _scan(view, page):
    asyncio.run(view._on_scan(Event(page)))


def _delete(view, page):
    view._set_state(page, dv.CONFIRM)
    asyncio.run(view._on_delete(Event(page)))


def test_read_only_category_is_listed_but_never_selected(make, page):
    view, org = make({"Cameras": _items("cam", 5), "Unassigned Devices": _items("u", 3)})
    _scan(view, page)
    assert view._state == dv.REVIEW
    assert "Unassigned Devices" not in view._selected
    view._set_state(page, dv.SELECT)
    assert "Unassigned Devices" not in view._category_checkboxes


def test_confirm_total_matches_what_is_deleted(make, page):
    view, org = make({"Cameras": _items("cam", 5), "Unassigned Devices": _items("u", 3)})
    _scan(view, page)
    view._set_state(page, dv.CONFIRM)
    confirm_btn = view._content_area.controls[-1].controls[1]
    assert confirm_btn.content.value == "Delete 5 Assets"
    asyncio.run(view._on_delete(Event(page)))
    assert len(org.deleted) == 5
    assert all(c == "Cameras" for c, _ in org.deleted)


def test_only_ticked_items_are_deleted(make, page):
    view, org = make({"Cameras": _items("cam", 4), "Doors": _items("door", 2)})
    _scan(view, page)
    view._set_state(page, dv.SELECT)
    view._show_items = True
    view._rebuild_tiles(page)
    # Untick one camera and the whole Doors category.
    cam_box = view._item_checkboxes["Cameras"][2]
    cam_box.value = False
    view._toggle_item(Event(page, cam_box), "Cameras", 2)
    view._toggle_category(Event(page), "Doors")
    assert view._category_checkboxes["Cameras"].value is None  # mixed
    _delete(view, page)
    assert sorted(i for _, i in org.deleted) == ["cam0", "cam1", "cam3"]
    assert view._results["Cameras"] == (3, 3)


def test_search_scopes_bulk_selection_to_matches(make, page):
    view, org = make(
        {"Cameras": [{"id": "c1", "name": "Lab Cam"}, {"id": "c2", "name": "Lobby"}]}
    )
    _scan(view, page)
    view._set_state(page, dv.SELECT)
    view._bulk_select(page, value=False)
    field = view._search_field
    field.value = "lab"
    view._on_search_change(Event(page, field))
    assert view._show_items  # searching reveals the item lists
    assert view._search_field is field  # same control, keeps focus
    view._bulk_select(page, value=True)
    assert view._selected["Cameras"] == {0}
    assert "matching “lab”" in view._selection_hint.value
    _delete(view, page)
    assert org.deleted == [("Cameras", "c1")]


def test_one_page_category_is_drained_past_the_first_page(make, page):
    total = C.INTERNAL_PAGE_SIZE * 2 + 5
    view, org = make({"Visits": _items("visit", total)})
    _scan(view, page)
    assert len(view._assets["Visits"]) == C.INTERNAL_PAGE_SIZE
    assert view._count_label("Visits") == f"{C.INTERNAL_PAGE_SIZE}+"
    _delete(view, page)
    assert len(org.deleted) == total
    assert org.store["Visits"] == []
    assert view._results["Visits"] == (total, total)


def test_partial_selection_of_a_paged_category_is_not_drained(make, page):
    view, org = make({"Visits": _items("visit", C.INTERNAL_PAGE_SIZE + 10)})
    _scan(view, page)
    view._selected["Visits"].discard(0)
    _delete(view, page)
    assert len(org.deleted) == C.INTERNAL_PAGE_SIZE - 1


def test_drain_stops_when_only_failed_items_remain(make, page):
    view, org = make(
        {"Visits": _items("visit", C.INTERNAL_PAGE_SIZE + 3)},
        fail_ids={"visit0"},
    )
    _scan(view, page)
    _delete(view, page)
    total = C.INTERNAL_PAGE_SIZE + 3
    assert view._results["Visits"] == (total - 1, total)
    assert org.store["Visits"] == [{"id": "visit0", "name": "visit 0"}]


@pytest.mark.parametrize("fail", [False, True])
def test_org_is_released_after_a_delete_run(make, page, fail):
    view, org = make({"Cameras": _items("cam", 2)}, fail_ids={"cam0"} if fail else ())
    _scan(view, page)
    _delete(view, page)
    # Reverted whatever the outcome (previously only after a clean run).
    assert org.calls[-2:] == ["gsa_off", _ROLES_OFF]
    assert ("done", "Global Site Admin turned back off") in view._cleanup
    assert ("done", "Access admin roles revoked") in view._cleanup
    assert session._active_run is None


def test_org_is_released_when_the_scan_fails(make, page):
    view, org = make({"Cameras": _items("cam", 2)}, scan_error="Doors")
    _scan(view, page)
    assert view._state == dv.SCAN
    assert org.calls == [
        "gsa_on", _ROLES_ON, "gsa_off", _ROLES_OFF
    ]
    assert page.dialogs  # "Scan Failed" alert
    assert session._active_run is None


def test_org_is_released_when_leaving_after_a_scan(make, page):
    view, org = make({"Cameras": _items("cam", 2)})

    async def scan_then_leave():
        await view._on_scan(Event(page))
        view.on_leave()
        await asyncio.sleep(0.05)  # let the spawned cleanup run

    asyncio.run(scan_then_leave())
    assert org.calls[-2:] == ["gsa_off", _ROLES_OFF]
    assert not org.deleted


def test_cancelling_mid_run_skips_the_rest_and_still_releases(make, page):
    # Deletes go out PARALLEL_REQUESTS at a time; a cancel stops before the
    # next chunk, so the chunk in flight completes.
    n = dv.PARALLEL_REQUESTS + 2
    view, org = make({"Cameras": _items("cam", n), "Sites": _items("site", 2)})
    original = org._delete

    def delete_then_cancel(category, item_id):
        original(category, item_id)
        session.cancel_run()  # e.g. the navigation guard's "Stop and continue"

    org._delete = delete_then_cancel
    _scan(view, page)
    _delete(view, page)
    assert sorted(i for _, i in org.deleted) == sorted(
        f"cam{i}" for i in range(dv.PARALLEL_REQUESTS)
    )
    assert view._cancelled_at == "Cameras"
    assert view._results["Sites"] == (0, 2)
    assert org.calls[-2:] == ["gsa_off", _ROLES_OFF]
    assert view._state == dv.COMPLETE


def test_roles_the_user_already_held_are_neither_granted_nor_revoked(make, page):
    view, org = make(
        {"Cameras": _items("cam", 1)}, roles={"ACCESS_CONTROL_SYSTEM_ADMIN"}
    )
    _scan(view, page)
    _delete(view, page)
    assert "access_admin_on:ACCESS_CONTROL_USER_ADMIN" in org.calls
    assert "access_admin_off:ACCESS_CONTROL_USER_ADMIN" in org.calls
    assert not [c for c in org.calls if "SYSTEM_ADMIN" in c]


def test_no_role_calls_when_the_user_holds_both(make, page):
    view, org = make(
        {"Cameras": _items("cam", 1)},
        roles={"ACCESS_CONTROL_SYSTEM_ADMIN", "ACCESS_CONTROL_USER_ADMIN"},
    )
    _scan(view, page)
    _delete(view, page)
    assert not [c for c in org.calls if c.startswith("access_admin")]
    assert org.calls[-1:] == ["gsa_off"]


def test_command_users_are_deleted_in_one_call(make, page):
    view, org = make({"Command Users": _items("user", 5), "Cameras": _items("cam", 1)})
    _scan(view, page)
    _delete(view, page)
    assert "delete_users:5" in org.calls
    assert view._results["Command Users"] == (5, 5)
    assert not org.store["Command Users"]


def test_alarm_categories_are_deleted_one_at_a_time(make, page, monkeypatch):
    import threading
    import time

    lock, state = threading.Lock(), {"now": 0, "max": {}}
    view, org = make({"Wired Outputs": _items("out", 4), "Cameras": _items("cam", 4)})
    original = org._delete

    def timed(category, item_id):
        with lock:
            state["now"] += 1
            state["max"][category] = max(state["max"].get(category, 0), state["now"])
        time.sleep(0.03)
        with lock:
            state["now"] -= 1
        original(category, item_id)

    org._delete = timed
    _scan(view, page)
    _delete(view, page)
    assert state["max"]["Wired Outputs"] == 1
    assert state["max"]["Cameras"] > 1


def test_persons_of_interest_are_deleted_in_one_call(make, page):
    view, org = make({"Persons of Interest": _items("poi", 6)})
    _scan(view, page)
    _delete(view, page)
    assert "delete_poi:6" in org.calls
    assert view._results["Persons of Interest"] == (6, 6)


def test_scan_lists_every_category_inside_the_read_cache(make, page):
    view, org = make({"Cameras": _items("cam", 2), "Sites": _items("s", 1)})
    _scan(view, page)
    assert view._state == dv.REVIEW
    listed = set(org.listed_while_caching)
    assert {"Cameras", "Sites"} <= listed
    assert not org.caching  # released after the scan


def test_intercom_cameras_are_not_listed_twice(make, page):
    intercom = {"id": "ic1", "name": "Door", "serial_number": "SER1"}
    view, org = make(
        {
            "Intercoms": [intercom],
            "Cameras": [
                {"id": "cam-ic", "name": "Door cam", "serial_number": "SER1"},
                {"id": "cam2", "name": "Lobby", "serial_number": "SER2"},
            ],
        }
    )
    _scan(view, page)
    assert [c["id"] for c in view._assets["Cameras"]] == ["cam2"]
    # Cameras are listed after Intercoms so the dedup serials are known.
    order = org.listed_while_caching
    assert order.index("Cameras") > order.index("Intercoms")
