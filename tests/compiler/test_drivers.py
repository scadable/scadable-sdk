"""Driver fetcher — pin parsing, protocol→driver mapping, CDN fetch."""

from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import pytest

from scadable.compiler import _drivers as D
from scadable.compiler._drivers import (
    ARCHS_FOR_TARGET,
    PROTOCOL_TO_DRIVER,
    DriverFetchError,
    DriverPin,
    fetch_drivers,
    read_driver_pins,
    required_drivers,
)

# ── helpers ──────────────────────────────────────────────────────


def _write_build_yml(project_root: Path, body: str) -> None:
    (project_root / ".scadable").mkdir(exist_ok=True)
    (project_root / ".scadable" / "build.yml").write_text(body)


# ── read_driver_pins ─────────────────────────────────────────────


def test_read_driver_pins_missing_file_returns_empty(tmp_path):
    # Pre-W3 projects with no build.yml compile the same as before.
    assert read_driver_pins(tmp_path) == []


def test_read_driver_pins_missing_drivers_block_returns_empty(tmp_path):
    _write_build_yml(tmp_path, "target: linux\n")
    assert read_driver_pins(tmp_path) == []


def test_read_driver_pins_parses_mapping(tmp_path):
    _write_build_yml(
        tmp_path,
        'target: linux\ndrivers:\n  modbus: "0.1.0"\n  bluetooth: "0.2.3"\n',
    )
    pins = read_driver_pins(tmp_path)
    assert {(p.name, p.version) for p in pins} == {
        ("modbus", "0.1.0"),
        ("bluetooth", "0.2.3"),
    }


def test_read_driver_pins_bad_shape_raises(tmp_path):
    # A list instead of a mapping — user confused the YAML shape.
    _write_build_yml(tmp_path, "drivers:\n  - modbus\n  - bluetooth\n")
    with pytest.raises(DriverFetchError):
        read_driver_pins(tmp_path)


# ── required_drivers ─────────────────────────────────────────────


def test_required_drivers_dedup_modbus_tcp_rtu_to_one_driver():
    # Both protocols map to the same `modbus` driver — don't
    # double-fetch.
    devs = [
        {"connection": {"protocol": "modbus_tcp"}},
        {"connection": {"protocol": "modbus_rtu"}},
    ]
    assert required_drivers(devs) == {"modbus"}


def test_required_drivers_unknown_protocol_skipped():
    # An SDK protocol that doesn't have a driver mapping today (e.g.
    # something exotic) shouldn't break the compile — just don't try
    # to fetch a driver for it.
    devs = [{"connection": {"protocol": "ethernet_ip"}}]
    assert required_drivers(devs) == set()


def test_required_drivers_empty_for_empty_input():
    assert required_drivers([]) == set()


def test_protocol_to_driver_covers_all_sdk_protocols():
    # Guard: every protocol the target matrix declares for any
    # runnable target should have a driver mapping. Adding a new
    # protocol in `_targets.py` without wiring its driver is the
    # most likely place for a silent "compile accepts it but the
    # gateway never polls it" bug to land.
    from scadable._targets import TARGETS

    declared: set[str] = set()
    for spec in TARGETS.values():
        declared.update(spec.get("protocols", frozenset()))
    missing = declared - PROTOCOL_TO_DRIVER.keys()
    assert not missing, f"protocols without driver mapping: {sorted(missing)}"


# ── fetch_drivers (mocked CDN) ───────────────────────────────────


class _FakeCdn:
    """Tiny HTTP server that returns a canned binary + matching
    sha256 sidecar at the paths the fetcher hits. Runs on an
    ephemeral port so tests are parallel-safe."""

    def __init__(self) -> None:
        # `bytes × sha` table: the server picks a response based on
        # the URL path.
        self.binaries: dict[str, bytes] = {}
        self.server: HTTPServer | None = None
        self.thread: Thread | None = None

    def publish(self, name: str, version: str, arch: str, content: bytes) -> str:
        key = f"/drivers/{name}/{version}/{arch}/driver-{name}"
        self.binaries[key] = content
        self.binaries[key + ".sha256"] = hashlib.sha256(content).hexdigest().encode()
        return hashlib.sha256(content).hexdigest()

    def start(self) -> str:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = outer.binaries.get(self.path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a, **kw):  # quiet
                return

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        port = self.server.server_address[1]
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{port}"

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()


@pytest.fixture
def fake_cdn(monkeypatch):
    cdn = _FakeCdn()
    base = cdn.start()
    monkeypatch.setattr(D, "CDN_BASE", base)
    yield cdn
    cdn.stop()


def test_fetch_drivers_downloads_binary_and_verifies_sha(tmp_path, fake_cdn):
    content = b"\x7fELF fake modbus binary"
    expected_sha = fake_cdn.publish("modbus", "0.1.0", "linux-amd64", content)
    # Only one arch for this test — temporarily narrow the matrix
    # to avoid downloads for archs we didn't publish.
    orig = ARCHS_FOR_TARGET["linux"]
    ARCHS_FOR_TARGET["linux"] = ["linux-amd64"]
    try:
        staged = fetch_drivers([DriverPin("modbus", "0.1.0")], {"modbus"}, "linux", tmp_path)
    finally:
        ARCHS_FOR_TARGET["linux"] = orig

    assert len(staged) == 1
    s = staged[0]
    assert s.name == "modbus"
    assert s.version == "0.1.0"
    assert s.arch == "linux-amd64"
    assert s.sha256 == expected_sha
    bin_path = tmp_path / "drivers" / "linux-amd64" / "driver-modbus"
    assert bin_path.exists()
    assert bin_path.read_bytes() == content
    # Sidecar also bundled so the gateway can re-verify on apply.
    assert (
        tmp_path / "drivers" / "linux-amd64" / "driver-modbus.sha256"
    ).read_text() == expected_sha


def test_fetch_drivers_sha_mismatch_raises(tmp_path, fake_cdn, monkeypatch):
    # Publish one content but override the sha sidecar to a different
    # digest — simulates a poisoned CDN where binary and sidecar
    # disagree. Must NOT write a bad binary to the bundle.
    fake_cdn.publish("modbus", "0.1.0", "linux-amd64", b"legit")
    fake_cdn.binaries["/drivers/modbus/0.1.0/linux-amd64/driver-modbus.sha256"] = b"0" * 64

    orig = ARCHS_FOR_TARGET["linux"]
    ARCHS_FOR_TARGET["linux"] = ["linux-amd64"]
    try:
        with pytest.raises(DriverFetchError) as exc:
            fetch_drivers([DriverPin("modbus", "0.1.0")], {"modbus"}, "linux", tmp_path)
    finally:
        ARCHS_FOR_TARGET["linux"] = orig

    assert "sha256 mismatch" in str(exc.value)
    # Nothing staged on failure.
    assert not (tmp_path / "drivers").exists()


def test_fetch_drivers_missing_version_pin_raises(tmp_path, fake_cdn):
    # Device uses `modbus` but user didn't pin it. Error points the
    # user at the exact fix (the YAML snippet).
    with pytest.raises(DriverFetchError) as exc:
        fetch_drivers([], {"modbus"}, "linux", tmp_path)
    msg = str(exc.value)
    assert "modbus" in msg
    assert "drivers:" in msg  # helpful YAML stub in error


def test_fetch_drivers_404_fails_with_clear_message(tmp_path, fake_cdn):
    # Version pinned but not actually published for any arch.
    orig = ARCHS_FOR_TARGET["linux"]
    ARCHS_FOR_TARGET["linux"] = ["linux-amd64"]
    try:
        with pytest.raises(DriverFetchError) as exc:
            fetch_drivers(
                [DriverPin("modbus", "99.99.99")],
                {"modbus"},
                "linux",
                tmp_path,
            )
    finally:
        ARCHS_FOR_TARGET["linux"] = orig
    assert "not found on CDN" in str(exc.value)


def test_fetch_drivers_invalid_sha_sidecar_rejected(tmp_path, fake_cdn):
    fake_cdn.publish("modbus", "0.1.0", "linux-amd64", b"x")
    fake_cdn.binaries["/drivers/modbus/0.1.0/linux-amd64/driver-modbus.sha256"] = b"not hex at all"

    orig = ARCHS_FOR_TARGET["linux"]
    ARCHS_FOR_TARGET["linux"] = ["linux-amd64"]
    try:
        with pytest.raises(DriverFetchError) as exc:
            fetch_drivers([DriverPin("modbus", "0.1.0")], {"modbus"}, "linux", tmp_path)
    finally:
        ARCHS_FOR_TARGET["linux"] = orig
    assert "not a valid sha256" in str(exc.value)


def test_fetch_drivers_empty_needed_no_downloads(tmp_path, fake_cdn):
    # A user pins `modbus` in build.yml but has no modbus devices.
    # required_drivers returns an empty set; fetch_drivers should
    # return an empty list without any HTTP calls. (The
    # `_drivers.py::fetch_drivers` entrypoint only loops over
    # `needed`, not pins, so this is a one-liner to verify.)
    staged = fetch_drivers([DriverPin("modbus", "0.1.0")], set(), "linux", tmp_path)
    assert staged == []
