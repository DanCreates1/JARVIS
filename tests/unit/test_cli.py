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
