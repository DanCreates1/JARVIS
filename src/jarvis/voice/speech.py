"""Local CPU-first VAD, STT, TTS, and wake-word adapters."""

from __future__ import annotations

import asyncio
import base64
import importlib
import io
import math
import os
import wave
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from typing import Any

from .models import (
    AudioChunk,
    AudioClip,
    AudioFrame,
    SpeechSegment,
    TranscriptEvent,
    TranscriptKind,
    WakeWordEvent,
)
from .signal import phrase_chunks, signal_features


class VoiceProviderError(RuntimeError):
    """Local speech adapter failed without exposing raw speech."""


class VoiceDependencyError(VoiceProviderError):
    """Optional local speech dependency is not installed."""


class VoiceOperationCancelled(VoiceProviderError):
    """A bounded voice operation was cancelled."""


class EnergyVADProvider:
    """Dependency-free conservative fallback VAD for safe text degradation."""

    def __init__(self, *, rms_threshold: float = 0.015, minimum_speech_ms: int = 120) -> None:
        if not 0 < rms_threshold <= 1:
            raise ValueError("RMS threshold must be in (0, 1]")
        if minimum_speech_ms < 1:
            raise ValueError("minimum speech duration must be positive")
        self.rms_threshold = rms_threshold
        self.minimum_speech_ms = minimum_speech_ms

    async def speech_segments(self, clip: AudioClip) -> tuple[SpeechSegment, ...]:
        rms, _peak, _crossings = signal_features(clip.pcm_s16le)
        if rms < self.rms_threshold or clip.duration_ms < self.minimum_speech_ms:
            return ()
        return (SpeechSegment(start_ms=0, end_ms=clip.duration_ms),)

    async def is_speech(self, frame: AudioFrame) -> bool:
        rms, _peak, _crossings = signal_features(frame.pcm_s16le)
        return rms >= self.rms_threshold

    async def reset(self) -> None:
        return None


class SileroVADProvider:
    """Official Silero VAD package adapter, fixed to local CPU inference."""

    def __init__(
        self,
        *,
        threshold: float = 0.5,
        minimum_speech_ms: int = 180,
        minimum_silence_ms: int = 350,
        module_loader: Callable[[str], Any] = importlib.import_module,
    ) -> None:
        if not 0 < threshold < 1:
            raise ValueError("Silero threshold must be in (0, 1)")
        self.threshold = threshold
        self.minimum_speech_ms = minimum_speech_ms
        self.minimum_silence_ms = minimum_silence_ms
        self._module_loader = module_loader
        self._model: Any | None = None
        self._silero: Any | None = None
        self._numpy: Any | None = None
        self._torch: Any | None = None
        self._lock = asyncio.Lock()

    def _load(self) -> tuple[Any, Any, Any, Any]:
        if self._model is None:
            try:
                self._silero = self._module_loader("silero_vad")
                self._numpy = self._module_loader("numpy")
                self._torch = self._module_loader("torch")
                self._model = self._silero.load_silero_vad(onnx=False)
            except (ImportError, AttributeError) as exc:
                raise VoiceDependencyError(
                    "Silero VAD is unavailable; install the voice extra"
                ) from exc
        return self._model, self._silero, self._numpy, self._torch

    async def speech_segments(self, clip: AudioClip) -> tuple[SpeechSegment, ...]:
        if clip.sample_rate_hz not in {8_000, 16_000} or clip.channels != 1:
            raise VoiceProviderError("Silero VAD requires mono 8 kHz or 16 kHz PCM")
        async with self._lock:
            return await asyncio.to_thread(self._segments_sync, clip)

    def _segments_sync(self, clip: AudioClip) -> tuple[SpeechSegment, ...]:
        model, silero, numpy, torch = self._load()
        audio = numpy.frombuffer(clip.pcm_s16le, dtype=numpy.int16).astype(numpy.float32) / 32768.0
        tensor = torch.from_numpy(audio)
        raw_segments = silero.get_speech_timestamps(
            tensor,
            model,
            threshold=self.threshold,
            sampling_rate=clip.sample_rate_hz,
            min_speech_duration_ms=self.minimum_speech_ms,
            min_silence_duration_ms=self.minimum_silence_ms,
            return_seconds=False,
        )
        return tuple(
            SpeechSegment(
                start_ms=round(int(segment["start"]) * 1_000 / clip.sample_rate_hz),
                end_ms=round(int(segment["end"]) * 1_000 / clip.sample_rate_hz),
            )
            for segment in raw_segments
        )

    async def is_speech(self, frame: AudioFrame) -> bool:
        if frame.sample_rate_hz not in {8_000, 16_000} or frame.channels != 1:
            return False
        async with self._lock:
            return await asyncio.to_thread(self._is_speech_sync, frame)

    def _is_speech_sync(self, frame: AudioFrame) -> bool:
        model, _silero, numpy, torch = self._load()
        audio = numpy.frombuffer(frame.pcm_s16le, dtype=numpy.int16).astype(numpy.float32) / 32768.0
        if len(audio) not in {256, 512, 768, 1_024, 1_536}:
            return False
        probability = float(model(torch.from_numpy(audio), frame.sample_rate_hz).item())
        return probability >= self.threshold

    async def reset(self) -> None:
        async with self._lock:
            if self._model is not None:
                await asyncio.to_thread(self._model.reset_states)

    async def health_check(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._load)


class FasterWhisperSTTProvider:
    """Segment-bounded faster-whisper adapter using CPU int8 by default."""

    def __init__(
        self,
        *,
        model_name: str,
        model_dir: Path,
        language: str = "en",
        cpu_threads: int = 4,
        local_files_only: bool = True,
        model_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.model_name = model_name
        self.model_dir = model_dir
        self.language = language
        self.cpu_threads = cpu_threads
        self.local_files_only = local_files_only
        self._model_factory = model_factory
        self._model: Any | None = None
        self._numpy: Any | None = None
        self._lock = asyncio.Lock()

    def _load(self) -> tuple[Any, Any]:
        if self._model is None:
            try:
                numpy = importlib.import_module("numpy")
                factory = self._model_factory
                if factory is None:
                    faster_whisper = importlib.import_module("faster_whisper")
                    factory = faster_whisper.WhisperModel
                self.model_dir.mkdir(parents=True, exist_ok=True)
                model = factory(
                    self.model_name,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=self.cpu_threads,
                    num_workers=1,
                    download_root=str(self.model_dir),
                    local_files_only=self.local_files_only,
                )
            except (ImportError, AttributeError, OSError, RuntimeError) as exc:
                raise VoiceDependencyError(
                    "local faster-whisper model is unavailable; run voice setup"
                ) from exc
            self._numpy = numpy
            self._model = model
        return self._model, self._numpy

    def transcribe(
        self,
        clip: AudioClip,
        *,
        speech_segments: Sequence[SpeechSegment],
        cancel: asyncio.Event,
    ) -> AsyncIterator[TranscriptEvent]:
        return self._transcribe(clip, speech_segments=speech_segments, cancel=cancel)

    async def health_check(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._load)

    async def _transcribe(
        self,
        clip: AudioClip,
        *,
        speech_segments: Sequence[SpeechSegment],
        cancel: asyncio.Event,
    ) -> AsyncIterator[TranscriptEvent]:
        if clip.channels != 1:
            raise VoiceProviderError("faster-whisper adapter requires mono PCM")
        if not speech_segments:
            speech_segments = (SpeechSegment(start_ms=0, end_ms=clip.duration_ms),)
        collected: list[str] = []
        sequence = 0
        async with self._lock:
            for speech in speech_segments:
                if cancel.is_set():
                    raise VoiceOperationCancelled("speech transcription cancelled")
                normalized = await asyncio.to_thread(self._transcribe_segment, clip, speech)
                for text, start_ms, end_ms, language, confidence in normalized:
                    if cancel.is_set():
                        raise VoiceOperationCancelled("speech transcription cancelled")
                    if not text:
                        continue
                    collected.append(text)
                    sequence += 1
                    yield TranscriptEvent(
                        session_id=clip.session_id,
                        sequence=sequence,
                        kind=TranscriptKind.PARTIAL,
                        text=" ".join(collected),
                        start_ms=start_ms,
                        end_ms=end_ms,
                        language=language,
                        confidence=confidence,
                    )
        final_text = " ".join(collected).strip()
        if not final_text:
            raise VoiceProviderError("local STT returned no transcript")
        sequence += 1
        yield TranscriptEvent(
            session_id=clip.session_id,
            sequence=sequence,
            kind=TranscriptKind.FINAL,
            text=final_text,
            start_ms=speech_segments[0].start_ms,
            end_ms=speech_segments[-1].end_ms,
            language=self.language,
        )

    def _transcribe_segment(
        self,
        clip: AudioClip,
        speech: SpeechSegment,
    ) -> tuple[tuple[str, int, int, str | None, float | None], ...]:
        model, numpy = self._load()
        all_audio = numpy.frombuffer(clip.pcm_s16le, dtype=numpy.int16).astype(numpy.float32)
        all_audio /= 32768.0
        start = round(speech.start_ms * clip.sample_rate_hz / 1_000)
        end = round(speech.end_ms * clip.sample_rate_hz / 1_000)
        audio = all_audio[start:end]
        segments, info = model.transcribe(
            audio,
            language=self.language,
            beam_size=1,
            best_of=1,
            condition_on_previous_text=False,
            vad_filter=False,
            word_timestamps=False,
        )
        language = getattr(info, "language", self.language)
        language_probability = getattr(info, "language_probability", None)
        confidence = (
            float(language_probability) if isinstance(language_probability, int | float) else None
        )
        results = []
        for segment in segments:
            text = " ".join(str(segment.text).split())
            results.append(
                (
                    text,
                    speech.start_ms + round(float(segment.start) * 1_000),
                    speech.start_ms + round(float(segment.end) * 1_000),
                    str(language) if language else None,
                    confidence,
                )
            )
        return tuple(results)


_SAPI_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
$text = [Console]::In.ReadToEnd()
$memory = New-Object System.IO.MemoryStream
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $synth.SetOutputToWaveStream($memory)
  $synth.Speak($text)
  [Console]::Out.Write([Convert]::ToBase64String($memory.ToArray()))
} finally {
  $synth.Dispose()
  $memory.Dispose()
}
""".strip()
_SAPI_ENCODED = base64.b64encode(_SAPI_SCRIPT.encode("utf-16le")).decode("ascii")


class SapiTTSProvider:
    """Local Windows SAPI provider; text is stdin data, never shell source."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 30,
        max_output_bytes: int = 16_000_000,
        max_phrases: int = 64,
        max_total_duration_ms: int = 120_000,
    ) -> None:
        if (
            timeout_seconds <= 0
            or max_output_bytes < 1
            or max_phrases < 1
            or max_total_duration_ms < 1
        ):
            raise ValueError("TTS timeout, size, phrase, and duration limits must be positive")
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes
        self.max_phrases = max_phrases
        self.max_total_duration_ms = max_total_duration_ms

    def synthesize(
        self,
        *,
        session_id: str,
        text: str,
        cancel: asyncio.Event,
    ) -> AsyncIterator[AudioChunk]:
        return self._synthesize(session_id=session_id, text=text, cancel=cancel)

    async def health_check(self) -> None:
        cancel = asyncio.Event()
        chunks = [
            chunk
            async for chunk in self.synthesize(
                session_id="voice-diagnostic",
                text="ready",
                cancel=cancel,
            )
        ]
        if not chunks:
            raise VoiceProviderError("local TTS produced no diagnostic audio")

    async def _synthesize(
        self,
        *,
        session_id: str,
        text: str,
        cancel: asyncio.Event,
    ) -> AsyncIterator[AudioChunk]:
        if os.name != "nt":
            raise VoiceDependencyError("Windows SAPI TTS is available only on Windows")
        phrases = phrase_chunks(text)
        if len(phrases) > self.max_phrases:
            raise VoiceProviderError("local TTS response exceeds phrase limit")
        total_duration_ms = 0
        for sequence, phrase in enumerate(phrases, start=1):
            if cancel.is_set():
                raise VoiceOperationCancelled("speech synthesis cancelled")
            wav_data = await self._synthesize_phrase(phrase, cancel)
            chunk = self._decode_wav(session_id, sequence, phrase, wav_data)
            total_duration_ms += round(chunk.sample_count * 1_000 / chunk.sample_rate_hz)
            if total_duration_ms > self.max_total_duration_ms:
                raise VoiceProviderError("local TTS response exceeds duration limit")
            yield chunk

    async def _synthesize_phrase(self, phrase: str, cancel: asyncio.Event) -> bytes:
        try:
            process = await asyncio.create_subprocess_exec(
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-EncodedCommand",
                _SAPI_ENCODED,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise VoiceDependencyError("Windows PowerShell or SAPI is unavailable") from exc
        communicate = asyncio.create_task(process.communicate(phrase.encode("utf-8")))
        cancelled = asyncio.create_task(cancel.wait())
        try:
            async with asyncio.timeout(self.timeout_seconds):
                done, _pending = await asyncio.wait(
                    {communicate, cancelled}, return_when=asyncio.FIRST_COMPLETED
                )
                if cancelled in done and cancel.is_set():
                    process.terminate()
                    await process.wait()
                    communicate.cancel()
                    raise VoiceOperationCancelled("speech synthesis cancelled")
                stdout, _stderr = await communicate
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise VoiceProviderError("local TTS timed out") from exc
        finally:
            cancelled.cancel()
        if process.returncode != 0:
            raise VoiceProviderError("local TTS failed")
        if len(stdout) > math.ceil(self.max_output_bytes * 4 / 3) + 8:
            raise VoiceProviderError("local TTS response exceeds size limit")
        try:
            decoded = base64.b64decode(stdout, validate=True)
        except ValueError as exc:
            raise VoiceProviderError("local TTS returned malformed audio") from exc
        if len(decoded) > self.max_output_bytes:
            raise VoiceProviderError("local TTS audio exceeds size limit")
        return decoded

    @staticmethod
    def _decode_wav(
        session_id: str,
        sequence: int,
        phrase: str,
        wav_data: bytes,
    ) -> AudioChunk:
        try:
            with wave.open(io.BytesIO(wav_data), "rb") as stream:
                if stream.getsampwidth() != 2 or stream.getcomptype() != "NONE":
                    raise VoiceProviderError("local TTS returned unsupported WAV format")
                channels = stream.getnchannels()
                sample_rate_hz = stream.getframerate()
                pcm = stream.readframes(stream.getnframes())
        except (EOFError, wave.Error) as exc:
            raise VoiceProviderError("local TTS returned malformed WAV audio") from exc
        return AudioChunk(
            session_id=session_id,
            sequence=sequence,
            sample_rate_hz=sample_rate_hz,
            channels=channels,
            pcm_s16le=pcm,
            phrase=phrase,
        )


class OpenWakeWordProvider:
    """Optional ONNX openWakeWord adapter; no model is loaded unless configured explicitly."""

    def __init__(
        self,
        *,
        model_path: Path,
        wake_word: str = "hey_jarvis",
        threshold: float = 0.5,
        model_factory: Callable[..., Any] | None = None,
    ) -> None:
        if not 0 < threshold <= 1:
            raise ValueError("wake-word threshold must be in (0, 1]")
        self.model_path = model_path
        self.wake_word = wake_word
        self.threshold = threshold
        self._model_factory = model_factory
        self._model: Any | None = None
        self._numpy: Any | None = None
        self._lock = asyncio.Lock()

    def _load(self) -> tuple[Any, Any]:
        if self._model is None:
            if not self.model_path.is_file():
                raise VoiceDependencyError("configured wake-word model file is unavailable")
            try:
                numpy = importlib.import_module("numpy")
                factory = self._model_factory
                if factory is None:
                    module = importlib.import_module("openwakeword.model")
                    factory = module.Model
                model = factory(
                    wakeword_models=[str(self.model_path)],
                    inference_framework="onnx",
                    enable_speex_noise_suppression=False,
                    melspec_model_path=str(self.model_path.parent / "melspectrogram.onnx"),
                    embedding_model_path=str(self.model_path.parent / "embedding_model.onnx"),
                )
            except (ImportError, AttributeError, RuntimeError) as exc:
                raise VoiceDependencyError("openWakeWord is unavailable") from exc
            self._numpy = numpy
            self._model = model
        return self._model, self._numpy

    async def detect(self, frame: AudioFrame) -> WakeWordEvent | None:
        if frame.sample_rate_hz != 16_000 or frame.channels != 1:
            return None
        async with self._lock:
            scores = await asyncio.to_thread(self._predict, frame.pcm_s16le)
        matching_scores = (
            value
            for key, value in scores.items()
            if key == self.wake_word or key.startswith(f"{self.wake_word}_")
        )
        score = max(matching_scores, default=0.0)
        if score < self.threshold:
            return None
        return WakeWordEvent(
            session_id=frame.session_id,
            wake_word=self.wake_word,
            confidence=min(1.0, max(0.0, score)),
        )

    async def health_check(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._load)

    def _predict(self, pcm_s16le: bytes) -> dict[str, float]:
        model, numpy = self._load()
        audio = numpy.frombuffer(pcm_s16le, dtype=numpy.int16)
        raw = model.predict(audio)
        return {str(key): float(value) for key, value in raw.items()}

    async def reset(self) -> None:
        async with self._lock:
            if self._model is not None:
                reset = getattr(self._model, "reset", None)
                if callable(reset):
                    await asyncio.to_thread(reset)
