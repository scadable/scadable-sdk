"""Pin the storage-API preview behaviour.

Storage primitives (DataStore / FileStore / StateStore) are exposed
in the SDK but their gateway-side implementations don't exist yet.
Without the PreviewError raise, user code calling .write() would
silently lose data — the worst possible failure mode for an IoT
product. These tests lock in the contract until the deferred
follow-ups land:

  https://github.com/scadable/gateway-linux/issues/1  (sqlite DataStore)
  https://github.com/scadable/gateway-linux/issues/2  (Redis StateStore)
  https://github.com/scadable/gateway-linux/issues/3  (FileStore + cloud upload)
"""

import pytest

from scadable.storage import (
    DataStore,
    FileStore,
    PreviewError,
    StateStore,
    data,
    files,
    state,
)


def test_datastore_methods_raise_preview_error():
    d = data("64MB")
    assert isinstance(d, DataStore)
    with pytest.raises(PreviewError, match="data"):
        d.write("temp", 42.0)
    with pytest.raises(PreviewError, match="data"):
        d.read("temp")
    with pytest.raises(PreviewError, match="data"):
        d.avg("temp")
    with pytest.raises(PreviewError, match="data"):
        d.flush()


def test_filestore_methods_raise_preview_error():
    f = files("128MB", ttl="7d")
    assert isinstance(f, FileStore)
    with pytest.raises(PreviewError, match="files"):
        f.write("/img/cap.png", b"\x00")
    with pytest.raises(PreviewError, match="files"):
        f.read("/img/cap.png")
    with pytest.raises(PreviewError, match="files"):
        f.list()
    with pytest.raises(PreviewError, match="files"):
        f.delete("/img/cap.png")


def test_statestore_methods_are_in_memory_now():
    """StateStore moved from preview → production in v0.4 (NW-E).

    Chip-side runtime is NVS-backed (gateway-esp/.../handlers/state.rs).
    The Python class is the local sandbox — in-memory only — so methods
    must succeed without raising PreviewError. Pinned here so a future
    refactor doesn't accidentally re-introduce the raise.
    """
    s = state("8MB")
    assert isinstance(s, StateStore)
    assert s.get("counter") is None
    s.set("counter", 1)
    assert s.get("counter") == 1
    n = s.increment("counter")
    assert n == 2
    assert s.get("counter") == 2
    s.delete("counter")
    assert s.get("counter") is None
    s.set("a", 1)
    s.set("b", 2)
    s.clear()
    assert s.get("a") is None and s.get("b") is None


def test_preview_error_subclasses_notimplementederror():
    """PreviewError must remain a subclass of NotImplementedError so
    user code that catches NIE keeps working when storage moves from
    preview → real impl."""
    assert issubclass(PreviewError, NotImplementedError)


def test_error_message_points_at_tracking_issue():
    """The error message must include the gateway-linux tracking
    issue URL so the user knows where to follow progress instead of
    filing a duplicate bug."""
    with pytest.raises(PreviewError) as exc:
        data("64MB").write("k", 1.0)
    assert "github.com/scadable/gateway-linux/issues" in str(exc.value)
