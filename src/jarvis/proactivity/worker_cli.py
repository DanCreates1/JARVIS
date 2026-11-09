"""Trusted-local bounded worker controls; never composed by normal Core startup."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from typing import Annotated

import typer

from jarvis.config import Settings
from jarvis.memory import local_memory_host_id

from .policy import HostProactivityPolicy
from .worker import BoundedProactivityWorker
from .worker_models import WorkerDeniedError, WorkerPlan, policy_digest, utc_now
from .worker_store import SQLiteProactivityWorkerStore

app = typer.Typer(help="Explicit local bounded worker review, run, status and stop.")


def _policy(settings: Settings) -> HostProactivityPolicy:
    return HostProactivityPolicy(
        enabled=settings.proactivity_enabled,
        enabled_features=frozenset(settings.proactivity_enabled_features),
        max_candidates_per_hour=settings.proactivity_max_candidates_per_hour,
        max_candidates_per_day=settings.proactivity_max_candidates_per_day,
        max_attention_seconds_per_day=settings.proactivity_max_attention_seconds_per_day,
        max_rule_lifetime_days=settings.proactivity_max_rule_lifetime_days,
        clock_skew_seconds=settings.proactivity_clock_skew_seconds,
        max_task_steps=settings.proactivity_max_task_steps,
        max_provider_requests=settings.proactivity_max_provider_requests,
        max_tool_calls=settings.proactivity_max_tool_calls,
        max_tokens=settings.proactivity_max_tokens,
        max_cost_usd=int(settings.proactivity_max_cost_usd),
        max_concurrency=settings.proactivity_max_concurrency,
    )


def _current_policy() -> tuple[HostProactivityPolicy, bool]:
    settings = Settings()
    return _policy(settings), settings.proactivity_runner_enabled


def _fail() -> None:
    typer.echo("Background operation failed closed. No task or external notification executed.")


@app.command("preview")
def preview(
    output: Annotated[
        Path, typer.Argument(help="New explicit local review file; refuses overwrite.")
    ],
    feature: Annotated[list[str], typer.Option(help="Exact enabled feature; repeat as needed.")],
    seconds: Annotated[int, typer.Option(min=1, max=3_600)] = 300,
    poll_seconds: Annotated[int, typer.Option(min=1, max=60)] = 5,
    max_ticks: Annotated[int, typer.Option(min=1, max=3_600)] = 3_600,
) -> None:
    """Prepare exact bounded consent. Does not enable or start evaluation."""
    try:
        settings = Settings()

        async def prepare() -> WorkerPlan:
            async with SQLiteProactivityWorkerStore(settings.database_path) as store:
                status = await store.status(host_id=local_memory_host_id())
            now = utc_now()
            return WorkerPlan(
                host_id=local_memory_host_id(),
                expected_generation=int(str(status["generation"])),
                policy_sha256=policy_digest(_policy(settings)),
                features=tuple(feature),
                poll_seconds=poll_seconds,
                max_ticks=max_ticks,
                created_at=now,
                expires_at=now + timedelta(seconds=seconds),
            )

        plan = asyncio.run(prepare())
        plan.validate_policy(_policy(settings), runner_enabled=settings.proactivity_runner_enabled)
        with output.open("x", encoding="utf-8") as handle:
            handle.write(plan.model_dump_json(indent=2))
    except Exception:
        _fail()
        raise typer.Exit(1) from None
    typer.echo(
        f"Review SHA-256: {plan.sha256}\nFeatures: {', '.join(plan.features)}\n"
        f"Expires UTC: {plan.expires_at.isoformat()}\nPoll: {plan.poll_seconds}s; "
        f"maximum {plan.max_ticks} ticks; 500 rule scans/tick; 5s tick timeout.\n"
        "Generic local inbox only; tasks/providers/models/effects/external sends=0.\n"
        f"Activation phrase: ENABLE BACKGROUND {plan.sha256[:8]}\nNo worker started."
    )


@app.command("enable")
def enable(
    review: Annotated[Path, typer.Argument(help="Exact previously reviewed local JSON.")],
    expected_digest: Annotated[str, typer.Option(help="Full SHA-256 printed by preview.")],
    confirm: Annotated[str, typer.Option(help="Exact activation phrase from preview.")],
) -> None:
    """Consume a <=5-minute local review; does not launch a process."""
    try:
        with review.open("rb") as handle:
            raw = handle.read(16_385)
        if len(raw) > 16_384:
            raise WorkerDeniedError("worker review too large")
        plan = WorkerPlan.model_validate_json(raw)
        settings = Settings()
        if (
            plan.host_id != local_memory_host_id()
            or expected_digest != plan.sha256
            or confirm != f"ENABLE BACKGROUND {plan.sha256[:8]}"
        ):
            raise WorkerDeniedError("worker confirmation mismatch")
        plan.validate_policy(_policy(settings), runner_enabled=settings.proactivity_runner_enabled)

        async def activate() -> None:
            async with SQLiteProactivityWorkerStore(settings.database_path) as store:
                await store.enable(plan)

        asyncio.run(activate())
    except Exception:
        _fail()
        raise typer.Exit(1) from None
    typer.echo("Bounded background consent recorded. No worker started.")


@app.command("run")
def run() -> None:
    """Run one approved bounded process. Ctrl+C or stop revokes/stops its work."""
    try:
        settings = Settings()
        result = asyncio.run(
            BoundedProactivityWorker(
                settings.database_path,
                host_id=local_memory_host_id(),
                policy_supplier=_current_policy,
            ).run()
        )
    except (Exception, KeyboardInterrupt):
        _fail()
        raise typer.Exit(1) from None
    typer.echo(
        f"Worker stopped: {result.reason}; ticks={result.ticks}; candidates={result.candidates}; "
        f"local_inbox={result.inbox_items}; tasks/providers/effects/external_sends=0."
    )


@app.command("status")
def status() -> None:
    """Show generic consent/lease/budget metadata; no title or notification preview."""
    try:
        settings = Settings()

        async def read() -> dict[str, object]:
            async with SQLiteProactivityWorkerStore(settings.database_path) as store:
                return await store.status(host_id=local_memory_host_id())

        typer.echo(json.dumps(asyncio.run(read()), sort_keys=True))
    except Exception:
        _fail()
        raise typer.Exit(1) from None


@app.command("stop")
def stop() -> None:
    """Persistently revoke consent and old leases; erase the stored plan."""
    try:
        settings = Settings()

        async def revoke() -> None:
            async with SQLiteProactivityWorkerStore(settings.database_path) as store:
                await store.stop(host_id=local_memory_host_id())

        asyncio.run(revoke())
    except Exception:
        _fail()
        raise typer.Exit(1) from None
    typer.echo("Background consent revoked. Old worker leases invalid; stored review removed.")
