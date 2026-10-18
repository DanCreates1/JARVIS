"""Opt-in real local STT evidence from synthetic SAPI audio; no microphone or host enablement."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from jarvis.config import Settings
from jarvis.voice.models import VoiceControl
from jarvis.voice.pwa import PWAVoiceService
from jarvis.voice.settings_store import VoiceSettingsFile
from jarvis.voice.signal import resample_mono_pcm_s16le
from jarvis.voice.speech import FasterWhisperSTTProvider, SapiTTSProvider

REFERENCE = "The quick brown fox jumps over the lazy dog."


async def main() -> None:
    host = Settings()
    root = await asyncio.to_thread(Path("runtime/mvp4-fixes/f13-voice").resolve)
    root.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dir=root, pwa_voice_enabled=True, _env_file=None)
    controls = VoiceSettingsFile(settings.voice_settings_path)
    controls.save_control(VoiceControl(enabled=True))  # Isolated fixture control, never host file.
    stt = FasterWhisperSTTProvider(
        model_name=host.voice_stt_model,
        model_dir=host.voice_model_dir,
        language=host.voice_stt_language,
        cpu_threads=host.voice_stt_cpu_threads,
        local_files_only=True,
    )
    service = PWAVoiceService(settings, stt=stt, controls=controls)
    started = time.perf_counter()
    await service.prepare()
    assert service.metadata()["available"], "Real local adapters/model unavailable"
    ready_ms = round((time.perf_counter() - started) * 1000, 2)
    chunks = [
        chunk
        async for chunk in SapiTTSProvider().synthesize(
            session_id="f13:synthetic", text=REFERENCE, cancel=asyncio.Event()
        )
    ]
    assert len(chunks) == 1
    chunk = chunks[0]
    pcm = resample_mono_pcm_s16le(
        chunk.pcm_s16le, source_rate_hz=chunk.sample_rate_hz, target_rate_hz=16000
    )

    async def valid() -> None:
        return None

    async def connected() -> bool:
        return False

    started = time.perf_counter()
    lease = service.reserve()
    try:
        result = await service.transcribe(pcm, lease=lease, validate=valid, disconnected=connected)
    finally:
        service.release_upload(lease)
        await service.close()
    normalized = " ".join(result.text.lower().replace(".", "").split())
    assert normalized == REFERENCE.lower().replace(".", ""), result.text
    evidence = {
        "pass": True,
        "fixture": "Windows SAPI synthetic speech; no microphone",
        "model": host.voice_stt_model,
        "device": "cpu",
        "compute_type": "int8",
        "local_files_only": True,
        "ready_ms": ready_ms,
        "transcription_ms": round((time.perf_counter() - started) * 1000, 2),
        "duration_ms": result.duration_ms,
        "pcm_bytes": len(pcm),
        "reference_match": True,
        "physical_acceptance": False,
    }
    (root / "acceptance.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence))


if __name__ == "__main__":
    asyncio.run(main())
