from unittest import mock

import requests

from utils import version_check


def test_parse():
    assert version_check._parse("v3.5") == (3, 5)
    assert version_check._parse("3.10.2") == (3, 10, 2)
    assert version_check._parse("V2") == (2,)
    assert version_check._parse("v3.5.0") == version_check._parse("3.5") == (3, 5)
    assert version_check._parse("v3.0") == (3,) and version_check._parse("0") == (0,)


def _response(status, payload):
    resp = mock.Mock(status_code=status)
    resp.json.return_value = payload
    return resp


def test_newer_release_is_reported(monkeypatch):
    monkeypatch.setattr(version_check, "APP_VERSION", "3.5")
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **k: _response(200, {"tag_name": "v3.10", "html_url": "u"}),
    )
    assert version_check.check_for_update() == ("3.10", "u")


def test_same_or_older_release_is_ignored(monkeypatch):
    monkeypatch.setattr(version_check, "APP_VERSION", "3.5")
    for tag in ("v3.5", "v3.5.0", "3.5.0.0", "v3.4", "v3.4.9"):
        monkeypatch.setattr(
            requests, "get", lambda *a, t=tag, **k: _response(200, {"tag_name": t})
        )
        assert version_check.check_for_update() is None


def test_network_failure_is_swallowed(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", boom)
    assert version_check.check_for_update() is None


def test_a_patch_release_is_reported(monkeypatch):
    monkeypatch.setattr(version_check, "APP_VERSION", "3.5")
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: _response(200, {"tag_name": "v3.5.1", "html_url": "u"})
    )
    assert version_check.check_for_update() == ("3.5.1", "u")
