"""Local storage type factories.

Three storage types:
  data   — time-series ring buffer (oldest dropped when full) — PREVIEW
  files  — managed file storage (auto-cleanup by TTL)         — PREVIEW
  state  — persistent key-value (survives reboots)            — PRODUCTION on ESP32

``self.state`` (NW-E)
---------------------

In a controller, ``self.state`` is the recommended entry point::

    class MotionCounter(Controller):
        @on.startup
        def init(self):
            self.state.set("count", 0)

        @on.message(command="motion_detected")
        def hit(self):
            self.state.increment("count")

The chip-side runtime (``gateway-esp/.../handlers/state.rs``) is the
production backing store: per-gateway, NVS-persisted, debounced flush
to flash. The SDK's compiler recognises ``self.state.<op>(...)`` calls
statically and lowers them into ``StateAction`` entries in the manifest
the chip applies. No Python runs on the chip.

The classes in this module also work as a **local Python sandbox**:
in-memory only, no NVS, no cross-process sharing. Useful for
``scadable verify`` and unit-testing controller logic on a laptop
before flashing. Anything written to the sandbox is gone when the
process exits — the chip is the source of truth in production.

``data`` and ``files`` still raise ``PreviewError`` — those backends
haven't shipped on either gateway. Linux ``state`` is also still
in-memory only (gateway-linux#2 tracks the Redis-backed runtime).
"""

from __future__ import annotations

from typing import Any


class PreviewError(NotImplementedError):
    """Raised when preview-status SDK surface is invoked at runtime.

    Subclasses ``NotImplementedError`` so existing user code that
    catches NIE keeps working, but the dedicated type is greppable
    in logs and lets us add a single message format.
    """


_STORAGE_PREVIEW_MSG = (
    "scadable.{kind}() is preview — the gateway runtime does not "
    "persist these calls yet. Tracking in "
    "https://github.com/scadable/gateway-linux/issues/{issue}. "
    "Calls to {method}() raise so your data isn't silently lost."
)


def _preview(kind: str, issue: int, method: str) -> PreviewError:
    return PreviewError(_STORAGE_PREVIEW_MSG.format(kind=kind, issue=issue, method=method))


class DataStore:
    """Time-series ring buffer for sensor readings (preview)."""

    def __init__(self, max_size: str):
        self.max_size = max_size

    def write(self, key: str, value: float) -> None:
        raise _preview("data", 1, "write")

    def read(self, key: str, *, last: int = 1) -> list[float]:
        raise _preview("data", 1, "read")

    def avg(self, key: str, *, window: str = "1h") -> float:
        raise _preview("data", 1, "avg")

    def max(self, key: str, *, window: str = "24h") -> float:
        raise _preview("data", 1, "max")

    def min(self, key: str, *, window: str = "24h") -> float:
        raise _preview("data", 1, "min")

    def trend(self, key: str, *, window: str = "30m") -> float:
        raise _preview("data", 1, "trend")

    def count(self, key: str, *, window: str = "1h") -> int:
        raise _preview("data", 1, "count")

    def flush(self) -> None:
        raise _preview("data", 1, "flush")


class FileStore:
    """Managed file storage with TTL-based cleanup (preview)."""

    def __init__(self, max_size: str, *, ttl: str = ""):
        self.max_size = max_size
        self.ttl = ttl

    def write(self, path: str, data: bytes, *, metadata: dict | None = None) -> None:
        raise _preview("files", 3, "write")

    def read(self, path: str) -> bytes:
        raise _preview("files", 3, "read")

    def list(self, prefix: str = "") -> list[str]:
        raise _preview("files", 3, "list")

    def delete(self, path: str) -> None:
        raise _preview("files", 3, "delete")


class StateStore:
    """Persistent key-value store that survives reboots.

    ESP32 (production): backed by NVS in
    ``gateway-esp/.../handlers/state.rs``. Reads + writes resolve at
    apply time against the chip's in-memory cache, debounced-flushed
    to flash at most once per second.

    This Python class is the **local sandbox**. The compiler recognises
    ``self.state.set("k", v)`` etc. as AST patterns and emits manifest
    entries the chip executes — your Python doesn't run on the chip.
    Use these methods directly only when stepping through controller
    logic on a laptop; the in-memory dict here vanishes on process
    exit.
    """

    def __init__(self, max_size: str = ""):
        # max_size accepted for forward-compat with future quota knobs;
        # ignored today (NVS partition cap is the real limit on chip).
        self.max_size = max_size
        self._store: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def increment(self, key: str, by: int = 1) -> int:
        cur = self._store.get(key, 0)
        try:
            cur_n = float(cur)
        except (TypeError, ValueError):
            cur_n = 0.0
        nxt = cur_n + by
        # Match the chip behavior: stay an int when both sides round-
        # trip integral. Otherwise keep the float.
        if nxt == int(nxt):
            self._store[key] = int(nxt)
            return int(nxt)
        self._store[key] = nxt
        return nxt  # type: ignore[return-value]

    def clear(self) -> None:
        self._store.clear()


def data(max_size: str) -> DataStore:
    return DataStore(max_size)


def files(max_size: str, *, ttl: str = "") -> FileStore:
    return FileStore(max_size, ttl=ttl)


def state(max_size: str = "") -> StateStore:
    return StateStore(max_size)
