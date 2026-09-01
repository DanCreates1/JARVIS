from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from pathlib import Path

import pytest

from jarvis.core import SensitivityClass
from jarvis.memory import (
    ConfirmationInterface,
    MemoryCategory,
    MemoryConfirmation,
    MemoryCorruptionError,
    MemoryNotFoundError,
    MemoryQuery,
    MemoryState,
    MemoryStateError,
    ProvenanceSource,
    SQLiteMemoryStore,
    explicit_provenance,
    untrusted_provenance,
)

HOST_A = "host-a"
HOST_B = "host-b"


def explicit(label: str, *, now: datetime | None = None):  # type: ignore[no-untyped-def]
    return explicit_provenance(source_id=label, source_label=label, now=now)


async def test_candidate_confirmation_correction_conflict_and_retrieval(tmp_path: Path) -> None:
    now = datetime(2026, 8, 29, 12, tzinfo=UTC)
    async with SQLiteMemoryStore(tmp_path / "memory.db") as store:
        candidate = await store.propose(
            host_id=HOST_A,
            category=MemoryCategory.PROFILE,
            key="preference.status",
            content="Prefers concise weekly status reports",
            confidence=0.95,
            provenance=untrusted_provenance(
                source_type=ProvenanceSource.MESSAGE,
                source_id="message-1",
                source_label="synthetic host statement",
                conversation_id="conversation-1",
                message_id="message-1",
                source_content="I prefer concise weekly status reports",
                now=now,
            ),
            now=now,
        )
        assert candidate.state is MemoryState.CANDIDATE
        assert await store.search(MemoryQuery(host_id=HOST_A, text="weekly status")) == ()

        with pytest.raises(MemoryNotFoundError):
            await store.promote(
                MemoryConfirmation(
                    host_id=HOST_B,
                    interface=ConfirmationInterface.TEST,
                    candidate_id=candidate.id,
                    expected_version=candidate.version,
                    expected_content_sha256=candidate.content_sha256,
                    confirmed_at=now,
                )
            )
        with pytest.raises(MemoryStateError, match="content changed"):
            await store.promote(
                MemoryConfirmation(
                    host_id=HOST_A,
                    interface=ConfirmationInterface.TEST,
                    candidate_id=candidate.id,
                    expected_version=candidate.version,
                    expected_content_sha256="0" * 64,
                    confirmed_at=now,
                )
            )

        committed = await store.promote(
            MemoryConfirmation(
                host_id=HOST_A,
                interface=ConfirmationInterface.TEST,
                candidate_id=candidate.id,
                expected_version=candidate.version,
                expected_content_sha256=candidate.content_sha256,
                confirmed_at=now,
            )
        )
        assert committed.state is MemoryState.COMMITTED
        assert {item.trust.value for item in committed.provenance} == {
            "trusted_host",
            "untrusted_content",
        }
        hit = (await store.search(MemoryQuery(host_id=HOST_A, text="weekly status")))[0]
        assert hit.item.id == committed.id
        assert "untrusted-source provenance" in hit.reason

        conflicting = await store.remember(
            host_id=HOST_A,
            category=MemoryCategory.PROFILE,
            key="preference.status",
            content="Prefers detailed weekly status reports",
            provenance=explicit("explicit-conflict", now=now),
            now=now + timedelta(minutes=1),
        )
        assert conflicting.conflict_ids
        conflict = (await store.list_conflicts(host_id=HOST_A))[0]
        assert {conflict.left_memory_id, conflict.right_memory_id} == {
            committed.id,
            conflicting.id,
        }
        conflict_hits = await store.search(
            MemoryQuery(host_id=HOST_A, text="weekly status reports")
        )
        assert all("OPEN CONTRADICTION" in item.reason for item in conflict_hits)

        resolved = await store.resolve_conflict(
            host_id=HOST_A,
            conflict_id=conflict.id,
            winner_memory_id=conflicting.id,
            now=now + timedelta(minutes=2),
        )
        assert resolved.winner_memory_id == conflicting.id
        assert (
            await store.get(host_id=HOST_A, memory_id=committed.id)
        ).state is MemoryState.CORRECTED  # type: ignore[union-attr]

        correction = await store.correct(
            host_id=HOST_A,
            memory_id=conflicting.id,
            expected_version=conflicting.version,
            content="Prefers concise monthly status reports",
            provenance=explicit("explicit-correction", now=now),
            now=now + timedelta(minutes=3),
        )
        assert correction.supersedes_id == conflicting.id
        old = await store.get(host_id=HOST_A, memory_id=conflicting.id)
        assert old is not None and old.state is MemoryState.CORRECTED
        assert not await store.search(MemoryQuery(host_id=HOST_A, text="detailed weekly"))
        assert (await store.search(MemoryQuery(host_id=HOST_A, text="concise monthly")))[
            0
        ].item.id == correction.id


async def test_deduplication_retention_and_candidate_replay_fail_closed(tmp_path: Path) -> None:
    now = datetime(2026, 8, 29, 12, tzinfo=UTC)
    async with SQLiteMemoryStore(tmp_path / "memory.db") as store:
        first = await store.remember(
            host_id=HOST_A,
            category=MemoryCategory.WORKING,
            key="working.focus",
            content="Focus on synthetic migration fixtures",
            provenance=explicit("first", now=now),
            now=now,
        )
        duplicate = await store.remember(
            host_id=HOST_A,
            category=MemoryCategory.WORKING,
            key="working.focus",
            content="Focus on synthetic migration fixtures",
            provenance=explicit("second", now=now),
            now=now,
        )
        assert duplicate.id == first.id
        assert len(duplicate.provenance) == 2

        await store.set_retention_rule(
            host_id=HOST_A,
            category=MemoryCategory.WORKING,
            retention_days=2,
            now=now,
        )
        updated = await store.get(host_id=HOST_A, memory_id=first.id)
        assert updated is not None and updated.expires_at == now + timedelta(days=2)
        result = await store.expire_due(host_id=HOST_A, now=now + timedelta(days=3))
        assert result.expired_memory_ids == (first.id,)
        expired = await store.get(host_id=HOST_A, memory_id=first.id)
        assert expired is not None and expired.state is MemoryState.EXPIRED
        assert await store.search(MemoryQuery(host_id=HOST_A, text="migration fixtures")) == ()

        candidate = await store.propose(
            host_id=HOST_A,
            category=MemoryCategory.TASK,
            key="task.synthetic",
            content="Run the synthetic task",
            confidence=0.8,
            provenance=untrusted_provenance(
                source_type=ProvenanceSource.MESSAGE,
                source_id="message-2",
                source_label="synthetic",
                conversation_id="conversation-2",
                message_id="message-2",
                now=now,
            ),
            now=now,
        )
        confirmation = MemoryConfirmation(
            host_id=HOST_A,
            interface=ConfirmationInterface.TEST,
            candidate_id=candidate.id,
            expected_version=candidate.version,
            expected_content_sha256=candidate.content_sha256,
            confirmed_at=now,
        )
        await store.promote(confirmation)
        with pytest.raises(MemoryStateError, match="not a promotable candidate"):
            await store.promote(confirmation)


async def test_host_isolation_across_all_mutating_and_retrieval_paths(tmp_path: Path) -> None:
    async with SQLiteMemoryStore(tmp_path / "memory.db") as store:
        private = await store.remember(
            host_id=HOST_A,
            category=MemoryCategory.PROFILE,
            key="profile.synthetic",
            content="Synthetic private host profile",
            provenance=explicit("host-a-explicit"),
            sensitivity=SensitivityClass.PRIVATE,
        )

        assert await store.get(host_id=HOST_B, memory_id=private.id) is None
        assert await store.list(host_id=HOST_B) == ()
        assert await store.search(MemoryQuery(host_id=HOST_B, text="synthetic profile")) == ()
        with pytest.raises(MemoryNotFoundError):
            await store.delete(host_id=HOST_B, memory_id=private.id)
        with pytest.raises(MemoryNotFoundError):
            await store.correct(
                host_id=HOST_B,
                memory_id=private.id,
                expected_version=private.version,
                content="cross-host mutation",
                provenance=explicit("host-b-explicit"),
            )
        assert (await store.get(host_id=HOST_A, memory_id=private.id)).content == private.content  # type: ignore[union-attr]


async def test_transitive_deletion_removes_fts_provenance_conflicts_and_sole_sources(
    tmp_path: Path,
) -> None:
    database = tmp_path / "memory.db"
    async with SQLiteMemoryStore(database) as store:
        source_one = await store.remember(
            host_id=HOST_A,
            category=MemoryCategory.SEMANTIC,
            key="source.one",
            content="Synthetic source alpha",
            provenance=explicit("source-one"),
        )
        source_two = await store.remember(
            host_id=HOST_A,
            category=MemoryCategory.SEMANTIC,
            key="source.two",
            content="Synthetic source beta",
            provenance=explicit("source-two"),
        )
        derived = await store.create_derived(
            host_id=HOST_A,
            category=MemoryCategory.SEMANTIC,
            key="derived.summary",
            content="Synthetic combined summary",
            source_memory_ids=(source_one.id, source_two.id),
            derivation_type="summary",
        )
        conflict = await store.remember(
            host_id=HOST_A,
            category=MemoryCategory.SEMANTIC,
            key="source.one",
            content="Contradictory synthetic source alpha",
            provenance=explicit("conflict"),
        )
        assert conflict.conflict_ids

        first_receipt = await store.delete(host_id=HOST_A, memory_id=source_one.id)
        assert first_receipt.canonical_rows == 1
        assert await store.get(host_id=HOST_A, memory_id=derived.id) is not None
        second_receipt = await store.delete(host_id=HOST_A, memory_id=source_two.id)
        assert set(second_receipt.deleted_memory_ids) == {source_two.id, derived.id}
        assert second_receipt.canonical_rows == 2
        assert await store.search(MemoryQuery(host_id=HOST_A, text="combined summary")) == ()

    with closing(sqlite3.connect(database)) as connection:
        remaining = connection.execute(
            "SELECT count(*) FROM memory_items WHERE id IN (?, ?, ?)",
            (source_one.id, source_two.id, derived.id),
        ).fetchone()[0]
        fts = connection.execute(
            "SELECT count(*) FROM memory_fts WHERE memory_id IN (?, ?, ?)",
            (source_one.id, source_two.id, derived.id),
        ).fetchone()[0]
        provenance = connection.execute(
            "SELECT count(*) FROM memory_provenance WHERE memory_id IN (?, ?, ?)",
            (source_one.id, source_two.id, derived.id),
        ).fetchone()[0]
        tombstone_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(memory_tombstones)")
        }
        tombstones = connection.execute(
            "SELECT count(*) FROM memory_tombstones WHERE memory_id IN (?, ?, ?)",
            (source_one.id, source_two.id, derived.id),
        ).fetchone()[0]
    assert (remaining, fts, provenance) == (0, 0, 0)
    assert tombstones == 3
    assert "content" not in tombstone_columns
    assert "content_sha256" not in tombstone_columns


async def test_export_restart_backup_restore_and_corrupt_record_behavior(tmp_path: Path) -> None:
    database = tmp_path / "memory.db"
    export = tmp_path / "memory-export.json"
    backup = tmp_path / "memory-backup.db"
    store = SQLiteMemoryStore(database)
    await store.initialize()
    item = await store.remember(
        host_id=HOST_A,
        category=MemoryCategory.EPISODIC,
        key="episode.synthetic",
        content="Synthetic restart episode",
        provenance=explicit("restart"),
    )
    receipt = await store.export_json(host_id=HOST_A, destination=export)
    assert receipt.record_count == 1
    payload = json.loads(export.read_text(encoding="utf-8"))
    assert payload["memories"][0]["id"] == item.id
    with pytest.raises(FileExistsError):
        await store.export_json(host_id=HOST_A, destination=export)
    await store.backup_to(backup)
    await store.close()

    async with SQLiteMemoryStore(database) as reopened:
        assert (await reopened.get(host_id=HOST_A, memory_id=item.id)).content == item.content  # type: ignore[union-attr]
    async with SQLiteMemoryStore(backup) as restored:
        assert (await restored.search(MemoryQuery(host_id=HOST_A, text="restart episode")))[
            0
        ].item.id == item.id

    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "UPDATE memory_items SET structured_json = '{broken' WHERE id = ?", (item.id,)
        )
        connection.commit()
    async with SQLiteMemoryStore(database) as corrupt:
        with pytest.raises(MemoryCorruptionError, match="invalid memory record"):
            await corrupt.get(host_id=HOST_A, memory_id=item.id)


async def test_migration_preserves_legacy_memory_under_isolated_scope(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL
            );
            """
        )
        root = files("jarvis.memory.migrations")
        for version in range(1, 5):
            resource = next(
                item for item in root.iterdir() if item.name.startswith(f"{version:03d}_")
            )
            connection.executescript(resource.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                (version, resource.name, datetime.now(UTC).isoformat()),
            )
        connection.execute(
            "INSERT INTO memory_records VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-memory",
                "profile",
                "Legacy synthetic preference",
                "legacy explicit fixture",
                "private",
                "{}",
                datetime.now(UTC).isoformat(),
            ),
        )
        connection.commit()

    async with SQLiteMemoryStore(database) as store:
        legacy = await store.get(host_id="host-legacy", memory_id="legacy-memory")
        assert legacy is not None
        assert legacy.category is MemoryCategory.PROFILE
        assert legacy.content_sha256 != "0" * 64
        assert await store.get(host_id=HOST_A, memory_id="legacy-memory") is None
        assert (await store.search(MemoryQuery(host_id="host-legacy", text="legacy preference")))[
            0
        ].item.id == legacy.id


async def test_concurrent_independent_connections_preserve_committed_rows(tmp_path: Path) -> None:
    database = tmp_path / "concurrent.db"
    stores = [SQLiteMemoryStore(database, busy_timeout_ms=10_000) for _ in range(4)]
    for store in stores:
        await store.initialize()
    try:

        async def write(index: int) -> str:
            item = await stores[index % len(stores)].remember(
                host_id=HOST_A if index % 2 == 0 else HOST_B,
                category=MemoryCategory.TASK,
                key=f"task.concurrent.{index}",
                content=f"Synthetic concurrent task {index}",
                provenance=explicit(f"concurrent-{index}"),
            )
            return item.id

        ids = await asyncio.gather(*(write(index) for index in range(40)))
        assert len(set(ids)) == 40
        assert len(await stores[0].list(host_id=HOST_A, limit=100)) == 20
        assert len(await stores[1].list(host_id=HOST_B, limit=100)) == 20
        assert not await stores[0].search(MemoryQuery(host_id=HOST_A, text="39"))
    finally:
        await asyncio.gather(*(store.close() for store in stores))
