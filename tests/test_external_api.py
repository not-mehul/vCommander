"""Public-API client (Users tool): pagination, region routing, tokens."""

import json

import pytest

from apis.external_api import VerkadaExternalAPIClient


class _Resp:
    def __init__(self, payload, status=200):
        self.status_code = status
        self.ok = status < 400
        self.text = json.dumps(payload)
        self.content = self.text.encode()
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    """Records requests and answers from a {path: [pages]} script.

    A page may be a ready _Resp (to script an error status).
    """

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def request(self, method, url, json=None, params=None, headers=None):
        self.calls.append((method, url, dict(params or {})))
        token = (params or {}).get("page_token")
        page = self.pages[url][int(token) if token else 0]
        return page if isinstance(page, _Resp) else _Resp(page)


def _client(pages, region="api"):
    client = object.__new__(VerkadaExternalAPIClient)
    client.api_key, client.org_short_name, client.region = "k", "org", region
    client.api_token = "t"
    client.session = _Session(pages)
    return client


def test_list_follows_next_page_token():
    url = "https://api.verkada.com/guest/v1/sites"
    site = lambda i: {"site_id": f"s{i}", "site_name": f"Site {i}"}  # noqa: E731
    client = _client(
        {
            url: [
                {"guest_sites": [site(0), site(1)], "next_page_token": "1"},
                {"guest_sites": [site(2)], "next_page_token": "2"},
                {"guest_sites": [site(3)]},
            ]
        }
    )
    assert client.get_sites() == [{"site_id": f"s{i}", "name": f"Site {i}"} for i in range(4)]
    assert [p.get("page_token") for _, _, p in client.session.calls] == [None, "1", "2"]
    assert all(p["page_size"] == 200 for _, _, p in client.session.calls)


def test_repeated_page_token_stops_the_loop():
    url = "https://api.verkada.com/guest/v1/sites"
    page = {"guest_sites": [{"site_id": "g", "site_name": "G"}], "next_page_token": "0"}
    client = _client({url: [page]})
    client.get_sites()
    assert len(client.session.calls) == 2


@pytest.mark.parametrize("region", ["api", "api.oh", "api.eu"])
def test_calls_use_the_client_region(region):
    url = f"https://{region}.verkada.com/guest/v1/sites"
    client = _client({url: [{"guest_sites": []}]}, region=region)
    assert client.get_sites() == []
    assert client.session.calls[0][1] == url


def test_guest_visits_are_paged():
    url = "https://api.verkada.com/guest/v1/visits"
    visit = lambda n: {"guest": {"full_name": f"Guest {n}", "email": f"g{n}@x.com"}}  # noqa: E731
    client = _client(
        {url: [{"visits": [visit(1)], "next_page_token": "1"}, {"visits": [visit(2)]}]}
    )
    emails = [v["email"] for v in client.get_guest_visits("site", 0, 1)]
    assert emails == ["g1@x.com", "g2@x.com"]


_PLATE = "https://api.verkada.com/access/v1/credentials/license_plate"
_USER = "https://api.verkada.com/access/v1/access_users/user"
_IN_USE = _Resp({"message": "This license plate number is already in use"}, 400)


@pytest.mark.parametrize("region", ["evil.com", "api/../x", "api.eu/x", "API"])
def test_malformed_region_is_rejected(region):
    with pytest.raises(ValueError):
        VerkadaExternalAPIClient("k", "org", region=region)


class _TokenSession:
    def __init__(self, resp):
        self.resp, self.urls = resp, []

    def post(self, url, headers=None):
        self.urls.append(url)
        return self.resp


@pytest.mark.parametrize(
    ("resp", "reason"),
    [
        (_Resp({"message": "invalid api key"}, 401), "invalid api key"),
        (_Resp({"id": "x"}, 200), "missing 'token'"),
        (_Resp(["unexpected"], 200), "unexpected"),
    ],
)
def test_token_failures_are_logged_and_name_the_host(resp, reason, monkeypatch):
    import apis.external_api as ext

    logged = []
    monkeypatch.setattr(ext, "log_api_call", lambda *a: logged.append(a))
    monkeypatch.setattr(ext, "build_session", lambda: _TokenSession(resp))
    with pytest.raises(ConnectionError, match="api.eu.verkada.com") as err:
        VerkadaExternalAPIClient("k", "org", region="api.eu")
    assert reason in str(err.value)
    (method, endpoint, req, status, summary), = logged
    assert endpoint == "api.eu.verkada.com/token" and reason in summary
    assert req == '{"x-api-key": "***"}'


