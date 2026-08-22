"""Durable SQLite-backed conversation storage."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Final
from uuid import uuid4

import aiosqlite
from pydantic import JsonValue

from jarvis.core.models import Conversation, Message, SensitivityClass, ToolRisk
from jarvis.memory.models import AuditOutcome, AuditRecord, MemoryKind, MemoryRecord

_MIGRATION_PATTERN: Final = re.compile(r"^(?P<version>[0-9]{3})_(?P<name>[a-z0-9_]+)\.sql$")
_DEFAULT_BUSY_TIMEOUT_MS: Final = 5_000
_DEFAULT_MAX_RECENT_MESSAGES: Final = 500


class SQLiteConversationStore:
    """Persist conversations and messages in a local SQLite database.

    A single connection is intentionally serialized: it keeps transaction boundaries
    predictable, makes ``close`` safe alongside in-flight operations, and is sufficient for
    the low-write-volume conversation workload.
    """

    def __init__(
        self,
        database_path: str | Path,
        *,
        busy_timeout_ms: int = _DEFAULT_BUSY_TIMEOUT_MS,
        max_recent_messages: int = _DEFAULT_MAX_RECENT_MESSAGES,
    ) -> None:
        if busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")
        if max_recent_messages < 1:
            raise ValueError("max_recent_messages must be positive")

        self._database_path = Path(database_path)
        self._busy_timeout_ms = busy_timeout_ms
        self._max_recent_messages = max_recent_messages
        self._connection: aiosqlite.Connection | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._operation_lock = asyncio.Lock()

    @property
    def database_path(self) -> Path:
        """Return the configured database path."""
        return self._database_path

    async def initialize(self) -> None:
        """Open the database and apply every pending packaged migration."""
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
                await self._apply_migrations(connection)
            except BaseException:
                await connection.close()
                raise

            self._connection = connection

    async def close(self) -> None:
        """Close the database safely; repeated calls are harmless."""
        async with self._operation_lock, self._lifecycle_lock:
            connection = self._connection
            self._connection = None
            if connection is not None:
                await connection.close()

    async def __aenter__(self) -> SQLiteConversationStore:
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self.close()

    async def create_conversation(
        self,
        *,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> Conversation:
        """Create and return a conversation with a collision-resistant identifier."""
        conversation = Conversation(id=str(uuid4()), metadata=dict(metadata or {}))
        timestamp = _utc_timestamp()

        async with self._operation_lock:
            connection = await self._get_connection()
            await connection.execute(
                """
                INSERT INTO conversations (id, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    conversation.id,
                    _dump_json(conversation.metadata),
                    timestamp,
                    timestamp,
                ),
            )
            await connection.commit()
        return conversation

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Return a conversation by identifier, or ``None`` when it does not exist."""
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                "SELECT id, metadata_json FROM conversations WHERE id = ?",
                (conversation_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if row is None:
            return None
        return Conversation(id=row["id"], metadata=json.loads(row["metadata_json"]))

    async def append_message(self, message: Message) -> Message:
        """Append a message and return it with a persistent message identifier."""
        stored_message = (
            message if message.id is not None else message.model_copy(update={"id": str(uuid4())})
        )
        assert stored_message.id is not None
        timestamp = _utc_timestamp()

        async with self._operation_lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN IMMEDIATE")
                async with connection.execute(
                    "SELECT 1 FROM conversations WHERE id = ?",
                    (stored_message.conversation_id,),
                ) as cursor:
                    if await cursor.fetchone() is None:
                        raise KeyError(
                            f"conversation does not exist: {stored_message.conversation_id}"
                        )

                async with connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) + 1
                    FROM messages
                    WHERE conversation_id = ?
                    """,
                    (stored_message.conversation_id,),
                ) as cursor:
                    sequence_row = await cursor.fetchone()
                assert sequence_row is not None
                sequence = int(sequence_row[0])

                await connection.execute(
                    """
                    INSERT INTO messages
                        (id, conversation_id, sequence, role, payload_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stored_message.id,
                        stored_message.conversation_id,
                        sequence,
                        stored_message.role.value,
                        stored_message.model_dump_json(),
                        timestamp,
                    ),
                )
                await connection.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (timestamp, stored_message.conversation_id),
                )
                await connection.commit()
            except BaseException:
                await connection.rollback()
                raise

        return stored_message

    async def recent_messages(
        self,
        conversation_id: str,
        *,
        limit: int,
    ) -> Sequence[Message]:
        """Return at most ``limit`` recent messages in chronological order."""
        if not 1 <= limit <= self._max_recent_messages:
            raise ValueError(f"limit must be between 1 and {self._max_recent_messages}, inclusive")

        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                """
                SELECT payload_json
                FROM (
                    SELECT sequence, payload_json
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY sequence DESC
                    LIMIT ?
                )
                ORDER BY sequence ASC
                """,
                (conversation_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()

        return [Message.model_validate_json(row["payload_json"]) for row in rows]

    async def delete_conversation(self, conversation_id: str) -> bool:
        """Delete one conversation and its messages transactionally."""
        async with self._operation_lock:
            connection = await self._get_connection()
            cursor = await connection.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            )
            await connection.commit()
            return cursor.rowcount > 0

    async def create_memory(
        self,
        *,
        kind: MemoryKind,
        content: str,
        provenance: str,
        sensitivity: SensitivityClass = SensitivityClass.PRIVATE,
        metadata: Mapping[str, JsonValue] | None = None,
    ) -> MemoryRecord:
        """Create an explicit, inspectable memory record. No automatic extraction occurs."""
        record = MemoryRecord(
            id=str(uuid4()),
            kind=kind,
            content=content,
            provenance=provenance,
            sensitivity=sensitivity,
            metadata=dict(metadata or {}),
            created_at=datetime.now(UTC),
        )
        async with self._operation_lock:
            connection = await self._get_connection()
            await connection.execute(
                """
                INSERT INTO memory_records
                    (id, kind, content, provenance, sensitivity, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.kind.value,
                    record.content,
                    record.provenance,
                    record.sensitivity.value,
                    _dump_json(record.metadata),
                    record.created_at.isoformat(timespec="microseconds"),
                ),
            )
            await connection.commit()
        return record

    async def list_memories(self, *, limit: int = 100) -> Sequence[MemoryRecord]:
        if not 1 <= limit <= 500:
            raise ValueError("memory limit must be between 1 and 500")
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                "SELECT * FROM memory_records ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            MemoryRecord(
                id=row["id"],
                kind=row["kind"],
                content=row["content"],
                provenance=row["provenance"],
                sensitivity=row["sensitivity"],
                metadata=json.loads(row["metadata_json"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete one durable memory; returns whether it existed."""
        async with self._operation_lock:
            connection = await self._get_connection()
            cursor = await connection.execute(
                "DELETE FROM memory_records WHERE id = ?", (memory_id,)
            )
            await connection.commit()
            return cursor.rowcount > 0

    async def append_audit_record(
        self,
        *,
        conversation_id: str | None,
        action: str,
        outcome: AuditOutcome | str,
        risk: ToolRisk | str,
        detail: Mapping[str, JsonValue] | None = None,
    ) -> AuditRecord:
        record = AuditRecord(
            id=str(uuid4()),
            conversation_id=conversation_id,
            action=action,
            outcome=outcome,
            risk=risk,
            detail=dict(detail or {}),
            created_at=datetime.now(UTC),
        )
        async with self._operation_lock:
            connection = await self._get_connection()
            await connection.execute(
                """
                INSERT INTO audit_records
                    (id, conversation_id, action, outcome, risk, detail_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.conversation_id,
                    record.action,
                    record.outcome.value,
                    record.risk.value,
                    _dump_json(record.detail),
                    record.created_at.isoformat(timespec="microseconds"),
                ),
            )
            await connection.commit()
        return record

    async def list_audit_records(self, *, limit: int = 100) -> Sequence[AuditRecord]:
        if not 1 <= limit <= 500:
            raise ValueError("audit limit must be between 1 and 500")
        async with self._operation_lock:
            connection = await self._get_connection()
            async with connection.execute(
                "SELECT * FROM audit_records ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            AuditRecord(
                id=row["id"],
                conversation_id=row["conversation_id"],
                action=row["action"],
                outcome=row["outcome"],
                risk=row["risk"],
                detail=json.loads(row["detail_json"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    async def _get_connection(self) -> aiosqlite.Connection:
        await self.initialize()
        connection = self._connection
        if connection is None:  # Defensive: initialize either succeeds or raises.
            raise RuntimeError("SQLite conversation store is not initialized")
        return connection

    @staticmethod
    async def _apply_migrations(connection: aiosqlite.Connection) -> None:
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL
            )
            """
        )
        await connection.commit()

        async with connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ) as cursor:
            applied = {int(row[0]): str(row[1]) for row in await cursor.fetchall()}

        migration_root = files("jarvis.memory.migrations")
        migrations: list[tuple[int, str, str]] = []
        for resource in migration_root.iterdir():
            match = _MIGRATION_PATTERN.fullmatch(resource.name)
            if match is None:
                continue
            migrations.append(
                (
                    int(match.group("version")),
                    resource.name,
                    resource.read_text(encoding="utf-8"),
                )
            )

        seen_versions: set[int] = set()
        for version, name, sql in sorted(migrations):
            if version in seen_versions:
                raise RuntimeError(f"duplicate SQLite migration version: {version:03d}")
            seen_versions.add(version)

            applied_name = applied.get(version)
            if applied_name is not None:
                if applied_name != name:
                    raise RuntimeError(
                        f"migration {version:03d} was applied as {applied_name!r}, not {name!r}"
                    )
                continue

            timestamp = _utc_timestamp()
            script = (
                "BEGIN IMMEDIATE;\n"
                f"{sql.rstrip()}\n"
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES "
                f"({version}, {_sql_literal(name)}, {_sql_literal(timestamp)});\n"
                "COMMIT;"
            )
            try:
                await connection.executescript(script)
            except BaseException:
                await connection.rollback()
                raise


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
