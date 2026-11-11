"""Real subprocess ownership, control and killed-runner recovery on isolated state."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from jarvis.planning import (
    NodeStatus,
    TaskHandlerResult,
    TaskNodeKind,
    TaskNodeProposal,
    TaskStateError,
    TaskStatus,
)
from tests.integration.test_phase14_workflows import service
from tests.unit.test_phase6_scheduler import FixtureHandler, make_proposal

SOURCE_ROOT = str(Path(__file__).resolve().parents[2] / "src")

CHILD = r"""
import asyncio, sys
from pathlib import Path
from jarvis.planning import *
from tests.integration.test_phase14_workflows import service
from tests.unit.test_phase6_scheduler import FixtureHandler

class Blocking(FixtureHandler):
    async def execute(self, context):
        Path(sys.argv[2]).write_text(context.node.id, encoding="utf-8")
        await asyncio.sleep(30)
        return TaskHandlerResult(output={"node": context.node.id})

async def main():
    handler = Blocking("fixture.block", kind=TaskNodeKind(sys.argv[3]))
    scheduler = await service(Path(sys.argv[1]), handler)
    try:
        await scheduler.run(host_id="host", task_id="process-task")
    finally:
        await scheduler.close()

asyncio.run(main())
"""


async def start_child(database, marker, kind):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = SOURCE_ROOT
    process = await asyncio.to_thread(
        subprocess.Popen,
        [sys.executable, "-c", CHILD, str(database), str(marker), kind.value],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    for _ in range(500):
        if marker.exists():
            return process
        if process.poll() is not None:
            raise AssertionError(process.communicate()[1].decode(errors="replace"))
        await asyncio.sleep(0.01)
    process.kill()
    process.communicate()
    raise AssertionError("subprocess did not reach dispatch")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [TaskNodeKind.READ_ONLY, TaskNodeKind.EFFECT])
async def test_killed_runner_releases_owner_and_never_replays_effect(tmp_path, kind):
    database, marker = tmp_path / "tasks.db", tmp_path / "dispatch.txt"
    handler = FixtureHandler(
        "fixture.block", kind=kind, reconcile_result=TaskHandlerResult(output={"node": "work"})
    )
    scheduler = await service(database, handler)
    proposal = make_proposal(
        TaskNodeProposal(
            id="work",
            handler="fixture.block",
            timeout_seconds=5,
            idempotency_key="synthetic-effect" if kind == TaskNodeKind.EFFECT else None,
        )
    )
    task = await scheduler.submit(host_id="host", task_id="process-task", proposal=proposal)
    if kind == TaskNodeKind.EFFECT:
        await scheduler.bind_approval(
            host_id="host",
            task_id=task.graph.id,
            node_id="work",
            grant_id="synthetic-grant",
            expected_version=task.version,
        )
    process = await start_child(database, marker, kind)
    try:
        with pytest.raises(TaskStateError, match="active"):
            await scheduler.run(host_id="host", task_id=task.graph.id)
        process.kill()
        await asyncio.to_thread(process.communicate, timeout=5)
        result = await scheduler.run(host_id="host", task_id=task.graph.id)
        assert handler.execute_count == 0
        if kind == TaskNodeKind.EFFECT:
            assert result.status == TaskStatus.NEEDS_RECONCILIATION
            await scheduler.cancel(host_id="host", task_id=task.graph.id)
            assert (
                await scheduler.store.require_task(host_id="host", task_id=task.graph.id)
            ).status == TaskStatus.NEEDS_RECONCILIATION
            result = await scheduler.reconcile(
                host_id="host", task_id=task.graph.id, node_id="work"
            )
            assert result.status == TaskStatus.COMPLETED
            assert marker.read_text(encoding="utf-8") == "work"
        else:
            assert result.status == TaskStatus.FAILED
            assert result.nodes[0].status == NodeStatus.FAILED
    finally:
        if process.poll() is None:
            process.kill()
            await asyncio.to_thread(process.communicate, timeout=5)
        await scheduler.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["pause", "cancel"])
async def test_real_process_receives_durable_control(tmp_path, action):
    database, marker = tmp_path / "tasks.db", tmp_path / "dispatch.txt"
    handler = FixtureHandler("fixture.block")
    scheduler = await service(database, handler)
    await scheduler.submit(
        host_id="host",
        task_id="process-task",
        proposal=make_proposal(
            TaskNodeProposal(id="work", handler="fixture.block", timeout_seconds=0.3),
            TaskNodeProposal(
                id="tail", handler="task.value", arguments={"value": "tail"}, dependencies=("work",)
            ),
        ),
    )
    process = await start_child(database, marker, TaskNodeKind.READ_ONLY)
    try:
        await getattr(scheduler, action)(host_id="host", task_id="process-task")
        await asyncio.to_thread(process.communicate, timeout=5)
        assert process.returncode == 0
        result = await scheduler.store.require_task(host_id="host", task_id="process-task")
        if action == "cancel":
            assert result.status == TaskStatus.CANCELLED
        else:
            # Pause finishes the dispatched node (here, its timeout), then stops before tail.
            assert result.status == TaskStatus.PAUSED
            assert result.nodes[1].attempts == 0
    finally:
        if process.poll() is None:
            process.kill()
            await asyncio.to_thread(process.communicate, timeout=5)
        await scheduler.close()
