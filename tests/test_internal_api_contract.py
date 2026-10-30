"""Contract tests for VerkadaInternalAPIClient against the endpoint registry.

Every call the app makes is fed the registry's example response for the
endpoint it hits (apis/endpoints.py — the examples were checked against
live recordings), so these catch, without a network:

- a getter whose field mapping no longer matches the response shape;
- a call to an unregistered endpoint, or a path placeholder left unfilled;
- a write that sends a top-level field the registry doesn't document;
- a create that can't find the new id in its response.
"""

from __future__ import annotations

import copy

import pytest

from apis.endpoints import ENDPOINTS, resolve
from apis.internal_api import APIError, VerkadaInternalAPIClient
from constants import (
    _BATCH_DELETERS,
    _INTERNAL_DELETERS,
    _INTERNAL_GETTERS,
    ESS_ADDRESS,
    ESS_ALARM_ADDRESS,
    ESS_GUEST_ADDRESS,
)


class Recorder:
    """Stands in for _request: answers with the registry example response
    and records every call (key, path_params, json)."""

    def __init__(self):
        self.calls: list[tuple[str, dict | None, dict | None]] = []

    def __call__(self, key, *, json=None, path_params=None, **_kwargs):
        resolve(key, path_params)  # unknown key / unfilled placeholder raises
        self.calls.append((key, path_params, json))
        example = ENDPOINTS[key].response
        data = copy.deepcopy(example if example is not None else {})
        return ({"items": data} if isinstance(data, list) else data), 200

    @property
    def keys(self) -> list[str]:
        return [k for k, _, _ in self.calls]


@pytest.fixture
def client():
    c = VerkadaInternalAPIClient("me@x.com", "pw", "org")
    c.auth_data = {"csrfToken": "c", "organizationId": "o", "adminUserId": "u"}
    c._request = Recorder()
    return c


def _documented(payload) -> set[str]:
    return set(payload) if isinstance(payload, dict) else set()


# ---------------------------------------------------------------------------
# Getters (Decommission scan)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("category, getter", sorted(_INTERNAL_GETTERS.items()))
def test_every_getter_maps_its_response(client, category, getter):
    items = getattr(client, getter)()
    assert items, f"{getter} mapped nothing from its example response"
    for item in items:
        assert isinstance(item, dict) and item.get("id"), item
    assert all(ENDPOINTS[k].method in ("GET", "POST") for k in client._request.keys)


# ---------------------------------------------------------------------------
# Deleters (Decommission delete)
# ---------------------------------------------------------------------------


def _delete_args(category):
    if category == "Alarm Sites":
        return ("alarm-site-1", "site-1")
    if category == "Schedules":
        return ([{"scheduleId": "sched-1", "name": "S", "type": "DOOR"}],)
    return ("item-1",)


@pytest.mark.parametrize("category, deleter", sorted(_INTERNAL_DELETERS.items()))
def test_every_deleter_sends_the_item_to_a_write_endpoint(client, category, deleter):
    args = _delete_args(category)
    getattr(client, deleter)(*args)
    assert client._request.calls, f"{deleter} sent nothing"
    key, path_params, body = client._request.calls[-1]
    assert ENDPOINTS[key].method in ("POST", "PUT", "DELETE", "PATCH")
    sent = repr(path_params) + repr(body)
    wanted = "sched-1" if category == "Schedules" else args[0]
    assert wanted in sent, f"{deleter} didn't send the id: {sent}"


@pytest.mark.parametrize("category, deleter", sorted(_BATCH_DELETERS.items()))
def test_batch_deleters_send_every_id_in_one_call(client, category, deleter):
    getattr(client, deleter)(["a", "b", "c"])
    assert len(client._request.calls) == 1
    _, _, body = client._request.calls[0]
    assert all(i in repr(body) for i in ("a", "b", "c"))


# ---------------------------------------------------------------------------
# Commission, Users tool and permission calls
# ---------------------------------------------------------------------------

ID = "id"  # the call must return a non-empty id string

# (method, args, kwargs, expected return): every client call the flows make.
CALLS = [
    ("create_or_reuse_site", ("HQ",), {}, ID),
    ("create_or_reuse_building", ("HQ", ESS_ADDRESS, ["G"]), {}, ID),
    ("add_devices", ([("HQ CD62", "AAAA-BBBB-CCCC")],), {}, dict),
    ("configure_cameras", (["cam-1", "cam-2"], "site-1", ESS_ADDRESS), {}, None),
    ("configure_connector", ("dev-1", "HQ Connector", "site-1", ESS_ADDRESS), {}, None),
    ("configure_access_controller", ("dev-1", "HQ Controller", "site-1", "floor-1", "America/Los_Angeles"), {}, ID),
    ("configure_access_station_pro", ("dev-1", "HQ AF64", "site-1", ESS_ADDRESS), {}, ID),
    ("create_door", ("ac-1", "HQ Door", "floor-1"), {}, ID),
    ("create_door", ("ac-1", "Garage Door", "floor-1"), {"lpr": True}, ID),
    ("create_access_station_pro_door", ("ac-1", "HQ Door", "floor-1"), {"mfa": True}, ID),
    ("create_mfa_schedule", ("door-1", "[DO NOT TOUCH] AF64 2FA"), {}, None),
    ("create_access_level", ("door-1", "HQ 24/7 Access", "site-1", "group-1"), {}, None),
    ("delete_door", ("door-1",), {}, None),
    ("delete_access_controller", ("ac-1",), {}, None),
    ("pair_lpr_camera", ("door-1", "cam-1"), {}, None),
    ("enable_org_features", (True,), {}, None),
    ("enable_org_features", (False,), {}, None),
    ("enable_org_face_unlock", (), {}, None),
    ("enable_camera_analytics", (["cam-1"],), {}, None),
    ("enable_camera_lpr", (["cam-1"],), {}, None),
    ("disable_camera_install_mode", (["cam-1"],), {}, None),
    ("enable_custom_roles", (), {}, None),
    ("enable_global_site_admin", (), {}, None),
    ("disable_global_site_admin", (), {}, None),
    ("create_alarm_site", ("Verkada", ESS_ALARM_ADDRESS, "site-1"), {}, ID),
    ("set_alarm_self_monitored", ("site-1", "rc-1"), {}, None),
    ("set_alarm_response_outputs", ("site-1", "rc-1", ["out-1"]), {}, None),
    ("create_guest_site", (ESS_GUEST_ADDRESS, "site-1"), {}, None),
    ("create_alarm_system", ("site-1",), {}, ID),
    ("configure_alarm_panel", ("dev-1", "HQ Alarm Panel", "sys-1"), {}, None),
    ("configure_keypad", ("dev-2", "HQ Keypad", "sys-1", "AAAA-BBBB-CCCC"), {}, None),
    ("create_wired_output", ("Strobe Light", "sys-1", "panel-1", 0), {}, ID),
    ("set_alarm_keycode", ("sys-1",), {}, ID),
    ("create_access_group", ("VCE Access Group",), {}, ID),
    ("add_user_to_access_group", ("user-1", "group-1"), {}, None),
    ("add_users_to_access_group", (["user-1", "user-2"], "group-1"), {}, None),
    ("create_group", ("All Participants",), {}, ID),
    ("add_users_to_group", (["user-1"], "group-1"), {}, None),
    ("invite_user", ("a@x.com", "Ada", "Lovelace"), {}, dict),
    ("rename_site", ("site-1", "HQ-10/30/26"), {}, None),
    ("enable_access_admin", (["ACCESS_CONTROL_SYSTEM_ADMIN"],), {}, None),
    ("disable_access_admin", (), {}, None),
    ("revoke_user_permissions", ("user-2", [{"entityId": "o", "permission": "SITE_ADMIN"}]), {}, None),
]


@pytest.mark.parametrize(
    "method, args, kwargs, expect",
    CALLS,
    ids=[f"{m}{'-' + '-'.join(k) if k else ''}" for m, _a, k, _e in CALLS],
)
def test_flow_calls_use_registered_endpoints(client, method, args, kwargs, expect):
    result = getattr(client, method)(*args, **kwargs)
    assert client._request.calls, f"{method} sent nothing"
    if expect is ID:
        assert isinstance(result, str) and result, f"{method} returned {result!r}"
    elif expect is not None:
        assert isinstance(result, expect)
    for key, _params, body in client._request.calls:
        endpoint = ENDPOINTS[key]
        if endpoint.method == "GET" or not isinstance(body, dict):
            continue
        documented = _documented(endpoint.payload)
        undocumented = set(body) - documented
        assert not undocumented, (
            f"{method} sends {sorted(undocumented)} to {key}, which the "
            "registry doesn't document"
        )


def test_create_or_reuse_site_falls_back_to_the_existing_site(client):
    calls = []

    def request(key, **kwargs):
        calls.append(key)
        if key == "site.create":
            raise APIError("A sub-site with the name 'HQ' already exists", status_code=400)
        return {"sites": [{"siteId": "s-old", "name": "HQ"}]}, 200

    client._request = request
    assert client.create_or_reuse_site("HQ") == "s-old"
    assert calls == ["site.create", "site.list"]


def test_create_or_reuse_building_reuses_the_named_floor(client):
    def request(key, **kwargs):
        return {
            "building.list": {"items": [{"buildingId": "b1", "name": "HQ"}]},
            "floor.list": {"items": [
                {"floorId": "f1", "name": "1", "buildingId": "b1"},
                {"floorId": "fG", "name": "G", "buildingId": "b1"},
            ]},
        }[key], 200

    client._request = request
    assert client.create_or_reuse_building("HQ", ESS_ADDRESS, ["G"]) == "fG"


def test_invite_of_an_existing_user_is_a_value_error(client):
    def request(key, **kwargs):
        raise APIError("exists", code="cannot_invite_existing", status_code=400)

    client._request = request
    with pytest.raises(ValueError, match="already exists"):
        client.invite_user("a@x.com", "Ada", "L")


# ---------------------------------------------------------------------------
# Response handling (_send)
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status, body=b""):
        import json as _json

        self.status_code = status
        self.ok = 200 <= status < 300
        self.content = body if isinstance(body, bytes) else _json.dumps(body).encode()
        self.text = self.content.decode()

    def json(self):
        import json as _json

        from requests.exceptions import JSONDecodeError

        try:
            return _json.loads(self.text)
        except ValueError as e:
            raise JSONDecodeError(str(e), self.text, 0) from e


def _send(status, body):
    c = VerkadaInternalAPIClient("me@x.com", "pw", "org")
    c.auth_data = {"csrfToken": "c", "organizationId": "o", "adminUserId": "u"}
    c.session.request = lambda *a, **k: FakeResponse(status, body)
    return c._request("site.list", json={}, error_context="ctx", auto_log=False)


def test_send_decodes_objects_and_wraps_lists():
    assert _send(200, {"sites": []}) == ({"sites": []}, 200)
    assert _send(200, [1, 2]) == ({"items": [1, 2]}, 200)


def test_send_tolerates_empty_and_non_json_success_bodies():
    assert _send(204, b"") == ({}, 204)
    assert _send(200, b"OK") == ({}, 200)


def test_send_raises_typed_errors_with_the_server_message():
    with pytest.raises(APIError) as err:
        _send(400, {"id": "bad_thing", "message": "Nope"})
    assert (err.value.code, err.value.status_code) == ("bad_thing", 400)
    assert "ctx: Nope" in str(err.value)
    with pytest.raises(APIError) as err:
        _send(502, b"<html>Bad gateway</html>")
    assert err.value.status_code == 502 and "Bad gateway" in str(err.value)


def test_requests_need_a_login():
    c = VerkadaInternalAPIClient("me@x.com", "pw", "org")
    with pytest.raises(PermissionError):
        c._request("site.list", json={}, error_context="x")
