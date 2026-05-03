"""Tests for scadable.api.Client.

We stand up a tiny http.server in a background thread so the client
exercises the real urllib path end-to-end (no mocking the transport).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from scadable.api import APIError, Client

# ─── Test server ─────────────────────────────────────────────────────


class _FakeAPIHandler(BaseHTTPRequestHandler):
    """Captures the last request and replies with whatever the test
    pre-loaded into the server's `next_response` attribute."""

    def log_message(self, *_):  # noqa: D401 — silence noisy default
        return

    def _serve(self):
        srv = self.server  # type: ignore[attr-defined]
        body = b""
        if "Content-Length" in self.headers:
            body = self.rfile.read(int(self.headers["Content-Length"]))
        srv.last_request = {
            "method": self.command,
            "path": self.path,
            "headers": dict(self.headers),
            "body": body.decode("utf-8") if body else "",
        }
        status, payload = srv.next_response
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if payload is not None:
            self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_GET(self):  # noqa: N802 — http.server contract
        self._serve()

    def do_POST(self):  # noqa: N802
        self._serve()


@pytest.fixture()
def fake_api():
    """Spin up a fake API server, give the test its base URL, and
    expose `last_request` / `next_response` for assertions + setup."""
    srv = HTTPServer(("127.0.0.1", 0), _FakeAPIHandler)
    srv.next_response = (200, {})  # type: ignore[attr-defined]
    srv.last_request = None  # type: ignore[attr-defined]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()


def _client(fake_api) -> Client:
    return Client(
        api_key="test-key",
        base_url=f"http://{fake_api.server_address[0]}:{fake_api.server_address[1]}",
    )


# ─── Auth + base URL handling ────────────────────────────────────────


def test_constructor_requires_api_key(monkeypatch):
    """No api_key + no env var = clear error, not silent failure later
    on the first request."""
    monkeypatch.delenv("SCADABLE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="api_key"):
        Client()


def test_constructor_uses_env_var(monkeypatch):
    monkeypatch.setenv("SCADABLE_API_KEY", "from-env")
    c = Client()
    assert c._api_key == "from-env"


def test_explicit_api_key_wins_over_env(monkeypatch):
    monkeypatch.setenv("SCADABLE_API_KEY", "from-env")
    c = Client(api_key="explicit")
    assert c._api_key == "explicit"


def test_base_url_env_override(monkeypatch):
    monkeypatch.setenv("SCADABLE_API_URL", "https://staging.scadable.com")
    c = Client(api_key="x")
    assert c._base_url == "https://staging.scadable.com"


def test_base_url_default_is_production(monkeypatch):
    monkeypatch.delenv("SCADABLE_API_URL", raising=False)
    c = Client(api_key="x")
    assert c._base_url == "https://api.scadable.com"


# ─── send_command (the headline method) ──────────────────────────────


def test_send_command_posts_to_v1_gateways_commands(fake_api):
    fake_api.next_response = (
        200,
        {
            "id": "cmd_xyz",
            "gateway_id": "gw-abc",
            "type": "set_temperature",
            "status": "completed",
            "result": {"ok": True},
        },
    )
    c = _client(fake_api)
    out = c.send_command("gw-abc", "set_temperature", {"value": 22.5})

    assert out["id"] == "cmd_xyz"
    assert out["status"] == "completed"
    req = fake_api.last_request
    assert req["method"] == "POST"
    assert req["path"] == "/v1/gateways/gw-abc/commands"
    assert req["headers"]["X-Api-Key"] == "test-key"
    sent = json.loads(req["body"])
    assert sent["type"] == "set_temperature"
    assert sent["payload"] == {"value": 22.5}
    assert sent["timeout_secs"] == 30


def test_send_command_omitted_payload_defaults_to_empty(fake_api):
    fake_api.next_response = (200, {"status": "completed"})
    c = _client(fake_api)
    c.send_command("gw-abc", "ping")
    sent = json.loads(fake_api.last_request["body"])
    assert sent["payload"] == {}


def test_send_command_4xx_raises_api_error(fake_api):
    fake_api.next_response = (400, {"error": "command type is required"})
    c = _client(fake_api)
    with pytest.raises(APIError) as exc_info:
        c.send_command("gw-abc", "")
    assert exc_info.value.status == 400
    assert "command type is required" in exc_info.value.body


def test_send_command_5xx_raises_api_error(fake_api):
    fake_api.next_response = (503, {"error": "orchestrator unavailable"})
    c = _client(fake_api)
    with pytest.raises(APIError) as exc_info:
        c.send_command("gw-abc", "ping")
    assert exc_info.value.status == 503


# ─── Read endpoints ──────────────────────────────────────────────────


def test_list_gateways_passes_query_params(fake_api):
    fake_api.next_response = (200, {"gateways": [], "total": 0})
    c = _client(fake_api)
    c.list_gateways(limit=5, offset=10, status="online")
    req = fake_api.last_request
    assert req["method"] == "GET"
    assert "/v1/gateways?" in req["path"]
    assert "limit=5" in req["path"]
    assert "offset=10" in req["path"]
    assert "status=online" in req["path"]


def test_get_gateway_includes_path_param(fake_api):
    fake_api.next_response = (200, {"id": "gw-abc", "name": "mine"})
    c = _client(fake_api)
    out = c.get_gateway("gw-abc")
    assert out["id"] == "gw-abc"
    assert fake_api.last_request["path"] == "/v1/gateways/gw-abc"


def test_user_agent_header_includes_sdk(fake_api):
    fake_api.next_response = (200, {})
    c = _client(fake_api)
    c.get_gateway("gw-abc")
    ua = fake_api.last_request["headers"]["User-Agent"]
    assert "scadable-sdk" in ua
