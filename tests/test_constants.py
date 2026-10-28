"""Integrity of the decommission category tables (string-dispatched)."""

import constants as C
from apis.internal_api import VerkadaInternalAPIClient

_GETTERS = set(C._INTERNAL_GETTERS)
_DELETERS = set(C._INTERNAL_DELETERS) | set(C._BATCH_DELETERS)


def test_dispatch_names_resolve_to_client_methods():
    for mapping, cls in (
        (C._INTERNAL_GETTERS, VerkadaInternalAPIClient),
        (C._INTERNAL_DELETERS, VerkadaInternalAPIClient),
        (C._BATCH_DELETERS, VerkadaInternalAPIClient),
    ):
        missing = {k: v for k, v in mapping.items() if not hasattr(cls, v)}
        assert not missing


def test_every_category_can_be_scanned():
    assert [c for c in C.ASSET_CATEGORIES if c not in _GETTERS] == []


def test_every_deletable_category_has_a_deleter():
    assert [c for c in C.DELETION_ORDER if c not in _DELETERS] == []


def test_read_only_categories_are_scanned_but_never_deleted():
    for category in C.READ_ONLY_CATEGORIES:
        assert category in C.ASSET_CATEGORIES
        assert category not in C.DELETION_ORDER
        assert category not in _DELETERS


def test_deletion_order_covers_every_other_category_once():
    deletable = [c for c in C.ASSET_CATEGORIES if c not in C.READ_ONLY_CATEGORIES]
    assert sorted(C.DELETION_ORDER) == sorted(deletable)
    assert len(set(C.DELETION_ORDER)) == len(C.DELETION_ORDER)


def test_category_groups_reference_real_categories():
    for children in C.CATEGORY_GROUPS.values():
        assert set(children) <= set(C.ASSET_CATEGORIES)


def test_dependency_order_invariants():
    order = C.DELETION_ORDER.index
    assert order("Visits") < order("Visitors") < order("Command Users")
    assert order("Doors") < order("Access Station Pro") < order("Cameras")
    assert order("Intercoms") < order("Cameras")
    assert order("Scenarios") < order("Access Groups")
    assert order("Schedules") < order("Access Levels")
    assert order("Partitions") < order("Alarm Panels") < order("Alarm Systems")
    assert order("Alarm Systems") < order("Alarm Sites")
    assert C.DELETION_ORDER[-1] == "Sites"


def test_paged_categories_are_internal_getters():
    assert set(C.PAGED_CATEGORIES) <= set(C._INTERNAL_GETTERS)


def test_template_tables_agree():
    assert set(C.TEMPLATE_FIELDS) == set(C.TEMPLATE_DISPLAY_NAMES)


def test_decommission_does_not_use_the_public_api():
    import pages.decommission_view as dv

    assert not hasattr(C, "_EXTERNAL_GETTERS") and not hasattr(C, "_EXTERNAL_DELETERS")
    assert "VerkadaExternalAPIClient" not in vars(dv)


def test_persons_of_interest_go_before_cameras():
    # videntity refuses people calls once no camera is left in the org.
    order = C.DELETION_ORDER
    assert order.index("Persons of Interest") < order.index("Cameras")
