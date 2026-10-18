"""Memory-only, local PWA transcription. No chat/tool/conversation authority."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime

from jarvis.config import Settings

from .contracts import STTProvider, VADProvider, VoiceSettingsStore
from .models import AudioClip, TranscriptKind
from .settings_store import VoiceSettingsFile
from .speech import FasterWhisperSTTProvider, SileroVADProvider

VOICE_PATH = "/api/v1/client/voice/transcriptions"
MAX_PCM_BYTES = 960_000
MIN_PCM_BYTES = 3_840
UPLOAD_SECONDS = 15


class PWAVoiceError(RuntimeError):
    def __init__(self, code: str, status: int = 503) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class Transcription:
    text: str
    duration_ms: int


class PWAVoiceService:
    def __init__(
        self,
        settings: Settings,
        *,
        stt: STTProvider | None = None,
        vad: VADProvider | None = None,
        controls: VoiceSettingsStore | None = None,
    ) -> None:
        self.settings = settings
        self.controls = controls or VoiceSettingsFile(settings.voice_settings_path)
        self.stt = stt or FasterWhisperSTTProvider(
            model_name=settings.voice_stt_model,
            model_dir=settings.voice_model_dir,
            language=settings.voice_stt_language,
            cpu_threads=settings.voice_stt_cpu_threads,
            local_files_only=True,
        )
        self.vad = vad or SileroVADProvider()
        self.ready = False
        self._busy = False
        self._lease: object | None = None
        self._closed = False
        self._worker: asyncio.Task[Transcription] | None = None
        self._cancel: asyncio.Event | None = None
        self._startup: asyncio.Task[None] | None = None
        self.max_bytes = min(MAX_PCM_BYTES, settings.voice_max_capture_seconds * 32_000)
        self.timeout = min(90, settings.voice_stt_timeout_seconds)

    def allowed(self) -> bool:
        try:
            return (
                not self._closed
                and self.settings.pwa_voice_enabled
                and self.controls.load_control().enabled
            )
        except Exception:
            return False

    def start(self) -> None:
        if self.settings.pwa_voice_enabled:
            self._startup = asyncio.create_task(self.prepare())

    async def prepare(self) -> None:
        """Local cache only. Failure never prevents text service startup."""
        try:
            for provider in (self.vad, self.stt):
                check = getattr(provider, "health_check", None)
                if check is not None:
                    await check()
            self.ready = True
        except Exception:
            self.ready = False

    def metadata(self) -> dict[str, object]:
        return {
            "available": self.allowed() and self.ready,
            "busy": self._busy,
            "max_duration_ms": self.max_bytes // 32,
            "min_duration_ms": 120,
            "format": "pcm_s16le_16000_mono",
            "local_only": True,
        }

    def reserve(self) -> object:
        if not self.allowed() or not self.ready:
            raise PWAVoiceError("voice_unavailable")
        if self._busy:
            raise PWAVoiceError("voice_busy", 409)
        self._busy = True
        self._lease = object()
        return self._lease

    def release_upload(self, lease: object) -> None:
        # Native worker owns capacity after handoff, including cancelled awaits.
        if self._worker is None and self._lease is lease:
            self._busy = False
            self._lease = None

    async def transcribe(
        self,
        pcm: bytes,
        *,
        lease: object,
        validate: Callable[[], Awaitable[None]],
        disconnected: Callable[[], Awaitable[bool]],
    ) -> Transcription:
        if not self._busy or self._lease is not lease or self._worker is not None:
            raise PWAVoiceError("voice_busy", 409)
        if not MIN_PCM_BYTES <= len(pcm) <= self.max_bytes or len(pcm) % 2:
            raise PWAVoiceError("invalid_pcm", 400)
        await validate()
        if not self.allowed():
            raise PWAVoiceError("voice_unavailable")
        clip = AudioClip(
            session_id="pwa:transcription",
            captured_at=datetime.now(UTC),
            sample_rate_hz=16_000,
            pcm_s16le=pcm,
        )
        cancel = asyncio.Event()
        self._cancel = cancel
        worker = asyncio.create_task(self._infer(clip, cancel))
        self._worker = worker
        worker.add_done_callback(self._finished)
        deadline = time.monotonic() + self.timeout
        try:
            while True:
                await validate()
                if not self.allowed():
                    raise PWAVoiceError("voice_unavailable")
                if await disconnected():
                    raise PWAVoiceError("voice_cancelled", 409)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PWAVoiceError("voice_timeout", 504)
                done, _ = await asyncio.wait({worker}, timeout=min(0.1, remaining))
                if done:
                    result = worker.result()
                    await validate()
                    if not self.allowed() or cancel.is_set():
                        raise PWAVoiceError("voice_unavailable")
                    return result
        finally:
            cancel.set()
            # Never task.cancel(): to_thread cancellation does not terminate native work.

    async def _infer(self, clip: AudioClip, cancel: asyncio.Event) -> Transcription:
        try:
            segments = await self.vad.speech_segments(clip)
            if cancel.is_set():
                raise PWAVoiceError("voice_cancelled", 409)
            if not segments:
                raise PWAVoiceError("no_speech", 422)
            text = ""
            async for event in self.stt.transcribe(clip, speech_segments=segments, cancel=cancel):
                if cancel.is_set():
                    raise PWAVoiceError("voice_cancelled", 409)
                if event.kind is TranscriptKind.FINAL:
                    text = event.text.strip()
            if not text or len(text) > 100_000:
                raise PWAVoiceError("invalid_transcript", 422)
            return Transcription(text, clip.duration_ms)
        except PWAVoiceError:
            raise
        except Exception:
            raise PWAVoiceError("local_transcription_failed") from None

    def _finished(self, task: asyncio.Task[Transcription]) -> None:
        with suppress(asyncio.CancelledError, Exception):
            task.exception()
        self._worker = None
        self._cancel = None
        self._busy = False

    async def close(self) -> None:
        self._closed = True
        if self._cancel is not None:
            self._cancel.set()
        # Drain actual workers before Core lifecycle ends; no new admissions.
        for task in (self._startup, self._worker):
            if task is not None:
                with suppress(Exception):
                    await asyncio.shield(task)
