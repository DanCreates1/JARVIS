from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from jarvis.config import Settings
from jarvis.voice.models import (
    AudioClip,
    SpeechSegment,
    TranscriptEvent,
    TranscriptKind,
    VoiceControl,
)
from jarvis.voice.pwa import PWAVoiceError, PWAVoiceService
from jarvis.voice.settings_store import VoiceSettingsFile
from jarvis.voice.speech import EnergyVADProvider

PCM = b"\x00\x20" * 3200


class STT:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.finish = asyncio.Event()
        self.finish.set()
        self.cancel: asyncio.Event | None = None
        self.fail = False
        self.text = "Synthetic transcript"

    async def health_check(self) -> None:
        if self.fail:
            raise RuntimeError("private error must not escape")

    async def transcribe(
        self, clip: AudioClip, *, speech_segments: Sequence[SpeechSegment], cancel: asyncio.Event
    ) -> AsyncIterator[TranscriptEvent]:
        self.started.set()
        self.cancel = cancel
        await self.finish.wait()  # Deliberately ignore cancellation like native work.
        if self.fail:
            raise RuntimeError("private error must not escape")
        yield TranscriptEvent(
            session_id=clip.session_id,
            sequence=1,
            kind=TranscriptKind.FINAL,
            text=self.text,
            start_ms=0,
            end_ms=clip.duration_ms,
        )


def service(tmp_path: Path, **settings: object) -> tuple[PWAVoiceService, STT]:
    config = Settings(data_dir=tmp_path, pwa_voice_enabled=True, _env_file=None, **settings)
    controls = VoiceSettingsFile(config.voice_settings_path)
    controls.save_control(VoiceControl(enabled=True))
    stt = STT()
    return PWAVoiceService(config, stt=stt, vad=EnergyVADProvider(), controls=controls), stt


async def valid() -> None:
    return None


async def connected() -> bool:
    return False


async def run(svc: PWAVoiceService, pcm: bytes = PCM, **kwargs: object) -> object:
    lease = svc.reserve()
    try:
        return await svc.transcribe(
            pcm,
            lease=lease,
            validate=kwargs.get("validate", valid),
            disconnected=kwargs.get("disconnected", connected),
        )
    finally:
        svc.release_upload(lease)


async def test_local_draft_has_no_persistence_and_limits(tmp_path: Path) -> None:
    svc, _ = service(tmp_path)
    await svc.prepare()
    result = await run(svc)
    assert result.text == "Synthetic transcript"
    assert result.duration_ms == 200
    assert svc.metadata()["local_only"] is True
    assert await asyncio.to_thread(lambda: list(tmp_path.iterdir())) == [
        svc.settings.voice_settings_path
    ]
    await svc.close()


@pytest.mark.parametrize(
    "pcm", [b"", b"x" * 3841, b"x" * 3838, b"x" * 960002], ids=["empty", "odd", "short", "long"]
)
async def test_pcm_shape_rejected_before_adapters(tmp_path: Path, pcm: bytes) -> None:
    svc, stt = service(tmp_path)
    await svc.prepare()
    with pytest.raises(PWAVoiceError, match="invalid_pcm"):
        await run(svc, pcm)
    assert not stt.started.is_set()
    assert svc.metadata()["busy"] is False


async def test_silence_and_adapter_error_are_safe(tmp_path: Path) -> None:
    svc, stt = service(tmp_path)
    await svc.prepare()
    with pytest.raises(PWAVoiceError, match="no_speech"):
        await run(svc, b"\0" * 6400)
    assert not stt.started.is_set()
    stt.fail = True
    with pytest.raises(PWAVoiceError, match="local_transcription_failed"):
        await run(svc)


async def test_readiness_defaults_missing_model_and_corrupt_kill_fail_closed(
    tmp_path: Path,
) -> None:
    assert not PWAVoiceService(Settings(data_dir=tmp_path, _env_file=None)).allowed()
    svc, stt = service(tmp_path)
    stt.fail = True
    await svc.prepare()
    assert not svc.metadata()["available"]
    with pytest.raises(PWAVoiceError, match="unavailable"):
        svc.reserve()
    stt.fail = False
    await svc.prepare()
    svc.settings.voice_settings_path.write_text("broken", encoding="utf-8")
    assert not svc.metadata()["available"]


@pytest.mark.parametrize("reason", ["timeout", "kill", "revoke", "disconnect", "cancel"])
async def test_native_slot_retained_until_worker_exits(tmp_path: Path, reason: str) -> None:
    svc, stt = service(tmp_path)
    await svc.prepare()
    stt.finish.clear()
    revoked = False
    disconnected = False

    async def validate() -> None:
        if revoked:
            raise RuntimeError("identity revoked")

    async def connection() -> bool:
        return disconnected

    if reason == "timeout":
        svc.timeout = 0.02
    task = asyncio.create_task(run(svc, validate=validate, disconnected=connection))
    await stt.started.wait()
    if reason == "kill":
        svc.controls.save_control(VoiceControl(enabled=False))
    elif reason == "revoke":
        revoked = True
    elif reason == "disconnect":
        disconnected = True
    elif reason == "cancel":
        task.cancel()
    with pytest.raises((PWAVoiceError, RuntimeError, asyncio.CancelledError)):
        await task
    assert stt.cancel is not None and stt.cancel.is_set()
    assert svc.metadata()["busy"] is True
    svc.controls.save_control(VoiceControl(enabled=True))
    with pytest.raises(PWAVoiceError, match="busy"):
        svc.reserve()
    stt.finish.set()
    for _ in range(10):
        await asyncio.sleep(0)
    assert svc.metadata()["busy"] is False
    assert (await run(svc)).text == "Synthetic transcript"
    await svc.close()


async def test_upload_lease_cannot_release_another_owner(tmp_path: Path) -> None:
    svc, _ = service(tmp_path)
    await svc.prepare()
    old = svc.reserve()
    svc.release_upload(old)
    new = svc.reserve()
    svc.release_upload(old)
    assert svc.metadata()["busy"] is True
    svc.release_upload(new)
    assert svc.metadata()["busy"] is False


async def test_lower_capture_limit_and_close_drain(tmp_path: Path) -> None:
    svc, stt = service(tmp_path, voice_max_capture_seconds=1)
    await svc.prepare()
    assert svc.max_bytes == 32000
    stt.finish.clear()
    task = asyncio.create_task(run(svc))
    await stt.started.wait()
    close = asyncio.create_task(svc.close())
    await asyncio.sleep(0)
    assert not close.done()
    stt.finish.set()
    with pytest.raises(PWAVoiceError):
        await task
    await close
