"""Deterministic temporal gesture recognizer with strict no-event uncertainty."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from uuid import uuid4

from .features import GestureFeatures, extract_features
from .models import (
    GestureCalibrationProfile,
    GestureKind,
    GestureObservation,
    HandObservation,
    LandmarkFrame,
)

Now = Callable[[], datetime]
IdFactory = Callable[[], str]


@dataclass(frozen=True, slots=True)
class _Candidate:
    kind: GestureKind
    confidence: float


@dataclass(frozen=True, slots=True)
class _RollPoint:
    sequence: int
    captured_at: datetime
    angle: float
    radius_ratio: float
    confidence: float


class TemporalGestureRecognizer:
    """Recognize one local hand only; it has no mapping, approval, or action dependency."""

    def __init__(
        self,
        profile: GestureCalibrationProfile | None = None,
        *,
        now: Now | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self.profile = profile or GestureCalibrationProfile()
        self._now = now or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self._roll: deque[_RollPoint] = deque(maxlen=self.profile.roll_window_frames)
        self.reset()

    def reset(self) -> None:
        self._session_id: str | None = None
        self._last_sequence: int | None = None
        self._last_monotonic_ns: int | None = None
        self._candidate: _Candidate | None = None
        self._candidate_count = 0
        self._candidate_start_sequence: int | None = None
        self._candidate_started_at: datetime | None = None
        self._candidate_confidence_total = 0.0
        self._armed = True
        self._release_count = 0
        self._cooldown_until_ns = 0
        self._roll.clear()

    def consume(self, frame: LandmarkFrame) -> GestureObservation | None:
        if not isinstance(frame, LandmarkFrame):
            raise TypeError("recognizer requires a LandmarkFrame")
        if self._session_id != frame.session_id:
            self.reset()
            self._session_id = frame.session_id
        if self._is_out_of_order(frame):
            self._clear_candidate_and_roll()
            return None
        gap_too_large = self._frame_gap_too_large(frame)
        self._last_sequence = frame.sequence
        self._last_monotonic_ns = frame.monotonic_ns
        if gap_too_large or not self._is_fresh(frame):
            self._clear_candidate_and_roll()
            return None
        if len(frame.hands) != 1:
            self._clear_candidate_and_roll()
            if not frame.hands:
                self._observe_release(frame.monotonic_ns)
            else:
                self._release_count = 0
            return None
        hand = frame.hands[0]
        if not self._hand_confident(hand):
            self._clear_candidate_and_roll()
            self._release_count = 0
            return None
        try:
            features = extract_features(hand)
        except ValueError:
            self._clear_candidate_and_roll()
            self._release_count = 0
            return None
        roll = self._observe_roll(frame, hand, features)
        if roll is not None:
            if not self._armed or frame.monotonic_ns < self._cooldown_until_ns:
                return None
            start = self._roll[0]
            return self._emit(
                frame=frame,
                hand=hand,
                kind=roll.kind,
                confidence=roll.confidence,
                start_sequence=start.sequence,
                started_at=start.captured_at,
            )
        static = self._classify_static(hand, features)
        if static is None:
            self._clear_static_candidate()
            self._observe_release(frame.monotonic_ns)
            return None
        self._release_count = 0
        if not self._armed or frame.monotonic_ns < self._cooldown_until_ns:
            self._clear_static_candidate()
            return None
        if self._candidate is None or self._candidate.kind is not static.kind:
            self._candidate = static
            self._candidate_count = 1
            self._candidate_start_sequence = frame.sequence
            self._candidate_started_at = frame.captured_at
            self._candidate_confidence_total = static.confidence
            return None
        self._candidate_count += 1
        self._candidate_confidence_total += static.confidence
        if self._candidate_count < self.profile.debounce_frames:
            return None
        assert self._candidate_start_sequence is not None
        assert self._candidate_started_at is not None
        confidence = self._candidate_confidence_total / self._candidate_count
        return self._emit(
            frame=frame,
            hand=hand,
            kind=static.kind,
            confidence=confidence,
            start_sequence=self._candidate_start_sequence,
            started_at=self._candidate_started_at,
        )

    def _is_out_of_order(self, frame: LandmarkFrame) -> bool:
        if self._last_sequence is None or self._last_monotonic_ns is None:
            return False
        return (
            frame.sequence <= self._last_sequence or frame.monotonic_ns <= self._last_monotonic_ns
        )

    def _frame_gap_too_large(self, frame: LandmarkFrame) -> bool:
        if self._last_monotonic_ns is None:
            return False
        gap_ns = frame.monotonic_ns - self._last_monotonic_ns
        return gap_ns > self.profile.max_frame_gap_ms * 1_000_000

    def _is_fresh(self, frame: LandmarkFrame) -> bool:
        now = self._now()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("recognizer clock must be timezone-aware")
        age_ms = (now.astimezone(UTC) - frame.captured_at).total_seconds() * 1_000
        return -50 <= age_ms <= self.profile.max_observation_age_ms

    def _hand_confident(self, hand: HandObservation) -> bool:
        return (
            hand.tracking_confidence >= self.profile.min_tracking_confidence
            and hand.handedness_confidence >= self.profile.min_handedness_confidence
        )

    def _classify_static(
        self,
        hand: HandObservation,
        features: GestureFeatures,
    ) -> _Candidate | None:
        extended = features.extended(self.profile)
        curled = features.curled(self.profile)
        base_confidence = min(hand.tracking_confidence, hand.handedness_confidence)
        if extended[0] and features.pinch_ratio <= self.profile.pinch_ratio_threshold:
            return _Candidate(GestureKind.PINCH, base_confidence)
        if all(extended) and features.pinch_ratio > self.profile.pinch_ratio_threshold:
            return _Candidate(GestureKind.OPEN_PALM, base_confidence)
        if all(curled):
            return _Candidate(GestureKind.CLOSED_FIST, base_confidence)
        return None

    def _observe_roll(
        self,
        frame: LandmarkFrame,
        hand: HandObservation,
        features: GestureFeatures,
    ) -> _Candidate | None:
        extended = features.extended(self.profile)
        curled = features.curled(self.profile)
        roll_pose = (
            extended[0]
            and all(curled[1:])
            and features.pinch_ratio > self.profile.pinch_ratio_threshold
            and 0.5 <= features.roll_radius_ratio <= 4
        )
        if not roll_pose:
            self._roll.clear()
            return None
        confidence = min(hand.tracking_confidence, hand.handedness_confidence)
        self._roll.append(
            _RollPoint(
                sequence=frame.sequence,
                captured_at=frame.captured_at,
                angle=features.roll_angle,
                radius_ratio=features.roll_radius_ratio,
                confidence=confidence,
            )
        )
        if len(self._roll) < max(4, self.profile.debounce_frames + 1):
            return None
        radii = [point.radius_ratio for point in self._roll]
        mean_radius = sum(radii) / len(radii)
        if (
            mean_radius <= 0
            or max(abs(radius - mean_radius) for radius in radii) > mean_radius * 0.45
        ):
            return None
        points = tuple(self._roll)
        deltas = [_normalized_angle(right.angle - left.angle) for left, right in pairwise(points)]
        if self.profile.mirrored_input:
            deltas = [-delta for delta in deltas]
        absolute_motion = sum(abs(delta) for delta in deltas)
        signed_motion = sum(deltas)
        if absolute_motion <= 1e-6:
            return None
        consistency = abs(signed_motion) / absolute_motion
        if (
            abs(signed_motion) < self.profile.roll_min_radians
            or consistency < self.profile.roll_direction_consistency
        ):
            return None
        kind = (
            GestureKind.FINGER_ROLL_CLOCKWISE
            if signed_motion > 0
            else GestureKind.FINGER_ROLL_COUNTERCLOCKWISE
        )
        return _Candidate(kind, sum(point.confidence for point in self._roll) / len(self._roll))

    def _emit(
        self,
        *,
        frame: LandmarkFrame,
        hand: HandObservation,
        kind: GestureKind,
        confidence: float,
        start_sequence: int,
        started_at: datetime,
    ) -> GestureObservation:
        token = self._id_factory()
        if (
            not isinstance(token, str)
            or not 8 <= len(token) <= 64
            or any(not (character.isascii() and character.isalnum()) for character in token)
        ):
            raise ValueError("gesture ID factory returned an invalid token")
        event = GestureObservation(
            event_id=f"gesture-{token}",
            session_id=frame.session_id,
            gesture=kind,
            handedness=hand.handedness,
            confidence=max(0.8, min(1.0, confidence)),
            started_at=started_at,
            detected_at=frame.captured_at,
            start_sequence=start_sequence,
            end_sequence=frame.sequence,
        )
        self._armed = False
        self._release_count = 0
        self._cooldown_until_ns = frame.monotonic_ns + self.profile.cooldown_ms * 1_000_000
        self._clear_candidate_and_roll()
        return event

    def _observe_release(self, monotonic_ns: int) -> None:
        self._release_count += 1
        if (
            self._release_count >= self.profile.release_frames
            and monotonic_ns >= self._cooldown_until_ns
        ):
            self._armed = True

    def _clear_static_candidate(self) -> None:
        self._candidate = None
        self._candidate_count = 0
        self._candidate_start_sequence = None
        self._candidate_started_at = None
        self._candidate_confidence_total = 0.0

    def _clear_candidate_and_roll(self) -> None:
        self._clear_static_candidate()
        self._roll.clear()


def _normalized_angle(value: float) -> float:
    return (value + math.pi) % (2 * math.pi) - math.pi
