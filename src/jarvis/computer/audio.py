"""Narrow Windows Core Audio master-volume primitives.

The default adapter opens the default ``eRender``/``eConsole`` endpoint through
``IMMDeviceEnumerator`` and ``IMMDevice::Activate``. Mutations are absolute,
single-attempt operations with a non-null event-context GUID and read-back
verification. This module contains no policy or approval logic; callers must
obtain an exact grant before invoking a setter.
"""

from __future__ import annotations

import ctypes
import math
import os
import threading
from ctypes import wintypes
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, Protocol
from uuid import UUID

from . import windows as _windows

_IS_WINDOWS: Final = os.name == "nt"
_CLSCTX_INPROC_SERVER: Final = 0x1
_COINIT_MULTITHREADED: Final = 0x0
_E_RENDER: Final = 0
_E_CONSOLE: Final = 0
_DEFAULT_TOLERANCE: Final = 0.001

_IMMDEVICE_ENUMERATOR_GET_DEFAULT_ENDPOINT_SLOT: Final = 4
_IMMDEVICE_ACTIVATE_SLOT: Final = 3
_IAUDIO_ENDPOINT_SET_SCALAR_SLOT: Final = 7
_IAUDIO_ENDPOINT_GET_SCALAR_SLOT: Final = 9
_IAUDIO_ENDPOINT_SET_MUTE_SLOT: Final = 14
_IAUDIO_ENDPOINT_GET_MUTE_SLOT: Final = 15
_IUNKNOWN_RELEASE_SLOT: Final = 2

_COMFUNCTYPE: Any = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)
_ole32: Any | None = None
if _IS_WINDOWS:
    _ole32 = ctypes.WinDLL("ole32", use_last_error=True)


class _GUID(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_uuid(cls, value: UUID) -> _GUID:
        return cls.from_buffer_copy(value.bytes_le)


_CLSID_MMDEVICE_ENUMERATOR: Final = _GUID.from_uuid(UUID("bcde0395-e52f-467c-8e3d-c4579291692e"))
_IID_IMMDEVICE_ENUMERATOR: Final = _GUID.from_uuid(UUID("a95664d2-9614-4f35-a746-de8db63617e6"))
_IID_IAUDIO_ENDPOINT_VOLUME: Final = _GUID.from_uuid(UUID("5cdf2c82-841e-4546-9722-0cf74078229a"))


def _configure_ole32() -> None:
    if _ole32 is None:
        return
    _ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    _ole32.CoInitializeEx.restype = ctypes.c_long
    _ole32.CoUninitialize.argtypes = []
    _ole32.CoUninitialize.restype = None
    _ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(_GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _ole32.CoCreateInstance.restype = ctypes.c_long


_configure_ole32()


class CoreAudioError(_windows.WindowsPrimitiveError):
    """Base error for the bounded Core Audio primitive."""


class CoreAudioProtocolError(CoreAudioError):
    """Raised when Core Audio or an injected endpoint returns malformed state."""


class CoreAudioHResultError(CoreAudioError):
    """Raised for a failed HRESULT without leaking unrelated process state."""

    def __init__(self, operation: str, hresult: int) -> None:
        self.operation = operation
        self.hresult = hresult & 0xFFFFFFFF
        super().__init__(f"{operation} failed with HRESULT 0x{self.hresult:08X}")


class MasterVolumeOperation(StrEnum):
    SET_SCALAR = "set_scalar"
    SET_MUTE = "set_mute"


@dataclass(frozen=True, slots=True)
class MasterVolumeState:
    scalar: float
    muted: bool

    def __post_init__(self) -> None:
        scalar = _validated_scalar(self.scalar, label="endpoint scalar")
        if type(self.muted) is not bool:
            raise ValueError("endpoint mute state must be boolean")
        object.__setattr__(self, "scalar", scalar)


@dataclass(frozen=True, slots=True)
class MasterVolumeReceipt:
    operation: MasterVolumeOperation
    event_context: UUID
    before: MasterVolumeState
    after: MasterVolumeState
    requested_scalar: float | None = None
    requested_muted: bool | None = None

    def __post_init__(self) -> None:
        _validated_event_context(self.event_context)
        if self.operation is MasterVolumeOperation.SET_SCALAR:
            if self.requested_scalar is None or self.requested_muted is not None:
                raise ValueError("scalar receipt requires only requested_scalar")
            object.__setattr__(
                self,
                "requested_scalar",
                _validated_scalar(self.requested_scalar, label="requested scalar"),
            )
        elif self.operation is MasterVolumeOperation.SET_MUTE:
            if type(self.requested_muted) is not bool or self.requested_scalar is not None:
                raise ValueError("mute receipt requires only requested_muted")


class AudioPostconditionError(CoreAudioError):
    """A setter returned but the endpoint did not match the exact requested state."""

    def __init__(
        self,
        *,
        operation: MasterVolumeOperation,
        event_context: UUID,
        before: MasterVolumeState,
        observed: MasterVolumeState,
        requested_scalar: float | None = None,
        requested_muted: bool | None = None,
    ) -> None:
        self.operation = operation
        self.event_context = event_context
        self.before = before
        self.observed = observed
        self.requested_scalar = requested_scalar
        self.requested_muted = requested_muted
        super().__init__(f"Core Audio {operation.value} postcondition did not match")


class EndpointVolume(Protocol):
    """Small injectable seam around the four IAudioEndpointVolume methods used here."""

    def get_scalar(self) -> float: ...

    def get_mute(self) -> bool: ...

    def set_scalar(self, value: float, event_context: UUID) -> None: ...

    def set_mute(self, value: bool, event_context: UUID) -> None: ...

    def close(self) -> None: ...


_MUTATION_LOCK = threading.Lock()


def _validated_scalar(value: object, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number from 0.0 to 1.0")
    scalar = float(value)
    if not math.isfinite(scalar) or not 0.0 <= scalar <= 1.0:
        raise ValueError(f"{label} must be a finite number from 0.0 to 1.0")
    return scalar


def _validated_tolerance(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("verification tolerance must be from 0.0 to 0.001")
    tolerance = float(value)
    if not math.isfinite(tolerance) or not 0.0 <= tolerance <= _DEFAULT_TOLERANCE:
        raise ValueError("verification tolerance must be from 0.0 to 0.001")
    return tolerance


def _validated_event_context(value: object) -> UUID:
    if not isinstance(value, UUID) or value.int == 0:
        raise ValueError("event context must be a non-null UUID")
    return value


def _check_hresult(value: int, operation: str) -> None:
    if int(value) < 0:
        raise CoreAudioHResultError(operation, int(value))


def _com_method(
    pointer: ctypes.c_void_p,
    slot: int,
    restype: Any,
    *argtypes: Any,
) -> Any:
    if pointer.value is None:
        raise CoreAudioProtocolError("COM interface pointer is null")
    vtable = ctypes.cast(
        pointer,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
    ).contents
    address = vtable[slot]
    if not address:
        raise CoreAudioProtocolError(f"COM vtable slot {slot} is null")
    prototype = _COMFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return prototype(address)


def _release(pointer: ctypes.c_void_p) -> None:
    if pointer.value is None:
        return
    release = _com_method(pointer, _IUNKNOWN_RELEASE_SLOT, ctypes.c_ulong)
    release(pointer)


class _ComEndpointVolume:
    """Own COM references created on one calling thread and release them in reverse."""

    def __init__(
        self,
        *,
        enumerator: ctypes.c_void_p,
        device: ctypes.c_void_p,
        endpoint: ctypes.c_void_p,
    ) -> None:
        self._enumerator = enumerator
        self._device = device
        self._endpoint = endpoint
        self._closed = False

    @classmethod
    def open(cls) -> _ComEndpointVolume:
        if not _IS_WINDOWS or _ole32 is None:
            raise _windows.UnsupportedPlatformError(
                "Windows Core Audio is unavailable on this platform"
            )
        initialized = False
        enumerator = ctypes.c_void_p()
        device = ctypes.c_void_p()
        endpoint = ctypes.c_void_p()
        try:
            result = int(_ole32.CoInitializeEx(None, _COINIT_MULTITHREADED))
            _check_hresult(result, "CoInitializeEx")
            initialized = True

            result = int(
                _ole32.CoCreateInstance(
                    ctypes.byref(_CLSID_MMDEVICE_ENUMERATOR),
                    None,
                    _CLSCTX_INPROC_SERVER,
                    ctypes.byref(_IID_IMMDEVICE_ENUMERATOR),
                    ctypes.byref(enumerator),
                )
            )
            _check_hresult(result, "CoCreateInstance(MMDeviceEnumerator)")
            if enumerator.value is None:
                raise CoreAudioProtocolError("MMDeviceEnumerator returned a null interface")

            get_default = _com_method(
                enumerator,
                _IMMDEVICE_ENUMERATOR_GET_DEFAULT_ENDPOINT_SLOT,
                ctypes.c_long,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_void_p),
            )
            result = int(get_default(enumerator, _E_RENDER, _E_CONSOLE, ctypes.byref(device)))
            _check_hresult(result, "IMMDeviceEnumerator.GetDefaultAudioEndpoint")
            if device.value is None:
                raise CoreAudioProtocolError("default render endpoint is null")

            activate = _com_method(
                device,
                _IMMDEVICE_ACTIVATE_SLOT,
                ctypes.c_long,
                ctypes.POINTER(_GUID),
                wintypes.DWORD,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_void_p),
            )
            result = int(
                activate(
                    device,
                    ctypes.byref(_IID_IAUDIO_ENDPOINT_VOLUME),
                    _CLSCTX_INPROC_SERVER,
                    None,
                    ctypes.byref(endpoint),
                )
            )
            _check_hresult(result, "IMMDevice.Activate(IAudioEndpointVolume)")
            if endpoint.value is None:
                raise CoreAudioProtocolError("IAudioEndpointVolume interface is null")
            return cls(enumerator=enumerator, device=device, endpoint=endpoint)
        except BaseException:
            _release(endpoint)
            _release(device)
            _release(enumerator)
            if initialized:
                _ole32.CoUninitialize()
            raise

    def _require_open(self) -> ctypes.c_void_p:
        if self._closed or self._endpoint.value is None:
            raise CoreAudioProtocolError("Core Audio endpoint is closed")
        return self._endpoint

    def get_scalar(self) -> float:
        endpoint = self._require_open()
        value = ctypes.c_float()
        method = _com_method(
            endpoint,
            _IAUDIO_ENDPOINT_GET_SCALAR_SLOT,
            ctypes.c_long,
            ctypes.POINTER(ctypes.c_float),
        )
        _check_hresult(int(method(endpoint, ctypes.byref(value))), "GetMasterVolumeLevelScalar")
        return float(value.value)

    def get_mute(self) -> bool:
        endpoint = self._require_open()
        value = wintypes.BOOL()
        method = _com_method(
            endpoint,
            _IAUDIO_ENDPOINT_GET_MUTE_SLOT,
            ctypes.c_long,
            ctypes.POINTER(wintypes.BOOL),
        )
        _check_hresult(int(method(endpoint, ctypes.byref(value))), "GetMute")
        return bool(value.value)

    def set_scalar(self, value: float, event_context: UUID) -> None:
        endpoint = self._require_open()
        context = _GUID.from_uuid(event_context)
        method = _com_method(
            endpoint,
            _IAUDIO_ENDPOINT_SET_SCALAR_SLOT,
            ctypes.c_long,
            ctypes.c_float,
            ctypes.POINTER(_GUID),
        )
        _check_hresult(
            int(method(endpoint, ctypes.c_float(value), ctypes.byref(context))),
            "SetMasterVolumeLevelScalar",
        )

    def set_mute(self, value: bool, event_context: UUID) -> None:
        endpoint = self._require_open()
        context = _GUID.from_uuid(event_context)
        method = _com_method(
            endpoint,
            _IAUDIO_ENDPOINT_SET_MUTE_SLOT,
            ctypes.c_long,
            wintypes.BOOL,
            ctypes.POINTER(_GUID),
        )
        _check_hresult(
            int(method(endpoint, wintypes.BOOL(value), ctypes.byref(context))),
            "SetMute",
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _release(self._endpoint)
        _release(self._device)
        _release(self._enumerator)
        self._endpoint = ctypes.c_void_p()
        self._device = ctypes.c_void_p()
        self._enumerator = ctypes.c_void_p()
        assert _ole32 is not None
        _ole32.CoUninitialize()


def _default_endpoint_factory() -> EndpointVolume:
    return _ComEndpointVolume.open()


def _default_elevation_guard() -> None:
    _windows._require_non_elevated()


def _read_state(endpoint: EndpointVolume) -> MasterVolumeState:
    try:
        return MasterVolumeState(scalar=endpoint.get_scalar(), muted=endpoint.get_mute())
    except ValueError as exc:
        raise CoreAudioProtocolError("audio endpoint returned invalid state") from exc


def get_master_volume_state() -> MasterVolumeState:
    """Read scalar and mute state from the default console render endpoint."""

    endpoint = _default_endpoint_factory()
    try:
        return _read_state(endpoint)
    finally:
        endpoint.close()


def get_master_volume_scalar() -> float:
    return get_master_volume_state().scalar


def get_master_mute() -> bool:
    return get_master_volume_state().muted


def set_master_volume_scalar(
    value: float,
    *,
    event_context: UUID,
    verification_tolerance: float = _DEFAULT_TOLERANCE,
) -> MasterVolumeReceipt:
    """Set one absolute scalar value once and verify the endpoint read-back."""

    requested = _validated_scalar(value, label="master volume scalar")
    context = _validated_event_context(event_context)
    tolerance = _validated_tolerance(verification_tolerance)
    with _MUTATION_LOCK:
        _default_elevation_guard()
        endpoint = _default_endpoint_factory()
        try:
            before = _read_state(endpoint)
            endpoint.set_scalar(requested, context)
            after = _read_state(endpoint)
        finally:
            endpoint.close()
    if abs(after.scalar - requested) > tolerance:
        raise AudioPostconditionError(
            operation=MasterVolumeOperation.SET_SCALAR,
            event_context=context,
            before=before,
            observed=after,
            requested_scalar=requested,
        )
    return MasterVolumeReceipt(
        operation=MasterVolumeOperation.SET_SCALAR,
        event_context=context,
        before=before,
        after=after,
        requested_scalar=requested,
    )


def set_master_mute(
    value: bool,
    *,
    event_context: UUID,
) -> MasterVolumeReceipt:
    """Set one absolute mute state once and verify the endpoint read-back."""

    if type(value) is not bool:
        raise ValueError("master mute state must be boolean")
    context = _validated_event_context(event_context)
    with _MUTATION_LOCK:
        _default_elevation_guard()
        endpoint = _default_endpoint_factory()
        try:
            before = _read_state(endpoint)
            endpoint.set_mute(value, context)
            after = _read_state(endpoint)
        finally:
            endpoint.close()
    if after.muted is not value:
        raise AudioPostconditionError(
            operation=MasterVolumeOperation.SET_MUTE,
            event_context=context,
            before=before,
            observed=after,
            requested_muted=value,
        )
    return MasterVolumeReceipt(
        operation=MasterVolumeOperation.SET_MUTE,
        event_context=context,
        before=before,
        after=after,
        requested_muted=value,
    )
