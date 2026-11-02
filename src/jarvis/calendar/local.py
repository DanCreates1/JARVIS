"""One explicit local file; no directory/account discovery or durable calendar cache."""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .ical import MAX_BYTES, digest, parse
from .models import CalendarError, CalendarSnapshot, CalendarWindow


class LocalCalendar:
    def __init__(self, path: Path, *, timezone: str) -> None:
        if not path.is_absolute() or str(path).startswith(("\\\\", "//")):
            raise CalendarError("calendar_local_path_required")
        if path.suffix.lower() != ".ics":
            raise CalendarError("calendar_file_type")
        if any(":" in part for part in path.parts[1:]):
            raise CalendarError("calendar_file_type")
        try:
            self.zone = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise CalendarError("calendar_timezone_invalid") from None
        self.path = path
        if os.name == "nt":
            query = ctypes.WinDLL("kernel32", use_last_error=True).GetDriveTypeW
            query.argtypes, query.restype = [ctypes.c_wchar_p], ctypes.c_uint
            if query(path.anchor) not in {2, 3, 6}:
                raise CalendarError("calendar_local_volume_required")
        self.source_id = digest(str(path) + "\0" + timezone)

    def _check(self) -> os.stat_result:
        for component in (self.path, *self.path.parents):
            info = component.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise CalendarError("calendar_link_denied")
        info = self.path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise CalendarError("calendar_file_type")
        return info

    def _read(self) -> bytes:
        try:
            before = self._check()
            if not 0 < before.st_size <= MAX_BYTES:
                raise CalendarError("calendar_size")
            with self.path.open("rb") as stream:
                opened = os.fstat(stream.fileno())
                raw = stream.read(MAX_BYTES + 1)
            after = self._check()
            identities = {
                (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns) for s in (before, opened, after)
            }
            if len(identities) != 1:
                raise CalendarError("calendar_source_changed")
            if not 0 < len(raw) <= MAX_BYTES:
                raise CalendarError("calendar_size")
            return raw
        except OSError:
            raise CalendarError("calendar_source_unavailable") from None

    async def read(self, window: CalendarWindow) -> CalendarSnapshot:
        raw = await asyncio.to_thread(self._read)
        return CalendarSnapshot(
            source_id=self.source_id,
            revision=hashlib.sha256(raw).hexdigest(),
            window=window,
            observed_at=datetime.now(UTC),
            events=parse(raw, window, source_id=self.source_id, all_day_zone=self.zone),
        )
