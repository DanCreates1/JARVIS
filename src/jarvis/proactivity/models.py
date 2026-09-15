"""Strict Phase 11A contracts for inert proactive suggestion policy."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from jarvis.core.models import CoreModel, Identifier

FeatureName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    ),
]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
TimezoneName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9_+.-]+(?:/[A-Za-z0-9_+.-]+)*$",
    ),
]


class TriggerKind(StrEnum):
    ONCE = "once"
    DAILY = "daily"
    EVENT = "event"


class RuleStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"


class ProposalSource(StrEnum):
    HOST = "host"
    MODEL = "model"
    RESEARCH = "research"
    API = "api"
    TEST = "test"


class DataClass(StrEnum):
    PUBLIC = "public"
    MEMORY = "memory"
    RESEARCH = "research"
    TASK_STATE = "task_state"
    DEVICE_STATUS = "device_status"


class EvaluationCode(StrEnum):
    CANDIDATE_CREATED = "candidate_created"
    GLOBAL_DISABLED = "global_disabled"
    FEATURE_DISABLED = "feature_disabled"
    RULE_INACTIVE = "rule_inactive"
    RULE_EXPIRED = "rule_expired"
    NOT_DUE = "not_due"
    STALE_OCCURRENCE = "stale_occurrence"
    INVALID_LOCAL_TIME = "invalid_local_time"
    CLOCK_SKEW = "clock_skew"
    EVENT_REQUIRED = "event_required"
    EVENT_MISMATCH = "event_mismatch"
    QUIET_HOURS = "quiet_hours"
    HOURLY_LIMIT = "hourly_limit"
    DAILY_LIMIT = "daily_limit"
    ATTENTION_LIMIT = "attention_limit"
    CANDIDATE_BUSY = "candidate_busy"
    DUPLICATE = "duplicate"


class ProactivityEventType(StrEnum):
    RULE_CREATED = "rule_created"
    RULE_ACTIVATED = "rule_activated"
    RULE_DISABLED = "rule_disabled"
    RULE_EXPIRED = "rule_expired"
    CANDIDATE_CREATED = "candidate_created"


class ProactivityProvenance(CoreModel):
    source_type: ProposalSource
    source_id: Identifier
    untrusted: Literal[True] = True


class TriggerSchedule(CoreModel):
    kind: TriggerKind
    timezone: TimezoneName
    local_date: date | None = None
    local_time: time | None = None
    fold: Annotated[int, Field(ge=0, le=1)] | None = None
    event_name: FeatureName | None = None

    @field_validator("local_time")
    @classmethod
    def require_naive_wall_time(cls, value: time | None) -> time | None:
        if value is not None and value.tzinfo is not None:
            raise ValueError("schedule local_time must not include a UTC offset")
        return value

    @model_validator(mode="after")
    def require_kind_shape(self) -> Self:
        if self.kind is TriggerKind.ONCE:
            if self.local_date is None or self.local_time is None or self.event_name is not None:
                raise ValueError("one-time schedule requires local_date/local_time only")
        elif self.kind is TriggerKind.DAILY:
            if (
                self.local_date is not None
                or self.local_time is None
                or self.event_name is not None
            ):
                raise ValueError("daily schedule requires local_time only")
        elif self.local_date is not None or self.local_time is not None or self.fold is not None:
            raise ValueError("event trigger cannot contain wall-clock fields")
        elif self.event_name is None:
            raise ValueError("event trigger requires event_name")
        return self


class QuietHours(CoreModel):
    start: time
    end: time
    weekdays: Annotated[tuple[int, ...], Field(min_length=1, max_length=7)] = tuple(range(7))

    @field_validator("start", "end")
    @classmethod
    def require_naive_time(cls, value: time) -> time:
        if value.tzinfo is not None:
            raise ValueError("quiet-hour times must not include a UTC offset")
        return value

    @field_validator("weekdays")
    @classmethod
    def normalize_weekdays(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(day < 0 or day > 6 for day in value) or len(value) != len(set(value)):
            raise ValueError("quiet-hour weekdays must be unique values from 0 through 6")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def require_nonempty_window(self) -> Self:
        if self.start == self.end:
            raise ValueError("quiet hours cannot cover an ambiguous full day")
        return self


class ProactivityBudget(CoreModel):
    max_candidates_per_hour: Annotated[int, Field(ge=1, le=6)] = 1
    max_candidates_per_day: Annotated[int, Field(ge=1, le=24)] = 3
    max_attention_seconds_per_day: Annotated[int, Field(ge=1, le=300)] = 60
    max_task_steps: Annotated[int, Field(ge=0, le=10)] = 0
    max_provider_requests: Annotated[int, Field(ge=0, le=2)] = 0
    max_tool_calls: Annotated[int, Field(ge=0, le=5)] = 0
    max_tokens: Annotated[int, Field(ge=0, le=10_000)] = 0
    max_cost_usd: Literal[0] = 0
    max_concurrency: Literal[1] = 1

    @model_validator(mode="after")
    def require_hour_within_day(self) -> Self:
        if self.max_candidates_per_hour > self.max_candidates_per_day:
            raise ValueError("hourly candidate limit cannot exceed daily limit")
        return self


class ProactivityScope(CoreModel):
    data_classes: Annotated[tuple[DataClass, ...], Field(max_length=5)] = ()
    task_template_id: Identifier | None = None
    cloud_disclosure_allowed: Literal[False] = False
    effect_execution_allowed: Literal[False] = False
    notification_send_allowed: Literal[False] = False
    approval_creation_allowed: Literal[False] = False
    retains_candidate_content: Literal[False] = False

    @field_validator("data_classes")
    @classmethod
    def unique_data_classes(cls, value: tuple[DataClass, ...]) -> tuple[DataClass, ...]:
        if len(value) != len(set(value)):
            raise ValueError("data classes must be unique")
        return tuple(sorted(value, key=str))


class ProactivityProposal(CoreModel):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    feature: FeatureName
    schedule: TriggerSchedule
    quiet_hours: tuple[QuietHours, ...] = ()
    budget: ProactivityBudget = Field(default_factory=ProactivityBudget)
    scope: ProactivityScope = Field(default_factory=ProactivityScope)
    estimated_attention_seconds: Annotated[int, Field(ge=1, le=60)] = 10
    provenance: ProactivityProvenance
    created_at: datetime
    expires_at: datetime

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("proposal title cannot be blank")
        return normalized

    @field_validator("created_at", "expires_at")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("proposal expiry must follow creation")
        if len(self.quiet_hours) > 8:
            raise ValueError("at most eight quiet-hour windows are allowed")
        return self


class RulePreview(CoreModel):
    proposal: ProactivityProposal
    proposal_sha256: Digest
    next_occurrence_at: datetime | None
    mode: Literal["suggestion"] = "suggestion"
    execution_authorized: Literal[False] = False

    @field_validator("next_occurrence_at")
    @classmethod
    def normalize_next_occurrence(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _aware(value)


class ProactivityRule(CoreModel):
    id: Identifier
    host_id: Identifier
    proposal: ProactivityProposal
    proposal_sha256: Digest
    status: RuleStatus = RuleStatus.DRAFT
    version: Annotated[int, Field(ge=1)] = 1
    created_at: datetime
    updated_at: datetime
    activated_at: datetime | None = None

    @field_validator("created_at", "updated_at", "activated_at")
    @classmethod
    def normalize_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _aware(value)


class TrustedActivation(CoreModel):
    approval_id: Identifier
    host_id: Identifier
    rule_id: Identifier
    expected_version: Annotated[int, Field(ge=1)]
    expected_proposal_sha256: Digest
    interface: Literal["trusted_local_cli"] = "trusted_local_cli"
    approved_at: datetime
    expires_at: datetime

    @field_validator("approved_at", "expires_at")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def require_short_lived_approval(self) -> Self:
        if self.expires_at <= self.approved_at:
            raise ValueError("activation approval expiry must follow approval")
        if (self.expires_at - self.approved_at).total_seconds() > 300:
            raise ValueError("activation approval cannot live longer than five minutes")
        return self


class TriggerEvent(CoreModel):
    id: Identifier
    name: FeatureName
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value)


class EvaluationDecision(CoreModel):
    rule_id: Identifier
    code: EvaluationCode
    eligible: bool
    occurrence_key: Digest | None = None
    scheduled_for: datetime | None = None
    execution_authorized: Literal[False] = False

    @field_validator("scheduled_for")
    @classmethod
    def normalize_scheduled_time(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _aware(value)


class SuggestionCandidate(CoreModel):
    id: Identifier
    host_id: Identifier
    rule_id: Identifier
    feature: FeatureName
    occurrence_key: Digest
    scheduled_for: datetime
    attention_seconds: Annotated[int, Field(ge=1, le=60)]
    created_at: datetime
    expires_at: datetime
    execution_authorized: Literal[False] = False
    notification_sent: Literal[False] = False
    content_retained: Literal[False] = False

    @field_validator("scheduled_for", "created_at", "expires_at")
    @classmethod
    def normalize_times(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("candidate expiry must follow creation")
        return self


class ProactivityExplanation(CoreModel):
    """Sanitized local explanation for one inert proactive suggestion."""

    candidate_id: Identifier
    rule_id: Identifier
    feature: FeatureName
    trigger_kind: TriggerKind
    scheduled_for: datetime
    decision_reason: Annotated[str, Field(min_length=1, max_length=100)]
    proposal_source: ProposalSource
    declared_data_classes: Annotated[tuple[DataClass, ...], Field(max_length=5)] = ()
    used_data_classes: Annotated[tuple[DataClass, ...], Field(max_length=0)] = ()
    tools_used: Annotated[tuple[Identifier, ...], Field(max_length=0)] = ()
    providers_used: Annotated[tuple[Identifier, ...], Field(max_length=0)] = ()
    effective_audience: Literal["local_host", "scoped_pwa_device"]
    notification_channel: Literal["local_inbox"] = "local_inbox"
    provider_requests: Literal[0] = 0
    tool_calls: Literal[0] = 0
    task_executions: Literal[0] = 0
    effects_executed: Literal[0] = 0
    external_notifications_sent: Literal[0] = 0
    cloud_cost_usd: Literal[0] = 0
    suggestion_only: Literal[True] = True
    content_minimized: Literal[True] = True

    @field_validator("scheduled_for")
    @classmethod
    def normalize_scheduled_for(cls, value: datetime) -> datetime:
        return _aware(value)


class ProactivityEvent(CoreModel):
    sequence: Annotated[int, Field(ge=1)]
    id: Identifier
    host_id: Identifier
    rule_id: Identifier
    candidate_id: Identifier | None = None
    event_type: ProactivityEventType
    reason_code: Annotated[str, Field(min_length=1, max_length=100)]
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value)


class RuleDeletionReceipt(CoreModel):
    rule_id: Identifier
    deleted_candidates: Annotated[int, Field(ge=0)]
    deleted_events: Annotated[int, Field(ge=0)]
    deleted_at: datetime

    @field_validator("deleted_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value)


class ProactivityExportReceipt(CoreModel):
    path: Annotated[str, Field(min_length=1, max_length=4_096)]
    rule_count: Annotated[int, Field(ge=0)]
    candidate_count: Annotated[int, Field(ge=0)]
    event_count: Annotated[int, Field(ge=0)]
    exported_at: datetime

    @field_validator("exported_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return _aware(value)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("proactivity timestamps must include a timezone")
    return value.astimezone(UTC)
