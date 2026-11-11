"""Foreground calendar reads, conflict evidence and unsent exact-source proposals."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import ValidationError

from jarvis.proactivity.models import (
    ProactivityBudget,
    ProactivityProposal,
    ProactivityProvenance,
    ProactivityScope,
    ProposalSource,
    TriggerKind,
    TriggerSchedule,
)
from jarvis.proactivity.policy import HostProactivityPolicy

from .models import (
    CalendarChangeProposal,
    CalendarError,
    CalendarOccurrence,
    CalendarSnapshot,
    CalendarWindow,
    aware,
)


class CalendarReadProvider(Protocol):
    async def read(self, window: CalendarWindow) -> CalendarSnapshot: ...


def conflicts(
    events: tuple[CalendarOccurrence, ...], window: CalendarWindow, *, exclude: str | None = None
) -> tuple[str, ...]:
    return tuple(
        e.occurrence_id
        for e in events
        if e.occurrence_id != exclude
        and e.busy
        and not e.cancelled
        and e.start < window.end
        and e.end > window.start
    )


class CalendarService:
    def __init__(
        self,
        provider: CalendarReadProvider,
        *,
        source_id: str,
        enabled: bool = False,
        source_kind: Literal["local-export", "provider"] = "local-export",
        control_enabled: Callable[[bool], None] | None = None,
    ) -> None:
        self.provider, self.source_id = provider, source_id
        self.source_kind = source_kind
        self._control_enabled = control_enabled
        self._generation = 0
        self.enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        if self._control_enabled is not None:
            self._control_enabled(value)
        self._generation += 1
        self._enabled = value

    async def read(self, window: CalendarWindow) -> CalendarSnapshot:
        if not self.enabled:
            raise CalendarError("calendar_disabled")
        generation = self._generation
        try:
            async with asyncio.timeout(5):
                received = await self.provider.read(window)
                snapshot = CalendarSnapshot.model_validate(
                    received.model_dump(warnings=False)
                    if isinstance(received, CalendarSnapshot)
                    else received
                )
            if not self.enabled or generation != self._generation:
                raise CalendarError("calendar_disabled")
            if (
                snapshot.source_id != self.source_id
                or snapshot.window != window
                or snapshot.source_kind != self.source_kind
            ):
                raise CalendarError("calendar_provider_provenance")
            if snapshot.freshness(datetime.now(UTC)) == "stale":
                raise CalendarError("calendar_provider_stale")
            return snapshot
        except TimeoutError:
            raise CalendarError("calendar_timeout") from None
        except ValidationError:
            raise CalendarError("calendar_provider_protocol") from None
        except CalendarError as exc:
            raise CalendarError(exc.code) from None
        except Exception:
            raise CalendarError("calendar_provider_unavailable") from None

    async def prepare(
        self,
        window: CalendarWindow,
        *,
        expected_revision: str,
        occurrence_id: str,
        operation: Literal["update", "cancel"],
        replacement: CalendarWindow | None = None,
    ) -> CalendarChangeProposal:
        if (operation == "update") != (replacement is not None):
            raise CalendarError("calendar_proposal_shape")
        # Reacquire source; stale/cached proposals cannot silently bind a different event version.
        snapshot = await self.read(window)
        if snapshot.revision != expected_revision:
            raise CalendarError("calendar_source_changed")
        event = next((e for e in snapshot.events if e.occurrence_id == occurrence_id), None)
        if event is None or event.cancelled:
            raise CalendarError("calendar_occurrence_unavailable")
        if replacement is not None and (
            replacement.start < window.start or replacement.end > window.end
        ):
            raise CalendarError("calendar_conflict_window_required")
        return CalendarChangeProposal(
            source_id=snapshot.source_id,
            revision=snapshot.revision,
            occurrence_id=occurrence_id,
            operation=operation,
            replacement=replacement,
            conflicts=()
            if replacement is None
            else conflicts(snapshot.events, replacement, exclude=occurrence_id),
        )


def reminder_proposal(
    *, title: str, at: datetime, timezone: str, now: datetime
) -> ProactivityProposal:
    """Owner-supplied inputs only; returns existing inert draft, never stores/activates it."""
    timestamp, instant = aware(now), aware(at)
    if not timestamp < instant < timestamp + timedelta(days=30):
        raise CalendarError("reminder_time_limit")
    try:
        local = instant.astimezone(ZoneInfo(timezone))
    except (ValueError, ZoneInfoNotFoundError):
        raise CalendarError("calendar_timezone_invalid") from None
    proposal = ProactivityProposal(
        title=title,
        feature="calendar.reminder",
        schedule=TriggerSchedule(
            kind=TriggerKind.ONCE,
            timezone=timezone,
            local_date=local.date(),
            local_time=local.time().replace(tzinfo=None),
            fold=local.fold
            if local.replace(fold=0).utcoffset() != local.replace(fold=1).utcoffset()
            else None,
        ),
        budget=ProactivityBudget(max_candidates_per_day=1),
        scope=ProactivityScope(),
        provenance=ProactivityProvenance(
            source_type=ProposalSource.HOST, source_id="source:local-operator"
        ),
        created_at=timestamp,
        expires_at=min(timestamp + timedelta(days=30), instant + timedelta(minutes=5)),
    )
    HostProactivityPolicy().preview(proposal, now=timestamp)
    return proposal
