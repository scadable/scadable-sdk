"""Local storage type factories.

Three storage types:
  data  — time-series ring buffer (oldest dropped when full)
  files — managed file storage (auto-cleanup by TTL)
  state — persistent key-value (survives reboots)
"""

from __future__ import annotations

from typing import Any


class DataStore:
    """Time-series ring buffer for sensor readings."""

    def __init__(self, max_size: str):
        self.max_size = max_size

    def write(self, key: str, value: float) -> None: ...
    def read(self, key: str, *, last: int = 1) -> list[float]:
        return []

    def avg(self, key: str, *, window: str = "1h") -> float:
        return 0.0

    def max(self, key: str, *, window: str = "24h") -> float:
        return 0.0

    def min(self, key: str, *, window: str = "24h") -> float:
        return 0.0

    def trend(self, key: str, *, window: str = "30m") -> float:
        return 0.0

    def count(self, key: str, *, window: str = "1h") -> int:
        return 0

    def flush(self) -> None: ...


class FileStore:
    """Managed file storage with TTL-based cleanup."""

    def __init__(self, max_size: str, *, ttl: str = ""):
        self.max_size = max_size
        self.ttl = ttl

    def write(self, path: str, data: bytes, *, metadata: dict | None = None) -> None: ...
    def read(self, path: str) -> bytes:
        return b""

    def list(self, prefix: str = "") -> list[str]:
        return []

    def delete(self, path: str) -> None: ...


class StateStore:
    """Persistent key-value store that survives reboots."""

    def __init__(self, max_size: str):
        self.max_size = max_size

    def get(self, key: str, default: Any = None) -> Any:
        return default

    def set(self, key: str, value: Any) -> None: ...
    def delete(self, key: str) -> None: ...
    def increment(self, key: str, by: int = 1) -> int:
        return 0

    def clear(self) -> None: ...


def data(max_size: str) -> DataStore:
    return DataStore(max_size)


def files(max_size: str, *, ttl: str = "") -> FileStore:
    return FileStore(max_size, ttl=ttl)


def state(max_size: str) -> StateStore:
    return StateStore(max_size)
