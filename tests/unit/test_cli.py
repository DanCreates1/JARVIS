from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console
from typer.testing import CliRunner

import jarvis.cli as cli
from jarvis.config import Settings
from jarvis.core import (
    AssistantRequest,
    RuntimeErrorCode,
    RuntimeErrorDetail,
    RuntimeEvent,
    RuntimeEventType,
    RuntimeResult,
    RuntimeStatus,
    RuntimeStreamFrame,
)
from jarvis.diagnostics import DiagnosticCheck, DiagnosticReport, DiagnosticStatus
from jarvis.research import (
    Citation,
    CitationValidationReceipt,
    ClaimStatus,
    PendingResearchRun,
    ResearchApprovalReceipt,
    ResearchClaim,
    ResearchInterface,
    ResearchPlan,
    ResearchReport,
    ResearchRunResult,
    SourceRecord,
    SQLiteResearchStore,
)
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

    async def stream(self, request: AssistantRequest) -> Any:
        self.requests.append((request.user_input, request.conversation_id, request.metadata))
        yield RuntimeStreamFrame(result=self.result)


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


def test_remote_enrollment_cli_requires_scope_and_persists_only_challenge_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = capture_console(monkeypatch)
    data_dir = tmp_path / "remote-cli"
    monkeypatch.setenv("JARVIS_DATA_DIR", str(data_dir))
    runner = CliRunner()

    missing_scope = runner.invoke(cli.app, ["remote", "enroll", "Phone"])
    assert missing_scope.exit_code == 2
    assert "at least one --scope is required" in output.getvalue()

    output.seek(0)
    output.truncate(0)
    enrolled = runner.invoke(
        cli.app,
        ["remote", "enroll", "Phone", "--scope", "identity.read"],
    )
    assert enrolled.exit_code == 0
    text = output.getvalue()
    assert '"challenge"' in text and "expires in 5 minutes" in text
    challenge_line = next(line for line in text.splitlines() if '"challenge"' in line)
    challenge = challenge_line.split('"')[3]
    with sqlite3.connect(data_dir / "jarvis.db") as connection:
        stored = connection.execute(
            "SELECT challenge_sha256, scopes_json FROM remote_enrollments"
        ).fetchone()
    assert stored is not None
    assert stored[0] != challenge and len(stored[0]) == 64
    assert json.loads(stored[1]) == ["identity.read"]

    output.seek(0)
    output.truncate(0)
    listed = runner.invoke(cli.app, ["remote", "devices"])
    assert listed.exit_code == 0
    assert "JARVIS enrolled devices" in output.getvalue()

    output.seek(0)
    output.truncate(0)
    mismatch = runner.invoke(
        cli.app,
        [
            "remote",
            "revoke",
            "device:missing",
            "--confirm-device-id",
            "device:other",
        ],
    )
    assert mismatch.exit_code == 2
    assert "confirmation does not match" in output.getvalue()


def test_phase6_task_cli_preview_list_show_default_off_and_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = capture_console(monkeypatch)
    data_dir = tmp_path / "data"
    monkeypatch.setenv("JARVIS_DATA_DIR", str(data_dir))
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "objective": "CLI bounded plan",
                "owner": "owner-a",
                "provenance": {
                    "source_type": "host",
                    "source_id": "cli-fixture",
                    "untrusted": True,
                },
                "budget": {
                    "max_steps": 1,
                    "max_wall_seconds": 60,
                    "max_tokens": 0,
                    "max_provider_requests": 0,
                    "max_retries": 0,
                    "max_tool_calls": 1,
                    "max_cost_usd": 0,
                    "max_concurrency": 1,
                },
                "deadline_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
                "nodes": [{"id": "value", "handler": "task.value", "arguments": {"value": 1}}],
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()
    created = runner.invoke(cli.app, ["task", "create", str(plan_path)])
    assert created.exit_code == 0
    text = output.getvalue()
    assert "CLI bounded plan" in text
    task_id = text.split("Task: ", 1)[1].split(" ", 1)[0]
    output.seek(0)
    output.truncate(0)
    assert runner.invoke(cli.app, ["task", "list"]).exit_code == 0
    assert task_id in output.getvalue()
    output.seek(0)
    output.truncate(0)
    assert runner.invoke(cli.app, ["task", "show", task_id]).exit_code == 0
    assert "Validated immutable plan" in output.getvalue()
    output.seek(0)
    output.truncate(0)
    assert runner.invoke(cli.app, ["task", "run", task_id]).exit_code == 1
    assert "Task execution is disabled" in output.getvalue()
    output.seek(0)
    output.truncate(0)
    deleted = runner.invoke(
        cli.app,
        ["task", "delete", task_id, "--confirm-task-id", task_id],
    )
    assert deleted.exit_code == 0
    assert "Deleted" in output.getvalue()


def test_phase6_task_cli_foreground_controls_events_and_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = capture_console(monkeypatch)
    data_dir = tmp_path / "data"
    monkeypatch.setenv("JARVIS_DATA_DIR", str(data_dir))
    monkeypatch.setenv("JARVIS_TASK_EXECUTION_ENABLED", "true")
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "objective": "CLI lifecycle plan",
                "owner": "owner-a",
                "provenance": {"source_type": "host", "source_id": "cli-lifecycle"},
                "budget": {
                    "max_steps": 1,
                    "max_wall_seconds": 60,
                    "max_tokens": 0,
                    "max_provider_requests": 0,
                    "max_retries": 0,
                    "max_tool_calls": 1,
                    "max_cost_usd": 0,
                    "max_concurrency": 1,
                },
                "deadline_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
                "nodes": [{"id": "value", "handler": "task.value", "arguments": {"value": 7}}],
            }
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    created = runner.invoke(cli.app, ["task", "create", str(plan_path)])
    assert created.exit_code == 0
    task_id = output.getvalue().split("Task: ", 1)[1].split(" ", 1)[0]

    output.seek(0)
    output.truncate(0)
    assert runner.invoke(cli.app, ["task", "pause", task_id]).exit_code == 0
    assert "Pause recorded" in output.getvalue()
    assert runner.invoke(cli.app, ["task", "resume", task_id]).exit_code == 0
    assert runner.invoke(cli.app, ["task", "run", task_id]).exit_code == 0

    output.seek(0)
    output.truncate(0)
    assert runner.invoke(cli.app, ["task", "events", task_id]).exit_code == 0
    assert "task_completed" in output.getvalue()
    export_path = tmp_path / "task-export.json"
    assert runner.invoke(cli.app, ["task", "export", str(export_path)]).exit_code == 0
    assert export_path.is_file()
    assert runner.invoke(cli.app, ["task", "export", str(export_path)]).exit_code == 1

    output.seek(0)
    output.truncate(0)
    second = runner.invoke(cli.app, ["task", "create", str(plan_path)])
    assert second.exit_code == 0
    second_id = output.getvalue().split("Task: ", 1)[1].split(" ", 1)[0]
    assert runner.invoke(cli.app, ["task", "cancel", second_id]).exit_code == 0
    assert runner.invoke(cli.app, ["task", "show", "missing-task"]).exit_code == 1
    assert (
        runner.invoke(
            cli.app,
            ["task", "delete", second_id, "--confirm-task-id", "wrong-task"],
        ).exit_code
        == 2
    )


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


@pytest.mark.asyncio
async def test_stream_cli_turn_prints_deltas_once_and_requires_terminal_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = capture_console(monkeypatch)
    result = RuntimeResult(
        status=RuntimeStatus.COMPLETED,
        reply="Ready now.",
        conversation_id="conversation-1",
    )

    class StreamingService:
        async def stream(self, _request: AssistantRequest) -> Any:
            yield RuntimeStreamFrame(
                event=RuntimeEvent(
                    sequence=1,
                    type=RuntimeEventType.CONVERSATION_CREATED,
                )
            )
            yield RuntimeStreamFrame(
                event=RuntimeEvent(
                    sequence=2,
                    type=RuntimeEventType.ASSISTANT_DELTA,
                    content_delta="Ready ",
                )
            )
            yield RuntimeStreamFrame(
                event=RuntimeEvent(
                    sequence=3,
                    type=RuntimeEventType.ASSISTANT_DELTA,
                    content_delta="now.",
                )
            )
            yield RuntimeStreamFrame(result=result)

    terminal, streamed = await cli._stream_cli_turn(
        StreamingService(),
        AssistantRequest(user_input="Hello"),
    )
    cli._render_result(terminal, reply_streamed=streamed)

    rendered = output.getvalue()
    assert terminal is result
    assert streamed is True
    assert rendered.count("JARVIS>") == 1
    assert "Ready now." in rendered
    assert "Conversation: conversation-1" in rendered

    class MissingTerminalService:
        async def stream(self, _request: AssistantRequest) -> Any:
            if False:
                yield

    with pytest.raises(RuntimeError, match="without a terminal result"):
        await cli._stream_cli_turn(
            MissingTerminalService(),
            AssistantRequest(user_input="Hello"),
        )


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


def _pending_research() -> PendingResearchRun:
    now = datetime(2026, 9, 6, tzinfo=UTC)
    source = SourceRecord(
        id="source-cli",
        host_id="host-cli",
        url="https://example.com/source",
        title="CLI source",
        topic="Alpha",
        media_type="text/plain",
        content_sha256="a" * 64,
        extracted_text="Alpha evidence.",
        retrieved_at=now,
        last_checked_at=now,
    )
    claim = ResearchClaim(
        id="claim-cli",
        statement="Alpha.",
        status=ClaimStatus.VERIFIED,
        citations=(Citation(source_id=source.id, locator="text:0-5", quote="Alpha"),),
    )
    plan = ResearchPlan(objective="Research Alpha", questions=("What is Alpha?",))
    result = ResearchRunResult(
        plan=plan,
        report=ResearchReport(
            objective=plan.objective,
            answer="Alpha. [source:source-cli]",
            sources=(source,),
            claims=(claim,),
            unanswered_questions=("What remains unknown?",),
            generated_at=now,
        ),
        validation=CitationValidationReceipt(
            source_count=1,
            claim_count=1,
            material_claim_count=1,
            citation_count=1,
            quoted_word_count=1,
        ),
        queries_attempted=1,
        search_results_considered=1,
        fetches_attempted=1,
    )
    return PendingResearchRun(
        id="pending-cli",
        host_id="host-cli",
        report_sha256="b" * 64,
        result=result,
        expires_at=now.replace(hour=1),
    )


def test_research_cli_defaults_to_denial_and_requires_store_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = capture_console(monkeypatch)
    settings = Settings(data_dir=tmp_path, _env_file=None)
    decisions: list[str] = []

    class FakeResearch:
        async def run(self, **_kwargs: object) -> PendingResearchRun:
            return _pending_research()

        async def deny(self, **_kwargs: object) -> ResearchApprovalReceipt:
            decisions.append("deny")
            return ResearchApprovalReceipt(
                pending_run_id="pending-cli", report_sha256="b" * 64, stored=False
            )

        async def approve(self, approval) -> ResearchApprovalReceipt:  # type: ignore[no-untyped-def]
            assert approval.interface is ResearchInterface.LOCAL_CLI
            decisions.append("approve")
            return ResearchApprovalReceipt(
                pending_run_id="pending-cli",
                report_sha256="b" * 64,
                stored=True,
                report_id="report-cli",
                source_count=1,
                claim_count=1,
            )

    class ResearchComponents:
        research = FakeResearch()
        memory_host_id = "host-cli"

        async def close(self) -> None:
            return None

    async def fake_runtime(_settings: Settings) -> ResearchComponents:
        return ResearchComponents()

    monkeypatch.setattr(cli, "_load_settings", lambda: settings)
    monkeypatch.setattr(cli, "build_runtime", fake_runtime)
    runner = CliRunner()
    volatile = runner.invoke(cli.app, ["research", "run", "Research Alpha", "-q", "What is Alpha?"])
    stored = runner.invoke(
        cli.app,
        ["research", "run", "Research Alpha", "-q", "What is Alpha?", "--store"],
    )
    assert volatile.exit_code == 0
    assert stored.exit_code == 0
    assert decisions == ["deny", "approve"]
    assert "Not stored" in output.getvalue()
    assert "Stored approved research report-cli" in output.getvalue()


def test_research_cli_delete_requires_exact_source_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = capture_console(monkeypatch)
    result = CliRunner().invoke(
        cli.app,
        ["research", "delete-source", "source-1", "--confirm", "source-2"],
    )
    assert result.exit_code == 2
    assert "must exactly match" in output.getvalue()


def test_research_cli_inspect_search_question_export_and_delete_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = capture_console(monkeypatch)
    settings = Settings(data_dir=tmp_path, _env_file=None)

    async def seed():  # type: ignore[no-untyped-def]
        pending = _pending_research()
        async with SQLiteResearchStore(settings.database_path) as store:
            return await store.store_approved_report(
                host_id=pending.host_id,
                report=pending.result.report,
                report_sha256=pending.report_sha256,
                interface=ResearchInterface.LOCAL_CLI,
                approved_at=datetime(2026, 9, 6, tzinfo=UTC),
            )

    stored = asyncio.run(seed())
    monkeypatch.setattr(cli, "_load_settings", lambda: settings)
    monkeypatch.setattr(cli, "local_memory_host_id", lambda: "host-cli")
    runner = CliRunner()

    listed = runner.invoke(cli.app, ["research", "list"])
    shown = runner.invoke(cli.app, ["research", "show", stored.id])
    searched = runner.invoke(cli.app, ["research", "search", "Alpha"])
    questions = runner.invoke(cli.app, ["research", "questions"])

    async def question_id() -> str:
        async with SQLiteResearchStore(settings.database_path) as store:
            return (await store.list_unanswered_questions(host_id="host-cli"))[0].id

    closed = runner.invoke(
        cli.app,
        [
            "research",
            "close-question",
            asyncio.run(question_id()),
            "--expected-version",
            "1",
            "--answer-claim-id",
            stored.claim_ids[0],
        ],
    )
    destination = tmp_path / "research-export.json"
    exported = runner.invoke(cli.app, ["research", "export", str(destination)])
    duplicate_export = runner.invoke(cli.app, ["research", "export", str(destination)])
    deleted = runner.invoke(
        cli.app,
        [
            "research",
            "delete-source",
            stored.source_ids[0],
            "--confirm",
            stored.source_ids[0],
        ],
    )

    assert all(
        result.exit_code == 0
        for result in (listed, shown, searched, questions, closed, exported, deleted)
    )
    assert duplicate_export.exit_code == 1
    rendered = output.getvalue()
    assert "Research Alpha" in rendered
    assert "[source:" in rendered
    assert "What remains unknown?" in rendered
    assert "Export path already exists" in rendered
    assert "Deleted research source history" in rendered
