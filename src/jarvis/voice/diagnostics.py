"""Local voice dependency, device, privacy, and model diagnostics."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

from jarvis.config import Settings
from jarvis.diagnostics import DiagnosticCheck, DiagnosticReport, DiagnosticStatus

from .audio_io import SoundDeviceAudio
from .models import AudioDevice, AudioDeviceDirection, CaptureRequest
from .settings_store import VoiceSettingsError, VoiceSettingsFile
from .speech import (
    FasterWhisperSTTProvider,
    OpenWakeWordProvider,
    SapiTTSProvider,
    SileroVADProvider,
)


async def run_voice_diagnostics(
    settings: Settings,
    *,
    audio: SoundDeviceAudio | None = None,
    settings_store: VoiceSettingsFile | None = None,
    vad: SileroVADProvider | None = None,
    stt: FasterWhisperSTTProvider | None = None,
    tts: SapiTTSProvider | None = None,
    wake: OpenWakeWordProvider | None = None,
) -> DiagnosticReport:
    """Validate explicit push-to-talk without enabling microphone capture."""
    audio = audio or SoundDeviceAudio()
    settings_store = settings_store or VoiceSettingsFile(settings.voice_settings_path)
    vad = vad or SileroVADProvider()
    stt = stt or FasterWhisperSTTProvider(
        model_name=settings.voice_stt_model,
        model_dir=settings.voice_model_dir,
        language=settings.voice_stt_language,
        cpu_threads=settings.voice_stt_cpu_threads,
        local_files_only=True,
    )
    tts = tts or SapiTTSProvider(timeout_seconds=settings.voice_tts_timeout_seconds)
    wake_path = settings.voice_wake_model_path or (
        settings.voice_wake_model_dir / "hey_jarvis_v0.1.onnx"
    )
    wake = wake or OpenWakeWordProvider(
        model_path=wake_path,
        wake_word=settings.voice_wake_word,
        threshold=settings.voice_wake_threshold,
    )
    checks = [
        DiagnosticCheck(
            name="voice privacy mode",
            status=DiagnosticStatus.PASS,
            detail=(
                "STT, VAD, and TTS adapters are local-only; always-listening wake/clap paths "
                "are hard-disabled in Phase 2 configuration."
            ),
        )
    ]
    try:
        control = settings_store.load_control()
        checks.append(
            DiagnosticCheck(
                name="voice software kill switch",
                status=DiagnosticStatus.PASS,
                detail=(
                    "Explicit push-to-talk is enabled."
                    if control.enabled
                    else "Microphone capture is disabled until `jarvis voice enable`."
                ),
            )
        )
        selection = settings_store.load_devices()
    except VoiceSettingsError:
        checks.append(
            DiagnosticCheck(
                name="voice settings",
                status=DiagnosticStatus.FAIL,
                detail="Voice settings are unreadable or invalid.",
                remediation=f"Move aside or repair: {settings.voice_settings_path}",
            )
        )
        selection = None

    devices: Sequence[AudioDevice] = ()
    try:
        devices = await audio.list_devices()
        inputs = [item for item in devices if item.direction is AudioDeviceDirection.INPUT]
        outputs = [item for item in devices if item.direction is AudioDeviceDirection.OUTPUT]
        if not inputs or not outputs:
            raise RuntimeError("capture or render endpoint missing")
        checks.append(
            DiagnosticCheck(
                name="audio endpoints",
                status=DiagnosticStatus.PASS,
                detail=f"Found {len(inputs)} capture and {len(outputs)} render endpoints.",
            )
        )
    except Exception:
        checks.append(
            DiagnosticCheck(
                name="audio endpoints",
                status=DiagnosticStatus.FAIL,
                detail="Audio endpoints could not be enumerated.",
                remediation="Install the voice extra and check Windows microphone permissions.",
            )
        )
    if selection is not None:
        _append_selection_check(
            checks, devices, selection.input_device_id, AudioDeviceDirection.INPUT
        )
        _append_selection_check(
            checks, devices, selection.output_device_id, AudioDeviceDirection.OUTPUT
        )
        try:
            await audio.check_input_settings(
                CaptureRequest(
                    device_id=selection.input_device_id,
                    sample_rate_hz=settings.voice_sample_rate_hz,
                    frame_samples=settings.voice_frame_samples,
                    max_duration_ms=settings.voice_max_capture_seconds * 1_000,
                )
            )
        except Exception:
            checks.append(
                DiagnosticCheck(
                    name="microphone format",
                    status=DiagnosticStatus.FAIL,
                    detail="Selected microphone cannot open the required local PCM format.",
                    remediation="Select another endpoint or repair its Windows audio driver.",
                )
            )
        else:
            checks.append(
                DiagnosticCheck(
                    name="microphone format",
                    status=DiagnosticStatus.PASS,
                    detail=(
                        f"Selected microphone accepts mono {settings.voice_sample_rate_hz} Hz "
                        "signed 16-bit PCM."
                    ),
                )
            )

    await _append_provider_check(
        checks,
        name="Silero VAD",
        health_check=vad.health_check,
        remediation="Install the voice extra with `uv sync --locked --extra voice`.",
    )
    await _append_provider_check(
        checks,
        name="faster-whisper STT",
        health_check=stt.health_check,
        remediation="Run `uv run jarvis voice setup` while online, then retry offline.",
    )
    await _append_provider_check(
        checks,
        name="Windows SAPI TTS",
        health_check=tts.health_check,
        remediation="Enable a Windows speech voice and verify Windows PowerShell/System.Speech.",
    )
    await _append_provider_check(
        checks,
        name="openWakeWord foundation",
        health_check=wake.health_check,
        remediation="Run `uv run jarvis voice setup`; continuous listening remains disabled.",
    )
    return DiagnosticReport(checks=tuple(checks))


async def download_stt_model(settings: Settings) -> Path:
    """Explicitly download public STT/wake candidates outside the repository."""
    provider = FasterWhisperSTTProvider(
        model_name=settings.voice_stt_model,
        model_dir=settings.voice_model_dir,
        language=settings.voice_stt_language,
        cpu_threads=settings.voice_stt_cpu_threads,
        local_files_only=False,
    )
    await provider.health_check()
    try:
        from openwakeword.utils import download_models
    except ImportError as exc:
        raise RuntimeError("openWakeWord is not installed") from exc
    await asyncio.to_thread(
        download_models,
        ["hey_jarvis"],
        str(settings.voice_wake_model_dir),
    )
    return settings.voice_model_dir


async def _append_provider_check(
    checks: list[DiagnosticCheck],
    *,
    name: str,
    health_check: Callable[[], Awaitable[None]],
    remediation: str,
) -> None:
    try:
        await health_check()
    except Exception:
        checks.append(
            DiagnosticCheck(
                name=name,
                status=DiagnosticStatus.FAIL,
                detail=f"{name} is unavailable or failed its local health check.",
                remediation=remediation,
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                name=name,
                status=DiagnosticStatus.PASS,
                detail=f"{name} local health check passed.",
            )
        )


def _append_selection_check(
    checks: list[DiagnosticCheck],
    devices: Sequence[AudioDevice],
    device_id: str | None,
    direction: AudioDeviceDirection,
) -> None:
    selected = next(
        (item for item in devices if item.id == device_id and item.direction is direction),
        None,
    )
    if device_id is None:
        checks.append(
            DiagnosticCheck(
                name=f"selected {direction.value} endpoint",
                status=DiagnosticStatus.PASS,
                detail=f"No endpoint pinned; current Windows default {direction.value} is used.",
            )
        )
    elif selected is None:
        checks.append(
            DiagnosticCheck(
                name=f"selected {direction.value} endpoint",
                status=DiagnosticStatus.FAIL,
                detail=f"Persisted {direction.value} endpoint is disconnected or missing.",
                remediation="Run `jarvis voice devices`, then select an available stable ID.",
            )
        )
    else:
        checks.append(
            DiagnosticCheck(
                name=f"selected {direction.value} endpoint",
                status=DiagnosticStatus.PASS,
                detail=f"Persisted endpoint is available: {selected.name}.",
            )
        )
