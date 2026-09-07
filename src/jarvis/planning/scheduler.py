"""Deterministic foreground scheduler for durable bounded task graphs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime

from pydantic import ValidationError

from .contracts import (
    TaskHandlerContext,
    TaskHandlerError,
    TaskHandlerResult,
)
from .models import (
    NodeStatus,
    TaskEventType,
    TaskFailureClass,
    TaskNode,
    TaskNodeKind,
    TaskNodeRuntime,
    TaskPlanProposal,
    TaskRecord,
    TaskRetryMode,
    TaskStatus,
)
from .registry import TaskHandlerRegistry
from .sqlite_store import SQLiteTaskStore, TaskNotFoundError, TaskStateError
from .validator import TaskPlanValidator

_TERMINAL_TASKS = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.PARTIAL, TaskStatus.FAILED, TaskStatus.CANCELLED}
)
_SUCCESS_NODES = frozenset({NodeStatus.COMPLETED})
_FAILED_NODES = frozenset(
    {
        NodeStatus.FAILED,
        NodeStatus.SKIPPED,
        NodeStatus.CANCELLED,
        NodeStatus.COMPENSATED,
    }
)
_TERMINAL_NODES = _SUCCESS_NODES | _FAILED_NODES


class TaskExecutionDisabledError(RuntimeError):
    pass


class TaskScheduler:
    """One explicit scheduler; no recursive delegation or hidden background loop."""

    def __init__(
        self,
        *,
        store: SQLiteTaskStore,
        registry: TaskHandlerRegistry,
        validator: TaskPlanValidator,
        execution_enabled: bool = False,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._validator = validator
        self._execution_enabled = execution_enabled
        self._clock = clock or (lambda: datetime.now(UTC))
        self._locks: dict[str, asyncio.Lock] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._pause_events: dict[str, asyncio.Event] = {}
        self._running: set[str] = set()

    @property
    def store(self) -> SQLiteTaskStore:
        return self._store

    async def close(self) -> None:
        """Close durable state; scheduler never owns hidden background tasks."""
        await self._store.close()

    async def submit(
        self, *, host_id: str, proposal: TaskPlanProposal, task_id: str | None = None
    ) -> TaskRecord:
        graph = self._validator.validate(proposal, host_id=host_id, task_id=task_id)
        draft = TaskRecord(
            graph=graph,
            nodes=tuple(TaskNodeRuntime(node_id=node.id) for node in graph.nodes),
            updated_at=graph.created_at,
        )
        await self._validate_handler_arguments(draft)
        return await self._store.create_task(graph)

    async def run(self, *, host_id: str, task_id: str) -> TaskRecord:
        if not self._execution_enabled:
            raise TaskExecutionDisabledError("task execution is disabled by host configuration")
        lock = self._locks.setdefault(task_id, asyncio.Lock())
        async with lock:
            self._running.add(task_id)
            cancel_event = self._cancel_events.setdefault(task_id, asyncio.Event())
            pause_event = self._pause_events.setdefault(task_id, asyncio.Event())
            try:
                record = await self._store.require_task(host_id=host_id, task_id=task_id)
                record = await self._recover_orphans(record)
                if record.status in _TERMINAL_TASKS:
                    return record
                if record.status is TaskStatus.NEEDS_RECONCILIATION:
                    return record
                if record.pause_requested:
                    return record
                if record.cancel_requested:
                    cancel_event.set()
                record = await self._set_task_started(record)
                while record.status not in _TERMINAL_TASKS | {
                    TaskStatus.WAITING_APPROVAL,
                    TaskStatus.PAUSED,
                    TaskStatus.NEEDS_RECONCILIATION,
                }:
                    if cancel_event.is_set() or record.cancel_requested:
                        record = await self._cancel_remaining(record)
                        break
                    if pause_event.is_set() or record.pause_requested:
                        record = await self._pause_record(record)
                        break
                    if self._now() >= record.graph.deadline_at:
                        record = await self._exhaust_budget(record, "wall_time_exhausted")
                        break
                    record = await self._refresh_node_states(record)
                    ready = [
                        (node, runtime)
                        for node, runtime in zip(record.graph.nodes, record.nodes, strict=True)
                        if runtime.status is NodeStatus.READY
                    ]
                    if not ready:
                        record = await self._finalize(record)
                        break
                    read_batch = [pair for pair in ready if pair[0].kind is TaskNodeKind.READ_ONLY][
                        : record.graph.budget.max_concurrency
                    ]
                    batch = read_batch or [ready[0]]
                    record, started = await self._start_batch(record, batch)
                    if not started:
                        record = await self._exhaust_budget(record, "resource_budget_exhausted")
                        break
                    outcomes = await asyncio.gather(
                        *(
                            self._invoke_node(record, node, runtime, cancel_event)
                            for node, runtime in started
                        )
                    )
                    for node, runtime, outcome in outcomes:
                        record = await self._apply_outcome(record, node, runtime, outcome)
                        if record.status is TaskStatus.NEEDS_RECONCILIATION:
                            break
                    if (
                        cancel_event.is_set()
                        and record.status is not TaskStatus.NEEDS_RECONCILIATION
                    ):
                        record = await self._cancel_remaining(record)
                        break
                    if record.status is not TaskStatus.NEEDS_RECONCILIATION:
                        record = await self._finalize(record, terminal_only=True)
                return record
            finally:
                self._running.discard(task_id)
                if task_id not in self._running:
                    self._cancel_events.pop(task_id, None)
                    self._pause_events.pop(task_id, None)

    async def pause(self, *, host_id: str, task_id: str) -> TaskRecord:
        self._pause_events.setdefault(task_id, asyncio.Event()).set()
        if task_id in self._running:
            return await self._store.require_task(host_id=host_id, task_id=task_id)
        lock = self._locks.setdefault(task_id, asyncio.Lock())
        async with lock:
            return await self._pause_record(
                await self._store.require_task(host_id=host_id, task_id=task_id)
            )

    async def resume(self, *, host_id: str, task_id: str) -> TaskRecord:
        lock = self._locks.setdefault(task_id, asyncio.Lock())
        async with lock:
            record = await self._store.require_task(host_id=host_id, task_id=task_id)
            if record.status is TaskStatus.NEEDS_RECONCILIATION:
                raise TaskStateError("task requires reconciliation before resume")
            if record.status in _TERMINAL_TASKS:
                raise TaskStateError("terminal task cannot resume")
            self._pause_events.pop(task_id, None)
            updated = record.model_copy(
                update={"pause_requested": False, "status": TaskStatus.READY}
            )
            return await self._store.save(
                updated,
                expected_version=record.version,
                event_type=TaskEventType.TASK_RESUMED,
                now=self._now(),
            )

    async def cancel(self, *, host_id: str, task_id: str) -> TaskRecord:
        self._cancel_events.setdefault(task_id, asyncio.Event()).set()
        if task_id in self._running:
            return await self._store.require_task(host_id=host_id, task_id=task_id)
        lock = self._locks.setdefault(task_id, asyncio.Lock())
        async with lock:
            record = await self._store.require_task(host_id=host_id, task_id=task_id)
            if record.status in _TERMINAL_TASKS:
                return record
            requested = record.model_copy(update={"cancel_requested": True})
            record = await self._store.save(
                requested,
                expected_version=record.version,
                event_type=TaskEventType.TASK_CANCEL_REQUESTED,
                now=self._now(),
            )
            return await self._cancel_remaining(record)

    async def bind_approval(
        self,
        *,
        host_id: str,
        task_id: str,
        node_id: str,
        grant_id: str,
        expected_version: int,
    ) -> TaskRecord:
        lock = self._locks.setdefault(task_id, asyncio.Lock())
        async with lock:
            record = await self._store.require_task(host_id=host_id, task_id=task_id)
            if record.version != expected_version:
                raise TaskStateError("task changed before approval binding")
            node, _ = _node_pair(record, node_id)
            bound_node = node.model_copy(update={"approval_grant_id": grant_id})
            graph_nodes = tuple(
                bound_node if item.id == node_id else item for item in record.graph.nodes
            )
            bound_graph = record.graph.model_copy(update={"nodes": graph_nodes})
            candidate = TaskRecord.model_validate(
                record.model_copy(update={"graph": bound_graph}).model_dump()
            )
            try:
                await self._registry.get(node.handler).validate(
                    self._context(candidate, bound_node)
                )
            except Exception as exc:
                raise TaskStateError("approval grant does not match the exact task node") from exc
            return await self._store.bind_approval(
                host_id=host_id,
                task_id=task_id,
                node_id=node_id,
                grant_id=grant_id,
                expected_version=expected_version,
                now=self._now(),
            )

    async def reconcile(self, *, host_id: str, task_id: str, node_id: str) -> TaskRecord:
        if not self._execution_enabled:
            raise TaskExecutionDisabledError("task execution is disabled by host configuration")
        lock = self._locks.setdefault(task_id, asyncio.Lock())
        async with lock:
            record = await self._store.require_task(host_id=host_id, task_id=task_id)
            node, runtime = _node_pair(record, node_id)
            if runtime.status is not NodeStatus.NEEDS_RECONCILIATION:
                raise TaskStateError("node does not require reconciliation")
            context = self._context(record, node)
            handler = self._registry.get(node.handler)
            try:
                result = await asyncio.wait_for(
                    handler.reconcile(context), timeout=node.timeout_seconds
                )
                verified = result is not None and await handler.verify(context, result)
            except Exception:
                result = None
                verified = False
            if not verified:
                return record
            updated_runtime = runtime.model_copy(
                update={
                    "status": NodeStatus.COMPLETED,
                    "output": result.output if result is not None else None,
                    "completed_at": self._now(),
                    "error_code": None,
                    "failure_class": None,
                }
            )
            updated = _replace_runtime(record, updated_runtime).model_copy(
                update={"status": TaskStatus.RUNNING}
            )
            record = await self._store.save(
                updated,
                expected_version=record.version,
                event_type=TaskEventType.ORPHAN_RECOVERED,
                node_id=node_id,
                checkpoint_phase="recovery",
                now=self._now(),
            )
            return await self._finalize(record)

    async def _validate_handler_arguments(self, record: TaskRecord) -> None:
        for node in record.graph.nodes:
            try:
                await self._registry.get(node.handler).validate(self._context(record, node))
            except Exception as exc:
                raise TaskStateError("task handler arguments failed validation") from exc

    async def _set_task_started(self, record: TaskRecord) -> TaskRecord:
        if record.status is TaskStatus.RUNNING:
            return record
        updated = record.model_copy(update={"status": TaskStatus.RUNNING})
        return await self._store.save(
            updated,
            expected_version=record.version,
            event_type=TaskEventType.TASK_STARTED,
            now=self._now(),
        )

    async def _refresh_node_states(self, record: TaskRecord) -> TaskRecord:
        while True:
            states = {runtime.node_id: runtime.status for runtime in record.nodes}
            changed = False
            for node, runtime in zip(record.graph.nodes, record.nodes, strict=True):
                if runtime.status not in {NodeStatus.PROPOSED, NodeStatus.WAITING_APPROVAL}:
                    continue
                dependency_states = [states[dependency] for dependency in node.dependencies]
                if any(state in _FAILED_NODES for state in dependency_states):
                    replacement = runtime.model_copy(
                        update={
                            "status": NodeStatus.SKIPPED,
                            "error_code": "dependency_failed",
                            "failure_class": TaskFailureClass.TERMINAL,
                            "completed_at": self._now(),
                        }
                    )
                    updated = _replace_runtime(record, replacement)
                    record = await self._store.save(
                        updated,
                        expected_version=record.version,
                        event_type=TaskEventType.NODE_SKIPPED,
                        node_id=node.id,
                        reason_code="dependency_failed",
                        now=self._now(),
                    )
                    changed = True
                    break
                if not all(state in _SUCCESS_NODES for state in dependency_states):
                    continue
                if node.kind is TaskNodeKind.EFFECT and node.approval_grant_id is None:
                    if runtime.status is not NodeStatus.WAITING_APPROVAL:
                        replacement = runtime.model_copy(
                            update={"status": NodeStatus.WAITING_APPROVAL}
                        )
                        record = await self._store.save(
                            _replace_runtime(record, replacement),
                            expected_version=record.version,
                            event_type=TaskEventType.NODE_WAITING_APPROVAL,
                            node_id=node.id,
                            reason_code="exact_grant_required",
                            now=self._now(),
                        )
                        changed = True
                        break
                elif runtime.status is not NodeStatus.READY:
                    replacement = runtime.model_copy(update={"status": NodeStatus.READY})
                    record = await self._store.save(
                        _replace_runtime(record, replacement),
                        expected_version=record.version,
                        event_type=TaskEventType.NODE_READY,
                        node_id=node.id,
                        now=self._now(),
                    )
                    changed = True
                    break
            if not changed:
                return record

    async def _start_batch(
        self,
        record: TaskRecord,
        batch: list[tuple[TaskNode, TaskNodeRuntime]],
    ) -> tuple[TaskRecord, list[tuple[TaskNode, TaskNodeRuntime]]]:
        started: list[tuple[TaskNode, TaskNodeRuntime]] = []
        for node, old_runtime in batch:
            retry = old_runtime.attempts > 0
            usage = record.usage.plus(node.charge, retry=retry)
            if not usage.fits(record.graph.budget):
                return record, started
            runtime = old_runtime.model_copy(
                update={
                    "status": NodeStatus.RUNNING,
                    "attempts": old_runtime.attempts + 1,
                    "started_at": self._now(),
                    "completed_at": None,
                    "error_code": None,
                    "failure_class": None,
                }
            )
            updated = _replace_runtime(record, runtime).model_copy(update={"usage": usage})
            record = await self._store.save(
                updated,
                expected_version=record.version,
                event_type=TaskEventType.NODE_STARTED,
                node_id=node.id,
                checkpoint_phase=("before_effect" if node.kind is TaskNodeKind.EFFECT else None),
                now=self._now(),
            )
            started.append((node, runtime))
        return record, started

    async def _invoke_node(
        self,
        record: TaskRecord,
        node: TaskNode,
        runtime: TaskNodeRuntime,
        cancel_event: asyncio.Event,
    ) -> tuple[TaskNode, TaskNodeRuntime, TaskHandlerResult | TaskHandlerError]:
        handler = self._registry.get(node.handler)
        context = self._context(record, node)

        async def invoke() -> TaskHandlerResult:
            await handler.validate(context)
            return TaskHandlerResult.model_validate((await handler.execute(context)).model_dump())

        task = asyncio.create_task(invoke())
        cancelled = asyncio.create_task(cancel_event.wait())
        try:
            done, _ = await asyncio.wait(
                {task, cancelled},
                timeout=node.timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if task in done:
                try:
                    return node, runtime, task.result()
                except TaskHandlerError as exc:
                    return node, runtime, exc
                except (ValidationError, ValueError):
                    return (
                        node,
                        runtime,
                        TaskHandlerError("invalid_handler_result", TaskFailureClass.INVALID_RESULT),
                    )
                except Exception:
                    return (
                        node,
                        runtime,
                        TaskHandlerError("handler_failed", TaskFailureClass.TERMINAL),
                    )
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
            if cancel_event.is_set():
                failure = (
                    TaskFailureClass.UNCERTAIN
                    if node.kind is TaskNodeKind.EFFECT
                    else TaskFailureClass.CANCELLED
                )
                return node, runtime, TaskHandlerError("cancelled", failure)
            failure = (
                TaskFailureClass.UNCERTAIN
                if node.kind is TaskNodeKind.EFFECT
                else TaskFailureClass.TIMEOUT
            )
            return node, runtime, TaskHandlerError("timeout", failure)
        finally:
            cancelled.cancel()

    async def _apply_outcome(
        self,
        record: TaskRecord,
        node: TaskNode,
        runtime: TaskNodeRuntime,
        outcome: TaskHandlerResult | TaskHandlerError,
    ) -> TaskRecord:
        handler = self._registry.get(node.handler)
        context = self._context(record, node)
        current = _runtime(record, node.id)
        if isinstance(outcome, TaskHandlerResult):
            encoded = json.dumps(outcome.model_dump(mode="json"), ensure_ascii=False).encode(
                "utf-8"
            )
            if len(encoded) > handler.definition.max_output_bytes:
                outcome = TaskHandlerError(
                    "handler_result_too_large", TaskFailureClass.INVALID_RESULT
                )
            else:
                verifying = current.model_copy(update={"status": NodeStatus.VERIFYING})
                record = await self._store.save(
                    _replace_runtime(record, verifying),
                    expected_version=record.version,
                    event_type=TaskEventType.NODE_VERIFYING,
                    node_id=node.id,
                    now=self._now(),
                )
                try:
                    verified = await asyncio.wait_for(
                        handler.verify(context, outcome), timeout=node.timeout_seconds
                    )
                except Exception:
                    verified = False
                if verified:
                    completed = verifying.model_copy(
                        update={
                            "status": NodeStatus.COMPLETED,
                            "output": outcome.output,
                            "completed_at": self._now(),
                        }
                    )
                    return await self._store.save(
                        _replace_runtime(record, completed),
                        expected_version=record.version,
                        event_type=TaskEventType.NODE_COMPLETED,
                        node_id=node.id,
                        checkpoint_phase=(
                            "after_effect" if node.kind is TaskNodeKind.EFFECT else None
                        ),
                        now=self._now(),
                    )
                outcome = TaskHandlerError(
                    "postcondition_mismatch",
                    TaskFailureClass.INVALID_RESULT,
                    partial_effect=node.kind is TaskNodeKind.EFFECT,
                )
        assert isinstance(outcome, TaskHandlerError)
        if node.kind is TaskNodeKind.EFFECT and outcome.failure_class is TaskFailureClass.UNCERTAIN:
            needs = current.model_copy(
                update={
                    "status": NodeStatus.NEEDS_RECONCILIATION,
                    "error_code": outcome.code,
                    "failure_class": outcome.failure_class,
                }
            )
            updated = _replace_runtime(record, needs).model_copy(
                update={"status": TaskStatus.NEEDS_RECONCILIATION}
            )
            return await self._store.save(
                updated,
                expected_version=record.version,
                event_type=TaskEventType.NODE_RECONCILIATION_REQUIRED,
                node_id=node.id,
                reason_code=outcome.code,
                checkpoint_phase="recovery",
                now=self._now(),
            )
        if outcome.failure_class is TaskFailureClass.CANCELLED:
            cancelled = current.model_copy(
                update={
                    "status": NodeStatus.CANCELLED,
                    "error_code": outcome.code,
                    "failure_class": outcome.failure_class,
                    "completed_at": self._now(),
                }
            )
            return await self._store.save(
                _replace_runtime(record, cancelled),
                expected_version=record.version,
                event_type=TaskEventType.NODE_CANCELLED,
                node_id=node.id,
                reason_code=outcome.code,
                now=self._now(),
            )
        if outcome.partial_effect and handler.definition.supports_compensation:
            compensating = current.model_copy(update={"status": NodeStatus.COMPENSATING})
            record = await self._store.save(
                _replace_runtime(record, compensating),
                expected_version=record.version,
                event_type=TaskEventType.NODE_COMPENSATING,
                node_id=node.id,
                reason_code=outcome.code,
                now=self._now(),
            )
            try:
                compensated = await handler.compensate(context, None)
            except Exception:
                compensated = False
            if compensated:
                terminal = compensating.model_copy(
                    update={
                        "status": NodeStatus.COMPENSATED,
                        "error_code": outcome.code,
                        "failure_class": outcome.failure_class,
                        "completed_at": self._now(),
                    }
                )
                return await self._store.save(
                    _replace_runtime(record, terminal),
                    expected_version=record.version,
                    event_type=TaskEventType.NODE_COMPENSATED,
                    node_id=node.id,
                    reason_code=outcome.code,
                    checkpoint_phase="after_effect",
                    now=self._now(),
                )
        retry_allowed = (
            outcome.failure_class is TaskFailureClass.TRANSIENT
            and node.retry_mode is not TaskRetryMode.NEVER
            and current.attempts <= node.retry_limit
        )
        if retry_allowed:
            retry = current.model_copy(
                update={
                    "status": NodeStatus.READY,
                    "error_code": outcome.code,
                    "failure_class": outcome.failure_class,
                }
            )
            return await self._store.save(
                _replace_runtime(record, retry),
                expected_version=record.version,
                event_type=TaskEventType.NODE_RETRY_SCHEDULED,
                node_id=node.id,
                reason_code=outcome.code,
                now=self._now(),
            )
        failed = current.model_copy(
            update={
                "status": NodeStatus.FAILED,
                "error_code": outcome.code,
                "failure_class": outcome.failure_class,
                "completed_at": self._now(),
            }
        )
        return await self._store.save(
            _replace_runtime(record, failed),
            expected_version=record.version,
            event_type=TaskEventType.NODE_FAILED,
            node_id=node.id,
            reason_code=outcome.code,
            checkpoint_phase=("after_effect" if node.kind is TaskNodeKind.EFFECT else None),
            now=self._now(),
        )

    async def _recover_orphans(self, record: TaskRecord) -> TaskRecord:
        orphan_statuses = {NodeStatus.RUNNING, NodeStatus.VERIFYING, NodeStatus.COMPENSATING}
        for node, runtime in zip(record.graph.nodes, record.nodes, strict=True):
            if runtime.status not in orphan_statuses:
                continue
            if node.kind is TaskNodeKind.EFFECT:
                status = NodeStatus.NEEDS_RECONCILIATION
                task_status = TaskStatus.NEEDS_RECONCILIATION
                event = TaskEventType.NODE_RECONCILIATION_REQUIRED
                reason = "orphaned_effect"
            elif runtime.attempts <= node.retry_limit:
                status = NodeStatus.READY
                task_status = TaskStatus.RUNNING
                event = TaskEventType.ORPHAN_RECOVERED
                reason = "orphaned_read_retry"
            else:
                status = NodeStatus.FAILED
                task_status = TaskStatus.RUNNING
                event = TaskEventType.NODE_FAILED
                reason = "orphaned_read_retry_exhausted"
            replacement = runtime.model_copy(
                update={
                    "status": status,
                    "error_code": reason,
                    "failure_class": (
                        TaskFailureClass.UNCERTAIN
                        if node.kind is TaskNodeKind.EFFECT
                        else TaskFailureClass.TRANSIENT
                    ),
                }
            )
            updated = _replace_runtime(record, replacement).model_copy(
                update={"status": task_status}
            )
            record = await self._store.save(
                updated,
                expected_version=record.version,
                event_type=event,
                node_id=node.id,
                reason_code=reason,
                checkpoint_phase="recovery",
                now=self._now(),
            )
        return record

    async def _pause_record(self, record: TaskRecord) -> TaskRecord:
        if record.status in _TERMINAL_TASKS:
            return record
        updated = record.model_copy(update={"pause_requested": True, "status": TaskStatus.PAUSED})
        return await self._store.save(
            updated,
            expected_version=record.version,
            event_type=TaskEventType.TASK_PAUSED,
            now=self._now(),
        )

    async def _cancel_remaining(self, record: TaskRecord) -> TaskRecord:
        if not record.cancel_requested:
            requested = record.model_copy(update={"cancel_requested": True})
            record = await self._store.save(
                requested,
                expected_version=record.version,
                event_type=TaskEventType.TASK_CANCEL_REQUESTED,
                now=self._now(),
            )
        for runtime in record.nodes:
            if runtime.status in _TERMINAL_NODES:
                continue
            replacement = runtime.model_copy(
                update={
                    "status": NodeStatus.CANCELLED,
                    "error_code": "task_cancelled",
                    "failure_class": TaskFailureClass.CANCELLED,
                    "completed_at": self._now(),
                }
            )
            record = await self._store.save(
                _replace_runtime(record, replacement),
                expected_version=record.version,
                event_type=TaskEventType.NODE_CANCELLED,
                node_id=runtime.node_id,
                reason_code="task_cancelled",
                now=self._now(),
            )
        final_status = (
            TaskStatus.PARTIAL
            if any(runtime.status is NodeStatus.COMPLETED for runtime in record.nodes)
            else TaskStatus.CANCELLED
        )
        updated = record.model_copy(update={"status": final_status})
        return await self._store.save(
            updated,
            expected_version=record.version,
            event_type=(
                TaskEventType.TASK_PARTIAL
                if final_status is TaskStatus.PARTIAL
                else TaskEventType.TASK_CANCELLED
            ),
            reason_code="task_cancelled",
            now=self._now(),
        )

    async def _exhaust_budget(self, record: TaskRecord, reason: str) -> TaskRecord:
        for runtime in record.nodes:
            if runtime.status in _TERMINAL_NODES:
                continue
            replacement = runtime.model_copy(
                update={
                    "status": NodeStatus.SKIPPED,
                    "error_code": reason,
                    "failure_class": TaskFailureClass.CAPACITY,
                    "completed_at": self._now(),
                }
            )
            record = await self._store.save(
                _replace_runtime(record, replacement),
                expected_version=record.version,
                event_type=TaskEventType.BUDGET_EXHAUSTED,
                node_id=runtime.node_id,
                reason_code=reason,
                now=self._now(),
            )
        return await self._finalize(record)

    async def _finalize(self, record: TaskRecord, *, terminal_only: bool = False) -> TaskRecord:
        statuses = {runtime.status for runtime in record.nodes}
        if NodeStatus.NEEDS_RECONCILIATION in statuses:
            status = TaskStatus.NEEDS_RECONCILIATION
            event = TaskEventType.TASK_RECONCILIATION_REQUIRED
        elif statuses <= _SUCCESS_NODES:
            status = TaskStatus.COMPLETED
            event = TaskEventType.TASK_COMPLETED
        elif statuses & {
            NodeStatus.PROPOSED,
            NodeStatus.READY,
            NodeStatus.RUNNING,
            NodeStatus.VERIFYING,
        }:
            return record
        elif NodeStatus.WAITING_APPROVAL in statuses:
            if terminal_only and statuses & {NodeStatus.READY, NodeStatus.PROPOSED}:
                return record
            status = TaskStatus.WAITING_APPROVAL
            event = TaskEventType.NODE_WAITING_APPROVAL
        elif statuses & _FAILED_NODES:
            status = TaskStatus.PARTIAL if NodeStatus.COMPLETED in statuses else TaskStatus.FAILED
            event = (
                TaskEventType.TASK_PARTIAL
                if status is TaskStatus.PARTIAL
                else TaskEventType.TASK_FAILED
            )
        else:
            return record
        if record.status is status:
            return record
        updated = record.model_copy(update={"status": status})
        return await self._store.save(
            updated,
            expected_version=record.version,
            event_type=event,
            now=self._now(),
        )

    def _context(self, record: TaskRecord, node: TaskNode) -> TaskHandlerContext:
        outputs = {
            dependency: _runtime(record, dependency).output for dependency in node.dependencies
        }
        return TaskHandlerContext(
            task_id=record.graph.id,
            host_id=record.graph.host_id,
            node=node,
            usage=record.usage,
            dependency_outputs=outputs,
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("task scheduler clock must be timezone-aware")
        return value.astimezone(UTC)


def _runtime(record: TaskRecord, node_id: str) -> TaskNodeRuntime:
    try:
        return next(runtime for runtime in record.nodes if runtime.node_id == node_id)
    except StopIteration:
        raise TaskNotFoundError("task node not found") from None


def _node_pair(record: TaskRecord, node_id: str) -> tuple[TaskNode, TaskNodeRuntime]:
    try:
        index = next(i for i, node in enumerate(record.graph.nodes) if node.id == node_id)
    except StopIteration:
        raise TaskNotFoundError("task node not found") from None
    return record.graph.nodes[index], record.nodes[index]


def _replace_runtime(record: TaskRecord, replacement: TaskNodeRuntime) -> TaskRecord:
    nodes = tuple(
        replacement if runtime.node_id == replacement.node_id else runtime
        for runtime in record.nodes
    )
    return TaskRecord.model_validate(record.model_copy(update={"nodes": nodes}).model_dump())
