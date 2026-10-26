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
    ("region", "label"),
    [("US", "api"), ("EU", "api.eu"), ("AU", "api.au"), ("us", "api"), ("", "api")],
)
def test_public_api_host_follows_the_shard_region(region, label):
    # Command's shard table sets public_api_endpoint to "apiadmin" (the key
    # admin service) on every shard; it must never become the public host.
    shard = OrgShard("x", "x.verkada.com", public_api_endpoint="apiadmin",
                     readable_name=region)
    assert shard.public_api_region == label


def test_validate_accepts_the_apiadmin_label():
    live = json.loads(json.dumps(OHIO_RESPONSE))
    live["shard"]["host_metadata"]["public_api_endpoint"] = "apiadmin"
    session = _Session({"validate_short_name": _Resp(live)})
    shard = validate_org_short_name("sss-alpha", session)
    assert shard.public_api_endpoint == "apiadmin"
    assert shard.public_api_region == "api"


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
    assert client.public_api_region == "api"


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


def test_create_api_key_returns_its_id():
    client = _client()
    client._request = _fake_request(
        {"org.api_key.create": {"apiKey": "secret", "apiKeyId": "kid"}}
    )
    key = client.create_external_api_key()
    assert (key.key, key.key_id) == ("secret", "kid")


def test_create_api_key_falls_back_to_lookup_by_name():
    client = _client()
    created = {}

    def request(endpoint_key, json=None, **kwargs):
        if endpoint_key == "org.api_key.create":
            created["name"] = json["api_key_name"]
            return {"apiKey": "secret"}, 200
        return {
            "apiKeys": [
                {"apiKeyId": "other", "apiKeyName": "someone else's"},
                {"apiKeyId": "kid", "apiKeyName": created["name"]},
            ]
        }, 200

    client._request = request
    assert client.create_external_api_key().key_id == "kid"


def test_failed_lookup_still_returns_the_key():
    client = _client()

    def request(endpoint_key, **kwargs):
        if endpoint_key == "org.api_key.create":
            return {"apiKey": "secret"}, 200
        raise ConnectionError("list failed")

    client._request = request
    key = client.create_external_api_key()
    assert (key.key, key.key_id) == ("secret", None)
