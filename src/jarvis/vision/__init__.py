"""Local-only Phase 7A capture/privacy subsystem."""

from .contracts import CaptureIndicator, CaptureSettingsStore, FrameConsumer, FrameSource
from .models import (
    CaptureControl,
    CaptureError,
    CaptureFailureCode,
    CapturePurpose,
    CaptureRegion,
    CaptureRequest,
    CaptureSource,
    CaptureStopReason,
    CaptureSummary,
    EphemeralFrame,
    FrameMetadata,
    IndicatorState,
    PixelFormat,
    RetentionPolicy,
)
from .session import CaptureController

__all__ = [
    "CaptureControl",
    "CaptureController",
    "CaptureError",
    "CaptureFailureCode",
    "CaptureIndicator",
    "CapturePurpose",
    "CaptureRegion",
    "CaptureRequest",
    "CaptureSettingsStore",
    "CaptureSource",
    "CaptureStopReason",
    "CaptureSummary",
    "EphemeralFrame",
    "FrameConsumer",
    "FrameMetadata",
    "FrameSource",
    "IndicatorState",
    "PixelFormat",
    "RetentionPolicy",
]
