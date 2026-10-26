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
