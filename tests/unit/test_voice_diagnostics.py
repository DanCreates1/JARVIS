from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from jarvis.config import Settings
from jarvis.diagnostics import DiagnosticStatus
from jarvis.voice.diagnostics import run_voice_diagnostics
from jarvis.voice.models import (
    AudioDevice,
    AudioDeviceDirection,
    CaptureRequest,
    DeviceSelection,
    VoiceControl,
)
from jarvis.voice.settings_store import VoiceSettingsFile


class FakeAudio:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails

    async def list_devices(self) -> tuple[AudioDevice, ...]:
        if self.fails:
            raise RuntimeError("private driver detail")
        return (
            AudioDevice(
                id="input-id",
                name="Microphone",
                direction=AudioDeviceDirection.INPUT,
                host_api="WASAPI",
                backend_index=0,
                max_channels=2,
                default_sample_rate_hz=48_000,
                is_default=True,
            ),
            AudioDevice(
                id="output-id",
                name="Speakers",
                direction=AudioDeviceDirection.OUTPUT,
                host_api="WASAPI",
                backend_index=1,
                max_channels=2,
                default_sample_rate_hz=48_000,
                is_default=True,
            ),
        )

    async def check_input_settings(self, _request: CaptureRequest) -> None:
        if self.fails:
            raise RuntimeError("private format detail")


class FakeHealth:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.calls = 0

    async def health_check(self) -> None:
        self.calls += 1
        if self.fails:
            raise RuntimeError("private model detail")


@pytest.mark.asyncio
async def test_voice_diagnostics_pass_with_local_devices_models_and_defaults(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    store = VoiceSettingsFile(settings.voice_settings_path)
    store.save_control(VoiceControl(enabled=True, updated_at=datetime.now(UTC)))
    store.save_devices(DeviceSelection(input_device_id="input-id", output_device_id="output-id"))
    vad = FakeHealth()
    stt = FakeHealth()
    tts = FakeHealth()
    report = await run_voice_diagnostics(
        settings,
        audio=FakeAudio(),
        settings_store=store,
        vad=vad,
        stt=stt,
        tts=tts,
        wake=FakeHealth(),
    )
    assert report.ok
    assert all(check.status is DiagnosticStatus.PASS for check in report.checks)
    assert vad.calls == stt.calls == tts.calls == 1


@pytest.mark.asyncio
async def test_voice_diagnostics_fail_cleanly_for_devices_selection_and_provider(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    store = VoiceSettingsFile(settings.voice_settings_path)
    store.save_devices(DeviceSelection(input_device_id="missing", output_device_id="also-missing"))
    report = await run_voice_diagnostics(
        settings,
        audio=FakeAudio(fails=True),
        settings_store=store,
        vad=FakeHealth(fails=True),
        stt=FakeHealth(),
        tts=FakeHealth(),
        wake=FakeHealth(),
    )
    assert not report.ok
    failures = [check for check in report.checks if check.status is DiagnosticStatus.FAIL]
    assert {check.name for check in failures} >= {
        "audio endpoints",
        "selected input endpoint",
        "selected output endpoint",
        "Silero VAD",
    }
    assert "private" not in " ".join(check.detail for check in report.checks)


@pytest.mark.asyncio
async def test_voice_diagnostics_fail_closed_for_corrupt_settings(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    settings.voice_settings_path.write_text("bad", encoding="utf-8")
    report = await run_voice_diagnostics(
        settings,
        audio=FakeAudio(),
        settings_store=VoiceSettingsFile(settings.voice_settings_path),
        vad=FakeHealth(),
        stt=FakeHealth(),
        tts=FakeHealth(),
        wake=FakeHealth(),
    )
    assert any(check.name == "voice settings" for check in report.checks)
