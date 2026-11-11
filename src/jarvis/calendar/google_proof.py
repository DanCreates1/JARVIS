"""One explicitly approved primary-calendar read; aggregate evidence only."""

from __future__ import annotations

from datetime import timedelta

from .google import GoogleCalendarReadProvider
from .models import CalendarError, CalendarSnapshot, CalendarWindow
from .service import CalendarService, conflicts


def proof_window(window: CalendarWindow) -> CalendarWindow:
    if (
        window.start.microsecond
        or window.end.microsecond
        or window.end - window.start > timedelta(days=7)
    ):
        raise CalendarError("calendar_proof_configuration")
    return window


async def selected_calendar_proof(
    provider: GoogleCalendarReadProvider, window: CalendarWindow
) -> dict[str, bool | int]:
    proof_window(window)
    if provider._max_events != 100 or provider._calendar != "primary":
        raise CalendarError("calendar_proof_configuration")
    service = CalendarService(
        provider, source_id=provider.source_id, source_kind="provider", enabled=True
    )
    try:
        snapshot = await service.read(window)

        class Observed:
            async def read(self, requested: CalendarWindow) -> CalendarSnapshot:
                if requested != window:
                    raise CalendarError("calendar_proof_configuration")
                return snapshot

        # Use the exact observed volatile evidence. No second network acquisition.
        observed = CalendarService(
            Observed(), source_id=provider.source_id, source_kind="provider", enabled=True
        )
        event = next((e for e in snapshot.events if not e.cancelled), None)
        prepared = False
        if event is not None:
            proposal = await observed.prepare(
                window,
                expected_revision=snapshot.revision,
                occurrence_id=event.occurrence_id,
                operation="cancel",
            )
            if proposal.written or proposal.approval_granted:
                raise CalendarError("calendar_proof_failed")
            prepared = True
        pairs = {
            tuple(sorted((e.occurrence_id, other)))
            for e in snapshot.events
            if e.busy and not e.cancelled
            for other in conflicts(
                snapshot.events,
                CalendarWindow(start=max(e.start, window.start), end=min(e.end, window.end)),
                exclude=e.occurrence_id,
            )
        }
        return {
            "read_pass": True,
            "events": len(snapshot.events),
            "conflict_pairs": len(pairs),
            "proposal_prepared": prepared,
            "preparation_pass": prepared,
            "availability_proven": False,
            "provider_freshness_known": False,
            "calendar_cache": False,
            "proposal_written": False,
            "approval_granted": False,
            "cloud_calls": 0,
            "provider_writes": 0,
            "cost_usd": 0,
        }
    finally:
        service.enabled = False
        provider.enabled = False
