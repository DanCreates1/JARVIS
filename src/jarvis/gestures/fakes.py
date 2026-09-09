"""Camera-independent Phase 7B detector fake."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from jarvis.vision.models import EphemeralFrame

from .models import HandObservation, LandmarkError, LandmarkFailureCode, LandmarkFrame

FakeDetection = tuple[HandObservation, ...] | BaseException


class FakeHandLandmarkDetector:
    """Return scripted hand observations without reading or retaining frame pixels."""

    def __init__(self, script: Iterable[FakeDetection] = ()) -> None:
        self._script = deque(script)
        self.detect_calls: list[tuple[str, int]] = []
        self.closed = False

    async def detect(self, frame: EphemeralFrame) -> LandmarkFrame:
        if not isinstance(frame, EphemeralFrame):
            raise TypeError("fake detector requires an EphemeralFrame")
        if self.closed:
            raise LandmarkError(LandmarkFailureCode.MODEL_UNAVAILABLE, "detector is closed")
        if frame.released:
            raise LandmarkError(LandmarkFailureCode.MALFORMED_RESULT, "frame was already released")
        self.detect_calls.append((frame.metadata.session_id, frame.metadata.sequence))
        scripted = self._script.popleft() if self._script else ()
        if isinstance(scripted, BaseException):
            raise scripted
        return LandmarkFrame(
            session_id=frame.metadata.session_id,
            sequence=frame.metadata.sequence,
            captured_at=frame.metadata.captured_at,
            monotonic_ns=frame.metadata.monotonic_ns,
            hands=scripted,
        )

    async def close(self) -> None:
        self.closed = True
        self._script.clear()
