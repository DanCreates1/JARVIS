"""Inactive Google Calendar adapter. Trusted host tokens only; no login, store or writes."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from pydantic import ValidationError

from .ical import digest, wall
from .models import CalendarError, CalendarOccurrence, CalendarSnapshot, CalendarWindow, aware
from .service import CalendarService

GOOGLE_CALENDAR_READ_SCOPE = "https://www.googleapis.com/auth/calendar.events.owned.readonly"
GOOGLE_EMAIL_SCOPE = "https://www.googleapis.com/auth/userinfo.email"
GOOGLE_CALENDAR_SCOPES = frozenset({GOOGLE_CALENDAR_READ_SCOPE, GOOGLE_EMAIL_SCOPE})
_ORIGIN = "https://www.googleapis.com"
_FIELDS = (
    "kind,etag,timeZone,accessRole,nextPageToken,nextSyncToken,items("
    "id,etag,status,summary,start,end,transparency,recurringEventId,originalStartTime,"
    "endTimeUnspecified,eventType,recurrence)"
)


def _account(value: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 254
        or not re.fullmatch(
            r"[a-z0-9][a-z0-9.!#$%&'*+/=?^_`{|}~-]{0,63}@[a-z0-9-]+(?:\.[a-z0-9-]+)+", value
        )
    ):
        raise CalendarError("calendar_configuration")
    return value


def _calendar(value: str) -> str:
    if value == "primary":
        return value
    if (
        not isinstance(value, str)
        or len(value) > 254
        or not re.fullmatch(r"[a-z0-9][a-z0-9_.+-]{0,127}@[a-z0-9-]+(?:\.[a-z0-9-]+)+", value)
    ):
        raise CalendarError("calendar_configuration")
    return value


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CalendarError("calendar_provider_protocol")
    return value


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise CalendarError("calendar_provider_protocol")
        output[key] = value
    return output


def _constant(value: str) -> None:
    raise CalendarError("calendar_provider_protocol")


def _id(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", value):
        raise CalendarError("calendar_provider_protocol")
    return value


def _etag(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'"[A-Za-z0-9_+/=-]{1,256}"', value):
        raise CalendarError("calendar_provider_protocol")
    return value


def _query_window(window: CalendarWindow) -> CalendarWindow:
    try:
        return CalendarWindow(
            start=window.start.replace(microsecond=0),
            end=window.end.replace(microsecond=0) + timedelta(seconds=bool(window.end.microsecond)),
        )
    except ValidationError:
        raise CalendarError("calendar_window_limit") from None


@dataclass(frozen=True, repr=False)
class GoogleCalendarAccessToken:
    """Host-only verified grant; never display, cache, log or send to a model/client."""

    account: str
    access_token: str = field(repr=False)
    expires_at: datetime
    calendar_id: str = "primary"
    scopes: frozenset[str] = GOOGLE_CALENDAR_SCOPES


class GoogleCalendarTokenSource(Protocol):
    async def acquire(self) -> GoogleCalendarAccessToken:
        """Acquire an existing exact grant; no login, account switch or scope expansion."""
        ...


def _instant(value: object, zone: ZoneInfo) -> tuple[datetime, bool]:
    data = _object(value)
    if set(data) - {"date", "dateTime", "timeZone"} or ("date" in data) == ("dateTime" in data):
        raise CalendarError("calendar_provider_protocol")
    timezone = data.get("timeZone")
    if timezone is not None:
        if not isinstance(timezone, str) or len(timezone) > 100:
            raise CalendarError("calendar_timezone_invalid")
        try:
            event_zone = ZoneInfo(timezone)
        except (ValueError, ZoneInfoNotFoundError):
            raise CalendarError("calendar_timezone_invalid") from None
    else:
        event_zone = zone
    if "date" in data:
        raw = data["date"]
        if not isinstance(raw, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            raise CalendarError("calendar_invalid_date")
        if event_zone != zone:
            raise CalendarError("calendar_timezone_invalid")
        return wall(
            datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=UTC).replace(tzinfo=None), zone
        ), True
    raw = data["dateTime"]
    if (
        not isinstance(raw, str)
        or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", raw
        )
        or raw.endswith("-00:00")
    ):
        raise CalendarError("calendar_invalid_date")
    result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if timezone is not None and (
        result.astimezone(event_zone).replace(tzinfo=None) != result.replace(tzinfo=None)
        or result.astimezone(event_zone).utcoffset() != result.utcoffset()
    ):
        raise CalendarError("calendar_invalid_date")
    return aware(result), False


class GoogleCalendarReadProvider:
    def __init__(
        self,
        account: str,
        tokens: GoogleCalendarTokenSource,
        *,
        calendar_id: str = "primary",
        enabled: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
        max_events: int = 512,
    ) -> None:
        self._account, self._calendar = _account(account), _calendar(calendar_id)
        self._tokens, self._transport = tokens, transport
        if type(max_events) is not int or not 1 <= max_events <= 512:
            raise CalendarError("calendar_configuration")
        self._max_events = max_events
        self.source_id = digest("google-calendar\0" + self._account + "\0" + self._calendar)
        self._generation = 0
        self.enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        if type(value) is not bool:
            raise CalendarError("calendar_configuration")
        self._generation += 1
        self._enabled = value

    def _check(self, generation: int) -> None:
        if not self._enabled or generation != self._generation:
            raise CalendarError("calendar_disabled")

    async def _get(
        self,
        client: httpx.AsyncClient,
        generation: int,
        path: str,
        params: dict[str, str],
        limit: int,
    ) -> dict[str, Any]:
        self._check(generation)
        client.cookies.clear()
        async with client.stream("GET", _ORIGIN + path, params=params) as response:
            self._check(generation)
            if response.status_code in {401, 403}:
                raise CalendarError("calendar_credentials_denied")
            if response.status_code == 429:
                raise CalendarError("calendar_rate_limited")
            if response.status_code == 404:
                raise CalendarError("calendar_source_unavailable")
            if response.status_code != 200:
                raise CalendarError("calendar_provider_unavailable")
            if (
                response.headers.get("content-type", "").split(";", 1)[0].lower()
                != "application/json"
                or response.headers.get("content-encoding", "identity").lower() != "identity"
            ):
                raise CalendarError("calendar_provider_protocol")
            length = response.headers.get("content-length")
            if length is not None and not re.fullmatch(r"[0-9]{1,10}", length):
                raise CalendarError("calendar_provider_protocol")
            if length is not None and int(length) > limit:
                raise CalendarError("calendar_response_limit")
            raw = bytearray()
            async for chunk in response.aiter_raw(chunk_size=16_384):
                self._check(generation)
                if len(raw) + len(chunk) > limit:
                    raise CalendarError("calendar_response_limit")
                raw.extend(chunk)
            if length is not None and len(raw) != int(length):
                raise CalendarError("calendar_provider_protocol")
        self._check(generation)
        try:
            return _object(
                json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_constant)
            )
        except (ValueError, UnicodeError, RecursionError):
            raise CalendarError("calendar_provider_protocol") from None

    def _snapshot(self, data: dict[str, Any], window: CalendarWindow) -> CalendarSnapshot:
        if set(data) - {
            "kind",
            "etag",
            "timeZone",
            "accessRole",
            "nextPageToken",
            "nextSyncToken",
            "items",
        }:
            raise CalendarError("calendar_provider_protocol")
        if data.get("kind") != "calendar#events":
            raise CalendarError("calendar_provider_protocol")
        _etag(data.get("etag"))
        if data.get("accessRole") != "owner":
            raise CalendarError("calendar_owner_required")
        timezone = data.get("timeZone")
        if not isinstance(timezone, str) or len(timezone) > 100:
            raise CalendarError("calendar_timezone_invalid")
        zone = ZoneInfo(timezone)
        if "nextPageToken" in data:
            raise CalendarError("calendar_provider_incomplete")
        if "nextSyncToken" in data and (
            not isinstance(data["nextSyncToken"], str)
            or not 1 <= len(data["nextSyncToken"]) <= 2048
        ):
            raise CalendarError("calendar_provider_protocol")
        items = data.get("items", [])
        if not isinstance(items, list) or len(items) > self._max_events:
            raise CalendarError("calendar_occurrence_limit")
        events: list[CalendarOccurrence] = []
        seen: set[str] = set()
        envelope = _query_window(window)
        for item in items:
            event = _object(item)
            if set(event) - {
                "id",
                "etag",
                "status",
                "summary",
                "start",
                "end",
                "transparency",
                "recurringEventId",
                "originalStartTime",
                "endTimeUnspecified",
                "eventType",
                "recurrence",
            }:
                raise CalendarError("calendar_provider_protocol")
            identifier = _id(event.get("id"))
            if identifier in seen:
                raise CalendarError("calendar_duplicate_occurrence")
            seen.add(identifier)
            status = event.get("status")
            if status not in {"confirmed", "tentative", "cancelled"}:
                raise CalendarError("calendar_provider_protocol")
            if status == "cancelled":
                if "etag" in event:
                    _etag(event["etag"])
                continue  # Cancelled tombstones can lack time/title. Never busy or replayed.
            _etag(event.get("etag"))
            if event.get("recurrence") or event.get("endTimeUnspecified", False) is not False:
                raise CalendarError("calendar_unsupported_event")
            if event.get("eventType", "default") not in {
                "default",
                "outOfOffice",
                "focusTime",
                "workingLocation",
                "fromGmail",
                "birthday",
            }:
                raise CalendarError("calendar_unsupported_event")
            start, all_day = _instant(event.get("start"), zone)
            end, end_day = _instant(event.get("end"), zone)
            if all_day != end_day or end <= start:
                raise CalendarError("calendar_event_interval")
            if start >= envelope.end or end <= envelope.start:
                raise CalendarError("calendar_provider_window")
            title = event.get("summary", "")
            transparency = event.get("transparency", "opaque")
            if (
                not isinstance(title, str)
                or len(title) > 512
                or transparency not in {"opaque", "transparent"}
            ):
                raise CalendarError("calendar_provider_protocol")
            if ("recurringEventId" in event) != ("originalStartTime" in event):
                raise CalendarError("calendar_provider_protocol")
            root, occurrence = identifier, start
            if "recurringEventId" in event:
                root = _id(event["recurringEventId"])
                occurrence, original_day = _instant(event["originalStartTime"], zone)
                if original_day != all_day:
                    raise CalendarError("calendar_provider_protocol")
            event_id = digest(self.source_id + "\0" + root)
            if start >= window.end or end <= window.start:
                continue  # Exact subsecond window after conservative whole-second API query.
            events.append(
                CalendarOccurrence(
                    event_id=event_id,
                    occurrence_id=digest(
                        event_id + "\0" + str(all_day) + "\0" + aware(occurrence).isoformat()
                    ),
                    title=title,
                    start=start,
                    end=end,
                    all_day=all_day,
                    busy=transparency == "opaque",
                )
            )
        canonical = {k: v for k, v in data.items() if k != "nextSyncToken"}
        canonical["items"] = sorted(items, key=lambda e: e["id"])
        revision = digest(
            self.source_id
            + window.model_dump_json()
            + json.dumps(canonical, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        )
        return CalendarSnapshot(
            source_id=self.source_id,
            revision=revision,
            window=window,
            observed_at=datetime.now(UTC),
            events=tuple(sorted(events, key=lambda e: (e.start, e.occurrence_id))),
            source_kind="provider",
        )

    async def read(self, window: CalendarWindow) -> CalendarSnapshot:
        generation = self._generation
        self._check(generation)
        try:
            window = CalendarWindow.model_validate(window.model_dump(warnings=False))
            query = _query_window(window)
            async with asyncio.timeout(5):
                try:
                    token = await self._tokens.acquire()
                except Exception:
                    raise CalendarError("calendar_credentials_denied") from None
                self._check(generation)
                if (
                    not isinstance(token, GoogleCalendarAccessToken)
                    or token.account != self._account
                    or token.calendar_id != self._calendar
                    or token.scopes != GOOGLE_CALENDAR_SCOPES
                    or not isinstance(token.access_token, str)
                    or len(token.access_token) > 8192
                    or not re.fullmatch(r"[A-Za-z0-9._~+/-]{1,8192}={0,2}", token.access_token)
                    or not isinstance(token.expires_at, datetime)
                    or token.expires_at.tzinfo is None
                    or aware(token.expires_at) <= datetime.now(UTC)
                ):
                    raise CalendarError("calendar_credentials_denied")
                async with httpx.AsyncClient(
                    transport=self._transport,
                    timeout=5,
                    trust_env=False,
                    follow_redirects=False,
                    headers={
                        "Authorization": f"Bearer {token.access_token}",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                ) as client:
                    identity = await self._get(
                        client,
                        generation,
                        "/oauth2/v2/userinfo",
                        {"fields": "email,verified_email"},
                        16_384,
                    )
                    if (
                        set(identity) != {"email", "verified_email"}
                        or identity["email"] != self._account
                        or identity["verified_email"] is not True
                    ):
                        raise CalendarError("calendar_account_mismatch")
                    data = await self._get(
                        client,
                        generation,
                        "/calendar/v3/calendars/" + quote(self._calendar, safe="") + "/events",
                        {
                            "timeMin": query.start.isoformat(),
                            "timeMax": query.end.isoformat(),
                            "maxResults": str(self._max_events),
                            "singleEvents": "true",
                            "showDeleted": "false",
                            "showHiddenInvitations": "true",
                            "orderBy": "startTime",
                            "fields": _FIELDS,
                        },
                        1_048_576,
                    )
                    self._check(generation)
                    snapshot = self._snapshot(data, window)
                    self._check(generation)
                    return snapshot
        except CalendarError as exc:
            raise CalendarError(exc.code) from None
        except (TimeoutError, httpx.TimeoutException):
            raise CalendarError("calendar_timeout") from None
        except (ValueError, ValidationError, ZoneInfoNotFoundError, OverflowError, RecursionError):
            raise CalendarError("calendar_provider_protocol") from None
        except Exception:
            raise CalendarError("calendar_provider_unavailable") from None


def build_google_calendar_service(
    account: str,
    tokens: GoogleCalendarTokenSource,
    *,
    calendar_id: str = "primary",
    enabled: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
    max_events: int = 512,
) -> CalendarService:
    provider = GoogleCalendarReadProvider(
        account,
        tokens,
        calendar_id=calendar_id,
        enabled=enabled,
        transport=transport,
        max_events=max_events,
    )

    def control(value: bool) -> None:
        provider.enabled = value

    return CalendarService(
        provider,
        source_id=provider.source_id,
        enabled=enabled,
        source_kind="provider",
        control_enabled=control,
    )
