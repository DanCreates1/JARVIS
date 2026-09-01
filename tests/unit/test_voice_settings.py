from __future__ import annotations

from datetime import UTC, datetime

import pytest

from jarvis.voice.models import DeviceSelection, VoiceControl
from jarvis.voice.settings_store import VoiceSettingsError, VoiceSettingsFile


def test_voice_settings_default_disabled_and_persist_across_restart(tmp_path) -> None:
    path = tmp_path / "private" / "voice-settings.json"
    first = VoiceSettingsFile(path)
    assert first.load_control().enabled is False
    assert first.load_devices() == DeviceSelection()

    first.save_devices(DeviceSelection(input_device_id="audio-input"))
    first.save_control(VoiceControl(enabled=True, updated_at=datetime.now(UTC)))

    restarted = VoiceSettingsFile(path)
    assert restarted.load_devices().input_device_id == "audio-input"
    assert restarted.load_control().enabled is True
    assert not list(path.parent.glob(".voice-settings-*.tmp"))


def test_voice_settings_fail_closed_for_corrupt_or_oversized_file(tmp_path) -> None:
    path = tmp_path / "voice-settings.json"
    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(VoiceSettingsError, match="unreadable or invalid"):
        VoiceSettingsFile(path).load_control()
    path.write_bytes(b"x" * (65 * 1024))
    with pytest.raises(VoiceSettingsError, match="size limit"):
        VoiceSettingsFile(path).load_devices()
