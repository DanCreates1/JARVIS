from __future__ import annotations

import asyncio
import json
import shutil
from datetime import UTC, datetime, timedelta

import aiosqlite
import pytest

from jarvis.planning import (
    SQLiteTaskStore,
    TaskConflictError,
    TaskEventType,
    TaskHandlerRegistry,
    TaskNodeKind,
    TaskNodeProposal,
    TaskNotFoundError,
    TaskPlanProposal,
    TaskPlanValidator,
    TaskProvenance,
    TaskRetryMode,
    TaskStateError,
    TaskStatus,
    ValueTaskHandler,
)

NOW = datetime(2026, 9, 7, 12, tzinfo=UTC)


def graph(task_id: str = "task-a", host_id: str = "host-a"):
    proposal = TaskPlanProposal(
        objective="persist a graph",
        owner="owner-a",
        provenance=TaskProvenance(source_type="test", source_id="store-fixture"),
        deadline_at=NOW + timedelta(minutes=2),
        nodes=(TaskNodeProposal(id="first", handler="task.value", arguments={"value": 1}),),
    )
    return TaskPlanValidator(
        TaskHandlerRegistry((ValueTaskHandler(),)), clock=lambda: NOW
    ).validate(proposal, host_id=host_id, task_id=task_id)


@pytest.mark.asyncio
async def test_store_persists_host_isolated_graph_events_and_versions(tmp_path) -> None:
    async with SQLiteTaskStore(tmp_path / "task.db") as store:
        created = await store.create_task(graph())
        assert created.version == 1
        assert await store.get_task(host_id="host-b", task_id="task-a") is None
        updated = created.model_copy(update={"status": TaskStatus.RUNNING})
        saved = await store.save(
            updated,
            expected_version=1,
            event_type=TaskEventType.TASK_STARTED,
            now=NOW + timedelta(seconds=1),
        )
        assert saved.version == 2
        assert len(await store.list_events(host_id="host-a", task_id="task-a")) == 2
        with pytest.raises(TaskConflictError):
            await store.save(
                updated,
                expected_version=1,
                event_type=TaskEventType.TASK_STARTED,
                now=NOW + timedelta(seconds=2),
            )
        with pytest.raises(TaskNotFoundError):
            await store.list_events(host_id="host-b", task_id="task-a")


@pytest.mark.asyncio
async def test_store_binding_is_exact_unique_export_is_exclusive_and_delete_is_transitive(
    tmp_path,
) -> None:
    # Use a typed effect graph by adapting the resolved node for this persistence-only fixture.
    value_graph = graph()
    effect = value_graph.nodes[0].model_copy(
        update={
            "kind": TaskNodeKind.EFFECT,
            "retry_mode": TaskRetryMode.RECONCILE_FIRST,
            "idempotency_key": "effect-key",
        }
    )
    effect_graph = value_graph.model_copy(update={"nodes": (effect,)})
    export_path = tmp_path / "tasks.json"
    database = tmp_path / "task.db"
    async with SQLiteTaskStore(database) as store:
        created = await store.create_task(effect_graph)
        bound = await store.bind_approval(
            host_id="host-a",
            task_id="task-a",
            node_id="first",
            grant_id="grant-a",
            expected_version=created.version,
            now=NOW + timedelta(seconds=1),
        )
        assert bound.graph.nodes[0].approval_grant_id == "grant-a"
        with pytest.raises(TaskStateError):
            await store.bind_approval(
                host_id="host-a",
                task_id="task-a",
                node_id="first",
                grant_id="grant-b",
                expected_version=bound.version,
            )
        receipt = await store.export(host_id="host-a", path=export_path, now=NOW)
        assert receipt.task_count == 1
        assert json.loads(export_path.read_text(encoding="utf-8"))["schema"].endswith("v1")
        with pytest.raises(FileExistsError):
            await store.export(host_id="host-a", path=export_path, now=NOW)
        deletion = await store.delete_task(host_id="host-a", task_id="task-a", now=NOW)
        assert deletion.deleted_nodes == 1
        assert await store.get_task(host_id="host-a", task_id="task-a") is None
    async with aiosqlite.connect(database) as connection:
        for table in (
            "planning_tasks",
            "planning_events",
            "planning_checkpoints",
            "planning_approval_bindings",
        ):
            async with connection.execute(f"SELECT COUNT(*) FROM {table}") as cursor:
                assert (await cursor.fetchone())[0] == 0
        async with connection.execute("SELECT * FROM planning_tombstones") as cursor:
            tombstone = await cursor.fetchone()
        assert tombstone is not None
        assert len(tombstone) == 5


@pytest.mark.asyncio
async def test_store_rejects_corrupt_record(tmp_path) -> None:
    database = tmp_path / "task.db"
    async with SQLiteTaskStore(database) as store:
        await store.create_task(graph())
    async with aiosqlite.connect(database) as connection:
        await connection.execute(
            "UPDATE planning_tasks SET record_json = ? WHERE id = ?",
            ('{"bad":true}', "task-a"),
        )
        await connection.commit()
    async with SQLiteTaskStore(database) as store:
        with pytest.raises(RuntimeError, match="typed validation"):
            await store.get_task(host_id="host-a", task_id="task-a")


@pytest.mark.asyncio
async def test_store_database_backup_restores_task_graph_and_events(tmp_path) -> None:
    database = tmp_path / "task.db"
    backup = tmp_path / "task-backup.db"
    async with SQLiteTaskStore(database) as store:
        await store.create_task(graph())
    shutil.copy2(database, backup)

    async with SQLiteTaskStore(backup) as restored:
        record = await restored.require_task(host_id="host-a", task_id="task-a")
        events = await restored.list_events(host_id="host-a", task_id="task-a")

    assert record.graph.plan_sha256 == graph().plan_sha256
    assert [event.event_type for event in events] == [TaskEventType.TASK_CREATED]


@pytest.mark.asyncio
async def test_independent_store_connections_serialize_concurrent_creates(tmp_path) -> None:
    database = tmp_path / "task.db"
    first = SQLiteTaskStore(database)
    second = SQLiteTaskStore(database)
    await first.initialize()
    await second.initialize()
    try:
        created = await asyncio.gather(
            first.create_task(graph("task-a")),
            second.create_task(graph("task-b")),
        )
        listed = await first.list_tasks(host_id="host-a")
    finally:
        await first.close()
        await second.close()

    assert {record.graph.id for record in created} == {"task-a", "task-b"}
    assert {record.graph.id for record in listed} == {"task-a", "task-b"}
