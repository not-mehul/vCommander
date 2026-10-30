"""Retry policy: idempotent verbs retry, POST is never replayed blindly."""

import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from apis.http import build_session


class _Handler(BaseHTTPRequestHandler):
    hits: dict

    def log_message(self, *args):
        pass

    def _respond(self):
        key = f"{self.command} {self.path}"
        n = self.hits[key] = self.hits.get(key, 0) + 1
        if self.command == "POST":
            self.rfile.read(int(self.headers.get("content-length", 0)))
        first_status = {"/502": 502, "/429": 429}.get(self.path)
        if self.path == "/slow" and n == 1:
            time.sleep(0.6)  # past the client's read timeout
        try:
            self.send_response(first_status if first_status and n == 1 else 200)
            if first_status == 429:
                self.send_header("Retry-After", "0")
            self.end_headers()
            self.wfile.write(b"{}")
        except (BrokenPipeError, ConnectionResetError):
            pass  # the client already gave up on this attempt

    do_GET = do_POST = _respond


@pytest.fixture
def server():
    hits: dict = {}
    handler = type("H", (_Handler,), {"hits": hits})
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", hits
    srv.shutdown()


@pytest.fixture
def session():
    s = build_session(timeout=0.3)
    s.trust_env = False  # never route localhost through a proxy
    return s


def test_post_is_not_replayed_after_a_5xx(server, session):
    url, hits = server
    assert session.post(url + "/502", json={}).status_code == 502
    assert hits["POST /502"] == 1


def test_post_is_not_replayed_after_a_read_timeout(server, session):
    url, hits = server
    with pytest.raises(requests.ReadTimeout):
        session.post(url + "/slow", json={})
    assert hits["POST /slow"] == 1


def test_post_is_retried_after_429(server, session):
    url, hits = server
    assert session.post(url + "/429", json={}).status_code == 200
    assert hits["POST /429"] == 2


def test_get_is_retried_after_a_5xx(server, session):
    url, hits = server
    assert session.get(url + "/502").status_code == 200
    assert hits["GET /502"] == 2


def test_get_is_retried_after_a_read_timeout(server, session):
    url, hits = server
    assert session.get(url + "/slow").status_code == 200
    assert hits["GET /slow"] == 2


class _PutHandler(_Handler):
    def do_PUT(self):
        key = f"PUT {self.path}"
        self.hits[key] = self.hits.get(key, 0) + 1
        self.rfile.read(int(self.headers.get("content-length", 0)))
        if self.path == "/slow":
            time.sleep(0.6)  # past the client's read timeout
        self.send_response(502)
        self.end_headers()
        self.wfile.write(b"{}")


@pytest.fixture
def put_server():
    hits: dict = {}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), type("H", (_PutHandler,), {"hits": hits}))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", hits
    srv.shutdown()


def _session(**kw):
    s = build_session(timeout=0.3, **kw)
    s.trust_env = False
    for adapter in s.adapters.values():
        adapter.max_retries.backoff_factor = 0
    return s


def test_put_is_replayed_by_default(put_server):
    url, hits = put_server
    with pytest.raises(requests.exceptions.RetryError):
        _session().put(url + "/x", json={})
    assert hits["PUT /x"] > 1


def test_no_replay_session_sends_a_put_once(put_server):
    # A PUT that creates (schedule upsert without an id) must not be resent
    # after a 5xx: the first attempt may already have created it.
    url, hits = put_server
    assert _session(replay=False).put(url + "/x", json={}).status_code == 502
    assert hits["PUT /x"] == 1


def test_no_replay_session_still_retries_429(server):
    url, hits = server
    assert _session(replay=False).post(url + "/429", json={}).status_code == 200
    assert hits["POST /429"] == 2


def test_no_replay_session_does_not_resend_a_put_after_a_read_timeout(put_server):
    url, hits = put_server
    with pytest.raises(requests.exceptions.ReadTimeout):
        _session(replay=False).put(url + "/slow", json={})
    time.sleep(0.8)
    assert hits["PUT /slow"] == 1
