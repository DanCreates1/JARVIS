"""Ephemeral geometric features derived from owned normalized landmarks."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import GestureCalibrationProfile, HandObservation, NormalizedLandmark

_WRIST = 0
_THUMB_TIP = 4
_INDEX_MCP = 5
_INDEX_PIP = 6
_INDEX_TIP = 8
_MIDDLE_MCP = 9
_MIDDLE_PIP = 10
_MIDDLE_TIP = 12
_RING_MCP = 13
_RING_PIP = 14
_RING_TIP = 16
_PINKY_MCP = 17
_PINKY_PIP = 18
_PINKY_TIP = 20
_FINGERS = (
    (_INDEX_PIP, _INDEX_TIP),
    (_MIDDLE_PIP, _MIDDLE_TIP),
    (_RING_PIP, _RING_TIP),
    (_PINKY_PIP, _PINKY_TIP),
)


@dataclass(frozen=True, slots=True)
class GestureFeatures:
    pinch_ratio: float
    extension_ratios: tuple[float, float, float, float]
    roll_angle: float
    roll_radius_ratio: float

    def extended(self, profile: GestureCalibrationProfile) -> tuple[bool, bool, bool, bool]:
        return tuple(  # type: ignore[return-value]
            value >= profile.finger_extension_ratio_threshold for value in self.extension_ratios
        )

    def curled(self, profile: GestureCalibrationProfile) -> tuple[bool, bool, bool, bool]:
        return tuple(  # type: ignore[return-value]
            value <= profile.finger_curl_ratio_threshold for value in self.extension_ratios
        )


def extract_features(observation: HandObservation) -> GestureFeatures:
    landmarks = observation.landmarks
    wrist = landmarks[_WRIST]
    palm_width = _distance(landmarks[_INDEX_MCP], landmarks[_PINKY_MCP])
    if palm_width <= 1e-6:
        raise ValueError("degenerate palm width")
    extension_ratios: list[float] = []
    for pip_index, tip_index in _FINGERS:
        denominator = _distance(wrist, landmarks[pip_index])
        if denominator <= 1e-6:
            raise ValueError("degenerate finger geometry")
        extension_ratios.append(_distance(wrist, landmarks[tip_index]) / denominator)
    pinch_ratio = _distance(landmarks[_THUMB_TIP], landmarks[_INDEX_TIP]) / palm_width
    center_x = (
        wrist.x + landmarks[_INDEX_MCP].x + landmarks[_MIDDLE_MCP].x + landmarks[_PINKY_MCP].x
    ) / 4
    center_y = (
        wrist.y + landmarks[_INDEX_MCP].y + landmarks[_MIDDLE_MCP].y + landmarks[_PINKY_MCP].y
    ) / 4
    roll_dx = landmarks[_INDEX_TIP].x - center_x
    roll_dy = landmarks[_INDEX_TIP].y - center_y
    roll_radius = math.hypot(roll_dx, roll_dy)
    values = (pinch_ratio, *extension_ratios, roll_radius)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("derived gesture features must be finite")
    return GestureFeatures(
        pinch_ratio=pinch_ratio,
        extension_ratios=(
            extension_ratios[0],
            extension_ratios[1],
            extension_ratios[2],
            extension_ratios[3],
        ),
        roll_angle=math.atan2(roll_dy, roll_dx),
        roll_radius_ratio=roll_radius / palm_width,
    )


def _distance(left: NormalizedLandmark, right: NormalizedLandmark) -> float:
    return math.sqrt((left.x - right.x) ** 2 + (left.y - right.y) ** 2 + (left.z - right.z) ** 2)
