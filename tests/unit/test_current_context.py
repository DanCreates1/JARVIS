from __future__ import annotations

from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo

import pytest

from jarvis.core import ModelRole, SensitivityClass
from jarvis.current_context import (
    CurrentContextField,
    CurrentContextService,
    select_current_context_fields,
)


class FakeInternetProbe:
    def __init__(self, result: bool | BaseException) -> None:
        self.result = result
        self.calls = 0

    async def available(self) -> bool:
        self.calls += 1
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def fixed_now(zone: tzinfo | None) -> datetime:
    value = datetime(2026, 9, 15, 21, 52, 3, tzinfo=ZoneInfo("America/Toronto"))
    return value if zone is None else value.astimezone(zone)


def service(
    probe: FakeInternetProbe,
    *,
    home_region: str | None = None,
    monotonic_clock=lambda: 10.0,
) -> CurrentContextService:
    return CurrentContextService(
        timezone="America/Toronto",
        home_region=home_region,
        node_id="node:local-core",
        deployment_role="local-core",
        inference_mode="hybrid",
        internet_probe=probe,
        internet_cache_seconds=30,
        now=fixed_now,
        monotonic_clock=monotonic_clock,
    )


def test_field_selection_is_deterministic_and_request_relevant() -> None:
    assert select_current_context_fields("Explain photosynthesis") == frozenset()
    assert select_current_context_fields("What time is it?") == {CurrentContextField.TIME}
    assert select_current_context_fields("What is the latest weather near me?") == {
        CurrentContextField.TIME,
        CurrentContextField.LOCATION,
        CurrentContextField.INTERNET,
    }
    assert select_current_context_fields("Which model provider is active?") == {
        CurrentContextField.TIME,
        CurrentContextField.MODEL,
    }


@pytest.mark.asyncio
async def test_projection_omits_irrelevant_context_and_renders_exact_time() -> None:
    probe = FakeInternetProbe(True)
    current = service(probe)

    assert await current.project("Explain photosynthesis", metadata={}) is None
    projection = await current.project("What date is today?", metadata={})

    assert projection is not None
    assert projection.sensitivity is SensitivityClass.PUBLIC
    assert "Date: 2026-09-15 (Tuesday)" in projection.content
    assert "Time: 21:52:03" in projection.content
    assert "Timezone: America/Toronto (UTC-04:00)" in projection.content
    assert "Internet:" not in projection.content
    assert probe.calls == 0


@pytest.mark.asyncio
async def test_location_and_device_context_are_private_and_configured() -> None:
    current = service(
        FakeInternetProbe(True),
        home_region="Richmond Hill / Toronto area, Ontario, Canada",
    )

    projection = await current.project(
        "What is nearby on this device?",
        metadata={"interface": "browser", "ignored": "do not disclose"},
    )

    assert projection is not None
    assert projection.sensitivity is SensitivityClass.PRIVATE
    assert "Home region: Richmond Hill / Toronto area, Ontario, Canada" in projection.content
    assert "interface=browser; node=node:local-core; deployment=local-core" in projection.content
    assert "ignored" not in projection.content


@pytest.mark.asyncio
async def test_internet_probe_is_bounded_cached_and_failure_safe() -> None:
    ticks = iter((10.0, 10.0, 20.0, 45.0, 45.0))
    probe = FakeInternetProbe(True)
    current = service(probe, monotonic_clock=lambda: next(ticks))

    first = await current.project("latest news", metadata={})
    second = await current.project("live sports scores", metadata={})
    third = await current.project("current software version", metadata={})

    assert first is not None and "Internet: available" in first.content
    assert second is not None and "Internet: available" in second.content
    assert third is not None and "Internet: available" in third.content
    assert probe.calls == 2

    failed = service(FakeInternetProbe(RuntimeError("offline")))
    unknown = await failed.project("latest news", metadata={})
    assert unknown is not None and "Internet: unknown" in unknown.content


@pytest.mark.asyncio
async def test_model_context_reports_mode_without_guessing_active_route() -> None:
    current = service(FakeInternetProbe(True))

    projection = await current.project(
        "Which model is active?",
        metadata={},
        requested_model_role=ModelRole.REASONING,
    )

    assert projection is not None
    assert "Inference mode: hybrid" in projection.content
    assert "Requested model role: reasoning" in projection.content
    assert "Exact active provider/model is supplied after routing." in projection.content
