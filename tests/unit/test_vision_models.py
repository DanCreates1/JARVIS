from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from jarvis.vision.models import (
    CapturePurpose,
    CaptureRegion,
    CaptureRequest,
    CaptureSource,
    EphemeralFrame,
    FrameMetadata,
)


def _request(**updates: object) -> CaptureRequest:
    values: dict[str, object] = {
        "source": CaptureSource.CAMERA,
        "source_id": "camera:0",
        "purpose": CapturePurpose.DIAGNOSTIC,
        "region": CaptureRegion(x=0, y=0, width=2, height=2),
    }
    values.update(updates)
    return CaptureRequest.model_validate(values)


def test_capture_request_is_explicit_local_ephemeral_and_bounded() -> None:
    request = _request()

    assert request.retention.value == "ephemeral"
    assert request.cloud_allowed is False
    assert request.biometric_processing is False
    with pytest.raises(ValidationError):
        _request(retention="persisted")
    with pytest.raises(ValidationError):
        _request(cloud_allowed=True)
    with pytest.raises(ValidationError):
        _request(biometric_processing=True)
    with pytest.raises(ValidationError):
        _request(requested_fps=16)
    with pytest.raises(ValidationError):
        _request(max_frames=301)
    with pytest.raises(ValidationError):
        _request(max_duration_ms=30_001)
    with pytest.raises(ValidationError):
        _request(frame_timeout_ms=1_001)
    assert _request(camera_exposure=-4).camera_exposure == -4
    with pytest.raises(ValidationError):
        _request(camera_exposure=-14)


@pytest.mark.parametrize("source_id", ["0", "camera:-1", "camera:32", "camera:one"])
def test_camera_source_id_is_closed_and_bounded(source_id: str) -> None:
    with pytest.raises(ValidationError):
        _request(source_id=source_id)


def test_screen_requires_explicit_desktop_source_and_region() -> None:
    screen = _request(
        source=CaptureSource.SCREEN,
        source_id="screen:desktop",
        purpose=CapturePurpose.SCREEN_ANALYSIS,
        region=CaptureRegion(x=-100, y=0, width=100, height=100),
    )
    assert screen.region.x == -100
    with pytest.raises(ValidationError):
        _request(source=CaptureSource.SCREEN, source_id="screen:all")
    with pytest.raises(ValidationError):
        _request(
            source=CaptureSource.SCREEN,
            source_id="screen:desktop",
            camera_exposure=-4,
        )
    with pytest.raises(ValidationError):
        _request(region=CaptureRegion(x=-1, y=0, width=2, height=2))


def test_region_and_rgb_shape_limits_are_enforced() -> None:
    with pytest.raises(ValidationError):
        CaptureRegion(x=0, y=0, width=1_920, height=1_081)
    with pytest.raises(ValidationError):
        FrameMetadata(
            session_id="capture-1",
            sequence=1,
            source=CaptureSource.CAMERA,
            source_id="camera:0",
            purpose=CapturePurpose.DIAGNOSTIC,
            captured_at=datetime.now(UTC),
            monotonic_ns=1,
            width=2,
            height=2,
            byte_count=11,
        )


def test_ephemeral_frame_zeroes_owned_buffer_and_rejects_late_access() -> None:
    metadata = FrameMetadata(
        session_id="capture-1",
        sequence=1,
        source=CaptureSource.CAMERA,
        source_id="camera:0",
        purpose=CapturePurpose.DIAGNOSTIC,
        captured_at=datetime.now(UTC),
        monotonic_ns=1,
        width=2,
        height=2,
        byte_count=12,
    )
    frame = EphemeralFrame(metadata, bytearray([9]) * 12)
    retained_view = frame.pixels

    frame.release()
    frame.release()

    assert frame.released
    assert bytes(retained_view) == bytes(12)
    with pytest.raises(RuntimeError, match="released"):
        _ = frame.pixels
