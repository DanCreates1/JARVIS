"""Explicit bounded background evaluation reusing the existing suggestion runner.

No detach, service, startup registration, source acquisition, task handoff or sender.
Only trusted local CLI composition creates this process; runtime startup never does.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from .policy import HostProactivityPolicy
from .runner import ForegroundProactivityRunner
from .runner_store import SQLiteProactivityRunnerStore
from .sqlite_store import SQLiteProactivityStore
from .worker_models import WorkerDeniedError, utc_now
from .worker_store import SQLiteProactivityWorkerStore

PolicySupplier = Callable[[], tuple[HostProactivityPolicy, bool]]


@dataclass(frozen=True, slots=True)
class WorkerResult:
    ticks: int
    candidates: int
    inbox_items: int
    reason: str


class BoundedProactivityWorker:
    def __init__(
        self,
        database_path: str | Path,
        *,
        host_id: str,
        policy_supplier: PolicySupplier,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        self._path = Path(database_path)
        self._host_id = host_id
        self._policy_supplier = policy_supplier
        self._stop = stop_event or asyncio.Event()

    async def run(self) -> WorkerResult:
        ticks = candidates = notices = 0
        reason = "expired"
        async with (
            SQLiteProactivityWorkerStore(self._path, busy_timeout_ms=1_000) as control,
            SQLiteProactivityStore(self._path, busy_timeout_ms=1_000) as rules,
            SQLiteProactivityRunnerStore(self._path, busy_timeout_ms=1_000) as inbox,
        ):
            plan, permit = await control.claim(host_id=self._host_id)
            try:
                started_wall = utc_now()
                if not plan.created_at <= started_wall < plan.expires_at:
                    raise WorkerDeniedError("worker clock moved outside consent")
                started_monotonic = time.monotonic()
                deadline = started_monotonic + min(
                    3_600, max(0, (plan.expires_at - started_wall).total_seconds())
                )
                while not self._stop.is_set() and time.monotonic() < deadline:
                    drift = (utc_now() - started_wall).total_seconds() - (
                        time.monotonic() - started_monotonic
                    )
                    if abs(drift) > 5:
                        raise WorkerDeniedError("worker clock changed")
                    policy, enabled = self._policy_supplier()
                    plan.validate_policy(policy, runner_enabled=enabled)
                    async with asyncio.timeout(min(5.0, max(0, deadline - time.monotonic()))):
                        await control.reserve_tick(permit, plan)
                        runner = ForegroundProactivityRunner(
                            policy_store=rules,
                            runner_store=inbox,
                            task_store=None,
                            policy=policy,
                            runner_enabled=enabled,
                            task_handoff_enabled=False,
                        )
                        result = await runner.tick(
                            host_id=self._host_id,
                            runner_id="bounded-background",
                            worker_permit=permit,
                        )
                    ticks += 1
                    candidates += result.candidates_created
                    notices += result.notifications_ready
                    # No catch-up burst. Recheck stop/revocation/config at most one second apart.
                    next_tick = time.monotonic() + plan.poll_seconds
                    while not self._stop.is_set() and time.monotonic() < min(next_tick, deadline):
                        await control.check(permit)
                        current_policy, current_enabled = self._policy_supplier()
                        plan.validate_policy(current_policy, runner_enabled=current_enabled)
                        with suppress(TimeoutError):
                            await asyncio.wait_for(
                                self._stop.wait(),
                                timeout=min(
                                    1.0, max(0, min(next_tick, deadline) - time.monotonic())
                                ),
                            )
                if self._stop.is_set():
                    reason = "stopped"
            except WorkerDeniedError:
                reason = "revoked_or_budget_exhausted"
            except TimeoutError:
                reason = "tick_timeout"
            finally:
                await control.release(permit)
        return WorkerResult(ticks, candidates, notices, reason)
