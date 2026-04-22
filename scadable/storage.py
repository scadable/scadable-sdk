"""Local storage type factories — PREVIEW.

The storage primitives in this module are declared but **not
implemented in the gateway runtime yet**. Calling any method on
``data()``, ``files()``, or ``state()`` raises ``PreviewError`` so
your data isn't silently dropped on the floor.

Three storage types (planned):
  data  — time-series ring buffer (oldest dropped when full)
  files — managed file storage (auto-cleanup by TTL)
  state — persistent key-value (survives reboots)

Tracked in:
  https://github.com/scadable/gateway-linux/issues/1  (sqlite DataStore)
  https://github.com/scadable/gateway-linux/issues/2  (Redis StateStore)
  https://github.com/scadable/gateway-linux/issues/3  (FileStore + cloud upload)

Until the gateway-side implementations land, ``scadable verify`` /
``scadable compile`` will warn when any of these factories are
imported, and runtime use raises immediately. This is by design:
silent data loss is the worst possible failure mode for a
sensor-data product.
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
    """Persistent key-value store that survives reboots (preview)."""

    def __init__(self, max_size: str):
        self.max_size = max_size

    def get(self, key: str, default: Any = None) -> Any:
        raise _preview("state", 2, "get")

    def set(self, key: str, value: Any) -> None:
        raise _preview("state", 2, "set")

    def delete(self, key: str) -> None:
        raise _preview("state", 2, "delete")

    def increment(self, key: str, by: int = 1) -> int:
        raise _preview("state", 2, "increment")

    def clear(self) -> None:
        raise _preview("state", 2, "clear")


def data(max_size: str) -> DataStore:
    return DataStore(max_size)


def files(max_size: str, *, ttl: str = "") -> FileStore:
    return FileStore(max_size, ttl=ttl)


def state(max_size: str) -> StateStore:
    return StateStore(max_size)
