"""HTTP client for the Scadable cloud API.

Stdlib-only (urllib) so installing scadable-sdk doesn't drag in
requests/httpx for users who only need the controller DSL. If you want
async or connection pooling, wrap a Client in your own
httpx.AsyncClient — the wire format is documented and stable.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

DEFAULT_BASE_URL = "https://api.scadable.com"
DEFAULT_TIMEOUT_SECS = 35  # 30s server timeout + 5s slack


class APIError(Exception):
    """Raised when the API returns a non-2xx response.

    The raw body and status code are preserved so the caller can
    inspect validation errors without re-fetching. Network failures
    raise the underlying urllib exception, not APIError — that
    distinction matters for retry logic.
    """

    def __init__(self, status: int, body: str, *, url: str = ""):
        self.status = status
        self.body = body
        self.url = url
        super().__init__(f"API error {status} from {url}: {body}")


class Client:
    """Synchronous HTTP client for the Scadable cloud API.

    Auth: API key, sent as the ``X-API-Key`` header. Generate keys from
    the dashboard's API Keys panel.

    All methods raise ``APIError`` on non-2xx responses; network errors
    propagate as ``urllib.error.URLError``.

    Example
    -------

    ::

        from scadable.api import Client

        client = Client(api_key="sk_live_abcd1234")
        client.send_command(
            gateway_id="gw-abc",
            command="set_temperature",
            payload={"value": 22.5},
        )
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout_secs: float = DEFAULT_TIMEOUT_SECS,
    ):
        key = api_key or os.environ.get("SCADABLE_API_KEY", "")
        if not key:
            raise ValueError("api_key is required (pass api_key= or set SCADABLE_API_KEY env var)")
        self._api_key = key
        self._base_url = (
            base_url or os.environ.get("SCADABLE_API_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self._timeout = timeout_secs

    # ─── Gateways ────────────────────────────────────────────────────

    def list_gateways(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
    ) -> dict[str, Any]:
        """GET /v1/gateways. Returns ``{"gateways": [...], "total": N}``."""
        params: dict[str, str] = {"limit": str(limit), "offset": str(offset)}
        if status:
            params["status"] = status
        return self._request("GET", f"/v1/gateways?{urlencode(params)}")

    def get_gateway(self, gateway_id: str) -> dict[str, Any]:
        """GET /v1/gateways/{id}. Returns the gateway record."""
        return self._request("GET", f"/v1/gateways/{gateway_id}")

    def get_gateway_status(self, gateway_id: str) -> dict[str, Any]:
        """GET /v1/gateways/{id}/status. Returns ``{"status": "online", ...}``."""
        return self._request("GET", f"/v1/gateways/{gateway_id}/status")

    def list_gateway_devices(self, gateway_id: str) -> dict[str, Any]:
        """GET /v1/gateways/{id}/devices. Returns ``{"devices": [...]}``."""
        return self._request("GET", f"/v1/gateways/{gateway_id}/devices")

    # ─── Commands ────────────────────────────────────────────────────

    def send_command(
        self,
        gateway_id: str,
        command: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout_secs: int = 30,
    ) -> dict[str, Any]:
        """Send a command to a gateway. Blocks until the gateway acks
        (synchronous) or ``timeout_secs`` elapses.

        ``command`` matches the user controller's
        ``@on.message(command="X")`` declaration. ``payload`` becomes
        the JSON body the chip's handler reads via ``message.field``.

        Returns the command record:

        ::

            {
                "id": "cmd_...",
                "gateway_id": "gw-abc",
                "type": "set_temperature",
                "status": "completed" | "failed" | "timeout",
                "result": {...},      # present on completed
                "error_msg": "...",   # present on failed/timeout
                ...
            }

        Raises ``APIError`` on validation / authz / dispatch failures
        (4xx, 5xx). Returns normally for handler-level failures —
        check ``result["status"]``.
        """
        body = {
            "type": command,
            "payload": payload or {},
            "timeout_secs": timeout_secs,
        }
        return self._request(
            "POST",
            f"/v1/gateways/{gateway_id}/commands",
            body=body,
        )

    # ─── Internals ───────────────────────────────────────────────────

    def _request(
        self, method: str, path: str, *, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        data = None
        headers = {
            "X-API-Key": self._api_key,
            "Accept": "application/json",
            "User-Agent": _user_agent(),
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            # Drain the body so we can put it in the error message.
            err_body = e.read().decode("utf-8", errors="replace")
            raise APIError(e.code, err_body, url=url) from e


def _user_agent() -> str:
    """Stable user-agent so the cloud's access log can grep for SDK
    callers vs. dashboard / curl."""
    try:
        from .. import __version__
    except Exception:
        __version__ = "unknown"
    return f"scadable-sdk/{__version__} (python)"
