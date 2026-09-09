from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from jarvis.gestures.models import (
    GestureCalibrationProfile,
    Handedness,
    HandObservation,
    LandmarkFrame,
    NormalizedLandmark,
)

BASE_TIME = datetime(2026, 9, 8, 20, 0, tzinfo=UTC)


def hand(
    pose: str,
    *,
    handedness: Handedness = Handedness.RIGHT,
    confidence: float = 0.95,
    angle: float = 0.0,
) -> HandObservation:
    points = [(0.5, 0.65, 0.0) for _ in range(21)]
    points[0] = (0.5, 0.8, 0.0)
    points[5] = (0.34, 0.56, 0.0)
    points[9] = (0.45, 0.52, 0.0)
    points[13] = (0.56, 0.54, 0.0)
    points[17] = (0.67, 0.59, 0.0)
    points[4] = (0.2, 0.38, 0.0)
    pips = (6, 10, 14, 18)
    tips = (8, 12, 16, 20)
    if pose in {"open", "pinch"}:
        for offset, (pip, tip) in enumerate(zip(pips, tips, strict=True)):
            x = 0.34 + offset * 0.11
            points[pip] = (x, 0.38 + offset * 0.01, 0.0)
            points[tip] = (x, 0.14 + offset * 0.015, 0.0)
        if pose == "pinch":
            index = points[8]
            points[4] = (index[0] + 0.01, index[1] + 0.01, 0.0)
    elif pose == "fist":
        for offset, (pip, tip) in enumerate(zip(pips, tips, strict=True)):
            x = 0.39 + offset * 0.07
            points[pip] = (x, 0.57, 0.0)
            points[tip] = (x, 0.72, 0.0)
    elif pose == "roll":
        points[6] = (0.501, 0.799, 0.0)
        center_x = (points[0][0] + points[5][0] + points[9][0] + points[17][0]) / 4
        center_y = (points[0][1] + points[5][1] + points[9][1] + points[17][1]) / 4
        points[8] = (
            center_x + 0.19 * math.cos(angle),
            center_y + 0.19 * math.sin(angle),
            0.0,
        )
        for offset, (pip, tip) in enumerate(zip(pips[1:], tips[1:], strict=True)):
            x = 0.45 + offset * 0.08
            points[pip] = (x, 0.58, 0.0)
            points[tip] = (x, 0.73, 0.0)
    elif pose != "ambiguous":
        raise ValueError("unknown fixture pose")
    return HandObservation(
        handedness=handedness,
        handedness_confidence=confidence,
        tracking_confidence=confidence,
        landmarks=tuple(NormalizedLandmark(x=x, y=y, z=z) for x, y, z in points),
    )


def frame(
    sequence: int,
    *hands: HandObservation,
    session_id: str = "gesture-session",
    step_ms: int = 100,
    captured_at: datetime | None = None,
) -> LandmarkFrame:
    return LandmarkFrame(
        session_id=session_id,
        sequence=sequence,
        captured_at=captured_at or BASE_TIME + timedelta(milliseconds=sequence * step_ms),
        monotonic_ns=sequence * step_ms * 1_000_000,
        hands=hands,
    )


def gesture_profile(**updates: object) -> GestureCalibrationProfile:
    values: dict[str, object] = {
        "mirrored_input": False,
        "cooldown_ms": 250,
        "max_observation_age_ms": 1_000,
        "roll_min_radians": 1.2,
    }
    values.update(updates)
    return GestureCalibrationProfile(**values)
