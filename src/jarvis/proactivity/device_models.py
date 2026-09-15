"""Content-free Phase 11C multi-device ownership contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from jarvis.core.models import CoreModel, Identifier

from .models import FeatureName
from .runner_models import DispatchState, NotificationState


class OwnershipKind(StrEnum):
    LOCAL_HOST = "local_host"
    DEVICE = "device"


class DeviceBindingState(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class OwnershipEventType(StrEnum):
    LOCAL_OWNER_CREATED = "local_owner_created"
    DEVICE_CLAIMED = "device_claimed"
    DEVICE_RENEWED = "device_renewed"
    DEVICE_RELEASED = "device_released"
    DEVICE_HANDOFF = "device_handoff"
    LOCAL_RECLAIMED = "local_reclaimed"
    LEASE_EXPIRED = "lease_expired"
    ADAPTER_DISABLED = "adapter_disabled"
    BINDING_REVOKED = "binding_revoked"
    DEVICE_REVOKED = "device_revoked"


class ProactivityAdapterControl(CoreModel):
    host_id: Identifier
    enabled: bool
    version: Annotated[int, Field(ge=1)]
    kill_generation: Annotated[int, Field(ge=1)]
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value)


class ProactivityDeviceBinding(CoreModel):
    host_id: Identifier
    device_id: Identifier
    feature: FeatureName
    allow_manage: bool
    state: DeviceBindingState
    version: Annotated[int, Field(ge=1)]
    expires_at: datetime
    created_at: datetime
    updated_at: datetime

    @field_validator("expires_at", "created_at", "updated_at")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return _aware(value)


class CandidateOwnership(CoreModel):
    candidate_id: Identifier
    host_id: Identifier
    rule_id: Identifier
    owner_kind: OwnershipKind
    owner_id: Identifier
    owner_device_id: Identifier | None = None
    version: Annotated[int, Field(ge=1)]
    lease_expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("lease_expires_at", "created_at", "updated_at")
    @classmethod
    def normalize_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _aware(value)

    @model_validator(mode="after")
    def consistent_owner(self) -> Self:
        if self.owner_kind is OwnershipKind.LOCAL_HOST:
            if (
                self.owner_id != self.host_id
                or self.owner_device_id is not None
                or self.lease_expires_at is not None
            ):
                raise ValueError("local ownership must name only the host")
        elif (
            self.owner_device_id is None
            or self.owner_id != self.owner_device_id
            or self.lease_expires_at is None
        ):
            raise ValueError("device ownership must name one leased device")
        return self


class VisibleProactivityState(CoreModel):
    candidate_id: Identifier
    feature: FeatureName
    dispatch_state: DispatchState
    notification_state: NotificationState
    owner_kind: OwnershipKind
    owned_by_this_device: bool
    ownership_version: Annotated[int, Field(ge=1)]
    lease_expires_at: datetime | None = None
    available_at: datetime
    expires_at: datetime
    generic_content_only: Literal[True] = True

    @field_validator("lease_expires_at", "available_at", "expires_at")
    @classmethod
    def normalize_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _aware(value)


class OwnershipEvent(CoreModel):
    sequence: Annotated[int, Field(ge=1)]
    id: Identifier
    host_id: Identifier
    candidate_id: Identifier
    event_type: OwnershipEventType
    reason_code: Annotated[str, Field(min_length=1, max_length=100)]
    owner_kind: OwnershipKind
    owner_device_id: Identifier | None = None
    version: Annotated[int, Field(ge=1)]
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("ownership timestamps must include a timezone")
    return value.astimezone(UTC)
