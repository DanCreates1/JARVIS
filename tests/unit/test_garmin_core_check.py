"""Core acceptance diagnostics use synthetic sessions and disclose no health values."""

from __future__ import annotations

import importlib.util
import json
import logging
import socket
import sys
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from jarvis.garmin import service as service_module
from jarvis.garmin.service import GarminSummary, GarminUnavailableError

_PRIVATE = "SYNTHETIC_PRIVATE_GARMIN_DIAGNOSTIC"
_NOW = datetime(2026, 10, 8, 16, 30, tzinfo=UTC)
_FIELDS = (
    "steps",
    "resting_heart_rate",
    "sleep_minutes",
    "stress",
    "body_battery",
    "activities",
)
_OUTPUT_FIELDS = {"status", "schema_valid", "fresh", "available", "activity_bound"}


def _load_script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "garmin_core_check.py"
    spec = importlib.util.spec_from_file_location("garmin_core_check_test_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    spec.loader.exec_module(module)
    return module


CHECK = _load_script()


@pytest.fixture(autouse=True)
def block_real_session_access(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("Synthetic check must not access real sessions or network")

    monkeypatch.setattr(service_module.GarminSummaryService, "summary", forbidden)
    monkeypatch.setattr(service_module.asyncio, "create_subprocess_exec", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

    def run_synthetic(coroutine: Coroutine[Any, Any, Any]) -> Any:
        # Immediate synthetic reads need no event loop or Windows socketpair.
        # Service tests separately cover subprocess scheduling and cancellation.
        try:
            coroutine.send(None)
        except StopIteration as finished:
            return finished.value
        finally:
            coroutine.close()
        raise AssertionError("Synthetic read unexpectedly scheduled external work")

    monkeypatch.setattr(CHECK.asyncio, "run", run_synthetic)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return _NOW.astimezone(tz) if tz is not None else _NOW.astimezone().replace(tzinfo=None)

    monkeypatch.setattr(CHECK, "datetime", FrozenDateTime)


def _summary(**overrides: Any) -> GarminSummary:
    values: dict[str, Any] = {
        "date": _NOW.astimezone().date().isoformat(),
        "refreshed_at": _NOW,
        "steps": 76_543,
        "resting_heart_rate": 63,
        "sleep_minutes": 487,
        "stress": 37,
        "body_battery": 81,
        "activities": [
            {"name": _PRIVATE, "type": "walking", "started": "2026-10-08T09:25:00"},
        ],
    }
    values.update(overrides)
    return GarminSummary.model_validate(values)


def _fake_service(monkeypatch: pytest.MonkeyPatch, result: GarminSummary) -> tuple[Mock, AsyncMock]:
    read = AsyncMock(return_value=result)
    factory = Mock(return_value=Mock(summary=read))
    monkeypatch.setattr(CHECK, "GarminSummaryService", factory)
    return factory, read


def _result(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    output = capsys.readouterr()
    assert not output.err
    assert _PRIVATE not in output.out
    result = json.loads(output.out)
    assert set(result) == _OUTPUT_FIELDS
    assert set(result["available"]) == set(_FIELDS)
    assert all(type(value) is bool for value in result["available"].values())
    assert type(result["schema_valid"]) is bool
    assert type(result["fresh"]) is bool
    assert type(result["activity_bound"]) is bool
    return result


def test_core_check_requires_explicit_read_without_creating_service(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    factory = Mock(side_effect=AssertionError("Unauthorized service creation"))
    monkeypatch.setattr(CHECK, "GarminSummaryService", factory)

    assert CHECK.main([]) == 2

    factory.assert_not_called()
    output = capsys.readouterr()
    assert "authority" in (output.out + output.err).lower()
    assert _PRIVATE not in output.out + output.err


def test_core_check_full_summary_reads_once_and_emits_only_presence(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    factory, read = _fake_service(monkeypatch, _summary())

    assert CHECK.main(["--read"]) == 0

    factory.assert_called_once_with()
    read.assert_awaited_once_with(refresh=True)
    assert _result(capsys) == {
        "status": "pass",
        "schema_valid": True,
        "fresh": True,
        "available": dict.fromkeys(_FIELDS, True),
        "activity_bound": True,
    }


@pytest.mark.parametrize("available_field", _FIELDS)
def test_core_check_accepts_partial_data_without_turning_missing_values_into_zero(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    available_field: str,
) -> None:
    values = dict.fromkeys(_FIELDS, None)
    values["activities"] = []
    values[available_field] = (
        [{"name": _PRIVATE, "type": "walking", "started": ""}]
        if available_field == "activities"
        else 63
        if available_field == "resting_heart_rate"
        else 0
    )
    _, read = _fake_service(monkeypatch, _summary(**values))

    assert CHECK.main(["--read"]) == 0

    read.assert_awaited_once_with(refresh=True)
    result = _result(capsys)
    assert result["status"] == "pass"
    assert result["schema_valid"] and result["fresh"] and result["activity_bound"]
    assert result["available"] == {field: field == available_field for field in _FIELDS}


def test_core_check_absent_metrics_do_not_pass(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    values = dict.fromkeys(_FIELDS, None)
    values["activities"] = []
    _, read = _fake_service(monkeypatch, _summary(**values))

    assert CHECK.main(["--read"]) == 1

    read.assert_awaited_once_with(refresh=True)
    result = _result(capsys)
    assert result["status"] == "unavailable"
    assert result["schema_valid"] and result["fresh"] and result["activity_bound"]
    assert result["available"] == dict.fromkeys(_FIELDS, False)


@pytest.mark.parametrize("age", [0, 300])
def test_core_check_accepts_inclusive_freshness_bounds(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], age: int
) -> None:
    _fake_service(monkeypatch, _summary(refreshed_at=_NOW - timedelta(seconds=age)))

    assert CHECK.main(["--read"]) == 0

    assert _result(capsys)["fresh"] is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"refreshed_at": _NOW - timedelta(seconds=300, microseconds=1)},
        {"refreshed_at": _NOW + timedelta(microseconds=1)},
        {"refreshed_at": _NOW.replace(tzinfo=None)},
        {"date": (_NOW.astimezone().date() - timedelta(days=1)).isoformat()},
        {"date": (_NOW.astimezone().date() + timedelta(days=1)).isoformat()},
    ],
    ids=("stale", "future", "naive", "yesterday", "tomorrow"),
)
def test_core_check_rejects_stale_future_naive_or_wrong_day(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    overrides: dict[str, Any],
) -> None:
    _, read = _fake_service(monkeypatch, _summary(**overrides))

    assert CHECK.main(["--read"]) == 1

    read.assert_awaited_once_with(refresh=True)
    result = _result(capsys)
    assert result["status"] == "unavailable"
    assert result["schema_valid"] is True
    assert result["fresh"] is False


@pytest.mark.parametrize("use_local_day", [True, False])
def test_core_check_uses_local_day_at_utc_midnight_boundary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    use_local_day: bool,
) -> None:
    near_midnight = datetime(2026, 10, 8, 0, 30, tzinfo=UTC)
    local_zone = timezone(timedelta(hours=-4))

    class LocalClock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return cls(2026, 10, 8, 0, 30, tzinfo=UTC)

        def astimezone(self, tz: Any = None) -> datetime:
            return super().astimezone(tz if tz is not None else local_zone)

    monkeypatch.setattr(CHECK, "datetime", LocalClock)
    day = near_midnight.astimezone(local_zone).date() if use_local_day else near_midnight.date()
    _fake_service(monkeypatch, _summary(date=day.isoformat(), refreshed_at=near_midnight))

    assert CHECK.main(["--read"]) == (0 if use_local_day else 1)

    assert _result(capsys)["fresh"] is use_local_day


@pytest.mark.parametrize("raises", [False, True])
def test_core_check_suppresses_private_diagnostics_and_restores_logging(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    raises: bool,
) -> None:
    async def noisy_read(*, refresh: bool) -> GarminSummary:
        assert refresh is True
        print(_PRIVATE)
        print(_PRIVATE, file=sys.stderr)
        logging.warning(_PRIVATE)
        if raises:
            raise GarminUnavailableError(_PRIVATE)
        return _summary()

    read = AsyncMock(side_effect=noisy_read)
    monkeypatch.setattr(CHECK, "GarminSummaryService", Mock(return_value=Mock(summary=read)))
    monkeypatch.setattr(logging.root.manager, "disable", 17)

    assert CHECK.main(["--read"]) == (1 if raises else 0)

    read.assert_awaited_once_with(refresh=True)
    assert logging.root.manager.disable == 17
    assert _PRIVATE not in caplog.text
    assert _result(capsys)["status"] == ("unavailable" if raises else "pass")


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError, OSError, KeyboardInterrupt])
def test_core_check_generic_errors_never_retry_or_expose_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error_type: type[BaseException],
) -> None:
    read = AsyncMock(side_effect=error_type(_PRIVATE))
    monkeypatch.setattr(CHECK, "GarminSummaryService", Mock(return_value=Mock(summary=read)))

    assert CHECK.main(["--read"]) == 1

    read.assert_awaited_once_with(refresh=True)
    assert _result(capsys)["status"] == "unavailable"


def test_core_check_constructor_failure_remains_generic(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    factory = Mock(side_effect=RuntimeError(_PRIVATE))
    monkeypatch.setattr(CHECK, "GarminSummaryService", factory)

    assert CHECK.main(["--read"]) == 1

    factory.assert_called_once_with()
    result = _result(capsys)
    assert result["status"] == "unavailable"
    assert result["schema_valid"] is False
