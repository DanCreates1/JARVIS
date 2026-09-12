"""Deterministic hardware-independent wearable adapter for contract and abuse tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from uuid import uuid4

from .models import (
    WearableAuthorization,
    WearableCapability,
    WearableConnectionState,
    WearableDataClass,
    WearableDeviceDescriptor,
    WearableError,
    WearableFailureCode,
    WearableNegotiationRequest,
    WearableNegotiationResult,
    WearableOperationReceipt,
    WearableOperationRequest,
    WearablePermissionState,
    WearableTransport,
    required_data_class,
    requires_visible_indicator,
)


class FakeWearableClient:
    """Stateful fake. Trusted grants enter only through constructor or test controls."""

    def __init__(
        self,
        device: WearableDeviceDescriptor,
        *,
        trusted_authorizations: Iterable[WearableAuthorization] = (),
        indicator_available: bool = True,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if not device.simulated or device.transport is not WearableTransport.SIMULATOR:
            raise ValueError("fake wearable requires a simulated device descriptor")
        self._device = device
        self._capabilities = {item.capability: item for item in device.capabilities}
        self._authorizations = {item.grant_id: item for item in trusted_authorizations}
        self._indicator_available = indicator_available
        self._now = now or (lambda: datetime.now(UTC))
        self._seen_requests: set[str] = set()
        self._closed = False
        self._state = device.connection

    async def describe(self) -> WearableDeviceDescriptor:
        return self._snapshot()

    async def negotiate(
        self,
        request: WearableNegotiationRequest,
        *,
        cancel: asyncio.Event | None = None,
    ) -> WearableNegotiationResult:
        self._check_cancel(cancel)
        self._check_request_id(request.request_id)
        self._check_device(request.device_id)
        if request.protocol_major != self._device.protocol_major:
            raise WearableError(
                WearableFailureCode.INCOMPATIBLE_VERSION,
                "wearable protocol major version is incompatible",
            )
        if request.protocol_minor > self._device.protocol_minor:
            raise WearableError(
                WearableFailureCode.INCOMPATIBLE_VERSION,
                "wearable protocol minor version is unavailable",
            )
        missing = set(request.required_capabilities) - self._capabilities.keys()
        if missing:
            raise WearableError(
                WearableFailureCode.UNSUPPORTED_CAPABILITY,
                "required wearable capability is unavailable",
            )
        selected = set(request.required_capabilities) | (
            set(request.optional_capabilities) & self._capabilities.keys()
        )
        unavailable = set(request.optional_capabilities) - self._capabilities.keys()
        return WearableNegotiationResult(
            request_id=request.request_id,
            device_id=request.device_id,
            session_id=request.session_id,
            protocol_minor=request.protocol_minor,
            available_capabilities=tuple(
                self._capabilities[item] for item in sorted(selected, key=str)
            ),
            unavailable_optional_capabilities=tuple(sorted(unavailable, key=str)),
        )

    async def execute(
        self,
        request: WearableOperationRequest,
        authorization: WearableAuthorization,
        *,
        cancel: asyncio.Event | None = None,
    ) -> WearableOperationReceipt:
        self._check_cancel(cancel)
        self._check_request_id(request.request_id)
        self._check_device(request.device_id)
        descriptor = self._capabilities.get(request.capability)
        if descriptor is None:
            raise WearableError(
                WearableFailureCode.UNSUPPORTED_CAPABILITY,
                "wearable capability is unavailable",
            )
        if descriptor.permission is not WearablePermissionState.GRANTED:
            raise WearableError(
                WearableFailureCode.PERMISSION_DENIED,
                "wearable capability permission is not granted",
            )
        trusted = self._authorizations.get(authorization.grant_id)
        if trusted is None or trusted != authorization:
            raise WearableError(
                WearableFailureCode.AUTHORIZATION_DENIED,
                "wearable authorization is not trusted",
            )
        if self._now().astimezone(UTC) >= trusted.expires_at:
            raise WearableError(
                WearableFailureCode.AUTHORIZATION_EXPIRED,
                "wearable authorization has expired",
            )
        if (
            request.host_id != trusted.host_id
            or request.device_id != trusted.device_id
            or request.session_id != trusted.session_id
            or request.capability not in trusted.capabilities
        ):
            raise WearableError(
                WearableFailureCode.AUTHORIZATION_DENIED,
                "wearable operation does not match authorization",
            )
        data_class = required_data_class(request.capability)
        if data_class is not request.data_class:
            raise WearableError(
                WearableFailureCode.CLASSIFICATION_MISMATCH,
                "wearable operation classification mismatch",
            )
        if data_class is WearableDataClass.MEDIA and not trusted.media_allowed:
            raise WearableError(
                WearableFailureCode.AUTHORIZATION_DENIED,
                "wearable media access is not authorized",
            )
        if data_class is WearableDataClass.HEALTH and not trusted.health_allowed:
            raise WearableError(
                WearableFailureCode.AUTHORIZATION_DENIED,
                "wearable health access is not authorized",
            )
        limits = descriptor.limits
        if (
            request.max_payload_bytes > limits.max_payload_bytes
            or request.max_duration_ms > limits.max_duration_ms
            or request.max_events > limits.max_events
        ):
            raise WearableError(
                WearableFailureCode.LIMIT_EXCEEDED,
                "wearable operation exceeds negotiated limits",
            )
        indicator_required = requires_visible_indicator(request.capability)
        if indicator_required and not self._indicator_available:
            raise WearableError(
                WearableFailureCode.INDICATOR_UNAVAILABLE,
                "wearable media indicator is unavailable",
            )
        self._check_cancel(cancel)
        return WearableOperationReceipt(
            request_id=request.request_id,
            operation_id=f"operation:{uuid4().hex}",
            device_id=request.device_id,
            session_id=request.session_id,
            capability=request.capability,
            completed_at=self._now(),
            bytes_processed=min(request.max_payload_bytes, 1024),
            events_processed=min(request.max_events, 1),
            indicator_observed=indicator_required,
        )

    async def close(self) -> None:
        self._closed = True
        self._state = WearableConnectionState.DISCONNECTED
        self._authorizations.clear()

    def trust_authorization(self, authorization: WearableAuthorization) -> None:
        """Trusted-host/test control, deliberately absent from WearableClient."""
        self._authorizations[authorization.grant_id] = authorization

    def revoke_authorization(self, grant_id: str) -> None:
        self._authorizations.pop(grant_id, None)

    def set_connection(self, state: WearableConnectionState) -> None:
        self._state = state
        if state in {WearableConnectionState.REMOVED, WearableConnectionState.REVOKED}:
            self._authorizations.clear()

    def set_permission(
        self, capability: WearableCapability, permission: WearablePermissionState
    ) -> None:
        descriptor = self._capabilities.get(capability)
        if descriptor is None:
            raise ValueError("wearable capability is unavailable")
        self._capabilities[capability] = descriptor.model_copy(update={"permission": permission})

    def remove_capability(self, capability: WearableCapability) -> None:
        self._capabilities.pop(capability, None)

    def _snapshot(self) -> WearableDeviceDescriptor:
        return self._device.model_copy(
            update={
                "connection": self._state,
                "capabilities": tuple(self._capabilities.values()),
            }
        )

    def _check_cancel(self, cancel: asyncio.Event | None) -> None:
        if cancel is not None and cancel.is_set():
            raise WearableError(WearableFailureCode.CANCELLED, "wearable operation cancelled")

    def _check_request_id(self, request_id: str) -> None:
        if request_id in self._seen_requests:
            raise WearableError(
                WearableFailureCode.REPLAYED_REQUEST,
                "wearable request was already consumed",
            )
        self._seen_requests.add(request_id)

    def _check_device(self, device_id: str) -> None:
        if device_id != self._device.device_id:
            raise WearableError(
                WearableFailureCode.DEVICE_MISMATCH,
                "wearable device does not match request",
            )
        if self._closed or self._state is not WearableConnectionState.AVAILABLE:
            raise WearableError(
                WearableFailureCode.DEVICE_UNAVAILABLE,
                "wearable device is unavailable",
            )
