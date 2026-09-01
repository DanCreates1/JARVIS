"""Bounded Unicode clipboard primitives with postcondition and guarded rollback."""

from __future__ import annotations

import ctypes
import hashlib
import os
import threading
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any, Final, Protocol

from .windows import UnsupportedPlatformError, WindowsPrimitiveError, require_non_elevated_process

_IS_WINDOWS: Final = os.name == "nt"
_CF_TEXT: Final = 1
_CF_OEMTEXT: Final = 7
_CF_UNICODETEXT: Final = 13
_CF_LOCALE: Final = 16
_TEXT_FORMATS: Final = frozenset({_CF_TEXT, _CF_OEMTEXT, _CF_UNICODETEXT, _CF_LOCALE})
_GMEM_MOVEABLE: Final = 0x0002
_DEFAULT_MAX_BYTES: Final = 8 * 1024
_MAX_FORMATS: Final = 32


class ClipboardError(WindowsPrimitiveError):
    """Clipboard access, bound, or verification failure."""


class ClipboardChangedError(ClipboardError):
    """Rollback refused because another application changed the clipboard."""


@dataclass(frozen=True, slots=True)
class ClipboardSnapshot:
    sequence: int
    text: str | None
    text_sha256: str | None
    utf16_bytes: int
    formats: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ClipboardMutationReceipt:
    before_sequence: int
    after_sequence: int
    before_sha256: str | None
    after_sha256: str
    utf16_bytes: int
    changed: bool
    verified: bool


@dataclass(frozen=True, slots=True)
class ClipboardRollbackReceipt:
    before_sequence: int
    after_sequence: int
    restored_sha256: str | None
    verified: bool


class _ClipboardBackend(Protocol):
    def snapshot(self, *, max_bytes: int) -> ClipboardSnapshot: ...

    def replace_text(self, text: str | None) -> None: ...


_user32: Any | None = None
_kernel32: Any | None = None
if _IS_WINDOWS:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def _configure_win32() -> None:
    if not _IS_WINDOWS:
        return
    assert _user32 is not None and _kernel32 is not None
    _user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        wintypes.LPVOID,
    ]
    _user32.CreateWindowExW.restype = wintypes.HWND
    _user32.DestroyWindow.argtypes = [wintypes.HWND]
    _user32.DestroyWindow.restype = wintypes.BOOL
    _user32.OpenClipboard.argtypes = [wintypes.HWND]
    _user32.OpenClipboard.restype = wintypes.BOOL
    _user32.CloseClipboard.argtypes = []
    _user32.CloseClipboard.restype = wintypes.BOOL
    _user32.EmptyClipboard.argtypes = []
    _user32.EmptyClipboard.restype = wintypes.BOOL
    _user32.GetClipboardData.argtypes = [wintypes.UINT]
    _user32.GetClipboardData.restype = wintypes.HANDLE
    _user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    _user32.SetClipboardData.restype = wintypes.HANDLE
    _user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    _user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    _user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
    _user32.EnumClipboardFormats.restype = wintypes.UINT
    _user32.GetClipboardSequenceNumber.argtypes = []
    _user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
    _kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    _kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    _kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalLock.restype = wintypes.LPVOID
    _kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalUnlock.restype = wintypes.BOOL
    _kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalSize.restype = ctypes.c_size_t
    _kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    _kernel32.GlobalFree.restype = wintypes.HGLOBAL


_configure_win32()


def _win_error(operation: str) -> OSError:
    code = ctypes.get_last_error()
    return OSError(code, f"{operation} failed: {ctypes.FormatError(code).strip()}")


class _Win32ClipboardBackend:
    def snapshot(self, *, max_bytes: int) -> ClipboardSnapshot:
        self._require_windows()
        assert _user32 is not None and _kernel32 is not None
        window = self._create_window()
        try:
            if not _user32.OpenClipboard(window):
                raise _win_error("OpenClipboard")
            try:
                sequence = int(_user32.GetClipboardSequenceNumber())
                formats = self._formats()
                text: str | None = None
                if _user32.IsClipboardFormatAvailable(_CF_UNICODETEXT):
                    handle = _user32.GetClipboardData(_CF_UNICODETEXT)
                    if not handle:
                        raise _win_error("GetClipboardData(CF_UNICODETEXT)")
                    size = int(_kernel32.GlobalSize(handle))
                    if size <= 0 or size > max_bytes + 2:
                        raise ClipboardError("clipboard Unicode text exceeds the configured limit")
                    pointer = _kernel32.GlobalLock(handle)
                    if not pointer:
                        raise _win_error("GlobalLock(clipboard)")
                    try:
                        payload = ctypes.string_at(pointer, size)
                    finally:
                        _kernel32.GlobalUnlock(handle)
                    try:
                        text = _decode_clipboard_payload(payload)
                    except UnicodeError as exc:
                        raise ClipboardError("clipboard Unicode text is malformed") from exc
                encoded = _encode_text(text) if text is not None else b""
                return ClipboardSnapshot(
                    sequence=sequence,
                    text=text,
                    text_sha256=_text_digest(text),
                    utf16_bytes=len(encoded),
                    formats=formats,
                )
            finally:
                _user32.CloseClipboard()
        finally:
            _user32.DestroyWindow(window)

    def replace_text(self, text: str | None) -> None:
        self._require_windows()
        assert _user32 is not None and _kernel32 is not None
        allocation: int | None = None
        if text is not None:
            payload = _encode_text(text) + b"\x00\x00"
            raw_handle = _kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(payload))
            if not raw_handle:
                raise _win_error("GlobalAlloc(clipboard)")
            allocation = int(raw_handle)
            pointer = _kernel32.GlobalLock(allocation)
            if not pointer:
                _kernel32.GlobalFree(allocation)
                raise _win_error("GlobalLock(clipboard allocation)")
            try:
                ctypes.memmove(pointer, payload, len(payload))
            finally:
                _kernel32.GlobalUnlock(allocation)
        window = self._create_window()
        try:
            if not _user32.OpenClipboard(window):
                raise _win_error("OpenClipboard")
            try:
                if not _user32.EmptyClipboard():
                    raise _win_error("EmptyClipboard")
                if allocation is not None:
                    if not _user32.SetClipboardData(_CF_UNICODETEXT, allocation):
                        raise _win_error("SetClipboardData(CF_UNICODETEXT)")
                    allocation = None
            finally:
                _user32.CloseClipboard()
        finally:
            _user32.DestroyWindow(window)
            if allocation is not None:
                _kernel32.GlobalFree(allocation)

    @staticmethod
    def _require_windows() -> None:
        if not _IS_WINDOWS:
            raise UnsupportedPlatformError("Windows clipboard is unavailable on this platform")

    @staticmethod
    def _create_window() -> int:
        assert _user32 is not None
        window = _user32.CreateWindowExW(
            0,
            "STATIC",
            "JARVIS Clipboard Broker",
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            None,
            None,
        )
        if not window:
            raise _win_error("CreateWindowExW(clipboard owner)")
        return int(window)

    @staticmethod
    def _formats() -> tuple[int, ...]:
        assert _user32 is not None
        values: list[int] = []
        current = 0
        while len(values) < _MAX_FORMATS:
            ctypes.set_last_error(0)
            current = int(_user32.EnumClipboardFormats(current))
            if current == 0:
                if ctypes.get_last_error() != 0:
                    raise _win_error("EnumClipboardFormats")
                break
            values.append(current)
        if len(values) == _MAX_FORMATS:
            raise ClipboardError("clipboard exposes too many formats for safe replacement")
        return tuple(values)


_BACKEND: _ClipboardBackend = _Win32ClipboardBackend()
_LOCK = threading.Lock()


def get_clipboard_snapshot(*, max_bytes: int = _DEFAULT_MAX_BYTES) -> ClipboardSnapshot:
    """Read one bounded Unicode snapshot; callers must treat text as sensitive."""
    _validate_max_bytes(max_bytes)
    with _LOCK:
        return _BACKEND.snapshot(max_bytes=max_bytes)


def set_clipboard_text(
    text: str,
    *,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> ClipboardMutationReceipt:
    """Replace bounded text after non-elevated guard and verify exact readback."""
    _validate_text(text, max_bytes=max_bytes)
    require_non_elevated_process()
    with _LOCK:
        before = _BACKEND.snapshot(max_bytes=max_bytes)
        unsupported = set(before.formats).difference(_TEXT_FORMATS)
        if unsupported:
            raise ClipboardError("clipboard contains non-text formats that cannot be rolled back")
        if before.formats and (_CF_UNICODETEXT not in before.formats or before.text is None):
            raise ClipboardError(
                "nonempty text clipboard lacks materialized Unicode text for rollback"
            )
        expected = _text_digest(text)
        assert expected is not None
        if before.text == text:
            return ClipboardMutationReceipt(
                before_sequence=before.sequence,
                after_sequence=before.sequence,
                before_sha256=before.text_sha256,
                after_sha256=expected,
                utf16_bytes=len(_encode_text(text)),
                changed=False,
                verified=True,
            )
        try:
            _BACKEND.replace_text(text)
            after = _BACKEND.snapshot(max_bytes=max_bytes)
        except BaseException:
            _restore_best_effort(before.text)
            raise
        if after.text != text or after.text_sha256 != expected:
            _restore_best_effort(before.text)
            raise ClipboardError(
                "clipboard postcondition mismatch; prior text restoration attempted"
            )
        return ClipboardMutationReceipt(
            before_sequence=before.sequence,
            after_sequence=after.sequence,
            before_sha256=before.text_sha256,
            after_sha256=expected,
            utf16_bytes=len(_encode_text(text)),
            changed=True,
            verified=True,
        )


def rollback_clipboard_text(
    previous_text: str | None,
    *,
    expected_current_sha256: str,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> ClipboardRollbackReceipt:
    """Restore text only while clipboard still matches this action's postcondition."""
    if previous_text is not None:
        _validate_text(previous_text, max_bytes=max_bytes)
    _validate_digest(expected_current_sha256)
    require_non_elevated_process()
    with _LOCK:
        current = _BACKEND.snapshot(max_bytes=max_bytes)
        if current.text_sha256 != expected_current_sha256:
            raise ClipboardChangedError("clipboard changed after action; rollback refused")
        _BACKEND.replace_text(previous_text)
        restored = _BACKEND.snapshot(max_bytes=max_bytes)
        if restored.text != previous_text:
            raise ClipboardError("clipboard rollback postcondition mismatch")
        return ClipboardRollbackReceipt(
            before_sequence=current.sequence,
            after_sequence=restored.sequence,
            restored_sha256=restored.text_sha256,
            verified=True,
        )


def _restore_best_effort(text: str | None) -> None:
    try:
        _BACKEND.replace_text(text)
    except BaseException:
        return


def _validate_max_bytes(value: int) -> None:
    if not 1 <= value <= 64 * 1024:
        raise ValueError("clipboard max_bytes must be in [1, 65536]")


def _validate_text(value: str, *, max_bytes: int) -> None:
    _validate_max_bytes(max_bytes)
    if "\x00" in value:
        raise ValueError("clipboard text cannot contain NUL")
    try:
        encoded = _encode_text(value)
    except UnicodeError as exc:
        raise ValueError("clipboard text must be valid Unicode") from exc
    if len(encoded) > max_bytes:
        raise ValueError("clipboard text exceeds the configured UTF-16 byte limit")


def _encode_text(value: str) -> bytes:
    return value.encode("utf-16-le", errors="strict")


def _decode_clipboard_payload(payload: bytes) -> str:
    terminator = next(
        (
            offset
            for offset in range(0, max(0, len(payload) - 1), 2)
            if payload[offset : offset + 2] == b"\x00\x00"
        ),
        len(payload),
    )
    return payload[:terminator].decode("utf-16-le", errors="strict")


def _text_digest(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(_encode_text(value)).hexdigest()


def _validate_digest(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("expected clipboard SHA-256 is invalid")
