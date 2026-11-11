from __future__ import annotations

import ctypes
from types import SimpleNamespace

import pytest

from jarvis.email import EmailError
from jarvis.email.gmail_credentials import WindowsGmailCredentials, _Credential


class Native:
    def __init__(self, store):
        self.store = store
        self.value = None
        self.read_error = 1168
        self.write_ok = True
        self.delete_ok = True
        self.item = None
        self.frees = 0
        self.buffer = None

    def CredReadW(self, target, kind, flags, out):
        assert target == self.store.target and kind == 1 and flags == 0
        if self.value is None:
            return False
        self.buffer = (ctypes.c_ubyte * len(self.value)).from_buffer_copy(self.value)
        item = self.item or _Credential()
        if self.item is None:
            item.Type, item.Persist = 1, 2
            item.TargetName, item.UserName = target, "JARVIS Gmail"
            item.CredentialBlob, item.CredentialBlobSize = self.buffer, len(self.value)
        self.item_keepalive = item
        ctypes.cast(out, ctypes.POINTER(ctypes.POINTER(_Credential)))[0] = ctypes.pointer(item)
        return True

    def CredWriteW(self, pointer, flags):
        assert flags == 0
        self.written = ctypes.cast(pointer, ctypes.POINTER(_Credential)).contents
        self.written_buffer = self.written.CredentialBlob
        self.value = ctypes.string_at(self.written.CredentialBlob, self.written.CredentialBlobSize)
        return self.write_ok

    def CredFree(self, _):
        self.frees += 1

    def CredDeleteW(self, target, kind, flags):
        assert target == self.store.target and kind == 1 and flags == 0
        self.value = None
        return self.delete_ok


@pytest.fixture
def native(monkeypatch):
    store = WindowsGmailCredentials("synthetic@gmail.com", "synthetic-client")
    api = Native(store)
    state = SimpleNamespace(mutex=1, wait=0, released=0, closed=0)

    def release(_):
        state.released += 1

    def close(_):
        state.closed += 1

    kernel = SimpleNamespace(
        CreateMutexW=lambda *_: state.mutex,
        WaitForSingleObject=lambda *_: state.wait,
        ReleaseMutex=release,
        CloseHandle=close,
    )
    monkeypatch.setattr(store, "_api", lambda: (api, kernel))
    monkeypatch.setattr(ctypes, "get_last_error", lambda: api.read_error, raising=False)
    return store, api, state


@pytest.mark.parametrize("operation", ["read", "create", "delete"])
def test_native_failures_are_fixed_and_handles_released(native, operation):
    store, api, state = native
    api.read_error, api.write_ok, api.delete_ok = 5, False, False
    with pytest.raises(EmailError, match="gmail_store_unavailable"):
        getattr(store, operation)(b"synthetic") if operation == "create" else getattr(
            store, operation
        )()
    assert state.released == 1 and state.closed == 1


def test_write_failure_clears_native_buffer(native, monkeypatch):
    store, api, state = native
    observed = []
    memset = ctypes.memset

    def clear(buffer, value, size):
        memset(buffer, value, size)
        observed.append(ctypes.string_at(buffer, size))

    monkeypatch.setattr(ctypes, "memset", clear)
    api.write_ok = False
    with pytest.raises(EmailError, match="gmail_store_unavailable"):
        store.create(b"synthetic")
    assert observed == [b"\0" * len(b"synthetic")]
    assert state.released == state.closed == 1


@pytest.mark.parametrize("value", [b"", b"x" * 2561, "plaintext", None])
def test_store_invalid_size_or_type_never_writes(native, value):
    store, api, state = native
    with pytest.raises(EmailError, match="gmail_store_invalid"):
        store.create(value)
    assert api.value is None and state.closed == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("Type", 2),
        ("TargetName", "wrong"),
        ("Persist", 3),
        ("UserName", "wrong"),
        ("CredentialBlobSize", 2561),
        ("CredentialBlobSize", 0),
        ("CredentialBlob", None),
    ],
)
def test_invalid_native_record_is_freed_and_denied(native, field, value):
    store, api, state = native
    api.value = b"synthetic"
    item = _Credential()
    item.Type, item.Persist = 1, 2
    item.TargetName, item.UserName = store.target, "JARVIS Gmail"
    buffer = (ctypes.c_ubyte * 9)(*b"synthetic")
    item.CredentialBlob, item.CredentialBlobSize = buffer, 9
    setattr(item, field, value)
    api.item = item
    with pytest.raises(EmailError, match="gmail_store_invalid"):
        store.read()
    assert api.frees == 1 and state.closed == state.released == 1


@pytest.mark.parametrize(
    "mutex,wait,code",
    [
        (0, 0, "gmail_store_unavailable"),
        (1, 258, "gmail_store_busy"),
        (1, 0xFFFFFFFF, "gmail_store_busy"),
    ],
)
def test_mutex_failures_never_access_credential(native, mutex, wait, code):
    store, api, state = native
    state.mutex, state.wait = mutex, wait
    with pytest.raises(EmailError, match=code):
        store.read()
    assert state.released == 0 and api.frees == 0
    assert state.closed == bool(mutex)


def test_abandoned_mutex_missing_delete_and_nonwindows(native, monkeypatch):
    store, api, state = native
    state.wait = 0x80
    assert store.read() is None
    api.delete_ok = False
    store.delete()
    assert state.released == state.closed == 2
    import jarvis.email.gmail_credentials as module

    monkeypatch.setattr(module.os, "name", "posix")
    with pytest.raises(EmailError, match="gmail_windows_required"):
        WindowsGmailCredentials("synthetic@gmail.com", "synthetic-client").read()
