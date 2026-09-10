"""Read-only and minimally mutating installation diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from importlib.util import find_spec
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from jarvis.bootstrap import _fast_profile, _primary_profile, _reasoning_profile
from jarvis.computer.config import ComputerAccessConfigStore
from jarvis.computer.windows import ExecutableEnrollment
from jarvis.config import Settings
from jarvis.llm import (
    GeminiChatProvider,
    GroqChatProvider,
    ModelProvider,
    NvidiaChatProvider,
    OllamaChatProvider,
)
from jarvis.memory import SQLiteConversationStore
from jarvis.memory.identity import local_memory_host_id
from jarvis.remote import SQLiteRemoteIdentityStore
from jarvis.research import FetchedDocument, SandboxedDocumentParser


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
        model=settings.effective_local_model,
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

    checks.append(_research_parser_check(settings))

    checks.append(_computer_access_check(settings))

    checks.append(_bounded_task_check(settings))

    checks.append(_vision_capture_check(settings))

    checks.append(await _remote_identity_check(settings))

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

    cloud_providers: list[ModelProvider] = []
    if settings.cloud_policy == "privacy_aware" and settings.groq_api_key is not None:
        key = settings.groq_api_key.get_secret_value()
        cloud_providers.extend(
            (
                GroqChatProvider(
                    api_key=key,
                    profile=_fast_profile(settings),
                    base_url=str(settings.groq_base_url),
                    timeout_seconds=settings.request_timeout_seconds,
                    max_response_bytes=settings.max_provider_response_bytes,
                ),
                GroqChatProvider(
                    api_key=key,
                    profile=_primary_profile(settings),
                    base_url=str(settings.groq_base_url),
                    timeout_seconds=settings.request_timeout_seconds,
                    max_response_bytes=settings.max_provider_response_bytes,
                ),
            )
        )
    if (
        settings.cloud_policy == "privacy_aware"
        and settings.reasoning_provider == "gemini"
        and settings.gemini_api_key is not None
    ):
        cloud_providers.append(
            GeminiChatProvider(
                api_key=settings.gemini_api_key.get_secret_value(),
                profile=_reasoning_profile(settings),
                base_url=str(settings.gemini_base_url),
                timeout_seconds=settings.request_timeout_seconds,
                max_response_bytes=settings.max_provider_response_bytes,
            )
        )
    if (
        settings.cloud_policy == "privacy_aware"
        and settings.reasoning_provider == "nvidia"
        and settings.nvidia_api_key is not None
    ):
        cloud_providers.append(
            NvidiaChatProvider(
                api_key=settings.nvidia_api_key.get_secret_value(),
                profile=_reasoning_profile(settings),
                base_url=str(settings.nvidia_base_url),
                timeout_seconds=settings.request_timeout_seconds,
                max_response_bytes=settings.max_provider_response_bytes,
                max_output_tokens=settings.nvidia_max_output_tokens,
                max_requests_per_minute=settings.nvidia_max_requests_per_minute,
                max_concurrency=settings.nvidia_max_concurrency,
            )
        )
    for cloud_provider in cloud_providers:
        profile = cloud_provider.profile
        try:
            available = await cloud_provider.validate_model()
            checks.append(
                DiagnosticCheck(
                    name=f"{profile.role.value.upper()} model catalog",
                    status=DiagnosticStatus.PASS if available else DiagnosticStatus.FAIL,
                    detail=(
                        f"Configured model is available: {profile.provider}/{profile.model_id}"
                        if available
                        else f"Configured model is absent: {profile.provider}/{profile.model_id}"
                    ),
                    remediation=(
                        None
                        if available
                        else "Replace the role model ID in configuration; fallback remains active."
                    ),
                )
            )
        except Exception:
            checks.append(
                DiagnosticCheck(
                    name=f"{profile.role.value.upper()} model catalog",
                    status=DiagnosticStatus.FAIL,
                    detail=f"Could not validate {profile.provider}/{profile.model_id}.",
                    remediation=(
                        "Check free-tier credentials, quota, network, and live model catalog."
                    ),
                )
            )
        finally:
            await cloud_provider.close()

    return DiagnosticReport(checks=tuple(checks))


async def _remote_identity_check(settings: Settings) -> DiagnosticCheck:
    store = SQLiteRemoteIdentityStore(settings.database_path)
    try:
        await store.initialize()
        devices = await store.list_devices(host_id=local_memory_host_id())
    except Exception:
        return DiagnosticCheck(
            name="remote API identity",
            status=DiagnosticStatus.FAIL,
            detail="Remote identity migration or store validation failed.",
            remediation="Keep the listener on loopback; check database permissions and migrations.",
        )
    finally:
        await store.close()
    active_count = sum(device.state.value == "active" for device in devices)
    browser_detail = (
        f"{len(settings.trusted_browser_origins)} exact HTTPS browser origin(s) configured"
        if settings.trusted_browser_origins
        else "browser cookie bootstrap disabled until an exact HTTPS origin is configured"
    )
    return DiagnosticCheck(
        name="remote API identity",
        status=DiagnosticStatus.PASS,
        detail=(
            f"Versioned device authentication is available with {active_count} active device(s); "
            f"{browser_detail}; web listener remains loopback-only at "
            f"{settings.web_host}:{settings.web_port}."
        ),
    )


def _computer_access_check(settings: Settings) -> DiagnosticCheck:
    if not settings.computer_access_enabled:
        return DiagnosticCheck(
            name="controlled computer access",
            status=DiagnosticStatus.PASS,
            detail="Computer access master switch is disabled; no action authority is exposed.",
        )
    try:
        policy = ComputerAccessConfigStore(settings.data_dir).load()
        if not policy.enabled:
            raise ValueError("host policy is disabled")
        if not policy.controlled_root.is_dir() or policy.controlled_root.is_symlink():
            raise ValueError("controlled root is unavailable")
        for application_id, application in policy.applications.items():
            enrollment = ExecutableEnrollment.capture(application.executable)
            if enrollment.sha256 != application.sha256:
                raise ValueError(f"application enrollment changed: {application_id}")
    except (OSError, ValueError):
        return DiagnosticCheck(
            name="controlled computer access",
            status=DiagnosticStatus.FAIL,
            detail="Computer access policy, controlled root, or application enrollment is invalid.",
            remediation=(
                "Run `uv run jarvis computer status`; disable the master switch or repair the "
                "trusted local policy before requesting actions."
            ),
        )
    return DiagnosticCheck(
        name="controlled computer access",
        status=DiagnosticStatus.PASS,
        detail=(
            f"Dual enablement is valid at maximum permission Level "
            f"{int(policy.maximum_permission_level)} with {len(policy.applications)} enrolled "
            "application(s)."
        ),
    )


def _research_parser_check(settings: Settings) -> DiagnosticCheck:
    if not settings.research_enabled:
        return DiagnosticCheck(
            name="research parser sandbox",
            status=DiagnosticStatus.PASS,
            detail="Research is disabled; no network or parser surface is active.",
        )
    try:
        if find_spec("pypdf") is None:
            raise ModuleNotFoundError("pypdf")
        parsed = SandboxedDocumentParser(timeout_seconds=5).parse(
            FetchedDocument(
                requested_url="https://example.com/doctor",
                final_url="https://example.com/doctor",
                media_type="text/plain",
                body=b"JARVIS isolated parser diagnostic.",
                retrieved_at=datetime.now(UTC),
                status_code=200,
            )
        )
        if parsed.text != "JARVIS isolated parser diagnostic.":
            raise ValueError("unexpected parser output")
    except Exception:
        return DiagnosticCheck(
            name="research parser sandbox",
            status=DiagnosticStatus.FAIL,
            detail="The isolated research parser or PDF dependency is unavailable.",
            remediation="Run `uv sync --locked`, then run `uv run jarvis doctor` again.",
        )
    return DiagnosticCheck(
        name="research parser sandbox",
        status=DiagnosticStatus.PASS,
        detail="Isolated parser worker and locked PDF dependency are available.",
    )


def _bounded_task_check(settings: Settings) -> DiagnosticCheck:
    state = (
        "enabled for explicit foreground runs" if settings.task_execution_enabled else "disabled"
    )
    return DiagnosticCheck(
        name="bounded task execution",
        status=DiagnosticStatus.PASS,
        detail=(
            f"Task execution is {state}; host ceilings are {settings.task_max_steps} steps, "
            f"{settings.task_max_wall_seconds:g}s wall time, {settings.task_max_retries} retries, "
            f"{settings.task_max_tool_calls} tool calls, {settings.task_max_concurrency} "
            f"read-only workers, and ${settings.task_max_cost_usd:g} cloud cost."
        ),
    )


def _vision_capture_check(settings: Settings) -> DiagnosticCheck:
    if not settings.vision_capture_enabled:
        return DiagnosticCheck(
            name="vision capture",
            status=DiagnosticStatus.PASS,
            detail="Vision host gate is disabled; no camera/screen source can open.",
        )
    from jarvis.vision.settings_store import VisionSettingsError, VisionSettingsFile

    try:
        control = VisionSettingsFile(settings.vision_settings_path).load_control()
        if find_spec("cv2") is None or find_spec("PIL.ImageGrab") is None:
            raise ModuleNotFoundError
    except (VisionSettingsError, ModuleNotFoundError):
        return DiagnosticCheck(
            name="vision capture",
            status=DiagnosticStatus.FAIL,
            detail="Enabled vision capture lacks valid controls or optional local dependencies.",
            remediation=(
                "Disable JARVIS_VISION_CAPTURE_ENABLED or run "
                "`uv sync --locked --extra vision` and repair vision settings."
            ),
        )
    return DiagnosticCheck(
        name="vision capture",
        status=DiagnosticStatus.PASS,
        detail=(
            "Vision host gate is enabled; user control is "
            f"{'enabled' if control.enabled else 'disabled'}, and no background listener exists."
        ),
    )
