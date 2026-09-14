"""Content-minimized Phase 11B runner and local notification contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator

from jarvis.core.models import CoreModel, Identifier

from .models import Digest, FeatureName


class DispatchState(StrEnum):
    CLAIMED = "claimed"
    NOTIFIED = "notified"
    SNOOZED = "snoozed"
    HANDED_OFF = "handed_off"
    DISMISSED = "dismissed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


class NotificationState(StrEnum):
    ACTIVE = "active"
    SNOOZED = "snoozed"
    HANDED_OFF = "handed_off"
    DISMISSED = "dismissed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class RunnerEventType(StrEnum):
    CANDIDATE_CLAIMED = "candidate_claimed"
    LEASE_RECOVERED = "lease_recovered"
    NOTIFICATION_READY = "notification_ready"
    NOTIFICATION_RESURFACED = "notification_resurfaced"
    SNOOZED = "snoozed"
    DISMISSED = "dismissed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    HANDOFF_CREATED = "handoff_created"
    DELIVERY_FAILED = "delivery_failed"


class CandidateDispatch(CoreModel):
    candidate_id: Identifier
    host_id: Identifier
    rule_id: Identifier
    state: DispatchState
    version: Annotated[int, Field(ge=1)]
    attempts: Annotated[int, Field(ge=1, le=10)]
    lease_id: Identifier | None = None
    lease_expires_at: datetime | None = None
    notification_id: Identifier | None = None
    snoozed_until: datetime | None = None
    task_id: Identifier | None = None
    task_version: Annotated[int, Field(ge=1)] | None = None
    task_plan_sha256: Digest | None = None
    failure_code: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime

    @field_validator("lease_expires_at", "snoozed_until", "expires_at", "created_at", "updated_at")
    @classmethod
    def normalize_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _aware(value)


class LocalNotification(CoreModel):
    id: Identifier
    host_id: Identifier
    rule_id: Identifier
    candidate_id: Identifier
    dispatch_version: Annotated[int, Field(ge=1)]
    feature: FeatureName
    state: NotificationState
    available_at: datetime
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    generic_content_only: Literal[True] = True

    @field_validator("available_at", "expires_at", "created_at", "updated_at")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return _aware(value)


class RunnerEvent(CoreModel):
    sequence: Annotated[int, Field(ge=1)]
    id: Identifier
    host_id: Identifier
    rule_id: Identifier
    candidate_id: Identifier
    event_type: RunnerEventType
    reason_code: Annotated[str, Field(min_length=1, max_length=100)]
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value)


class RunnerTickResult(CoreModel):
    rules_evaluated: Annotated[int, Field(ge=0)] = 0
    candidates_created: Annotated[int, Field(ge=0)] = 0
    notifications_ready: Annotated[int, Field(ge=0)] = 0
    recovered_leases: Annotated[int, Field(ge=0)] = 0
    denied: Annotated[int, Field(ge=0)] = 0
    effects_executed: Literal[0] = 0


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("runner timestamps must include a timezone")
    return value.astimezone(UTC)
