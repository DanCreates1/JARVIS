from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
import pytest

from jarvis.gestures.models import Handedness, LandmarkError, LandmarkFailureCode
from jarvis.gestures.opencv_detector import (
    OpenCVDNNHandLandmarkDetector,
    _box_iou,
    _generate_palm_anchors,
    _nms,
    _square_crop,
)
from jarvis.vision.models import (
    CapturePurpose,
    CaptureSource,
    EphemeralFrame,
    FrameMetadata,
    PixelFormat,
)


class FakeNet:
    def __init__(self, outputs):  # type: ignore[no-untyped-def]
        self.outputs = outputs
        self.inputs = []

    def getUnconnectedOutLayersNames(self):  # type: ignore[no-untyped-def]
        return tuple(f"output-{index}" for index in range(len(self.outputs)))

    def setInput(self, value):  # type: ignore[no-untyped-def]
        self.inputs.append(value)

    def forward(self, _names):  # type: ignore[no-untyped-def]
        return self.outputs


class FakeCV:
    INTER_AREA = 1
    INTER_LINEAR = 2
    BORDER_CONSTANT = 3

    def __init__(self, nets):  # type: ignore[no-untyped-def]
        self._nets = iter(nets)
        self.dnn = SimpleNamespace(readNet=lambda _path: next(self._nets))

    @staticmethod
    def resize(image, size, interpolation):  # type: ignore[no-untyped-def]
        del interpolation
        return np.resize(image, (size[1], size[0], 3))

    @staticmethod
    def getRotationMatrix2D(_center, _angle, _scale):  # type: ignore[no-untyped-def]
        return np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])

    @staticmethod
    def invertAffineTransform(matrix):  # type: ignore[no-untyped-def]
        return matrix

    @staticmethod
    def warpAffine(image, _matrix, size, flags):  # type: ignore[no-untyped-def]
        del flags
        return np.resize(image, (size[1], size[0], 3))

    @staticmethod
    def copyMakeBorder(image, top, bottom, left, right, _kind, value):  # type: ignore[no-untyped-def]
        del value
        return np.pad(image, ((top, bottom), (left, right), (0, 0)))


def _frame(*, purpose: CapturePurpose = CapturePurpose.GESTURE_INPUT) -> EphemeralFrame:
    return EphemeralFrame(
        FrameMetadata(
            session_id="capture-detector",
            sequence=1,
            source=CaptureSource.CAMERA,
            source_id="camera:0",
            purpose=purpose,
            captured_at=datetime(2026, 9, 9, tzinfo=UTC),
            monotonic_ns=1,
            width=64,
            height=48,
            pixel_format=PixelFormat.RGB24,
            byte_count=64 * 48 * 3,
        ),
        bytearray([127] * (64 * 48 * 3)),
    )


def _outputs():  # type: ignore[no-untyped-def]
    palms = np.zeros((1, 2016, 18), dtype=np.float32)
    palms[0, 0, 2:4] = (50, 50)
    palms[0, 0, 4:] = np.array(
        [0, 15, -12, 0, 0, -15, 12, 0, 18, 8, -18, 8, 0, 22],
        dtype=np.float32,
    )
    logits = np.full((1, 2016, 1), -100, dtype=np.float32)
    logits[0, 0, 0] = 10
    landmarks = np.zeros((1, 63), dtype=np.float32)
    points = landmarks.reshape(21, 3)
    for index in range(21):
        points[index] = (70 + index * 2, 60 + index * 2, 0)
    return (palms, logits), (
        landmarks,
        np.array([[0.99]], dtype=np.float32),
        np.array([[0.9]], dtype=np.float32),
        np.zeros((1, 63), dtype=np.float32),
    )


def _detector(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    palm_outputs, hand_outputs = _outputs()
    fake_cv = FakeCV((FakeNet(palm_outputs), FakeNet(hand_outputs)))
    monkeypatch.setitem(sys.modules, "cv2", fake_cv)
    monkeypatch.setattr("jarvis.gestures.opencv_detector.verify_model", lambda *_args: True)
    return OpenCVDNNHandLandmarkDetector(tmp_path)


@pytest.mark.asyncio
async def test_detector_maps_local_model_output_to_owned_landmarks(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    detector = _detector(tmp_path, monkeypatch)
    result = await detector.detect(_frame())

    assert result.session_id == "capture-detector"
    assert len(result.hands) == 1
    assert result.hands[0].handedness is Handedness.RIGHT
    assert len(result.hands[0].landmarks) == 21
    assert result.hands[0].local_only is True
    await detector.close()
    with pytest.raises(LandmarkError) as caught:
        await detector.detect(_frame())
    assert caught.value.code is LandmarkFailureCode.CANCELLED


@pytest.mark.asyncio
async def test_detector_rejects_released_wrong_purpose_and_bad_models(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    detector = _detector(tmp_path, monkeypatch)
    released = _frame()
    released.release()
    with pytest.raises(LandmarkError) as caught:
        await detector.detect(released)
    assert caught.value.code is LandmarkFailureCode.MALFORMED_RESULT

    with pytest.raises(LandmarkError):
        await detector.detect(_frame(purpose=CapturePurpose.DIAGNOSTIC))
    with pytest.raises(TypeError):
        await detector.detect(object())  # type: ignore[arg-type]
    await detector.close()

    monkeypatch.setattr("jarvis.gestures.opencv_detector.verify_model", lambda *_args: False)
    with pytest.raises(LandmarkError) as missing:
        OpenCVDNNHandLandmarkDetector(tmp_path)
    assert missing.value.code is LandmarkFailureCode.MODEL_UNAVAILABLE


def test_detector_geometry_helpers_are_bounded() -> None:
    anchors = _generate_palm_anchors(np)
    assert anchors.shape == (2016, 2)
    assert np.all((anchors > 0) & (anchors < 1))
    assert _box_iou(np.array([0, 0, 2, 2]), np.array([1, 1, 3, 3])) == pytest.approx(1 / 7)
    candidates = [
        (0.9, np.array([0, 0, 2, 2]), None),
        (0.8, np.array([0, 0, 2, 2]), None),
        (0.7, np.array([3, 3, 4, 4]), None),
    ]
    assert [item[0] for item in _nms(candidates, 0.3, 2)] == [0.9, 0.7]
    crop, origin = _square_crop(
        np.ones((2, 2, 3), dtype=np.uint8),
        np.array([0.0, 0.0]),
        4,
        FakeCV(()),
        np,
    )
    assert crop.shape == (4, 4, 3)
    assert origin.tolist() == [-2.0, -2.0]
