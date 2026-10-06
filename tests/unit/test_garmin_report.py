"""Batch report bounds, privacy, partial data, and rate-limit handling."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from jarvis.garmin.report import READS, collect_report, render_markdown, write_report


class FakeClient:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def __getattr__(self, method: str) -> Any:
        assert method in READS.values(), "Only fixed read methods allowed"

        def call(*args: object) -> Any:
            self.calls.append(method)
            assert args == ((0, 3) if method == "get_activities" else ("2026-10-05",))
            value = self.responses.get(method)
            if isinstance(value, Exception):
                raise value
            return value

        return call


def test_batch_report_omits_private_fields_and_handles_partial_data(tmp_path: Path) -> None:
    client = FakeClient(
        {
            "get_stats": {"totalSteps": 8000, "email": "PRIVATE", "latitude": 43.6},
            "get_sleep_data": {"dailySleepDTO": {"sleepTimeSeconds": 25_200}},
            "get_hrv_data": {"hrvSummary": {"lastNightAvg": 52, "userId": "PRIVATE"}},
            "get_hydration_data": RuntimeError("PRIVATE token in upstream exception"),
            "get_activities": [
                {"activityName": "PRIVATE", "activityType": {"typeKey": "walking"}},
                {"activityType": {"typeKey": "PRIVATE"}, "startTimeLocal": "PRIVATE"},
            ],
        }
    )
    report = collect_report(client, date(2026, 10, 5))
    assert report["summary"]["steps"] == 8000
    assert report["summary"]["sleep_minutes"] == 420
    assert report["sections"]["hrv"]["metrics"]["last_night_ms"] == 52
    assert report["sections"]["hydration"]["status"] == "unavailable"
    assert report["sections"]["spo2"]["status"] == "no_data"
    assert len(client.calls) == len(READS)
    assert "PRIVATE" not in json.dumps(report) + render_markdown(report)
    assert "latitude" not in json.dumps(report)
    first = write_report(report, tmp_path)
    second = write_report(report, tmp_path)
    assert first != second
    assert json.loads(first[0].read_text(encoding="utf-8")) == report
    assert "Private health data" in first[1].read_text(encoding="utf-8")


@pytest.mark.parametrize("value", [True, -1, 200_001, 10**1000, float("nan"), float("inf"), "8000"])
def test_batch_report_rejects_bad_metric(value: object) -> None:
    report = collect_report(
        FakeClient(
            {"get_stats": {"totalSteps": value}, "get_heart_rates": {"restingHeartRate": 60}}
        ),
        date(2026, 10, 5),
    )
    assert report["sections"]["daily"]["metrics"]["steps"] is None


def test_batch_report_rejects_oversized_response() -> None:
    with pytest.raises(ValueError, match="No Garmin health categories"):
        collect_report(FakeClient({"get_stats": {"private": "x" * 1_000_001}}), date(2026, 10, 5))


def test_batch_report_stops_after_rate_limit() -> None:
    class GarminConnectTooManyRequestsError(Exception):
        pass

    client = FakeClient(
        {
            "get_stats": {"totalSteps": 1000},
            "get_heart_rates": GarminConnectTooManyRequestsError("PRIVATE"),
        }
    )
    report = collect_report(client, date(2026, 10, 5))
    assert client.calls == ["get_stats", "get_heart_rates"]
    assert report["sections"]["heart"]["status"] == "rate_limited"
    assert report["sections"]["sleep"]["status"] == "skipped_after_rate_limit"
    assert "PRIVATE" not in json.dumps(report)


def test_batch_report_all_failed_never_claims_success() -> None:
    with pytest.raises(ValueError, match="No Garmin health categories"):
        collect_report(FakeClient({}), date(2026, 10, 5))
