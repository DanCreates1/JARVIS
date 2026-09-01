"""Provider-neutral Phase 2 voice ports."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Protocol, runtime_checkable

from pydantic import JsonValue

from jarvis.core.models import RuntimeResult

from .models import (
    AudioChunk,
    AudioClip,
    AudioDevice,
    AudioFrame,
    AudioOutputEvent,
    CaptureRequest,
    DeviceSelection,
    HandsFreeIntent,
    SpeechSegment,
    TranscriptEvent,
    VoiceControl,
    WakeWordEvent,
)


@runtime_checkable
class AudioInput(Protocol):
    async def list_devices(self) -> Sequence[AudioDevice]: ...

    def stream(
        self,
        *,
        session_id: str,
        request: CaptureRequest,
        stop: asyncio.Event,
    ) -> AsyncIterator[AudioFrame]: ...

    async def capture(
        self,
        *,
        session_id: str,
        request: CaptureRequest,
        stop: asyncio.Event,
    ) -> AudioClip: ...


@runtime_checkable
class VADProvider(Protocol):
    async def speech_segments(self, clip: AudioClip) -> tuple[SpeechSegment, ...]: ...

    async def is_speech(self, frame: AudioFrame) -> bool: ...

    async def reset(self) -> None: ...


@runtime_checkable
class STTProvider(Protocol):
    def transcribe(
        self,
        clip: AudioClip,
        *,
        speech_segments: Sequence[SpeechSegment],
        cancel: asyncio.Event,
    ) -> AsyncIterator[TranscriptEvent]: ...


@runtime_checkable
class TTSProvider(Protocol):
    def synthesize(
        self,
        *,
        session_id: str,
        text: str,
        cancel: asyncio.Event,
    ) -> AsyncIterator[AudioChunk]: ...


@runtime_checkable
class AudioOutput(Protocol):
    async def list_devices(self) -> Sequence[AudioDevice]: ...

    async def play(
        self,
        chunk: AudioChunk,
        *,
        device_id: str | None,
        cancel: asyncio.Event,
    ) -> tuple[AudioOutputEvent, ...]: ...

    async def stop(self) -> None: ...


@runtime_checkable
class WakeWordProvider(Protocol):
    async def detect(self, frame: AudioFrame) -> WakeWordEvent | None: ...

    async def reset(self) -> None: ...


@runtime_checkable
class AcousticEventDetector(Protocol):
    def process(self, frame: AudioFrame) -> HandsFreeIntent | None: ...

    def reset(self) -> None: ...


@runtime_checkable
class AssistantResponder(Protocol):
    async def respond(
        self,
        user_input: str,
        *,
        conversation_id: str | None = None,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> RuntimeResult: ...


@runtime_checkable
class VoiceSettingsStore(Protocol):
    def load_devices(self) -> DeviceSelection: ...

    def save_devices(self, selection: DeviceSelection) -> None: ...

    def load_control(self) -> VoiceControl: ...

    def save_control(self, control: VoiceControl) -> None: ...
