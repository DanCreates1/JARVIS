"""Owned values crossing the generic Phase 10 wearable boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from jarvis.core.models import CoreModel, Identifier

WEARABLE_PROTOCOL_MAJOR = 1
WEARABLE_PROTOCOL_MINOR = 0
MAX_WEARABLE_PAYLOAD_BYTES = 8 * 1024 * 1024
MAX_WEARABLE_DURATION_MS = 30_000
MAX_WEARABLE_EVENTS = 256


class WearableCapability(StrEnum):
    AUDIO_INPUT = "audio_input"
    AUDIO_OUTPUT = "audio_output"
    DISPLAY = "display"
    CAMERA = "camera"
    INPUT = "input"
    NOTIFICATION = "notification"
    HEALTH = "health"


class WearableDataClass(StrEnum):
    PRIVATE = "private"
    MEDIA = "media"
    HEALTH = "health"


class WearableTransport(StrEnum):
    DIRECT = "direct"
    PHONE_BRIDGE = "phone_bridge"
    SIMULATOR = "simulator"


class WearableConnectionState(StrEnum):
    AVAILABLE = "available"
    DISCONNECTED = "disconnected"
    REMOVED = "removed"
    REVOKED = "revoked"


class WearablePermissionState(StrEnum):
    UNKNOWN = "unknown"
    DENIED = "denied"
    GRANTED = "granted"


class WearableRetention(StrEnum):
    EPHEMERAL = "ephemeral"


class WearableFailureCode(StrEnum):
    CANCELLED = "cancelled"
    DEVICE_MISMATCH = "device_mismatch"
    DEVICE_UNAVAILABLE = "device_unavailable"
    INCOMPATIBLE_VERSION = "incompatible_version"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    PERMISSION_DENIED = "permission_denied"
    AUTHORIZATION_DENIED = "authorization_denied"
    AUTHORIZATION_EXPIRED = "authorization_expired"
    CLASSIFICATION_MISMATCH = "classification_mismatch"
    INDICATOR_UNAVAILABLE = "indicator_unavailable"
    LIMIT_EXCEEDED = "limit_exceeded"
    REPLAYED_REQUEST = "replayed_request"


def required_data_class(capability: WearableCapability) -> WearableDataClass:
    if capability in {WearableCapability.AUDIO_INPUT, WearableCapability.CAMERA}:
        return WearableDataClass.MEDIA
    if capability is WearableCapability.HEALTH:
        return WearableDataClass.HEALTH
    return WearableDataClass.PRIVATE


def requires_visible_indicator(capability: WearableCapability) -> bool:
    return capability in {WearableCapability.AUDIO_INPUT, WearableCapability.CAMERA}


class WearableCapabilityLimits(CoreModel):
    max_payload_bytes: Annotated[int, Field(ge=1, le=MAX_WEARABLE_PAYLOAD_BYTES)]
    max_duration_ms: Annotated[int, Field(ge=1, le=MAX_WEARABLE_DURATION_MS)]
    max_events: Annotated[int, Field(ge=1, le=MAX_WEARABLE_EVENTS)]
    background_allowed: Literal[False] = False


class WearableCapabilityDescriptor(CoreModel):
    capability: WearableCapability
    data_class: WearableDataClass
    permission: WearablePermissionState
    limits: WearableCapabilityLimits
    visible_indicator_required: bool

    @model_validator(mode="after")
    def enforce_classification_and_indicator(self) -> Self:
        if self.data_class is not required_data_class(self.capability):
            raise ValueError("wearable capability uses the wrong data classification")
        if self.visible_indicator_required is not requires_visible_indicator(self.capability):
            raise ValueError("wearable capability uses the wrong indicator requirement")
        return self


class WearableDeviceDescriptor(CoreModel):
    device_id: Identifier
    vendor: Identifier
    model: Identifier
    adapter_id: Identifier
    adapter_version: Identifier
    protocol_major: Literal[1] = 1
    protocol_minor: Annotated[int, Field(ge=0, le=99)] = WEARABLE_PROTOCOL_MINOR
    transport: WearableTransport
    connection: WearableConnectionState
    capabilities: Annotated[tuple[WearableCapabilityDescriptor, ...], Field(max_length=16)]
    simulated: bool = False

    @field_validator("capabilities")
    @classmethod
    def unique_capabilities(
        cls, value: tuple[WearableCapabilityDescriptor, ...]
    ) -> tuple[WearableCapabilityDescriptor, ...]:
        names = [item.capability for item in value]
        if len(names) != len(set(names)):
            raise ValueError("wearable capabilities must be unique")
        return tuple(sorted(value, key=lambda item: item.capability.value))

    @model_validator(mode="after")
    def validate_transport(self) -> Self:
        if self.simulated is not (self.transport is WearableTransport.SIMULATOR):
            raise ValueError("simulated devices must use the simulator transport")
        return self


class WearableNegotiationRequest(CoreModel):
    request_id: Identifier
    host_id: Identifier
    device_id: Identifier
    session_id: Identifier
    protocol_major: Annotated[int, Field(ge=1, le=99)] = WEARABLE_PROTOCOL_MAJOR
    protocol_minor: Annotated[int, Field(ge=0, le=99)] = WEARABLE_PROTOCOL_MINOR
    required_capabilities: Annotated[tuple[WearableCapability, ...], Field(max_length=16)] = ()
    optional_capabilities: Annotated[tuple[WearableCapability, ...], Field(max_length=16)] = ()

    @model_validator(mode="after")
    def unique_disjoint_capabilities(self) -> Self:
        required = set(self.required_capabilities)
        optional = set(self.optional_capabilities)
        if len(required) != len(self.required_capabilities):
            raise ValueError("required wearable capabilities must be unique")
        if len(optional) != len(self.optional_capabilities):
            raise ValueError("optional wearable capabilities must be unique")
        if required & optional:
            raise ValueError("required and optional wearable capabilities must be disjoint")
        return self


class WearableNegotiationResult(CoreModel):
    request_id: Identifier
    device_id: Identifier
    session_id: Identifier
    protocol_major: Literal[1] = 1
    protocol_minor: Annotated[int, Field(ge=0, le=99)]
    available_capabilities: tuple[WearableCapabilityDescriptor, ...]
    unavailable_optional_capabilities: tuple[WearableCapability, ...] = ()
    authorization_granted: Literal[False] = False


class WearableAuthorization(CoreModel):
    """Host-issued exact grant; adapters accept it only when present in a trusted store."""

    grant_id: Identifier
    host_id: Identifier
    device_id: Identifier
    session_id: Identifier
    capabilities: Annotated[tuple[WearableCapability, ...], Field(min_length=1, max_length=16)]
    media_allowed: bool = False
    health_allowed: bool = False
    issued_at: datetime
    expires_at: datetime

    @field_validator("capabilities")
    @classmethod
    def unique_granted_capabilities(
        cls, value: tuple[WearableCapability, ...]
    ) -> tuple[WearableCapability, ...]:
        if len(value) != len(set(value)):
            raise ValueError("authorized wearable capabilities must be unique")
        return tuple(sorted(value, key=str))

    @field_validator("issued_at", "expires_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("wearable authorization timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_scope_and_expiry(self) -> Self:
        if self.expires_at <= self.issued_at:
            raise ValueError("wearable authorization must expire after issue")
        if not self.media_allowed and any(
            required_data_class(item) is WearableDataClass.MEDIA for item in self.capabilities
        ):
            raise ValueError("media capability requires explicit media authorization")
        if WearableCapability.HEALTH in self.capabilities and not self.health_allowed:
            raise ValueError("health capability requires explicit health authorization")
        return self


class WearableOperationRequest(CoreModel):
    request_id: Identifier
    host_id: Identifier
    device_id: Identifier
    session_id: Identifier
    capability: WearableCapability
    purpose: Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_.-]*$")]
    data_class: WearableDataClass
    max_payload_bytes: Annotated[int, Field(ge=1, le=MAX_WEARABLE_PAYLOAD_BYTES)]
    max_duration_ms: Annotated[int, Field(ge=1, le=MAX_WEARABLE_DURATION_MS)]
    max_events: Annotated[int, Field(ge=1, le=MAX_WEARABLE_EVENTS)]
    visible_indicator_required: bool
    retention: Literal[WearableRetention.EPHEMERAL] = WearableRetention.EPHEMERAL
    cloud_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_boundary(self) -> Self:
        if self.data_class is not required_data_class(self.capability):
            raise ValueError("wearable operation uses the wrong data classification")
        if self.visible_indicator_required is not requires_visible_indicator(self.capability):
            raise ValueError("wearable operation uses the wrong indicator requirement")
        return self


class WearableOperationReceipt(CoreModel):
    request_id: Identifier
    operation_id: Identifier
    device_id: Identifier
    session_id: Identifier
    capability: WearableCapability
    completed_at: datetime
    bytes_processed: Annotated[int, Field(ge=0, le=MAX_WEARABLE_PAYLOAD_BYTES)]
    events_processed: Annotated[int, Field(ge=0, le=MAX_WEARABLE_EVENTS)]
    indicator_observed: bool
    content_retained: Literal[False] = False
    cloud_disclosed: Literal[False] = False

    @field_validator("completed_at")
    @classmethod
    def normalize_completion_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("wearable completion timestamp must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_indicator(self) -> Self:
        if requires_visible_indicator(self.capability) and not self.indicator_observed:
            raise ValueError("wearable media receipt requires an observed indicator")
        return self


class WearableError(RuntimeError):
    """Content-free classified failure crossing the wearable boundary."""

    def __init__(self, code: WearableFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code
