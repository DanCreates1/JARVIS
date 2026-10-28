"""Bounded Core-owned Garmin view; only normalized values reach remote clients."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import suppress
from datetime import UTC, date, datetime
from pathlib import Path
from time import monotonic
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

_OUTPUT_LIMIT = 8_192


class GarminActivity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(max_length=80)
    type: str = Field(max_length=40)
    started: str = Field(max_length=19)


class GarminSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    refreshed_at: datetime
    steps: int | None = Field(default=None, ge=0, le=200_000, strict=True)
    resting_heart_rate: int | None = Field(default=None, ge=20, le=240, strict=True)
    sleep_minutes: int | None = Field(default=None, ge=0, le=1_440, strict=True)
    stress: int | None = Field(default=None, ge=0, le=100, strict=True)
    body_battery: int | None = Field(default=None, ge=0, le=100, strict=True)
    activities_available: bool = Field(default=False, strict=True)
    activities: tuple[GarminActivity, ...] = Field(max_length=3)

    @field_validator("date")
    @classmethod
    def valid_day(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @field_validator("refreshed_at")
    @classmethod
    def aware_fetch_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timezone-aware Garmin fetch time required")
        return value


class GarminUnavailableError(Exception):
    """A sanitized Garmin failure safe to map to a generic API response."""


class GarminReader(Protocol):
    async def summary(self, *, refresh: bool = False) -> GarminSummary: ...


class GarminSummaryService:
    """Run isolated Python 3.12 bridge with a short, shared, memory-only cache."""

    def __init__(self, *, python_path: Path | None = None, bridge_path: Path | None = None) -> None:
        repo = Path(__file__).resolve().parents[3]
        self._python = python_path or repo / "garmin_sync" / ".venv" / "Scripts" / "python.exe"
        self._bridge = bridge_path or Path(__file__).with_name("bridge.py")
        self._lock = asyncio.Lock()
        self._cached: GarminSummary | None = None
        self._cached_at = 0.0
        self._last_attempt: float | None = None

    async def summary(self, *, refresh: bool = False) -> GarminSummary:
        async with self._lock:
            now = monotonic()
            if (
                self._cached is not None
                and not refresh
                and now - self._cached_at < 300
                and self._cached.date == datetime.now(UTC).astimezone().date().isoformat()
            ):
                return self._cached
            if self._last_attempt is not None and now - self._last_attempt < 60:
                if self._cached is not None:
                    return self._cached
                raise GarminUnavailableError("refresh_limited")
            self._last_attempt = now
            # A failed/cancelled refresh must not turn an old cache into a later success.
            # The client can retain its prior snapshot with an explicit failure/stale label.
            self._cached = None
            if not self._python.is_file() or not self._bridge.is_file():
                raise GarminUnavailableError("bridge_unavailable")
            try:
                process = await asyncio.create_subprocess_exec(
                    str(self._python),
                    "-I",
                    str(self._bridge),
                    "summary",
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    limit=_OUTPUT_LIMIT + 1,
                    env={
                        key: value
                        for key, value in os.environ.items()
                        if key.upper()
                        in {
                            "SYSTEMROOT",
                            "WINDIR",
                            "SYSTEMDRIVE",
                            "TEMP",
                            "TMP",
                            "LOCALAPPDATA",
                            "APPDATA",
                            "PROGRAMDATA",
                            "USERPROFILE",
                            "HOMEDRIVE",
                            "HOMEPATH",
                        }
                    },
                )
                try:
                    stdout = await asyncio.wait_for(_read_output(process), timeout=90)
                except TimeoutError:
                    raise GarminUnavailableError("refresh_timeout") from None
                finally:
                    if process.returncode is None:
                        with suppress(ProcessLookupError):
                            process.kill()
                        await process.wait()
                if process.returncode != 0:
                    raise GarminUnavailableError("refresh_failed")
                summary = GarminSummary.model_validate(
                    json.loads(stdout, object_pairs_hook=_unique_object)
                )
            except (OSError, ValueError, ValidationError):
                raise GarminUnavailableError("refresh_failed") from None
            self._cached = summary
            self._cached_at = monotonic()
            return summary


async def _read_output(process: asyncio.subprocess.Process) -> bytes:
    """Bound memory before decoding; deadline also covers waiting for child exit."""
    if process.stdout is None:
        raise GarminUnavailableError("refresh_failed")
    output = bytearray()
    while chunk := await process.stdout.read(min(4_096, _OUTPUT_LIMIT + 1 - len(output))):
        output.extend(chunk)
        if len(output) > _OUTPUT_LIMIT:
            raise GarminUnavailableError("refresh_failed")
    await process.wait()
    return bytes(output)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate Garmin output field")
        result[key] = value
    return result
