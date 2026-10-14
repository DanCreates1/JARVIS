"""Durable phone chat reservations and exact device-owned conversation reads."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import aiosqlite

from jarvis.memory.sqlite_store import SQLiteConversationStore
from jarvis.remote.models import RemoteIdentityContext

MAX_CHAT_RESPONSE_BYTES = 131_072


class PWAChatError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def chat_result(
    request_id: str,
    conversation_id: str | None,
    status: str,
    *,
    reply: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    truncated = reply is not None and len(reply.encode("utf-8")) > 100_000
    if truncated and reply is not None:
        reply = reply.encode("utf-8")[:100_000].decode("utf-8", errors="ignore")
    result: dict[str, Any] = {
        "request_id": request_id,
        "conversation_id": conversation_id,
        "status": status,
        "reply": reply,
        "error": {"code": error, "message": "Chat request did not complete."} if error else None,
    }
    if truncated:
        result["reply_truncated"] = True
    while len(_dump(result).encode("utf-8")) > MAX_CHAT_RESPONSE_BYTES - 1024:
        assert isinstance(result["reply"], str)
        result["reply"] = result["reply"][: len(result["reply"]) // 2]
        result["reply_truncated"] = True
    return result


class SQLitePWAChatStore:
    """Reserve once before starting Core work; retain terminal outcomes across sessions/restart."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._connection: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self._lock:
            if self._connection is not None:
                return
            connection = await aiosqlite.connect(self._database_path)
            connection.row_factory = aiosqlite.Row
            try:
                await connection.execute("PRAGMA foreign_keys = ON")
                await connection.execute("PRAGMA busy_timeout = 5000")
                await SQLiteConversationStore._apply_migrations(connection)
            except BaseException:
                await connection.close()
                raise
            self._connection = connection

    async def close(self) -> None:
        async with self._lock:
            connection, self._connection = self._connection, None
            if connection is not None:
                await connection.close()

    def _db(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Phone chat store unavailable")
        return self._connection

    async def recover_interrupted(self) -> None:
        """A process restart cannot prove provider outcome; never replay reserved work."""
        async with self._lock:
            connection = self._db()
            async with connection.execute(
                "SELECT host_id,device_id,request_id,conversation_id FROM pwa_chat_requests "
                "WHERE status='running'"
            ) as cursor:
                rows = await cursor.fetchall()
            for row in rows:
                result = chat_result(
                    row["request_id"], row["conversation_id"], "interrupted", error="core_restarted"
                )
                await connection.execute(
                    "UPDATE pwa_chat_requests SET status='interrupted',result_json=?,updated_at=?, "
                    "end_sequence=(SELECT COALESCE(MAX(sequence),0) FROM messages "
                    "WHERE messages.conversation_id=pwa_chat_requests.conversation_id) "
                    "WHERE host_id=? AND device_id=? AND request_id=? AND status='running'",
                    (_dump(result), _now(), row["host_id"], row["device_id"], row["request_id"]),
                )
            await connection.commit()

    async def reserve(
        self,
        *,
        context: RemoteIdentityContext,
        request_id: str,
        fingerprint: str,
        conversation_id: str | None,
    ) -> tuple[bool, dict[str, Any]]:
        async with self._lock:
            connection = self._db()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                async with connection.execute(
                    "SELECT fingerprint,result_json FROM pwa_chat_requests "
                    "WHERE host_id=? AND device_id=? AND request_id=?",
                    (context.host_id, context.device_id, request_id),
                ) as cursor:
                    existing = await cursor.fetchone()
                if existing is not None:
                    if existing["fingerprint"] and existing["fingerprint"] != fingerprint:
                        raise PWAChatError("request_conflict")
                    existing_result = cast(dict[str, Any], json.loads(existing["result_json"]))
                    if existing_result["conversation_id"] is not None:
                        await self._require_owner(
                            connection, context, existing_result["conversation_id"]
                        )
                    await connection.commit()
                    return False, existing_result
                async with connection.execute(
                    "SELECT 1 FROM pwa_chat_requests WHERE host_id=? AND device_id=? "
                    "AND status='running'",
                    (context.host_id, context.device_id),
                ) as cursor:
                    if await cursor.fetchone() is not None:
                        raise PWAChatError("request_running")
                timestamp = _now()
                if conversation_id is None:
                    conversation_id = str(uuid4())
                    await connection.execute(
                        "INSERT INTO conversations(id,metadata_json,created_at,updated_at) "
                        "VALUES (?,?,?,?)",
                        (conversation_id, '{"interface":"browser"}', timestamp, timestamp),
                    )
                    await connection.execute(
                        "INSERT INTO pwa_conversation_owners VALUES (?,?,?,?)",
                        (conversation_id, context.host_id, context.device_id, timestamp),
                    )
                else:
                    await self._require_owner(connection, context, conversation_id)
                result = chat_result(request_id, conversation_id, "running")
                async with connection.execute(
                    "SELECT COALESCE(MAX(sequence),0) FROM messages WHERE conversation_id=?",
                    (conversation_id,),
                ) as cursor:
                    sequence = await cursor.fetchone()
                assert sequence is not None
                await connection.execute(
                    "INSERT INTO pwa_chat_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        context.host_id,
                        context.device_id,
                        request_id,
                        fingerprint,
                        conversation_id,
                        context.session_id,
                        int(sequence[0]),
                        None,
                        "running",
                        _dump(result),
                        timestamp,
                        timestamp,
                    ),
                )
                await connection.commit()
                return True, result
            except BaseException:
                await connection.rollback()
                raise

    async def cancel_unknown(
        self, *, context: RemoteIdentityContext, request_id: str
    ) -> dict[str, Any]:
        """Commit a no-replay receipt even when cancellation overtakes the initial POST."""
        async with self._lock:
            connection = self._db()
            await connection.execute("BEGIN IMMEDIATE")
            try:
                async with connection.execute(
                    "SELECT result_json FROM pwa_chat_requests "
                    "WHERE host_id=? AND device_id=? AND request_id=?",
                    (context.host_id, context.device_id, request_id),
                ) as cursor:
                    existing = await cursor.fetchone()
                if existing is not None:
                    await connection.commit()
                    return cast(dict[str, Any], json.loads(existing["result_json"]))
                async with connection.execute(
                    "SELECT COUNT(*) FROM pwa_chat_requests WHERE host_id=? AND device_id=? "
                    "AND fingerprint=''",
                    (context.host_id, context.device_id),
                ) as cursor:
                    count = await cursor.fetchone()
                assert count is not None
                if int(count[0]) >= 1024:
                    raise PWAChatError("chat_capacity")
                result = chat_result(request_id, None, "cancelled", error="cancelled")
                timestamp = _now()
                await connection.execute(
                    "INSERT INTO pwa_chat_requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        context.host_id,
                        context.device_id,
                        request_id,
                        "",
                        None,
                        context.session_id,
                        0,
                        0,
                        "cancelled",
                        _dump(result),
                        timestamp,
                        timestamp,
                    ),
                )
                await connection.commit()
                return result
            except BaseException:
                await connection.rollback()
                raise

    async def complete(
        self, *, context: RemoteIdentityContext, request_id: str, result: dict[str, Any]
    ) -> None:
        encoded = _dump(result)
        if len(encoded.encode("utf-8")) > MAX_CHAT_RESPONSE_BYTES:
            raise PWAChatError("response_too_large")
        async with self._lock:
            connection = self._db()
            await connection.execute(
                "UPDATE pwa_chat_requests SET status=?,result_json=?,updated_at=?, "
                "end_sequence=(SELECT COALESCE(MAX(sequence),0) FROM messages "
                "WHERE messages.conversation_id=pwa_chat_requests.conversation_id) "
                "WHERE host_id=? AND device_id=? AND request_id=? AND status='running'",
                (
                    result["status"],
                    encoded,
                    _now(),
                    context.host_id,
                    context.device_id,
                    request_id,
                ),
            )
            await connection.commit()

    async def get(self, *, context: RemoteIdentityContext, request_id: str) -> dict[str, Any]:
        async with (
            self._lock,
            self._db().execute(
                "SELECT result_json,conversation_id FROM pwa_chat_requests "
                "WHERE host_id=? AND device_id=? AND request_id=?",
                (context.host_id, context.device_id, request_id),
            ) as cursor,
        ):
            row = await cursor.fetchone()
            if row is not None and row["conversation_id"] is not None:
                await self._require_owner(self._db(), context, row["conversation_id"])
        if row is None:
            raise PWAChatError("request_not_found")
        return cast(dict[str, Any], json.loads(row["result_json"]))

    async def conversations(self, context: RemoteIdentityContext) -> dict[str, Any]:
        async with self._lock:
            connection = self._db()
            async with connection.execute(
                "SELECT c.id,c.updated_at FROM conversations c JOIN pwa_conversation_owners o "
                "ON o.conversation_id=c.id WHERE o.host_id=? AND o.device_id=? "
                "AND c.attachment_private=0 AND c.email_private=0 "
                "ORDER BY c.updated_at DESC,c.id DESC LIMIT 20",
                (context.host_id, context.device_id),
            ) as cursor:
                rows = list(await cursor.fetchall())
            async with connection.execute(
                "SELECT r.result_json FROM pwa_chat_requests r JOIN conversations c "
                "ON c.id=r.conversation_id WHERE host_id=? AND device_id=? "
                "AND status='running' AND c.attachment_private=0 AND c.email_private=0 LIMIT 1",
                (context.host_id, context.device_id),
            ) as cursor:
                active = await cursor.fetchone()
        return {
            "conversations": [dict(row) for row in rows],
            "active_request": json.loads(active["result_json"]) if active else None,
        }

    async def messages(
        self,
        *,
        context: RemoteIdentityContext,
        conversation_id: str,
        before: int | None,
        limit: int,
    ) -> dict[str, Any]:
        async with self._lock:
            connection = self._db()
            await self._require_owner(connection, context, conversation_id)
            async with connection.execute(
                "SELECT m.id,m.sequence,m.role,m.payload_json, "
                "json_extract(m.payload_json,'$.client_request_id') AS request_id "
                "FROM messages m WHERE m.conversation_id=? "
                "AND EXISTS (SELECT 1 FROM pwa_chat_requests r "
                "WHERE r.conversation_id=m.conversation_id "
                "AND r.request_id=json_extract(m.payload_json,'$.client_request_id') "
                "AND r.host_id=? AND r.device_id=?) "
                "AND (m.role='user' OR (m.role='assistant' "
                "AND json_array_length(json_extract(m.payload_json,'$.tool_calls'))=0 "
                "AND trim(COALESCE(json_extract(m.payload_json,'$.content'),''))<>'')) "
                "AND (? IS NULL OR sequence < ?) "
                "ORDER BY sequence DESC LIMIT ?",
                (conversation_id, context.host_id, context.device_id, before, before, limit + 1),
            ) as cursor:
                rows = list(await cursor.fetchall())
            async with connection.execute(
                "SELECT result_json FROM pwa_chat_requests WHERE host_id=? AND device_id=? "
                "AND conversation_id=? ORDER BY created_at DESC LIMIT 20",
                (context.host_id, context.device_id, conversation_id),
            ) as cursor:
                request_rows = await cursor.fetchall()
        requests = []
        for row in request_rows:
            summary = json.loads(row["result_json"])
            summary.pop("reply", None)
            requests.append(summary)
        result: dict[str, Any] = {
            "conversation_id": conversation_id,
            "messages": [],
            "has_more": len(rows) > limit,
            "next_before": None,
            "requests": requests,
        }
        remaining = MAX_CHAT_RESPONSE_BYTES - len(_dump(result).encode("utf-8")) - 1024
        selected: list[dict[str, Any]] = []
        for row in rows[:limit]:
            message = {
                "id": row["id"],
                "sequence": row["sequence"],
                "role": row["role"],
                "content": json.loads(row["payload_json"])["content"],
                "request_id": row["request_id"],
            }
            encoded = _dump(message).encode("utf-8")
            if len(encoded) > remaining and selected:
                result["has_more"] = True
                break
            if len(encoded) > remaining:
                message["content"] = (
                    message["content"]
                    .encode("utf-8")[: remaining // 2]
                    .decode("utf-8", errors="ignore")
                )
                message["truncated"] = True
                encoded = _dump(message).encode("utf-8")
                while len(encoded) > remaining:
                    message["content"] = message["content"][: len(message["content"]) // 2]
                    encoded = _dump(message).encode("utf-8")
            selected.append(message)
            remaining -= len(encoded)
        result["messages"] = list(reversed(selected))
        result["next_before"] = selected[-1]["sequence"] if selected else None
        return result

    @staticmethod
    async def _require_owner(
        connection: aiosqlite.Connection,
        context: RemoteIdentityContext,
        conversation_id: str,
    ) -> None:
        async with connection.execute(
            "SELECT 1 FROM pwa_conversation_owners o JOIN conversations c "
            "ON c.id=o.conversation_id "
            "WHERE o.conversation_id=? AND o.host_id=? AND o.device_id=? "
            "AND c.attachment_private=0 AND c.email_private=0",
            (conversation_id, context.host_id, context.device_id),
        ) as cursor:
            if await cursor.fetchone() is None:
                raise PWAChatError("conversation_not_found")


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")
