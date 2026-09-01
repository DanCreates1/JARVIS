from __future__ import annotations

import math
from array import array
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from jarvis.voice.models import (
    AudioChunk,
    AudioClip,
    AudioDeviceDirection,
    AudioFrame,
    SpeechSegment,
    TranscriptEvent,
    TranscriptKind,
    VoiceFailure,
    VoiceFailureCode,
    VoiceState,
    VoiceTurnResult,
)
from jarvis.voice.signal import (
    DoubleClapDetector,
    RenderReferenceSuppressor,
    phrase_chunks,
    resample_mono_pcm_s16le,
    signal_features,
    stable_device_id,
)


def pcm(values: list[int]) -> bytes:
    return array("h", values).tobytes()


def frame(values: list[int], *, sequence: int = 1, monotonic_ns: int = 1) -> AudioFrame:
    return AudioFrame(
        session_id="voice-test",
        sequence=sequence,
        captured_at=datetime.now(UTC),
        monotonic_ns=monotonic_ns,
        sample_rate_hz=16_000,
        pcm_s16le=pcm(values),
    )


def test_audio_clip_derives_duration_and_rejects_malformed_pcm() -> None:
    clip = AudioClip(
        session_id="voice-test",
        captured_at=datetime.now(UTC),
        sample_rate_hz=16_000,
        pcm_s16le=pcm([0] * 16_000),
    )
    assert clip.sample_count == 16_000
    assert clip.duration_ms == 1_000
    with pytest.raises(ValidationError, match="cannot be empty"):
        AudioClip(
            session_id="voice-test",
            captured_at=datetime.now(UTC),
            sample_rate_hz=16_000,
            pcm_s16le=b"",
        )
    with pytest.raises(ValidationError, match="complete signed 16-bit"):
        AudioClip(
            session_id="voice-test",
            captured_at=datetime.now(UTC),
            sample_rate_hz=16_000,
            pcm_s16le=b"odd",
        )


def test_audio_and_transcript_require_ordered_aware_timestamps() -> None:
    naive = datetime.now(UTC).replace(tzinfo=None)
    with pytest.raises(ValidationError, match="timezone-aware"):
        AudioFrame.model_validate({**frame([0] * 10).model_dump(), "captured_at": naive})
    with pytest.raises(ValidationError, match="end must follow"):
        SpeechSegment(start_ms=5, end_ms=5)
    with pytest.raises(ValidationError, match="must not precede"):
        TranscriptEvent(
            session_id="voice-test",
            sequence=1,
            kind=TranscriptKind.FINAL,
            text="hello",
            start_ms=10,
            end_ms=5,
        )


def test_voice_turn_result_requires_failure_only_for_error() -> None:
    with pytest.raises(ValidationError, match="requires a failure"):
        VoiceTurnResult(session_id="voice-test", final_state=VoiceState.ERROR, events=())
    with pytest.raises(ValidationError, match="cannot include a failure"):
        VoiceTurnResult(
            session_id="voice-test",
            final_state=VoiceState.IDLE,
            events=(),
            failure=VoiceFailure(code=VoiceFailureCode.NO_SPEECH, message="none"),
        )


def test_stable_device_id_is_deterministic_and_direction_specific() -> None:
    common = {
        "host_api": "Windows WASAPI",
        "name": "Microphone Array",
        "max_channels": 2,
        "default_sample_rate_hz": 48_000,
    }
    first = stable_device_id(direction=AudioDeviceDirection.INPUT, **common)
    assert first == stable_device_id(direction=AudioDeviceDirection.INPUT, **common)
    assert first != stable_device_id(direction=AudioDeviceDirection.OUTPUT, **common)


def test_phrase_chunks_normalize_and_bound_sentences() -> None:
    assert phrase_chunks("  One sentence.   Two? ") == ("One sentence.", "Two?")
    chunks = phrase_chunks("word " * 30, max_characters=25)
    assert chunks
    assert all(len(chunk) <= 25 for chunk in chunks)
    assert phrase_chunks("   ") == ()
    with pytest.raises(ValueError, match="at least 20"):
        phrase_chunks("hello", max_characters=10)


def test_signal_features_and_resampling_are_bounded() -> None:
    tone = [round(10_000 * math.sin(index / 4)) for index in range(512)]
    rms, peak, crossings = signal_features(pcm(tone))
    assert 0 < rms < peak < 1
    assert 0 < crossings < 1
    assert signal_features(b"") == (0.0, 0.0, 0.0)
    source = pcm([0, 10_000, 0, -10_000] * 4)
    downsampled = resample_mono_pcm_s16le(
        source,
        source_rate_hz=16_000,
        target_rate_hz=8_000,
    )
    assert len(downsampled) == len(source) // 2
    assert resample_mono_pcm_s16le(source, source_rate_hz=16_000, target_rate_hz=16_000) is source
    with pytest.raises(ValueError, match="positive"):
        resample_mono_pcm_s16le(source, source_rate_hz=0, target_rate_hz=16_000)


def test_double_clap_emits_one_typed_intent_and_honors_cooldown() -> None:
    detector = DoubleClapDetector()
    impulse = [26_000 if index % 2 else -26_000 for index in range(40)] + [0] * 472
    assert detector.process(frame(impulse, monotonic_ns=1_000_000_000)) is None
    intent = detector.process(frame(impulse, sequence=2, monotonic_ns=1_300_000_000))
    assert intent is not None
    assert intent.source.value == "double_clap"
    assert intent.intent.value == "launch_app_group"
    assert detector.process(frame(impulse, sequence=3, monotonic_ns=1_700_000_000)) is None
    detector.reset()
    quiet = [50 if index % 2 else -50 for index in range(512)]
    assert detector.process(frame(quiet, monotonic_ns=4_000_000_000)) is None
    with pytest.raises(ValueError):
        DoubleClapDetector(minimum_interval_ms=700, maximum_interval_ms=650)


def test_render_reference_suppresses_echo_but_not_unrelated_speech() -> None:
    rendered = pcm([12_000 if index % 4 < 2 else -12_000 for index in range(512)])
    chunk = AudioChunk(
        session_id="voice-test",
        sequence=1,
        sample_rate_hz=16_000,
        pcm_s16le=rendered,
        phrase="test",
    )
    suppressor = RenderReferenceSuppressor(correlation_threshold=0.8)
    suppressor.remember(chunk)
    assert suppressor.is_render_echo(frame(list(array("h", rendered))))
    unrelated = [8_000 if index % 7 < 3 else -3_000 for index in range(512)]
    assert not suppressor.is_render_echo(frame(unrelated))
    suppressor.clear()
    assert not suppressor.is_render_echo(frame(list(array("h", rendered))))
