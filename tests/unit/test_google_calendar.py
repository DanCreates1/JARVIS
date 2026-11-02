"""Synthetic Google protocol fixtures. No owner accounts, grants or calendar data."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from jarvis.calendar.google import (
    GOOGLE_CALENDAR_SCOPES,
    GoogleCalendarAccessToken,
    GoogleCalendarReadProvider,
    build_google_calendar_service,
)
from jarvis.calendar.models import CalendarError, CalendarWindow
from jarvis.calendar.service import conflicts
from jarvis.cli import app

ACCOUNT = "synthetic-owner@gmail.com"
WINDOW = CalendarWindow(
    start=datetime(2026, 11, 1, tzinfo=UTC), end=datetime(2026, 11, 8, tzinfo=UTC)
)


def event(identifier: str = "fixture1", **changes: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": identifier,
        "etag": '"event-v1"',
        "status": "confirmed",
        "summary": "Synthetic [red] appointment",
        "start": {"dateTime": "2026-11-03T09:00:00-05:00", "timeZone": "America/Toronto"},
        "end": {"dateTime": "2026-11-03T10:00:00-05:00", "timeZone": "America/Toronto"},
    }
    value.update(changes)
    return value


def listing(*items: dict[str, Any], **changes: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "kind": "calendar#events",
        "etag": '"collection-v1"',
        "timeZone": "America/Toronto",
        "accessRole": "owner",
        "items": list(items),
    }
    value.update(changes)
    return value


class Tokens:
    def __init__(self, token: GoogleCalendarAccessToken | None = None) -> None:
        self.token = token or GoogleCalendarAccessToken(
            ACCOUNT, "synthetic-access-token", datetime.now(UTC) + timedelta(hours=1)
        )
        self.calls = 0

    async def acquire(self) -> GoogleCalendarAccessToken:
        self.calls += 1
        return self.token


class Body(httpx.AsyncByteStream):
    def __init__(self, value: bytes) -> None:
        self.value = value

    async def __aiter__(self):
        yield self.value


class Wire:
    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self.data = listing(event()) if data is None else data
        self.identity: dict[str, Any] = {"email": ACCOUNT, "verified_email": True}
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.headers: dict[str, str] = {}
        self.raw: bytes | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.method == "GET" and request.url.host == "www.googleapis.com"
        assert request.headers["authorization"] == "Bearer synthetic-access-token"
        assert request.headers["accept-encoding"] == "identity"
        assert "cookie" not in request.headers and "access_token" not in str(request.url)
        if request.url.path == "/oauth2/v2/userinfo":
            return httpx.Response(
                200,
                stream=Body(json.dumps(self.identity).encode()),
                headers={"set-cookie": "private=deny; Secure", "content-type": "application/json"},
            )
        headers = {"content-type": "application/json", **self.headers}
        return httpx.Response(
            self.status,
            stream=Body(self.raw if self.raw is not None else json.dumps(self.data).encode()),
            headers=headers,
        )


def provider(
    wire: Wire | None = None,
    tokens: Tokens | None = None,
    *,
    enabled: bool = True,
    account: str = ACCOUNT,
    calendar_id: str = "primary",
) -> GoogleCalendarReadProvider:
    return GoogleCalendarReadProvider(
        account,
        tokens or Tokens(),
        calendar_id=calendar_id,
        enabled=enabled,
        transport=httpx.MockTransport(wire or Wire()),
    )


async def test_real_service_read_prepare_identity_and_no_extra_disclosure() -> None:
    wire, tokens = Wire(), Tokens()
    service = build_google_calendar_service(
        ACCOUNT, tokens, enabled=True, transport=httpx.MockTransport(wire)
    )
    first = await service.read(WINDOW)
    assert first.source_kind == "provider" and first.provider_freshness == "unknown"
    assert first.events[0].start == datetime(2026, 11, 3, 14, tzinfo=UTC)
    assert first.events[0].end == datetime(2026, 11, 3, 15, tzinfo=UTC)
    assert len(wire.requests) == 2 and tokens.calls == 1
    request = wire.requests[1]
    assert request.url.path == "/calendar/v3/calendars/primary/events"
    assert (
        request.url.params["singleEvents"] == "true" and request.url.params["maxResults"] == "512"
    )
    assert request.url.params["timeMin"] == WINDOW.start.isoformat()
    assert request.url.params["timeMax"] == WINDOW.end.isoformat()
    assert (
        "description" not in request.url.params["fields"]
        and "attendees" not in request.url.params["fields"]
    )
    proposal = await service.prepare(
        WINDOW,
        expected_revision=first.revision,
        occurrence_id=first.events[0].occurrence_id,
        operation="cancel",
    )
    assert not proposal.written and not proposal.approval_granted
    assert len(wire.requests) == 4 and tokens.calls == 2
    assert (
        "synthetic-owner" not in first.model_dump_json()
        and "fixture1" not in first.model_dump_json()
    )
    assert "synthetic-access" not in repr(tokens.token)


async def test_stable_revision_reorder_sync_token_and_source_change_refusal() -> None:
    wire = Wire(listing(event(), event("fixture2"), nextSyncToken="volatile-1"))
    svc = build_google_calendar_service(
        ACCOUNT, Tokens(), enabled=True, transport=httpx.MockTransport(wire)
    )
    first = await svc.read(WINDOW)
    wire.data["items"].reverse()
    wire.data["nextSyncToken"] = "volatile-2"
    assert (await svc.read(WINDOW)).revision == first.revision
    wire.data["items"][0]["etag"] = '"changed"'
    with pytest.raises(CalendarError, match="calendar_source_changed"):
        await svc.prepare(
            WINDOW,
            expected_revision=first.revision,
            occurrence_id=first.events[0].occurrence_id,
            operation="cancel",
        )


async def test_calendar_dst_all_day_moved_instance_cancellation_and_conflicts() -> None:
    repeated = event(
        "series_20261101T053000Z",
        recurringEventId="series",
        originalStartTime={"dateTime": "2026-11-01T01:30:00-04:00", "timeZone": "America/Toronto"},
    )
    # Moved exception retains original instance identity, independent of new actual start.
    day = event("allDay", start={"date": "2026-11-01"}, end={"date": "2026-11-02"})
    tombstone = {
        "id": "deleted-instance",
        "status": "cancelled",
        "recurringEventId": "series",
        "originalStartTime": {"dateTime": "2026-11-02T09:00:00-05:00"},
    }
    wire = Wire(listing(day, repeated, tombstone, event("free", transparency="transparent")))
    adapter = provider(wire)
    first = await adapter.read(WINDOW)
    assert len(first.events) == 3
    assert first.events[0].all_day
    assert first.events[0].start == datetime(2026, 11, 1, 4, tzinfo=UTC)
    assert first.events[0].end == datetime(2026, 11, 2, 5, tzinfo=UTC)
    actual = next(e for e in first.events if e.busy and not e.all_day)
    assert conflicts(first.events, CalendarWindow(start=actual.start, end=actual.end)) == (
        actual.occurrence_id,
    )
    repeated["start"] = {"dateTime": "2026-11-04T09:00:00-05:00"}
    repeated["end"] = {"dateTime": "2026-11-04T10:00:00-05:00"}
    second = await adapter.read(WINDOW)
    assert actual.occurrence_id in {e.occurrence_id for e in second.events}
    assert first.revision != second.revision


@pytest.mark.parametrize(
    "changes",
    [
        {"account": "wrong@gmail.com"},
        {"calendar_id": "other@gmail.com"},
        {"scopes": frozenset()},
        {"scopes": GOOGLE_CALENDAR_SCOPES | {"https://www.googleapis.com/auth/calendar"}},
        {"scopes": frozenset({"https://www.googleapis.com/auth/gmail.readonly"})},
        {"access_token": "secret\r\nInjected: true"},
        {"access_token": "x" * 8193},
        {"access_token": "x" + "=" * 8192},
        {"expires_at": datetime(2020, 1, 1, tzinfo=UTC)},
        {"expires_at": datetime.now(UTC).replace(tzinfo=None)},
    ],
)
async def test_grant_account_calendar_scope_and_token_bounds(changes: dict[str, Any]) -> None:
    wire, tokens = Wire(), Tokens()
    tokens.token = replace(tokens.token, **changes)
    with pytest.raises(CalendarError, match="calendar_credentials_denied"):
        await provider(wire, tokens).read(WINDOW)
    assert not wire.requests


@pytest.mark.parametrize(
    "identity",
    [
        {"email": "other@gmail.com", "verified_email": True},
        {"email": ACCOUNT, "verified_email": False},
        {"email": ACCOUNT, "verified_email": 1},
        {"email": ACCOUNT},
        {"email": ACCOUNT, "verified_email": True, "name": "PRIVATE"},
    ],
)
async def test_identity_mismatch_stops_before_calendar_read(identity: dict[str, Any]) -> None:
    wire = Wire()
    wire.identity = identity
    with pytest.raises(CalendarError, match="calendar_account_mismatch"):
        await provider(wire).read(WINDOW)
    assert len(wire.requests) == 1


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "credentials_denied"),
        (403, "credentials_denied"),
        (404, "source_unavailable"),
        (429, "rate_limited"),
        (500, "provider_unavailable"),
        (302, "provider_unavailable"),
        (204, "provider_unavailable"),
    ],
)
async def test_http_errors_no_retry_redirect_or_private_error(status: int, code: str) -> None:
    wire = Wire()
    wire.status, wire.raw = status, b"PRIVATE PROVIDER ERROR"
    wire.headers["location"] = "https://attacker.invalid/private"
    with pytest.raises(CalendarError, match="calendar_" + code):
        await provider(wire).read(WINDOW)
    assert len(wire.requests) == 2


@pytest.mark.parametrize(
    "headers,raw,code",
    [
        ({"content-type": "text/html"}, b"private", "protocol"),
        ({"content-encoding": "gzip"}, b"private", "protocol"),
        ({"content-length": "-1"}, b"private", "protocol"),
        ({"content-length": "1048577"}, b"", "response_limit"),
        ({"content-length": "1"}, b"{}", "protocol"),
        ({}, b"PRIVATE", "protocol"),
        ({}, b"[]", "protocol"),
        ({}, b'{"a":1,"a":2}', "protocol"),
        ({}, b'{"a": NaN}', "protocol"),
        ({}, b"\xff", "protocol"),
        ({}, b"x" * 1048577, "response_limit"),
    ],
    ids=lambda value: type(value).__name__,
)
async def test_response_bounds_and_malformed_json(
    headers: dict[str, str], raw: bytes, code: str
) -> None:
    wire = Wire()
    wire.headers, wire.raw = headers, raw
    with pytest.raises(CalendarError, match=code):
        await provider(wire).read(WINDOW)


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"kind": "wrong"}, "protocol"),
        ({"accessRole": "reader"}, "owner_required"),
        ({"accessRole": "writer"}, "owner_required"),
        ({"nextPageToken": "next"}, "incomplete"),
        ({"nextPageToken": ""}, "incomplete"),
        ({"nextSyncToken": 1}, "protocol"),
        ({"timeZone": "No/Such"}, "protocol"),
        ({"timeZone": 1}, "timezone_invalid"),
        ({"items": "PRIVATE"}, "occurrence_limit"),
        ({"etag": "bad\nsecret"}, "protocol"),
        ({"unexpected": "PRIVATE"}, "protocol"),
        ({"items": [event(), event()]}, "duplicate_occurrence"),
    ],
)
async def test_whole_snapshot_rejects_incomplete_or_malformed_provider(
    changes: dict[str, Any], code: str
) -> None:
    wire = Wire(listing(event(), **changes))
    with pytest.raises(CalendarError, match=code):
        await provider(wire).read(WINDOW)


@pytest.mark.parametrize(
    "changes",
    [
        {"id": "../escape"},
        {"status": "unknown"},
        {"summary": "x" * 513},
        {"summary": 5},
        {"transparency": "maybe"},
        {"recurrence": ["RRULE:FREQ=DAILY"]},
        {"eventType": "futureUnknown"},
        {"endTimeUnspecified": True},
        {"endTimeUnspecified": 0},
        {"description": "PRIVATE"},
        {"recurringEventId": "series"},
        {"originalStartTime": {"date": "2026-11-03"}},
        {"start": {"dateTime": "2026-11-03T09:00:00"}},
        {"start": {"dateTime": "2026-11-03T09:00:00-00:00"}},
        {"start": {"dateTime": "2026-11-03T09:00:00-04:00", "timeZone": "America/Toronto"}},
        {"start": {"dateTime": "2026-11-03T09:00:00-05:00", "timeZone": "Bad/Zone"}},
        {"start": {"date": "2026-11-03", "dateTime": "2026-11-03T09:00:00-05:00"}},
        {"start": {"date": "2026-11-03", "timeZone": "UTC"}},
        {"start": {"date": "not-date"}},
        {"start": {"dateTime": "2026-13-01T09:00:00Z"}},
        {"end": {"dateTime": "2026-11-03T08:00:00-05:00"}},
        {"end": {"date": "2026-11-04"}},
        {
            "start": {"dateTime": "2026-12-03T09:00:00-05:00"},
            "end": {"dateTime": "2026-12-03T10:00:00-05:00"},
        },
    ],
)
async def test_malformed_event_is_never_silently_omitted(changes: dict[str, Any]) -> None:
    with pytest.raises(CalendarError):
        await provider(Wire(listing(event(**changes)))).read(WINDOW)


async def test_empty_page_capacity_and_subsecond_filter() -> None:
    assert not (await provider(Wire(listing())).read(WINDOW)).events
    data = listing(*(event(str(n)) for n in range(512)))
    assert len((await provider(Wire(data)).read(WINDOW)).events) == 512
    data["items"].append(event("overflow"))
    with pytest.raises(CalendarError, match="occurrence_limit"):
        await provider(Wire(data)).read(WINDOW)
    at = datetime(2026, 11, 3, 14, tzinfo=UTC)
    window = CalendarWindow(
        start=at + timedelta(microseconds=500000), end=at + timedelta(hours=2, microseconds=1)
    )
    fringe = event(
        end={"dateTime": "2026-11-03T14:00:00.200000Z"}, start={"dateTime": "2026-11-03T13:00:00Z"}
    )
    wire = Wire(listing(fringe))
    assert not (await provider(wire).read(window)).events
    assert wire.requests[-1].url.params["timeMax"] == "2026-11-03T16:00:01+00:00"


async def test_default_off_disable_generation_cancellation_and_restart() -> None:
    wire, tokens = Wire(), Tokens()
    dormant = provider(wire, tokens, enabled=False)
    with pytest.raises(CalendarError, match="disabled"):
        await dormant.read(WINDOW)
    assert not wire.requests and tokens.calls == 0
    entered, release = asyncio.Event(), asyncio.Event()

    class Delayed(Tokens):
        async def acquire(self) -> GoogleCalendarAccessToken:
            entered.set()
            await release.wait()
            return self.token

    adapter = provider(wire, Delayed())
    task = asyncio.create_task(adapter.read(WINDOW))
    await entered.wait()
    adapter.enabled = False
    adapter.enabled = True
    release.set()
    with pytest.raises(CalendarError, match="disabled"):
        await task
    release.clear()
    entered.clear()
    task = asyncio.create_task(adapter.read(WINDOW))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not wire.requests
    first = await provider(wire).read(WINDOW)
    second = await provider(wire).read(WINDOW)
    assert first.revision == second.revision and first.events == second.events


async def test_real_operation_timeout_and_private_token_source_exception() -> None:
    cancelled = asyncio.Event()

    class Hanging(Tokens):
        async def acquire(self) -> GoogleCalendarAccessToken:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
            return self.token

    with pytest.raises(CalendarError, match="calendar_timeout"):
        await provider(tokens=Hanging()).read(WINDOW)
    assert cancelled.is_set()

    class Broken(Tokens):
        async def acquire(self) -> GoogleCalendarAccessToken:
            raise RuntimeError("PRIVATE-CREDENTIAL-CONTENT")

    with pytest.raises(CalendarError, match=r"^calendar_credentials_denied$"):
        await provider(tokens=Broken()).read(WINDOW)


async def test_service_disable_during_identity_get_prevents_calendar_request() -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        entered.set()
        await release.wait()
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=Body(json.dumps({"email": ACCOUNT, "verified_email": True}).encode()),
        )

    service = build_google_calendar_service(
        ACCOUNT, Tokens(), enabled=True, transport=httpx.MockTransport(handler)
    )
    task = asyncio.create_task(service.read(WINDOW))
    await entered.wait()
    service.enabled = False
    service.enabled = True
    release.set()
    with pytest.raises(CalendarError, match="disabled"):
        await task
    assert len(requests) == 1


async def test_transport_cancel_reaps_response_and_denies_private_failures(capsys) -> None:
    entered, closed = asyncio.Event(), asyncio.Event()

    class Waiting(Body):
        async def __aiter__(self):
            entered.set()
            await asyncio.Event().wait()
            yield b""

        async def aclose(self) -> None:
            closed.set()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "application/json"}, stream=Waiting(b"")
        )

    adapter = GoogleCalendarReadProvider(
        ACCOUNT, Tokens(), enabled=True, transport=httpx.MockTransport(handler)
    )
    task = asyncio.create_task(adapter.read(WINDOW))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()

    for exception, expected in [
        (httpx.ReadTimeout("PRIVATE"), "calendar_timeout"),
        (httpx.ConnectError("PRIVATE"), "calendar_provider_unavailable"),
    ]:

        def failed(request: httpx.Request, exception: Exception = exception) -> httpx.Response:
            raise exception

        adapter = GoogleCalendarReadProvider(
            ACCOUNT, Tokens(), enabled=True, transport=httpx.MockTransport(failed)
        )
        with pytest.raises(CalendarError, match=expected):
            await adapter.read(WINDOW)
    assert not capsys.readouterr().err


def test_google_plan_cli_is_inert_and_explicit() -> None:
    result = CliRunner().invoke(app, ["calendar", "google-plan"])
    assert result.exit_code == 0, result.output
    plan = json.loads(result.output)
    assert plan["target"] == "primary" and not plan["enabled"] and not plan["approval_granted"]
    assert not plan["login_implemented"] and not plan["owner_credentials_accessed"]
    assert plan["scopes_proposed"] == sorted(GOOGLE_CALENDAR_SCOPES)


async def test_first_live_proof_ceiling_is_enforceable_before_any_later_work() -> None:
    wire = Wire(listing(*(event(str(n)) for n in range(101))))
    service = build_google_calendar_service(
        ACCOUNT, Tokens(), enabled=True, max_events=100, transport=httpx.MockTransport(wire)
    )
    with pytest.raises(CalendarError, match="occurrence_limit"):
        await service.read(WINDOW)
    assert wire.requests[-1].url.params["maxResults"] == "100"
    for limit in [0, 513, True]:
        with pytest.raises(CalendarError, match="configuration"):
            GoogleCalendarReadProvider(ACCOUNT, Tokens(), max_events=limit)


@pytest.mark.parametrize(
    "account,calendar_id",
    [
        ("UPPER@gmail.com", "primary"),
        ("bad", "primary"),
        (ACCOUNT, "https://evil.invalid"),
        (ACCOUNT, "../escape"),
        (ACCOUNT, ""),
    ],
)
def test_configuration_cannot_select_external_network_target(
    account: str, calendar_id: str
) -> None:
    with pytest.raises(CalendarError, match="configuration"):
        provider(account=account, calendar_id=calendar_id)
    with pytest.raises(CalendarError, match="configuration"):
        provider().enabled = 1  # type: ignore[assignment]
