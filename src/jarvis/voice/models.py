"""Strict values crossing Phase 2 voice boundaries."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, field_validator, model_validator

from jarvis.core.models import CoreModel, Identifier, RuntimeResult

MAX_AUDIO_BYTES = 24_000_000
MAX_CAPTURE_MILLISECONDS = 120_000


class AudioDeviceDirection(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


class AudioDevice(CoreModel):
    """Stable logical audio endpoint; ``backend_index`` is only a current observation."""

    id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=300)]
    direction: AudioDeviceDirection
    host_api: Annotated[str, Field(min_length=1, max_length=200)]
    backend_index: Annotated[int, Field(ge=0)]
    max_channels: Annotated[int, Field(ge=1, le=64)]
    default_sample_rate_hz: Annotated[int, Field(ge=8_000, le=384_000)]
    is_default: bool = False


class CaptureRequest(CoreModel):
    device_id: Identifier | None = None
    sample_rate_hz: Annotated[int, Field(ge=8_000, le=48_000)] = 16_000
    channels: Annotated[int, Field(ge=1, le=2)] = 1
    frame_samples: Annotated[int, Field(ge=80, le=4_800)] = 512
    max_duration_ms: Annotated[int, Field(ge=100, le=MAX_CAPTURE_MILLISECONDS)] = 30_000


class AudioFrame(CoreModel):
    session_id: Identifier
    sequence: Annotated[int, Field(ge=1)]
    captured_at: datetime
    monotonic_ns: Annotated[int, Field(ge=0)]
    sample_rate_hz: Annotated[int, Field(ge=8_000, le=48_000)]
    channels: Annotated[int, Field(ge=1, le=2)] = 1
    pcm_s16le: bytes
    overflowed: bool = False

    @field_validator("captured_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("audio timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_pcm_shape(self) -> Self:
        _validate_pcm(self.pcm_s16le, self.channels)
        return self


class AudioClip(CoreModel):
    session_id: Identifier
    captured_at: datetime
    sample_rate_hz: Annotated[int, Field(ge=8_000, le=48_000)]
    channels: Annotated[int, Field(ge=1, le=2)] = 1
    pcm_s16le: bytes
    dropped_frames: Annotated[int, Field(ge=0)] = 0

    @field_validator("captured_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("audio timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_pcm_shape_and_duration(self) -> Self:
        _validate_pcm(self.pcm_s16le, self.channels)
        if self.duration_ms > MAX_CAPTURE_MILLISECONDS:
            raise ValueError("audio clip exceeds maximum duration")
        return self

    @property
    def sample_count(self) -> int:
        return len(self.pcm_s16le) // (2 * self.channels)

    @property
    def duration_ms(self) -> int:
        return round(self.sample_count * 1_000 / self.sample_rate_hz)


class AudioChunk(CoreModel):
    session_id: Identifier
    sequence: Annotated[int, Field(ge=1)]
    sample_rate_hz: Annotated[int, Field(ge=8_000, le=48_000)]
    channels: Annotated[int, Field(ge=1, le=2)] = 1
    pcm_s16le: bytes
    phrase: Annotated[str, Field(min_length=1, max_length=4_000)]

    @model_validator(mode="after")
    def validate_pcm_shape(self) -> Self:
        _validate_pcm(self.pcm_s16le, self.channels)
        return self

    @property
    def sample_count(self) -> int:
        return len(self.pcm_s16le) // (2 * self.channels)


class SpeechSegment(CoreModel):
    start_ms: Annotated[int, Field(ge=0)]
    end_ms: Annotated[int, Field(gt=0, le=MAX_CAPTURE_MILLISECONDS)]
    confidence: Annotated[float, Field(ge=0, le=1)] | None = None

    @model_validator(mode="after")
    def require_ordered_segment(self) -> Self:
        if self.end_ms <= self.start_ms:
            raise ValueError("speech segment end must follow start")
        return self


class TranscriptKind(StrEnum):
    PARTIAL = "partial"
    FINAL = "final"


class TranscriptEvent(CoreModel):
    session_id: Identifier
    sequence: Annotated[int, Field(ge=1)]
    kind: TranscriptKind
    text: Annotated[str, Field(min_length=1, max_length=100_000)]
    start_ms: Annotated[int, Field(ge=0)]
    end_ms: Annotated[int, Field(ge=0, le=MAX_CAPTURE_MILLISECONDS)]
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    language: Annotated[str, Field(min_length=2, max_length=35)] | None = None
    confidence: Annotated[float, Field(ge=0, le=1)] | None = None

    @field_validator("emitted_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("transcript timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def require_ordered_timestamps(self) -> Self:
        if self.end_ms < self.start_ms:
            raise ValueError("transcript end must not precede start")
        return self


class AudioOutputKind(StrEnum):
    QUEUED = "queued"
    STARTED = "started"
    FINISHED = "finished"
    STOPPED = "stopped"
    FAILED = "failed"


class AudioOutputEvent(CoreModel):
    session_id: Identifier
    sequence: Annotated[int, Field(ge=1)]
    kind: AudioOutputKind
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    phrase: Annotated[str, Field(max_length=4_000)] = ""
    sample_count: Annotated[int, Field(ge=0)] = 0
    detail: Annotated[str, Field(max_length=1_000)] | None = None

    @field_validator("emitted_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("output timestamps must be timezone-aware")
        return value.astimezone(UTC)


class WakeWordEvent(CoreModel):
    session_id: Identifier
    wake_word: Annotated[str, Field(min_length=1, max_length=100)]
    confidence: Annotated[float, Field(ge=0, le=1)]
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AcousticEventType(StrEnum):
    DOUBLE_CLAP = "double_clap"


class HandsFreeIntentType(StrEnum):
    LAUNCH_APP_GROUP = "launch_app_group"


class HandsFreeIntent(CoreModel):
    session_id: Identifier
    source: AcousticEventType
    intent: HandsFreeIntentType
    confidence: Annotated[float, Field(ge=0, le=1)]
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_id: Identifier


class VoiceState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    ERROR = "error"
    DISABLED = "disabled"


class VoiceEventType(StrEnum):
    STATE_CHANGED = "state_changed"
    LISTENING_VISIBLE = "listening_visible"
    AUDIO_CAPTURED = "audio_captured"
    TRANSCRIPT = "transcript"
    AUDIO_OUTPUT = "audio_output"
    TEXT_FALLBACK = "text_fallback"
    KILL_SWITCH = "kill_switch"
    ERROR = "error"


class VoiceEvent(CoreModel):
    session_id: Identifier
    sequence: Annotated[int, Field(ge=1)]
    type: VoiceEventType
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    state: VoiceState | None = None
    detail: Annotated[str, Field(max_length=2_000)] | None = None
    transcript: TranscriptEvent | None = None
    audio_output: AudioOutputEvent | None = None


class VoiceFailureCode(StrEnum):
    DISABLED = "disabled"
    DEVICE_UNAVAILABLE = "device_unavailable"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    CAPTURE_FAILED = "capture_failed"
    NO_SPEECH = "no_speech"
    STT_FAILED = "stt_failed"
    STT_TIMEOUT = "stt_timeout"
    ASSISTANT_FAILED = "assistant_failed"
    TTS_FAILED = "tts_failed"
    OUTPUT_FAILED = "output_failed"
    CANCELLED = "cancelled"


class VoiceFailure(CoreModel):
    code: VoiceFailureCode
    message: Annotated[str, Field(min_length=1, max_length=2_000)]
    recoverable_with_text: bool = True


class VoiceTurnResult(CoreModel):
    session_id: Identifier
    final_state: VoiceState
    transcript: Annotated[str, Field(max_length=100_000)] | None = None
    assistant_result: RuntimeResult | None = None
    events: tuple[VoiceEvent, ...]
    failure: VoiceFailure | None = None
    text_fallback: bool = False
    interrupted: bool = False

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.final_state is VoiceState.ERROR and self.failure is None:
            raise ValueError("error voice result requires a failure")
        if self.final_state is not VoiceState.ERROR and self.failure is not None:
            raise ValueError("successful voice result cannot include a failure")
        return self


class DeviceSelection(CoreModel):
    input_device_id: Identifier | None = None
    output_device_id: Identifier | None = None


class VoiceControl(CoreModel):
    enabled: bool = False
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def _validate_pcm(data: bytes, channels: int) -> None:
    if not data:
        raise ValueError("PCM audio cannot be empty")
    if len(data) > MAX_AUDIO_BYTES:
        raise ValueError("PCM audio exceeds size limit")
    if len(data) % (2 * channels):
        raise ValueError("PCM audio must contain complete signed 16-bit samples")
