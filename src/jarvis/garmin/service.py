"""Bounded Core-owned Garmin view; only normalized values reach remote clients."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class GarminActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=80)
    type: str = Field(max_length=40)
    started: str = Field(max_length=19)


class GarminSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    refreshed_at: datetime
    steps: int | None = Field(default=None, ge=0, le=200_000)
    resting_heart_rate: int | None = Field(default=None, ge=20, le=240)
    sleep_minutes: int | None = Field(default=None, ge=0, le=1_440)
    stress: int | None = Field(default=None, ge=0, le=100)
    body_battery: int | None = Field(default=None, ge=0, le=100)
    activities: tuple[GarminActivity, ...] = Field(max_length=3)


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
        self._last_attempt = 0.0

    async def summary(self, *, refresh: bool = False) -> GarminSummary:
        async with self._lock:
            now = monotonic()
            if self._cached is not None and not refresh and now - self._cached_at < 300:
                return self._cached
            if self._last_attempt and now - self._last_attempt < 60:
                if self._cached is not None:
                    return self._cached
                raise GarminUnavailableError("refresh_limited")
            if not self._python.is_file() or not self._bridge.is_file():
                raise GarminUnavailableError("bridge_unavailable")
            self._last_attempt = now
            try:
                process = await asyncio.create_subprocess_exec(
                    str(self._python),
                    str(self._bridge),
                    "summary",
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                try:
                    stdout, _ = await asyncio.wait_for(process.communicate(), timeout=90)
                except TimeoutError:
                    process.kill()
                    await process.wait()
                    raise GarminUnavailableError("refresh_timeout") from None
                if process.returncode != 0 or len(stdout) > 8_192:
                    raise GarminUnavailableError("refresh_failed")
                summary = GarminSummary.model_validate(json.loads(stdout))
            except (OSError, ValueError, ValidationError) as exc:
                raise GarminUnavailableError("refresh_failed") from exc
            self._cached = summary
            self._cached_at = monotonic()
            return summary
