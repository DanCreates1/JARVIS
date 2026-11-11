"""Bounded provider-neutral calendar evidence and inert proposals."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from jarvis.core.models import CoreModel

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_ERROR_CODES = frozenset(
    [
        "calendar_timezone_required",
        "calendar_window_limit",
        "calendar_event_interval",
        "calendar_duplicate_occurrence",
        "calendar_provider_window",
        "calendar_proposal_shape",
        "calendar_local_path_required",
        "calendar_file_type",
        "calendar_timezone_invalid",
        "calendar_local_volume_required",
        "calendar_link_denied",
        "calendar_size",
        "calendar_source_changed",
        "calendar_source_unavailable",
        "calendar_disabled",
        "calendar_provider_provenance",
        "calendar_provider_stale",
        "calendar_timeout",
        "calendar_provider_protocol",
        "calendar_provider_unavailable",
        "calendar_occurrence_unavailable",
        "calendar_conflict_window_required",
        "reminder_time_limit",
        "calendar_dst_gap",
        "calendar_unsupported_parameter",
        "calendar_unsupported_date",
        "calendar_invalid_date",
        "calendar_invalid_text",
        "calendar_encoding",
        "calendar_controls",
        "calendar_structure",
        "calendar_line_limit",
        "calendar_event_limit",
        "calendar_invalid_parameter",
        "calendar_unsupported_component",
        "calendar_unsupported_header",
        "calendar_unsupported_property",
        "calendar_duplicate_property",
        "calendar_unsupported_scale",
        "calendar_required_property",
        "calendar_duplicate_uid",
        "calendar_invalid_timestamp",
        "calendar_mixed_date_types",
        "calendar_end_required",
        "calendar_title_limit",
        "calendar_invalid_status",
        "calendar_invalid_sequence",
        "calendar_recurrence_limit",
        "calendar_unsupported_recurrence",
        "calendar_date_overflow",
        "calendar_occurrence_limit",
    ]
)


class CalendarError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = (
            code if type(code) is str and code in _ERROR_CODES else "calendar_provider_unavailable"
        )
        super().__init__(self.code)


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CalendarError("calendar_timezone_required")
    return value.astimezone(UTC)


class CalendarWindow(CoreModel):
    start: datetime
    end: datetime

    _aware = field_validator("start", "end")(aware)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if not timedelta(0) < self.end - self.start <= timedelta(days=31):
            raise CalendarError("calendar_window_limit")
        return self


class CalendarOccurrence(CoreModel):
    event_id: Digest
    occurrence_id: Digest
    title: Annotated[str, Field(max_length=512)]
    start: datetime
    end: datetime
    all_day: bool = False
    cancelled: bool = False
    busy: bool = True

    _aware = field_validator("start", "end")(aware)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end <= self.start:
            raise CalendarError("calendar_event_interval")
        return self


class CalendarSnapshot(CoreModel):
    source_id: Digest
    revision: Digest
    window: CalendarWindow
    observed_at: datetime
    events: Annotated[tuple[CalendarOccurrence, ...], Field(max_length=512)]
    source_kind: Literal["local-export", "provider"] = "local-export"
    provider_freshness: Literal["unknown"] = "unknown"
    complete: Literal[True] = True

    _aware = field_validator("observed_at")(aware)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if len({e.occurrence_id for e in self.events}) != len(self.events):
            raise CalendarError("calendar_duplicate_occurrence")
        if any(e.start >= self.window.end or e.end <= self.window.start for e in self.events):
            raise CalendarError("calendar_provider_window")
        return self

    def freshness(self, now: datetime) -> Literal["observed-export", "observed-provider", "stale"]:
        age = aware(now) - self.observed_at
        if not timedelta(0) <= age < timedelta(minutes=5):
            return "stale"
        return "observed-export" if self.source_kind == "local-export" else "observed-provider"


class CalendarChangeProposal(CoreModel):
    source_id: Digest
    revision: Digest
    occurrence_id: Digest
    operation: Literal["update", "cancel"]
    replacement: CalendarWindow | None = None
    conflicts: tuple[Digest, ...] = ()
    written: Literal[False] = False
    approval_granted: Literal[False] = False

    @model_validator(mode="after")
    def shape(self) -> Self:
        if (self.operation == "update") != (self.replacement is not None):
            raise CalendarError("calendar_proposal_shape")
        return self
