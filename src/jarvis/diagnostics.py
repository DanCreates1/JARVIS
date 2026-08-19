"""Read-only and minimally mutating installation diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from jarvis.config import Settings
from jarvis.llm import OllamaChatProvider
from jarvis.memory import SQLiteConversationStore


class DiagnosticStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    name: str
    status: DiagnosticStatus
    detail: str
    remediation: str | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    checks: tuple[DiagnosticCheck, ...]

    @property
    def ok(self) -> bool:
        return all(check.status is DiagnosticStatus.PASS for check in self.checks)


class DiagnosticStore(Protocol):
    async def initialize(self) -> None: ...

    async def close(self) -> None: ...


class ModelDiagnostics(Protocol):
    @property
    def configured_model(self) -> str: ...

    @property
    def installed_models(self) -> tuple[str, ...]: ...

    @property
    def available(self) -> bool: ...


class DiagnosticProvider(Protocol):
    async def model_diagnostics(self) -> ModelDiagnostics: ...

    async def close(self) -> None: ...


StoreFactory = Callable[[Path], DiagnosticStore]
ProviderFactory = Callable[[Settings], DiagnosticProvider]


def _default_store_factory(path: Path) -> DiagnosticStore:
    return SQLiteConversationStore(path)


def _default_provider_factory(settings: Settings) -> DiagnosticProvider:
    return OllamaChatProvider(
        base_url=str(settings.ollama_base_url),
        model=settings.ollama_model,
        timeout_seconds=settings.request_timeout_seconds,
    )


async def run_diagnostics(
    settings: Settings,
    *,
    store_factory: StoreFactory = _default_store_factory,
    provider_factory: ProviderFactory = _default_provider_factory,
) -> DiagnosticReport:
    """Validate local runtime prerequisites without downloading models or changing settings."""
    checks = [
        DiagnosticCheck(
            name="configuration",
            status=DiagnosticStatus.PASS,
            detail="JARVIS settings are valid and the provider endpoint passed safety checks.",
        )
    ]

    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        probe = settings.data_dir / f".write-probe-{uuid4().hex}"
        try:
            probe.write_text("JARVIS write probe", encoding="utf-8")
        finally:
            probe.unlink(missing_ok=True)
        checks.append(
            DiagnosticCheck(
                name="data directory",
                status=DiagnosticStatus.PASS,
                detail=f"Runtime data directory is writable: {settings.data_dir}",
            )
        )
    except OSError:
        checks.append(
            DiagnosticCheck(
                name="data directory",
                status=DiagnosticStatus.FAIL,
                detail="Runtime data directory could not be created or written.",
                remediation="Set JARVIS_DATA_DIR to a private, writable per-user directory.",
            )
        )

    store: DiagnosticStore | None = None
    try:
        store = store_factory(settings.database_path)
        await store.initialize()
        checks.append(
            DiagnosticCheck(
                name="SQLite memory",
                status=DiagnosticStatus.PASS,
                detail="Conversation database opened and all migrations are applied.",
            )
        )
    except Exception:
        checks.append(
            DiagnosticCheck(
                name="SQLite memory",
                status=DiagnosticStatus.FAIL,
                detail="Conversation database initialization failed.",
                remediation="Check JARVIS_DATA_DIR permissions and available disk space.",
            )
        )
    finally:
        if store is not None:
            await store.close()

    provider: DiagnosticProvider | None = None
    try:
        provider = provider_factory(settings)
        model_info = await provider.model_diagnostics()
        checks.append(
            DiagnosticCheck(
                name="Ollama service",
                status=DiagnosticStatus.PASS,
                detail=f"Ollama is reachable at {settings.ollama_base_url}",
            )
        )
        if model_info.available:
            checks.append(
                DiagnosticCheck(
                    name="Ollama model",
                    status=DiagnosticStatus.PASS,
                    detail=f"Configured model is installed: {model_info.configured_model}",
                )
            )
        else:
            checks.append(
                DiagnosticCheck(
                    name="Ollama model",
                    status=DiagnosticStatus.FAIL,
                    detail=f"Configured model is not installed: {model_info.configured_model}",
                    remediation=f"Run: ollama pull {model_info.configured_model}",
                )
            )
    except Exception:
        checks.append(
            DiagnosticCheck(
                name="Ollama service",
                status=DiagnosticStatus.FAIL,
                detail=f"Ollama is not reachable at {settings.ollama_base_url}",
                remediation="Install or start Ollama, then run `uv run jarvis doctor` again.",
            )
        )
    finally:
        if provider is not None:
            await provider.close()

    return DiagnosticReport(checks=tuple(checks))
