from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from jarvis.planning import (
    NodeStatus,
    SQLiteTaskStore,
    TaskBudget,
    TaskEventType,
    TaskExecutionDisabledError,
    TaskFailureClass,
    TaskHandlerContext,
    TaskHandlerDefinition,
    TaskHandlerError,
    TaskHandlerRegistry,
    TaskHandlerResult,
    TaskNodeKind,
    TaskNodeProposal,
    TaskPlanProposal,
    TaskPlanValidator,
    TaskProvenance,
    TaskRetryMode,
    TaskScheduler,
    TaskStateError,
    TaskStatus,
    TaskUsage,
    ValueTaskHandler,
)

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)


class FixtureHandler:
    def __init__(
        self,
        name: str,
        *,
        kind: TaskNodeKind = TaskNodeKind.READ_ONLY,
        retry_mode: TaskRetryMode = TaskRetryMode.NEVER,
        failures: list[TaskHandlerError] | None = None,
        delay: float = 0,
        verified: bool = True,
        supports_compensation: bool = False,
        reconcile_result: TaskHandlerResult | None = None,
    ) -> None:
        self.definition = TaskHandlerDefinition(
            name=name,
            kind=kind,
            retry_mode=retry_mode,
            max_timeout_seconds=5,
            requires_approval=kind is TaskNodeKind.EFFECT,
            supports_compensation=supports_compensation,
        )
        self.failures = list(failures or ())
        self.delay = delay
        self.verified = verified
        self.reconcile_result = reconcile_result
        self.started = asyncio.Event()
        self.execute_count = 0
        self.compensate_count = 0

    async def validate(self, context: TaskHandlerContext) -> None:
        if context.node.arguments.get("invalid"):
            raise ValueError("invalid")

    async def execute(self, context: TaskHandlerContext) -> TaskHandlerResult:
        self.execute_count += 1
        self.started.set()
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.failures:
            raise self.failures.pop(0)
        return TaskHandlerResult(output={"node": context.node.id})

    async def verify(self, context: TaskHandlerContext, result: TaskHandlerResult) -> bool:
        return self.verified

    async def compensate(
        self, context: TaskHandlerContext, result: TaskHandlerResult | None
    ) -> bool:
        self.compensate_count += 1
        return True

    async def reconcile(self, context: TaskHandlerContext) -> TaskHandlerResult | None:
        return self.reconcile_result


def make_proposal(
    *nodes: TaskNodeProposal,
    budget: TaskBudget | None = None,
    deadline_at: datetime | None = None,
) -> TaskPlanProposal:
    return TaskPlanProposal(
        objective="scheduler fixture",
        owner="owner-a",
        provenance=TaskProvenance(source_type="test", source_id="scheduler"),
        budget=budget or TaskBudget(max_steps=20, max_retries=3, max_tool_calls=20),
        deadline_at=deadline_at or NOW + timedelta(minutes=2),
        nodes=nodes,
    )


async def scheduler(tmp_path, *handlers: FixtureHandler, enabled: bool = True) -> TaskScheduler:
    store = SQLiteTaskStore(tmp_path / "task.db")
    await store.initialize()
    registry = TaskHandlerRegistry((ValueTaskHandler(), *handlers))
    return TaskScheduler(
        store=store,
        registry=registry,
        validator=TaskPlanValidator(
            registry,
            envelope=TaskBudget(
                max_steps=100, max_wall_seconds=600, max_retries=10, max_tool_calls=100
            ),
            clock=lambda: NOW,
        ),
        execution_enabled=enabled,
        clock=lambda: NOW,
    )


@pytest.mark.asyncio
async def test_scheduler_executes_fan_out_and_fan_in_in_dependency_order(tmp_path) -> None:
    service = await scheduler(tmp_path)
    record = await service.submit(
        host_id="host-a",
        task_id="task-a",
        proposal=make_proposal(
            TaskNodeProposal(id="root", handler="task.value", arguments={"value": "root"}),
            TaskNodeProposal(
                id="left", handler="task.value", arguments={"value": "left"}, dependencies=("root",)
            ),
            TaskNodeProposal(
                id="right",
                handler="task.value",
                arguments={"value": "right"},
                dependencies=("root",),
            ),
            TaskNodeProposal(
                id="join",
                handler="task.value",
                arguments={"value": "done"},
                dependencies=("left", "right"),
            ),
        ),
    )
    assert record.status is TaskStatus.PROPOSED
    result = await service.run(host_id="host-a", task_id="task-a")
    assert result.status is TaskStatus.COMPLETED
    assert [node.output for node in result.nodes] == ["root", "left", "right", "done"]
    assert result.usage.steps == 4
    await service.close()


@pytest.mark.asyncio
async def test_scheduler_stops_effect_for_exact_grant_then_executes_once(tmp_path) -> None:
    effect = FixtureHandler("effect.fixture", kind=TaskNodeKind.EFFECT)
    service = await scheduler(tmp_path, effect)
    created = await service.submit(
        host_id="host-a",
        task_id="task-effect",
        proposal=make_proposal(
            TaskNodeProposal(
                id="effect",
                handler="effect.fixture",
                arguments={},
                idempotency_key="exact-effect",
            )
        ),
    )
    waiting = await service.run(host_id="host-a", task_id="task-effect")
    assert waiting.status is TaskStatus.WAITING_APPROVAL
    assert effect.execute_count == 0
    bound = await service.bind_approval(
        host_id="host-a",
        task_id="task-effect",
        node_id="effect",
        grant_id="grant-effect",
        expected_version=waiting.version,
    )
    assert bound.graph.nodes[0].approval_grant_id == "grant-effect"
    completed = await service.run(host_id="host-a", task_id="task-effect")
    assert completed.status is TaskStatus.COMPLETED
    assert effect.execute_count == 1
    replay = await service.run(host_id="host-a", task_id="task-effect")
    assert replay.status is TaskStatus.COMPLETED
    assert effect.execute_count == 1
    assert created.graph.plan_sha256 == completed.graph.plan_sha256
    await service.close()


@pytest.mark.asyncio
async def test_scheduler_retries_only_classified_transient_failure(tmp_path) -> None:
    handler = FixtureHandler(
        "read.retry",
        retry_mode=TaskRetryMode.TRANSIENT,
        failures=[TaskHandlerError("temporary", TaskFailureClass.TRANSIENT)],
    )
    service = await scheduler(tmp_path, handler)
    await service.submit(
        host_id="host-a",
        task_id="task-retry",
        proposal=make_proposal(
            TaskNodeProposal(
                id="retry",
                handler="read.retry",
                arguments={},
                retry_limit=1,
            ),
            budget=TaskBudget(max_steps=2, max_retries=1, max_tool_calls=2),
        ),
    )
    result = await service.run(host_id="host-a", task_id="task-retry")
    assert result.status is TaskStatus.COMPLETED
    assert result.nodes[0].attempts == 2
    assert result.usage.retries == 1
    assert handler.execute_count == 2
    await service.close()


@pytest.mark.asyncio
async def test_dependency_failure_skips_downstream_and_reports_partial(tmp_path) -> None:
    handler = FixtureHandler(
        "read.fail",
        failures=[TaskHandlerError("terminal", TaskFailureClass.TERMINAL)],
    )
    service = await scheduler(tmp_path, handler)
    await service.submit(
        host_id="host-a",
        task_id="task-partial",
        proposal=make_proposal(
            TaskNodeProposal(id="ok", handler="task.value", arguments={"value": 1}),
            TaskNodeProposal(id="bad", handler="read.fail", arguments={}, dependencies=("ok",)),
            TaskNodeProposal(
                id="blocked", handler="task.value", arguments={"value": 2}, dependencies=("bad",)
            ),
        ),
    )
    result = await service.run(host_id="host-a", task_id="task-partial")
    assert result.status is TaskStatus.PARTIAL
    assert [node.status for node in result.nodes] == [
        NodeStatus.COMPLETED,
        NodeStatus.FAILED,
        NodeStatus.SKIPPED,
    ]
    await service.close()


@pytest.mark.asyncio
async def test_effect_timeout_requires_reconciliation_without_duplicate_execution(tmp_path) -> None:
    effect = FixtureHandler(
        "effect.slow",
        kind=TaskNodeKind.EFFECT,
        delay=0.05,
        reconcile_result=TaskHandlerResult(output={"reconciled": True}),
    )
    service = await scheduler(tmp_path, effect)
    await service.submit(
        host_id="host-a",
        task_id="task-uncertain",
        proposal=make_proposal(
            TaskNodeProposal(
                id="effect",
                handler="effect.slow",
                arguments={},
                timeout_seconds=0.01,
                idempotency_key="uncertain-effect",
            )
        ),
    )
    waiting = await service.run(host_id="host-a", task_id="task-uncertain")
    bound = await service.bind_approval(
        host_id="host-a",
        task_id="task-uncertain",
        node_id="effect",
        grant_id="grant-uncertain",
        expected_version=waiting.version,
    )
    result = await service.run(host_id="host-a", task_id="task-uncertain")
    assert result.status is TaskStatus.NEEDS_RECONCILIATION
    assert effect.execute_count == 1
    with pytest.raises(TaskStateError):
        await service.resume(host_id="host-a", task_id="task-uncertain")
    reconciled = await service.reconcile(
        host_id="host-a", task_id="task-uncertain", node_id="effect"
    )
    assert reconciled.status is TaskStatus.COMPLETED
    assert effect.execute_count == 1
    assert bound.version < reconciled.version
    await service.close()


@pytest.mark.asyncio
async def test_compensation_runs_after_failed_effect_verification(tmp_path) -> None:
    effect = FixtureHandler(
        "effect.compensate",
        kind=TaskNodeKind.EFFECT,
        verified=False,
        supports_compensation=True,
    )
    service = await scheduler(tmp_path, effect)
    await service.submit(
        host_id="host-a",
        task_id="task-compensate",
        proposal=make_proposal(
            TaskNodeProposal(
                id="effect",
                handler="effect.compensate",
                arguments={},
                idempotency_key="compensate-effect",
            )
        ),
    )
    waiting = await service.run(host_id="host-a", task_id="task-compensate")
    await service.bind_approval(
        host_id="host-a",
        task_id="task-compensate",
        node_id="effect",
        grant_id="grant-compensate",
        expected_version=waiting.version,
    )
    result = await service.run(host_id="host-a", task_id="task-compensate")
    assert result.status is TaskStatus.FAILED
    assert result.nodes[0].status is NodeStatus.COMPENSATED
    assert effect.compensate_count == 1
    await service.close()


@pytest.mark.asyncio
async def test_cancel_interrupts_read_node_and_preserves_terminal_state(tmp_path) -> None:
    slow = FixtureHandler("read.slow", delay=1)
    service = await scheduler(tmp_path, slow)
    await service.submit(
        host_id="host-a",
        task_id="task-cancel",
        proposal=make_proposal(TaskNodeProposal(id="slow", handler="read.slow", arguments={})),
    )
    running = asyncio.create_task(service.run(host_id="host-a", task_id="task-cancel"))
    await slow.started.wait()
    await service.cancel(host_id="host-a", task_id="task-cancel")
    result = await running
    assert result.status is TaskStatus.CANCELLED
    assert result.nodes[0].status is NodeStatus.CANCELLED
    await service.close()


@pytest.mark.asyncio
async def test_pause_takes_effect_between_nodes_and_resume_completes(tmp_path) -> None:
    slow = FixtureHandler("read.pause", delay=0.03)
    service = await scheduler(tmp_path, slow)
    await service.submit(
        host_id="host-a",
        task_id="task-pause",
        proposal=make_proposal(
            TaskNodeProposal(id="slow", handler="read.pause", arguments={}),
            TaskNodeProposal(
                id="after", handler="task.value", arguments={"value": 2}, dependencies=("slow",)
            ),
        ),
    )
    running = asyncio.create_task(service.run(host_id="host-a", task_id="task-pause"))
    await slow.started.wait()
    await service.pause(host_id="host-a", task_id="task-pause")
    paused = await running
    assert paused.status is TaskStatus.PAUSED
    resumed = await service.resume(host_id="host-a", task_id="task-pause")
    assert resumed.status is TaskStatus.READY
    completed = await service.run(host_id="host-a", task_id="task-pause")
    assert completed.status is TaskStatus.COMPLETED
    await service.close()


@pytest.mark.asyncio
async def test_default_off_execution_and_invalid_arguments_fail_closed(tmp_path) -> None:
    disabled = await scheduler(tmp_path, enabled=False)
    await disabled.submit(
        host_id="host-a",
        task_id="task-disabled",
        proposal=make_proposal(
            TaskNodeProposal(id="value", handler="task.value", arguments={"value": 1})
        ),
    )
    with pytest.raises(TaskExecutionDisabledError):
        await disabled.run(host_id="host-a", task_id="task-disabled")
    with pytest.raises(TaskStateError):
        await disabled.submit(
            host_id="host-a",
            task_id="task-invalid",
            proposal=make_proposal(
                TaskNodeProposal(id="value", handler="task.value", arguments={"wrong": 1})
            ),
        )
    await disabled.close()


@pytest.mark.asyncio
async def test_restart_retries_orphaned_read_only_node_within_declared_budget(tmp_path) -> None:
    handler = FixtureHandler("read.restart", retry_mode=TaskRetryMode.TRANSIENT)
    service = await scheduler(tmp_path, handler)
    created = await service.submit(
        host_id="host-a",
        task_id="task-restart-read",
        proposal=make_proposal(
            TaskNodeProposal(
                id="read",
                handler="read.restart",
                arguments={},
                retry_limit=1,
            ),
            budget=TaskBudget(max_steps=2, max_retries=1, max_tool_calls=2),
        ),
    )
    orphan = created.nodes[0].model_copy(
        update={"status": NodeStatus.RUNNING, "attempts": 1, "started_at": NOW}
    )
    injected = created.model_copy(
        update={
            "status": TaskStatus.RUNNING,
            "nodes": (orphan,),
            "usage": TaskUsage(steps=1, tool_calls=1),
        }
    )
    await service.store.save(
        injected,
        expected_version=created.version,
        event_type=TaskEventType.NODE_STARTED,
        node_id="read",
        now=NOW,
    )
    recovered = await service.run(host_id="host-a", task_id="task-restart-read")
    assert recovered.status is TaskStatus.COMPLETED
    assert recovered.nodes[0].attempts == 2
    assert handler.execute_count == 1
    await service.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "orphan_status", [NodeStatus.RUNNING, NodeStatus.VERIFYING, NodeStatus.COMPENSATING]
)
async def test_restart_never_blindly_replays_orphaned_effect(tmp_path, orphan_status) -> None:
    effect = FixtureHandler("effect.restart", kind=TaskNodeKind.EFFECT)
    service = await scheduler(tmp_path, effect)
    created = await service.submit(
        host_id="host-a",
        task_id=f"task-restart-{orphan_status.value}",
        proposal=make_proposal(
            TaskNodeProposal(
                id="effect",
                handler="effect.restart",
                arguments={},
                idempotency_key=f"key-{orphan_status.value}",
            )
        ),
    )
    bound = await service.bind_approval(
        host_id="host-a",
        task_id=created.graph.id,
        node_id="effect",
        grant_id=f"grant-{orphan_status.value}",
        expected_version=created.version,
    )
    orphan = bound.nodes[0].model_copy(
        update={"status": orphan_status, "attempts": 1, "started_at": NOW}
    )
    injected = bound.model_copy(
        update={
            "status": TaskStatus.RUNNING,
            "nodes": (orphan,),
            "usage": TaskUsage(steps=1, tool_calls=1),
        }
    )
    await service.store.save(
        injected,
        expected_version=bound.version,
        event_type=TaskEventType.NODE_STARTED,
        node_id="effect",
        now=NOW,
    )
    recovered = await service.run(host_id="host-a", task_id=created.graph.id)
    assert recovered.status is TaskStatus.NEEDS_RECONCILIATION
    assert recovered.nodes[0].status is NodeStatus.NEEDS_RECONCILIATION
    assert effect.execute_count == 0
    await service.close()


@pytest.mark.asyncio
async def test_expired_wall_budget_stops_without_handler_execution(tmp_path) -> None:
    clock = [NOW]
    handler = FixtureHandler("read.wall")
    store = SQLiteTaskStore(tmp_path / "task.db")
    await store.initialize()
    registry = TaskHandlerRegistry((handler,))
    service = TaskScheduler(
        store=store,
        registry=registry,
        validator=TaskPlanValidator(registry, clock=lambda: clock[0]),
        execution_enabled=True,
        clock=lambda: clock[0],
    )
    await service.submit(
        host_id="host-a",
        task_id="task-wall",
        proposal=make_proposal(
            TaskNodeProposal(id="read", handler="read.wall", arguments={}),
            budget=TaskBudget(max_steps=1, max_wall_seconds=2, max_tool_calls=1),
            deadline_at=NOW + timedelta(seconds=1),
        ),
    )
    clock[0] = NOW + timedelta(seconds=2)
    stopped = await service.run(host_id="host-a", task_id="task-wall")
    assert stopped.status is TaskStatus.FAILED
    assert stopped.nodes[0].error_code == "wall_time_exhausted"
    assert handler.execute_count == 0
    await service.close()
