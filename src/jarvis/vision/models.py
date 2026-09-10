"""Strict values crossing the Phase 7 capture boundary."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from jarvis.core.models import CoreModel, Identifier

MAX_CAPTURE_FPS = 15.0
MAX_CAPTURE_FRAMES = 300
MAX_CAPTURE_MILLISECONDS = 30_000
MAX_FRAME_TIMEOUT_MILLISECONDS = 1_000
MAX_REGION_WIDTH = 1_920
MAX_REGION_HEIGHT = 1_080
MAX_REGION_PIXELS = MAX_REGION_WIDTH * MAX_REGION_HEIGHT
RGB_CHANNELS = 3
MAX_FRAME_BYTES = MAX_REGION_PIXELS * RGB_CHANNELS


class CaptureSource(StrEnum):
    CAMERA = "camera"
    SCREEN = "screen"


class CapturePurpose(StrEnum):
    GESTURE_CALIBRATION = "gesture_calibration"
    GESTURE_INPUT = "gesture_input"
    SCREEN_ANALYSIS = "screen_analysis"
    DIAGNOSTIC = "diagnostic"


class PixelFormat(StrEnum):
    RGB24 = "rgb24"


class RetentionPolicy(StrEnum):
    EPHEMERAL = "ephemeral"


class CaptureRegion(CoreModel):
    """Explicit bounded region in source pixel coordinates."""

    x: Annotated[int, Field(ge=-32_768, le=32_767)]
    y: Annotated[int, Field(ge=-32_768, le=32_767)]
    width: Annotated[int, Field(ge=1, le=MAX_REGION_WIDTH)]
    height: Annotated[int, Field(ge=1, le=MAX_REGION_HEIGHT)]

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if self.width * self.height > MAX_REGION_PIXELS:
            raise ValueError("capture region exceeds pixel limit")
        if self.x + self.width > 32_768 or self.y + self.height > 32_768:
            raise ValueError("capture region exceeds coordinate limit")
        return self


class CaptureRequest(CoreModel):
    """One explicit foreground capture envelope; it cannot authorize recognition or actions."""

    source: CaptureSource
    source_id: Identifier
    purpose: CapturePurpose
    region: CaptureRegion
    requested_fps: Annotated[float, Field(ge=1, le=MAX_CAPTURE_FPS)] = 10.0
    camera_exposure: Annotated[int, Field(ge=-13, le=0)] | None = None
    max_frames: Annotated[int, Field(ge=1, le=MAX_CAPTURE_FRAMES)] = 1
    max_duration_ms: Annotated[int, Field(ge=100, le=MAX_CAPTURE_MILLISECONDS)] = 1_000
    open_timeout_ms: Annotated[int, Field(ge=100, le=5_000)] = 3_000
    frame_timeout_ms: Annotated[int, Field(ge=50, le=MAX_FRAME_TIMEOUT_MILLISECONDS)] = 1_000
    consumer_timeout_ms: Annotated[int, Field(ge=50, le=MAX_FRAME_TIMEOUT_MILLISECONDS)] = 1_000
    max_frame_age_ms: Annotated[int, Field(ge=10, le=1_000)] = 250
    pixel_format: Literal[PixelFormat.RGB24] = PixelFormat.RGB24
    retention: Literal[RetentionPolicy.EPHEMERAL] = RetentionPolicy.EPHEMERAL
    cloud_allowed: Literal[False] = False
    biometric_processing: Literal[False] = False

    @model_validator(mode="after")
    def validate_source_shape(self) -> Self:
        if self.source is CaptureSource.CAMERA:
            if not self.source_id.startswith("camera:"):
                raise ValueError("camera source IDs must use camera:<index>")
            raw_index = self.source_id.removeprefix("camera:")
            if not raw_index.isascii() or not raw_index.isdigit() or not 0 <= int(raw_index) <= 31:
                raise ValueError("camera index must be an integer from 0 through 31")
            if self.region.x < 0 or self.region.y < 0:
                raise ValueError("camera regions cannot use negative coordinates")
        else:
            if self.source_id != "screen:desktop":
                raise ValueError("screen capture currently requires source_id='screen:desktop'")
            if self.camera_exposure is not None:
                raise ValueError("camera exposure is valid only for camera capture")
        theoretical_frames = math.ceil(self.requested_fps * (self.max_duration_ms / 1_000))
        if theoretical_frames < 1:
            raise ValueError("capture envelope cannot produce a frame")
        return self


class FrameMetadata(CoreModel):
    session_id: Identifier
    sequence: Annotated[int, Field(ge=1, le=MAX_CAPTURE_FRAMES)]
    source: CaptureSource
    source_id: Identifier
    purpose: CapturePurpose
    captured_at: datetime
    monotonic_ns: Annotated[int, Field(ge=0)]
    width: Annotated[int, Field(ge=1, le=MAX_REGION_WIDTH)]
    height: Annotated[int, Field(ge=1, le=MAX_REGION_HEIGHT)]
    pixel_format: Literal[PixelFormat.RGB24] = PixelFormat.RGB24
    byte_count: Annotated[int, Field(ge=1, le=MAX_FRAME_BYTES)]

    @field_validator("captured_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("frame timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        expected = self.width * self.height * RGB_CHANNELS
        if self.byte_count != expected:
            raise ValueError("frame byte count does not match RGB24 dimensions")
        return self


class EphemeralFrame:
    """Controller-owned mutable pixels that are zeroed after consumer return."""

    __slots__ = ("_pixels", "_released", "metadata")

    def __init__(self, metadata: FrameMetadata, pixels: bytearray) -> None:
        if len(pixels) != metadata.byte_count:
            raise ValueError("frame buffer size does not match metadata")
        self.metadata = metadata
        self._pixels = pixels
        self._released = False

    @property
    def pixels(self) -> memoryview:
        if self._released:
            raise RuntimeError("frame buffer has been released")
        return memoryview(self._pixels).toreadonly()

    @property
    def released(self) -> bool:
        return self._released

    def release(self) -> None:
        if self._released:
            return
        self._pixels[:] = bytes(len(self._pixels))
        self._released = True


class CaptureControl(CoreModel):
    enabled: bool = False
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("updated_at")
    @classmethod
    def require_control_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("capture control timestamp must be timezone-aware")
        return value.astimezone(UTC)


class IndicatorState(CoreModel):
    session_id: Identifier
    source: CaptureSource
    source_id: Identifier
    purpose: CapturePurpose
    region: CaptureRegion
    requested_fps: Annotated[float, Field(ge=1, le=MAX_CAPTURE_FPS)]
    max_frames: Annotated[int, Field(ge=1, le=MAX_CAPTURE_FRAMES)]
    active: Literal[True] = True
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CaptureStopReason(StrEnum):
    FRAME_LIMIT = "frame_limit"
    DURATION_LIMIT = "duration_limit"
    CANCELLED = "cancelled"
    KILL_SWITCH = "kill_switch"


class CaptureSummary(CoreModel):
    session_id: Identifier
    source: CaptureSource
    source_id: Identifier
    purpose: CapturePurpose
    frames_delivered: Annotated[int, Field(ge=0, le=MAX_CAPTURE_FRAMES)]
    bytes_delivered: Annotated[int, Field(ge=0, le=MAX_FRAME_BYTES * MAX_CAPTURE_FRAMES)]
    duration_ms: Annotated[float, Field(ge=0, le=MAX_CAPTURE_MILLISECONDS + 5_000)]
    stop_reason: CaptureStopReason
    retention: Literal[RetentionPolicy.EPHEMERAL] = RetentionPolicy.EPHEMERAL


class CaptureFailureCode(StrEnum):
    DISABLED = "disabled"
    BUSY = "busy"
    SETTINGS_INVALID = "settings_invalid"
    INDICATOR_FAILED = "indicator_failed"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    SOURCE_UNAVAILABLE = "source_unavailable"
    SOURCE_LOST = "source_lost"
    SOURCE_MISMATCH = "source_mismatch"
    FRAME_STALE = "frame_stale"
    OPEN_TIMEOUT = "open_timeout"
    FRAME_TIMEOUT = "frame_timeout"
    CONSUMER_TIMEOUT = "consumer_timeout"
    MALFORMED_FRAME = "malformed_frame"


class CaptureError(RuntimeError):
    """Content-free classified failure crossing the capture boundary."""

    def __init__(self, code: CaptureFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code
