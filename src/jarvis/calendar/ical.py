"""Fail-closed RFC 5545 subset. No URLs, alarms, scripts or invitations executed."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import CalendarError, CalendarOccurrence, CalendarWindow

MAX_BYTES = 256 * 1024


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def wall(value: datetime, zone: ZoneInfo) -> datetime:
    result = value.replace(tzinfo=zone, fold=0)
    if result.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != value:
        raise CalendarError("calendar_dst_gap")
    return result


def _instant(params: dict[str, str], value: str) -> tuple[datetime, bool]:
    if set(params) - {"TZID", "VALUE"}:
        raise CalendarError("calendar_unsupported_parameter")
    all_day = params.get("VALUE") == "DATE"
    if params.get("VALUE", "DATE-TIME") not in {"DATE", "DATE-TIME"}:
        raise CalendarError("calendar_unsupported_date")
    try:
        if all_day:
            if "TZID" in params or not re.fullmatch(r"\d{8}", value):
                raise CalendarError("calendar_invalid_date")
            return datetime.strptime(value, "%Y%m%d").replace(tzinfo=UTC), True
        utc = value.endswith("Z")
        if utc == ("TZID" in params):
            raise CalendarError("calendar_timezone_required")
        raw = value[:-1] if utc else value
        if not re.fullmatch(r"\d{8}T\d{6}", raw):
            raise CalendarError("calendar_invalid_date")
        parsed = datetime.strptime(raw, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
        return (
            parsed if utc else wall(parsed.replace(tzinfo=None), ZoneInfo(params["TZID"]))
        ), False
    except (ValueError, ZoneInfoNotFoundError):
        raise CalendarError("calendar_invalid_date") from None


def _text(value: str) -> str:
    if not re.fullmatch(r"(?:[^\\]|\\[nN,;\\])*", value):
        raise CalendarError("calendar_invalid_text")
    return re.sub(r"\\([nN,;\\])", lambda m: "\n" if m[1] in "nN" else m[1], value)


Property = tuple[dict[str, str], str]


def _properties(raw: bytes) -> list[dict[str, list[Property]]]:
    if not raw or len(raw) > MAX_BYTES:
        raise CalendarError("calendar_size")
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise CalendarError("calendar_encoding") from None
    if any((ord(c) < 32 and c not in "\r\n\t") or ord(c) == 127 for c in text):
        raise CalendarError("calendar_controls")
    lines: list[str] = []
    for line in text.replace("\r\n", "\n").splitlines():
        if line.startswith((" ", "\t")):
            if not lines:
                raise CalendarError("calendar_structure")
            lines[-1] += line[1:]
        else:
            lines.append(line)
        if len(lines[-1]) > 8192:
            raise CalendarError("calendar_line_limit")
    if len(lines) < 4 or lines[0] != "BEGIN:VCALENDAR" or lines[-1] != "END:VCALENDAR":
        raise CalendarError("calendar_structure")
    events: list[dict[str, list[Property]]] = []
    current: dict[str, list[Property]] | None = None
    headers: dict[str, str] = {}
    for line in lines[1:-1]:
        if line == "BEGIN:VEVENT":
            if current is not None or len(events) >= 100:
                raise CalendarError("calendar_event_limit")
            current = {}
        elif line == "END:VEVENT":
            if current is None:
                raise CalendarError("calendar_structure")
            events.append(current)
            current = None
        else:
            head, sep, value = line.partition(":")
            parts = head.split(";")
            name = parts[0]
            params: dict[str, str] = {}
            for part in parts[1:]:
                key, eq, val = part.partition("=")
                if not eq or key in params or not val:
                    raise CalendarError("calendar_invalid_parameter")
                params[key] = val
            if not sep or name in {"BEGIN", "END"}:
                raise CalendarError("calendar_unsupported_component")
            if current is None:
                if params or name not in {"VERSION", "PRODID", "CALSCALE"} or name in headers:
                    raise CalendarError("calendar_unsupported_header")
                headers[name] = value
            else:
                if name not in {
                    "UID",
                    "DTSTAMP",
                    "DTSTART",
                    "DTEND",
                    "SUMMARY",
                    "RRULE",
                    "EXDATE",
                    "STATUS",
                    "TRANSP",
                    "SEQUENCE",
                }:
                    raise CalendarError("calendar_unsupported_property")
                if name in current and name != "EXDATE":
                    raise CalendarError("calendar_duplicate_property")
                current.setdefault(name, []).append((params, value))
    if current is not None or headers.get("VERSION") != "2.0" or not headers.get("PRODID"):
        raise CalendarError("calendar_structure")
    if headers.get("CALSCALE", "GREGORIAN") != "GREGORIAN":
        raise CalendarError("calendar_unsupported_scale")
    return events


def parse(
    raw: bytes, window: CalendarWindow, *, source_id: str, all_day_zone: ZoneInfo
) -> tuple[CalendarOccurrence, ...]:
    occurrences: list[CalendarOccurrence] = []
    seen: set[str] = set()
    for props in _properties(raw):
        if not {"UID", "DTSTAMP", "DTSTART"} <= props.keys():
            raise CalendarError("calendar_required_property")

        def scalar(name: str, default: str = "", props: dict[str, list[Property]] = props) -> str:
            params, value = props.get(name, [({}, default)])[0]
            if params:
                raise CalendarError("calendar_unsupported_parameter")
            return value

        uid = scalar("UID")
        if not uid or len(uid) > 512 or uid in seen:
            raise CalendarError("calendar_duplicate_uid")
        seen.add(uid)
        stamp_params, stamp = props["DTSTAMP"][0]
        if stamp_params or not stamp.endswith("Z"):
            raise CalendarError("calendar_invalid_timestamp")
        _instant(stamp_params, stamp)
        start, all_day = _instant(*props["DTSTART"][0])
        if all_day:
            start = wall(start.replace(tzinfo=None), all_day_zone)
        if "DTEND" in props:
            end, end_day = _instant(*props["DTEND"][0])
            if end_day:
                end = wall(end.replace(tzinfo=None), all_day_zone)
            if all_day != end_day or end.tzinfo != start.tzinfo:
                raise CalendarError("calendar_mixed_date_types")
        elif all_day:
            end = start + timedelta(days=1)
        else:
            raise CalendarError("calendar_end_required")
        duration = (
            end.replace(tzinfo=None) - start.replace(tzinfo=None)
            if all_day
            else end.astimezone(UTC) - start.astimezone(UTC)
        )
        if not timedelta(0) < duration <= timedelta(days=31):
            raise CalendarError("calendar_event_interval")
        title = _text(scalar("SUMMARY"))
        if len(title) > 512:
            raise CalendarError("calendar_title_limit")
        status, transparency = scalar("STATUS", "CONFIRMED"), scalar("TRANSP", "OPAQUE")
        if status not in {"TENTATIVE", "CONFIRMED", "CANCELLED"} or transparency not in {
            "OPAQUE",
            "TRANSPARENT",
        }:
            raise CalendarError("calendar_invalid_status")
        if not re.fullmatch(r"\d{1,9}", scalar("SEQUENCE", "0")):
            raise CalendarError("calendar_invalid_sequence")
        excluded: set[datetime] = set()
        for params, values in props.get("EXDATE", []):
            for value in values.split(","):
                at, day = _instant(params, value)
                if day:
                    at = wall(at.replace(tzinfo=None), all_day_zone)
                if day != all_day or at.tzinfo != start.tzinfo:
                    raise CalendarError("calendar_mixed_date_types")
                excluded.add(at.astimezone(UTC))
                if len(excluded) > 366:
                    raise CalendarError("calendar_recurrence_limit")
        count, step = 1, 1
        if "RRULE" in props:
            rule: dict[str, str] = {}
            for item in scalar("RRULE").split(";"):
                key, eq, value = item.partition("=")
                if not eq or key in rule:
                    raise CalendarError("calendar_unsupported_recurrence")
                rule[key] = value
            if (
                set(rule) - {"FREQ", "COUNT", "INTERVAL"}
                or rule.get("FREQ") not in {"DAILY", "WEEKLY"}
                or not re.fullmatch(r"\d{1,3}", rule.get("COUNT", ""))
                or not re.fullmatch(r"\d{1,3}", rule.get("INTERVAL", "1"))
            ):
                raise CalendarError("calendar_unsupported_recurrence")
            count, step = int(rule["COUNT"]), int(rule.get("INTERVAL", "1"))
            if not 1 <= count <= 366 or not 1 <= step <= 52:
                raise CalendarError("calendar_recurrence_limit")
            step *= 7 if rule["FREQ"] == "WEEKLY" else 1
        event_id = digest(source_id + "\0" + uid)
        valid, attempts = 0, 0
        while valid < count:
            if attempts >= 732:
                raise CalendarError("calendar_recurrence_limit")
            try:
                local = start.replace(tzinfo=None) + timedelta(days=attempts * step)
                local_end = local + duration
                if isinstance(start.tzinfo, ZoneInfo):
                    current = wall(local, start.tzinfo)
                    finish = (
                        wall(local_end, start.tzinfo)
                        if all_day
                        else current.astimezone(UTC) + duration
                    )
                else:
                    current, finish = local.replace(tzinfo=UTC), local_end.replace(tzinfo=UTC)
            except OverflowError:
                raise CalendarError("calendar_date_overflow") from None
            except CalendarError as exc:
                if exc.code != "calendar_dst_gap" or count == 1:
                    raise
                attempts += 1
                continue
            valid += 1
            attempts += 1
            at, until = current.astimezone(UTC), finish.astimezone(UTC)
            if until <= at:
                raise CalendarError("calendar_event_interval")
            if at in excluded or at >= window.end or until <= window.start:
                continue
            occurrences.append(
                CalendarOccurrence(
                    event_id=event_id,
                    occurrence_id=digest(event_id + "\0" + at.isoformat()),
                    title=title,
                    start=at,
                    end=until,
                    all_day=all_day,
                    cancelled=status == "CANCELLED",
                    busy=transparency == "OPAQUE",
                )
            )
            if len(occurrences) > 512:
                raise CalendarError("calendar_occurrence_limit")
    return tuple(sorted(occurrences, key=lambda e: (e.start, e.occurrence_id)))
