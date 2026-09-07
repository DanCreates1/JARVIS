"""Transactional host-isolated persistence for Phase 6 task graphs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from uuid import uuid4

import aiosqlite
from pydantic import ValidationError

from jarvis.memory.sqlite_store import SQLiteConversationStore

from .models import (
    NodeStatus,
    TaskDeletionReceipt,
    TaskEvent,
    TaskEventType,
    TaskExportReceipt,
    TaskGraph,
    TaskNodeRuntime,
    TaskRecord,
    TaskStatus,
)

_DEFAULT_BUSY_TIMEOUT_MS: Final = 5_000


class TaskStoreError(RuntimeError):
    pass


class TaskNotFoundError(TaskStoreError):
    pass


class TaskStateError(TaskStoreError):
    pass


class TaskConflictError(TaskStoreError):
    pass


class TaskCorruptionError(TaskStoreError):
    pass


class SQLiteTaskStore:
    def __init__(self, database_path: str | Path, *, busy_timeout_ms: int = 5_000) -> None:
        if busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")
        self._database_path = Path(database_path)
        self._busy_timeout_ms = busy_timeout_ms
        self._connection: aiosqlite.Connection | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._operation_lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._lifecycle_lock:
            if self._connection is not None:
                return
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = await aiosqlite.connect(self._database_path)
            connection.row_factory = aiosqlite.Row
            try:
                await connection.execute("PRAGMA foreign_keys = ON")
                await connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms:d}")
                await connection.execute("PRAGMA journal_mode = WAL")
                await connection.execute("PRAGMA synchronous = NORMAL")
                await SQLiteConversationStore._apply_migrations(connection)
                async with connection.execute("PRAGMA quick_check") as cursor:
                    row = await cursor.fetchone()
                if row is None or row[0] != "ok":
                    raise TaskCorruptionError("SQLite quick_check failed")
            except BaseException:
                await connection.close()
                raise
            self._connection = connection

    async def close(self) -> None:
        async with self._operation_lock, self._lifecycle_lock:
            connection = self._connection
            self._connection = None
            if connection is not None:
                await connection.close()

    async def __aenter__(self) -> SQLiteTaskStore:
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self.close()

    async def create_task(self, graph: TaskGraph, *, now: datetime | None = None) -> TaskRecord:
        timestamp = _aware(now or graph.created_at)
        record = TaskRecord(
            graph=graph,
            nodes=tuple(TaskNodeRuntime(node_id=node.id) for node in graph.nodes),
            updated_at=timestamp,
        )
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await connection.execute(
                    """
                    INSERT INTO planning_tasks
                        (id, host_id, owner, status, plan_sha256, record_json, version,
                         deadline_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        graph.id,
                        graph.host_id,
                        graph.owner,
                        record.status.value,
                        graph.plan_sha256,
                        record.model_dump_json(),
                        record.version,
                        graph.deadline_at.isoformat(timespec="microseconds"),
                        graph.created_at.isoformat(timespec="microseconds"),
                        timestamp.isoformat(timespec="microseconds"),
                    ),
                )
                await self._append_event(
                    connection,
                    record,
                    TaskEventType.TASK_CREATED,
                    created_at=timestamp,
                )
                await connection.commit()
            except aiosqlite.IntegrityError as exc:
                await connection.rollback()
                raise TaskConflictError("task ID already exists") from exc
            except BaseException:
                await connection.rollback()
                raise
        return record

    async def get_task(self, *, host_id: str, task_id: str) -> TaskRecord | None:
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                "SELECT record_json FROM planning_tasks WHERE host_id = ? AND id = ?",
                (host_id, task_id),
            ) as cursor:
                row = await cursor.fetchone()
        return None if row is None else _record(row["record_json"])

    async def require_task(self, *, host_id: str, task_id: str) -> TaskRecord:
        record = await self.get_task(host_id=host_id, task_id=task_id)
        if record is None:
            raise TaskNotFoundError("task not found")
        return record

    async def list_tasks(
        self,
        *,
        host_id: str,
        status: TaskStatus | None = None,
        limit: int = 100,
    ) -> Sequence[TaskRecord]:
        if not 1 <= limit <= 500:
            raise ValueError("task limit must be between 1 and 500")
        sql = "SELECT record_json FROM planning_tasks WHERE host_id = ?"
        parameters: list[object] = [host_id]
        if status is not None:
            sql += " AND status = ?"
            parameters.append(status.value)
        sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        parameters.append(limit)
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(sql, parameters) as cursor:
                rows = await cursor.fetchall()
        return tuple(_record(row["record_json"]) for row in rows)

    async def save(
        self,
        record: TaskRecord,
        *,
        expected_version: int,
        event_type: TaskEventType,
        node_id: str | None = None,
        reason_code: str | None = None,
        checkpoint_phase: str | None = None,
        now: datetime | None = None,
    ) -> TaskRecord:
        timestamp = _aware(now or datetime.now(UTC))
        updated = record.model_copy(
            update={"version": expected_version + 1, "updated_at": timestamp}
        )
        updated = TaskRecord.model_validate(updated.model_dump())
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                cursor = await connection.execute(
                    """
                    UPDATE planning_tasks
                    SET status = ?, record_json = ?, version = ?, updated_at = ?
                    WHERE id = ? AND host_id = ? AND version = ?
                    """,
                    (
                        updated.status.value,
                        updated.model_dump_json(),
                        updated.version,
                        timestamp.isoformat(timespec="microseconds"),
                        updated.graph.id,
                        updated.graph.host_id,
                        expected_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise TaskConflictError("task changed or belongs to another host")
                await self._append_event(
                    connection,
                    updated,
                    event_type,
                    node_id=node_id,
                    reason_code=reason_code,
                    created_at=timestamp,
                )
                if checkpoint_phase is not None:
                    await self._append_checkpoint(
                        connection,
                        updated,
                        phase=checkpoint_phase,
                        node_id=node_id,
                        created_at=timestamp,
                    )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        return updated

    async def bind_approval(
        self,
        *,
        host_id: str,
        task_id: str,
        node_id: str,
        grant_id: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> TaskRecord:
        timestamp = _aware(now or datetime.now(UTC))
        record = await self.require_task(host_id=host_id, task_id=task_id)
        if record.version != expected_version:
            raise TaskConflictError("task changed before approval binding")
        graph_nodes = list(record.graph.nodes)
        try:
            index = next(i for i, node in enumerate(graph_nodes) if node.id == node_id)
        except StopIteration:
            raise TaskNotFoundError("task node not found") from None
        node = graph_nodes[index]
        if node.kind.value != "effect":
            raise TaskStateError("only effect nodes can bind approval grants")
        if node.approval_grant_id is not None:
            raise TaskStateError("task node already has an approval grant")
        graph_nodes[index] = node.model_copy(update={"approval_grant_id": grant_id})
        graph = record.graph.model_copy(update={"nodes": tuple(graph_nodes)})
        runtimes = list(record.nodes)
        runtime = runtimes[index]
        if runtime.status not in {
            NodeStatus.PROPOSED,
            NodeStatus.READY,
            NodeStatus.WAITING_APPROVAL,
        }:
            raise TaskStateError("task node cannot accept approval in its current state")
        runtimes[index] = runtime.model_copy(update={"status": NodeStatus.READY})
        updated = TaskRecord.model_validate(
            record.model_copy(
                update={
                    "graph": graph,
                    "nodes": tuple(runtimes),
                    "status": TaskStatus.READY,
                    "version": expected_version + 1,
                    "updated_at": timestamp,
                }
            ).model_dump()
        )
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                await connection.execute(
                    """
                    INSERT INTO planning_approval_bindings (grant_id, task_id, node_id, bound_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (grant_id, task_id, node_id, timestamp.isoformat(timespec="microseconds")),
                )
                cursor = await connection.execute(
                    """
                    UPDATE planning_tasks
                    SET status = ?, record_json = ?, version = ?, updated_at = ?
                    WHERE id = ? AND host_id = ? AND version = ?
                    """,
                    (
                        updated.status.value,
                        updated.model_dump_json(),
                        updated.version,
                        timestamp.isoformat(timespec="microseconds"),
                        task_id,
                        host_id,
                        expected_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise TaskConflictError("task changed before approval binding")
                await self._append_event(
                    connection,
                    updated,
                    TaskEventType.NODE_APPROVAL_BOUND,
                    node_id=node_id,
                    created_at=timestamp,
                )
                await connection.commit()
            except aiosqlite.IntegrityError as exc:
                await connection.rollback()
                raise TaskConflictError("approval grant is already bound") from exc
            except BaseException:
                await connection.rollback()
                raise
        return updated

    async def list_events(
        self, *, host_id: str, task_id: str, limit: int = 500
    ) -> Sequence[TaskEvent]:
        if not 1 <= limit <= 2_000:
            raise ValueError("event limit must be between 1 and 2000")
        if await self.get_task(host_id=host_id, task_id=task_id) is None:
            raise TaskNotFoundError("task not found")
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """
                SELECT * FROM planning_events
                WHERE host_id = ? AND task_id = ?
                ORDER BY sequence ASC LIMIT ?
                """,
                (host_id, task_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        return tuple(
            TaskEvent(
                sequence=row["sequence"],
                id=row["id"],
                task_id=row["task_id"],
                host_id=row["host_id"],
                node_id=row["node_id"],
                event_type=row["event_type"],
                task_status=row["task_status"],
                node_status=row["node_status"],
                reason_code=row["reason_code"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        )

    async def delete_task(
        self, *, host_id: str, task_id: str, now: datetime | None = None
    ) -> TaskDeletionReceipt:
        timestamp = _aware(now or datetime.now(UTC))
        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                row = await _fetchone(
                    connection,
                    "SELECT record_json FROM planning_tasks WHERE host_id = ? AND id = ?",
                    (host_id, task_id),
                )
                if row is None:
                    raise TaskNotFoundError("task not found")
                record = _record(row["record_json"])
                count_row = await _fetchone(
                    connection,
                    "SELECT COUNT(*) AS count FROM planning_events WHERE task_id = ?",
                    (task_id,),
                )
                deleted_events = int(count_row["count"]) if count_row is not None else 0
                await connection.execute(
                    "DELETE FROM planning_events WHERE task_id = ?", (task_id,)
                )
                await connection.execute("DELETE FROM planning_tasks WHERE id = ?", (task_id,))
                await connection.execute(
                    """
                    INSERT INTO planning_tombstones
                        (task_id, host_id, deleted_nodes, deleted_events, deleted_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        host_id,
                        len(record.graph.nodes),
                        deleted_events,
                        timestamp.isoformat(timespec="microseconds"),
                    ),
                )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise
        return TaskDeletionReceipt(
            task_id=task_id,
            deleted_nodes=len(record.graph.nodes),
            deleted_events=deleted_events,
            deleted_at=timestamp,
        )

    async def export(
        self, *, host_id: str, path: str | Path, now: datetime | None = None
    ) -> TaskExportReceipt:
        timestamp = _aware(now or datetime.now(UTC))
        tasks = await self.list_tasks(host_id=host_id, limit=500)
        events: list[TaskEvent] = []
        for task in tasks:
            events.extend(
                await self.list_events(host_id=host_id, task_id=task.graph.id, limit=2_000)
            )
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "jarvis.phase6.tasks.v1",
            "exported_at": timestamp.isoformat(timespec="microseconds"),
            "tasks": [task.model_dump(mode="json") for task in tasks],
            "events": [event.model_dump(mode="json") for event in events],
        }
        await asyncio.to_thread(_write_exclusive_json, output_path, payload)
        return TaskExportReceipt(
            path=str(output_path),
            task_count=len(tasks),
            event_count=len(events),
            exported_at=timestamp,
        )

    async def _append_event(
        self,
        connection: aiosqlite.Connection,
        record: TaskRecord,
        event_type: TaskEventType,
        *,
        node_id: str | None = None,
        reason_code: str | None = None,
        created_at: datetime,
    ) -> None:
        node_status = None
        if node_id is not None:
            node_status = next(
                node.status.value for node in record.nodes if node.node_id == node_id
            )
        await connection.execute(
            """
            INSERT INTO planning_events
                (id, task_id, host_id, node_id, event_type, task_status, node_status,
                 reason_code, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                record.graph.id,
                record.graph.host_id,
                node_id,
                event_type.value,
                record.status.value,
                node_status,
                reason_code,
                created_at.isoformat(timespec="microseconds"),
            ),
        )

    async def _append_checkpoint(
        self,
        connection: aiosqlite.Connection,
        record: TaskRecord,
        *,
        phase: str,
        node_id: str | None,
        created_at: datetime,
    ) -> None:
        state = {
            "task_status": record.status.value,
            "node_states": {node.node_id: node.status.value for node in record.nodes},
            "attempts": {node.node_id: node.attempts for node in record.nodes},
            "usage": record.usage.model_dump(mode="json"),
            "version": record.version,
        }
        await connection.execute(
            """
            INSERT INTO planning_checkpoints
                (id, task_id, host_id, node_id, phase, state_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                record.graph.id,
                record.graph.host_id,
                node_id,
                phase,
                json.dumps(state, separators=(",", ":"), sort_keys=True),
                created_at.isoformat(timespec="microseconds"),
            ),
        )

    async def _get_connection(self) -> aiosqlite.Connection:
        await self.initialize()
        if self._connection is None:
            raise RuntimeError("SQLite task store is not initialized")
        return self._connection


def _record(value: str) -> TaskRecord:
    try:
        return TaskRecord.model_validate_json(value)
    except ValidationError as exc:
        raise TaskCorruptionError("stored task failed typed validation") from exc


async def _fetchone(
    connection: aiosqlite.Connection, sql: str, parameters: Sequence[object]
) -> aiosqlite.Row | None:
    async with connection.execute(sql, parameters) as cursor:
        return await cursor.fetchone()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("task store timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _write_exclusive_json(path: Path, payload: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
