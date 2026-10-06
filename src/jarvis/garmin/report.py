"""Local batch health report using the owner's existing demo session only."""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from jarvis.garmin.bridge import normalize_summary

# Fixed reads only. Never enumerate or execute the upstream demo's menu.
READS = {
    "daily": "get_stats",
    "heart": "get_heart_rates",
    "sleep": "get_sleep_data",
    "stress": "get_stress_data",
    "body_battery": "get_body_battery",
    "hrv": "get_hrv_data",
    "readiness": "get_training_readiness",
    "respiration": "get_respiration_data",
    "spo2": "get_spo2_data",
    "intensity": "get_intensity_minutes_data",
    "hydration": "get_hydration_data",
    "body_composition": "get_body_composition",
    "fitness": "get_max_metrics",
    "activities": "get_activities",
}

_ACTIVITY_TYPES = frozenset(
    {
        "walking",
        "running",
        "trail_running",
        "treadmill_running",
        "hiking",
        "cycling",
        "road_biking",
        "mountain_biking",
        "indoor_cycling",
        "swimming",
        "lap_swimming",
        "open_water_swimming",
        "strength_training",
        "cardio_training",
        "yoga",
        "elliptical",
        "stair_climbing",
        "rowing",
        "golf",
        "other",
    }
)


def _activity(row: dict[str, str]) -> dict[str, str]:
    try:
        started = datetime.fromisoformat(row["started"]).isoformat(timespec="seconds")
    except ValueError:
        started = ""
    return {"type": row["type"] if row["type"] in _ACTIVITY_TYPES else "other", "started": started}


# Explicit response paths and units. Unknown fields, IDs, locations, account
# details, free text, and time series never enter the report.
FIELDS: dict[str, dict[str, tuple[str, float, float]]] = {
    "daily": {
        "steps": ("totalSteps", 0, 200_000),
        "distance_m": ("totalDistanceMeters", 0, 500_000),
        "calories_kcal": ("totalKilocalories", 0, 30_000),
        "active_calories_kcal": ("activeKilocalories", 0, 30_000),
        "floors_climbed": ("floorsAscended", 0, 5_000),
    },
    "heart": {
        "resting_bpm": ("restingHeartRate", 20, 240),
        "minimum_bpm": ("minHeartRate", 20, 240),
        "maximum_bpm": ("maxHeartRate", 20, 240),
    },
    "sleep": {
        "total_seconds": ("dailySleepDTO.sleepTimeSeconds", 0, 86_400),
        "deep_seconds": ("dailySleepDTO.deepSleepSeconds", 0, 86_400),
        "light_seconds": ("dailySleepDTO.lightSleepSeconds", 0, 86_400),
        "rem_seconds": ("dailySleepDTO.remSleepSeconds", 0, 86_400),
        "awake_seconds": ("dailySleepDTO.awakeSleepSeconds", 0, 86_400),
        "score": ("dailySleepDTO.sleepScores.overall.value", 0, 100),
    },
    "stress": {"average": ("avgStressLevel", 0, 100)},
    "hrv": {
        "last_night_ms": ("hrvSummary.lastNightAvg", 0, 500),
        "weekly_ms": ("hrvSummary.weeklyAvg", 0, 500),
    },
    "readiness": {
        "score": ("0.score", 0, 100),
        "recovery_minutes": ("0.recoveryTime", 0, 10_080),
    },
    "respiration": {
        "waking_breaths_per_min": ("avgWakingRespirationValue", 0, 100),
        "sleeping_breaths_per_min": ("avgSleepRespirationValue", 0, 100),
    },
    "spo2": {
        "average_percent": ("averageSpO2", 0, 100),
        "lowest_percent": ("lowestSpO2", 0, 100),
        "latest_percent": ("latestSpO2", 0, 100),
    },
    "intensity": {
        "moderate_minutes": ("moderateIntensityMinutes", 0, 1_440),
        "vigorous_minutes": ("vigorousIntensityMinutes", 0, 1_440),
    },
    "hydration": {
        "consumed_ml": ("valueInML", 0, 30_000),
        "goal_ml": ("goalInML", 0, 30_000),
    },
    "body_composition": {
        "weight_g": ("totalAverage.weight", 1_000, 700_000),
        "body_fat_percent": ("totalAverage.bodyFat", 0, 100),
        "bmi": ("totalAverage.bmi", 1, 150),
    },
    "fitness": {
        "running_vo2_max": ("0.generic.vo2MaxPreciseValue", 1, 150),
        "cycling_vo2_max": ("0.cycling.vo2MaxPreciseValue", 1, 150),
    },
}


def _metric(raw: Any, path: str, minimum: float, maximum: float) -> int | float | None:
    for component in path.split("."):
        if isinstance(raw, dict):
            raw = raw.get(component)
        elif isinstance(raw, list) and component.isdecimal() and int(component) < len(raw):
            raw = raw[int(component)]
        else:
            return None
    if type(raw) not in (int, float) or not minimum <= raw <= maximum or not math.isfinite(raw):
        return None
    return int(raw) if type(raw) is int else round(float(raw), 2)


def collect_report(client: Any, day: date) -> dict[str, Any]:
    """Read each supported category once; unavailable never means zero."""
    raw: dict[str, Any] = {}
    states: dict[str, str] = {}
    stop = False
    for category, method in READS.items():
        if stop:
            states[category] = "skipped_after_rate_limit"
            continue
        try:
            call = getattr(client, method)
            value = call(0, 3) if category == "activities" else call(day.isoformat())
            if not value:
                states[category] = "no_data"
            elif len(json.dumps(value, allow_nan=False)) > 1_000_000:
                states[category] = "invalid_response"
            else:
                raw[category] = value
                states[category] = "read"
        except Exception as exc:
            # Do not retain exception text: upstream failures can contain private data.
            stop = type(exc).__name__ == "GarminConnectTooManyRequestsError"
            states[category] = "rate_limited" if stop else "unavailable"
    if not raw:
        raise ValueError("No Garmin health categories available")
    summary = normalize_summary(
        day=day,
        stats=raw.get("daily"),
        heart=raw.get("heart"),
        sleep=raw.get("sleep"),
        stress=raw.get("stress"),
        battery=raw.get("body_battery"),
        activities=raw.get("activities"),
    )
    # Activity names are free text; omit them from this machine-consumable report.
    summary["activities"] = [_activity(row) for row in summary["activities"]]
    sections: dict[str, Any] = {}
    for category in READS:
        metrics: dict[str, Any] = {
            name: _metric(raw.get(category), *spec)
            for name, spec in FIELDS.get(category, {}).items()
        }
        if category == "body_battery":
            metrics = {"latest_percent": summary["body_battery"]}
        elif category == "activities":
            metrics = {"recent": summary["activities"]}
        state = states[category]
        if state == "read":
            state = (
                "available"
                if any(v is not None and v != [] for v in metrics.values())
                else "no_supported_values"
            )
        sections[category] = {"status": state, "metrics": metrics}
    return {"schema_version": 1, "summary": summary, "sections": sections}


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Local Garmin report",
        "",
        "Private health data. Keep local; do not paste into cloud chat or commit to Git.",
        "",
        f"Date: {report['summary']['date']}",
        f"Fetched: {report['summary']['refreshed_at']}",
        "",
        "Missing values mean unavailable, never zero. Recent activities may predate report date.",
        "",
    ]
    for category, section in report["sections"].items():
        lines.extend([f"## {category.replace('_', ' ')} ({section['status']})", ""])
        for name, value in section["metrics"].items():
            lines.append(f"- {name}: {json.dumps(value) if value is not None else 'unavailable'}")
        lines.append("")
    return "\n".join(lines)


def read_saved_session(tokenstore: Path, day: date) -> dict[str, Any]:
    """Use already configured local demo session. Never prompt for credentials."""
    import logging

    from garminconnect import Garmin  # type: ignore[import-not-found]

    logging.disable(logging.CRITICAL)
    client = Garmin(retry_attempts=0)
    client.login(str(tokenstore.expanduser()))
    return collect_report(client, day)


def write_report(report: dict[str, Any], directory: Path) -> tuple[Path, Path]:
    """Unique report files, without overwriting prior private reports."""
    from uuid import uuid4

    directory.mkdir(parents=True, exist_ok=True)
    name = f"garmin-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    json_path = directory / f"{name}.json"
    markdown_path = directory / f"{name}.md"
    with json_path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    with markdown_path.open("x", encoding="utf-8") as stream:
        stream.write(render_markdown(report))
    return json_path, markdown_path
