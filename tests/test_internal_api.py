"""Internal client: region routing and temporary API key lifecycle."""

import pytest

from apis.endpoints import ENDPOINTS, REGIONAL_SUBDOMAIN, build_url, resolve
from apis.internal_api import VerkadaInternalAPIClient


def _client(region="api"):
    client = VerkadaInternalAPIClient("me@x.com", "  pw  ", "lab", region=region)
    client.auth_data = {"csrfToken": "c", "organizationId": "o", "adminUserId": "u"}
    return client


def test_regional_endpoints_follow_the_region():
    endpoint, path = resolve("user.delete")
    assert endpoint.subdomain == REGIONAL_SUBDOMAIN
    assert build_url(endpoint, "lab", path, "api.eu").startswith(
        "https://api.eu.command.verkada.com/__v/lab/"
    )


def test_service_endpoints_keep_their_subdomain():
    endpoint, path = resolve("site.create")
    assert build_url(endpoint, "lab", path, "api.au").startswith(
        "https://vprovision.command.verkada.com/"
    )


def test_every_regional_endpoint_is_routed(monkeypatch):
    client = _client("api.au")
    seen = []

    class _Session:
        def request(self, method, url, **kw):
            seen.append(url)
            raise RuntimeError("stop")  # we only care about the URL

    client.session = _Session()
    for key, endpoint in ENDPOINTS.items():
        if endpoint.subdomain == REGIONAL_SUBDOMAIN and "{" not in endpoint.path:
            with pytest.raises(RuntimeError):
                client._request(key, error_context="x")
    assert seen and all(u.startswith("https://api.au.command.") for u in seen)


def test_invalid_region_is_rejected():
    with pytest.raises(ValueError):
        VerkadaInternalAPIClient("e", "p", "lab", region="eu")


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
