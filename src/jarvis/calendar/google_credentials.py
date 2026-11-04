"""Per-user Windows Credential Manager. No enumeration, roaming or plaintext fallback."""

from __future__ import annotations

import ctypes
import hashlib
import os
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes
from typing import Any

from .google import GOOGLE_CALENDAR_SCOPES, _account
from .models import CalendarError


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class WindowsGoogleCalendarCredentials:
    """One exact account/client target; construction does not access credentials."""

    def __init__(self, account: str, client_id: str) -> None:
        account = _account(account)
        binding = "\0".join((account, client_id, "primary", *sorted(GOOGLE_CALENDAR_SCOPES)))
        fingerprint = hashlib.sha256(binding.encode()).hexdigest()
        self.target = f"JARVIS/Calendar/Google/v1/{fingerprint}"

    def _api(self) -> tuple[Any, Any]:
        if os.name != "nt":
            raise CalendarError("calendar_windows_required")
        api = ctypes.WinDLL("advapi32", use_last_error=True)
        pointer = ctypes.POINTER(_Credential)
        api.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(pointer),
        ]
        api.CredReadW.restype = wintypes.BOOL
        api.CredWriteW.argtypes = [pointer, wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        api.CredDeleteW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        api.CredFree.restype = None
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
        kernel.ReleaseMutex.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        return api, kernel

    @contextmanager
    def _locked(self) -> Iterator[Any]:
        api, kernel = self._api()
        mutex = kernel.CreateMutexW(None, False, "Local\\" + self.target.replace("/", "_"))
        if not mutex:
            raise CalendarError("calendar_store_unavailable")
        owned = False
        try:
            # Nonblocking: another foreground process owns this exact target. Never queue writes.
            result = kernel.WaitForSingleObject(mutex, 0)
            owned = result in {0, 0x80}
            if not owned:
                raise CalendarError("calendar_store_busy")
            yield api
        finally:
            if owned:
                kernel.ReleaseMutex(mutex)
            kernel.CloseHandle(mutex)

    def _read(self, api: Any) -> bytes | None:
        pointer = ctypes.POINTER(_Credential)()
        if not api.CredReadW(self.target, 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168:
                return None
            raise CalendarError("calendar_store_unavailable")
        try:
            item = pointer.contents
            if (
                item.Type != 1
                or item.TargetName != self.target
                or item.Persist != 2
                or item.UserName != "JARVIS Calendar"
                or not item.CredentialBlob
                or not 1 <= item.CredentialBlobSize <= 2560
            ):
                raise CalendarError("calendar_store_invalid")
            return ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize)
        finally:
            api.CredFree(pointer)

    def read(self) -> bytes | None:
        with self._locked() as api:
            return self._read(api)

    def create(self, value: bytes) -> None:
        if not isinstance(value, bytes) or not 1 <= len(value) <= 2560:
            raise CalendarError("calendar_store_invalid")
        with self._locked() as api:
            if self._read(api) is not None:
                raise CalendarError("calendar_credential_exists")
            buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
            item = _Credential()
            item.Type = 1
            item.TargetName = self.target
            item.UserName = "JARVIS Calendar"
            item.Persist = (
                2  # CRED_PERSIST_LOCAL_MACHINE: same user, same Windows host; no roaming.
            )
            item.CredentialBlobSize = len(value)
            item.CredentialBlob = buffer
            try:
                if not api.CredWriteW(ctypes.byref(item), 0):
                    raise CalendarError("calendar_store_unavailable")
            finally:
                ctypes.memset(buffer, 0, len(value))

    def delete(self) -> None:
        """Caller must obtain exact local-token deletion confirmation. Does not revoke Google."""
        with self._locked() as api:
            if not api.CredDeleteW(self.target, 1, 0) and ctypes.get_last_error() != 1168:
                raise CalendarError("calendar_store_unavailable")
