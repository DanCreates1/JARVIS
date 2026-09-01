"""Composition root for the local-only Phase 2 voice vertical slice."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.bootstrap import RuntimeComponents, build_runtime
from jarvis.config import Settings

from .audio_io import SoundDeviceAudio
from .models import CaptureRequest
from .session import EventSink, VoiceSessionController
from .settings_store import VoiceSettingsFile
from .speech import FasterWhisperSTTProvider, SapiTTSProvider, SileroVADProvider


@dataclass(slots=True)
class VoiceRuntimeComponents:
    core: RuntimeComponents
    audio: SoundDeviceAudio
    settings_store: VoiceSettingsFile
    vad: SileroVADProvider
    stt: FasterWhisperSTTProvider
    tts: SapiTTSProvider
    controller: VoiceSessionController

    async def close(self) -> None:
        await self.audio.stop()
        await self.core.close()

    async def __aenter__(self) -> VoiceRuntimeComponents:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self.close()


async def build_voice_runtime(
    settings: Settings,
    *,
    event_sink: EventSink | None = None,
) -> VoiceRuntimeComponents:
    """Build local speech adapters without enabling continuous listening."""
    core = await build_runtime(settings)
    try:
        audio = SoundDeviceAudio()
        settings_store = VoiceSettingsFile(settings.voice_settings_path)
        vad = SileroVADProvider()
        stt = FasterWhisperSTTProvider(
            model_name=settings.voice_stt_model,
            model_dir=settings.voice_model_dir,
            language=settings.voice_stt_language,
            cpu_threads=settings.voice_stt_cpu_threads,
            local_files_only=True,
        )
        tts = SapiTTSProvider(timeout_seconds=settings.voice_tts_timeout_seconds)
        controller = VoiceSessionController(
            assistant=core.service,
            audio_input=audio,
            vad=vad,
            stt=stt,
            tts=tts,
            audio_output=audio,
            settings_store=settings_store,
            capture_request=CaptureRequest(
                sample_rate_hz=settings.voice_sample_rate_hz,
                frame_samples=settings.voice_frame_samples,
                max_duration_ms=settings.voice_max_capture_seconds * 1_000,
            ),
            stt_timeout_seconds=settings.voice_stt_timeout_seconds,
            assistant_timeout_seconds=settings.voice_assistant_timeout_seconds,
            event_sink=event_sink,
            monitor_barge_in=settings.voice_barge_in_enabled,
        )
    except BaseException:
        await core.close()
        raise
    return VoiceRuntimeComponents(
        core=core,
        audio=audio,
        settings_store=settings_store,
        vad=vad,
        stt=stt,
        tts=tts,
        controller=controller,
    )
