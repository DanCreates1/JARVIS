"""Owned, local-only values for Phase 7B gesture recognition."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from jarvis.core.models import CoreModel, Identifier
from jarvis.vision.models import MAX_CAPTURE_FRAMES

HAND_LANDMARK_COUNT = 21
MAX_HANDS_PER_FRAME = 2


class Handedness(StrEnum):
    LEFT = "left"
    RIGHT = "right"


class GestureKind(StrEnum):
    CLOSED_FIST = "closed_fist"
    OPEN_PALM = "open_palm"
    PINCH = "pinch"
    FINGER_ROLL_CLOCKWISE = "finger_roll_clockwise"
    FINGER_ROLL_COUNTERCLOCKWISE = "finger_roll_counterclockwise"


class CalibrationPose(StrEnum):
    CLOSED_FIST = "closed_fist"
    OPEN_PALM = "open_palm"
    PINCH = "pinch"


class NormalizedLandmark(CoreModel):
    """One MediaPipe-compatible normalized landmark; no identity or world coordinate."""

    x: Annotated[float, Field(ge=0, le=1)]
    y: Annotated[float, Field(ge=0, le=1)]
    z: Annotated[float, Field(ge=-2, le=2)] = 0.0

    @model_validator(mode="after")
    def require_finite(self) -> Self:
        if not all(math.isfinite(value) for value in (self.x, self.y, self.z)):
            raise ValueError("landmark coordinates must be finite")
        return self


class HandObservation(CoreModel):
    """Ephemeral local landmark observation for one hand in one capture frame."""

    handedness: Handedness
    handedness_confidence: Annotated[float, Field(ge=0, le=1)]
    tracking_confidence: Annotated[float, Field(ge=0, le=1)]
    landmarks: Annotated[
        tuple[NormalizedLandmark, ...],
        Field(min_length=HAND_LANDMARK_COUNT, max_length=HAND_LANDMARK_COUNT),
    ]
    local_only: Literal[True] = True
    retention: Literal["ephemeral"] = "ephemeral"

    @field_validator("handedness_confidence", "tracking_confidence")
    @classmethod
    def require_finite_confidence(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("hand confidence must be finite")
        return value


class LandmarkFrame(CoreModel):
    """Content-free frame identity plus zero, one, or conflicting hand observations."""

    session_id: Identifier
    sequence: Annotated[int, Field(ge=1, le=MAX_CAPTURE_FRAMES)]
    captured_at: datetime
    monotonic_ns: Annotated[int, Field(ge=0)]
    hands: Annotated[tuple[HandObservation, ...], Field(max_length=MAX_HANDS_PER_FRAME)] = ()
    local_only: Literal[True] = True
    retention: Literal["ephemeral"] = "ephemeral"

    @field_validator("captured_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("landmark timestamps must be timezone-aware")
        return value.astimezone(UTC)


class GestureCalibrationProfile(CoreModel):
    """Persistable aggregate thresholds; never raw landmarks or body geometry."""

    schema_version: Literal[1] = 1
    mirrored_input: bool = True
    min_tracking_confidence: Annotated[float, Field(ge=0.8, le=1)] = 0.85
    min_handedness_confidence: Annotated[float, Field(ge=0.8, le=1)] = 0.85
    pinch_ratio_threshold: Annotated[float, Field(ge=0.05, le=0.8)] = 0.70
    finger_extension_ratio_threshold: Annotated[float, Field(ge=1.01, le=2)] = 1.12
    finger_curl_ratio_threshold: Annotated[float, Field(ge=0.2, le=0.99)] = 0.92
    debounce_frames: Annotated[int, Field(ge=2, le=10)] = 3
    release_frames: Annotated[int, Field(ge=1, le=10)] = 2
    cooldown_ms: Annotated[int, Field(ge=250, le=10_000)] = 1_000
    max_frame_gap_ms: Annotated[int, Field(ge=50, le=1_000)] = 250
    max_observation_age_ms: Annotated[int, Field(ge=50, le=1_000)] = 300
    roll_window_frames: Annotated[int, Field(ge=4, le=30)] = 12
    roll_min_radians: Annotated[float, Field(ge=0.5, le=6.3)] = 1.4
    roll_direction_consistency: Annotated[float, Field(ge=0.6, le=1)] = 0.8

    @model_validator(mode="after")
    def validate_threshold_separation(self) -> Self:
        values = (
            self.min_tracking_confidence,
            self.min_handedness_confidence,
            self.pinch_ratio_threshold,
            self.finger_extension_ratio_threshold,
            self.finger_curl_ratio_threshold,
            self.roll_min_radians,
            self.roll_direction_consistency,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("calibration thresholds must be finite")
        if self.finger_curl_ratio_threshold >= self.finger_extension_ratio_threshold:
            raise ValueError("curl threshold must remain below extension threshold")
        if self.roll_window_frames < self.debounce_frames + 1:
            raise ValueError("roll window must exceed the debounce window")
        return self


class GestureObservation(CoreModel):
    """Recognized gesture only. Phase 7B deliberately has no action or approval fields."""

    event_id: Identifier
    session_id: Identifier
    gesture: GestureKind
    handedness: Handedness
    confidence: Annotated[float, Field(ge=0.8, le=1)]
    started_at: datetime
    detected_at: datetime
    start_sequence: Annotated[int, Field(ge=1, le=MAX_CAPTURE_FRAMES)]
    end_sequence: Annotated[int, Field(ge=1, le=MAX_CAPTURE_FRAMES)]
    local_only: Literal[True] = True
    retention: Literal["event_only"] = "event_only"

    @field_validator("started_at", "detected_at")
    @classmethod
    def require_event_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("gesture timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("confidence")
    @classmethod
    def require_finite_confidence(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("gesture confidence must be finite")
        return value

    @model_validator(mode="after")
    def validate_event_order(self) -> Self:
        if self.end_sequence < self.start_sequence:
            raise ValueError("gesture sequence range is reversed")
        if self.detected_at < self.started_at:
            raise ValueError("gesture timestamp range is reversed")
        return self


class LandmarkFailureCode(StrEnum):
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    MODEL_UNAVAILABLE = "model_unavailable"
    MODEL_INVALID = "model_invalid"
    DETECTION_TIMEOUT = "detection_timeout"
    CANCELLED = "cancelled"
    MALFORMED_RESULT = "malformed_result"


class LandmarkError(RuntimeError):
    """Content-free local detector failure."""

    def __init__(self, code: LandmarkFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code
