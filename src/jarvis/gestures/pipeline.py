"""Bounded bridge from one ephemeral 7A frame to one optional 7B gesture event."""

from __future__ import annotations

from jarvis.vision.models import EphemeralFrame

from .contracts import GestureSink, HandLandmarkDetector
from .models import LandmarkError, LandmarkFailureCode
from .recognizer import TemporalGestureRecognizer


class GestureFrameProcessor:
    """Detect and recognize locally; only content-free gesture events reach the sink."""

    def __init__(
        self,
        *,
        detector: HandLandmarkDetector,
        recognizer: TemporalGestureRecognizer,
        sink: GestureSink,
    ) -> None:
        self.detector = detector
        self.recognizer = recognizer
        self.sink = sink

    async def __call__(self, frame: EphemeralFrame) -> None:
        landmarks = await self.detector.detect(frame)
        metadata = frame.metadata
        if (
            landmarks.session_id != metadata.session_id
            or landmarks.sequence != metadata.sequence
            or landmarks.captured_at != metadata.captured_at
            or landmarks.monotonic_ns != metadata.monotonic_ns
        ):
            self.recognizer.reset()
            raise LandmarkError(
                LandmarkFailureCode.MALFORMED_RESULT,
                "landmark result does not match its owning capture frame",
            )
        event = self.recognizer.consume(landmarks)
        if event is not None:
            await self.sink(event)

    async def close(self) -> None:
        self.recognizer.reset()
        await self.detector.close()
