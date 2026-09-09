from __future__ import annotations

from datetime import timedelta

import pytest

from jarvis.gestures.models import GestureKind, GestureObservation, Handedness
from jarvis.gestures.recognizer import TemporalGestureRecognizer
from tests.unit.gesture_fixtures import BASE_TIME, frame, gesture_profile, hand


@pytest.mark.parametrize(
    ("pose", "expected"),
    [
        ("fist", GestureKind.CLOSED_FIST),
        ("open", GestureKind.OPEN_PALM),
        ("pinch", GestureKind.PINCH),
    ],
)
def test_static_gesture_requires_debounce_and_emits_closed_observation(
    pose: str,
    expected: GestureKind,
) -> None:
    recognizer = TemporalGestureRecognizer(
        gesture_profile(),
        now=lambda: BASE_TIME + timedelta(milliseconds=500),
        id_factory=lambda: "12345678",
    )
    assert recognizer.consume(frame(1, hand(pose))) is None
    assert recognizer.consume(frame(2, hand(pose))) is None
    event = recognizer.consume(frame(3, hand(pose)))
    assert event is not None
    assert event.gesture is expected
    assert event.start_sequence == 1
    assert event.end_sequence == 3
    assert event.handedness is Handedness.RIGHT
    assert event.event_id == "gesture-12345678"
    assert event.local_only is True
    assert recognizer.consume(frame(4, hand(pose))) is None


def test_hold_never_repeats_until_release_and_cooldown() -> None:
    clock = [BASE_TIME]
    recognizer = TemporalGestureRecognizer(
        gesture_profile(),
        now=lambda: clock[0],
        id_factory=lambda: "abcdefgh",
    )

    def consume(sequence: int, pose: str | None = None) -> GestureObservation | None:
        frame_hands = () if pose is None else (hand(pose),)
        current = frame(sequence, *frame_hands)
        clock[0] = current.captured_at + timedelta(milliseconds=10)
        return recognizer.consume(current)

    assert [consume(i, "open") for i in range(1, 4)][-1] is not None
    for sequence in range(4, 9):
        assert consume(sequence, "open") is None
    assert consume(9) is None
    assert consume(10) is None
    assert consume(11, "open") is None
    assert consume(12, "open") is None
    assert consume(13, "open") is not None


def test_uncertainty_conflict_stale_gap_and_order_emit_nothing() -> None:
    clock = BASE_TIME + timedelta(milliseconds=500)
    recognizer = TemporalGestureRecognizer(gesture_profile(), now=lambda: clock)
    assert recognizer.consume(frame(1, hand("open", confidence=0.7))) is None
    assert recognizer.consume(frame(2, hand("open"), hand("fist"))) is None
    assert recognizer.consume(frame(2, hand("open"))) is None
    assert recognizer.consume(frame(3, hand("open"), step_ms=400)) is None
    stale = frame(4, hand("open"), captured_at=BASE_TIME - timedelta(seconds=5))
    assert recognizer.consume(stale) is None
    future = frame(5, hand("open"), captured_at=clock + timedelta(milliseconds=100))
    assert recognizer.consume(future) is None
    assert recognizer.consume(frame(6, hand("ambiguous"))) is None
    assert recognizer.consume(frame(7)) is None


def test_new_session_and_reset_discard_temporal_history() -> None:
    recognizer = TemporalGestureRecognizer(
        gesture_profile(), now=lambda: BASE_TIME + timedelta(seconds=1)
    )
    assert recognizer.consume(frame(1, hand("fist"))) is None
    assert recognizer.consume(frame(2, hand("fist"))) is None
    assert recognizer.consume(frame(3, hand("fist"), session_id="new-session")) is None
    recognizer.reset()
    assert recognizer.consume(frame(4, hand("fist"), session_id="new-session")) is None


@pytest.mark.parametrize(
    ("mirrored", "expected"),
    [
        (False, GestureKind.FINGER_ROLL_CLOCKWISE),
        (True, GestureKind.FINGER_ROLL_COUNTERCLOCKWISE),
    ],
)
def test_temporal_roll_direction_respects_mirror_configuration(
    mirrored: bool,
    expected: GestureKind,
) -> None:
    recognizer = TemporalGestureRecognizer(
        gesture_profile(mirrored_input=mirrored),
        now=lambda: BASE_TIME + timedelta(milliseconds=700),
        id_factory=lambda: "roll1234",
    )
    event = None
    for sequence, angle in enumerate((0.0, 0.35, 0.7, 1.05, 1.4, 1.75), start=1):
        event = recognizer.consume(frame(sequence, hand("roll", angle=angle)))
        if event is not None:
            break
    assert event is not None
    assert event.gesture is expected
    assert event.start_sequence == 1


def test_inconsistent_roll_and_bad_clock_or_id_fail_closed() -> None:
    recognizer = TemporalGestureRecognizer(
        gesture_profile(), now=lambda: BASE_TIME + timedelta(milliseconds=900)
    )
    for sequence, angle in enumerate((0.0, 0.5, 0.1, 0.7, 0.2, 0.8), start=1):
        assert recognizer.consume(frame(sequence, hand("roll", angle=angle))) is None
    bad_clock = TemporalGestureRecognizer(
        gesture_profile(),
        now=lambda: BASE_TIME.replace(tzinfo=None),
    )
    with pytest.raises(ValueError, match="clock"):
        bad_clock.consume(frame(1, hand("open")))
    bad_id = TemporalGestureRecognizer(
        gesture_profile(),
        now=lambda: BASE_TIME + timedelta(seconds=1),
        id_factory=lambda: "bad!",
    )
    bad_id.consume(frame(1, hand("fist")))
    bad_id.consume(frame(2, hand("fist")))
    with pytest.raises(ValueError, match="ID factory"):
        bad_id.consume(frame(3, hand("fist")))


def test_recognizer_rejects_wrong_input_type() -> None:
    with pytest.raises(TypeError):
        TemporalGestureRecognizer().consume(object())  # type: ignore[arg-type]
