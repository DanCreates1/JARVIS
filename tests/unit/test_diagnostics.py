from dataclasses import dataclass
from pathlib import Path

import pytest

from jarvis.config import Settings
from jarvis.diagnostics import DiagnosticStatus, run_diagnostics


class FakeStore:
    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.initialized = False
        self.closed = False

    async def initialize(self) -> None:
        if self.fails:
            raise OSError("private database detail")
        self.initialized = True

    async def close(self) -> None:
        self.closed = True


@dataclass(frozen=True)
class FakeModelInfo:
    configured_model: str
    installed_models: tuple[str, ...]

    @property
    def available(self) -> bool:
        return self.configured_model in self.installed_models


class FakeProvider:
    def __init__(self, info: FakeModelInfo | BaseException) -> None:
        self.info = info
        self.closed = False

    async def model_diagnostics(self) -> FakeModelInfo:
        if isinstance(self.info, BaseException):
            raise self.info
        return self.info

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_diagnostics_pass_with_writable_store_and_installed_model(tmp_path: Path) -> None:
    store = FakeStore()
    provider = FakeProvider(FakeModelInfo("model:1", ("model:1",)))
    report = await run_diagnostics(
        Settings(data_dir=tmp_path, ollama_model="model:1", _env_file=None),
        store_factory=lambda _path: store,
        provider_factory=lambda _settings: provider,
    )

    assert report.ok is True
    assert all(check.status is DiagnosticStatus.PASS for check in report.checks)
    assert store.initialized and store.closed
    assert provider.closed


@pytest.mark.asyncio
async def test_diagnostics_fail_cleanly_for_store_and_provider(tmp_path: Path) -> None:
    store = FakeStore(fails=True)
    provider = FakeProvider(RuntimeError("private provider detail"))
    report = await run_diagnostics(
        Settings(data_dir=tmp_path, _env_file=None),
        store_factory=lambda _path: store,
        provider_factory=lambda _settings: provider,
    )

    assert report.ok is False
    failures = [check for check in report.checks if check.status is DiagnosticStatus.FAIL]
    assert {check.name for check in failures} == {"SQLite memory", "Ollama service"}
    assert "private" not in " ".join(check.detail for check in report.checks)
    assert store.closed and provider.closed


@pytest.mark.asyncio
async def test_diagnostics_report_missing_model_with_pull_command(tmp_path: Path) -> None:
    provider = FakeProvider(FakeModelInfo("missing:1", ("other:1",)))
    report = await run_diagnostics(
        Settings(data_dir=tmp_path, ollama_model="missing:1", _env_file=None),
        store_factory=lambda _path: FakeStore(),
        provider_factory=lambda _settings: provider,
    )

    model_check = next(check for check in report.checks if check.name == "Ollama model")
    assert model_check.status is DiagnosticStatus.FAIL
    assert model_check.remediation == "Run: ollama pull missing:1"
