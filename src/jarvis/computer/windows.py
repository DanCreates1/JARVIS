"""Narrow Windows 11 primitives for the Phase 3 action broker.

The module deliberately contains no policy, approval, persistence, or model-facing
code.  Callers must still obtain a typed, one-use grant before invoking a mutating
primitive.  Importing this module is safe on non-Windows hosts; invoking a Win32
primitive there fails closed.
"""

from __future__ import annotations

import ctypes
import hashlib
import hmac
import os
import re
import subprocess
from collections.abc import Callable, Iterable, Mapping, Sequence
from ctypes import wintypes
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, ClassVar, Final

_IS_WINDOWS: Final = os.name == "nt"

_kernel32: Any | None = None
_advapi32: Any | None = None
_winspool: Any | None = None
_user32: Any | None = None
if _IS_WINDOWS:
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)
    _user32 = ctypes.WinDLL("user32", use_last_error=True)


class WindowsPrimitiveError(RuntimeError):
    """Base failure for a Windows primitive."""


class UnsupportedPlatformError(WindowsPrimitiveError):
    """Raised when a Windows primitive is invoked on another platform."""


class ElevatedProcessError(WindowsPrimitiveError):
    """Raised when a side effect is attempted from an elevated process."""


class UnsafePathError(WindowsPrimitiveError):
    """Raised when a path cannot satisfy the local allowlist invariant."""


class IdentityMismatchError(WindowsPrimitiveError):
    """Raised when a path no longer names its enrolled object."""


class DestinationExistsError(WindowsPrimitiveError):
    """Raised rather than replacing an existing destination."""


class RenamePostconditionError(IdentityMismatchError):
    """A handle-bound rename completed but its final state needs reconciliation."""

    def __init__(self, message: str, recovery: RenameReceipt) -> None:
        super().__init__(message)
        self.recovery = recovery


_INVALID_HANDLE_VALUE: Final = ctypes.c_void_p(-1).value
_DELETE: Final = 0x00010000
_FILE_READ_ATTRIBUTES: Final = 0x0080
_FILE_TRAVERSE: Final = 0x0020
_GENERIC_READ: Final = 0x80000000
_FILE_SHARE_READ: Final = 0x00000001
_FILE_SHARE_WRITE: Final = 0x00000002
_FILE_SHARE_DELETE: Final = 0x00000004
_OPEN_EXISTING: Final = 3
_FILE_ATTRIBUTE_DIRECTORY: Final = 0x00000010
_FILE_ATTRIBUTE_REPARSE_POINT: Final = 0x00000400
_FILE_ATTRIBUTE_OFFLINE: Final = 0x00001000
_FILE_ATTRIBUTE_RECALL_ON_OPEN: Final = 0x00040000
_FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS: Final = 0x00400000
_FILE_FLAG_BACKUP_SEMANTICS: Final = 0x02000000
_FILE_FLAG_SEQUENTIAL_SCAN: Final = 0x08000000
_IO_REPARSE_TAG_NAME_SURROGATE: Final = 0x20000000
_FILE_ID_INFO_CLASS: Final = 18
_FILE_RENAME_INFO_CLASS: Final = 3
_FILE_NAME_NORMALIZED: Final = 0x0
_VOLUME_NAME_GUID: Final = 0x1
_DRIVE_FIXED: Final = 3
_TOKEN_QUERY: Final = 0x0008
_TOKEN_USER_CLASS: Final = 1
_TOKEN_ELEVATION_CLASS: Final = 20
_PROCESS_QUERY_LIMITED_INFORMATION: Final = 0x1000
_RRF_RT_REG_SZ: Final = 0x00000002
_ERROR_SUCCESS: Final = 0
_ERROR_INSUFFICIENT_BUFFER: Final = 122
_ERROR_NOT_SAME_DEVICE: Final = 17
_ERROR_FILE_EXISTS: Final = 80
_ERROR_ALREADY_EXISTS: Final = 183
_PRINTER_ENUM_LOCAL: Final = 0x00000002
_PRINTER_ATTRIBUTE_NETWORK: Final = 0x00000010
_INPUT_KEYBOARD: Final = 1
_KEYEVENTF_KEYUP: Final = 0x0002

_SAFE_CHILD_ENVIRONMENT: Final = (
    "SystemRoot",
    "WINDIR",
    "SystemDrive",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "LOCALAPPDATA",
    "APPDATA",
    "PROGRAMDATA",
)
_RESERVED_BASENAMES: Final = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)
_DRIVE_PATTERN: Final = re.compile(r"[A-Za-z]:")


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", _FILETIME),
        ("ftLastAccessTime", _FILETIME),
        ("ftLastWriteTime", _FILETIME),
        ("dwVolumeSerialNumber", wintypes.DWORD),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("nNumberOfLinks", wintypes.DWORD),
        ("nFileIndexHigh", wintypes.DWORD),
        ("nFileIndexLow", wintypes.DWORD),
    ]


class _FILE_ID_128(ctypes.Structure):
    _fields_ = [("identifier", ctypes.c_ubyte * 16)]


class _FILE_ID_INFO(ctypes.Structure):
    _fields_ = [("volume_serial_number", ctypes.c_ulonglong), ("file_id", _FILE_ID_128)]


class _FILE_RENAME_INFO(ctypes.Structure):
    _fields_ = [
        ("flags", wintypes.DWORD),
        ("root_directory", wintypes.HANDLE),
        ("file_name_length", wintypes.DWORD),
        ("file_name", wintypes.WCHAR * 1),
    ]


class _TOKEN_ELEVATION(ctypes.Structure):
    _fields_ = [("token_is_elevated", wintypes.DWORD)]


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("sid", wintypes.LPVOID), ("attributes", wintypes.DWORD)]


class _TOKEN_USER(ctypes.Structure):
    _fields_ = [("user", _SID_AND_ATTRIBUTES)]


class _PRINTER_INFO_4W(ctypes.Structure):
    _fields_ = [
        ("printer_name", wintypes.LPWSTR),
        ("server_name", wintypes.LPWSTR),
        ("attributes", wintypes.DWORD),
    ]


class _PRINTER_INFO_6(ctypes.Structure):
    _fields_ = [("status", wintypes.DWORD)]


_ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("virtual_key", wintypes.WORD),
        ("scan_code", wintypes.WORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra_info", _ULONG_PTR),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouse_data", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("extra_info", _ULONG_PTR),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("message", wintypes.DWORD),
        ("parameter_low", wintypes.WORD),
        ("parameter_high", wintypes.WORD),
    ]


class _INPUT_VALUE(ctypes.Union):
    _fields_: ClassVar[list[tuple[str, Any]]] = [
        ("mouse", _MOUSEINPUT),
        ("keyboard", _KEYBDINPUT),
        ("hardware", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", wintypes.DWORD), ("value", _INPUT_VALUE)]


def _configure_win32() -> None:
    if not _IS_WINDOWS:
        return
    assert _kernel32 is not None
    assert _advapi32 is not None
    assert _winspool is not None
    assert _user32 is not None

    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_BY_HANDLE_FILE_INFORMATION),
    ]
    _kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
    _kernel32.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    _kernel32.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _kernel32.SetFileInformationByHandle.restype = wintypes.BOOL
    _kernel32.GetFinalPathNameByHandleW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    _kernel32.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    _kernel32.ReadFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    _kernel32.ReadFile.restype = wintypes.BOOL
    _kernel32.SetFilePointerEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_longlong,
        ctypes.POINTER(ctypes.c_longlong),
        wintypes.DWORD,
    ]
    _kernel32.SetFilePointerEx.restype = wintypes.BOOL
    _kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    _kernel32.GetDriveTypeW.restype = wintypes.UINT
    _kernel32.GetCurrentProcess.argtypes = []
    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL

    _advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    _advapi32.OpenProcessToken.restype = wintypes.BOOL
    _advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _advapi32.GetTokenInformation.restype = wintypes.BOOL
    _advapi32.IsValidSid.argtypes = [wintypes.LPVOID]
    _advapi32.IsValidSid.restype = wintypes.BOOL
    _advapi32.GetLengthSid.argtypes = [wintypes.LPVOID]
    _advapi32.GetLengthSid.restype = wintypes.DWORD
    _advapi32.RegGetValueW.argtypes = [
        wintypes.HKEY,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _advapi32.RegGetValueW.restype = wintypes.LONG

    _winspool.EnumPrintersW.argtypes = [
        wintypes.DWORD,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.LPBYTE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    _winspool.EnumPrintersW.restype = wintypes.BOOL
    _winspool.OpenPrinterW.argtypes = [
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.LPVOID,
    ]
    _winspool.OpenPrinterW.restype = wintypes.BOOL
    _winspool.GetPrinterW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPBYTE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _winspool.GetPrinterW.restype = wintypes.BOOL
    _winspool.ClosePrinter.argtypes = [wintypes.HANDLE]
    _winspool.ClosePrinter.restype = wintypes.BOOL

    _user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
    _user32.SendInput.restype = wintypes.UINT


_configure_win32()


def _require_windows() -> None:
    if not _IS_WINDOWS:
        raise UnsupportedPlatformError("Windows primitive is unavailable on this platform")


def _win_error(operation: str, error: int | None = None) -> OSError:
    code = ctypes.get_last_error() if error is None else error
    return OSError(code, f"{operation} failed: {ctypes.FormatError(code).strip()}")


def _close_handle(handle: int) -> None:
    assert _kernel32 is not None
    if handle:
        _kernel32.CloseHandle(handle)


def _validate_local_absolute_path(value: str | os.PathLike[str]) -> Path:
    _require_windows()
    raw = os.fspath(value)
    if not raw or len(raw) > 32_000 or "\x00" in raw:
        raise UnsafePathError("path is empty, too long, or contains NUL")
    normalized = raw.replace("/", "\\")
    if normalized.startswith("\\\\"):
        raise UnsafePathError("UNC, device, and extended paths are not accepted")
    candidate = Path(normalized)
    if (
        not candidate.is_absolute()
        or not _DRIVE_PATTERN.fullmatch(candidate.drive)
        or candidate.anchor.casefold() != f"{candidate.drive}\\".casefold()
    ):
        raise UnsafePathError("path must be an absolute drive-qualified local path")
    for component in candidate.parts[1:]:
        if component in {".", ".."}:
            raise UnsafePathError("relative path components are not accepted")
        if (
            not component
            or component.endswith((" ", "."))
            or any(ord(character) < 32 for character in component)
            or any(character in '<>:"/\\|?*' for character in component)
        ):
            raise UnsafePathError("path contains a forbidden Windows name")
        basename = component.split(".", maxsplit=1)[0].upper()
        if basename in _RESERVED_BASENAMES:
            raise UnsafePathError("path contains a reserved Windows device name")
    assert _kernel32 is not None
    if int(_kernel32.GetDriveTypeW(candidate.anchor)) != _DRIVE_FIXED:
        raise UnsafePathError("only fixed local volumes are accepted")
    return candidate


def _reject_name_surrogate_components(path: Path) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current /= component
        try:
            info = os.lstat(current)
        except FileNotFoundError as exc:
            raise UnsafePathError(f"path component does not exist: {current}") from exc
        attributes = int(getattr(info, "st_file_attributes", 0))
        tag = int(getattr(info, "st_reparse_tag", 0))
        if attributes & _FILE_ATTRIBUTE_REPARSE_POINT and tag & _IO_REPARSE_TAG_NAME_SURROGATE:
            raise UnsafePathError(f"name-surrogate reparse point is not accepted: {current}")


def _create_file_handle(
    path: Path,
    *,
    desired_access: int,
    share_mode: int,
    flags: int,
) -> int:
    assert _kernel32 is not None
    handle = _kernel32.CreateFileW(
        str(path),
        desired_access,
        share_mode,
        None,
        _OPEN_EXISTING,
        flags,
        None,
    )
    if handle in {None, 0, _INVALID_HANDLE_VALUE}:
        raise _win_error(f"CreateFileW({path})")
    return int(handle)


def _open_handle(path: Path, *, hash_content: bool, lock_path: bool) -> int:
    desired_access = _GENERIC_READ if hash_content else _FILE_READ_ATTRIBUTES
    share_mode = _FILE_SHARE_READ
    if not lock_path:
        share_mode |= _FILE_SHARE_WRITE | _FILE_SHARE_DELETE
    flags = _FILE_FLAG_BACKUP_SEMANTICS
    if hash_content:
        flags |= _FILE_FLAG_SEQUENTIAL_SCAN
    return _create_file_handle(
        path,
        desired_access=desired_access,
        share_mode=share_mode,
        flags=flags,
    )


def _final_path_for_handle(handle: int) -> str:
    assert _kernel32 is not None
    required = int(
        _kernel32.GetFinalPathNameByHandleW(
            handle,
            None,
            0,
            _FILE_NAME_NORMALIZED | _VOLUME_NAME_GUID,
        )
    )
    if required == 0:
        raise _win_error("GetFinalPathNameByHandleW")
    buffer = ctypes.create_unicode_buffer(required + 1)
    copied = int(
        _kernel32.GetFinalPathNameByHandleW(
            handle,
            buffer,
            len(buffer),
            _FILE_NAME_NORMALIZED | _VOLUME_NAME_GUID,
        )
    )
    if copied == 0 or copied >= len(buffer):
        raise _win_error("GetFinalPathNameByHandleW")
    return buffer.value


def _sha256_for_handle(handle: int) -> str:
    assert _kernel32 is not None
    if not _kernel32.SetFilePointerEx(handle, 0, None, 0):
        raise _win_error("SetFilePointerEx")
    digest = hashlib.sha256()
    buffer = ctypes.create_string_buffer(1024 * 1024)
    while True:
        read = wintypes.DWORD()
        if not _kernel32.ReadFile(handle, buffer, len(buffer), ctypes.byref(read), None):
            raise _win_error("ReadFile")
        if read.value == 0:
            break
        digest.update(buffer.raw[: read.value])
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class FileIdentity:
    """Stable object identity plus change-sensitive metadata."""

    path: Path
    final_path: str
    volume_serial: int
    file_id: str
    size: int
    modified_100ns: int
    link_count: int
    attributes: int
    sha256: str | None = None

    def same_object(self, other: FileIdentity) -> bool:
        return (self.volume_serial, self.file_id) == (other.volume_serial, other.file_id)

    def unchanged(self, other: FileIdentity) -> bool:
        return (
            self.same_object(other)
            and self.size == other.size
            and self.modified_100ns == other.modified_100ns
            and (self.sha256 is None or hmac.compare_digest(self.sha256, other.sha256 or ""))
        )


def _identity_for_handle(path: Path, handle: int, *, compute_sha256: bool) -> FileIdentity:
    assert _kernel32 is not None
    file_id = _FILE_ID_INFO()
    if not _kernel32.GetFileInformationByHandleEx(
        handle,
        _FILE_ID_INFO_CLASS,
        ctypes.byref(file_id),
        ctypes.sizeof(file_id),
    ):
        raise _win_error("GetFileInformationByHandleEx(FileIdInfo)")
    details = _BY_HANDLE_FILE_INFORMATION()
    if not _kernel32.GetFileInformationByHandle(handle, ctypes.byref(details)):
        raise _win_error("GetFileInformationByHandle")
    modified = (int(details.ftLastWriteTime.dwHighDateTime) << 32) | int(
        details.ftLastWriteTime.dwLowDateTime
    )
    size = (int(details.nFileSizeHigh) << 32) | int(details.nFileSizeLow)
    digest = _sha256_for_handle(handle) if compute_sha256 else None
    return FileIdentity(
        path=path,
        final_path=_final_path_for_handle(handle),
        volume_serial=int(file_id.volume_serial_number),
        file_id=bytes(file_id.file_id.identifier).hex(),
        size=size,
        modified_100ns=modified,
        link_count=int(details.nNumberOfLinks),
        attributes=int(details.dwFileAttributes),
        sha256=digest,
    )


def _probe_object(
    value: str | os.PathLike[str],
    *,
    expect_directory: bool,
    compute_sha256: bool = False,
    lock_path: bool = False,
) -> FileIdentity:
    candidate = _validate_local_absolute_path(value)
    _reject_name_surrogate_components(candidate)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise UnsafePathError(f"path cannot be resolved: {candidate}") from exc
    _reject_name_surrogate_components(candidate)
    handle = _open_handle(
        resolved,
        hash_content=compute_sha256,
        lock_path=lock_path,
    )
    try:
        identity = _identity_for_handle(resolved, handle, compute_sha256=compute_sha256)
    finally:
        _close_handle(handle)
    is_directory = bool(identity.attributes & _FILE_ATTRIBUTE_DIRECTORY)
    if is_directory != expect_directory:
        expected = "directory" if expect_directory else "regular file"
        raise UnsafePathError(f"path is not an expected {expected}: {candidate}")
    return identity


def _path_is_within(candidate: str, root: str) -> bool:
    normalized_candidate = candidate.rstrip("\\").casefold()
    normalized_root = root.rstrip("\\").casefold()
    return normalized_candidate == normalized_root or normalized_candidate.startswith(
        f"{normalized_root}\\"
    )


@dataclass(frozen=True, slots=True)
class _RootBinding:
    identity: FileIdentity


class AllowedRootGuard:
    """Validate existing files against fixed-volume, handle-bound roots."""

    def __init__(self, roots: Iterable[Path]) -> None:
        bindings = tuple(_RootBinding(_probe_object(root, expect_directory=True)) for root in roots)
        if not bindings:
            raise ValueError("at least one allowed root is required")
        self._roots = bindings

    @property
    def roots(self) -> tuple[Path, ...]:
        return tuple(binding.identity.path for binding in self._roots)

    def probe_existing_file(
        self,
        path: str | os.PathLike[str],
        *,
        compute_sha256: bool = False,
        for_mutation: bool = False,
    ) -> FileIdentity:
        identity = _probe_object(path, expect_directory=False, compute_sha256=compute_sha256)
        self._assert_inside_bound_root(identity)
        if for_mutation:
            if identity.link_count != 1:
                raise UnsafePathError("mutation of multiply-linked files is not accepted")
            if identity.attributes & (
                _FILE_ATTRIBUTE_OFFLINE
                | _FILE_ATTRIBUTE_RECALL_ON_OPEN
                | _FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
            ):
                raise UnsafePathError(
                    "mutation of offline or recall-on-access files is not accepted"
                )
        return identity

    def revalidate(self, expected: FileIdentity, *, for_mutation: bool = False) -> FileIdentity:
        current = self.probe_existing_file(
            expected.path,
            compute_sha256=expected.sha256 is not None,
            for_mutation=for_mutation,
        )
        if not expected.unchanged(current):
            raise IdentityMismatchError("file identity or approved content changed")
        return current

    def _assert_inside_bound_root(self, candidate: FileIdentity) -> None:
        for binding in self._roots:
            current_root = _probe_object(binding.identity.path, expect_directory=True)
            if (
                not binding.identity.same_object(current_root)
                or binding.identity.final_path.casefold() != current_root.final_path.casefold()
            ):
                raise IdentityMismatchError("allowed root identity changed")
            if candidate.volume_serial == current_root.volume_serial and _path_is_within(
                candidate.final_path, current_root.final_path
            ):
                return
        raise UnsafePathError("path is outside configured allowed roots")

    def _prepare_destination(self, path: str | os.PathLike[str]) -> tuple[Path, FileIdentity]:
        destination = _validate_local_absolute_path(path)
        if os.path.lexists(destination):
            raise DestinationExistsError(f"destination already exists: {destination}")
        parent = _probe_object(destination.parent, expect_directory=True)
        self._assert_inside_bound_root(parent)
        return destination, parent


@dataclass(frozen=True, slots=True)
class RenameReceipt:
    """Evidence needed for a collision-safe rollback attempt."""

    source: Path
    destination: Path
    identity: FileIdentity
    postcondition_verified: bool = True
    postcondition_error: str | None = None


@dataclass(slots=True)
class _PinnedObject:
    path: Path
    handle: int
    identity: FileIdentity

    def close(self) -> None:
        _close_handle(self.handle)
        self.handle = 0


RenameDispatchHook = Callable[[], None]


def _open_pinned_object(
    path: Path,
    *,
    expect_directory: bool,
    desired_access: int,
    share_mode: int,
) -> _PinnedObject:
    candidate = _validate_local_absolute_path(path)
    _reject_name_surrogate_components(candidate)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise UnsafePathError(f"path cannot be resolved: {candidate}") from exc
    _reject_name_surrogate_components(candidate)
    handle = _create_file_handle(
        resolved,
        desired_access=desired_access,
        share_mode=share_mode,
        flags=_FILE_FLAG_BACKUP_SEMANTICS,
    )
    try:
        identity = _identity_for_handle(resolved, handle, compute_sha256=False)
        is_directory = bool(identity.attributes & _FILE_ATTRIBUTE_DIRECTORY)
        if is_directory != expect_directory:
            expected = "directory" if expect_directory else "regular file"
            raise UnsafePathError(f"path is not an expected {expected}: {candidate}")
        if identity.attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
            raise UnsafePathError("reparse points are not accepted for handle-bound mutation")
        if not expect_directory:
            if identity.link_count != 1:
                raise UnsafePathError("mutation of multiply-linked files is not accepted")
            if identity.attributes & (
                _FILE_ATTRIBUTE_OFFLINE
                | _FILE_ATTRIBUTE_RECALL_ON_OPEN
                | _FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
            ):
                raise UnsafePathError(
                    "mutation of offline or recall-on-access files is not accepted"
                )
    except BaseException:
        _close_handle(handle)
        raise
    return _PinnedObject(path=resolved, handle=handle, identity=identity)


def _open_pinned_directory(path: Path) -> _PinnedObject:
    return _open_pinned_object(
        path,
        expect_directory=True,
        desired_access=_FILE_TRAVERSE | _FILE_READ_ATTRIBUTES,
        share_mode=_FILE_SHARE_READ | _FILE_SHARE_WRITE,
    )


def _open_pinned_rename_source(path: Path) -> _PinnedObject:
    return _open_pinned_object(
        path,
        expect_directory=False,
        desired_access=_DELETE | _FILE_READ_ATTRIBUTES,
        share_mode=_FILE_SHARE_READ,
    )


def _assert_stable_pin(pin: _PinnedObject) -> FileIdentity:
    current = _identity_for_handle(pin.path, pin.handle, compute_sha256=False)
    if (
        not pin.identity.same_object(current)
        or pin.identity.final_path.casefold() != current.final_path.casefold()
    ):
        raise IdentityMismatchError("pinned path identity changed")
    return current


def _pin_bound_root(
    guard: AllowedRootGuard,
    candidate: FileIdentity,
    pins: list[_PinnedObject],
) -> _PinnedObject:
    for binding in guard._roots:
        root = _open_pinned_directory(binding.identity.path)
        if (
            not binding.identity.same_object(root.identity)
            or binding.identity.final_path.casefold() != root.identity.final_path.casefold()
        ):
            root.close()
            raise IdentityMismatchError("allowed root identity changed")
        if candidate.volume_serial == root.identity.volume_serial and _path_is_within(
            candidate.final_path,
            root.identity.final_path,
        ):
            pins.append(root)
            return root
        root.close()
    raise UnsafePathError("path is outside configured allowed roots")


def _pin_directory_chain(
    root: _PinnedObject,
    target: Path,
    pins: list[_PinnedObject],
) -> _PinnedObject:
    try:
        relative = target.relative_to(root.identity.path)
    except ValueError as exc:
        raise UnsafePathError("directory path is outside its pinned allowed root") from exc
    current = root.identity.path
    last = root
    for component in relative.parts:
        current /= component
        last = _open_pinned_directory(current)
        if last.identity.volume_serial != root.identity.volume_serial or not _path_is_within(
            last.identity.final_path,
            root.identity.final_path,
        ):
            last.close()
            raise UnsafePathError("directory chain escaped its pinned allowed root")
        pins.append(last)
    return last


def _set_handle_name(source_handle: int, destination: Path) -> None:
    assert _kernel32 is not None
    target = _validate_local_absolute_path(destination)
    encoded = str(target).encode("utf-16-le", errors="strict")
    offset = _FILE_RENAME_INFO.file_name.offset
    buffer = ctypes.create_string_buffer(offset + len(encoded) + ctypes.sizeof(wintypes.WCHAR))
    information = _FILE_RENAME_INFO.from_buffer(buffer)
    information.flags = 0
    information.root_directory = None
    information.file_name_length = len(encoded)
    ctypes.memmove(ctypes.addressof(buffer) + offset, encoded, len(encoded))
    ctypes.set_last_error(0)
    if _kernel32.SetFileInformationByHandle(
        source_handle,
        _FILE_RENAME_INFO_CLASS,
        buffer,
        len(buffer),
    ):
        return
    error = ctypes.get_last_error()
    if error in {_ERROR_FILE_EXISTS, _ERROR_ALREADY_EXISTS}:
        raise DestinationExistsError("destination already exists")
    if error == _ERROR_NOT_SAME_DEVICE:
        raise UnsafePathError("cross-volume moves are not accepted")
    raise _win_error("SetFileInformationByHandle(FileRenameInfo)", error)


def _identity_at_expected_destination(
    before: FileIdentity,
    target: Path,
    final_path: str,
) -> FileIdentity:
    return FileIdentity(
        path=target,
        final_path=final_path,
        volume_serial=before.volume_serial,
        file_id=before.file_id,
        size=before.size,
        modified_100ns=before.modified_100ns,
        link_count=before.link_count,
        attributes=before.attributes,
        sha256=before.sha256,
    )


def _handle_bound_rename(
    guard: AllowedRootGuard,
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    expected: FileIdentity | None = None,
    before_dispatch: RenameDispatchHook | None = None,
) -> RenameReceipt:
    before = guard.probe_existing_file(source, for_mutation=True)
    if expected is not None and not expected.unchanged(before):
        raise IdentityMismatchError("file identity or approved content changed")
    target, target_parent = guard._prepare_destination(destination)
    source_parent = _probe_object(before.path.parent, expect_directory=True)
    guard._assert_inside_bound_root(source_parent)
    if before.volume_serial != target_parent.volume_serial:
        raise UnsafePathError("cross-volume moves are not accepted")

    pins: list[_PinnedObject] = []
    try:
        source_root = _pin_bound_root(guard, before, pins)
        target_root = _pin_bound_root(guard, target_parent, pins)
        pinned_source_parent = _pin_directory_chain(source_root, before.path.parent, pins)
        pinned_target_parent = _pin_directory_chain(target_root, target_parent.path, pins)
        if not source_parent.same_object(pinned_source_parent.identity):
            raise IdentityMismatchError("source parent identity changed")
        if not target_parent.same_object(pinned_target_parent.identity):
            raise IdentityMismatchError("destination parent identity changed")

        pinned_source = _open_pinned_rename_source(before.path)
        pins.append(pinned_source)
        if (
            not before.unchanged(pinned_source.identity)
            or before.final_path.casefold() != pinned_source.identity.final_path.casefold()
        ):
            raise IdentityMismatchError("source identity changed before handle-bound rename")

        if before_dispatch is not None:
            before_dispatch()

        for pin in pins[:-1]:
            _assert_stable_pin(pin)
        current_source = _assert_stable_pin(pinned_source)
        if not before.unchanged(current_source):
            raise IdentityMismatchError("source changed before handle-bound rename")
        current_target_parent = _assert_stable_pin(pinned_target_parent)
        if not target_parent.same_object(current_target_parent):
            raise IdentityMismatchError("destination parent changed before handle-bound rename")
        if os.path.lexists(target):
            raise DestinationExistsError(f"destination already exists: {target}")

        parent_final_path = current_target_parent.final_path.rstrip("\\")
        expected_final_path = f"{parent_final_path}\\{target.name}"
        _set_handle_name(pinned_source.handle, target)

        fallback = _identity_at_expected_destination(before, target, expected_final_path)
        try:
            after = _identity_for_handle(target, pinned_source.handle, compute_sha256=False)
            source_absent = not os.path.lexists(before.path)
        except (OSError, WindowsPrimitiveError):
            return RenameReceipt(
                source=before.path,
                destination=target,
                identity=fallback,
                postcondition_verified=False,
                postcondition_error="postcondition_probe_failed",
            )
        verified = (
            before.unchanged(after)
            and after.link_count == 1
            and not after.attributes
            & (
                _FILE_ATTRIBUTE_REPARSE_POINT
                | _FILE_ATTRIBUTE_OFFLINE
                | _FILE_ATTRIBUTE_RECALL_ON_OPEN
                | _FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS
            )
            and after.final_path.casefold() == expected_final_path.casefold()
            and source_absent
        )
        return RenameReceipt(
            source=before.path,
            destination=target,
            identity=after if after.same_object(before) else fallback,
            postcondition_verified=verified,
            postcondition_error=None if verified else "postcondition_mismatch",
        )
    finally:
        for pin in reversed(pins):
            pin.close()


def rename_file_same_volume(
    guard: AllowedRootGuard,
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    _before_dispatch: RenameDispatchHook | None = None,
) -> RenameReceipt:
    """Rename the exact open file into the exact open parent without replacement."""

    _require_non_elevated()
    return _handle_bound_rename(
        guard,
        source,
        destination,
        before_dispatch=_before_dispatch,
    )


def rollback_rename(
    guard: AllowedRootGuard,
    receipt: RenameReceipt,
    *,
    _before_dispatch: RenameDispatchHook | None = None,
) -> FileIdentity:
    """Rollback a rename only while both path and object identity remain unchanged."""

    _require_non_elevated()
    recovery = _handle_bound_rename(
        guard,
        receipt.destination,
        receipt.source,
        expected=receipt.identity,
        before_dispatch=_before_dispatch,
    )
    if not recovery.postcondition_verified:
        raise RenamePostconditionError(
            "rollback completed but its postcondition requires reconciliation",
            recovery,
        )
    return recovery.identity


def _read_token_state() -> tuple[bool, bytes]:
    _require_windows()
    assert _kernel32 is not None
    assert _advapi32 is not None
    token = wintypes.HANDLE()
    if not _advapi32.OpenProcessToken(
        _kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)
    ):
        raise _win_error("OpenProcessToken")
    if token.value is None:
        raise WindowsPrimitiveError("OpenProcessToken returned a null token")
    handle = int(token.value)
    try:
        elevation = _TOKEN_ELEVATION()
        returned = wintypes.DWORD()
        if not _advapi32.GetTokenInformation(
            handle,
            _TOKEN_ELEVATION_CLASS,
            ctypes.byref(elevation),
            ctypes.sizeof(elevation),
            ctypes.byref(returned),
        ):
            raise _win_error("GetTokenInformation(TokenElevation)")

        needed = wintypes.DWORD()
        _advapi32.GetTokenInformation(
            handle,
            _TOKEN_USER_CLASS,
            None,
            0,
            ctypes.byref(needed),
        )
        if needed.value == 0:
            raise _win_error("GetTokenInformation(TokenUser size)")
        buffer = ctypes.create_string_buffer(needed.value)
        if not _advapi32.GetTokenInformation(
            handle,
            _TOKEN_USER_CLASS,
            buffer,
            len(buffer),
            ctypes.byref(needed),
        ):
            raise _win_error("GetTokenInformation(TokenUser)")
        token_user = ctypes.cast(buffer, ctypes.POINTER(_TOKEN_USER)).contents
        sid = token_user.user.sid
        if not sid or not _advapi32.IsValidSid(sid):
            raise WindowsPrimitiveError("current token contains an invalid user SID")
        sid_length = int(_advapi32.GetLengthSid(sid))
        sid_bytes = ctypes.string_at(sid, sid_length)
        return bool(elevation.token_is_elevated), sid_bytes
    finally:
        _close_handle(handle)


def _read_machine_guid() -> bytes:
    _require_windows()
    assert _advapi32 is not None
    key = wintypes.HKEY(0x80000002)
    subkey = r"SOFTWARE\Microsoft\Cryptography"
    needed = wintypes.DWORD()
    result = int(
        _advapi32.RegGetValueW(
            key,
            subkey,
            "MachineGuid",
            _RRF_RT_REG_SZ,
            None,
            None,
            ctypes.byref(needed),
        )
    )
    if result != _ERROR_SUCCESS or needed.value < 2:
        raise _win_error("RegGetValueW(MachineGuid size)", result)
    buffer = ctypes.create_unicode_buffer(needed.value // ctypes.sizeof(ctypes.c_wchar) + 1)
    result = int(
        _advapi32.RegGetValueW(
            key,
            subkey,
            "MachineGuid",
            _RRF_RT_REG_SZ,
            None,
            buffer,
            ctypes.byref(needed),
        )
    )
    if result != _ERROR_SUCCESS or not buffer.value:
        raise _win_error("RegGetValueW(MachineGuid)", result)
    return buffer.value.strip().casefold().encode("utf-8")


@dataclass(frozen=True, slots=True)
class WindowsIdentity:
    is_elevated: bool
    user_id_hash: str
    device_id_hash: str


class WindowsIdentityProbe:
    """Return keyed hashes; never expose raw SID or MachineGuid."""

    def __init__(self, hmac_key: bytes) -> None:
        if len(hmac_key) < 16:
            raise ValueError("identity HMAC key must contain at least 16 bytes")
        self._key = bytes(hmac_key)

    def probe(self, *, require_non_elevated: bool = True) -> WindowsIdentity:
        elevated, sid = _read_token_state()
        if require_non_elevated and elevated:
            raise ElevatedProcessError("controlled actions refuse an elevated process")
        device = _read_machine_guid()
        return WindowsIdentity(
            is_elevated=elevated,
            user_id_hash=hmac.new(self._key, b"user\0" + sid, hashlib.sha256).hexdigest(),
            device_id_hash=hmac.new(self._key, b"device\0" + device, hashlib.sha256).hexdigest(),
        )


def _require_non_elevated() -> None:
    elevated, _sid = _read_token_state()
    if elevated:
        raise ElevatedProcessError("controlled actions refuse an elevated process")


def require_non_elevated_process() -> None:
    """Fail closed when the current JARVIS process has an elevated token."""
    _require_non_elevated()


@dataclass(frozen=True, slots=True)
class ExecutableEnrollment:
    path: Path
    identity: FileIdentity
    sha256: str

    @classmethod
    def capture(cls, path: str | os.PathLike[str]) -> ExecutableEnrollment:
        candidate = _validate_local_absolute_path(path)
        if candidate.suffix.casefold() != ".exe":
            raise UnsafePathError("enrolled application must be an absolute .exe path")
        identity = _probe_object(candidate, expect_directory=False, compute_sha256=True)
        assert identity.sha256 is not None
        return cls(path=identity.path, identity=identity, sha256=identity.sha256)


@dataclass(frozen=True, slots=True)
class LaunchReceipt:
    pid: int
    image_path: Path | None
    image_verified: bool
    process: subprocess.Popen[bytes] = field(repr=False, compare=False)


def _sanitized_environment(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if environment is None else environment
    casefolded = {key.casefold(): value for key, value in source.items()}
    sanitized: dict[str, str] = {}
    for key in _SAFE_CHILD_ENVIRONMENT:
        value = casefolded.get(key.casefold())
        if value is not None:
            if "\x00" in value:
                raise WindowsPrimitiveError(f"child environment {key} contains NUL")
            sanitized[key] = value
    if "SystemRoot" not in sanitized:
        raise WindowsPrimitiveError("SystemRoot is required in the sanitized child environment")
    return sanitized


def _query_process_image(pid: int) -> Path | None:
    assert _kernel32 is not None
    process = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if process in {None, 0, _INVALID_HANDLE_VALUE}:
        return None
    handle = int(process)
    try:
        capacity = 32_768
        buffer = ctypes.create_unicode_buffer(capacity)
        size = wintypes.DWORD(capacity)
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return Path(buffer.value)
    finally:
        _close_handle(handle)


def _terminate_unverified(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class FixedExecutableLauncher:
    """Launch one enrollment with constructor-fixed argv and no inherited PATH."""

    def __init__(
        self,
        enrollment: ExecutableEnrollment,
        argv: Sequence[str] = (),
    ) -> None:
        arguments = tuple(argv)
        if any("\x00" in argument for argument in arguments):
            raise ValueError("fixed application arguments cannot contain NUL")
        if sum(len(argument) + 3 for argument in arguments) > 30_000:
            raise ValueError("fixed application command line is too long")
        self._enrollment = enrollment
        self._argv = arguments

    @property
    def enrollment(self) -> ExecutableEnrollment:
        return self._enrollment

    @property
    def argv(self) -> tuple[str, ...]:
        return self._argv

    def launch(self) -> LaunchReceipt:
        _require_non_elevated()
        candidate = _validate_local_absolute_path(self._enrollment.path)
        _reject_name_surrogate_components(candidate)
        handle = _open_handle(
            candidate,
            hash_content=True,
            lock_path=True,
        )
        try:
            current = _identity_for_handle(candidate, handle, compute_sha256=True)
            if (
                not self._enrollment.identity.unchanged(current)
                or self._enrollment.path != self._enrollment.identity.path
                or current.final_path.casefold() != self._enrollment.identity.final_path.casefold()
                or current.sha256 is None
                or not hmac.compare_digest(self._enrollment.sha256, current.sha256)
            ):
                raise IdentityMismatchError("enrolled executable identity or SHA-256 changed")
            executable = str(self._enrollment.path)
            process = subprocess.Popen(
                [executable, *self._argv],
                executable=executable,
                shell=False,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(self._enrollment.path.parent),
                env=_sanitized_environment(),
            )
            image_path = _query_process_image(process.pid)
            if image_path is None:
                if process.poll() is None:
                    _terminate_unverified(process)
                    raise IdentityMismatchError("running process image could not be verified")
                return LaunchReceipt(
                    pid=process.pid,
                    image_path=None,
                    image_verified=False,
                    process=process,
                )
            launched = _probe_object(image_path, expect_directory=False)
            if not self._enrollment.identity.same_object(launched):
                _terminate_unverified(process)
                raise IdentityMismatchError("spawned process image differs from enrollment")
            return LaunchReceipt(
                pid=process.pid,
                image_path=image_path,
                image_verified=True,
                process=process,
            )
        finally:
            _close_handle(handle)


@dataclass(frozen=True, slots=True)
class PrinterStatus:
    name: str
    attributes: int
    status: int | None
    status_error: int | None = None


def _printer_status(name: str) -> tuple[int | None, int | None]:
    assert _winspool is not None
    printer = wintypes.HANDLE()
    if not _winspool.OpenPrinterW(name, ctypes.byref(printer), None):
        return None, ctypes.get_last_error()
    if printer.value is None:
        return None, 0
    handle = int(printer.value)
    try:
        needed = wintypes.DWORD()
        _winspool.GetPrinterW(handle, 6, None, 0, ctypes.byref(needed))
        if needed.value == 0:
            return None, ctypes.get_last_error()
        buffer = ctypes.create_string_buffer(needed.value)
        if not _winspool.GetPrinterW(
            handle,
            6,
            ctypes.cast(buffer, wintypes.LPBYTE),
            len(buffer),
            ctypes.byref(needed),
        ):
            return None, ctypes.get_last_error()
        info = ctypes.cast(buffer, ctypes.POINTER(_PRINTER_INFO_6)).contents
        return int(info.status), None
    finally:
        _winspool.ClosePrinter(handle)


def discover_local_printers(*, max_printers: int = 64) -> tuple[PrinterStatus, ...]:
    """Enumerate installed local queues and query status; never submit a job."""

    _require_windows()
    if not 1 <= max_printers <= 256:
        raise ValueError("max_printers must be between 1 and 256")
    assert _winspool is not None
    needed = wintypes.DWORD()
    returned = wintypes.DWORD()
    ctypes.set_last_error(0)
    ok = bool(
        _winspool.EnumPrintersW(
            _PRINTER_ENUM_LOCAL,
            None,
            4,
            None,
            0,
            ctypes.byref(needed),
            ctypes.byref(returned),
        )
    )
    error = ctypes.get_last_error()
    if needed.value == 0:
        if ok or error in {_ERROR_SUCCESS, _ERROR_INSUFFICIENT_BUFFER}:
            return ()
        raise _win_error("EnumPrintersW(size)", error)
    if not ok and error != _ERROR_INSUFFICIENT_BUFFER:
        raise _win_error("EnumPrintersW(size)", error)
    buffer = ctypes.create_string_buffer(needed.value)
    if not _winspool.EnumPrintersW(
        _PRINTER_ENUM_LOCAL,
        None,
        4,
        ctypes.cast(buffer, wintypes.LPBYTE),
        len(buffer),
        ctypes.byref(needed),
        ctypes.byref(returned),
    ):
        raise _win_error("EnumPrintersW")
    if returned.value > max_printers:
        raise WindowsPrimitiveError("local printer count exceeds configured discovery limit")
    entries = ctypes.cast(buffer, ctypes.POINTER(_PRINTER_INFO_4W))
    discovered: list[PrinterStatus] = []
    for index in range(returned.value):
        entry = entries[index]
        name = entry.printer_name
        if (
            not name
            or int(entry.attributes) & _PRINTER_ATTRIBUTE_NETWORK
            or len(name) > 512
            or any(ord(character) < 32 for character in name)
        ):
            continue
        status, status_error = _printer_status(name)
        discovered.append(
            PrinterStatus(
                name=name,
                attributes=int(entry.attributes),
                status=status,
                status_error=status_error,
            )
        )
    return tuple(discovered)


class MediaKey(IntEnum):
    PREVIOUS_TRACK = 0xB1
    NEXT_TRACK = 0xB0
    STOP = 0xB2
    PLAY_PAUSE = 0xB3
    VOLUME_MUTE = 0xAD


@dataclass(frozen=True, slots=True)
class MediaInputResult:
    key: MediaKey
    requested_count: int
    accepted_count: int
    last_error: int | None

    @property
    def accepted(self) -> bool:
        return self.accepted_count == self.requested_count


def _send_media_input(key: MediaKey) -> tuple[int, int | None]:
    assert _user32 is not None
    inputs = (_INPUT * 2)()
    inputs[0].type = _INPUT_KEYBOARD
    inputs[0].keyboard = _KEYBDINPUT(key.value, 0, 0, 0, 0)
    inputs[1].type = _INPUT_KEYBOARD
    inputs[1].keyboard = _KEYBDINPUT(key.value, 0, _KEYEVENTF_KEYUP, 0, 0)
    ctypes.set_last_error(0)
    accepted = int(_user32.SendInput(len(inputs), inputs, ctypes.sizeof(_INPUT)))
    error = ctypes.get_last_error()
    return accepted, error or None


def send_media_key(key: MediaKey) -> MediaInputResult:
    """Send one global media key pair once; result proves injection, not playback."""

    _require_windows()
    if not isinstance(key, MediaKey):
        raise TypeError("key must be a MediaKey")
    _require_non_elevated()
    accepted, error = _send_media_input(key)
    return MediaInputResult(
        key=key,
        requested_count=2,
        accepted_count=accepted,
        last_error=error,
    )
