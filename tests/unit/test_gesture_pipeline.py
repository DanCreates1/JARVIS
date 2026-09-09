from __future__ import annotations

from datetime import timedelta

import pytest

from jarvis.gestures.fakes import FakeHandLandmarkDetector
from jarvis.gestures.models import GestureKind, LandmarkError, LandmarkFailureCode
from jarvis.gestures.pipeline import GestureFrameProcessor
from jarvis.gestures.recognizer import TemporalGestureRecognizer
from jarvis.vision.models import (
    CapturePurpose,
    CaptureSource,
    EphemeralFrame,
    FrameMetadata,
    PixelFormat,
)
from tests.unit.gesture_fixtures import BASE_TIME, gesture_profile, hand


def pixel_frame(sequence: int) -> EphemeralFrame:
    metadata = FrameMetadata(
        session_id="capture-session",
        sequence=sequence,
        source=CaptureSource.CAMERA,
        source_id="camera:0",
        purpose=CapturePurpose.GESTURE_INPUT,
        captured_at=BASE_TIME + timedelta(milliseconds=sequence * 100),
        monotonic_ns=sequence * 100_000_000,
        width=2,
        height=2,
        pixel_format=PixelFormat.RGB24,
        byte_count=12,
    )
    return EphemeralFrame(metadata, bytearray(range(12)))


@pytest.mark.asyncio
async def test_fake_detector_pipeline_emits_event_without_reading_or_owning_pixels() -> None:
    detector = FakeHandLandmarkDetector([(hand("open"),)] * 3)
    events = []

    async def sink(event: object) -> None:
        events.append(event)

    processor = GestureFrameProcessor(
        detector=detector,
        recognizer=TemporalGestureRecognizer(
            gesture_profile(),
            now=lambda: BASE_TIME + timedelta(seconds=1),
            id_factory=lambda: "pipeline1",
        ),
        sink=sink,  # type: ignore[arg-type]
    )
    frames = [pixel_frame(sequence) for sequence in range(1, 4)]
    original = [bytes(frame.pixels) for frame in frames]
    for frame in frames:
        await processor(frame)
    assert detector.detect_calls == [
        ("capture-session", 1),
        ("capture-session", 2),
        ("capture-session", 3),
    ]
    assert [event.gesture for event in events] == [GestureKind.OPEN_PALM]
    assert [bytes(frame.pixels) for frame in frames] == original
    await processor.close()
    assert detector.closed is True
    with pytest.raises(LandmarkError, match="closed"):
        await detector.detect(frames[0])


@pytest.mark.asyncio
async def test_fake_detector_rejects_released_frame_and_forwards_classified_failure() -> None:
    frame = pixel_frame(1)
    frame.release()
    detector = FakeHandLandmarkDetector()
    with pytest.raises(LandmarkError) as caught:
        await detector.detect(frame)
    assert caught.value.code is LandmarkFailureCode.MALFORMED_RESULT
    failure = LandmarkError(LandmarkFailureCode.DETECTION_TIMEOUT, "detector timed out")
    detector = FakeHandLandmarkDetector([failure])
    with pytest.raises(LandmarkError) as forwarded:
        await detector.detect(pixel_frame(2))
    assert forwarded.value is failure


@pytest.mark.asyncio
async def test_pipeline_rejects_mismatched_detector_result() -> None:
    class MismatchDetector(FakeHandLandmarkDetector):
        async def detect(self, frame: EphemeralFrame):  # type: ignore[no-untyped-def]
            result = await super().detect(frame)
            return result.model_copy(update={"session_id": "wrong-session"})

    detector = MismatchDetector([(hand("open"),)])

    async def sink(_event: object) -> None:
        raise AssertionError("sink must not run")

    processor = GestureFrameProcessor(
        detector=detector,
        recognizer=TemporalGestureRecognizer(gesture_profile()),
        sink=sink,  # type: ignore[arg-type]
    )
    with pytest.raises(LandmarkError) as caught:
        await processor(pixel_frame(1))
    assert caught.value.code is LandmarkFailureCode.MALFORMED_RESULT


@pytest.mark.asyncio
async def test_fake_detector_validates_input_type() -> None:
    detector = FakeHandLandmarkDetector()
    with pytest.raises(TypeError):
        await detector.detect(object())  # type: ignore[arg-type]
