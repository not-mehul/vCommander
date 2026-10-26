"""Public-API client: pagination and region routing."""

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
    """Records requests and answers from a {path: [pages]} script."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def request(self, method, url, json=None, params=None, headers=None):
        self.calls.append((method, url, dict(params or {})))
        token = (params or {}).get("page_token")
        return _Resp(self.pages[url][int(token) if token else 0])


def _client(pages, region="api"):
    client = object.__new__(VerkadaExternalAPIClient)
    client.api_key, client.org_short_name, client.region = "k", "org", region
    client.api_token = "t"
    client.session = _Session(pages)
    return client


def test_list_follows_next_page_token():
    url = "https://api.verkada.com/cameras/v1/devices"
    cam = lambda i: {"camera_id": f"c{i}", "name": f"Cam {i}", "serial": f"S{i}"}  # noqa: E731
    client = _client(
        {
            url: [
                {"cameras": [cam(0), cam(1)], "next_page_token": "1"},
                {"cameras": [cam(2)], "next_page_token": "2"},
                {"cameras": [cam(3)]},
            ]
        }
    )
    assert [c["id"] for c in client.get_cameras()] == ["c0", "c1", "c2", "c3"]
    assert [p.get("page_token") for _, _, p in client.session.calls] == [None, "1", "2"]
    assert all(p["page_size"] == 200 for _, _, p in client.session.calls)


def test_repeated_page_token_stops_the_loop():
    url = "https://api.verkada.com/guest/v1/sites"
    page = {"guest_sites": [{"site_id": "g", "site_name": "G"}], "next_page_token": "0"}
    client = _client({url: [page]})
    client.get_guest_sites()
    assert len(client.session.calls) == 2


def test_guest_visits_are_paged():
    url = "https://api.verkada.com/guest/v1/visits"
    visit = lambda n: {"guest": {"full_name": f"Guest {n}", "email": f"g{n}@x.com"}}  # noqa: E731
    client = _client(
        {url: [{"visits": [visit(1)], "next_page_token": "1"}, {"visits": [visit(2)]}]}
    )
    emails = [v["email"] for v in client.get_guest_visits("site", 0, 1)]
    assert emails == ["g1@x.com", "g2@x.com"]


@pytest.mark.parametrize("region", ["api", "api.eu", "api.au"])
def test_access_group_calls_use_the_client_region(region):
    base = f"https://{region}.verkada.com/access/v1"
    client = _client(
        {
            f"{base}/access_groups/group": [{"group_id": "g1"}],
            f"{base}/access_groups/group/user": [{"successful_adds": ["u1"]}],
            f"{base}/credentials/license_plate": [{"license_plate_number": "ABC"}],
        },
        region=region,
    )
    client.create_access_group("VCE")
    client.add_user_to_access_group("u1", "g1")
    client.add_license_plate_to_user("u1", "ABC")
    assert {url for _, url, _ in client.session.calls} == {
        f"{base}/access_groups/group",
        f"{base}/access_groups/group/user",
        f"{base}/credentials/license_plate",
    }


@pytest.mark.parametrize("region", ["evil.com", "api/../x", "api.eu/x", "API"])
def test_malformed_region_is_rejected(region):
    with pytest.raises(ValueError):
        VerkadaExternalAPIClient("k", "org", region=region)
