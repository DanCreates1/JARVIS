"""Privacy-minimal calibration that persists aggregate thresholds only."""

from __future__ import annotations

import statistics
from collections import defaultdict

from .features import extract_features
from .models import CalibrationPose, GestureCalibrationProfile, HandObservation


class CalibrationError(ValueError):
    pass


class GestureCalibrator:
    """Accumulate bounded scalar ratios; never retain pixels or landmark objects."""

    def __init__(self, *, minimum_samples_per_pose: int = 5, maximum_samples_per_pose: int = 100):
        if not 3 <= minimum_samples_per_pose <= maximum_samples_per_pose <= 500:
            raise ValueError("calibration sample limits are invalid")
        self.minimum_samples_per_pose = minimum_samples_per_pose
        self.maximum_samples_per_pose = maximum_samples_per_pose
        self._pinch: dict[CalibrationPose, list[float]] = defaultdict(list)
        self._extensions: dict[CalibrationPose, list[float]] = defaultdict(list)

    def add(self, pose: CalibrationPose, observation: HandObservation) -> None:
        if not isinstance(pose, CalibrationPose):
            raise TypeError("calibration pose must be a CalibrationPose")
        if not isinstance(observation, HandObservation):
            raise TypeError("calibration requires a hand observation")
        if len(self._pinch[pose]) >= self.maximum_samples_per_pose:
            raise CalibrationError("calibration sample capacity reached")
        features = extract_features(observation)
        self._pinch[pose].append(features.pinch_ratio)
        self._extensions[pose].extend(features.extension_ratios)

    def finish(self, *, mirrored_input: bool) -> GestureCalibrationProfile:
        for pose in CalibrationPose:
            if len(self._pinch[pose]) < self.minimum_samples_per_pose:
                raise CalibrationError(f"insufficient {pose.value} calibration samples")
        pinch_upper = _percentile(self._pinch[CalibrationPose.PINCH], 0.9)
        non_pinch_lower = min(
            _percentile(self._pinch[CalibrationPose.OPEN_PALM], 0.1),
            _percentile(self._pinch[CalibrationPose.CLOSED_FIST], 0.1),
        )
        if pinch_upper >= non_pinch_lower:
            raise CalibrationError("pinch samples do not separate from non-pinch samples")
        fist_upper = _percentile(self._extensions[CalibrationPose.CLOSED_FIST], 0.9)
        palm_lower = _percentile(self._extensions[CalibrationPose.OPEN_PALM], 0.1)
        if fist_upper >= palm_lower:
            raise CalibrationError("open-palm and closed-fist samples do not separate")
        midpoint = statistics.fmean
        return GestureCalibrationProfile(
            mirrored_input=mirrored_input,
            pinch_ratio_threshold=midpoint((pinch_upper, non_pinch_lower)),
            finger_curl_ratio_threshold=min(0.99, fist_upper + (palm_lower - fist_upper) * 0.35),
            finger_extension_ratio_threshold=max(
                1.01, fist_upper + (palm_lower - fist_upper) * 0.65
            ),
        )

    def reset(self) -> None:
        self._pinch.clear()
        self._extensions.clear()


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction
