from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from jarvis.gestures.calibration import CalibrationError, GestureCalibrator
from jarvis.gestures.features import extract_features
from jarvis.gestures.models import (
    CalibrationPose,
    GestureCalibrationProfile,
    GestureKind,
    GestureObservation,
    Handedness,
    HandObservation,
    LandmarkError,
    LandmarkFailureCode,
    LandmarkFrame,
    NormalizedLandmark,
)
from tests.unit.gesture_fixtures import BASE_TIME, hand


def test_landmark_models_are_strict_local_and_fixed_shape() -> None:
    observation = hand("open")
    assert len(observation.landmarks) == 21
    assert observation.local_only is True
    assert observation.retention == "ephemeral"
    assert set(GestureObservation.model_fields).isdisjoint(
        {"action", "action_id", "arguments", "approval", "permission_level", "tool"}
    )
    with pytest.raises(ValidationError):
        HandObservation(
            handedness=Handedness.LEFT,
            handedness_confidence=0.9,
            tracking_confidence=0.9,
            landmarks=observation.landmarks[:-1],
        )
    with pytest.raises(ValidationError):
        NormalizedLandmark(x=math.nan, y=0.5)
    with pytest.raises(ValidationError):
        NormalizedLandmark(x=-0.1, y=0.5)
    with pytest.raises(ValidationError):
        LandmarkFrame(
            session_id="session",
            sequence=1,
            captured_at=datetime(2026, 1, 1),  # noqa: DTZ001 - deliberately invalid input
            monotonic_ns=1,
        )


def test_gesture_event_requires_ordered_time_and_sequence() -> None:
    event = GestureObservation(
        event_id="gesture-12345678",
        session_id="session",
        gesture=GestureKind.OPEN_PALM,
        handedness=Handedness.RIGHT,
        confidence=0.95,
        started_at=BASE_TIME,
        detected_at=BASE_TIME + timedelta(milliseconds=200),
        start_sequence=1,
        end_sequence=3,
    )
    assert event.detected_at.tzinfo is UTC
    with pytest.raises(ValidationError):
        event.model_copy(update={"start_sequence": 4, "end_sequence": 3}).model_validate(
            event.model_copy(update={"start_sequence": 4, "end_sequence": 3}).model_dump()
        )
    with pytest.raises(ValidationError):
        GestureObservation(**(event.model_dump() | {"confidence": float("inf")}))


def test_profile_rejects_invalid_thresholds() -> None:
    with pytest.raises(ValidationError, match=r"greater than or equal to 1\.01"):
        GestureCalibrationProfile(finger_extension_ratio_threshold=0.9)
    with pytest.raises(ValidationError, match="roll window"):
        GestureCalibrationProfile(debounce_frames=5, roll_window_frames=5)


def test_feature_extraction_separates_fixture_poses_and_degenerate_geometry() -> None:
    opened = extract_features(hand("open"))
    closed = extract_features(hand("fist"))
    pinched = extract_features(hand("pinch"))
    assert min(opened.extension_ratios) > max(closed.extension_ratios)
    assert pinched.pinch_ratio < opened.pinch_ratio
    broken = hand("open").model_dump()
    points = list(broken["landmarks"])
    points[17] = points[5]
    broken["landmarks"] = points
    with pytest.raises(ValueError, match="palm width"):
        extract_features(HandObservation.model_validate(broken))


def test_feature_ratios_ignore_model_depth_scale() -> None:
    flat = hand("pinch")
    with_depth = flat.model_dump()
    for index, landmark in enumerate(with_depth["landmarks"]):
        landmark["z"] = float(index - 10) * 0.15

    flat_features = extract_features(flat)
    depth_features = extract_features(HandObservation.model_validate(with_depth))
    assert depth_features.pinch_ratio == pytest.approx(flat_features.pinch_ratio)
    assert depth_features.extension_ratios == pytest.approx(flat_features.extension_ratios)
    assert GestureCalibrationProfile().pinch_ratio_threshold == 0.70


def test_calibrator_derives_aggregate_thresholds_and_resets() -> None:
    calibrator = GestureCalibrator(minimum_samples_per_pose=3, maximum_samples_per_pose=4)
    for _ in range(3):
        calibrator.add(CalibrationPose.OPEN_PALM, hand("open"))
        calibrator.add(CalibrationPose.CLOSED_FIST, hand("fist"))
        calibrator.add(CalibrationPose.PINCH, hand("pinch"))
    profile = calibrator.finish(mirrored_input=False)
    assert profile.mirrored_input is False
    assert extract_features(hand("pinch")).pinch_ratio < profile.pinch_ratio_threshold
    assert extract_features(hand("open")).pinch_ratio > profile.pinch_ratio_threshold
    assert max(extract_features(hand("fist")).extension_ratios) < (
        profile.finger_extension_ratio_threshold
    )
    calibrator.add(CalibrationPose.OPEN_PALM, hand("open"))
    with pytest.raises(CalibrationError, match="capacity"):
        calibrator.add(CalibrationPose.OPEN_PALM, hand("open"))
    calibrator.reset()
    with pytest.raises(CalibrationError, match="insufficient"):
        calibrator.finish(mirrored_input=True)


def test_calibrator_rejects_unseparated_samples_and_bad_inputs() -> None:
    calibrator = GestureCalibrator(minimum_samples_per_pose=3)
    for pose in CalibrationPose:
        for _ in range(3):
            calibrator.add(pose, hand("open"))
    with pytest.raises(CalibrationError, match="pinch samples"):
        calibrator.finish(mirrored_input=True)
    with pytest.raises(ValueError, match="limits"):
        GestureCalibrator(minimum_samples_per_pose=2)
    with pytest.raises(TypeError):
        GestureCalibrator().add("open_palm", hand("open"))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        GestureCalibrator().add(CalibrationPose.OPEN_PALM, object())  # type: ignore[arg-type]


def test_landmark_error_is_content_free_and_classified() -> None:
    error = LandmarkError(LandmarkFailureCode.MODEL_INVALID, "local model invalid")
    assert error.code is LandmarkFailureCode.MODEL_INVALID
    assert str(error) == "local model invalid"
