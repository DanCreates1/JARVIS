"""Duplex Phase 2 session controller with cancellation and text degradation."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from uuid import uuid4

from jarvis.core.models import RuntimeResult, RuntimeStatus

from .audio_io import AudioDependencyError, AudioDeviceError
from .contracts import (
    AssistantResponder,
    AudioInput,
    AudioOutput,
    STTProvider,
    TTSProvider,
    VADProvider,
    VoiceSettingsStore,
)
from .models import (
    AudioChunk,
    AudioOutputEvent,
    AudioOutputKind,
    CaptureRequest,
    TranscriptEvent,
    TranscriptKind,
    VoiceControl,
    VoiceEvent,
    VoiceEventType,
    VoiceFailure,
    VoiceFailureCode,
    VoiceState,
    VoiceTurnResult,
)
from .settings_store import VoiceSettingsError
from .signal import RenderReferenceSuppressor, resample_mono_pcm_s16le
from .speech import VoiceDependencyError, VoiceOperationCancelled, VoiceProviderError

EventSink = Callable[[VoiceEvent], None]

_ALLOWED_TRANSITIONS: dict[VoiceState, frozenset[VoiceState]] = {
    VoiceState.IDLE: frozenset({VoiceState.LISTENING, VoiceState.DISABLED}),
    VoiceState.LISTENING: frozenset(
        {VoiceState.TRANSCRIBING, VoiceState.ERROR, VoiceState.INTERRUPTED}
    ),
    VoiceState.TRANSCRIBING: frozenset(
        {VoiceState.THINKING, VoiceState.ERROR, VoiceState.INTERRUPTED}
    ),
    VoiceState.THINKING: frozenset({VoiceState.SPEAKING, VoiceState.ERROR, VoiceState.INTERRUPTED}),
    VoiceState.SPEAKING: frozenset({VoiceState.IDLE, VoiceState.ERROR, VoiceState.INTERRUPTED}),
    VoiceState.INTERRUPTED: frozenset({VoiceState.IDLE, VoiceState.LISTENING}),
    VoiceState.ERROR: frozenset({VoiceState.IDLE}),
    VoiceState.DISABLED: frozenset({VoiceState.IDLE}),
}


class VoiceSessionController:
    """Own one voice turn at a time and recover deterministically after every failure."""

    def __init__(
        self,
        *,
        assistant: AssistantResponder,
        audio_input: AudioInput,
        vad: VADProvider,
        stt: STTProvider,
        tts: TTSProvider,
        audio_output: AudioOutput,
        settings_store: VoiceSettingsStore,
        capture_request: CaptureRequest,
        stt_timeout_seconds: float = 90,
        assistant_timeout_seconds: float = 120,
        event_sink: EventSink | None = None,
        monitor_barge_in: bool = True,
        barge_in_confirmation_frames: int = 2,
    ) -> None:
        if stt_timeout_seconds <= 0 or assistant_timeout_seconds <= 0:
            raise ValueError("voice operation timeouts must be positive")
        if barge_in_confirmation_frames < 1:
            raise ValueError("barge-in confirmation frames must be positive")
        self.assistant = assistant
        self.audio_input = audio_input
        self.vad = vad
        self.stt = stt
        self.tts = tts
        self.audio_output = audio_output
        self.settings_store = settings_store
        self.capture_request = capture_request
        self.stt_timeout_seconds = stt_timeout_seconds
        self.assistant_timeout_seconds = assistant_timeout_seconds
        self.event_sink = event_sink
        self.monitor_barge_in = monitor_barge_in
        self.barge_in_confirmation_frames = barge_in_confirmation_frames
        self.state = VoiceState.IDLE
        self._events: list[VoiceEvent] = []
        self._turn_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self._turn_cancel = asyncio.Event()
        self._output_cancel = asyncio.Event()
        self._session_id: str | None = None
        self._interrupted = False
        self._active_assistant_task: asyncio.Task[RuntimeResult] | None = None
        self._suppressor = RenderReferenceSuppressor(correlation_threshold=0.72)

    async def run_push_to_talk(
        self,
        *,
        stop_capture: asyncio.Event,
        conversation_id: str | None = None,
    ) -> VoiceTurnResult:
        if self._turn_lock.locked():
            return self._standalone_failure(
                VoiceFailureCode.CAPTURE_FAILED,
                "another voice turn is already active",
            )
        async with self._turn_lock:
            self._events = []
            self._turn_cancel.clear()
            self._output_cancel.clear()
            self._interrupted = False
            self._suppressor.clear()
            self._session_id = f"voice-{uuid4().hex}"
            try:
                control = self.settings_store.load_control()
            except VoiceSettingsError:
                return await self._fail(
                    VoiceFailureCode.DISABLED,
                    "voice controls are unreadable; text chat remains available",
                )
            if not control.enabled:
                await self._transition(VoiceState.DISABLED, "software microphone kill switch is on")
                result = self._error_result(
                    VoiceFailureCode.DISABLED,
                    "voice is disabled; run `jarvis voice enable` to allow explicit push-to-talk",
                )
                await self._transition(VoiceState.IDLE, "voice controller reset")
                return result

            kill_watch = asyncio.create_task(self._watch_kill_switch(stop_capture))
            try:
                selection = self.settings_store.load_devices()
                request = self.capture_request.model_copy(
                    update={"device_id": selection.input_device_id}
                )
                await self._transition(VoiceState.LISTENING, "push-to-talk capture started")
                self._add_event(
                    VoiceEventType.LISTENING_VISIBLE,
                    state=VoiceState.LISTENING,
                    detail="microphone active until push-to-talk release or duration limit",
                )
                clip = await self.audio_input.capture(
                    session_id=self._require_session_id(),
                    request=request,
                    stop=stop_capture,
                )
                if self._turn_cancel.is_set():
                    raise VoiceOperationCancelled("voice kill switch cancelled capture")
                self._add_event(
                    VoiceEventType.AUDIO_CAPTURED,
                    state=VoiceState.LISTENING,
                    detail=(
                        f"captured {clip.duration_ms} ms; dropped frames={clip.dropped_frames}; "
                        "raw audio not retained"
                    ),
                )
                await self._transition(VoiceState.TRANSCRIBING, "local speech recognition started")
                segments = await self.vad.speech_segments(clip)
                if not segments:
                    return await self._fail(
                        VoiceFailureCode.NO_SPEECH,
                        "no speech was detected; use push-to-talk again or type instead",
                    )
                transcript = ""
                try:
                    async with asyncio.timeout(self.stt_timeout_seconds):
                        async for transcript_event in self.stt.transcribe(
                            clip,
                            speech_segments=segments,
                            cancel=self._turn_cancel,
                        ):
                            self._add_event(
                                VoiceEventType.TRANSCRIPT,
                                state=VoiceState.TRANSCRIBING,
                                transcript=transcript_event,
                            )
                            if transcript_event.kind is TranscriptKind.FINAL:
                                transcript = transcript_event.text
                except TimeoutError:
                    return await self._fail(
                        VoiceFailureCode.STT_TIMEOUT,
                        "local speech recognition timed out; type instead",
                    )
                if not transcript:
                    return await self._fail(
                        VoiceFailureCode.STT_FAILED,
                        "local speech recognition returned no final transcript; type instead",
                    )
                await self._transition(VoiceState.THINKING, "assistant turn started")
                try:
                    async with asyncio.timeout(self.assistant_timeout_seconds):
                        self._active_assistant_task = asyncio.create_task(
                            self.assistant.respond(
                                transcript,
                                conversation_id=conversation_id,
                                metadata={"interface": "voice", "audio_retained": False},
                            )
                        )
                        assistant_result = await self._active_assistant_task
                except TimeoutError:
                    return await self._fail(
                        VoiceFailureCode.ASSISTANT_FAILED,
                        "assistant response timed out; transcript remains available for text retry",
                        transcript=transcript,
                    )
                finally:
                    self._active_assistant_task = None
                if (
                    assistant_result.status is not RuntimeStatus.COMPLETED
                    or not assistant_result.reply
                ):
                    return await self._fail(
                        VoiceFailureCode.ASSISTANT_FAILED,
                        "assistant response failed; transcript remains available for text retry",
                        transcript=transcript,
                        assistant_result=assistant_result,
                    )
                await self._transition(VoiceState.SPEAKING, "local speech output started")
                failure = await self._speak(
                    assistant_result.reply,
                    input_device_id=selection.input_device_id,
                    output_device_id=selection.output_device_id,
                )
                if failure is not None:
                    return await self._fail(
                        failure.code,
                        failure.message,
                        transcript=transcript,
                        assistant_result=assistant_result,
                    )
                if self.state is VoiceState.INTERRUPTED:
                    await self._transition(VoiceState.IDLE, "interrupted output recovered")
                elif self.state is VoiceState.SPEAKING:
                    await self._transition(VoiceState.IDLE, "voice turn completed")
                return VoiceTurnResult(
                    session_id=self._require_session_id(),
                    final_state=VoiceState.IDLE,
                    transcript=transcript,
                    assistant_result=assistant_result,
                    events=tuple(self._events),
                    interrupted=self._interrupted,
                )
            except VoiceOperationCancelled:
                return await self._fail(
                    VoiceFailureCode.CANCELLED,
                    "voice turn was cancelled; text chat remains available",
                )
            except (AudioDependencyError, VoiceDependencyError):
                return await self._fail(
                    VoiceFailureCode.DEPENDENCY_UNAVAILABLE,
                    "local voice dependency is unavailable; type instead and run voice doctor",
                )
            except AudioDeviceError:
                return await self._fail(
                    VoiceFailureCode.DEVICE_UNAVAILABLE,
                    "selected audio device is unavailable; type instead and select another device",
                )
            except VoiceSettingsError:
                return await self._fail(
                    VoiceFailureCode.DEVICE_UNAVAILABLE,
                    "voice device settings are invalid; type instead and repair voice settings",
                )
            except VoiceProviderError:
                return await self._fail(
                    VoiceFailureCode.STT_FAILED,
                    "local speech processing failed; type instead and run voice doctor",
                )
            except asyncio.CancelledError:
                killed_by_control = self._turn_cancel.is_set()
                self._turn_cancel.set()
                self._output_cancel.set()
                await self.audio_output.stop()
                if not killed_by_control:
                    raise
                return await self._fail(
                    VoiceFailureCode.CANCELLED,
                    "software microphone kill switch cancelled the voice turn",
                )
            except Exception:
                failure_code = {
                    VoiceState.LISTENING: VoiceFailureCode.CAPTURE_FAILED,
                    VoiceState.TRANSCRIBING: VoiceFailureCode.STT_FAILED,
                    VoiceState.THINKING: VoiceFailureCode.ASSISTANT_FAILED,
                    VoiceState.SPEAKING: VoiceFailureCode.TTS_FAILED,
                }.get(self.state, VoiceFailureCode.CAPTURE_FAILED)
                return await self._fail(
                    failure_code,
                    "voice pipeline rejected an unexpected adapter result; text remains available",
                )
            finally:
                kill_watch.cancel()
                with suppress(asyncio.CancelledError):
                    await kill_watch

    async def interrupt(self, *, detail: str = "barge-in detected") -> None:
        """Stop current/queued output promptly without changing the persisted text turn."""
        if self.state not in {VoiceState.SPEAKING, VoiceState.THINKING}:
            return
        self._interrupted = True
        self._output_cancel.set()
        if self.state is VoiceState.THINKING:
            self._turn_cancel.set()
        await self.audio_output.stop()
        await self._transition(VoiceState.INTERRUPTED, detail)

    async def disable(self) -> None:
        """Technically enforce the software kill switch and stop active capture/output."""
        self.settings_store.save_control(VoiceControl(enabled=False, updated_at=datetime.now(UTC)))
        self._turn_cancel.set()
        self._output_cancel.set()
        await self.audio_output.stop()
        if self._session_id is not None:
            self._add_event(
                VoiceEventType.KILL_SWITCH,
                state=self.state,
                detail="software microphone kill switch enforced",
            )
        if self.state not in {VoiceState.IDLE, VoiceState.DISABLED}:
            await self._transition(VoiceState.INTERRUPTED, "software kill switch")

    async def _watch_kill_switch(self, stop_capture: asyncio.Event) -> None:
        while True:
            await asyncio.sleep(0.1)
            try:
                enabled = self.settings_store.load_control().enabled
            except VoiceSettingsError:
                enabled = False
            if enabled:
                continue
            stop_capture.set()
            self._turn_cancel.set()
            self._output_cancel.set()
            task = self._active_assistant_task
            if task is not None:
                task.cancel()
            await self.audio_output.stop()
            self._add_event(
                VoiceEventType.KILL_SWITCH,
                state=self.state,
                detail="software microphone kill switch enforced during active turn",
            )
            return

    async def _speak(
        self,
        text: str,
        *,
        input_device_id: str | None,
        output_device_id: str | None,
    ) -> VoiceFailure | None:
        monitor_stop = asyncio.Event()
        monitor: asyncio.Task[None] | None = None
        if self.monitor_barge_in:
            monitor = asyncio.create_task(
                self._monitor_for_barge_in(input_device_id=input_device_id, stop=monitor_stop)
            )
        try:
            async for chunk in self.tts.synthesize(
                session_id=self._require_session_id(),
                text=text,
                cancel=self._output_cancel,
            ):
                if self._output_cancel.is_set():
                    break
                self._remember_render(chunk)
                queued = AudioOutputEvent(
                    session_id=chunk.session_id,
                    sequence=(chunk.sequence * 2) - 1,
                    kind=AudioOutputKind.QUEUED,
                    phrase=chunk.phrase,
                    sample_count=chunk.sample_count,
                )
                self._add_event(
                    VoiceEventType.AUDIO_OUTPUT,
                    state=VoiceState.SPEAKING,
                    audio_output=queued,
                )
                output_events = await self.audio_output.play(
                    chunk,
                    device_id=output_device_id,
                    cancel=self._output_cancel,
                )
                for output_event in output_events:
                    self._add_event(
                        VoiceEventType.AUDIO_OUTPUT,
                        state=self.state,
                        audio_output=output_event,
                    )
                    if output_event.kind is AudioOutputKind.FAILED:
                        return VoiceFailure(
                            code=VoiceFailureCode.OUTPUT_FAILED,
                            message="local audio output failed; response remains available as text",
                        )
                    if output_event.kind is AudioOutputKind.STOPPED:
                        self._interrupted = True
            return None
        except VoiceOperationCancelled:
            if self._interrupted:
                return None
            raise
        except VoiceProviderError:
            return VoiceFailure(
                code=VoiceFailureCode.TTS_FAILED,
                message="local speech synthesis failed; response remains available as text",
            )
        finally:
            monitor_stop.set()
            if monitor is not None:
                monitor.cancel()
                try:
                    await monitor
                except asyncio.CancelledError:
                    pass
                except (AudioDeviceError, AudioDependencyError, VoiceProviderError):
                    pass
            await self.vad.reset()

    async def _monitor_for_barge_in(
        self,
        *,
        input_device_id: str | None,
        stop: asyncio.Event,
    ) -> None:
        request = self.capture_request.model_copy(
            update={"device_id": input_device_id, "max_duration_ms": 120_000}
        )
        consecutive_speech = 0
        self._add_event(
            VoiceEventType.LISTENING_VISIBLE,
            state=VoiceState.SPEAKING,
            detail="barge-in microphone active during local playback",
        )
        async for frame in self.audio_input.stream(
            session_id=self._require_session_id(),
            request=request,
            stop=stop,
        ):
            if self._suppressor.is_render_echo(frame):
                consecutive_speech = 0
                continue
            if await self.vad.is_speech(frame):
                consecutive_speech += 1
            else:
                consecutive_speech = 0
            if consecutive_speech >= self.barge_in_confirmation_frames:
                await self.interrupt(detail="non-echo host speech interrupted output")
                stop.set()
                return

    def _remember_render(self, chunk: AudioChunk) -> None:
        reference = chunk
        if chunk.channels == 1 and chunk.sample_rate_hz != self.capture_request.sample_rate_hz:
            reference = chunk.model_copy(
                update={
                    "sample_rate_hz": self.capture_request.sample_rate_hz,
                    "pcm_s16le": resample_mono_pcm_s16le(
                        chunk.pcm_s16le,
                        source_rate_hz=chunk.sample_rate_hz,
                        target_rate_hz=self.capture_request.sample_rate_hz,
                    ),
                }
            )
        self._suppressor.remember(reference, frame_samples=self.capture_request.frame_samples)

    async def _transition(self, target: VoiceState, detail: str) -> None:
        async with self._state_lock:
            if target is self.state:
                return
            if target not in _ALLOWED_TRANSITIONS[self.state]:
                raise RuntimeError(f"invalid voice state transition: {self.state} -> {target}")
            self.state = target
            self._add_event(
                VoiceEventType.STATE_CHANGED,
                state=target,
                detail=detail,
            )

    async def _fail(
        self,
        code: VoiceFailureCode,
        message: str,
        *,
        transcript: str | None = None,
        assistant_result: RuntimeResult | None = None,
    ) -> VoiceTurnResult:
        if self.state not in {VoiceState.ERROR, VoiceState.IDLE, VoiceState.DISABLED}:
            await self._transition(VoiceState.ERROR, message)
        self._add_event(VoiceEventType.ERROR, state=VoiceState.ERROR, detail=message)
        self._add_event(
            VoiceEventType.TEXT_FALLBACK,
            state=VoiceState.ERROR,
            detail="terminal and browser text interfaces remain available",
        )
        result = VoiceTurnResult(
            session_id=self._require_session_id(),
            final_state=VoiceState.ERROR,
            transcript=transcript,
            assistant_result=assistant_result,
            events=tuple(self._events),
            failure=VoiceFailure(code=code, message=message),
            text_fallback=True,
            interrupted=self._interrupted,
        )
        if self.state is VoiceState.ERROR:
            await self._transition(VoiceState.IDLE, "voice controller recovered for text or retry")
        return result

    def _standalone_failure(self, code: VoiceFailureCode, message: str) -> VoiceTurnResult:
        session_id = f"voice-{uuid4().hex}"
        event = VoiceEvent(
            session_id=session_id,
            sequence=1,
            type=VoiceEventType.TEXT_FALLBACK,
            state=VoiceState.ERROR,
            detail=message,
        )
        return VoiceTurnResult(
            session_id=session_id,
            final_state=VoiceState.ERROR,
            events=(event,),
            failure=VoiceFailure(code=code, message=message),
            text_fallback=True,
        )

    def _error_result(self, code: VoiceFailureCode, message: str) -> VoiceTurnResult:
        self._add_event(VoiceEventType.TEXT_FALLBACK, state=VoiceState.DISABLED, detail=message)
        return VoiceTurnResult(
            session_id=self._require_session_id(),
            final_state=VoiceState.ERROR,
            events=tuple(self._events),
            failure=VoiceFailure(code=code, message=message),
            text_fallback=True,
        )

    def _add_event(
        self,
        event_type: VoiceEventType,
        *,
        state: VoiceState | None = None,
        detail: str | None = None,
        transcript: TranscriptEvent | None = None,
        audio_output: AudioOutputEvent | None = None,
    ) -> None:
        event = VoiceEvent(
            session_id=self._require_session_id(),
            sequence=len(self._events) + 1,
            type=event_type,
            state=state,
            detail=detail,
            transcript=transcript,
            audio_output=audio_output,
        )
        self._events.append(event)
        if self.event_sink is not None:
            with suppress(Exception):
                self.event_sink(event)

    def _require_session_id(self) -> str:
        if self._session_id is None:
            raise RuntimeError("voice session is not active")
        return self._session_id
