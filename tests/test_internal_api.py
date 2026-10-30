"""Internal client: shard resolution, host routing and the API key lifecycle."""

import json

import pytest

from apis.endpoints import (
    API_GATEWAY_SUBDOMAIN,
    DEFAULT_SHARD,
    ENDPOINTS,
    GLOBAL_DOMAIN,
    OrgShard,
    build_url,
    resolve,
)
from apis.internal_api import (
    APIError,
    MFARequiredError,
    OrgNotFoundError,
    VerkadaInternalAPIClient,
    validate_org_short_name,
)

# The sample org/validate_short_name response for an org on the Ohio shard.
OHIO_RESPONSE = {
    "name": "SSS Alpha",
    "shard": {
        "name": "prod-us-ohio",
        "readable_name": "US",
        "host_metadata": {
            "domain": "prod-us-ohio.verkada.com",
            "guest_domain": "prod-us-ohio.my.verkada.com",
            "local_camera_domain": "prod-us-ohio.verkada-lan.com",
            "public_api_endpoint": "api",
            "api_gateway_endpoint": "api",
            "saml_endpoint": "https://saml.prod-us-ohio.verkada.com",
            "scim_endpoint": "https://scim.prod-us-ohio.verkada.com",
        },
        "enum_value": 13,
    },
}
OHIO = OrgShard(
    name="prod-us-ohio",
    domain="prod-us-ohio.verkada.com",
    public_api_endpoint="api",
    readable_name="US",
    org_name="SSS Alpha",
)


class _Resp:
    def __init__(self, payload, status=200):
        self.status_code = status
        self.ok = status < 400
        self.content = json.dumps(payload).encode() if payload is not None else b""
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    """Records POSTs; answers each URL from `routes` (url-substring -> resp)."""

    def __init__(self, routes):
        self.routes = routes
        self.posts = []
        self.cookies = _Cookies()

    def post(self, url, json=None, timeout=None):
        self.posts.append((url, json))
        for fragment, resp in self.routes.items():
            if fragment in url:
                return resp
        raise AssertionError(f"unexpected POST {url}")


class _Cookies(dict):
    def set(self, name, value):
        self[name] = value


def _client(shard=OHIO):
    client = VerkadaInternalAPIClient("me@x.com", "  pw  ", "sss-alpha", shard=shard)
    client.auth_data = {"csrfToken": "c", "organizationId": "o", "adminUserId": "u"}
    return client


# -- org/validate_short_name ----------------------------------------------


def test_validate_parses_the_shard():
    session = _Session({"validate_short_name": _Resp(OHIO_RESPONSE)})
    shard = validate_org_short_name("sss-alpha", session)
    assert shard == OHIO
    url, body = session.posts[0]
    assert url == (
        "https://vglobal.global-prod.verkada.com/__v/sss-alpha/org/validate_short_name"
    )
    assert body == {"orgShortName": "sss-alpha"}


@pytest.mark.parametrize(
    ("payload", "status"),
    [({"message": "not found"}, 404), ({"message": "bad"}, 400), ({}, 200), (None, 200)],
)
def test_validate_unknown_org(payload, status):
    session = _Session({"validate_short_name": _Resp(payload, status)})
    with pytest.raises(OrgNotFoundError):
        validate_org_short_name("nope", session)


def test_validate_server_error_is_not_reported_as_unknown_org():
    session = _Session({"validate_short_name": _Resp({"message": "down"}, 503)})
    with pytest.raises(ConnectionError):
        validate_org_short_name("sss-alpha", session)


@pytest.mark.parametrize(
    ("field", "value"),
    [("domain", "evil.com/x?"), ("api_gateway_endpoint", "a b"), ("domain", "")],
)
def test_validate_rejects_unusable_hosts(field, value):
    bad = json.loads(json.dumps(OHIO_RESPONSE))
    bad["shard"]["host_metadata"][field] = value
    session = _Session({"validate_short_name": _Resp(bad)})
    with pytest.raises(ConnectionError):
        validate_org_short_name("sss-alpha", session)


@pytest.mark.parametrize(
    ("name", "region", "label"),
    [
        ("prod1", "US", "api"),
        ("prod-us-ohio", "US", "api.oh"),  # US, but its own public API
        ("prod2", "EU", "api.eu"),
        ("prod-ap-syd", "AU", "api.au"),
        ("new-shard", "eu", "api.eu"),  # unknown shard: fall back to region
        ("new-shard", "", "api"),
    ],
)
def test_public_api_host_follows_the_shard(name, region, label):
    # Command's shard table sets public_api_endpoint to "apiadmin" (the key
    # admin service) on every shard; it must never become the public host.
    shard = OrgShard(name, "x.verkada.com", public_api_endpoint="apiadmin",
                     readable_name=region)
    assert shard.public_api_region == label


def test_validate_accepts_the_apiadmin_label():
    live = json.loads(json.dumps(OHIO_RESPONSE))
    live["shard"]["host_metadata"]["public_api_endpoint"] = "apiadmin"
    session = _Session({"validate_short_name": _Resp(live)})
    shard = validate_org_short_name("sss-alpha", session)
    assert shard.public_api_endpoint == "apiadmin"
    assert shard.public_api_region == "api.oh"


def test_validate_uses_the_global_domain():
    endpoint, path = resolve("org.validate_short_name")
    assert endpoint.domain == GLOBAL_DOMAIN
    # The org's shard never changes where the lookup itself goes.
    assert build_url(endpoint, "x", path, OHIO).startswith(
        "https://vglobal.global-prod.verkada.com/"
    )


# -- host routing ------------------------------------------------------------


def test_service_endpoints_use_the_shard_domain():
    endpoint, path = resolve("site.create")
    assert build_url(endpoint, "sss-alpha", path, OHIO) == (
        "https://vprovision.prod-us-ohio.verkada.com/__v/sss-alpha/" + path
    )


def test_gateway_endpoints_use_the_shard_gateway_label():
    endpoint, path = resolve("user.delete")
    assert endpoint.subdomain == API_GATEWAY_SUBDOMAIN
    shard = OHIO._replace(api_gateway_endpoint="api-gw")
    assert build_url(endpoint, "o", path, shard).startswith(
        "https://api-gw.prod-us-ohio.verkada.com/"
    )


def test_default_shard_keeps_the_original_hosts():
    endpoint, path = resolve("site.create")
    assert build_url(endpoint, "o", path).startswith(
        "https://vprovision.command.verkada.com/__v/o/"
    )
    assert DEFAULT_SHARD.name == "prod1"


def test_every_request_goes_to_the_org_shard():
    client = _client()
    seen = []

    class _S:
        def request(self, method, url, **kw):
            seen.append(url)
            raise RuntimeError("stop")  # only the URL matters

    client.session = _S()
    for key, endpoint in ENDPOINTS.items():
        if endpoint.domain is None and "{" not in endpoint.path:
            with pytest.raises(RuntimeError):
                client._request(key, error_context="x")
    assert seen and all(".prod-us-ohio.verkada.com/" in u for u in seen)


# -- login --------------------------------------------------------------------


def test_login_resolves_the_shard_then_logs_in_there():
    client = VerkadaInternalAPIClient("me@x.com", "pw", "sss-alpha")
    client.session = _Session(
        {
            "validate_short_name": _Resp(OHIO_RESPONSE),
            "/user/login": _Resp(
                {
                    "loggedIn": True,
                    "csrfToken": "c",
                    "userToken": "t",
                    "organizationId": "o",
                    "userId": "u",
                }
            ),
        }
    )
    client.login()
    (lookup_url, _), (login_url, payload) = client.session.posts
    assert "vglobal.global-prod.verkada.com" in lookup_url
    assert login_url == "https://vprovision.prod-us-ohio.verkada.com/__v/sss-alpha/user/login"
    assert payload["shard"] == "prod-us-ohio"
    assert client.shard == OHIO
    assert client.public_api_region == "api.oh"


def test_mfa_sms_goes_to_the_shard_auth_host():
    client = VerkadaInternalAPIClient("me@x.com", "pw", "sss-alpha")
    client.session = _Session(
        {
            "validate_short_name": _Resp(OHIO_RESPONSE),
            "/user/login": _Resp(
                {"message": "2FA invalid", "data": {"smsEnabled": True}}
            ),
            "twofactor/sms/new": _Resp({"smsSent": "1234"}),
        }
    )
    with pytest.raises(MFARequiredError):
        client.login()
    assert client.session.posts[-1][0] == (
        "https://vauth.prod-us-ohio.verkada.com/__v/sss-alpha/auth/twofactor/sms/new"
    )


def test_unknown_org_fails_before_any_credentials_are_sent():
    client = VerkadaInternalAPIClient("me@x.com", "pw", "nope")
    client.session = _Session({"validate_short_name": _Resp({}, 404)})
    with pytest.raises(OrgNotFoundError):
        client.login()
    assert len(client.session.posts) == 1  # the lookup only, no login POST


def test_password_is_kept_verbatim():
    assert _client().password == "  pw  "


def _fake_request(responses):
    def request(endpoint_key, **kwargs):
        return responses[endpoint_key], 200

    return request


# -- sites -------------------------------------------------------------------


def _site_client(create_error=None, sites=()):
    client = VerkadaInternalAPIClient("me@x.com", "pw", "lab")
    calls = []

    def create_site(name):
        calls.append(("create", name))
        if create_error:
            raise ConnectionError(create_error)
        return "new-site"

    client.create_site = create_site
    client.get_site = lambda: calls.append(("list",)) or list(sites)
    return client, calls


def test_create_or_reuse_site_creates_when_free():
    client, calls = _site_client()
    assert client.create_or_reuse_site("HQ") == "new-site"
    assert calls == [("create", "HQ")]


def test_create_or_reuse_site_reuses_a_same_named_site():
    # Command's reply when a template's "HQ" site is already there.
    client, _ = _site_client(
        "Failed to create site 'HQ': A sub-site with the name 'HQ' already "
        "exists under the same parent site.",
        sites=[{"id": "other", "name": "Lab"}, {"id": "hq-id", "name": "HQ"}],
    )
    assert client.create_or_reuse_site("HQ") == "hq-id"


@pytest.mark.parametrize(
    ("error", "sites"),
    [
        ("Failed to create site 'HQ': quota reached", [{"id": "hq", "name": "HQ"}]),
        ("A sub-site with the name 'HQ' already exists", [{"id": "x", "name": "Lab"}]),
    ],
)
def test_create_or_reuse_site_reraises_other_failures(error, sites):
    client, _ = _site_client(error, sites)
    with pytest.raises(ConnectionError):
        client.create_or_reuse_site("HQ")


# -- buildings ----------------------------------------------------------------


def _building_client(buildings=(), floors=()):
    client = VerkadaInternalAPIClient("me@x.com", "pw", "lab")
    created = []
    client.get_building = lambda: list(buildings)
    client.get_floor = lambda: list(floors)
    client.create_building = lambda name, addr, fl: created.append(name) or "new-floor"
    return client, created


def test_create_or_reuse_building_creates_when_none_exists():
    client, created = _building_client(buildings=[{"id": "b1", "name": "Lab"}])
    assert client.create_or_reuse_building("HQ", None, ["G"]) == "new-floor"
    assert created == ["HQ"]


def test_create_or_reuse_building_reuses_the_named_floor():
    client, created = _building_client(
        buildings=[{"id": "b1", "name": "HQ"}],
        floors=[
            {"id": "f-other", "name": "1", "building_id": "b1"},
            {"id": "f-g", "name": "G", "building_id": "b1"},
            {"id": "f-elsewhere", "name": "G", "building_id": "b9"},
        ],
    )
    assert client.create_or_reuse_building("HQ", None, ["G"]) == "f-g"
    assert created == []


def test_create_or_reuse_building_falls_back_to_any_floor_of_it():
    client, _ = _building_client(
        buildings=[{"id": "b1", "name": "HQ"}],
        floors=[{"id": "f1", "name": "Basement", "building_id": "b1"}],
    )
    assert client.create_or_reuse_building("HQ", None, ["G"]) == "f1"


# -- door/create ------------------------------------------------------------


@pytest.mark.parametrize("mfa", [False, True])
def test_access_station_pro_door_mfa_configs(monkeypatch, mfa):
    client = _client()
    sent = {}

    def fake_request(key, json=None, **kw):
        sent.update(json)
        return {"doors": [{"doorId": "d1"}]}, 200

    monkeypatch.setattr(client, "_request", fake_request)
    assert client.create_access_station_pro_door("ac", "Door", "f", mfa=mfa) == "d1"
    configs = {c["paramName"]: c["paramValue"] for c in sent["configs"]}
    assert configs["face-unlock-enabled"] == "True"
    modes = ("mfa-card-code-enabled", "mfa-face-card-enabled", "mfa-face-code-enabled")
    assert all(configs.get(m) == ("True" if mfa else None) for m in modes)


def test_org_role_keys_come_from_role_grants(monkeypatch):
    client = _client()
    sent = {}

    def fake_request(key, json=None, **kw):
        sent.update(key=key, **json)
        grants = [
            {"roleKey": "ACCESS_CONTROL_USER_ADMIN", "granteeId": "u",
             "targetEntityType": "organization"},
            {"roleKey": "SITE_ADMIN", "granteeId": "u", "targetEntityType": "site"},
        ]
        return {"roleGrant": grants}, 200

    monkeypatch.setattr(client, "_request", fake_request)
    assert client.get_org_role_keys() == {"ACCESS_CONTROL_USER_ADMIN"}
    assert sent["key"] == "permissions.user_roles.get"
    assert sent["grant"] == sent["revoke"] == [] and sent["returnPermissions"] is True


def test_org_role_keys_ignore_other_users_grants():
    # The response lists other users' grants too (seen live: 2 grantees for
    # one read). Someone else's Access System Admin must not count as held,
    # or Decommission would skip granting it.
    client = _client()
    client._request = _fake_request({"permissions.user_roles.get": {"roleGrant": [
        {"roleKey": "ORG_MANAGER", "granteeId": "u", "targetEntityType": "organization"},
        {"roleKey": "ACCESS_CONTROL_SYSTEM_ADMIN", "granteeId": "attendee",
         "targetEntityType": "organization"},
        {"roleKey": "ACCESS_CONTROL_USER_ADMIN", "targetEntityType": "organization"},
    ]}})
    assert client.get_org_role_keys() == {"ORG_MANAGER"}


def test_access_admin_roles_change_in_one_call(monkeypatch):
    client = _client()
    sent = []
    monkeypatch.setattr(
        client, "_request", lambda key, json=None, **kw: sent.append((key, json)) or ({}, 200)
    )
    client.enable_access_admin(["ACCESS_CONTROL_USER_ADMIN"])
    client.disable_access_admin()
    client.disable_access_admin([])  # nothing to do: no call
    assert [k for k, _ in sent] == ["permissions.user_roles.set"] * 2
    assert [p["permission"] for p in sent[0][1]["grant"]] == ["ACCESS_CONTROL_USER_ADMIN"]
    assert sent[0][1]["revoke"] == []
    assert [p["permission"] for p in sent[1][1]["revoke"]] == [
        "ACCESS_CONTROL_SYSTEM_ADMIN",
        "ACCESS_CONTROL_USER_ADMIN",
    ]


# -- license plates (internal API, as the web app) -----------------------------


def _plate_client(monkeypatch, holder):
    client = _client()
    sent = []

    def fake_request(key, json=None, path_params=None, **kw):
        sent.append(key)
        if key == "user.license_plate.get":
            if holder is None:
                raise APIError("No such license plate registered", status_code=404)
            return {"userId": holder}, 200
        return {}, 201

    monkeypatch.setattr(client, "_request", fake_request)
    return client, sent


def test_new_license_plate_is_looked_up_then_added(monkeypatch):
    client, sent = _plate_client(monkeypatch, None)
    assert client.add_license_plate_to_user("u", "VC1") == "VC1"
    assert sent == ["user.license_plate.get", "user.add_license_plate"]


def test_license_plate_already_on_the_user_is_not_added_again(monkeypatch):
    client, sent = _plate_client(monkeypatch, "u")
    assert client.add_license_plate_to_user("u", "VC1") == "VC1"
    assert sent == ["user.license_plate.get"]


def test_license_plate_of_another_user_is_refused(monkeypatch):
    client, sent = _plate_client(monkeypatch, "someone-else")
    with pytest.raises(ValueError, match="another user"):
        client.add_license_plate_to_user("u", "VC1")
    assert sent == ["user.license_plate.get"]


def test_standard_door_configs_leave_polling_frequency_at_its_default():
    # The web app doesn't send it; Command applies 10000 ms either way.
    from apis.endpoints import _DOOR_CREATE_CONFIGS, _LPR_DOOR_CREATE_CONFIGS

    for configs in (_DOOR_CREATE_CONFIGS, _LPR_DOOR_CREATE_CONFIGS):
        assert "polling-frequency-ms" not in {c["paramName"] for c in configs}


# -- batch claims / camera setup --------------------------------------------------


def test_add_devices_claims_all_in_one_call_and_maps_results(monkeypatch):
    client = _client()
    sent = []

    def fake_request(key, json=None, **kw):
        sent.append(json)
        return {
            "successfulDevices": [{"serialNumber": "AAAABBBBCCCC", "deviceId": "d1"}],
            "failedSerials": ["DDDD-EEEE-FFFF"],
        }, 200

    monkeypatch.setattr(client, "_request", fake_request)
    out = client.add_devices([("Cam", "aaaa-bbbb-cccc"), ("Panel", "DDDD-EEEE-FFFF")])
    assert len(sent) == 1 and [d["name"] for d in sent[0]["devices"]] == ["Cam", "Panel"]
    assert out["AAAABBBBCCCC"] == "d1"
    assert isinstance(out["DDDDEEEEFFFF"], ConnectionError)
    with pytest.raises(ConnectionError, match="Panel"):
        client.add_device("Panel", "DDDD-EEEE-FFFF")


def test_configure_cameras_sets_the_site_once_and_no_names(monkeypatch):
    client = _client()
    sent = []
    monkeypatch.setattr(
        client, "_request", lambda key, json=None, **kw: sent.append((key, json)) or ({}, 200)
    )
    client.configure_cameras(["c1", "c2", "c3"], "s1", ("Addr", 1.0, 2.0))
    keys = [k for k, _ in sent]
    assert keys.count("camera.create.site") == 1 and "camera.create.name" not in keys
    assert sent[0][1]["cameraIds"] == ["c1", "c2", "c3"]
    assert sorted(j["cameraId"] for k, j in sent if k == "camera.create.location") == [
        "c1",
        "c2",
        "c3",
    ]


def test_parallel_runs_everything_then_raises_the_first_failure():
    done = []

    def work(i):
        done.append(i)
        if i == 2:
            raise ConnectionError("two")
        return i * 10

    with pytest.raises(ConnectionError, match="two"):
        VerkadaInternalAPIClient._parallel(work, [1, 2, 3, 4])
    assert sorted(done) == [1, 2, 3, 4]
    assert VerkadaInternalAPIClient._parallel(lambda i: i + 1, [1, 2]) == [2, 3]


def test_alarm_sites_are_listed_in_one_call_with_their_configs():
    client = _client()
    calls = []

    def request(endpoint_key, json=None, **kwargs):
        calls.append(endpoint_key)
        return {
            "responseSites": [
                {"id": "as1", "siteId": "s1", "businessName": "Verkada"},
                {"id": "as2", "siteId": "s2", "businessName": "Other"},
            ],
            "responseConfigs": [
                {"id": "rc2", "responseSiteId": "as2"},
                {"id": "rc1", "responseSiteId": "as1"},
            ],
        }, 200

    client._request = request
    sites = client.get_alarm_site()
    assert calls == ["alarm.sites.list"]
    assert [(s["site_id"], s["alarm_site_id"], s["response_config_id"]) for s in sites] == [
        ("s1", "as1", "rc1"),
        ("s2", "as2", "rc2"),
    ]


def test_read_cache_sends_identical_reads_once_and_never_caches_writes():
    client = _client()
    sent = []

    def send(endpoint, url, json, *rest):
        sent.append(url)
        return {"n": len(sent)}, 200

    client._send = send
    with client.read_cache():
        first, _ = client._request("alarm.sites.list", json={"siteIds": []}, error_context="x")
        first["n"] = "changed by the caller"
        again, _ = client._request("alarm.sites.list", json={"siteIds": []}, error_context="x")
        client._request("alarm.site.create", json={}, error_context="x")
        client._request("alarm.site.create", json={}, error_context="x")
    assert again == {"n": 1}  # shared, and a copy
    assert len(sent) == 3
    client._request("alarm.sites.list", json={"siteIds": []}, error_context="x")
    assert len(sent) == 4  # no caching outside the block


def test_read_cache_shares_one_request_between_many_threads():
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    client = _client()
    sent, lock = [], threading.Lock()

    def send(endpoint, url, json, *rest):
        with lock:
            sent.append(url)
        time.sleep(0.05)  # every thread arrives while the first is in flight
        return {"sites": [1, 2]}, 200

    client._send = send
    with client.read_cache(), ThreadPoolExecutor(max_workers=32) as pool:
        results = list(
            pool.map(
                lambda _: client._request("alarm.sites.list", json={}, error_context="x"),
                range(64),
            )
        )
    assert len(sent) == 1
    assert all(r == ({"sites": [1, 2]}, 200) for r in results)
    assert len({id(r[0]) for r in results}) == 64  # each caller gets its own copy


def test_read_cache_does_not_keep_a_failed_read():
    client = _client()
    outcomes = [ConnectionError("blip"), ({"ok": True}, 200)]

    def send(*args):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    client._send = send
    with client.read_cache():
        with pytest.raises(ConnectionError):
            client._request("alarm.sites.list", json={}, error_context="x")
        assert client._request("alarm.sites.list", json={}, error_context="x") == (
            {"ok": True},
            200,
        )


def test_read_cache_releases_waiters_on_a_base_exception():
    client = _client()

    def send(*args):
        raise KeyboardInterrupt

    client._send = send
    with client.read_cache():
        with pytest.raises(KeyboardInterrupt):
            client._request("alarm.sites.list", json={}, error_context="x")
        assert client._read_cache == {}  # nothing left for a waiter to block on


def test_read_cache_keys_on_the_payload():
    client = _client()
    sent = []
    client._send = lambda endpoint, url, json, *rest: (sent.append(json) or {}, 200)
    with client.read_cache():
        client._request("alarm.sites.list", json={"a": 1, "b": 2}, error_context="x")
        client._request("alarm.sites.list", json={"b": 2, "a": 1}, error_context="x")
        client._request("alarm.sites.list", json={"a": 2}, error_context="x")
    assert len(sent) == 2  # key order doesn't matter; values do


def test_add_devices_reports_each_serial_and_matches_dashes_and_case():
    client = _client()

    def request(endpoint_key, json=None, **kwargs):
        return {
            "successfulDevices": [{"serialNumber": "AAAABBBBCCCC", "deviceId": "d1"}],
            "failedSerials": [{"serialNumber": "dddd-eeee-ffff", "reason": "claimed elsewhere"}],
        }, 200

    client._request = request
    out = client.add_devices(
        [("Cam", "aaaa-bbbb-cccc"), ("Bad", "DDDD-EEEE-FFFF"), ("Gone", "1111-2222-3333")]
    )
    assert out["AAAABBBBCCCC"] == "d1"
    assert "claimed elsewhere" in str(out["DDDDEEEEFFFF"])
    assert "missing from the response" in str(out["111122223333"])


def test_find_group_matches_by_name_and_skips_managed_groups():
    client = _client()
    client._request = _fake_request(
        {
            "group.list": {
                "securityEntityGroup": [
                    {"entityGroupId": "m", "name": "All Participants", "verkadaManaged": True},
                    {"entityGroupId": "g", "name": "All Participants", "memberIds": ["u1"]},
                ]
            }
        }
    )
    assert client.find_group("All Participants") == {"id": "g", "member_ids": {"u1"}}
    assert client.find_group("Other") is None


def test_find_access_group_reads_members():
    client = _client()
    client._request = _fake_request(
        {
            "access_group.list": {
                "children": {
                    "a1": {"name": "VCE Access Group", "users": [{"userId": "x"}]},
                    "a2": {"name": "All Participants", "users": [{"userId": "u1"}, {}]},
                    "a3": None,
                }
            }
        }
    )
    found = client.find_access_groups(["All Participants", "Missing"])
    assert found == {"All Participants": {"id": "a2", "member_ids": {"u1"}}}


def test_user_ids_by_email_is_case_insensitive_and_skips_missing_emails():
    client = _client()
    client.get_user = lambda: [
        {"id": "1", "email": "Ada@X.com"},
        {"id": "2", "email": None},
        {"id": "3", "email": ""},
    ]
    assert client.get_user_ids_by_email() == {"ada@x.com": "1"}


def _poi_client(cameras):
    from apis.internal_api import APIError

    client = _client()

    def request(endpoint_key, **kwargs):
        raise APIError("Insufficient permissions", status_code=403)

    client._request = request
    client._log = lambda *a, **k: None
    client.get_camera = lambda: cameras
    return client, APIError


def test_persons_of_interest_are_none_in_an_org_without_cameras():
    client, _ = _poi_client(cameras=[])
    assert client.get_person_of_interest() == []


def test_a_poi_403_with_cameras_present_is_raised():
    client, APIError = _poi_client(cameras=[{"id": "c1"}])
    with pytest.raises(APIError):
        client.get_person_of_interest()


@pytest.mark.parametrize("sites, expect_error", [([], False), ([{"id": "s1"}], True)])
def test_a_camera_403_means_none_only_when_the_org_has_no_sites(sites, expect_error):
    from apis.internal_api import APIError

    client = _client()

    def refuse():
        raise APIError("User has no site permission for any device type.", status_code=403)

    client._list_cameras = refuse
    client.get_site = lambda: sites
    if expect_error:
        with pytest.raises(APIError):
            client.get_camera()
    else:
        assert client.get_camera() == []


def test_add_groups_to_access_level_sends_the_level_back_with_the_new_group():
    client = _client()
    sent = []
    client._request = lambda key, **kw: (sent.append((key, kw)) or ({}, 200))
    level = {
        "scheduleId": "l1", "name": "VCE Access Level", "type": "USER",
        "userGroups": ["g1"], "events": [{"weekday": 1}], "doors": ["d1"], "siteCount": 1,
    }
    assert client.add_groups_to_access_level(level, ["g1", "g2", "g2"]) == ["g2"]
    key, kw = sent[0]
    assert key == "access_level.update" and kw["path_params"] == {"schedule_id": "l1"}
    body = kw["json"]
    assert body["userGroups"] == ["g1", "g2"]
    assert body["doors"] == body["sites"] == {"add": [], "remove": []}
    assert "events" not in body and body["name"] == "VCE Access Level"
    assert client.add_groups_to_access_level({**level, "userGroups": ["g2"]}, ["g2"]) == []
    assert len(sent) == 1  # nothing to add, no call


def test_find_access_levels_matches_live_user_levels_by_name():
    client = _client()
    client._request = _fake_request({"access_level.list": {"schedules": [
        {"name": "A", "type": "DOOR", "scheduleId": "door"},
        {"name": "A", "type": "USER", "deleted": True, "scheduleId": "gone"},
        {"name": "A", "type": "USER", "scheduleId": "a"},
        {"name": "B", "type": "USER", "scheduleId": "b"},
    ]}})
    assert {n: v["scheduleId"] for n, v in client.find_access_levels(["A", "C"]).items()} == {"A": "a"}


def test_find_access_group_id_is_none_without_permission():
    from apis.internal_api import APIError

    client = _client()

    def refuse(*a, **k):
        raise APIError("Insufficient permissions", status_code=403)

    client._request = refuse
    assert client.find_access_group_id("All Participants") is None


def test_set_alarm_response_outputs_body():
    client = _client()
    sent = []
    client._request = lambda key, **kw: (sent.append((key, kw["json"])) or ({}, 200))
    client.set_alarm_response_outputs("s1", "rc1", ["strobe"])
    assert sent == [("alarm.response.set_outputs", {
        "siteId": "s1", "responseConfigId": "rc1",
        "updateType": "CONFIG_UPDATE_TYPE_SET_OUTPUT_DEVICES",
        "setOutputDevicesInput": {"deviceIds": ["strobe"]},
    })]



def test_removable_permissions_keep_org_admin_membership_and_the_signed_in_user():
    client = _client()
    client.auth_data = {"adminUserId": "me", "organizationId": "org"}

    def grant(user, key, entity="org", grantee=None):
        return {"roleKey": key, "entityId": entity, "granteeId": grantee or user}

    client._request = _fake_request({"user.list": {"users": [
        {"userId": "me", "firstName": "Me", "roleGrants": [grant("me", "ACCESS_CONTROL_SYSTEM_ADMIN")]},
        {"userId": "a", "firstName": "Ann", "lastName": "A", "roleGrants": [
            grant("a", "ORG_MANAGER"), grant("a", "ORG_MEMBER"), grant("a", "ACCESS_ORG_MEMBER"),
            grant("a", "ACCESS_CONTROL_SYSTEM_ADMIN"), grant("a", "COMMAND_USER_VIEWER"),
            grant("a", "SITE_ADMIN", "site1"), grant("a", "SITE_ADMIN", "site1"),
            grant("a", "SITE_VIEWER", "site2", grantee="group1"),
        ]},
        {"userId": "b", "email": "b@x.com", "roleGrants": [grant("b", "ORG_MEMBER")]},
    ]}})
    assert client.get_removable_permissions() == [{
        "id": "a", "name": "Ann A", "revoke": [
            {"entityId": "org", "permission": "ACCESS_CONTROL_SYSTEM_ADMIN"},
            {"entityId": "org", "permission": "COMMAND_USER_VIEWER"},
            {"entityId": "site1", "permission": "SITE_ADMIN"},
        ],
    }]


def test_revoke_user_permissions_refuses_the_signed_in_user():
    client = _client()
    client.auth_data = {"adminUserId": "me", "organizationId": "org"}
    with pytest.raises(ValueError):
        client.revoke_user_permissions("me", [{"entityId": "org", "permission": "X"}])


def test_schedule_create_goes_through_the_no_replay_session():
    from apis.endpoints import ENDPOINTS

    assert ENDPOINTS["schedule.create.mfa"].replayable is False
    assert all(e.replayable for k, e in ENDPOINTS.items() if k != "schedule.create.mfa")
    client = _client()
    client.session.cookies.set("auth", "token")
    s = client._session_for(ENDPOINTS["schedule.create.mfa"])
    assert s is not client.session and s.cookies is client.session.cookies
    for adapter in s.adapters.values():
        assert "PUT" not in adapter.max_retries.allowed_methods
    assert client._session_for(ENDPOINTS["schedule.delete"]) is client.session
