from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console
from typer.testing import CliRunner

import jarvis.cli as cli
from jarvis.config import Settings
from jarvis.core import (
    RuntimeErrorCode,
    RuntimeErrorDetail,
    RuntimeResult,
    RuntimeStatus,
)
from jarvis.diagnostics import DiagnosticCheck, DiagnosticReport, DiagnosticStatus
from jarvis.voice.models import (
    AudioDevice,
    AudioDeviceDirection,
    VoiceFailure,
    VoiceFailureCode,
    VoiceState,
    VoiceTurnResult,
)


class FakeService:
    def __init__(self, result: RuntimeResult) -> None:
        self.result = result
        self.requests: list[tuple[str, str | None, dict[str, str]]] = []

    async def respond(
        self,
        user_input: str,
        *,
        conversation_id: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> RuntimeResult:
        self.requests.append((user_input, conversation_id, metadata or {}))
        return self.result


class FakeComponents:
    def __init__(self, service: FakeService) -> None:
        self.service = service
        self.closed = False

    async def __aenter__(self) -> FakeComponents:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        self.closed = True


def capture_console(monkeypatch: pytest.MonkeyPatch) -> StringIO:
    output = StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, force_terminal=False, width=120))
    return output


def test_version_command(monkeypatch: pytest.MonkeyPatch) -> None:
    output = capture_console(monkeypatch)

    result = CliRunner().invoke(cli.app, ["version"])

    assert result.exit_code == 0
    assert output.getvalue().strip() == "JARVIS 0.1.0"


@pytest.mark.asyncio
async def test_one_shot_chat_returns_reply_and_reuses_conversation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = capture_console(monkeypatch)
    service = FakeService(
        RuntimeResult(
            status=RuntimeStatus.COMPLETED,
            reply="Ready.",
            conversation_id="conversation-1",
        )
    )
    components = FakeComponents(service)

    async def fake_build_runtime(_settings: Settings) -> FakeComponents:
        return components

    monkeypatch.setattr(cli, "build_runtime", fake_build_runtime)
    code = await cli._chat(
        Settings(data_dir=tmp_path, _env_file=None),
        message="  Hello  ",
        conversation_id="existing",
    )

    assert code == 0
    assert service.requests == [("Hello", "existing", {"interface": "cli"})]
    assert components.closed is True
    assert "JARVIS> Ready." in output.getvalue()
    assert "Conversation: conversation-1" in output.getvalue()


@pytest.mark.asyncio
async def test_one_shot_chat_rejects_blank_message_before_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = capture_console(monkeypatch)
    service = FakeService(RuntimeResult(status=RuntimeStatus.COMPLETED, reply="unused"))
    components = FakeComponents(service)

    async def fake_build_runtime(_settings: Settings) -> FakeComponents:
        return components

    monkeypatch.setattr(cli, "build_runtime", fake_build_runtime)
    code = await cli._chat(
        Settings(data_dir=tmp_path, _env_file=None),
        message="   ",
        conversation_id=None,
    )

    assert code == 2
    assert service.requests == []
    assert "cannot be blank" in output.getvalue()


def test_render_failure_preserves_structured_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = capture_console(monkeypatch)
    result = RuntimeResult(
        status=RuntimeStatus.FAILED,
        error=RuntimeErrorDetail(
            code=RuntimeErrorCode.PROVIDER_ERROR,
            message="Provider unavailable.",
        ),
    )

    cli._render_result(result)

    assert "[provider_error] Provider unavailable." in output.getvalue()


def test_render_diagnostics_includes_remediation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = capture_console(monkeypatch)
    report = DiagnosticReport(
        checks=(
            DiagnosticCheck(
                name="Ollama model",
                status=DiagnosticStatus.FAIL,
                detail="Model is missing.",
                remediation="Run ollama pull model:1",
            ),
        )
    )

    cli._render_diagnostics(report)

    assert "Ollama model" in output.getvalue()
    assert "Run ollama pull model:1" in output.getvalue()
    assert "needs attention" in output.getvalue()


def voice_endpoint(
    device_id: str,
    direction: AudioDeviceDirection,
) -> AudioDevice:
    return AudioDevice(
        id=device_id,
        name=f"{direction.value} device",
        direction=direction,
        host_api="WASAPI",
        backend_index=0 if direction is AudioDeviceDirection.INPUT else 1,
        max_channels=2,
        default_sample_rate_hz=48_000,
        is_default=True,
    )


def test_voice_enable_disable_and_device_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = capture_console(monkeypatch)
    settings = Settings(data_dir=tmp_path, _env_file=None)
    monkeypatch.setattr(cli, "_load_settings", lambda: settings)

    class FakeAudio:
        async def list_devices(self) -> tuple[AudioDevice, ...]:
            return (
                voice_endpoint("input-id", AudioDeviceDirection.INPUT),
                voice_endpoint("output-id", AudioDeviceDirection.OUTPUT),
            )

    monkeypatch.setattr("jarvis.voice.audio_io.SoundDeviceAudio", FakeAudio)
    runner = CliRunner()
    assert runner.invoke(cli.app, ["voice", "enable"]).exit_code == 0
    assert runner.invoke(cli.app, ["voice", "devices"]).exit_code == 0
    selected = runner.invoke(
        cli.app,
        [
            "voice",
            "select",
            "--input-device-id",
            "input-id",
            "--output-device-id",
            "output-id",
        ],
    )
    assert selected.exit_code == 0
    assert runner.invoke(cli.app, ["voice", "disable"]).exit_code == 0
    assert "push-to-talk enabled" in output.getvalue()
    assert "input-id" in output.getvalue()
    from jarvis.voice.settings_store import VoiceSettingsFile

    store = VoiceSettingsFile(settings.voice_settings_path)
    assert store.load_devices().input_device_id == "input-id"
    assert store.load_control().enabled is False


def test_voice_select_rejects_empty_or_unknown_device(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    monkeypatch.setattr(cli, "_load_settings", lambda: settings)

    class FakeAudio:
        async def list_devices(self) -> tuple[AudioDevice, ...]:
            return (voice_endpoint("input-id", AudioDeviceDirection.INPUT),)

    monkeypatch.setattr("jarvis.voice.audio_io.SoundDeviceAudio", FakeAudio)
    runner = CliRunner()
    assert runner.invoke(cli.app, ["voice", "select"]).exit_code == 2
    assert (
        runner.invoke(
            cli.app,
            ["voice", "select", "--output-device-id", "missing"],
        ).exit_code
        == 2
    )


def test_voice_setup_and_doctor_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = capture_console(monkeypatch)
    settings = Settings(data_dir=tmp_path, _env_file=None)
    monkeypatch.setattr(cli, "_load_settings", lambda: settings)

    async def fake_download(_settings: Settings) -> Path:
        return tmp_path / "models"

    async def fake_doctor(_settings: Settings) -> DiagnosticReport:
        return DiagnosticReport(
            checks=(
                DiagnosticCheck(
                    name="voice privacy mode",
                    status=DiagnosticStatus.PASS,
                    detail="local",
                ),
            )
        )

    monkeypatch.setattr("jarvis.voice.diagnostics.download_stt_model", fake_download)
    monkeypatch.setattr("jarvis.voice.diagnostics.run_voice_diagnostics", fake_doctor)
    runner = CliRunner()
    assert runner.invoke(cli.app, ["voice", "setup"]).exit_code == 0
    assert runner.invoke(cli.app, ["voice", "doctor"]).exit_code == 0
    assert "Local voice models ready" in output.getvalue()
    assert "voice privacy mode" in output.getvalue()


@pytest.mark.asyncio
async def test_voice_push_to_talk_renders_success_and_text_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = capture_console(monkeypatch)
    settings = Settings(data_dir=tmp_path, _env_file=None)

    class FakeController:
        def __init__(self, result: VoiceTurnResult) -> None:
            self.result = result

        async def run_push_to_talk(self, **_kwargs: object) -> VoiceTurnResult:
            return self.result

    class FakeVoiceComponents:
        def __init__(self, result: VoiceTurnResult) -> None:
            self.controller = FakeController(result)
            self.vad = self
            self.stt = self

        async def health_check(self) -> None:
            return None

        async def __aenter__(self) -> FakeVoiceComponents:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

    success = VoiceTurnResult(
        session_id="voice-test",
        final_state=VoiceState.IDLE,
        assistant_result=RuntimeResult(status=RuntimeStatus.COMPLETED, reply="Ready."),
        events=(),
    )

    async def build_success(_settings: Settings, **_kwargs: object) -> FakeVoiceComponents:
        return FakeVoiceComponents(success)

    monkeypatch.setattr("jarvis.voice.bootstrap.build_voice_runtime", build_success)
    assert await cli._voice_push_to_talk(settings, conversation_id=None) == 0
    assert "JARVIS> Ready." in output.getvalue()

    failure = VoiceTurnResult(
        session_id="voice-test",
        final_state=VoiceState.ERROR,
        events=(),
        failure=VoiceFailure(
            code=VoiceFailureCode.NO_SPEECH,
            message="No speech.",
        ),
        text_fallback=True,
    )

    async def build_failure(_settings: Settings, **_kwargs: object) -> FakeVoiceComponents:
        return FakeVoiceComponents(failure)

    monkeypatch.setattr("jarvis.voice.bootstrap.build_voice_runtime", build_failure)
    assert await cli._voice_push_to_talk(settings, conversation_id=None) == 1
    assert "Text fallback" in output.getvalue()


def test_computer_policy_commands_rotate_epochs_and_fail_closed_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from jarvis.computer.config import ComputerAccessConfigStore

    output = capture_console(monkeypatch)
    settings = Settings(data_dir=tmp_path, computer_access_enabled=False, _env_file=None)
    monkeypatch.setattr(cli, "_load_settings", lambda: settings)
    runner = CliRunner()
    store = ComputerAccessConfigStore(tmp_path)

    missing_enable = runner.invoke(cli.app, ["computer", "enable"])
    assert missing_enable.exit_code == 1
    assert not store.path.exists()

    initialized = runner.invoke(cli.app, ["computer", "init"])
    assert initialized.exit_code == 0
    initial = store.load()
    assert initial.enabled is False

    first_enable = runner.invoke(cli.app, ["computer", "enable"])
    assert first_enable.exit_code == 0
    enabled_once = store.load()
    assert enabled_once.enabled is True
    assert enabled_once.policy_version != initial.policy_version

    second_enable = runner.invoke(cli.app, ["computer", "enable"])
    assert second_enable.exit_code == 0
    enabled_twice = store.load()
    assert enabled_twice.policy_version != enabled_once.policy_version

    disabled = runner.invoke(cli.app, ["computer", "disable"])
    assert disabled.exit_code == 0
    disabled_policy = store.load()
    assert disabled_policy.enabled is False
    assert disabled_policy.policy_version != enabled_twice.policy_version

    store.path.unlink()
    missing_disable = runner.invoke(cli.app, ["computer", "disable"])
    assert missing_disable.exit_code == 0
    assert not store.path.exists()
    assert "prior grants cannot revive" in output.getvalue()


@pytest.mark.asyncio
async def test_computer_audit_kinds_are_bounded_sanitized_views(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = capture_console(monkeypatch)
    settings = Settings(data_dir=tmp_path, _env_file=None)

    assert await cli._computer_audit(settings, limit=1, kind="lifecycle") == 0
    assert await cli._computer_audit(settings, limit=1, kind="receipts") == 0
    assert await cli._computer_audit(settings, limit=1, kind="events") == 0

    rendered = output.getvalue()
    assert "Sanitized computer authority lifecycle" in rendered
    assert "Sanitized computer action receipts" in rendered
    assert "Sanitized computer broker events" in rendered


def test_computer_audit_rejects_unknown_view_before_state_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = capture_console(monkeypatch)

    result = CliRunner().invoke(cli.app, ["computer", "audit", "--kind", "private"])

    assert result.exit_code == 2
    assert "all, lifecycle, receipts, or events" in output.getvalue()
