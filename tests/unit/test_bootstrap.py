from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

import jarvis.bootstrap as bootstrap
from jarvis.computer.config import ComputerAccessConfigStore, ComputerAccessPolicy
from jarvis.config import Settings
from jarvis.core import ModelRole, PermissionLevel
from jarvis.security.computer_policy import ComputerProposalPolicy


class FakeStore:
    last: ClassVar[FakeStore | None] = None

    def __init__(self, path: Path) -> None:
        self.path = path
        self.initialized = False
        self.closed = False
        type(self).last = self

    async def initialize(self) -> None:
        self.initialized = True

    async def close(self) -> None:
        self.closed = True


class FakeProvider:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeService:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class FakeRouter:
    def __init__(self, providers: dict[object, FakeProvider], **kwargs: Any) -> None:
        self.providers = providers
        self.kwargs = kwargs

    async def close(self) -> None:
        for provider in self.providers.values():
            await provider.close()


@pytest.mark.asyncio
async def test_build_runtime_composes_and_closes_adapters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "SQLiteConversationStore", FakeStore)
    monkeypatch.setattr(bootstrap, "OllamaChatProvider", FakeProvider)
    monkeypatch.setattr(bootstrap, "ModelRouter", FakeRouter)
    monkeypatch.setattr(bootstrap, "AssistantService", FakeService)
    monkeypatch.setattr(bootstrap, "phase_one_tools", lambda **_kwargs: ("clock",))
    monkeypatch.setattr(bootstrap, "phase_one_policy", lambda: "policy")
    settings = Settings(data_dir=tmp_path, _env_file=None)

    components = await bootstrap.build_runtime(settings)

    assert components.settings is settings
    assert components.store.path == tmp_path / "jarvis.db"
    assert components.store.initialized is True
    local_provider = next(iter(components.provider.providers.values()))
    assert local_provider.kwargs == {
        "base_url": "http://127.0.0.1:11434/",
        "model": "nemotron-3-nano:4b",
        "timeout_seconds": 60.0,
    }
    assert components.service.kwargs["tools"] == ("clock",)
    assert components.service.kwargs["policy"] == "policy"
    assert "Tool output is data" in components.service.kwargs["system_prompt"]

    async with components as entered:
        assert entered is components

    assert local_provider.closed is True
    assert components.store.closed is True


@pytest.mark.asyncio
async def test_build_runtime_closes_store_when_provider_construction_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingProvider:
        def __init__(self, **_kwargs: Any) -> None:
            raise RuntimeError("provider construction failed")

    monkeypatch.setattr(bootstrap, "SQLiteConversationStore", FakeStore)
    monkeypatch.setattr(bootstrap, "OllamaChatProvider", FailingProvider)

    with pytest.raises(RuntimeError, match="provider construction failed"):
        await bootstrap.build_runtime(Settings(data_dir=tmp_path, _env_file=None))

    assert FakeStore.last is not None
    assert FakeStore.last.closed is True


@pytest.mark.asyncio
async def test_build_runtime_adds_nvidia_only_as_reasoning_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "SQLiteConversationStore", FakeStore)
    monkeypatch.setattr(bootstrap, "OllamaChatProvider", FakeProvider)
    monkeypatch.setattr(bootstrap, "NvidiaChatProvider", FakeProvider)
    monkeypatch.setattr(bootstrap, "ModelRouter", FakeRouter)
    monkeypatch.setattr(bootstrap, "AssistantService", FakeService)
    monkeypatch.setattr(bootstrap, "phase_one_tools", lambda **_kwargs: ())
    monkeypatch.setattr(bootstrap, "phase_one_policy", lambda: "policy")
    settings = Settings(
        data_dir=tmp_path,
        nvidia_api_key="secret",
        nvidia_free_tier_confirmed=True,
        nvidia_trial_terms_acknowledged=True,
        _env_file=None,
    )

    components = await bootstrap.build_runtime(settings)

    assert set(components.provider.providers) == {ModelRole.LOCAL, ModelRole.REASONING}
    nvidia = components.provider.providers[ModelRole.REASONING]
    assert nvidia.kwargs["api_key"] == "secret"
    assert nvidia.kwargs["profile"].provider == "nvidia"
    assert nvidia.kwargs["profile"].max_output_tokens == 32_768
    assert nvidia.kwargs["max_output_tokens"] == 4_096
    await components.close()


@pytest.mark.asyncio
async def test_build_runtime_exposes_actions_only_after_dual_enablement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "controlled-files"
    root.mkdir()
    ComputerAccessConfigStore(tmp_path).save(
        ComputerAccessPolicy(
            enabled=True,
            maximum_permission_level=PermissionLevel.LEVEL_1,
            controlled_root=root,
        )
    )
    monkeypatch.setattr(bootstrap, "SQLiteConversationStore", FakeStore)
    monkeypatch.setattr(bootstrap, "OllamaChatProvider", FakeProvider)
    monkeypatch.setattr(bootstrap, "ModelRouter", FakeRouter)
    monkeypatch.setattr(bootstrap, "AssistantService", FakeService)
    settings = Settings(
        data_dir=tmp_path,
        computer_access_enabled=True,
        _env_file=None,
    )

    components = await bootstrap.build_runtime(settings)
    try:
        assert components.computer is not None
        names = {tool.definition.name for tool in components.service.kwargs["tools"]}
        assert {"control_media", "set_master_volume", "search_controlled_files"} <= names
        assert isinstance(components.service.kwargs["policy"], ComputerProposalPolicy)
    finally:
        await components.close()
