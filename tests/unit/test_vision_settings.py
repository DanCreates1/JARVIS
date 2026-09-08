from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from jarvis.vision.models import CaptureControl
from jarvis.vision.settings_store import VisionSettingsError, VisionSettingsFile


def test_vision_settings_default_off_and_persist_only_control(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "vision-settings.json"
    store = VisionSettingsFile(path)

    assert not store.load_control().enabled
    store.save_control(CaptureControl(enabled=True, updated_at=datetime.now(UTC)))

    assert VisionSettingsFile(path).load_control().enabled
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) == {"version", "control"}
    assert "frame" not in path.read_text(encoding="utf-8").lower()


def test_vision_settings_corruption_and_oversize_fail_closed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "vision-settings.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(VisionSettingsError, match="unreadable"):
        VisionSettingsFile(path).load_control()

    path.write_bytes(b"x" * (16 * 1_024 + 1))
    with pytest.raises(VisionSettingsError, match="size"):
        VisionSettingsFile(path).load_control()


def test_vision_settings_reject_symlink_when_supported(tmp_path) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "target.json"
    target.write_text('{"version":1,"control":{"enabled":false}}', encoding="utf-8")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")

    with pytest.raises(VisionSettingsError, match="symbolic"):
        VisionSettingsFile(link).load_control()
