"""Decommission flow end to end against a fake org.

Covers: read-only categories, Confirm == Processing totals, item-level
selection + search, draining one-page categories, and reverting Global
Site Admin / deleting the temporary API key on every exit.
"""

import asyncio

import pytest
from conftest import Event

import constants as C
import pages.decommission_view as dv
from apis.internal_api import ExternalApiKey
from utils import session

_GETTER_TO_CATEGORY = {**{v: k for k, v in C._INTERNAL_GETTERS.items()}}
_EXT_GETTER_TO_CATEGORY = {v: k for k, v in C._EXTERNAL_GETTERS.items()}
_DELETER_TO_CATEGORY = {
    **{v: k for k, v in C._INTERNAL_DELETERS.items()},
    **{v: k for k, v in C._EXTERNAL_DELETERS.items()},
}


class FakeOrg:
    """In-memory org. Paged categories return one INTERNAL_PAGE_SIZE page."""

    org_short_name, region, user_id = "lab", "api", "me"

    def __init__(self, assets, *, fail_ids=(), scan_error=None):
        self.store = {c: [dict(i) for i in items] for c, items in assets.items()}
        self.fail_ids = set(fail_ids)
        self.scan_error = scan_error
        self.calls = []
        self.deleted = []

    # -- org settings / key ------------------------------------------------
    def create_external_api_key(self):
        self.calls.append("create_key")
        return ExternalApiKey("secret", "kid")

    def delete_external_api_key(self, key_id):
        self.calls.append(f"delete_key:{key_id}")

    def enable_global_site_admin(self):
        self.calls.append("gsa_on")

    def disable_global_site_admin(self):
        self.calls.append("gsa_off")

    def enable_access_admin(self):
        self.calls.append("access_admin_on")

    # -- dispatch ------------------------------------------------------------
    def _list(self, category):
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

    def get_users(self, exclude_user_id=None, exclude_email=None):
        return self._list("Command Users")

    def rename_site(self, site_id, name):
        self.calls.append(f"rename:{site_id}")

    def __getattr__(self, name):
        if name in _GETTER_TO_CATEGORY or name in _EXT_GETTER_TO_CATEGORY:
            category = _GETTER_TO_CATEGORY.get(name) or _EXT_GETTER_TO_CATEGORY[name]
            return lambda: self._list(category)
        if name in _DELETER_TO_CATEGORY:
            category = _DELETER_TO_CATEGORY[name]
            return lambda item_id, *rest: self._delete(category, item_id)
        raise AttributeError(name)


def _items(prefix, n):
    return [{"id": f"{prefix}{i}", "name": f"{prefix} {i}"} for i in range(n)]


@pytest.fixture
def make(page, monkeypatch):
    def _make(assets, **kw):
        org = FakeOrg(assets, **kw)
        monkeypatch.setattr(dv, "get_internal_client", lambda: org)
        monkeypatch.setattr(dv, "VerkadaExternalAPIClient", lambda *a: org)
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
    assert org.calls[-2:] == ["gsa_off", "delete_key:kid"]
    assert ("done", "Global Site Admin turned back off") in view._cleanup
    assert session._active_run is None


def test_org_is_released_when_the_scan_fails(make, page):
    view, org = make({"Cameras": _items("cam", 2)}, scan_error="Doors")
    _scan(view, page)
    assert view._state == dv.SCAN
    assert org.calls == [
        "create_key", "gsa_on", "access_admin_on", "gsa_off", "delete_key:kid"
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
    assert org.calls[-2:] == ["gsa_off", "delete_key:kid"]
    assert not org.deleted


def test_cancelling_mid_run_skips_the_rest_and_still_releases(make, page):
    view, org = make({"Cameras": _items("cam", 3), "Sites": _items("site", 2)})
    original = org._delete

    def delete_then_cancel(category, item_id):
        original(category, item_id)
        session.cancel_run()  # e.g. the navigation guard's "Stop and continue"

    org._delete = delete_then_cancel
    _scan(view, page)
    _delete(view, page)
    assert org.deleted == [("Cameras", "cam0")]
    assert view._cancelled_at == "Cameras"
    assert view._results["Sites"] == (0, 2)
    assert org.calls[-2:] == ["gsa_off", "delete_key:kid"]
    assert view._state == dv.COMPLETE
