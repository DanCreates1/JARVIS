"""Terminal interfaces for text, explicit voice, vision, and controlled JARVIS features."""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import sqlite3
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Never

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table
from rich.text import Text

from jarvis import __version__
from jarvis.bootstrap import build_runtime
from jarvis.config import Settings
from jarvis.core import (
    AssistantRequest,
    ModelRole,
    RuntimeEventType,
    RuntimeResult,
    RuntimeStatus,
)
from jarvis.diagnostics import DiagnosticReport, DiagnosticStatus, run_diagnostics
from jarvis.logging_config import configure_logging
from jarvis.memory import (
    ConfirmationInterface,
    MemoryCategory,
    MemoryConfirmation,
    MemoryNotFoundError,
    MemoryQuery,
    MemoryState,
    MemoryStateError,
    SQLiteMemoryStore,
    explicit_provenance,
    local_memory_host_id,
)
from jarvis.planning import (
    SQLiteTaskStore,
    TaskExecutionDisabledError,
    TaskNotFoundError,
    TaskPlanProposal,
    TaskPlanValidationError,
    TaskRecord,
    TaskStateError,
    TaskStatus,
)
from jarvis.remote.migration import MigrationError, MigrationErrorCode
from jarvis.remote.topology import TopologyManifest
from jarvis.research import (
    ResearchInterface,
    ResearchNotFoundError,
    ResearchOrchestrationError,
    ResearchPlan,
    ResearchStorageApproval,
    SQLiteResearchStore,
    UnansweredQuestionStatus,
)

app = typer.Typer(
    name="jarvis",
    help="Secure, local-first JARVIS assistant.",
    no_args_is_help=True,
    add_completion=False,
)
voice_app = typer.Typer(
    name="voice",
    help="Local push-to-talk, devices, kill switch, and diagnostics.",
    no_args_is_help=True,
)
app.add_typer(voice_app, name="voice")
vision_app = typer.Typer(
    name="vision",
    help="Default-off local camera/screen capture controls and diagnostics.",
    no_args_is_help=True,
)
app.add_typer(vision_app, name="vision")
computer_app = typer.Typer(
    name="computer",
    help="Controlled access policy, proposals, trusted approvals, receipts, and audit.",
    no_args_is_help=True,
)
app.add_typer(computer_app, name="computer")
memory_app = typer.Typer(
    name="memory",
    help="Inspect, confirm, correct, retrieve, export, retain, and forget durable memory.",
    no_args_is_help=True,
)
app.add_typer(memory_app, name="memory")
research_app = typer.Typer(
    name="research",
    help="Run volatile cited research, approve storage, revalidate, and review open questions.",
    no_args_is_help=True,
)
app.add_typer(research_app, name="research")
task_app = typer.Typer(
    name="task",
    help="Preview, inspect, run, pause, resume, cancel, reconcile, and delete bounded tasks.",
    no_args_is_help=True,
)
app.add_typer(task_app, name="task")
remote_app = typer.Typer(
    name="remote",
    help="Trusted-local device enrollment, inventory, revocation, and identity audit.",
    no_args_is_help=True,
)
app.add_typer(remote_app, name="remote")
migration_app = typer.Typer(
    name="migration",
    help="Encrypted backup, restore, shadow, cutover, and rollback rehearsal.",
    no_args_is_help=True,
)
remote_app.add_typer(migration_app, name="migration")
console = Console(highlight=False, legacy_windows=False)


def _fresh_computer_policy_version() -> str:
    """Rotate the authority epoch so disabled grants never revive after re-enable."""
    return f"phase3-{secrets.token_hex(16)}"


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


@remote_app.command("enroll")
def remote_enroll(
    display_name: Annotated[str, typer.Argument(help="Human-readable device name.")],
    device_type: Annotated[
        str,
        typer.Option("--type", help="phone, browser, laptop, wearable, or service"),
    ] = "phone",
    scope: Annotated[
        list[str] | None,
        typer.Option("--scope", help="Repeat for each exact approved Phase 8A scope."),
    ] = None,
    risk_ceiling: Annotated[
        int,
        typer.Option("--risk-ceiling", min=0, max=2, help="Maximum device risk class."),
    ] = 0,
) -> None:
    """Create one short-lived enrollment challenge from this trusted local terminal."""
    from jarvis.remote import (
        DeviceType,
        RemoteIdentityService,
        RemoteScope,
        SQLiteRemoteIdentityStore,
    )

    settings = _load_settings()
    try:
        selected_type = DeviceType(device_type)
        selected_scopes = tuple(RemoteScope(value) for value in (scope or ()))
        if not selected_scopes:
            raise ValueError("at least one --scope is required")
    except ValueError as exc:
        console.print(f"[bold red]Invalid enrollment request.[/] {exc}")
        raise typer.Exit(code=2) from None

    async def run() -> None:
        store = SQLiteRemoteIdentityStore(settings.database_path)
        try:
            await store.initialize()
            ticket = await RemoteIdentityService(store).create_enrollment(
                host_id=local_memory_host_id(),
                display_name=display_name,
                device_type=selected_type,
                approved_scopes=selected_scopes,
                risk_ceiling=risk_ceiling,
            )
        finally:
            await store.close()
        console.print(ticket.model_dump_json(indent=2))
        console.print(
            "[bold yellow]Enrollment challenge shown once.[/] Transfer privately; "
            "it expires in 5 minutes. Device must prove possession of its Ed25519 private key."
        )

    asyncio.run(run())


@remote_app.command("devices")
def remote_devices() -> None:
    """List this host's enrolled device metadata without keys, tokens, or private content."""
    from jarvis.remote import RemoteIdentityService, SQLiteRemoteIdentityStore

    settings = _load_settings()

    async def run() -> None:
        store = SQLiteRemoteIdentityStore(settings.database_path)
        try:
            await store.initialize()
            devices = await RemoteIdentityService(store).list_devices(
                host_id=local_memory_host_id()
            )
        finally:
            await store.close()
        table = Table(title="JARVIS enrolled devices")
        table.add_column("Device ID")
        table.add_column("Name")
        table.add_column("Type")
        table.add_column("State")
        table.add_column("Key")
        table.add_column("Scopes")
        for device in devices:
            table.add_row(
                device.id,
                device.display_name,
                device.device_type.value,
                device.state.value,
                f"v{device.key_version}:{device.key_fingerprint[:12]}",
                ", ".join(scope.value for scope in device.approved_scopes),
            )
        console.print(table)

    asyncio.run(run())


@remote_app.command("revoke")
def remote_revoke(
    device_id: Annotated[str, typer.Argument(help="Exact device ID to revoke.")],
    confirm_device_id: Annotated[
        str,
        typer.Option("--confirm-device-id", help="Must exactly match the device ID."),
    ],
) -> None:
    """Immediately revoke one device and all its sessions from this trusted local terminal."""
    from jarvis.remote import RemoteIdentityService, SQLiteRemoteIdentityStore

    if confirm_device_id != device_id:
        console.print("[bold red]Revocation confirmation does not match device ID.[/]")
        raise typer.Exit(code=2)
    settings = _load_settings()

    async def run() -> bool:
        store = SQLiteRemoteIdentityStore(settings.database_path)
        try:
            await store.initialize()
            return await RemoteIdentityService(store).revoke_device(
                host_id=local_memory_host_id(),
                device_id=device_id,
            )
        finally:
            await store.close()

    if not asyncio.run(run()):
        console.print("[bold red]Active device not found.[/]")
        raise typer.Exit(code=1)
    console.print("[bold green]Device and all sessions revoked.[/]")


@remote_app.command("audit")
def remote_audit(
    device_id: Annotated[str, typer.Argument(help="Exact enrolled device ID.")],
    after: Annotated[int, typer.Option("--after", min=0)] = 0,
    limit: Annotated[int, typer.Option("--limit", min=1, max=500)] = 100,
) -> None:
    """Show content-free lifecycle events for one device owned by this host."""
    from jarvis.remote import RemoteAuditEvent, SQLiteRemoteIdentityStore

    settings = _load_settings()

    async def run() -> tuple[RemoteAuditEvent, ...] | None:
        store = SQLiteRemoteIdentityStore(settings.database_path)
        try:
            await store.initialize()
            devices = await store.list_devices(host_id=local_memory_host_id())
            if device_id not in {device.id for device in devices}:
                return None
            return await store.list_audit_events(
                device_id=device_id,
                after_sequence=after,
                limit=limit,
            )
        finally:
            await store.close()

    events = asyncio.run(run())
    if events is None:
        console.print("[bold red]Device not found.[/]")
        raise typer.Exit(code=1)
    table = Table(title="JARVIS remote identity audit")
    table.add_column("Seq", justify="right")
    table.add_column("Time")
    table.add_column("Event")
    table.add_column("Outcome")
    table.add_column("Reason")
    for event in events:
        table.add_row(
            str(event.sequence),
            event.created_at.isoformat(),
            event.event_type,
            event.outcome.value,
            event.reason_code,
        )
    console.print(table)


@task_app.command("create")
def task_create(
    plan_path: Annotated[Path, typer.Argument(help="UTF-8 JSON task-plan proposal.")],
) -> None:
    """Validate and persist an untrusted plan for human-readable preview; do not execute it."""
    settings = _load_settings()
    try:
        proposal = TaskPlanProposal.model_validate_json(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        console.print("[bold red]Task plan is unreadable or invalid.[/]")
        raise typer.Exit(code=2) from None
    exit_code = asyncio.run(_task_create(settings, proposal))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _task_create(settings: Settings, proposal: TaskPlanProposal) -> int:
    components = None
    try:
        components = await build_runtime(settings)
        if components.tasks is None or components.memory_host_id is None:
            console.print("[bold red]Task planning is unavailable.[/]")
            return 1
        record = await components.tasks.submit(
            host_id=components.memory_host_id,
            proposal=proposal,
        )
    except (TaskPlanValidationError, TaskStateError) as exc:
        console.print(f"[bold red]Task rejected.[/] {exc}")
        return 2
    except Exception:
        console.print("[bold red]Task creation failed.[/] No execution occurred.")
        return 1
    finally:
        if components is not None:
            await components.close()
    _render_task(record)
    console.print("[dim]Plan persisted only. Run explicitly with `jarvis task run <task-id>`.[/]")
    return 0


@task_app.command("list")
def task_list(
    status: Annotated[TaskStatus | None, typer.Option(help="Optional task status.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=500)] = 100,
) -> None:
    """List host-scoped durable task state."""
    settings = _load_settings()
    exit_code = asyncio.run(_task_list(settings, status=status, limit=limit))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _task_list(settings: Settings, *, status: TaskStatus | None, limit: int) -> int:
    try:
        async with SQLiteTaskStore(settings.database_path) as store:
            records = await store.list_tasks(
                host_id=local_memory_host_id(), status=status, limit=limit
            )
    except Exception:
        console.print("[bold red]Task state is unavailable.[/]")
        return 1
    table = Table(title="Bounded tasks")
    table.add_column("Task / version", no_wrap=True)
    table.add_column("Status")
    table.add_column("Objective")
    table.add_column("Usage")
    for record in records:
        table.add_row(
            f"{record.graph.id}\nv{record.version}",
            record.status.value,
            record.graph.objective,
            (
                f"steps={record.usage.steps}/{record.graph.budget.max_steps} "
                f"tools={record.usage.tool_calls}/{record.graph.budget.max_tool_calls} "
                f"retries={record.usage.retries}/{record.graph.budget.max_retries}"
            ),
        )
    console.print(table)
    return 0


@task_app.command("show")
def task_show(task_id: Annotated[str, typer.Argument(help="Exact task ID.")]) -> None:
    """Show plan, dependencies, limits, approval state, attempts, and results."""
    settings = _load_settings()
    exit_code = asyncio.run(_task_show(settings, task_id=task_id))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _task_show(settings: Settings, *, task_id: str) -> int:
    try:
        async with SQLiteTaskStore(settings.database_path) as store:
            record = await store.require_task(host_id=local_memory_host_id(), task_id=task_id)
    except TaskNotFoundError:
        console.print("[bold red]Task not found.[/]")
        return 1
    except Exception:
        console.print("[bold red]Task state is unavailable.[/]")
        return 1
    _render_task(record)
    return 0


@task_app.command("run")
def task_run(task_id: Annotated[str, typer.Argument(help="Exact task ID.")]) -> None:
    """Run one task in foreground under configured hard limits."""
    settings = _load_settings()
    exit_code = asyncio.run(_task_run(settings, task_id=task_id))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _task_run(settings: Settings, *, task_id: str) -> int:
    components = None
    try:
        components = await build_runtime(settings)
        if components.tasks is None or components.memory_host_id is None:
            raise TaskStateError("task scheduler is unavailable")
        record = await components.tasks.run(
            host_id=components.memory_host_id,
            task_id=task_id,
        )
    except TaskExecutionDisabledError:
        console.print(
            "[bold red]Task execution is disabled.[/] "
            "Set JARVIS_TASK_EXECUTION_ENABLED=true only after reviewing the plan."
        )
        return 1
    except (TaskNotFoundError, TaskStateError) as exc:
        console.print(f"[bold red]Task cannot run.[/] {exc}")
        return 1
    except Exception:
        console.print("[bold red]Task execution failed safely.[/] Inspect task events.")
        return 1
    finally:
        if components is not None:
            await components.close()
    _render_task(record)
    return 0 if record.status is TaskStatus.COMPLETED else 1


@task_app.command("pause")
def task_pause(task_id: Annotated[str, typer.Argument(help="Exact task ID.")]) -> None:
    """Pause before the next node; active effect verification still completes."""
    _run_task_control("pause", task_id)


@task_app.command("resume")
def task_resume(task_id: Annotated[str, typer.Argument(help="Exact task ID.")]) -> None:
    """Clear pause state; explicit run remains required."""
    _run_task_control("resume", task_id)


@task_app.command("cancel")
def task_cancel(task_id: Annotated[str, typer.Argument(help="Exact task ID.")]) -> None:
    """Cancel remaining work; uncertain effects require reconciliation."""
    _run_task_control("cancel", task_id)


def _run_task_control(action: str, task_id: str) -> None:
    settings = _load_settings()
    exit_code = asyncio.run(_task_control(settings, action=action, task_id=task_id))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _task_control(settings: Settings, *, action: str, task_id: str) -> int:
    components = None
    try:
        components = await build_runtime(settings)
        if components.tasks is None or components.memory_host_id is None:
            raise TaskStateError("task scheduler is unavailable")
        operation = getattr(components.tasks, action)
        record = await operation(host_id=components.memory_host_id, task_id=task_id)
    except (TaskNotFoundError, TaskStateError) as exc:
        console.print(f"[bold red]Task control failed.[/] {exc}")
        return 1
    except Exception:
        console.print("[bold red]Task control failed safely.[/]")
        return 1
    finally:
        if components is not None:
            await components.close()
    console.print(
        f"[bold green]{action.title()} recorded[/] {record.graph.id} · {record.status.value}"
    )
    return 0


@task_app.command("bind-approval")
def task_bind_approval(
    task_id: Annotated[str, typer.Argument(help="Exact task ID.")],
    node_id: Annotated[str, typer.Argument(help="Exact effect-node ID.")],
    grant_id: Annotated[str, typer.Argument(help="Existing exact Phase 3 one-use grant ID.")],
    expected_version: Annotated[int, typer.Option(min=1, help="Exact displayed task version.")],
) -> None:
    """Bind an existing one-use grant; this command cannot create or approve authority."""
    settings = _load_settings()
    exit_code = asyncio.run(
        _task_bind_approval(
            settings,
            task_id=task_id,
            node_id=node_id,
            grant_id=grant_id,
            expected_version=expected_version,
        )
    )
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _task_bind_approval(
    settings: Settings,
    *,
    task_id: str,
    node_id: str,
    grant_id: str,
    expected_version: int,
) -> int:
    components = None
    try:
        components = await build_runtime(settings)
        if components.tasks is None or components.memory_host_id is None:
            raise TaskStateError("task scheduler is unavailable")
        record = await components.tasks.bind_approval(
            host_id=components.memory_host_id,
            task_id=task_id,
            node_id=node_id,
            grant_id=grant_id,
            expected_version=expected_version,
        )
    except Exception as exc:
        console.print(f"[bold red]Approval binding denied.[/] {type(exc).__name__}")
        return 1
    finally:
        if components is not None:
            await components.close()
    console.print(
        f"[bold green]Exact grant bound[/] {record.graph.id}:{node_id} · v{record.version}"
    )
    return 0


@task_app.command("reconcile")
def task_reconcile(
    task_id: Annotated[str, typer.Argument(help="Exact task ID.")],
    node_id: Annotated[str, typer.Argument(help="Exact uncertain node ID.")],
) -> None:
    """Run handler-specific read-only reconciliation; never replay an effect blindly."""
    settings = _load_settings()
    exit_code = asyncio.run(_task_reconcile(settings, task_id=task_id, node_id=node_id))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _task_reconcile(settings: Settings, *, task_id: str, node_id: str) -> int:
    components = None
    try:
        components = await build_runtime(settings)
        if components.tasks is None or components.memory_host_id is None:
            raise TaskStateError("task scheduler is unavailable")
        record = await components.tasks.reconcile(
            host_id=components.memory_host_id, task_id=task_id, node_id=node_id
        )
    except Exception as exc:
        console.print(f"[bold red]Reconciliation incomplete.[/] {type(exc).__name__}")
        return 1
    finally:
        if components is not None:
            await components.close()
    _render_task(record)
    return 0 if record.status is TaskStatus.COMPLETED else 1


@task_app.command("events")
def task_events(
    task_id: Annotated[str, typer.Argument(help="Exact task ID.")],
    limit: Annotated[int, typer.Option(min=1, max=2_000)] = 500,
) -> None:
    """Show ordered content-minimized task lifecycle events."""
    settings = _load_settings()
    exit_code = asyncio.run(_task_events(settings, task_id=task_id, limit=limit))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _task_events(settings: Settings, *, task_id: str, limit: int) -> int:
    try:
        async with SQLiteTaskStore(settings.database_path) as store:
            events = await store.list_events(
                host_id=local_memory_host_id(), task_id=task_id, limit=limit
            )
    except TaskNotFoundError:
        console.print("[bold red]Task not found.[/]")
        return 1
    table = Table(title="Task lifecycle audit")
    table.add_column("Seq / time", no_wrap=True)
    table.add_column("Event")
    table.add_column("Task / node")
    table.add_column("Reason")
    for event in events:
        table.add_row(
            f"{event.sequence}\n{event.created_at.isoformat(timespec='seconds')}",
            event.event_type.value,
            f"{event.task_status.value}\n{event.node_id or '-'}:{event.node_status or '-'}",
            event.reason_code or "-",
        )
    console.print(table)
    return 0


@task_app.command("export")
def task_export(path: Annotated[Path, typer.Argument(help="New JSON export path.")]) -> None:
    """Export current host task graphs and content-minimized events without overwrite."""
    settings = _load_settings()
    exit_code = asyncio.run(_task_export(settings, path=path))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _task_export(settings: Settings, *, path: Path) -> int:
    try:
        async with SQLiteTaskStore(settings.database_path) as store:
            receipt = await store.export(host_id=local_memory_host_id(), path=path)
    except FileExistsError:
        console.print("[bold red]Export path already exists; refusing overwrite.[/]")
        return 1
    except Exception:
        console.print("[bold red]Task export failed.[/]")
        return 1
    console.print(
        f"[bold green]Exported[/] {receipt.task_count} tasks · "
        f"{receipt.event_count} events · {receipt.path}"
    )
    return 0


@task_app.command("delete")
def task_delete(
    task_id: Annotated[str, typer.Argument(help="Exact task ID.")],
    confirm_task_id: Annotated[
        str, typer.Option(help="Repeat exact task ID; deletion removes graph, outputs, and events.")
    ],
) -> None:
    """Delete one exact task transitively, leaving only a content-free tombstone."""
    if confirm_task_id != task_id:
        console.print("[bold red]Deletion confirmation does not match.[/]")
        raise typer.Exit(code=2)
    settings = _load_settings()
    exit_code = asyncio.run(_task_delete(settings, task_id=task_id))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _task_delete(settings: Settings, *, task_id: str) -> int:
    try:
        async with SQLiteTaskStore(settings.database_path) as store:
            receipt = await store.delete_task(host_id=local_memory_host_id(), task_id=task_id)
    except TaskNotFoundError:
        console.print("[bold red]Task not found.[/]")
        return 1
    console.print(
        f"[bold green]Deleted[/] {receipt.task_id} · nodes={receipt.deleted_nodes} · "
        f"events={receipt.deleted_events}"
    )
    return 0


def _render_task(record: TaskRecord) -> None:
    graph = record.graph
    runtimes = record.nodes
    console.print(
        f"[bold cyan]{graph.objective}[/]\n"
        f"Task: {graph.id} · status={record.status.value} · version={record.version} · "
        f"plan_sha256={graph.plan_sha256}\n"
        f"Budget: steps={graph.budget.max_steps}, wall={graph.budget.max_wall_seconds}s, "
        f"tokens={graph.budget.max_tokens}, "
        f"provider_requests={graph.budget.max_provider_requests}, "
        f"retries={graph.budget.max_retries}, tools={graph.budget.max_tool_calls}, "
        f"cost=${graph.budget.max_cost_usd:.2f}, concurrency={graph.budget.max_concurrency}"
    )
    table = Table(title="Validated immutable plan", show_lines=True)
    table.add_column("Node")
    table.add_column("Handler / kind")
    table.add_column("Dependencies")
    table.add_column("State / attempts")
    table.add_column("Approval / recovery")
    for node, runtime in zip(graph.nodes, runtimes, strict=True):
        table.add_row(
            node.id,
            f"{node.handler}\n{node.kind.value}",
            ", ".join(node.dependencies) or "-",
            f"{runtime.status.value}\n{runtime.attempts}/{node.retry_limit + 1}",
            (f"grant={node.approval_grant_id or '-'}\nerror={runtime.error_code or '-'}"),
        )
    console.print(table)


@research_app.command("run")
def research_run(
    objective: Annotated[str, typer.Argument(help="Public research objective.")],
    question: Annotated[
        list[str] | None,
        typer.Option("--question", "-q", help="Public search question; repeat as needed."),
    ] = None,
    store: Annotated[
        bool,
        typer.Option("--store", help="Explicitly approve storage of the exact displayed report."),
    ] = False,
    supersedes_report_id: Annotated[
        str | None,
        typer.Option(help="Current stored report replaced only when --store succeeds."),
    ] = None,
    max_sources: Annotated[int, typer.Option(min=1, max=50)] = 5,
    max_fetches: Annotated[int, typer.Option(min=1, max=100)] = 10,
) -> None:
    """Run bounded research; default result is volatile and disappears on exit."""
    settings = _load_settings()
    exit_code = asyncio.run(
        _research_run(
            settings,
            objective=objective,
            questions=tuple(question or (objective,)),
            store=store,
            supersedes_report_id=supersedes_report_id,
            max_sources=max_sources,
            max_fetches=max_fetches,
        )
    )
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _research_run(
    settings: Settings,
    *,
    objective: str,
    questions: tuple[str, ...],
    store: bool,
    supersedes_report_id: str | None,
    max_sources: int = 5,
    max_fetches: int = 10,
) -> int:
    components = None
    try:
        components = await build_runtime(settings)
        if components.research is None or components.memory_host_id is None:
            console.print("[bold red]Research is disabled.[/]")
            return 1
        pending = await components.research.run(
            host_id=components.memory_host_id,
            plan=ResearchPlan(
                objective=objective,
                questions=questions,
                max_sources=max_sources,
                max_fetches=max_fetches,
            ),
        )
        console.print(Text(pending.result.report.answer))
        console.print(
            f"[dim]Report SHA-256: {pending.report_sha256} · "
            f"sources={len(pending.result.report.sources)} · "
            f"claims={len(pending.result.report.claims)}[/]"
        )
        if store:
            receipt = await components.research.approve(
                ResearchStorageApproval(
                    host_id=components.memory_host_id,
                    pending_run_id=pending.id,
                    expected_report_sha256=pending.report_sha256,
                    interface=ResearchInterface.LOCAL_CLI,
                    approved_at=datetime.now(UTC),
                    supersedes_report_id=supersedes_report_id,
                )
            )
            console.print(f"[bold green]Stored approved research[/] {receipt.report_id}")
        else:
            await components.research.deny(
                host_id=components.memory_host_id,
                pending_run_id=pending.id,
                expected_report_sha256=pending.report_sha256,
            )
            console.print("[bold yellow]Not stored.[/] Re-run with --store after review.")
        return 0
    except asyncio.CancelledError:
        raise
    except ResearchOrchestrationError as exc:
        console.print(f"[bold red]Research failed.[/] {exc.code.value}: {exc}")
        for failure in exc.failures:
            console.print(f"[dim]{failure.stage.value}/{failure.code.value}: {failure.target}[/]")
        return 1
    except Exception as exc:
        console.print(f"[bold red]Research failed.[/] {type(exc).__name__}")
        return 1
    finally:
        if components is not None:
            await components.close()


@research_app.command("list")
def research_list(limit: Annotated[int, typer.Option(min=1, max=500)] = 100) -> None:
    """List explicitly approved research reports."""
    settings = _load_settings()
    exit_code = asyncio.run(_research_list(settings, limit=limit))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _research_list(settings: Settings, *, limit: int) -> int:
    async with SQLiteResearchStore(settings.database_path) as store:
        reports = await store.list_reports(host_id=local_memory_host_id(), limit=limit)
    table = Table(title="Approved research reports", show_lines=True)
    table.add_column("ID / state")
    table.add_column("Objective")
    table.add_column("Sources / claims")
    table.add_column("Approved")
    for report in reports:
        table.add_row(
            f"{report.id}\n{report.state.value}",
            report.objective,
            f"{len(report.source_ids)} / {len(report.claim_ids)}",
            f"{report.approved_interface.value}\n{report.approved_at.isoformat()}",
        )
    console.print(table)
    return 0


@research_app.command("show")
def research_show(
    report_id: Annotated[str, typer.Argument(help="Approved report ID.")],
) -> None:
    """Show one approved report with its durable source and claim ledger."""
    settings = _load_settings()
    exit_code = asyncio.run(_research_show(settings, report_id=report_id))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _research_show(settings: Settings, *, report_id: str) -> int:
    async with SQLiteResearchStore(settings.database_path) as store:
        host_id = local_memory_host_id()
        report = await store.get_report(host_id=host_id, report_id=report_id)
        if report is None:
            console.print("[bold red]Research report not found.[/]")
            return 1
        sources = [
            source
            for source_id in report.source_ids
            if (source := await store.get_source(host_id=host_id, source_id=source_id)) is not None
        ]
        claims = [
            claim
            for claim_id in report.claim_ids
            if (claim := await store.get_claim(host_id=host_id, claim_id=claim_id)) is not None
        ]
    console.print(f"[bold]{report.objective}[/]")
    console.print(Text(report.answer))
    console.print(f"[dim]Report {report.id} · state={report.state.value}[/]")
    for source in sources:
        console.print(
            f"[dim][source:{source.id}] {source.title} · {source.url} · "
            f"checked={source.last_checked_at.isoformat()} · state={source.state.value}[/]"
        )
    for claim in claims:
        console.print(f"[dim][claim:{claim.id}] {claim.status.value}: {claim.statement}[/]")
    return 0


@research_app.command("search")
def research_search(
    query: Annotated[str, typer.Argument(help="Search approved source text.")],
    limit: Annotated[int, typer.Option(min=1, max=100)] = 20,
) -> None:
    """Search the approved local research ledger; no network request occurs."""
    settings = _load_settings()
    exit_code = asyncio.run(_research_search(settings, query=query, limit=limit))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _research_search(settings: Settings, *, query: str, limit: int) -> int:
    async with SQLiteResearchStore(settings.database_path) as store:
        sources = await store.search_sources(
            host_id=local_memory_host_id(), text=query, limit=limit
        )
    table = Table(title="Approved research source matches", show_lines=True)
    table.add_column("ID / state")
    table.add_column("Title / topic")
    table.add_column("URL")
    table.add_column("Checked")
    for source in sources:
        table.add_row(
            f"{source.id}\n{source.state.value}",
            f"{source.title}\n{source.topic}",
            source.url,
            source.last_checked_at.isoformat(),
        )
    console.print(table)
    return 0


@research_app.command("export")
def research_export(
    destination: Annotated[Path, typer.Argument(help="New local JSON export path.")],
) -> None:
    """Export this host's approved research without overwriting an existing file."""
    settings = _load_settings()
    exit_code = asyncio.run(_research_export(settings, destination=destination))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _research_export(settings: Settings, *, destination: Path) -> int:
    try:
        async with SQLiteResearchStore(settings.database_path) as store:
            receipt = await store.export_json(
                host_id=local_memory_host_id(), destination=destination
            )
    except FileExistsError:
        console.print("[bold red]Export path already exists; nothing overwritten.[/]")
        return 1
    console.print(
        f"[bold green]Exported research[/] {receipt.path} · {receipt.byte_count} bytes · "
        f"sources={receipt.source_count} · claims={receipt.claim_count}"
    )
    return 0


@research_app.command("delete-source")
def research_delete_source(
    source_id: Annotated[str, typer.Argument(help="Approved source ID; all URL versions delete.")],
    confirm_source_id: Annotated[
        str,
        typer.Option("--confirm", help="Must exactly repeat source ID."),
    ],
) -> None:
    """Delete exact source URL history and dependent reports, claims, citations, and indexes."""
    if confirm_source_id != source_id:
        console.print("[bold red]Deletion confirmation must exactly match source ID.[/]")
        raise typer.Exit(code=2)
    settings = _load_settings()
    exit_code = asyncio.run(_research_delete_source(settings, source_id=source_id))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _research_delete_source(settings: Settings, *, source_id: str) -> int:
    try:
        async with SQLiteResearchStore(settings.database_path) as store:
            receipt = await store.delete_source(host_id=local_memory_host_id(), source_id=source_id)
    except ResearchNotFoundError:
        console.print("[bold red]Research source not found.[/]")
        return 1
    console.print(
        f"[bold green]Deleted research source history[/] {source_id} · "
        f"sources={receipt.source_rows} · claims={receipt.claim_rows} · "
        f"citations={receipt.citation_rows} · indexes={receipt.fts_rows}"
    )
    return 0


@research_app.command("revalidate")
def research_revalidate(
    source_id: Annotated[str, typer.Argument(help="Approved source ID to re-fetch explicitly.")],
) -> None:
    """Revalidate one approved source and stale dependent claims when content changes."""
    settings = _load_settings()
    exit_code = asyncio.run(_research_revalidate(settings, source_id=source_id))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _research_revalidate(settings: Settings, *, source_id: str) -> int:
    components = None
    try:
        components = await build_runtime(settings)
        if components.research is None or components.memory_host_id is None:
            console.print("[bold red]Research is disabled.[/]")
            return 1
        receipt = await components.research.revalidate_source(
            host_id=components.memory_host_id, source_id=source_id
        )
        console.print(
            f"[bold green]Revalidated[/] {receipt.requested_source_id} · "
            f"current={receipt.current_source_id} · changed={receipt.changed} · "
            f"state={receipt.state.value}"
        )
        return 0
    except Exception as exc:
        console.print(f"[bold red]Research revalidation failed.[/] {type(exc).__name__}")
        return 1
    finally:
        if components is not None:
            await components.close()


@research_app.command("questions")
def research_questions(
    limit: Annotated[int, typer.Option(min=1, max=500)] = 100,
) -> None:
    """List open questions from explicitly approved reports."""
    settings = _load_settings()
    exit_code = asyncio.run(_research_questions(settings, limit=limit))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _research_questions(settings: Settings, *, limit: int) -> int:
    async with SQLiteResearchStore(settings.database_path) as store:
        questions = await store.list_unanswered_questions(
            host_id=local_memory_host_id(), limit=limit
        )
    table = Table(title="Open research questions", show_lines=True)
    table.add_column("ID / version")
    table.add_column("Report")
    table.add_column("Question")
    for question in questions:
        table.add_row(f"{question.id}\nv{question.version}", question.report_id, question.question)
    console.print(table)
    return 0


@research_app.command("close-question")
def research_close_question(
    question_id: Annotated[str, typer.Argument(help="Open question ID.")],
    expected_version: Annotated[int, typer.Option(min=1)],
    answer_claim_id: Annotated[
        str | None,
        typer.Option(help="Approved active claim answering this question; omit to dismiss."),
    ] = None,
) -> None:
    """Answer from an approved claim or explicitly dismiss one open question."""
    settings = _load_settings()
    exit_code = asyncio.run(
        _research_close_question(
            settings,
            question_id=question_id,
            expected_version=expected_version,
            answer_claim_id=answer_claim_id,
        )
    )
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _research_close_question(
    settings: Settings,
    *,
    question_id: str,
    expected_version: int,
    answer_claim_id: str | None,
) -> int:
    try:
        async with SQLiteResearchStore(settings.database_path) as store:
            question = await store.update_unanswered_question(
                host_id=local_memory_host_id(),
                question_id=question_id,
                expected_version=expected_version,
                status=(
                    UnansweredQuestionStatus.ANSWERED
                    if answer_claim_id is not None
                    else UnansweredQuestionStatus.DISMISSED
                ),
                answer_claim_id=answer_claim_id,
                interface=ResearchInterface.LOCAL_CLI,
            )
    except Exception as exc:
        console.print(f"[bold red]Question update failed.[/] {type(exc).__name__}")
        return 1
    console.print(f"[bold green]Question {question.status.value}[/] {question.id}")
    return 0


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
            result, streamed = await _stream_cli_turn(
                components.service,
                AssistantRequest(
                    user_input=normalized,
                    conversation_id=conversation_id,
                    metadata={"interface": "cli"},
                    requested_model_role=model_role,
                ),
            )
            _render_result(result, reply_streamed=streamed)
            return 0 if result.status is RuntimeStatus.COMPLETED else 1

        console.print("[bold cyan]JARVIS[/] — type /exit to stop.")
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
            result, streamed = await _stream_cli_turn(
                components.service,
                AssistantRequest(
                    user_input=user_input,
                    conversation_id=active_conversation,
                    metadata={"interface": "cli"},
                    requested_model_role=model_role,
                ),
            )
            _render_result(result, reply_streamed=streamed)
            if result.conversation_id is not None:
                active_conversation = result.conversation_id


async def _stream_cli_turn(
    service: object,
    request: AssistantRequest,
) -> tuple[RuntimeResult, bool]:
    result: RuntimeResult | None = None
    streamed = False
    async for frame in service.stream(request):  # type: ignore[attr-defined]
        if frame.event is not None:
            if (
                frame.event.type is RuntimeEventType.ASSISTANT_DELTA
                and frame.event.content_delta is not None
            ):
                if not streamed:
                    console.print("[bold green]JARVIS>[/] ", end="")
                    streamed = True
                console.print(
                    frame.event.content_delta,
                    end="",
                    markup=False,
                    highlight=False,
                    soft_wrap=True,
                )
        else:
            result = frame.result
    if streamed:
        console.print()
    if result is None:
        raise RuntimeError("JARVIS runtime stream ended without a terminal result")
    return result, streamed


def _render_result(result: RuntimeResult, *, reply_streamed: bool = False) -> None:
    if result.status is RuntimeStatus.COMPLETED:
        if not reply_streamed:
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
    if result.error.approval_id is not None:
        console.print(
            f"[bold yellow]Approval:[/] {result.error.approval_id}\n"
            "[dim]Review only in `uv run jarvis computer approve <approval-id>`.[/]"
        )


@memory_app.command("remember")
def memory_remember(
    category: Annotated[MemoryCategory, typer.Argument(help="Memory category.")],
    content: Annotated[str, typer.Argument(help="Exact content to commit explicitly.")],
    key: Annotated[
        str | None,
        typer.Option(help="Stable key used for contradiction detection, such as profile.name."),
    ] = None,
) -> None:
    """Commit exact host-supplied memory; extraction candidates use separate confirmation."""
    settings = _load_settings()
    exit_code = asyncio.run(_memory_remember(settings, category=category, content=content, key=key))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _memory_remember(
    settings: Settings,
    *,
    category: MemoryCategory,
    content: str,
    key: str | None,
) -> int:
    store = SQLiteMemoryStore(settings.database_path)
    try:
        await store.initialize()
        item = await store.remember(
            host_id=local_memory_host_id(),
            category=category,
            content=content,
            key=key,
            provenance=explicit_provenance(
                source_id=f"cli-remember-{secrets.token_hex(16)}",
                source_label="explicit local CLI memory",
            ),
        )
    except Exception:
        console.print("[bold red]Memory commit failed.[/] No partial memory was committed.")
        return 1
    finally:
        await store.close()
    console.print(
        f"[bold green]Committed[/] {item.id} · {item.category.value} · "
        f"version {item.version} · confidence {item.confidence:.2f}"
    )
    if item.conflict_ids:
        console.print("[bold yellow]Contradiction open:[/] " + ", ".join(item.conflict_ids))
    return 0


@memory_app.command("list")
def memory_list(
    state: Annotated[MemoryState | None, typer.Option(help="Optional lifecycle state.")] = None,
    category: Annotated[MemoryCategory | None, typer.Option(help="Optional category.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=500)] = 100,
) -> None:
    """Inspect memory content, state, confidence, source, lineage, and contradictions."""
    settings = _load_settings()
    exit_code = asyncio.run(_memory_list(settings, state=state, category=category, limit=limit))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _memory_list(
    settings: Settings,
    *,
    state: MemoryState | None,
    category: MemoryCategory | None,
    limit: int,
) -> int:
    if state is MemoryState.DELETED:
        console.print(
            "[bold yellow]Deleted memory retains no content; inspect export tombstones.[/]"
        )
        return 0
    store = SQLiteMemoryStore(settings.database_path)
    try:
        await store.initialize()
        items = await store.list(
            host_id=local_memory_host_id(),
            states=(() if state is None else (state,)),
            categories=(() if category is None else (category,)),
            limit=limit,
        )
    except Exception:
        console.print("[bold red]Memory state is unavailable.[/]")
        return 1
    finally:
        await store.close()
    table = Table(title="Host-isolated durable memory", show_lines=True)
    table.add_column("ID / version", no_wrap=True)
    table.add_column("Category / state")
    table.add_column("Key / confidence")
    table.add_column("Content")
    table.add_column("Source / lineage / conflict")
    for item in items:
        table.add_row(
            f"{item.id}\nv{item.version}",
            f"{item.category.value}\n{item.state.value}",
            f"{item.key or '-'}\n{item.confidence:.2f}\nsha256={item.content_sha256}",
            item.content,
            (
                ", ".join(
                    f"{source.source_type.value}:{source.trust.value}" for source in item.provenance
                )
                + f"\nsupersedes={item.supersedes_id or '-'}"
                + f"\nconflicts={','.join(item.conflict_ids) or '-'}"
            ),
        )
    console.print(table)
    return 0


@memory_app.command("search")
def memory_search(
    query: Annotated[str, typer.Argument(help="Local FTS5 retrieval query.")],
    limit: Annotated[int, typer.Option(min=1, max=50)] = 8,
) -> None:
    """Search committed memory and show exact retrieval reasons."""
    settings = _load_settings()
    exit_code = asyncio.run(_memory_search(settings, query=query, limit=limit))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _memory_search(settings: Settings, *, query: str, limit: int) -> int:
    store = SQLiteMemoryStore(settings.database_path)
    try:
        await store.initialize()
        hits = await store.search(
            MemoryQuery(host_id=local_memory_host_id(), text=query, limit=limit)
        )
    except Exception:
        console.print("[bold red]Memory retrieval failed.[/] No memory context was projected.")
        return 1
    finally:
        await store.close()
    table = Table(title="Memory retrieval explanation", show_lines=True)
    table.add_column("Score", no_wrap=True)
    table.add_column("Memory")
    table.add_column("Content")
    table.add_column("Why retrieved")
    for hit in hits:
        table.add_row(
            f"{hit.score:.3f}",
            f"{hit.item.id}\n{hit.item.category.value}\n{hit.item.key or '-'}",
            hit.item.content,
            hit.reason,
        )
    console.print(table)
    return 0


@memory_app.command("promote")
def memory_promote(
    candidate_id: Annotated[str, typer.Argument(help="Exact candidate ID from memory list.")],
    expected_version: Annotated[
        int, typer.Option(min=1, help="Exact displayed candidate version.")
    ],
    expected_digest: Annotated[
        str,
        typer.Option(help="Exact displayed candidate SHA-256 content digest."),
    ],
) -> None:
    """Promote one unchanged candidate through trusted local confirmation."""
    settings = _load_settings()
    exit_code = asyncio.run(
        _memory_promote(
            settings,
            candidate_id=candidate_id,
            expected_version=expected_version,
            expected_digest=expected_digest,
        )
    )
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _memory_promote(
    settings: Settings,
    *,
    candidate_id: str,
    expected_version: int,
    expected_digest: str,
) -> int:
    from datetime import UTC, datetime

    store = SQLiteMemoryStore(settings.database_path)
    try:
        await store.initialize()
        item = await store.promote(
            MemoryConfirmation(
                host_id=local_memory_host_id(),
                interface=ConfirmationInterface.LOCAL_CLI,
                candidate_id=candidate_id,
                expected_version=expected_version,
                expected_content_sha256=expected_digest,
                confirmed_at=datetime.now(UTC),
            )
        )
    except (MemoryNotFoundError, MemoryStateError, ValueError):
        console.print(
            "[bold red]Candidate confirmation denied.[/] ID, version, or digest is stale."
        )
        return 1
    finally:
        await store.close()
    console.print(f"[bold green]Candidate committed:[/] {item.id} version {item.version}")
    return 0


@memory_app.command("reject")
def memory_reject(
    candidate_id: Annotated[str, typer.Argument(help="Exact candidate ID.")],
    expected_version: Annotated[int, typer.Option(min=1)],
) -> None:
    """Reject one unchanged extraction candidate; it never enters retrieval."""
    settings = _load_settings()
    exit_code = asyncio.run(
        _memory_reject(settings, candidate_id=candidate_id, expected_version=expected_version)
    )
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _memory_reject(settings: Settings, *, candidate_id: str, expected_version: int) -> int:
    store = SQLiteMemoryStore(settings.database_path)
    try:
        await store.initialize()
        item = await store.reject(
            host_id=local_memory_host_id(),
            memory_id=candidate_id,
            expected_version=expected_version,
        )
    except (MemoryNotFoundError, MemoryStateError):
        console.print("[bold red]Candidate rejection denied.[/] ID or version is stale.")
        return 1
    finally:
        await store.close()
    console.print(f"[bold yellow]Candidate rejected:[/] {item.id} version {item.version}")
    return 0


@memory_app.command("correct")
def memory_correct(
    memory_id: Annotated[str, typer.Argument(help="Exact committed memory ID.")],
    expected_version: Annotated[int, typer.Option(min=1)],
    content: Annotated[str, typer.Option(help="Exact corrected content.")],
    key: Annotated[str | None, typer.Option(help="Optional replacement conflict key.")] = None,
) -> None:
    """Supersede an exact committed memory while retaining provenance lineage."""
    settings = _load_settings()
    exit_code = asyncio.run(
        _memory_correct(
            settings,
            memory_id=memory_id,
            expected_version=expected_version,
            content=content,
            key=key,
        )
    )
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _memory_correct(
    settings: Settings,
    *,
    memory_id: str,
    expected_version: int,
    content: str,
    key: str | None,
) -> int:
    store = SQLiteMemoryStore(settings.database_path)
    try:
        await store.initialize()
        item = await store.correct(
            host_id=local_memory_host_id(),
            memory_id=memory_id,
            expected_version=expected_version,
            content=content,
            key=key,
            provenance=explicit_provenance(
                source_id=f"cli-correction-{secrets.token_hex(16)}",
                source_label="explicit local CLI correction",
            ),
        )
    except (MemoryNotFoundError, MemoryStateError, ValueError):
        console.print(
            "[bold red]Memory correction denied.[/] ID/version/state is stale or invalid."
        )
        return 1
    finally:
        await store.close()
    console.print(f"[bold green]Correction committed:[/] {item.id} supersedes {item.supersedes_id}")
    return 0


@memory_app.command("forget")
def memory_forget(
    memory_id: Annotated[str, typer.Argument(help="Exact memory ID to delete transitively.")],
) -> None:
    """Delete content, FTS rows, provenance, conflicts, and sole-source derivations."""
    settings = _load_settings()
    exit_code = asyncio.run(_memory_forget(settings, memory_id=memory_id))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _memory_forget(settings: Settings, *, memory_id: str) -> int:
    store = SQLiteMemoryStore(settings.database_path)
    try:
        await store.initialize()
        receipt = await store.delete(host_id=local_memory_host_id(), memory_id=memory_id)
    except MemoryNotFoundError:
        console.print("[bold red]Memory not found.[/]")
        return 1
    finally:
        await store.close()
    console.print(
        f"[bold green]Deleted transitively:[/] {receipt.canonical_rows} canonical, "
        f"{receipt.fts_rows} FTS, {receipt.provenance_rows} provenance, "
        f"{receipt.derivation_rows} derivation, {receipt.conflict_rows} conflict rows; "
        f"{receipt.tombstones_written} content-free tombstones."
    )
    return 0


@memory_app.command("export")
def memory_export(
    destination: Annotated[
        str,
        typer.Argument(help="New local JSON path; existing files are never overwritten."),
    ],
) -> None:
    """Export all host memory states and content-free tombstones locally."""
    settings = _load_settings()
    exit_code = asyncio.run(_memory_export(settings, destination=Path(destination)))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _memory_export(settings: Settings, *, destination: Path) -> int:
    store = SQLiteMemoryStore(settings.database_path)
    try:
        await store.initialize()
        receipt = await store.export_json(host_id=local_memory_host_id(), destination=destination)
    except (FileExistsError, OSError, ValueError):
        console.print("[bold red]Memory export failed.[/] Destination must be a new local file.")
        return 1
    finally:
        await store.close()
    console.print(
        f"[bold green]Exported[/] {receipt.record_count} records, {receipt.byte_count} bytes "
        f"to {receipt.path}"
    )
    return 0


@memory_app.command("conflicts")
def memory_conflicts(
    limit: Annotated[int, typer.Option(min=1, max=500)] = 100,
) -> None:
    """List open contradictions without silently selecting a winner."""
    settings = _load_settings()
    exit_code = asyncio.run(_memory_conflicts(settings, limit=limit))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _memory_conflicts(settings: Settings, *, limit: int) -> int:
    store = SQLiteMemoryStore(settings.database_path)
    try:
        await store.initialize()
        conflicts = await store.list_conflicts(host_id=local_memory_host_id(), limit=limit)
    except Exception:
        console.print("[bold red]Memory conflicts are unavailable.[/]")
        return 1
    finally:
        await store.close()
    table = Table(title="Memory contradictions")
    table.add_column("Conflict ID")
    table.add_column("State")
    table.add_column("Left / right")
    table.add_column("Winner")
    table.add_column("Reason")
    for conflict in conflicts:
        table.add_row(
            conflict.id,
            conflict.status.value,
            f"{conflict.left_memory_id} / {conflict.right_memory_id}",
            conflict.winner_memory_id or "-",
            conflict.reason_code,
        )
    console.print(table)
    return 0


@memory_app.command("resolve-conflict")
def memory_resolve_conflict(
    conflict_id: Annotated[str, typer.Argument(help="Exact open conflict ID.")],
    winner_memory_id: Annotated[str, typer.Argument(help="Exact left or right memory ID.")],
) -> None:
    """Select one exact contradiction winner; loser becomes corrected, never erased."""
    settings = _load_settings()
    exit_code = asyncio.run(
        _memory_resolve_conflict(
            settings,
            conflict_id=conflict_id,
            winner_memory_id=winner_memory_id,
        )
    )
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _memory_resolve_conflict(
    settings: Settings,
    *,
    conflict_id: str,
    winner_memory_id: str,
) -> int:
    store = SQLiteMemoryStore(settings.database_path)
    try:
        await store.initialize()
        conflict = await store.resolve_conflict(
            host_id=local_memory_host_id(),
            conflict_id=conflict_id,
            winner_memory_id=winner_memory_id,
        )
    except (MemoryNotFoundError, MemoryStateError):
        console.print("[bold red]Conflict resolution denied.[/] Conflict or winner is invalid.")
        return 1
    finally:
        await store.close()
    console.print(
        f"[bold green]Conflict resolved:[/] {conflict.id} winner={conflict.winner_memory_id}"
    )
    return 0


@memory_app.command("retention")
def memory_retention() -> None:
    """Show effective per-category retention rules for this host."""
    settings = _load_settings()
    exit_code = asyncio.run(_memory_retention(settings))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _memory_retention(settings: Settings) -> int:
    store = SQLiteMemoryStore(settings.database_path)
    try:
        await store.initialize()
        rules = await store.get_retention_rules(host_id=local_memory_host_id())
    except Exception:
        console.print("[bold red]Memory retention state is unavailable.[/]")
        return 1
    finally:
        await store.close()
    table = Table(title="Memory retention")
    table.add_column("Category")
    table.add_column("Days")
    for rule in rules:
        table.add_row(rule.category.value, str(rule.retention_days or "indefinite"))
    console.print(table)
    return 0


@memory_app.command("set-retention")
def memory_set_retention(
    category: Annotated[MemoryCategory, typer.Argument()],
    days: Annotated[int, typer.Argument(min=1, max=36_500)],
) -> None:
    """Set bounded retention days and recompute committed record expiries."""
    settings = _load_settings()
    exit_code = asyncio.run(_memory_set_retention(settings, category=category, days=days))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _memory_set_retention(settings: Settings, *, category: MemoryCategory, days: int) -> int:
    store = SQLiteMemoryStore(settings.database_path)
    try:
        await store.initialize()
        rule = await store.set_retention_rule(
            host_id=local_memory_host_id(), category=category, retention_days=days
        )
    except ValueError:
        console.print("[bold red]Invalid retention rule.[/]")
        return 1
    finally:
        await store.close()
    console.print(
        f"[bold green]Retention updated:[/] {rule.category.value}={rule.retention_days} days"
    )
    return 0


@memory_app.command("expire")
def memory_expire() -> None:
    """Apply current retention and remove expired records from FTS/prompt projection."""
    settings = _load_settings()
    exit_code = asyncio.run(_memory_expire(settings))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _memory_expire(settings: Settings) -> int:
    store = SQLiteMemoryStore(settings.database_path)
    try:
        await store.initialize()
        result = await store.expire_due(host_id=local_memory_host_id())
    except Exception:
        console.print("[bold red]Retention evaluation failed.[/] No partial expiry committed.")
        return 1
    finally:
        await store.close()
    console.print(f"[bold green]Expired[/] {len(result.expired_memory_ids)} memory records.")
    return 0


@computer_app.command("status")
def computer_status() -> None:
    """Show both enablement gates and bounded host policy without creating authority."""
    from jarvis.computer.config import ComputerAccessConfigStore

    settings = _load_settings()
    store = ComputerAccessConfigStore(settings.data_dir)
    try:
        policy = store.load()
    except ValueError:
        console.print("[bold red]Computer access policy is invalid.[/]")
        raise typer.Exit(code=1) from None
    table = Table(title="JARVIS controlled computer access")
    table.add_column("Setting")
    table.add_column("Value")
    table.add_row("Master switch", "enabled" if settings.computer_access_enabled else "disabled")
    table.add_row("Policy file", str(store.path))
    table.add_row("Policy switch", "enabled" if policy.enabled else "disabled")
    table.add_row("Policy version", policy.policy_version)
    table.add_row("Maximum permission level", str(int(policy.maximum_permission_level)))
    table.add_row("Controlled root", str(policy.controlled_root))
    table.add_row("Applications / groups", f"{len(policy.applications)} / {len(policy.app_groups)}")
    table.add_row(
        "Browser targets / printers",
        f"{len(policy.browser_targets)} / {len(policy.printers)}",
    )
    console.print(table)
    if settings.computer_access_enabled and policy.enabled:
        console.print("[bold green]Dual enablement active.[/]")
    else:
        console.print("[bold yellow]No computer action authority is exposed.[/]")


@computer_app.command("init")
def computer_init() -> None:
    """Create a disabled policy and dedicated controlled root; never enable actions."""
    from jarvis.computer.config import ComputerAccessConfigStore

    settings = _load_settings()
    store = ComputerAccessConfigStore(settings.data_dir)
    if store.path.exists():
        console.print("[bold red]Computer access policy already exists; refusing overwrite.[/]")
        raise typer.Exit(code=1)
    store.controlled_root.mkdir(parents=True, exist_ok=True)
    store.save(store.default_policy())
    console.print(f"[bold green]Disabled policy created:[/] {store.path}")
    console.print(f"Controlled root: {store.controlled_root}")
    console.print("[dim]Review policy, then use `jarvis computer enable` and master switch.[/]")


@computer_app.command("enable")
def computer_enable() -> None:
    """Enable the reviewed policy file; environment master switch remains separate."""
    from jarvis.computer.config import ComputerAccessConfigStore

    settings = _load_settings()
    store = ComputerAccessConfigStore(settings.data_dir)
    if not store.path.exists():
        console.print(
            "[bold red]Computer access policy is not initialized.[/] "
            "Run `jarvis computer init`, review it, then enable."
        )
        raise typer.Exit(code=1)
    try:
        policy = store.load()
        store.controlled_root.mkdir(parents=True, exist_ok=True)
        store.save(
            policy.model_copy(
                update={
                    "enabled": True,
                    "policy_version": _fresh_computer_policy_version(),
                }
            )
        )
    except (OSError, ValueError):
        console.print("[bold red]Policy could not be enabled safely.[/]")
        raise typer.Exit(code=1) from None
    console.print("[bold green]Policy-file switch enabled.[/]")
    if not settings.computer_access_enabled:
        console.print(
            "[bold yellow]Master switch remains disabled.[/] "
            "Set JARVIS_COMPUTER_ACCESS_ENABLED=true only after review."
        )


@computer_app.command("disable")
def computer_disable() -> None:
    """Disable policy immediately; running brokers recheck this kill switch."""
    from jarvis.computer.config import ComputerAccessConfigStore

    settings = _load_settings()
    store = ComputerAccessConfigStore(settings.data_dir)
    if not store.path.exists():
        console.print("[bold yellow]Computer action policy is already absent and disabled.[/]")
        return
    try:
        policy = store.load()
        store.save(
            policy.model_copy(
                update={
                    "enabled": False,
                    "policy_version": _fresh_computer_policy_version(),
                }
            )
        )
    except (OSError, ValueError):
        console.print("[bold red]Policy could not be disabled safely.[/]")
        raise typer.Exit(code=1) from None
    console.print(
        "[bold yellow]Computer action policy disabled.[/] "
        "Policy epoch rotated; prior grants cannot revive."
    )


@computer_app.command("propose")
def computer_propose(
    action: Annotated[str, typer.Argument(help="Exact registered action ID.")],
    arguments_json: Annotated[
        str,
        typer.Option("--arguments", help="Bounded JSON object matching the action schema."),
    ],
) -> None:
    """Create one exact proposal; this command never approves or executes it."""
    if len(arguments_json.encode("utf-8")) > 100 * 1_024:
        console.print("[bold red]Action arguments exceed the 100 KiB input limit.[/]")
        raise typer.Exit(code=2)
    try:
        raw = json.loads(arguments_json)
    except json.JSONDecodeError:
        console.print("[bold red]Action arguments must be valid JSON.[/]")
        raise typer.Exit(code=2) from None
    if not isinstance(raw, dict):
        console.print("[bold red]Action arguments must be a JSON object.[/]")
        raise typer.Exit(code=2)
    settings = _load_settings()
    exit_code = asyncio.run(_computer_propose(settings, action=action, raw=raw))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _computer_propose(settings: Settings, *, action: str, raw: dict[str, object]) -> int:
    from pydantic import ValidationError

    from jarvis.computer.runtime import build_computer_runtime
    from jarvis.permissions import ActionCoordinatorStatus, ApprovalSource, render_approval_summary

    try:
        components = await build_computer_runtime(settings)
    except Exception:
        console.print(
            "[bold red]Controlled computer runtime is unavailable.[/] Run computer status."
        )
        return 1
    async with components:
        handler = components.registry.action(action)
        if handler is None:
            console.print("[bold red]Unknown registered action ID.[/]")
            return 2
        try:
            arguments = handler.input_model.model_validate(raw)
        except ValidationError:
            console.print("[bold red]Arguments do not match the fixed action schema.[/]")
            return 2
        result = await components.coordinator.propose(
            handler,
            arguments,
            actor=components.actor,
            source=ApprovalSource.LOCAL_CLI,
        )
        if result.status is not ActionCoordinatorStatus.PENDING or result.request is None:
            console.print(f"[bold red]Proposal denied:[/] {result.code or 'denied'}")
            return 1
        console.print(render_approval_summary(result.request))
        console.print(
            f"[bold yellow]Pending only.[/] Review: `uv run jarvis computer approve "
            f"{result.request.approval_id}`"
        )
        return 0


@computer_app.command("pending")
def computer_pending() -> None:
    """List unexpired approval requests; never approve from this viewer."""
    settings = _load_settings()
    exit_code = asyncio.run(_computer_pending(settings))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _computer_pending(settings: Settings) -> int:
    from jarvis.permissions import SQLiteActionStore

    store = SQLiteActionStore(settings.database_path)
    try:
        await store.initialize()
        records = await store.list_pending_approval_requests(limit=100)
    except Exception:
        console.print("[bold red]Approval state is unavailable.[/]")
        return 1
    finally:
        await store.close()
    table = Table(title="Pending exact computer approvals")
    table.add_column("Approval ID")
    table.add_column("Level")
    table.add_column("Action")
    table.add_column("Effect")
    table.add_column("Expires")
    for record in records:
        action = record.request.action
        table.add_row(
            record.request.approval_id,
            str(int(action.permission_level)),
            f"{action.action_id}@{action.action_version}",
            action.human_effect,
            record.request.expires_at.isoformat(),
        )
    console.print(table)
    return 0


@computer_app.command("approve")
def computer_approve(
    approval_id: Annotated[str, typer.Argument(help="Exact pending approval ID.")],
) -> None:
    """Review exact authority in trusted terminal and issue one short one-use grant."""
    settings = _load_settings()
    exit_code = asyncio.run(_computer_approve(settings, approval_id=approval_id))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _computer_approve(settings: Settings, *, approval_id: str) -> int:
    from jarvis.computer.runtime import build_computer_runtime
    from jarvis.permissions import (
        ActionCoordinatorStatus,
        LocalCliApprovalSurface,
        render_approval_summary,
    )

    try:
        components = await build_computer_runtime(settings)
    except Exception:
        console.print(
            "[bold red]Controlled computer runtime is unavailable.[/] Run computer status."
        )
        return 1

    def prompt(request: object, phrase: str) -> bool:
        from jarvis.permissions import ApprovalRequest

        exact = ApprovalRequest.model_validate(request)
        console.print(render_approval_summary(exact))
        console.print("[bold red]This approval can cause the exact effect above.[/]")
        entered = console.input(f"Type [bold]{phrase}[/] to approve, anything else to deny: ")
        return entered == phrase

    async with components:
        surface = LocalCliApprovalSurface(approver=components.actor, prompt=prompt)
        result = await components.coordinator.review(approval_id, surface)
        if result.status is not ActionCoordinatorStatus.APPROVED or result.grant_id is None:
            console.print(f"[bold yellow]Not approved:[/] {result.code or 'denied'}")
            return 1
        console.print(f"[bold green]One-use grant issued:[/] {result.grant_id}")
        console.print(f"Execute before expiry: `uv run jarvis computer execute {result.grant_id}`")
        return 0


@computer_app.command("execute")
def computer_execute(
    grant_id: Annotated[str, typer.Argument(help="Exact active one-use grant ID.")],
) -> None:
    """Execute one approved grant through fixed broker and print verified receipt."""
    settings = _load_settings()
    exit_code = asyncio.run(_computer_execute(settings, grant_id=grant_id))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _computer_execute(settings: Settings, *, grant_id: str) -> int:
    from jarvis.computer.runtime import build_computer_runtime
    from jarvis.permissions import ActionCoordinatorStatus

    try:
        components = await build_computer_runtime(settings)
    except Exception:
        console.print(
            "[bold red]Controlled computer runtime is unavailable.[/] Run computer status."
        )
        return 1
    async with components:
        result = await components.coordinator.execute(grant_id, actor=components.actor)
        if result.status is not ActionCoordinatorStatus.EXECUTED or result.receipt is None:
            console.print(f"[bold red]Execution denied:[/] {result.code or 'denied'}")
            return 1
        receipt = result.receipt
        console.print(
            f"[bold {'green' if receipt.outcome.value == 'succeeded' else 'red'}]"
            f"{receipt.outcome.value}[/] receipt={receipt.receipt_id} "
            f"postcondition={receipt.postcondition.status.value} "
            f"rollback={receipt.rollback.status.value}"
        )
        return 0 if receipt.outcome.value == "succeeded" else 1


@computer_app.command("audit")
def computer_audit(
    limit: Annotated[int, typer.Option(min=1, max=500, help="Maximum recent receipts.")] = 50,
    kind: Annotated[
        str,
        typer.Option(help="Bounded view: all, lifecycle, receipts, or events."),
    ] = "all",
) -> None:
    """View sanitized authority history; private arguments and results are never shown."""
    normalized_kind = kind.strip().casefold()
    if normalized_kind not in {"all", "lifecycle", "receipts", "events"}:
        console.print("[bold red]Audit kind must be all, lifecycle, receipts, or events.[/]")
        raise typer.Exit(code=2)
    settings = _load_settings()
    exit_code = asyncio.run(_computer_audit(settings, limit=limit, kind=normalized_kind))
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _computer_audit(settings: Settings, *, limit: int, kind: str = "all") -> int:
    from jarvis.permissions import SQLiteActionStore

    store = SQLiteActionStore(settings.database_path)
    try:
        await store.initialize()
        lifecycle = (
            await store.list_lifecycle_events(limit=limit) if kind in {"all", "lifecycle"} else ()
        )
        receipts = (
            await store.list_receipt_summaries(limit=limit) if kind in {"all", "receipts"} else ()
        )
        events = (
            await store.list_action_event_summaries(limit=limit)
            if kind in {"all", "events"}
            else ()
        )
    except Exception:
        console.print("[bold red]Action audit state is unavailable.[/]")
        return 1
    finally:
        await store.close()
    if kind in {"all", "lifecycle"}:
        table = Table(title="Sanitized computer authority lifecycle")
        table.add_column("Time")
        table.add_column("Event")
        table.add_column("Action")
        table.add_column("Level / source / risk")
        table.add_column("Outcome / reason")
        table.add_column("Request / approval / grant")
        for lifecycle_event in lifecycle:
            table.add_row(
                lifecycle_event.occurred_at.isoformat(),
                lifecycle_event.type.value,
                f"{lifecycle_event.action_id}@{lifecycle_event.action_version}",
                f"{int(lifecycle_event.permission_level)} / {lifecycle_event.source.value} / "
                f"{lifecycle_event.risk.value}",
                " / ".join(
                    part
                    for part in (
                        (
                            lifecycle_event.outcome.value
                            if lifecycle_event.outcome is not None
                            else None
                        ),
                        lifecycle_event.reason_code,
                    )
                    if part is not None
                )
                or "-",
                f"{lifecycle_event.request_id} / {lifecycle_event.approval_id} / "
                f"{lifecycle_event.grant_id or '-'}",
            )
        console.print(table)

    if kind in {"all", "receipts"}:
        table = Table(title="Sanitized computer action receipts")
        table.add_column("Finished")
        table.add_column("Action")
        table.add_column("Outcome / reason")
        table.add_column("Postcondition")
        table.add_column("Rollback")
        table.add_column("Receipt / request / grant")
        for receipt in receipts:
            table.add_row(
                receipt.finished_at.isoformat(),
                f"{receipt.action_id}@{receipt.action_version}",
                receipt.outcome.value
                + (f" / {receipt.reason_code}" if receipt.reason_code is not None else ""),
                receipt.postcondition_status,
                receipt.rollback_status,
                f"{receipt.receipt_id} / {receipt.request_id} / {receipt.grant_id}",
            )
        console.print(table)
    if kind in {"all", "events"}:
        table = Table(title="Sanitized computer broker events")
        table.add_column("Time")
        table.add_column("Event")
        table.add_column("Action")
        table.add_column("Outcome / reason")
        table.add_column("Request / grant")
        for broker_event in events:
            table.add_row(
                broker_event.occurred_at.isoformat(),
                broker_event.type.value,
                f"{broker_event.action_id}@{broker_event.action_version}",
                " / ".join(
                    part
                    for part in (
                        (broker_event.outcome.value if broker_event.outcome is not None else None),
                        broker_event.reason_code,
                    )
                    if part is not None
                )
                or "-",
                f"{broker_event.request_id} / {broker_event.grant_id}",
            )
        console.print(table)
    return 0


def _load_topology_manifest(path: Path) -> TopologyManifest:
    try:
        payload = path.read_bytes()
        if len(payload) > 1_048_576:
            raise ValueError("manifest exceeds 1 MiB")
        return TopologyManifest.model_validate_json(payload)
    except (OSError, ValueError) as exc:
        raise MigrationError(
            MigrationErrorCode.INVALID_INPUT, "topology manifest is unavailable or invalid"
        ) from exc


def _render_migration_error(exc: MigrationError) -> Never:
    console.print(f"[bold red]Migration blocked.[/] {exc.code.value}: {exc}")
    raise typer.Exit(code=2) from None


@migration_app.command("manifest")
def migration_manifest(
    destination: Annotated[Path, typer.Argument(dir_okay=False, resolve_path=True)],
    profile: Annotated[str, typer.Option("--profile")] = "split",
    server_node_id: Annotated[str, typer.Option("--server-node-id")] = "node:server",
    laptop_node_id: Annotated[str, typer.Option("--laptop-node-id")] = "node:laptop",
    epoch: Annotated[int, typer.Option("--epoch", min=1)] = 2,
    server_capability: Annotated[list[str] | None, typer.Option("--server-capability")] = None,
    laptop_capability: Annotated[list[str] | None, typer.Option("--laptop-capability")] = None,
    offline_capability: Annotated[list[str] | None, typer.Option("--offline-capability")] = None,
) -> None:
    """Create one reviewed, no-overwrite remote topology manifest for rehearsal."""
    from jarvis.remote import TopologyProfile, build_local_only_manifest, build_remote_manifest

    default_server = (
        "core.chat",
        "core.identity",
        "core.memory",
        "core.permissions",
        "core.research",
        "core.tasks",
        "transport.events",
    )
    default_laptop = ("node.computer", "node.vision", "node.voice", "transport.events")
    try:
        selected_profile = TopologyProfile(profile)
        if selected_profile is TopologyProfile.LOCAL_ONLY:
            if server_capability or offline_capability:
                raise ValueError("local-only manifest does not accept server/offline capabilities")
            topology = build_local_only_manifest(
                host_id=local_memory_host_id(),
                node_id=laptop_node_id,
                capabilities=tuple(
                    laptop_capability or sorted(set(default_server).union(default_laptop))
                ),
                epoch=epoch,
            )
        else:
            topology = build_remote_manifest(
                profile=selected_profile,
                host_id=local_memory_host_id(),
                server_node_id=server_node_id,
                laptop_node_id=laptop_node_id,
                server_capabilities=tuple(server_capability or default_server),
                laptop_capabilities=tuple(laptop_capability or default_laptop),
                laptop_offline_capabilities=tuple(offline_capability or ()),
                epoch=epoch,
            )
        if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
            raise ValueError("destination must be new and its parent must exist")
        with destination.open("x", encoding="utf-8") as output:
            output.write(topology.model_dump_json(indent=2) + "\n")
    except (OSError, ValueError) as exc:
        console.print(f"[bold red]Manifest blocked.[/] {exc}")
        raise typer.Exit(code=2) from None
    console.print(
        json.dumps(
            {
                "manifest_path": str(destination),
                "profile": topology.profile.value,
                "epoch": topology.epoch,
                "topology_digest": topology.digest,
                "activates_runtime": False,
            },
            indent=2,
        )
    )


@migration_app.command("backup")
def migration_backup(
    destination: Annotated[Path, typer.Argument(dir_okay=False, resolve_path=True)],
    manifest: Annotated[
        Path,
        typer.Option("--manifest", exists=True, dir_okay=False, readable=True, resolve_path=True),
    ],
    key_file: Annotated[
        Path,
        typer.Option("--key-file", exists=True, dir_okay=False, readable=True, resolve_path=True),
    ],
    key_id: Annotated[str, typer.Option("--key-id")],
    source_owner_node_id: Annotated[str, typer.Option("--source-owner-node-id")],
) -> None:
    """Create an encrypted no-overwrite snapshot of the configured JARVIS database."""
    from jarvis.remote import MigrationError, create_encrypted_backup, read_migration_key

    settings = _load_settings()
    try:
        receipt = create_encrypted_backup(
            settings.database_path,
            destination,
            topology=_load_topology_manifest(manifest),
            source_owner_node_id=source_owner_node_id,
            key=read_migration_key(key_file),
            key_id=key_id,
        )
    except MigrationError as exc:
        _render_migration_error(exc)
    console.print(receipt.model_dump_json(indent=2))


@migration_app.command("restore")
def migration_restore(
    bundle: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, readable=True, resolve_path=True)
    ],
    destination: Annotated[Path, typer.Argument(dir_okay=False, resolve_path=True)],
    manifest: Annotated[
        Path,
        typer.Option("--manifest", exists=True, dir_okay=False, readable=True, resolve_path=True),
    ],
    key_file: Annotated[
        Path,
        typer.Option("--key-file", exists=True, dir_okay=False, readable=True, resolve_path=True),
    ],
    key_id: Annotated[str, typer.Option("--key-id")],
) -> None:
    """Authenticate and restore an encrypted bundle to one new database path."""
    from jarvis.remote import MigrationError, read_migration_key, restore_encrypted_backup

    try:
        receipt = restore_encrypted_backup(
            bundle,
            destination,
            topology=_load_topology_manifest(manifest),
            key=read_migration_key(key_file),
            expected_key_id=key_id,
        )
    except MigrationError as exc:
        _render_migration_error(exc)
    console.print(receipt.model_dump_json(indent=2))


@migration_app.command("shadow")
def migration_shadow(
    source: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, readable=True, resolve_path=True)
    ],
    target: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, readable=True, resolve_path=True)
    ],
) -> None:
    """Compare exact logical schema, migrations, row counts, and table fingerprints."""
    from jarvis.remote import MigrationError, compare_shadow

    try:
        receipt = compare_shadow(source, target)
    except MigrationError as exc:
        _render_migration_error(exc)
    console.print(receipt.model_dump_json(indent=2))


@migration_app.command("cutover")
def migration_cutover(
    source: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, readable=True, resolve_path=True)
    ],
    target: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, readable=True, resolve_path=True)
    ],
    destination: Annotated[Path, typer.Argument(dir_okay=False, resolve_path=True)],
    manifest: Annotated[
        Path,
        typer.Option("--manifest", exists=True, dir_okay=False, readable=True, resolve_path=True),
    ],
    source_owner_node_id: Annotated[str, typer.Option("--source-owner-node-id")],
    accepted_state_sha256: Annotated[str, typer.Option("--accepted-state-sha256")],
) -> None:
    """Create a no-overwrite ownership receipt while both databases reject writers."""
    from jarvis.remote import MigrationError, create_cutover_receipt

    try:
        receipt = create_cutover_receipt(
            source,
            target,
            destination,
            topology=_load_topology_manifest(manifest),
            source_owner_node_id=source_owner_node_id,
            accepted_state_sha256=accepted_state_sha256,
        )
    except MigrationError as exc:
        _render_migration_error(exc)
    console.print(receipt.model_dump_json(indent=2))


@migration_app.command("rollback")
def migration_rollback(
    active: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, readable=True, resolve_path=True)
    ],
    restored_local: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, readable=True, resolve_path=True)
    ],
    destination: Annotated[Path, typer.Argument(dir_okay=False, resolve_path=True)],
    manifest: Annotated[
        Path,
        typer.Option("--manifest", exists=True, dir_okay=False, readable=True, resolve_path=True),
    ],
    previous_receipt: Annotated[
        Path,
        typer.Option(
            "--previous-receipt", exists=True, dir_okay=False, readable=True, resolve_path=True
        ),
    ],
    accepted_state_sha256: Annotated[str, typer.Option("--accepted-state-sha256")],
) -> None:
    """Chain ownership back to one local owner after verified reverse synchronization."""
    from jarvis.remote import MigrationError, create_rollback_receipt

    try:
        receipt = create_rollback_receipt(
            active,
            restored_local,
            destination,
            topology=_load_topology_manifest(manifest),
            previous_receipt=previous_receipt,
            accepted_state_sha256=accepted_state_sha256,
        )
    except MigrationError as exc:
        _render_migration_error(exc)
    console.print(receipt.model_dump_json(indent=2))


@remote_app.command("deployment-plan")
def remote_deployment_plan(
    tailscale_status_json: Annotated[
        Path,
        typer.Option(
            "--tailscale-status-json",
            exists=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="Bounded output from `tailscale status --json`.",
        ),
    ],
    backend_port: Annotated[
        int,
        typer.Option("--backend-port", min=1, max=65535),
    ] = 8765,
) -> None:
    """Derive a sanitized loopback-only Tailscale Serve deployment plan."""
    from jarvis.remote import (
        PrivateDeploymentError,
        build_private_deployment_plan,
        load_tailscale_status,
    )

    try:
        status = load_tailscale_status(tailscale_status_json)
        plan = build_private_deployment_plan(status, backend_port=backend_port)
    except PrivateDeploymentError as exc:
        console.print(f"[bold red]Private deployment blocked.[/] {exc}")
        raise typer.Exit(code=2) from None
    console.print(plan.model_dump_json(indent=2))


@remote_app.command("backup")
def remote_backup(
    destination: Annotated[
        Path,
        typer.Argument(
            dir_okay=False,
            resolve_path=True,
            help="New private path for a consistent full JARVIS SQLite backup.",
        ),
    ],
) -> None:
    """Create and verify a no-overwrite SQLite backup for deployment recovery."""
    settings = _load_settings()
    source_path = settings.database_path.resolve()
    target_path = destination.resolve()
    if not source_path.is_file():
        console.print("[bold red]Backup blocked.[/] JARVIS database is unavailable.")
        raise typer.Exit(code=2)
    if target_path.exists() or target_path.is_symlink():
        console.print("[bold red]Backup blocked.[/] Destination already exists.")
        raise typer.Exit(code=2)
    if not target_path.parent.is_dir():
        console.print("[bold red]Backup blocked.[/] Destination directory does not exist.")
        raise typer.Exit(code=2)
    if target_path == source_path:
        console.print("[bold red]Backup blocked.[/] Destination must differ from live database.")
        raise typer.Exit(code=2)

    created = False
    try:
        with target_path.open("xb"):
            created = True
        source_uri = f"{source_path.as_uri()}?mode=ro"
        with (
            sqlite3.connect(source_uri, uri=True) as source,
            sqlite3.connect(target_path) as target,
        ):
            source.backup(target)
            integrity = target.execute("PRAGMA integrity_check").fetchone()
            if integrity != ("ok",):
                raise sqlite3.DatabaseError("backup integrity check failed")
        with target_path.open("rb") as backup_file:
            digest = hashlib.file_digest(backup_file, "sha256").hexdigest()
    except (OSError, sqlite3.Error) as exc:
        if created:
            target_path.unlink(missing_ok=True)
        console.print(f"[bold red]Backup failed.[/] {type(exc).__name__}")
        raise typer.Exit(code=1) from None

    console.print(
        json.dumps(
            {
                "backup_path": str(target_path),
                "bytes": target_path.stat().st_size,
                "sha256": digest,
                "integrity_check": "ok",
                "contains_private_data": True,
            },
            indent=2,
        ),
        soft_wrap=True,
    )


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


@vision_app.command("status")
def vision_status() -> None:
    """Show both capture gates without opening a source."""
    from jarvis.vision.settings_store import VisionSettingsError, VisionSettingsFile

    settings = _load_settings()
    try:
        control = VisionSettingsFile(settings.vision_settings_path).load_control()
    except VisionSettingsError:
        console.print("[bold red]Vision control settings invalid.[/] Capture fails closed.")
        raise typer.Exit(code=1) from None
    table = Table(title="JARVIS vision capture state")
    table.add_column("Gate")
    table.add_column("State")
    table.add_column("Meaning")
    table.add_row(
        "Host configuration",
        "enabled" if settings.vision_capture_enabled else "disabled",
        "JARVIS_VISION_CAPTURE_ENABLED",
    )
    table.add_row(
        "Software control",
        "enabled" if control.enabled else "disabled",
        "Persistent user kill control",
    )
    table.add_row("Capture", "inactive", "No background listener or persisted active state")
    console.print(table)


@vision_app.command("enable")
def vision_enable() -> None:
    """Enable explicit foreground capture; this never starts a listener."""
    from jarvis.vision.models import CaptureControl
    from jarvis.vision.settings_store import VisionSettingsFile

    settings = _load_settings()
    VisionSettingsFile(settings.vision_settings_path).save_control(
        CaptureControl(enabled=True, updated_at=datetime.now(UTC))
    )
    if settings.vision_capture_enabled:
        console.print(
            "[bold green]Foreground vision capture enabled.[/] "
            "A separate explicit capture command and visible indicator remain required."
        )
    else:
        console.print(
            "[bold yellow]User control enabled, host gate remains disabled.[/] "
            "Set JARVIS_VISION_CAPTURE_ENABLED=true only for an explicit local session."
        )


@vision_app.command("disable")
def vision_disable() -> None:
    """Persist the software kill state; active controllers poll and stop."""
    from jarvis.vision.models import CaptureControl
    from jarvis.vision.settings_store import VisionSettingsFile

    settings = _load_settings()
    VisionSettingsFile(settings.vision_settings_path).save_control(
        CaptureControl(enabled=False, updated_at=datetime.now(UTC))
    )
    console.print("[bold yellow]Vision capture kill switch enabled.[/] No new source may open.")


@vision_app.command("doctor")
def vision_doctor() -> None:
    """Check capture dependencies and privacy gates without reading pixels."""
    from jarvis.vision.diagnostics import run_vision_diagnostics

    report = run_vision_diagnostics(_load_settings())
    _render_diagnostics(report)
    if not report.ok:
        raise typer.Exit(code=1)


@vision_app.command("setup")
def vision_setup() -> None:
    """Download pinned local hand models into private runtime storage."""
    from jarvis.gestures.model_store import VisionModelError, install_vision_models

    settings = _load_settings()
    console.print("Downloading pinned local OpenCV hand models to private runtime storage...")
    try:
        paths = install_vision_models(settings.vision_model_dir)
    except VisionModelError:
        console.print(
            "[bold red]Local vision model setup failed.[/] "
            "Check network, disk space, and model integrity."
        )
        raise typer.Exit(code=1) from None
    console.print(
        "[bold green]Local hand models ready.[/] "
        f"verified={len(paths)} directory={settings.vision_model_dir}"
    )


@vision_app.command("capture")
def vision_capture(
    source: Annotated[str, typer.Option("--source", help="camera or screen")],
    purpose: Annotated[
        str,
        typer.Option(
            "--purpose",
            help="diagnostic, gesture_calibration, gesture_input, or screen_analysis",
        ),
    ] = "diagnostic",
    source_id: Annotated[
        str | None,
        typer.Option("--source-id", help="camera:<index> or screen:desktop"),
    ] = None,
    x: Annotated[int, typer.Option("--x")] = 0,
    y: Annotated[int, typer.Option("--y")] = 0,
    width: Annotated[int, typer.Option("--width")] = 640,
    height: Annotated[int, typer.Option("--height")] = 480,
    fps: Annotated[float, typer.Option("--fps")] = 10,
    exposure: Annotated[
        int | None,
        typer.Option("--exposure", help="Optional DirectShow manual exposure from -13 through 0"),
    ] = None,
    frames: Annotated[int, typer.Option("--frames")] = 1,
    duration_ms: Annotated[int, typer.Option("--duration-ms")] = 1_000,
) -> None:
    """Read and immediately discard one bounded local foreground capture."""
    from jarvis.vision.bootstrap import build_vision_capture
    from jarvis.vision.models import (
        CaptureError,
        CapturePurpose,
        CaptureRegion,
        CaptureRequest,
        CaptureSource,
    )

    settings = _load_settings()
    try:
        selected_source = CaptureSource(source)
        selected_purpose = CapturePurpose(purpose)
        request = CaptureRequest(
            source=selected_source,
            source_id=(
                source_id
                or ("camera:0" if selected_source is CaptureSource.CAMERA else "screen:desktop")
            ),
            purpose=selected_purpose,
            region=CaptureRegion(x=x, y=y, width=width, height=height),
            requested_fps=fps,
            camera_exposure=exposure,
            max_frames=frames,
            max_duration_ms=duration_ms,
        )
    except (ValueError, ValidationError) as exc:
        console.print(f"[bold red]Invalid capture envelope.[/] {exc}")
        raise typer.Exit(code=2) from None

    async def run() -> None:
        components = build_vision_capture(settings)

        async def discard(_frame: object) -> None:
            return None

        try:
            result = await components.controller.run(request, consumer=discard)
        finally:
            await components.close()
        console.print(
            "[bold green]Bounded capture complete.[/] "
            f"frames={result.frames_delivered} bytes={result.bytes_delivered} "
            f"duration_ms={result.duration_ms:.3f} stop={result.stop_reason.value}; "
            "pixels discarded"
        )

    try:
        asyncio.run(run())
    except CaptureError as exc:
        console.print(f"[bold red]Capture blocked.[/] {exc.code.value}: {exc}")
        raise typer.Exit(code=1) from None
    except KeyboardInterrupt:
        console.print("[bold yellow]Capture cancelled; source closed and pixels discarded.[/]")
        raise typer.Exit(code=130) from None


@vision_app.command("gestures")
def vision_gestures(
    source_id: Annotated[str, typer.Option("--source-id")] = "camera:0",
    width: Annotated[int, typer.Option("--width")] = 640,
    height: Annotated[int, typer.Option("--height")] = 480,
    fps: Annotated[float, typer.Option("--fps")] = 10,
    exposure: Annotated[
        int | None,
        typer.Option("--exposure", help="Optional DirectShow manual exposure from -13 through 0"),
    ] = None,
    frames: Annotated[int, typer.Option("--frames")] = 300,
    duration_ms: Annotated[int, typer.Option("--duration-ms")] = 30_000,
) -> None:
    """Run one bounded local detector session; emit gesture names, never actions."""
    from jarvis.gestures.models import LandmarkError
    from jarvis.gestures.opencv_detector import OpenCVDNNHandLandmarkDetector
    from jarvis.gestures.pipeline import GestureFrameProcessor
    from jarvis.gestures.recognizer import TemporalGestureRecognizer
    from jarvis.vision.bootstrap import build_vision_capture
    from jarvis.vision.models import (
        CaptureError,
        CapturePurpose,
        CaptureRegion,
        CaptureRequest,
        CaptureSource,
    )

    settings = _load_settings()
    try:
        request = CaptureRequest(
            source=CaptureSource.CAMERA,
            source_id=source_id,
            purpose=CapturePurpose.GESTURE_INPUT,
            region=CaptureRegion(x=0, y=0, width=width, height=height),
            requested_fps=fps,
            camera_exposure=exposure,
            max_frames=frames,
            max_duration_ms=duration_ms,
        )
    except (ValueError, ValidationError) as exc:
        console.print(f"[bold red]Invalid gesture envelope.[/] {exc}")
        raise typer.Exit(code=2) from None

    async def run() -> None:
        components = build_vision_capture(settings)
        detector = OpenCVDNNHandLandmarkDetector(settings.vision_model_dir)
        event_count = 0

        async def show_event(event: object) -> None:
            nonlocal event_count
            from jarvis.gestures.models import GestureObservation

            if not isinstance(event, GestureObservation):
                raise TypeError("gesture sink received an invalid event")
            event_count += 1
            console.print(
                f"[bold cyan]Gesture:[/] {event.gesture.value} "
                f"confidence={event.confidence:.3f} hand={event.handedness.value}"
            )

        processor = GestureFrameProcessor(
            detector=detector,
            recognizer=TemporalGestureRecognizer(),
            sink=show_event,
        )
        try:
            result = await components.controller.run(request, consumer=processor)
        finally:
            await processor.close()
            await components.close()
        console.print(
            "[bold green]Bounded local gesture session complete.[/] "
            f"frames={result.frames_delivered} events={event_count} "
            f"duration_ms={result.duration_ms:.3f}; pixels and landmarks discarded; "
            "no action proposed or executed"
        )

    try:
        asyncio.run(run())
    except (CaptureError, LandmarkError) as exc:
        code = getattr(exc, "code", "failed")
        value = getattr(code, "value", str(code))
        console.print(f"[bold red]Gesture session blocked.[/] {value}: {exc}")
        raise typer.Exit(code=1) from None
    except KeyboardInterrupt:
        console.print(
            "[bold yellow]Gesture session cancelled; camera closed and buffers cleared.[/]"
        )
        raise typer.Exit(code=130) from None


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


@voice_app.command("enable")
def voice_enable() -> None:
    """Enable explicit push-to-talk capture; continuous listening stays disabled."""
    from datetime import UTC, datetime

    from jarvis.voice.models import VoiceControl
    from jarvis.voice.settings_store import VoiceSettingsFile

    settings = _load_settings()
    store = VoiceSettingsFile(settings.voice_settings_path)
    store.save_control(VoiceControl(enabled=True, updated_at=datetime.now(UTC)))
    console.print(
        "[bold green]Explicit push-to-talk enabled.[/] "
        "Wake-word and clap always-listening remain disabled."
    )


@voice_app.command("disable")
def voice_disable() -> None:
    """Enforce the software microphone kill switch for current/new voice turns."""
    from datetime import UTC, datetime

    from jarvis.voice.models import VoiceControl
    from jarvis.voice.settings_store import VoiceSettingsFile

    settings = _load_settings()
    store = VoiceSettingsFile(settings.voice_settings_path)
    store.save_control(VoiceControl(enabled=False, updated_at=datetime.now(UTC)))
    console.print("[bold yellow]Voice microphone kill switch enabled.[/] Text chat still works.")


@voice_app.command("devices")
def voice_devices() -> None:
    """List stable local capture and render endpoint IDs."""
    from jarvis.voice.audio_io import AudioDependencyError, AudioDeviceError, SoundDeviceAudio

    _load_settings()
    try:
        devices = asyncio.run(SoundDeviceAudio().list_devices())
    except (AudioDependencyError, AudioDeviceError):
        console.print(
            "[bold red]Audio endpoints unavailable.[/] "
            "Run `uv sync --locked --extra voice`, then check Windows microphone permissions."
        )
        raise typer.Exit(code=1) from None
    table = Table(title="JARVIS local audio endpoints")
    table.add_column("Direction", no_wrap=True)
    table.add_column("Default", no_wrap=True)
    table.add_column("Stable ID", no_wrap=True)
    table.add_column("Name")
    table.add_column("Host API")
    table.add_column("Channels", justify="right")
    table.add_column("Rate", justify="right")
    for device in devices:
        table.add_row(
            device.direction.value,
            "yes" if device.is_default else "",
            device.id,
            device.name,
            device.host_api,
            str(device.max_channels),
            str(device.default_sample_rate_hz),
        )
    console.print(table)


@voice_app.command("select")
def voice_select(
    input_device_id: Annotated[
        str | None,
        typer.Option("--input-device-id", help="Stable ID from `jarvis voice devices`."),
    ] = None,
    output_device_id: Annotated[
        str | None,
        typer.Option("--output-device-id", help="Stable ID from `jarvis voice devices`."),
    ] = None,
) -> None:
    """Persist selected endpoints; omitted direction keeps its current selection."""
    from jarvis.voice.audio_io import AudioDependencyError, AudioDeviceError, SoundDeviceAudio
    from jarvis.voice.models import AudioDeviceDirection
    from jarvis.voice.settings_store import VoiceSettingsFile

    if input_device_id is None and output_device_id is None:
        console.print("[bold red]Provide at least one stable device ID.[/]")
        raise typer.Exit(code=2)
    settings = _load_settings()
    store = VoiceSettingsFile(settings.voice_settings_path)
    current = store.load_devices()
    try:
        devices = asyncio.run(SoundDeviceAudio().list_devices())
    except (AudioDependencyError, AudioDeviceError):
        console.print("[bold red]Audio endpoints unavailable.[/]")
        raise typer.Exit(code=1) from None
    requested = (
        (input_device_id, AudioDeviceDirection.INPUT),
        (output_device_id, AudioDeviceDirection.OUTPUT),
    )
    for device_id, direction in requested:
        if device_id is None:
            continue
        if not any(item.id == device_id and item.direction is direction for item in devices):
            console.print(f"[bold red]Unknown {direction.value} stable device ID.[/]")
            raise typer.Exit(code=2)
    store.save_devices(
        current.model_copy(
            update={
                "input_device_id": input_device_id or current.input_device_id,
                "output_device_id": output_device_id or current.output_device_id,
            }
        )
    )
    console.print("[bold green]Voice endpoint selection saved.[/]")


@voice_app.command("setup")
def voice_setup() -> None:
    """Download configured public local speech models into private runtime storage."""
    from jarvis.voice.diagnostics import download_stt_model

    settings = _load_settings()
    console.print(
        f"Downloading local voice models (STT [bold]{settings.voice_stt_model}[/]) "
        "to private runtime storage..."
    )
    try:
        path = asyncio.run(download_stt_model(settings))
    except Exception:
        console.print(
            "[bold red]Local voice setup failed.[/] Check network, disk space, and voice extra."
        )
        raise typer.Exit(code=1) from None
    console.print(f"[bold green]Local voice models ready.[/] Model cache: {path}")


@voice_app.command("doctor")
def voice_doctor() -> None:
    """Validate local speech dependencies, devices, models, and privacy defaults."""
    from jarvis.voice.diagnostics import run_voice_diagnostics

    settings = _load_settings()
    report = asyncio.run(run_voice_diagnostics(settings))
    _render_diagnostics(report)
    if not report.ok:
        raise typer.Exit(code=1)


@voice_app.command("push-to-talk")
def voice_push_to_talk(
    conversation_id: Annotated[
        str | None,
        typer.Option("--conversation-id", "-c", help="Resume a saved conversation."),
    ] = None,
) -> None:
    """Capture one local speech turn; press Enter again to stop capture."""
    settings = _load_settings()
    console.input("[bold cyan]Press Enter to start local push-to-talk.[/]")
    try:
        exit_code = asyncio.run(_voice_push_to_talk(settings, conversation_id=conversation_id))
    except KeyboardInterrupt:
        console.print("\n[dim]Voice turn cancelled; text chat remains available.[/]")
        exit_code = 130
    if exit_code:
        raise typer.Exit(code=exit_code)


async def _voice_push_to_talk(settings: Settings, *, conversation_id: str | None) -> int:
    import msvcrt

    from jarvis.voice.bootstrap import build_voice_runtime
    from jarvis.voice.models import TranscriptKind, VoiceEvent, VoiceEventType

    def show_event(event: VoiceEvent) -> None:
        if event.type is VoiceEventType.LISTENING_VISIBLE:
            console.print(f"[bold red]MIC ON[/] — {event.detail}")
        elif (
            event.type is VoiceEventType.TRANSCRIPT
            and event.transcript is not None
            and event.transcript.kind is TranscriptKind.FINAL
        ):
            console.print(f"[bold cyan]You>[/] {event.transcript.text}")
        elif event.type is VoiceEventType.KILL_SWITCH:
            console.print("[bold yellow]Voice kill switch enforced.[/]")

    try:
        components = await build_voice_runtime(settings, event_sink=show_event)
    except Exception:
        console.print(
            "[bold red]Voice runtime could not initialize.[/] "
            "Run `uv run jarvis voice doctor`; text chat remains available."
        )
        return 1
    async with components:
        stop = asyncio.Event()

        console.print("[dim]Warming local VAD and STT models...[/]")
        try:
            await asyncio.gather(components.vad.health_check(), components.stt.health_check())
        except Exception:
            console.print(
                "[bold red]Local speech model warm-up failed.[/] "
                "Run `uv run jarvis voice setup`; text chat remains available."
            )
            return 1

        async def stop_on_enter() -> None:
            while not stop.is_set():
                if msvcrt.kbhit() and msvcrt.getwch() in {"\r", "\n"}:
                    stop.set()
                    return
                await asyncio.sleep(0.02)

        console.print(
            f"[bold red]MIC ON[/] — speak now; press Enter to stop "
            f"(maximum {settings.voice_max_capture_seconds}s)."
        )
        key_task = asyncio.create_task(stop_on_enter())
        try:
            result = await components.controller.run_push_to_talk(
                stop_capture=stop,
                conversation_id=conversation_id,
            )
        finally:
            stop.set()
            key_task.cancel()
            with suppress(asyncio.CancelledError):
                await key_task
        if result.assistant_result is not None:
            _render_result(result.assistant_result)
        if result.failure is not None:
            console.print(
                f"[bold red]Voice {result.failure.code.value}:[/] {result.failure.message}\n"
                "[dim]Text fallback: `uv run jarvis chat`.[/]"
            )
            return 1
        if result.interrupted:
            console.print("[dim]Speech output interrupted; conversation state preserved.[/]")
        return 0
