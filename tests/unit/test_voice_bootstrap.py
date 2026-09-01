from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.config import Settings
from jarvis.voice.bootstrap import build_voice_runtime


class FakeCore:
    def __init__(self) -> None:
        self.service = object()
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1


@pytest.mark.asyncio
async def test_build_voice_runtime_composes_local_adapters_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core = FakeCore()

    async def fake_build(_settings: Settings) -> FakeCore:
        return core

    monkeypatch.setattr("jarvis.voice.bootstrap.build_runtime", fake_build)
    components = await build_voice_runtime(Settings(data_dir=tmp_path, _env_file=None))
    assert components.core is core
    assert components.controller.assistant is core.service
    assert components.controller.monitor_barge_in
    async with components as entered:
        assert entered is components
    assert core.closed == 1


@pytest.mark.asyncio
async def test_build_voice_runtime_closes_core_when_adapter_composition_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core = FakeCore()

    async def fake_build(_settings: Settings) -> FakeCore:
        return core

    class BrokenAudio:
        def __init__(self) -> None:
            raise RuntimeError("broken")

    monkeypatch.setattr("jarvis.voice.bootstrap.build_runtime", fake_build)
    monkeypatch.setattr("jarvis.voice.bootstrap.SoundDeviceAudio", BrokenAudio)
    with pytest.raises(RuntimeError, match="broken"):
        await build_voice_runtime(Settings(data_dir=tmp_path, _env_file=None))
    assert core.closed == 1
