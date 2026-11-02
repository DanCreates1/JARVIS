"""Trusted-local foreground entry points. Private output never enters a model or browser."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import typer
from pydantic import ValidationError

from .local import LocalCalendar
from .models import CalendarError, CalendarWindow
from .service import CalendarService, conflicts, reminder_proposal

app = typer.Typer(no_args_is_help=True, help="Explicit local calendar reads and inert proposals.")


def _time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise CalendarError("calendar_invalid_date") from None


def _print(value: str) -> None:
    # ASCII JSON escapes control/bidi characters and bypasses Rich markup interpretation.
    typer.echo(json.dumps(json.loads(value), ensure_ascii=True))


def _error(exc: ValueError) -> None:
    typer.echo(exc.code if isinstance(exc, CalendarError) else "calendar_invalid_input", err=True)
    raise typer.Exit(1)


def _service(path: Path, timezone: str) -> CalendarService:
    provider = LocalCalendar(path, timezone=timezone)
    return CalendarService(provider, source_id=provider.source_id, enabled=True)


@app.command("inspect")
def inspect_calendar(path: Path, start: str, end: str, timezone: str = typer.Option(...)) -> None:
    """Read exactly one explicit .ics file; show private events, freshness and conflict pairs."""
    try:
        window = CalendarWindow(start=_time(start), end=_time(end))
        snapshot = asyncio.run(_service(path, timezone).read(window))
        pairs = sorted(
            {
                tuple(sorted((e.occurrence_id, other)))
                for e in snapshot.events
                if e.busy and not e.cancelled
                for other in conflicts(
                    snapshot.events,
                    CalendarWindow(start=max(e.start, window.start), end=min(e.end, window.end)),
                    exclude=e.occurrence_id,
                )
            }
        )
        _print(
            json.dumps(
                {
                    "snapshot": snapshot.model_dump(mode="json"),
                    "freshness": snapshot.freshness(datetime.now(UTC)),
                    "conflict_pairs": pairs,
                    "availability_proven": False,
                }
            )
        )
    except (CalendarError, ValidationError) as exc:
        _error(exc)


@app.command("prepare")
def prepare_calendar(
    path: Path,
    start: str,
    end: str,
    revision: str,
    occurrence_id: str,
    operation: str,
    timezone: str = typer.Option(...),
    replacement_start: str | None = None,
    replacement_end: str | None = None,
) -> None:
    """Re-read exact revision and prepare one unsent occurrence change; never write an event."""
    try:
        if operation not in {"update", "cancel"}:
            raise CalendarError("calendar_proposal_shape")
        op: Literal["update", "cancel"] = "update" if operation == "update" else "cancel"
        if (replacement_start is None) != (replacement_end is None):
            raise CalendarError("calendar_proposal_shape")
        replacement = (
            None
            if replacement_start is None
            else CalendarWindow(start=_time(replacement_start), end=_time(replacement_end or ""))
        )
        proposal = asyncio.run(
            _service(path, timezone).prepare(
                CalendarWindow(start=_time(start), end=_time(end)),
                expected_revision=revision,
                occurrence_id=occurrence_id,
                operation=op,
                replacement=replacement,
            )
        )
        _print(proposal.model_dump_json())
    except (CalendarError, ValidationError) as exc:
        _error(exc)


@app.command("reminder")
def reminder(title: str, at: str, timezone: str = typer.Option(...)) -> None:
    """Print owner-authored inert proposal; use proactive create/review/activate separately."""
    try:
        _print(
            reminder_proposal(
                title=title, at=_time(at), timezone=timezone, now=datetime.now(UTC)
            ).model_dump_json()
        )
    except (CalendarError, ValidationError) as exc:
        _error(exc)


@app.command("google-plan")
def google_plan() -> None:
    """Show selected primary-calendar read plan. No account/credential read, login or activation."""
    from .google import GOOGLE_CALENDAR_SCOPES

    _print(
        json.dumps(
            {
                "provider": "google",
                "target": "primary",
                "account": "same-personal-account-as-phase-15",
                "enabled": False,
                "scopes_proposed": sorted(GOOGLE_CALENDAR_SCOPES),
                "initial_proof_max_days": 7,
                "initial_proof_max_events": 100,
                "operation_seconds": 5,
                "identity_gets": 1,
                "calendar_gets": 1,
                "login_implemented": False,
                "owner_credentials_accessed": False,
                "approval_granted": False,
                "provider_writes": 0,
                "background_worker": False,
            }
        )
    )
