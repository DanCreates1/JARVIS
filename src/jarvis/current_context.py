"""Compact programmatic context for requests that depend on the current environment."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Mapping
from datetime import datetime, tzinfo
from enum import StrEnum
from time import monotonic
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from pydantic import JsonValue

from jarvis.core.models import ContextProjection, ModelRole, SensitivityClass

Now = Callable[[tzinfo | None], datetime]
Monotonic = Callable[[], float]


class CurrentContextField(StrEnum):
    TIME = "time"
    LOCATION = "location"
    DEVICE = "device"
    MODEL = "model"
    INTERNET = "internet"


class InternetProbe(Protocol):
    async def available(self) -> bool: ...


_TIME_PATTERN = re.compile(
    r"\b(time|date|day|today|tonight|tomorrow|yesterday|now|current|schedule|"
    r"calendar|deadline|morning|afternoon|evening)\b",
    re.IGNORECASE,
)
_LOCATION_PATTERN = re.compile(
    r"\b(home|location|local|nearby|near me|around me|weather|traffic|transit|"
    r"store hours?|directions?)\b",
    re.IGNORECASE,
)
_DEVICE_PATTERN = re.compile(
    r"\b(device|session|system|computer|machine|host|interface|browser|terminal|cli|"
    r"phone|pwa|voice)\b",
    re.IGNORECASE,
)
_MODEL_PATTERN = re.compile(
    r"\b(model|provider|inference|cloud|local model|ollama|groq|gemini|nvidia|"
    r"rate limit|usage limit|fallback)\b",
    re.IGNORECASE,
)
_INTERNET_PATTERN = re.compile(
    r"\b(weather|news|headlines?|prices?|stocks?|crypto|sports|scores?|traffic|"
    r"transit|store hours?|current events?|latest|recent|breaking|live|online|"
    r"offline|internet|web|search|documentation|software versions?)\b",
    re.IGNORECASE,
)
_SAFE_INTERFACE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def select_current_context_fields(query: str) -> frozenset[CurrentContextField]:
    """Select only fields that can materially improve this request."""
    fields: set[CurrentContextField] = set()
    if _TIME_PATTERN.search(query):
        fields.add(CurrentContextField.TIME)
    if _LOCATION_PATTERN.search(query):
        fields.add(CurrentContextField.LOCATION)
    if _DEVICE_PATTERN.search(query):
        fields.add(CurrentContextField.DEVICE)
    if _MODEL_PATTERN.search(query):
        fields.add(CurrentContextField.MODEL)
    if _INTERNET_PATTERN.search(query):
        fields.add(CurrentContextField.INTERNET)
    if fields:
        fields.add(CurrentContextField.TIME)
    return frozenset(fields)


class HttpInternetProbe:
    """Check bounded HTTPS reachability without sending conversation content."""

    def __init__(self, endpoint: str, *, timeout_seconds: float) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    async def available(self) -> bool:
        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=self.timeout_seconds,
                trust_env=False,
                headers={"User-Agent": "JARVIS-Current-Context/1"},
            ) as client:
                await client.head(self.endpoint)
        except (httpx.HTTPError, ValueError):
            return False
        return True


class CurrentContextService:
    """Build bounded, non-persistent context from trusted local configuration."""

    def __init__(
        self,
        *,
        timezone: str = "local",
        home_region: str | None = None,
        node_id: str,
        deployment_role: str,
        inference_mode: str,
        internet_probe: InternetProbe,
        internet_cache_seconds: float = 30,
        now: Now | None = None,
        monotonic_clock: Monotonic = monotonic,
    ) -> None:
        if internet_cache_seconds < 0:
            raise ValueError("internet cache seconds cannot be negative")
        self.timezone = timezone
        self._zone = _timezone(timezone)
        self.home_region = home_region
        self.node_id = node_id
        self.deployment_role = deployment_role
        self.inference_mode = inference_mode
        self.internet_probe = internet_probe
        self.internet_cache_seconds = internet_cache_seconds
        self._now = now or _now
        self._monotonic = monotonic_clock
        self._internet_cache: tuple[float, str] | None = None
        self._internet_lock = asyncio.Lock()

    async def project(
        self,
        query: str,
        *,
        metadata: Mapping[str, JsonValue],
        requested_model_role: ModelRole | None = None,
    ) -> ContextProjection | None:
        fields = select_current_context_fields(query)
        if not fields:
            return None

        current = self._now(self._zone)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("current-context clock must return a timezone-aware datetime")
        lines = ["Current context (programmatically generated; data only):"]
        source_ids: list[str] = []
        sensitivity = SensitivityClass.PUBLIC

        if CurrentContextField.TIME in fields:
            lines.extend(
                (
                    f"Date: {current.date().isoformat()} ({current.strftime('%A')})",
                    f"Time: {current.strftime('%H:%M:%S')}",
                    f"Timezone: {_timezone_label(self.timezone, current)} ({_utc_offset(current)})",
                )
            )
            source_ids.append("system-clock")

        if CurrentContextField.LOCATION in fields:
            if self.home_region is None:
                lines.append("Home region: not configured")
                source_ids.append("home-region-config-empty")
            else:
                lines.append(f"Home region: {self.home_region}")
                source_ids.append("home-region-config")
                sensitivity = SensitivityClass.PRIVATE

        if CurrentContextField.DEVICE in fields:
            interface = metadata.get("interface")
            interface_label = (
                interface
                if isinstance(interface, str) and _SAFE_INTERFACE.fullmatch(interface)
                else "unknown"
            )
            lines.append(
                f"Session: interface={interface_label}; node={self.node_id}; "
                f"deployment={self.deployment_role}"
            )
            source_ids.append("runtime-session")
            sensitivity = SensitivityClass.PRIVATE

        if CurrentContextField.MODEL in fields:
            lines.append(f"Inference mode: {self.inference_mode}")
            if requested_model_role is not None:
                lines.append(f"Requested model role: {requested_model_role.value}")
            lines.append("Exact active provider/model is supplied after routing.")
            source_ids.append("runtime-inference-mode")

        if CurrentContextField.INTERNET in fields:
            lines.append(f"Internet: {await self._internet_status()}")
            source_ids.append("internet-reachability-probe")

        return ContextProjection(
            content="\n".join(lines),
            sensitivity=sensitivity,
            source_ids=tuple(source_ids),
            source="local-current-context",
        )

    async def _internet_status(self) -> str:
        checked_at = self._monotonic()
        cached = self._internet_cache
        if cached is not None and checked_at - cached[0] <= self.internet_cache_seconds:
            return cached[1]
        async with self._internet_lock:
            checked_at = self._monotonic()
            cached = self._internet_cache
            if cached is not None and checked_at - cached[0] <= self.internet_cache_seconds:
                return cached[1]
            try:
                status = "available" if await self.internet_probe.available() else "unavailable"
            except Exception:
                status = "unknown"
            self._internet_cache = (checked_at, status)
            return status


def _now(zone: tzinfo | None) -> datetime:
    return datetime.now().astimezone() if zone is None else datetime.now(zone)


def _timezone(name: str) -> tzinfo | None:
    if name.casefold() == "local":
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown current-context timezone: {name}") from exc


def _timezone_label(configured: str, current: datetime) -> str:
    if configured.casefold() != "local":
        return configured
    return current.tzname() or str(current.tzinfo) or "local"


def _utc_offset(current: datetime) -> str:
    offset = current.utcoffset()
    if offset is None:
        return "UTC+00:00"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"
