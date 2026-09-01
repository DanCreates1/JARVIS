from __future__ import annotations

import asyncio
from array import array
from datetime import UTC, datetime
from pathlib import Path

import pytest

from jarvis.core.models import RuntimeErrorCode, RuntimeErrorDetail, RuntimeResult, RuntimeStatus
from jarvis.voice.audio_io import AudioDeviceError
from jarvis.voice.models import (
    AudioChunk,
    AudioClip,
    AudioFrame,
    AudioOutputEvent,
    AudioOutputKind,
    CaptureRequest,
    DeviceSelection,
    SpeechSegment,
    TranscriptEvent,
    TranscriptKind,
    VoiceControl,
    VoiceEventType,
    VoiceFailureCode,
    VoiceState,
)
from jarvis.voice.session import VoiceSessionController
from jarvis.voice.settings_store import VoiceSettingsFile
from jarvis.voice.speech import VoiceProviderError


def pcm(pattern: list[int], repeats: int = 1) -> bytes:
    return array("h", pattern * repeats).tobytes()


def clip() -> AudioClip:
    return AudioClip(
        session_id="captured",
        captured_at=datetime.now(UTC),
        sample_rate_hz=16_000,
        pcm_s16le=pcm([4_000, -4_000], 8_000),
    )


def transcript(session_id: str = "captured") -> TranscriptEvent:
    return TranscriptEvent(
        session_id=session_id,
        sequence=1,
        kind=TranscriptKind.FINAL,
        text="hello jarvis",
        start_ms=0,
        end_ms=1_000,
    )


class FakeInput:
    def __init__(self, *, failure: BaseException | None = None, stream_frames: int = 0) -> None:
        self.failure = failure
        self.stream_frames = stream_frames
        self.capture_requests: list[CaptureRequest] = []

    async def list_devices(self) -> tuple[object, ...]:
        return ()

    async def capture(
        self,
        *,
        session_id: str,
        request: CaptureRequest,
        stop: asyncio.Event,
    ) -> AudioClip:
        self.capture_requests.append(request)
        if self.failure:
            raise self.failure
        return clip().model_copy(update={"session_id": session_id})

    async def stream(
        self,
        *,
        session_id: str,
        request: CaptureRequest,
        stop: asyncio.Event,
    ):
        unrelated = pcm([5_000], 512)
        for sequence in range(1, self.stream_frames + 1):
            if stop.is_set():
                return
            yield AudioFrame(
                session_id=session_id,
                sequence=sequence,
                captured_at=datetime.now(UTC),
                monotonic_ns=sequence,
                sample_rate_hz=request.sample_rate_hz,
                pcm_s16le=unrelated,
            )
            await asyncio.sleep(0)


class BlockingInput(FakeInput):
    async def capture(
        self,
        *,
        session_id: str,
        request: CaptureRequest,
        stop: asyncio.Event,
    ) -> AudioClip:
        self.capture_requests.append(request)
        await stop.wait()
        return clip().model_copy(update={"session_id": session_id})


class FakeVAD:
    def __init__(self, *, segments: tuple[SpeechSegment, ...] | None = None) -> None:
        self.segments = (
            segments if segments is not None else (SpeechSegment(start_ms=0, end_ms=1000),)
        )
        self.resets = 0

    async def speech_segments(self, _clip: AudioClip) -> tuple[SpeechSegment, ...]:
        return self.segments

    async def is_speech(self, _frame: AudioFrame) -> bool:
        return True

    async def reset(self) -> None:
        self.resets += 1


class FakeSTT:
    def __init__(self, *, failure: BaseException | None = None, delay: float = 0) -> None:
        self.failure = failure
        self.delay = delay

    async def transcribe(
        self,
        source: AudioClip,
        *,
        speech_segments: object,
        cancel: asyncio.Event,
    ):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.failure:
            raise self.failure
        yield transcript(source.session_id)


class FakeTTS:
    def __init__(self, *, failure: BaseException | None = None) -> None:
        self.failure = failure

    async def synthesize(self, *, session_id: str, text: str, cancel: asyncio.Event):
        if self.failure:
            raise self.failure
        yield AudioChunk(
            session_id=session_id,
            sequence=1,
            sample_rate_hz=16_000,
            pcm_s16le=pcm([3_000, -3_000], 4_000),
            phrase=text,
        )


class FakeOutput:
    def __init__(self, *, failure: bool = False, block: bool = False) -> None:
        self.failure = failure
        self.block = block
        self.started = asyncio.Event()
        self.stopped = 0

    async def list_devices(self) -> tuple[object, ...]:
        return ()

    async def play(
        self,
        chunk: AudioChunk,
        *,
        device_id: str | None,
        cancel: asyncio.Event,
    ) -> tuple[AudioOutputEvent, ...]:
        self.started.set()
        if self.block:
            await cancel.wait()
        kind = (
            AudioOutputKind.FAILED
            if self.failure
            else AudioOutputKind.STOPPED
            if cancel.is_set()
            else AudioOutputKind.FINISHED
        )
        return (
            AudioOutputEvent(
                session_id=chunk.session_id,
                sequence=1,
                kind=kind,
                phrase=chunk.phrase,
            ),
        )

    async def stop(self) -> None:
        self.stopped += 1


class FakeAssistant:
    def __init__(self, result: RuntimeResult | None = None, *, delay: float = 0) -> None:
        self.result = result or RuntimeResult(
            status=RuntimeStatus.COMPLETED,
            reply="Hello from JARVIS.",
        )
        self.delay = delay
        self.requests: list[tuple[str, str | None, object]] = []

    async def respond(
        self,
        user_input: str,
        *,
        conversation_id: str | None = None,
        metadata: object = None,
    ) -> RuntimeResult:
        self.requests.append((user_input, conversation_id, metadata))
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.result


def enabled_store(tmp_path: Path) -> VoiceSettingsFile:
    store = VoiceSettingsFile(tmp_path / "voice-settings.json")
    store.save_control(VoiceControl(enabled=True, updated_at=datetime.now(UTC)))
    store.save_devices(DeviceSelection(input_device_id="mic", output_device_id="speaker"))
    return store


def controller(
    tmp_path: Path,
    *,
    assistant: FakeAssistant | None = None,
    audio_input: FakeInput | None = None,
    vad: FakeVAD | None = None,
    stt: FakeSTT | None = None,
    tts: FakeTTS | None = None,
    output: FakeOutput | None = None,
    enabled: bool = True,
    monitor_barge_in: bool = False,
    stt_timeout: float = 1,
    assistant_timeout: float = 1,
) -> tuple[VoiceSessionController, VoiceSettingsFile, FakeOutput]:
    store = enabled_store(tmp_path)
    if not enabled:
        store.save_control(VoiceControl(enabled=False, updated_at=datetime.now(UTC)))
    selected_output = output or FakeOutput()
    return (
        VoiceSessionController(
            assistant=assistant or FakeAssistant(),
            audio_input=audio_input or FakeInput(),
            vad=vad or FakeVAD(),
            stt=stt or FakeSTT(),
            tts=tts or FakeTTS(),
            audio_output=selected_output,
            settings_store=store,
            capture_request=CaptureRequest(max_duration_ms=1_000),
            monitor_barge_in=monitor_barge_in,
            stt_timeout_seconds=stt_timeout,
            assistant_timeout_seconds=assistant_timeout,
        ),
        store,
        selected_output,
    )


@pytest.mark.asyncio
async def test_push_to_talk_success_preserves_devices_and_local_metadata(tmp_path) -> None:
    assistant = FakeAssistant()
    audio_input = FakeInput()
    session, _store, _output = controller(tmp_path, assistant=assistant, audio_input=audio_input)
    result = await session.run_push_to_talk(stop_capture=asyncio.Event(), conversation_id="saved")
    assert result.final_state is VoiceState.IDLE
    assert result.transcript == "hello jarvis"
    assert result.assistant_result is not None
    assert session.state is VoiceState.IDLE
    assert audio_input.capture_requests[0].device_id == "mic"
    assert assistant.requests[0][0:2] == ("hello jarvis", "saved")
    assert assistant.requests[0][2] == {"interface": "voice", "audio_retained": False}
    event_types = [event.type for event in result.events]
    event_sequences = [event.sequence for event in result.events]
    assert event_sequences == list(range(1, len(event_sequences) + 1))
    assert VoiceEventType.AUDIO_CAPTURED in event_types
    assert VoiceEventType.TRANSCRIPT in event_types
    assert VoiceEventType.AUDIO_OUTPUT in event_types


@pytest.mark.asyncio
async def test_disabled_voice_fails_before_microphone_capture(tmp_path) -> None:
    audio_input = FakeInput()
    session, _store, _output = controller(tmp_path, audio_input=audio_input, enabled=False)
    result = await session.run_push_to_talk(stop_capture=asyncio.Event())
    assert result.failure is not None
    assert result.failure.code is VoiceFailureCode.DISABLED
    assert result.text_fallback
    assert audio_input.capture_requests == []
    assert session.state is VoiceState.IDLE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"vad": FakeVAD(segments=())}, VoiceFailureCode.NO_SPEECH),
        (
            {"audio_input": FakeInput(failure=AudioDeviceError("gone"))},
            VoiceFailureCode.DEVICE_UNAVAILABLE,
        ),
        (
            {"stt": FakeSTT(failure=VoiceProviderError("bad"))},
            VoiceFailureCode.STT_FAILED,
        ),
        (
            {"stt": FakeSTT(failure=ValueError("malformed adapter result"))},
            VoiceFailureCode.STT_FAILED,
        ),
        (
            {"tts": FakeTTS(failure=VoiceProviderError("bad"))},
            VoiceFailureCode.TTS_FAILED,
        ),
        ({"output": FakeOutput(failure=True)}, VoiceFailureCode.OUTPUT_FAILED),
    ],
)
async def test_voice_failures_degrade_to_text_and_recover(tmp_path, kwargs, expected) -> None:
    session, _store, _output = controller(tmp_path, **kwargs)
    result = await session.run_push_to_talk(stop_capture=asyncio.Event())
    assert result.failure is not None
    assert result.failure.code is expected
    assert result.text_fallback
    assert session.state is VoiceState.IDLE
    assert result.events[-1].type is VoiceEventType.TEXT_FALLBACK


@pytest.mark.asyncio
async def test_stt_and_assistant_timeouts_are_bounded(tmp_path) -> None:
    session, _store, _output = controller(tmp_path, stt=FakeSTT(delay=0.1), stt_timeout=0.01)
    result = await session.run_push_to_talk(stop_capture=asyncio.Event())
    assert result.failure is not None
    assert result.failure.code is VoiceFailureCode.STT_TIMEOUT

    session, _store, _output = controller(
        tmp_path, assistant=FakeAssistant(delay=0.1), assistant_timeout=0.01
    )
    result = await session.run_push_to_talk(stop_capture=asyncio.Event())
    assert result.failure is not None
    assert result.failure.code is VoiceFailureCode.ASSISTANT_FAILED


@pytest.mark.asyncio
async def test_failed_assistant_turn_keeps_transcript_for_text_retry(tmp_path) -> None:
    failed = RuntimeResult(
        status=RuntimeStatus.FAILED,
        error=RuntimeErrorDetail(code=RuntimeErrorCode.PROVIDER_ERROR, message="failed"),
    )
    session, _store, _output = controller(tmp_path, assistant=FakeAssistant(failed))
    result = await session.run_push_to_talk(stop_capture=asyncio.Event())
    assert result.transcript == "hello jarvis"
    assert result.failure is not None
    assert result.failure.code is VoiceFailureCode.ASSISTANT_FAILED


@pytest.mark.asyncio
async def test_explicit_barge_in_stops_output_and_preserves_completed_text_turn(tmp_path) -> None:
    output = FakeOutput(block=True)
    session, _store, _output = controller(tmp_path, output=output)
    turn = asyncio.create_task(session.run_push_to_talk(stop_capture=asyncio.Event()))
    await output.started.wait()
    await session.interrupt()
    result = await turn
    assert result.interrupted
    assert result.assistant_result is not None
    assert result.assistant_result.status is RuntimeStatus.COMPLETED
    assert output.stopped >= 1
    assert session.state is VoiceState.IDLE


@pytest.mark.asyncio
async def test_non_echo_speech_monitor_triggers_barge_in(tmp_path) -> None:
    output = FakeOutput(block=True)
    session, _store, _output = controller(
        tmp_path,
        audio_input=FakeInput(stream_frames=3),
        output=output,
        monitor_barge_in=True,
    )
    result = await session.run_push_to_talk(stop_capture=asyncio.Event())
    assert result.interrupted
    assert any(event.state is VoiceState.INTERRUPTED for event in result.events)


@pytest.mark.asyncio
async def test_external_kill_switch_cancels_active_capture(tmp_path) -> None:
    session, store, output = controller(tmp_path, audio_input=BlockingInput())
    turn = asyncio.create_task(session.run_push_to_talk(stop_capture=asyncio.Event()))
    await asyncio.sleep(0.02)
    store.save_control(VoiceControl(enabled=False, updated_at=datetime.now(UTC)))
    result = await asyncio.wait_for(turn, timeout=1)
    assert result.failure is not None
    assert result.failure.code is VoiceFailureCode.CANCELLED
    assert any(event.type is VoiceEventType.KILL_SWITCH for event in result.events)
    assert output.stopped >= 1
    assert session.state is VoiceState.IDLE


@pytest.mark.asyncio
async def test_concurrent_voice_turn_is_rejected_without_corrupting_first(tmp_path) -> None:
    blocking = BlockingInput()
    session, _store, _output = controller(tmp_path, audio_input=blocking)
    release = asyncio.Event()
    first = asyncio.create_task(session.run_push_to_talk(stop_capture=release))
    await asyncio.sleep(0)
    second = await session.run_push_to_talk(stop_capture=asyncio.Event())
    assert second.failure is not None
    assert second.failure.code is VoiceFailureCode.CAPTURE_FAILED
    release.set()
    assert (await first).failure is None


@pytest.mark.asyncio
async def test_disable_is_safe_before_any_session(tmp_path) -> None:
    session, store, _output = controller(tmp_path)
    await session.disable()
    assert store.load_control().enabled is False
    assert session.state is VoiceState.IDLE
