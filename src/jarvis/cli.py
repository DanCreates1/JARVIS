"""Terminal interface for JARVIS Phase 1."""

from __future__ import annotations

import asyncio
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table
from rich.text import Text

from jarvis import __version__
from jarvis.bootstrap import build_runtime
from jarvis.config import Settings
from jarvis.core import ModelRole, RuntimeResult, RuntimeStatus
from jarvis.diagnostics import DiagnosticReport, DiagnosticStatus, run_diagnostics
from jarvis.logging_config import configure_logging

app = typer.Typer(
    name="jarvis",
    help="Secure, local-first JARVIS assistant.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console(highlight=False)


def _load_settings() -> Settings:
    try:
        settings = Settings()
    except ValidationError as exc:
        console.print("[bold red]Invalid JARVIS configuration.[/]")
        for error in exc.errors(include_url=False, include_input=False):
            location = ".".join(str(part) for part in error["loc"])
            console.print(f"  {location}: {error['msg']}")
        raise typer.Exit(code=2) from None
    configure_logging(settings.log_level)
    return settings


@app.command()
def version() -> None:
    """Print the installed JARVIS version."""
    console.print(f"JARVIS {__version__}")


@app.command()
def doctor() -> None:
    """Validate configuration, storage, Ollama, and the configured model."""
    settings = _load_settings()
    report = asyncio.run(run_diagnostics(settings))
    _render_diagnostics(report)
    if not report.ok:
        raise typer.Exit(code=1)


@app.command()
def chat(
    message: Annotated[
        str | None,
        typer.Option("--message", "-m", help="Send one message and exit."),
    ] = None,
    conversation_id: Annotated[
        str | None,
        typer.Option("--conversation-id", "-c", help="Resume a saved conversation."),
    ] = None,
    model_role: Annotated[
        ModelRole | None,
        typer.Option("--model-role", help="Request fast, primary, reasoning, or local routing."),
    ] = None,
) -> None:
    """Chat interactively or send one non-interactive message."""
    settings = _load_settings()
    try:
        exit_code = asyncio.run(
            _chat(
                settings,
                message=message,
                conversation_id=conversation_id,
                model_role=model_role,
            )
        )
    except KeyboardInterrupt:
        console.print("\n[dim]JARVIS stopped.[/]")
        exit_code = 130
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _chat(
    settings: Settings,
    *,
    message: str | None,
    conversation_id: str | None,
    model_role: ModelRole | None = None,
) -> int:
    try:
        components = await build_runtime(settings)
    except Exception:
        console.print(
            "[bold red]JARVIS could not initialize local memory.[/] "
            "Run `uv run jarvis doctor` for details."
        )
        return 1

    async with components:
        if message is not None:
            normalized = message.strip()
            if not normalized:
                console.print("[bold red]Message cannot be blank.[/]")
                return 2
            if model_role is None:
                result = await components.service.respond(
                    normalized,
                    conversation_id=conversation_id,
                    metadata={"interface": "cli"},
                )
            else:
                result = await components.service.respond(
                    normalized,
                    conversation_id=conversation_id,
                    metadata={"interface": "cli"},
                    requested_model_role=model_role,
                )
            _render_result(result)
            return 0 if result.status is RuntimeStatus.COMPLETED else 1

        console.print("[bold cyan]JARVIS Phase 1[/] — type /exit to stop.")
        active_conversation = conversation_id
        while True:
            try:
                user_input = console.input("[bold cyan]You> [/]").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]JARVIS stopped.[/]")
                return 0
            if user_input.casefold() in {"/exit", "/quit"}:
                return 0
            if not user_input:
                continue
            if model_role is None:
                result = await components.service.respond(
                    user_input,
                    conversation_id=active_conversation,
                    metadata={"interface": "cli"},
                )
            else:
                result = await components.service.respond(
                    user_input,
                    conversation_id=active_conversation,
                    metadata={"interface": "cli"},
                    requested_model_role=model_role,
                )
            _render_result(result)
            if result.conversation_id is not None:
                active_conversation = result.conversation_id


def _render_result(result: RuntimeResult) -> None:
    if result.status is RuntimeStatus.COMPLETED:
        console.print(f"[bold green]JARVIS>[/] {result.reply}")
        if result.conversation_id:
            console.print(f"[dim]Conversation: {result.conversation_id}[/]")
        return
    if result.error is None:
        console.print("[bold red]JARVIS failed without a structured error.[/]")
        return
    line = Text()
    line.append(f"JARVIS {result.status.value}", style="bold red")
    line.append(f" [{result.error.code.value}] {result.error.message}")
    console.print(line)


def _render_diagnostics(report: DiagnosticReport) -> None:
    table = Table(title="JARVIS doctor", show_lines=False)
    table.add_column("Status", no_wrap=True)
    table.add_column("Check", no_wrap=True)
    table.add_column("Detail")
    for check in report.checks:
        if check.status is DiagnosticStatus.PASS:
            status = "[bold green]PASS[/]"
        else:
            status = "[bold red]FAIL[/]"
        detail = check.detail
        if check.remediation:
            detail = f"{detail}\n[dim]{check.remediation}[/]"
        table.add_row(status, check.name, detail)
    console.print(table)
    if report.ok:
        console.print("[bold green]JARVIS is ready.[/]")
    else:
        console.print("[bold red]JARVIS needs attention before chat can run.[/]")


@app.command()
def serve() -> None:
    """Start loopback-only browser chat and local API."""
    import uvicorn

    from jarvis.web import create_app

    settings = _load_settings()
    console.print(
        f"[bold cyan]JARVIS browser chat:[/] http://{settings.web_host}:{settings.web_port}"
    )
    uvicorn.run(
        create_app(settings),
        host=settings.web_host,
        port=settings.web_port,
        log_level=settings.log_level.casefold(),
    )
