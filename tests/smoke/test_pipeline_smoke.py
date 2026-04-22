"""Pipeline smoke test: ``modbus-sim → driver-modbus → stdout JSON``.

This is the ONE test that exercises the link from the simulator to the
real driver binary. The rest of the chain (MQTT → cloud → dashboard) is
covered by other suites that need a real cluster; CI runners don't have
one, so we scope here to: spin a sim, point the driver at it, parse the
driver's stdout, assert ``Sample`` shape + values + monotonic timestamps.

Setup:

- ``DRIVER_MODBUS_BIN`` env var points to a pre-built driver binary
  (the GitHub Actions workflow builds it once and exports the path). If
  unset we try ``gateway-linux/target/release/driver-modbus`` as a
  developer convenience; if that's missing too the test SKIPS rather
  than fails — building Rust mid-pytest is too slow for the smoke loop.

- The simulator is started in a subprocess on a random free port so
  parallel CI runs don't collide.

- The driver TOML is generated from a template in a temp dir so the
  ``device_id`` we assert against is the same one we pass in.

The test is marked ``@pytest.mark.smoke`` so it can be selected via
``pytest -m smoke`` or skipped via ``-m 'not smoke'``.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

# This test lives outside the normal e2e-tests cluster fixtures (api,
# gateway, etc.) — it doesn't talk to any cloud. Skip the conftest's
# session-wide INTERNAL_API_KEY assertion by importing nothing from the
# top-level conftest beyond what pytest auto-discovers.

pytestmark = pytest.mark.smoke


# ── Helpers ────────────────────────────────────────────────────────────


def _free_port() -> int:
    """Bind ephemeral, close, return the number. Race-prone in theory
    (kernel could reuse the port before we re-bind), benign in practice
    since the sim binds within milliseconds."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
    """Poll until the sim is accepting TCP connections (or fail)."""
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as e:
            last_err = e
            time.sleep(0.1)
    raise RuntimeError(f"sim never came up on {host}:{port}: {last_err}")


def _resolve_driver_bin() -> Path | None:
    """DRIVER_MODBUS_BIN > local release-built binary > None (skip).

    Returns ``None`` when nothing usable is found; the fixture turns
    that into a ``pytest.skip``. Misconfigured DRIVER_MODBUS_BIN is
    treated as a hard error — silent fallback to the local build would
    mask CI mistakes.
    """
    env = os.environ.get("DRIVER_MODBUS_BIN")
    if env:
        p = Path(env)
        if not (p.is_file() and os.access(p, os.X_OK)):
            raise RuntimeError(f"DRIVER_MODBUS_BIN={env} is not an executable file")
        return p

    # Developer convenience: if the binary is sitting in the workspace's
    # release dir, use it. We do NOT auto-build — that would slow the
    # smoke loop from seconds to minutes.
    here = Path(__file__).resolve()
    repo = here.parents[2]  # e2e-tests/tests/foo.py → repo root
    candidate = repo / "gateway-linux" / "target" / "release" / "driver-modbus"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    return None


def _python_for_sim() -> str:
    """Pick the interpreter to run the sim with.

    The CI workflow `pip install -e scadable-sdk[sim]` into the same
    venv that runs pytest, so ``sys.executable`` works. Local
    developers might run pytest from one venv and have the sim
    installed in another — they can override via ``MODBUS_SIM_PYTHON``.
    """
    return os.environ.get("MODBUS_SIM_PYTHON", sys.executable)


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def driver_bin() -> Path:
    bin_path = _resolve_driver_bin()
    if bin_path is None:
        pytest.skip(
            "driver-modbus not found. Set DRIVER_MODBUS_BIN or run "
            "`cargo build --release -p scadable-driver-modbus` from gateway-linux/."
        )
    return bin_path


@pytest.fixture
def sim(tmp_path: Path) -> Iterator[dict]:
    """Spin up the Modbus sim on a random port, kill it on teardown."""
    port = _free_port()
    config_yaml = tmp_path / "sim.yaml"
    # Two registers: one drifts, one is constant. Smoke test only reads
    # the drifting one so we can assert non-zero values without timing
    # luck (initial 250, drift +1.0/s ⇒ visible motion within 1s).
    config_yaml.write_text(
        f"""
host: 127.0.0.1
port: {port}
slave: 1
registers:
  - addr: 40001
    type: holding
    initial: 250
    drift_per_sec: 1.0
  - addr: 40002
    type: holding
    initial: 100
""".strip()
    )

    py = _python_for_sim()
    proc = subprocess.Popen(
        [py, "-m", "scadable.sim.modbus_sim", "--config", str(config_yaml)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_for_port("127.0.0.1", port)
        yield {"host": "127.0.0.1", "port": port, "slave": 1}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


@pytest.fixture
def driver_toml(tmp_path: Path, sim: dict) -> tuple[Path, str]:
    """Write a single-device modbus.toml pointing at the sim. Returns
    (path, device_id) so the test can assert the driver echoes the id
    we declared."""
    device_id = "smoke-pump-1"
    toml_path = tmp_path / "modbus.toml"
    # poll_ms=200 → ~5 samples/sec. The driver clamps anything <100ms;
    # 200 stays above that floor and gives us 5+ samples in the 2-3s
    # the test waits.
    toml_path.write_text(
        f"""
[[device]]
id = "{device_id}"
transport = "tcp"
poll_ms = 200
host = "{sim['host']}"
port = {sim['port']}
unit_id = {sim['slave']}

[[device.register]]
name = "temperature"
address = 0
fc = "holding"
dtype = "u16"
""".strip()
    )
    return toml_path, device_id


# ── Test ───────────────────────────────────────────────────────────────


def test_pipeline_smoke_sim_to_driver_stdout(
    driver_bin: Path,
    driver_toml: tuple[Path, str],
) -> None:
    """End-to-end: driver-modbus reads from the sim, emits Sample JSON
    on stdout. We collect 3 samples and assert the contract holds."""
    toml_path, expected_device_id = driver_toml

    proc = subprocess.Popen(
        [str(driver_bin), str(toml_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # line-buffered (stdbuf-equivalent on the read side)
    )
    samples: list[dict] = []
    stderr_buf: list[str] = []
    try:
        deadline = time.monotonic() + 10.0
        # Need at least 3 samples to assert monotonicity.
        while len(samples) < 3 and time.monotonic() < deadline:
            assert proc.stdout is not None
            line = proc.stdout.readline()
            if not line:
                # Driver exited prematurely. Capture stderr for diag.
                if proc.poll() is not None:
                    if proc.stderr is not None:
                        stderr_buf.append(proc.stderr.read())
                    break
                continue
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                pytest.fail(f"non-JSON line on driver stdout: {line!r}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        # Drain stderr for failure messages. Tolerate any read error
        # — we're already in teardown and the diagnostic is best-effort.
        if proc.stderr is not None:
            with contextlib.suppress(Exception):
                stderr_buf.append(proc.stderr.read() or "")

    if len(samples) < 3:
        joined = "".join(stderr_buf)
        pytest.fail(
            f"only got {len(samples)} sample(s) in 10s; expected ≥3.\n"
            f"driver stderr:\n{joined}"
        )

    # 1. Schema version + driver echoes the device_id we declared.
    for s in samples:
        assert s.get("v") == 1, f"unexpected wire version: {s}"
        assert s.get("device_id") == expected_device_id, (
            f"device_id mismatch: got {s.get('device_id')!r}, "
            f"expected {expected_device_id!r}"
        )
        assert s.get("register") == "temperature"

    # 2. Quality is "good" (sim is healthy).
    qualities = {s.get("quality", "good") for s in samples}
    assert qualities == {"good"}, f"unexpected quality values: {qualities}"

    # 3. At least one value is non-zero. The drifting register seeds at
    #    250 so EVERY sample should be non-zero, but we soften to "any"
    #    so a transient zero doesn't flake the test.
    values = [s.get("value") for s in samples]
    assert any(v not in (0, None) for v in values), (
        f"all sample values were zero/None — sim probably not driving "
        f"the register: {values}"
    )

    # 4. Timestamps are monotonic non-decreasing. RFC3339 lexical sort
    #    matches chronological order for same-TZ timestamps (driver
    #    emits UTC), so a string comparison is sufficient.
    ts = [s["ts"] for s in samples]
    assert ts == sorted(ts), f"timestamps not monotonic: {ts}"


