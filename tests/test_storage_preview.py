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


def test_statestore_methods_raise_preview_error():
    s = state("8MB")
    assert isinstance(s, StateStore)
    with pytest.raises(PreviewError, match="state"):
        s.get("counter")
    with pytest.raises(PreviewError, match="state"):
        s.set("counter", 1)
    with pytest.raises(PreviewError, match="state"):
        s.increment("counter")
    with pytest.raises(PreviewError, match="state"):
        s.clear()


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
